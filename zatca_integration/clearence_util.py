import json
from datetime import datetime
import uuid
import frappe
from frappe.model.document import Document
import time
import requests
import base64
from requests.auth import HTTPBasicAuth

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
    buyer = get_buyer_information(doc)
    
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

    if response.status_code == 200:
        doc.custom_invoice_hash = invoice_request.get('invoiceHash')
        doc.custom_previous_invoice_hash = previousInvoiceHash
        doc.custom_invoice_unique_identifier = uniqueInvoiceIdentifier
        doc.custom_invoice_icv = invoiceCounterValue
        doc.custom_clearance_status = response_json.get('clearanceStatus')
        doc.custom_validation_results = json.dumps(response_json.get('validationResults', ''))
        cleared_invoice_xml = decode_invoice(response_json.get('clearedInvoice'))
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": invoiceNumber + ".xml",
            "content": cleared_invoice_xml,
            "is_private": True
        })
        file_doc.insert()
        doc.custom_invoice_xml = file_doc.file_url
    else:
        frappe.throw("Error Clearing Invoice")


def get_invoice_request(url, clientId, clientSecret, invoice):
    url = url + 'generateInvoiceRequest'
    # Set the headers
    headers = {
        'clientId': clientId,
        'clientSecret': clientSecret,
        'Content-Type': 'application/json'
    }

    # Encode the string into bytes, then encode it using base64
    data = {
        'invoice': encode_invoice(invoice)
    }

    try:
        # Make the POST request
        response = requests.post(url, headers=headers, json=data)
        response_json = response.json()
    except requests.exceptions.JSONDecodeError:
        frappe.throw("Error in generating invoice request from backend")

    return response_json

def encode_invoice(invoice):
    input_bytes = invoice.encode('utf-8')
    encoded_bytes = base64.b64encode(input_bytes)
    encoded_string = encoded_bytes.decode('utf-8')
    return encoded_string

def decode_invoice(encoded_invoice):
    encoded_bytes = encoded_invoice.encode('utf-8')
    decoded_bytes = base64.b64decode(encoded_bytes)
    decoded_string = decoded_bytes.decode('utf-8')
    return decoded_string

def get_seller_information(zatca_settings):
    return {
        "registrationScheme": zatca_settings.registration_scheme, #TODO ShortName and Add to Template
        "registrationNumber": zatca_settings.registration_number,
        "streetName": zatca_settings.street_name,
        "buildingNumber": zatca_settings.building_number,
        "citySubdivisionName": zatca_settings.city_subdivision_name,
        "cityName": zatca_settings.city_name,
        "postalZone": zatca_settings.postal_zone,
        "countryCode": zatca_settings.csrcountryname,
        "vatNumber": zatca_settings.csrorganizationidentifier,
        "organizationName": zatca_settings.csrorganizationname
    }

def get_buyer_information(doc): 
    customer = frappe.get_doc("Customer", doc.customer)
    return {
			"streetName": customer.custom_street_name,
			"buildingNumber":  customer.custom_building_number,
			"citySubdivisionName":  customer.custom_city_subdivision_name,
			"cityName":  customer.custom_city_name,
			"postalZone":  customer.custom_postal_zone,
			"countryCode":  customer.custom_country_code,
			"vatNumber":  customer.custom_vat_or_group_vat_registration_number,
			"organizationName":  customer.custom_organization_name
		}

def get_clearence_headers():
    return {
        'accept': 'application/json',
        'Accept-Language': 'en',
        'Clearance-Status': '1',
        'Accept-Version': 'V2',
        'Content-Type': 'application/json'
    }