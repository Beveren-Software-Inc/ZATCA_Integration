import json
from datetime import datetime
import uuid
import frappe
from frappe.model.document import Document
import time
import requests
import base64
from requests.auth import HTTPBasicAuth
from lxml import etree
import qrcode
from zatca_integration.common_util import decode_invoice, get_seller_information, get_buyer_information, get_invoice_request

def generate_einvoice(doc, method):

    # Get Zatca Settings, Environment, CSID and CSR
    zatca_settings = frappe.get_doc("Zatca Settings", "Zatca Settings") 
    production_csid = frappe.get_doc("Production CSID", zatca_settings.default_production_csid)
    compliance_csid = frappe.get_doc("Compliance CSID", production_csid.compliance_csid)
    compliance_csr = frappe.get_doc("Zatca CSR Settings", compliance_csid.csr_settings)
    zatca_environment = frappe.get_doc("Zatca Environment", compliance_csr.zatca_environment)
    
    # Check if E-Invoicing is enabled
    if not zatca_settings.enable_e_invoicing:
        return
    
    # Generate Invoice Number, Unique Identifier and Counter Value
    invoiceNumber = doc.name
    invoiceCounterValue  = int(time.time())
    uniqueInvoiceIdentifier = str(uuid.uuid4())

    # Fetch Previous Invoice Hash or use default TODO
    previousInvoiceHash = "NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRkNGU5MWI0NjcyOWQ3M2EyN2ZiNTdlOQ=="
    
    # Fetch Seller and Buyer Information
    seller = get_seller_information(compliance_csr)
    buyer = get_buyer_information(doc.customer)
    
    # Set Invoice Date and Time, Delivery Date
    invoice_date = datetime.strptime(doc.posting_date, "%Y-%m-%d").strftime("%Y-%m-%d")
    invoice_time = datetime.strptime(doc.posting_time, "%H:%M:%S.%f").strftime("%H:%M:%S")
    delivery_date = datetime.strptime(doc.custom_delivery_date, "%Y-%m-%d").strftime("%Y-%m-%d") 
    
    # Tax Template and Tax Percentage
    tax_template = frappe.get_doc("Sales Taxes and Charges Template", doc.taxes_and_charges)
    if not tax_template:
        frappe.throw("Sales Taxes and Charges Template must be provided.")
    tax_type = tax_template.custom_tax_type
    if tax_type == "Standard Rate":
        tax_percentage =  15 #TODO Verify no other standard rate
    elif tax_type == "Zero Rate":
        frappe.throw("Zero Rate is not Supported")
    elif tax_type == "Except Rate":
        frappe.throw("Except Rate is not Supported")
    else:
        frappe.throw("Tax Type is not Supported")

    # Validate Currency, Only SAR is supported
    currency = doc.currency
    if currency != "SAR":
        frappe.throw("Currency is not Supported")

    # PaymentMeansCode TODO
        
    # Advance Payment Not Supported
    total_advance = doc.total_advance
    if total_advance > 0:
        frappe.throw("Advance Payment is not Supported")

    # Prepare Line Items Details
    line_items = []
    for item in doc.items:
        taxable_amount = item.base_amount
        tax_mount = taxable_amount * tax_percentage / 100
        payable_amount = taxable_amount + tax_mount
        line_item = {
            "line_number": item.idx,
            "item_name": item.item_name,
            "quantity": item.qty,
            "unit_code": "C62",  # TODO: From Item
            "unit_price": item.base_rate,
            "tax_Percentage": tax_percentage,
            "taxable_amount": taxable_amount,
            "tax_mount": tax_mount,
            "payable_amount": payable_amount,
        }
        line_items.append(line_item)

    # Render Invoice XML from Template
    invoice_xml = frappe.render_template("zatca_integration/templates/zatca/clearence/Standard_Invoice.xml", {
        "invoiceNumber": invoiceNumber,
        "invoiceCounterValue": invoiceCounterValue,
        "uniqueInvoiceIdentifier": uniqueInvoiceIdentifier,
        "previousInvoiceHash": previousInvoiceHash,
        "invoice_date": invoice_date,
        "invoice_time": invoice_time,
        "delivery_date": delivery_date,
        "seller": seller,
        "buyer": buyer,
    
        # TaxTotal and MonetaryTotal
        "taxableAmount": doc.base_total,
        "taxAmount": doc.base_total_taxes_and_charges,
        "payableAmount": doc.base_grand_total,
        "taxPercentage": tax_percentage,

        # Line Items
        "line_items": line_items,
    })

    # Generate Invoice Request Body from Backend API
    invoice_request = get_invoice_request(
        zatca_environment.csr_generate_api, 
        zatca_environment.client_id, 
        zatca_environment.client_secret, 
        invoice_xml
    )

    # Post Clearance Request to ZATCA API
    response = requests.post(
        zatca_environment.invoice_clearance_api, 
        headers=get_clearence_headers(),
        auth=HTTPBasicAuth(production_csid.binary_security_token, production_csid.secret), 
        data=json.dumps(invoice_request)
    )

    try:
        response_json = response.json()
    except ValueError:
        response_json = None

    if response.status_code == 200 or response.status_code == 202:
        doc.custom_invoice_hash = invoice_request.get('invoiceHash')
        doc.custom_previous_invoice_hash = previousInvoiceHash
        doc.custom_invoice_unique_identifier = uniqueInvoiceIdentifier
        doc.custom_invoice_icv = invoiceCounterValue
        doc.custom_clearance_status = response_json.get('clearanceStatus')
        doc.custom_clearance_time = frappe.utils.now_datetime()
        doc.custom_validation_results = json.dumps(response_json.get('validationResults', ''))

        doc.custom_seller_name = seller.get('organizationName')
        doc.custom_seller_vat = seller.get('vatNumber')
        doc.custom_seller_address = seller.get('full_address')
        doc.custom_buyer_name = buyer.get('organizationName')
        doc.custom_buyer_vat = buyer.get('vatNumber')
        doc.custom_buyer_address = buyer.get('full_address')
        
        # Save Cleared Invoice XML 
        cleared_invoice_xml = decode_invoice(response_json.get('clearedInvoice'))
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
        frappe.throw("Error Clearing Invoice, Clearance is Deactivated")
    elif response.status_code == 400:
        update_status_on_error(doc, response_json.get('clearanceStatus'), json.dumps(response_json.get('validationResults', '')))
        frappe.throw("Error Clearing Invoice, Bad Request")
    elif response.status_code == 401:
        update_status_on_error(doc, 'FAILED', json.dumps(response_json.get('message', '')))
        frappe.throw("Error Clearing Invoice, Invalid Credentials")
    elif response.status_code == 500:
        update_status_on_error(doc, 'FAILED', json.dumps(response_json.get('message', '')))
        frappe.throw("Error Clearing Invoice, Internal Server Error")
    else:
        update_status_on_error(doc, 'FAILED', json.dumps(response_json.get('message', '')))
        frappe.throw("Error Clearing Invoice, Unknown Error")

def update_status_on_error(doc, status, validation_results):
    frappe.db.set_value("Sales Invoice", doc.name, "custom_clearance_status", status, update_modified=True)
    frappe.db.set_value("Sales Invoice", doc.name, "custom_validation_results", validation_results, update_modified=True)
    frappe.db.set_value("Sales Invoice", doc.name, "custom_clearance_time", frappe.utils.now_datetime(), update_modified=True)
    frappe.db.commit()

def get_clearence_headers():
    return {
        'accept': 'application/json',
        'Accept-Language': 'en',
        'Clearance-Status': '1',
        'Accept-Version': 'V2',
        'Content-Type': 'application/json'
    }

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