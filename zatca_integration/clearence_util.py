import json
from datetime import datetime, date, timedelta
from dateutil.parser import parse
import uuid
import frappe
from frappe.model.document import Document
import time
import requests
import base64
from requests.auth import HTTPBasicAuth
from lxml import etree
import qrcode
from zatca_integration.common_util import decode_invoice, get_seller_information, get_buyer_information, generate_clearance_request, generate_reporting_request

def generate_einvoice(doc, method):

    # Seller Information
    company = frappe.get_doc("Company", doc.company)

    # Check if Company is a Saudi Arabia based company
    if company.country != "Saudi Arabia":
        return

    # Check if ZATCA E-Invoicing is enabled
    if not company.custom_enable_zatca_e_invoicing == 1:
        return

    # Check if the active Zacta Phase is Phase 2
    if not company.custom_zatca_phase == "ZATCA Phase 2":
        return 
        
    # CSID, Compliance CSID, CSR, and Environment from Company ZATCA Settings
    production_csid = frappe.get_doc("Production CSID", company.custom_production_csid)
    compliance_csid = frappe.get_doc("Compliance CSID", production_csid.compliance_csid)
    compliance_csr = frappe.get_doc("Zatca CSR Settings", compliance_csid.csr_settings)
    zatca_environment = frappe.get_doc("Zatca Environment", compliance_csr.zatca_environment)

    seller = get_seller_information(compliance_csr)

    # Buyer Information
    customer = frappe.get_doc("Customer", doc.customer)
    customer_type = customer.customer_type
    if customer_type == "Company":
        invoice_type = "0100000"
    elif customer_type == "Individual":
        invoice_type = "0200000"
    else :
        frappe.throw("Customer Type is not Supported")

    buyer = get_buyer_information(doc.customer)
    
    # Check invoice type stndard, credit note or debit note    
    if doc.is_return:
        invoice_type_code = "381"
        invoice_document_reference = doc.return_against
    elif doc.is_debit_note:
        invoice_type_code = "383"
        invoice_document_reference = doc.debit_to
        frappe.throw("Debit Note is not Supported")
    else:
        invoice_type_code = "388"
        invoice_document_reference = ""
    
    # Set Invoice Number and Invoice Unique Identifier 
    invoiceNumber = doc.name
    uniqueInvoiceIdentifier = str(uuid.uuid4())

    # Set Invoice Counter Value(ICV)
    previousInvoiceCounter = int(get_previous_invoice_counter(production_csid.name))
    invoiceCounterValue = previousInvoiceCounter + 1

    # Set Previous Invoice Hash Value(PIH)
    previousInvoiceHash = get_previous_invoice_hash(production_csid.name)

    # Set Posting Date and Time to current date and time
    doc.posting_date = frappe.utils.now_datetime().strftime("%Y-%m-%d")
    doc.posting_time = frappe.utils.now_datetime().strftime("%H:%M:%S")
    
    # Set Invoice Date and Time
    invoice_date = datetime.strptime(doc.posting_date, "%Y-%m-%d").strftime("%Y-%m-%d")
    invoice_time = parse(doc.posting_time).time().strftime("%H:%M:%S")
    
    # Set and Validate Delivery Date
    if isinstance(doc.custom_delivery_date, date):
    # If it's a datetime.date object, format it as a string
        delivery_date = doc.custom_delivery_date.strftime("%Y-%m-%d")
    elif isinstance(doc.custom_delivery_date, str):
    # If it's a string, parse it into a datetime object
        delivery_date = datetime.strptime(doc.custom_delivery_date, "%Y-%m-%d").strftime("%Y-%m-%d")
    # Validate Delivery Date
    validate_delivery_date(delivery_date, invoice_date, customer_type)
    
    # Tax Template and Tax Percentage
    tax_template = frappe.get_doc("Sales Taxes and Charges Template", doc.taxes_and_charges)
    if not tax_template:
        frappe.throw("Sales Taxes and Charges Template must be provided.")
    tax_type = tax_template.custom_tax_type
    if tax_type == "Standard Rate":
        tax_category = "S"
        tax_percentage =  15
        tax_exemption_reason, tax_exemption_code = "", ""
    elif tax_type == "Zero Rate":
        tax_category = "Z"
        tax_percentage =  0
        tax_exemption_reason, tax_exemption_code = get_tax_exemption_code(tax_template.custom_zero_rate_reason)
    elif tax_type == "Except Rate":
        tax_category = "E"
        tax_percentage =  0
        tax_exemption_reason, tax_exemption_code = get_tax_exemption_code(tax_template.custom_except_rate_reason)
    else:
        frappe.throw("Tax Type is not Supported")

    # Validate Currency, Only SAR is supported
    currency = doc.currency
    if currency == "SAR":
        print("Currency SAR is Supported")
        document_currency_code = "SAR"
        tax_currency_code = "SAR"
    elif currency == "USD":
        document_currency_code = "USD"
        tax_currency_code = "SAR"
        print("Currency USD is Supported")
    else:
        frappe.throw("Currency is not Supported")

    # PaymentMeansCode
    payment_means_code = get_payment_means_code(doc.custom_payment_means)
        
    # Advance Payment Not Supported
    total_advance = doc.total_advance
    if total_advance > 0:
        frappe.throw("Advance Payment is not Supported")

    # Prepare Line Items Details
    line_items = []
    for item in doc.items:
        unit_price = round_to_four_places(abs(item.net_rate))
        taxable_amount = round_to_two_places(unit_price * abs(item.qty))
        tax_mount = round_to_two_places(taxable_amount * tax_percentage / 100)
        payable_amount = round_to_two_places(taxable_amount + tax_mount)
        line_item = {
            "line_number": item.idx,
            "item_name": item.item_name,
            "quantity": abs(item.qty),
            "unit_code": "C62",  # TODO: From Item
            "unit_price": unit_price,
            "tax_Percentage": tax_percentage,
            "taxable_amount": taxable_amount,
            "tax_mount": tax_mount,
            "payable_amount": payable_amount,
        }
        line_items.append(line_item)

    # Render Invoice XML from Template
    invoice_xml = frappe.render_template("zatca_integration/templates/zatca/clearence/Standard_Invoice.xml", {
        "invoice_type": invoice_type,
        "invoice_type_code": invoice_type_code,
        "invoice_document_reference": invoice_document_reference,
        "invoiceNumber": invoiceNumber,
        "invoiceCounterValue": invoiceCounterValue,
        "uniqueInvoiceIdentifier": uniqueInvoiceIdentifier,
        "previousInvoiceHash": previousInvoiceHash,
        "invoice_date": invoice_date,
        "invoice_time": invoice_time,
        "delivery_date": delivery_date,
        "seller": seller,
        "buyer": buyer,

        # Payment
        "payment_means_code": payment_means_code,

        # Currency
        "document_currency_code": document_currency_code,
        "tax_currency_code": tax_currency_code,
    
        # TaxTotal and MonetaryTotal
        "taxableAmount": abs(doc.net_total),
        "taxAmount": abs(doc.total_taxes_and_charges),
        "taxAmountBaseCurrency": abs(doc.base_total_taxes_and_charges),
        "payableAmount": abs(doc.grand_total),
        "taxPercentage": tax_percentage,
        "tax_category": tax_category,
        "tax_exemption_code": tax_exemption_code,
        "tax_exemption_reason": tax_exemption_reason,
        
        # Line Items
        "line_items": line_items,
    })

    print(invoice_xml)

    try:
        if customer_type == "Company":

            backend_start_time = time.time()
            invoice_request = generate_clearance_request(
                zatca_environment.csr_generate_api, 
                zatca_environment.client_id, 
                zatca_environment.client_secret, 
                invoice_xml
            )
            backend_end_time = time.time()
            backend_time_taken = backend_end_time - backend_start_time

            zatca_start_time = time.time()
            response = requests.post(
                zatca_environment.invoice_clearance_api, 
                headers=get_clearence_headers(),
                auth=HTTPBasicAuth(production_csid.binary_security_token, production_csid.secret), 
                data=json.dumps(invoice_request)
            )
            zatca_end_time = time.time()
            zatca_time_taken = zatca_end_time - zatca_start_time

            zatca_status_field = 'clearanceStatus'
        elif customer_type == "Individual":

            backend_start_time = time.time()
            invoice_request = generate_reporting_request(
                zatca_environment.csr_generate_api, 
                zatca_environment.client_id, 
                zatca_environment.client_secret,
                compliance_csr.private_key,
                decode_certificate(production_csid.binary_security_token),
                invoice_xml
            )
            backend_end_time = time.time()
            backend_time_taken = backend_end_time - backend_start_time

            zatca_start_time = time.time()
            response = requests.post(
                zatca_environment.invoice_reporting_api, 
                headers=get_clearence_headers(),
                auth=HTTPBasicAuth(production_csid.binary_security_token, production_csid.secret), 
                data=json.dumps(invoice_request)
            )
            zatca_end_time = time.time()
            zatca_time_taken = zatca_end_time - zatca_start_time

            zatca_status_field = 'reportingStatus'

        else :
            frappe.throw("Customer Type is not Supported")
        response_json = response.json()
    except ValueError:
        response_json = None
    except requests.exceptions.RequestException as e:
        frappe.throw("Error Clearing Invoice, " + str(e))

    print(response_json)

    # Save Transaction
    transaction = frappe.get_doc({
            'doctype': 'Zatca Transactions',
            'invoice_id': doc.name,
            'invoice_uuid': uniqueInvoiceIdentifier,
            'invoice_icv': invoiceCounterValue,
            'invoice_hash': invoice_request.get('invoiceHash'),
            'previous_invoice_hash': previousInvoiceHash,
            'egs_serial_number': compliance_csr.csrserialnumber,
            'production_csid': production_csid.name,
            'request_body': json.dumps(invoice_request),
            'response_code': response.status_code,
            'response_body': json.dumps(response_json),
            'backend_elapsed_time': backend_time_taken * 1000,
            'zatca_elapsed_time': zatca_time_taken * 1000,
            'transaction_time': frappe.utils.now_datetime(),
        })
    transaction.insert()

    # Handle Response
    if response.status_code == 200 or response.status_code == 202:
        doc.custom_invoice_type = invoice_type
        doc.custom_invoice_hash = invoice_request.get('invoiceHash')
        doc.custom_invoice_unique_identifier = uniqueInvoiceIdentifier
        doc.custom_invoice_icv = invoiceCounterValue

        doc.custom_zatca_submit_status = response_json.get(zatca_status_field)
        doc.custom_zatca_submit_time = frappe.utils.now_datetime()
        doc.custom_validation_results = json.dumps(response_json.get('validationResults', ''))

        doc.custom_seller_name = seller.get('organizationName')
        doc.custom_seller_vat = seller.get('vatNumber')
        doc.custom_seller_address = seller.get('full_address')
        doc.custom_buyer_name = buyer.get('organizationName')
        doc.custom_buyer_vat = buyer.get('vatNumber')
        doc.custom_buyer_address = buyer.get('full_address')
        
        # Save Cleared Invoice XML
        if customer_type == "Company":
            cleared_invoice_xml = decode_invoice(response_json.get('clearedInvoice'))
        elif customer_type == "Individual":
            cleared_invoice_xml = decode_invoice(invoice_request.get('invoice'))
        else :
            frappe.throw("Customer Type is not Supported")

        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": invoiceNumber + ".xml",
            "content": cleared_invoice_xml,
            "is_private": True
        })
        file_doc.insert()
        doc.custom_invoice_xml = file_doc.file_url
        
        # Save Cleared Invoice QR Code
        qr_code = extract_qr_code_from_cleared_invoice(cleared_invoice_xml)
        qr_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": invoiceNumber + ".png",
            "content": qr_code,
            "is_private": True
        })
        qr_doc.insert()
        doc.custom_invoice_qr_code = qr_doc.file_url
    elif response.status_code == 303:
        update_status_on_error(doc, 'FAILED', json.dumps(response_json.get('message', '')))
        frappe.throw("Error submitting invoice, Clearance is Deactivated")
    elif response.status_code == 400:
        update_status_on_error(doc, response_json.get(zatca_status_field), json.dumps(response_json.get('validationResults', '')))
        frappe.throw("Error submitting invoice, Bad Request")
    elif response.status_code == 401:
        update_status_on_error(doc, 'FAILED', json.dumps(response_json))
        frappe.throw("Error submitting invoice, Invalid Credentials")
    elif response.status_code == 500:
        update_status_on_error(doc, 'FAILED', json.dumps(response_json))
        frappe.throw("Error submitting invoice, Internal Server Error")
    else:
        update_status_on_error(doc, 'FAILED', json.dumps(response_json))
        frappe.throw("Error submitting invoice, Unknown Error")

def update_status_on_error(doc, status, validation_results):
    frappe.db.set_value("Sales Invoice", doc.name, "custom_zatca_submit_status", status, update_modified=True)
    frappe.db.set_value("Sales Invoice", doc.name, "custom_validation_results", validation_results, update_modified=True)
    frappe.db.set_value("Sales Invoice", doc.name, "custom_zatca_submit_time", frappe.utils.now_datetime(), update_modified=True)
    frappe.db.commit()

def get_payment_means_code(payment_means):
    if payment_means == "Cash":
        payment_means_code = "10"
    elif payment_means == "Credit":
        payment_means_code = "30"
    elif payment_means == "Bank Payment":
        payment_means_code = "42"
    elif payment_means == "Bank Card":
        payment_means_code = "48"
    else:
        payment_means_code = "10" # Default to Cash
    return payment_means_code

def get_tax_exemption_code(exempt_reason):
    reason, code = exempt_reason.split('(', 1)
    code = code.rstrip(')')
    return reason.strip(), code.strip()

def get_clearence_headers():
    return {
        'accept': 'application/json',
        'Accept-Language': 'en',
        'Clearance-Status': '1',
        'Accept-Version': 'V2',
        'Content-Type': 'application/json'
    }

def get_previous_invoice_counter(production_csid):
    # Get the latest Zatca Transaction for the given production_csid based on transaction_time
    latest_transaction = frappe.get_all('Zatca Transactions', 
                                        filters={'production_csid': production_csid}, 
                                        fields=['invoice_icv'], 
                                        order_by='transaction_time desc', 
                                        limit_page_length=1)
    if latest_transaction:
        # Return the invoice_icv of the latest transaction
        return latest_transaction[0].invoice_icv
    else:
        # Return 0 if there are no Zatca Transactions
        return 0

def get_previous_invoice_hash(production_csid):
    # Get the latest Zatca Transaction for the given production_csid based on transaction_time
    latest_transaction = frappe.get_all('Zatca Transactions', 
                                        filters={'production_csid': production_csid}, 
                                        fields=['invoice_hash'], 
                                        order_by='transaction_time desc', 
                                        limit_page_length=1)
    if latest_transaction:
        # Return the invoice_hash of the latest transaction
        return latest_transaction[0].invoice_hash
    else:
        # Return default hash if there are no Zatca Transactions
        return "NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRkNGU5MWI0NjcyOWQ3M2EyN2ZiNTdlOQ=="

def extract_qr_code_from_cleared_invoice(cleared_invoice_xml):

    # Define the namespaces used in the XML
    namespaces = {
        'cac': "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
        'cbc': "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
    }

    # Parse the XML string
    xml_tree = etree.fromstring(cleared_invoice_xml.encode('utf-8'))

    # Search for the QR Code text using relative paths
    qr_code_data = None
    for additional_document_reference in xml_tree.findall('.//cac:AdditionalDocumentReference', namespaces):
        id_element = additional_document_reference.find('./cbc:ID', namespaces)
        if id_element is not None and id_element.text == 'QR':
            embedded_document = additional_document_reference.find('./cac:Attachment/cbc:EmbeddedDocumentBinaryObject', namespaces)
            if embedded_document is not None:
                qr_code_data = embedded_document.text
                break

    if qr_code_data is not None:
        try:
            qr_code_text = base64.b64decode(qr_code_text).decode('utf-8')
        except Exception as e:
            # If there's an error in decoding, use the original data
            qr_code_text = qr_code_data

    # Generate QR code image
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_code_text)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    # Save the QR code image to a byte stream
    import io
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr = img_byte_arr.getvalue()

    return img_byte_arr

def validate_delivery_date(delivery_date, invoice_date, customer_type):
    # Validate Delivery Date
    del_date = datetime.strptime(delivery_date, "%Y-%m-%d")
    inv_date = datetime.strptime(invoice_date, "%Y-%m-%d")

    # Calculate the end of the month for the delivery date
    end_of_month = del_date.replace(day=1) + timedelta(days=32)
    end_of_month = end_of_month.replace(day=1) - timedelta(days=1)

    # Calculate the last valid date for issuing the invoice
    last_valid_invoice_date = end_of_month + timedelta(days=15)

    if customer_type == "Company":  # Standard Tax Invoices (B2B) must be issued and submitted within 15 days from the end of the month in which the supply takes place.
        if inv_date > last_valid_invoice_date:
            frappe.throw("Delivery Date is not valid, Standard Tax Invoices (B2B) must be issued and submitted within 15 days from the end of the month in which the supply takes place.")
        if del_date > inv_date:
            frappe.throw("Delivery Date is not valid, the supply must occur on or before the tax invoice date.")
    elif customer_type == "Individual":  # Delivery Date must be today, otherwise throw an error
        if del_date.date() != datetime.now().date():
            frappe.throw("Delivery Date is not valid, Delivery Date must be today")
    else:
        frappe.throw("Customer Type is not Supported")

def decode_certificate(production_certificate):
    decoded_production_certificate = base64.b64decode(production_certificate.encode('utf-8'))
    return decoded_production_certificate.decode('utf-8')

def round_to_two_places(value):
    return round(value, 2)

def round_to_four_places(value):
    return round(value, 4)