# Copyright (c) 2023, Shakir PM and contributors
# For license information, please see license.txt

import datetime
import uuid
import time
import json
import frappe
import base64
import requests
from requests.auth import HTTPBasicAuth
from frappe.model.document import Document
from zatca_integration.common_util import generate_clearance_request, generate_reporting_request, generate_invoice_payload_from_xml


class ComplianceCSID(Document):

	def before_save(self):
		csr_settings = frappe.get_doc("Zatca CSR Settings", self.csr_settings)
		if csr_settings.csr == "" or csr_settings.csr is None:
			frappe.throw("CSR is not generated. Please generate CSR")

	@frappe.whitelist()
	def genereate_zatca_compliance_csid(self):
		csr_settings = frappe.get_doc("Zatca CSR Settings", self.csr_settings)
		zatca_environment = frappe.get_doc("Zatca Environment", csr_settings.zatca_environment)

		headers = {
			'accept': 'application/json',
			'OTP': self.otp,
			'Accept-Version': 'V2',
			'Content-Type': 'application/json'
		}
		data = {
			"csr": csr_settings.csr
		}

		try:
			response = requests.post(zatca_environment.compliance_csid_api, headers=headers, json=data)
			response.raise_for_status()
			response_json = response.json()

			self.created_time = frappe.utils.now_datetime()
			self.request_id = response_json.get('requestID', '')
			self.disposition_message = response_json.get('dispositionMessage', '')
			self.binary_security_token = response_json.get('binarySecurityToken', '')
			self.secret = response_json.get('secret', '')
			self.errors = response_json.get('errors', '{}')

			self.reset_compliance_csid_status(False)
			self.save()

		except requests.exceptions.RequestException as req_err:
			self.handle_error(response, f"An error occurred: {req_err}")
		except ValueError as json_err:
			self.handle_error(response, f"JSON parsing error: {json_err}")
	
	def handle_error(self, response, error_message):
		"""Handle errors by logging and raising an exception."""
		error_details = [error_message]

		if response is not None:
			error_details.append(f"Response Text: {response.text if response.text else 'No response text'}")

		self.errors = "\n".join(error_details)
		self.save(); frappe.db.commit()

		frappe.throw(f"Error in generating ZATCA Compliance CSID: {error_message}")

	@frappe.whitelist()
	def validate_zatca_compliance_csid(self):
		"""Validate ZATCA Compliance CSID."""
		if not self.binary_security_token:
			frappe.throw("Binary Security Token is not generated. Please Generate ZATCA Compliance CSID")

		csr_settings = frappe.get_doc("Zatca CSR Settings", self.csr_settings)
		seller = get_seller_information(csr_settings)
		buyer = get_buyer_information()

		if csr_settings.csrinvoicetype == "1100":
      #Uncomment after testing
			# self.invoke_complaince_check("standard", csr_settings, seller, buyer)
			
			self.invoke_complaince_check("simplified", csr_settings, seller, buyer)
			
			# if not (self.standard_invoice and self.standard_credit_note and self.standard_debit_note and self.simplified_invoice and self.simplified_credit_note and self.simplified_debit_note):
			# 	self.save(); frappe.db.commit()
			# 	frappe.throw("Failed to Validate Compliance CSID, Review CSID TRANSACTIONS for more details")
			failed = []

			if not self.standard_invoice:
				failed.append("Standard Invoice")
			if not self.standard_credit_note:
				failed.append("Standard Credit Note")
			if not self.standard_debit_note:
				failed.append("Standard Debit Note")
			if not self.simplified_invoice:
				failed.append("Simplified Invoice")
			if not self.simplified_credit_note:
				failed.append("Simplified Credit Note")
			if not self.simplified_debit_note:
				failed.append("Simplified Debit Note")

			if failed:
				self.save()
				frappe.db.commit()
				frappe.throw(f"Failed to Validate Compliance CSID for: {', '.join(failed)}. Review CSID TRANSACTIONS for more details.")
		elif csr_settings.csrinvoicetype == "1000":
			self.invoke_complaince_check("standard", csr_settings, seller, buyer)
			if not (self.standard_invoice and self.standard_credit_note and self.standard_debit_note):
				self.save(); frappe.db.commit()
				frappe.throw("Failed to Validate Compliance CSID, Review CSID TRANSACTIONS for more details")
		elif csr_settings.csrinvoicetype == "0100":
			self.invoke_complaince_check("simplified", csr_settings, seller, buyer)
			if not (self.simplified_invoice and self.simplified_credit_note and self.simplified_debit_note):
				self.save(); frappe.db.commit()
				frappe.throw("Failed to Validate Compliance CSID, Review CSID TRANSACTIONS for more details")
		else:
			frappe.throw("Invalid Invoice Type in ZATCA CSR Settings : " + csr_settings.csrinvoicetype)
		
		self.save()

	def set_invoice_status(self, invoice_type, status, note_type):
		"""Set the status of the invoice or note."""
		if invoice_type == "standard":
			if note_type == "invoice":
				self.standard_invoice = status
			elif note_type == "credit_note":
				self.standard_credit_note = status
			elif note_type == "debit_note":
				self.standard_debit_note = status
		elif invoice_type == "simplified":
			if note_type == "invoice":
				self.simplified_invoice = status
			elif note_type == "credit_note":
				self.simplified_credit_note = status
			elif note_type == "debit_note":
				self.simplified_debit_note = status

	def invoke_complaince_check(self, invoice_type, csr_settings, seller, buyer):
		"""Invoke compliance check for the given invoice type."""
		first_invoice_hash = "NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRkNGU5MWI0NjcyOWQ3M2EyN2ZiNTdlOQ=="

		# Issue Invoice
		tax_invoice = generate_tax_invoice_xml(invoice_type, "INV-00001", seller, buyer, first_invoice_hash)
		tax_invoice_status, tax_invoice_hash = self.invoke_compliance_invoice_api(invoice_type, csr_settings, tax_invoice["xml"])
		if invoice_type == "standard":
			self.standard_invoice = tax_invoice_status
		elif invoice_type == "simplified":
			self.simplified_invoice = tax_invoice_status

		# Issue Credit Note
		credit_note = generate_credit_note_xml(invoice_type, "INV-00002", seller, buyer, tax_invoice["invoiceNumber"], tax_invoice["invoiceDeliveryDate"], tax_invoice_hash)
		credit_note_status, credit_note_hash = self.invoke_compliance_invoice_api(invoice_type, csr_settings, credit_note["xml"])
		if invoice_type == "standard":
			self.standard_credit_note = credit_note_status
		elif invoice_type == "simplified":
			self.simplified_credit_note = credit_note_status
		
		# Issue Invoice
		tax_invoice = generate_tax_invoice_xml(invoice_type, "INV-00003", seller, buyer, credit_note_hash)
		tax_invoice_status, tax_invoice_hash = self.invoke_compliance_invoice_api(invoice_type, csr_settings, tax_invoice["xml"])
		
		# Issue Debit Note
		debit_note = generate_debit_note_xml(invoice_type, "INV-00004", seller, buyer, tax_invoice["invoiceNumber"], tax_invoice["invoiceDeliveryDate"], tax_invoice_hash)
		debit_note_status, debit_note_hash = self.invoke_compliance_invoice_api(invoice_type, csr_settings, debit_note["xml"])
		
		if invoice_type == "standard":
			self.standard_debit_note = debit_note_status
		elif invoice_type == "simplified":
			self.simplified_debit_note = debit_note_status
		
	def invoke_compliance_invoice_api(self, invoice_type, csr_settings, invoice_xml):
		"""Invoke compliance invoice API."""
		zatca_environment = frappe.get_doc("Zatca Environment", csr_settings.zatca_environment)

		if invoice_type == "standard":
			invoice_request = generate_invoice_payload_from_xml(invoice_xml.encode("utf-8"))
		elif invoice_type == "simplified":
			# private_key = frappe.get_doc("Zatca CSR Settings", self.csr_settings).private_key
			# invoice_request = generate_reporting_request(zatca_environment.csr_generate_api, zatca_environment.client_id, zatca_environment.client_secret, base64.b64encode(private_key.encode("utf-8")).decode("utf-8"), self.decode_certificate(self.binary_security_token), invoice_xml)
			invoice_request = generate_invoice_payload_from_xml(invoice_xml.encode("utf-8"))
		else:
			frappe.throw(f"Invalid Invoice Type: {invoice_type}")

		headers = {
			'accept': 'application/json',
			'Accept-Language': 'en',
			'Accept-Version': 'V2',
			'Content-Type': 'application/json'
		}
		# frappe.throw(str(invoice_request))
		try:
			response = requests.post(zatca_environment.compliance_invoice_api, headers=headers, auth=HTTPBasicAuth(self.binary_security_token, self.secret), data=json.dumps(invoice_request))
			frappe.throw(str(response.text))
			response_code = response.status_code
			response_text = response.text
			response_headers = dict(response.headers)
		except requests.exceptions.RequestException as e:
			response_code = None
			response_text = str(e)
			response_headers = {}

		# Save the request and response details
		transaction = frappe.get_doc({
			'doctype': 'CSID Transactions',
			'compliance_csid': self.name,
			'request_url': zatca_environment.compliance_invoice_api,
			'request_header': json.dumps(headers),
			'request_body': json.dumps(invoice_request),
			'response_code': response_code,
			'response_header': json.dumps(response_headers),
			'response_body': response_text,
			'transaction_time': frappe.utils.now_datetime(),
		})
		transaction.insert()
		
		if response.status_code == 200:
			return True, invoice_request["invoiceHash"]
		else:
			return False, None
		
	def reset_compliance_csid_status(self, status):
		"""Reset the compliance CSID status."""
		self.standard_invoice = status
		self.standard_debit_note = status
		self.standard_credit_note = status
		self.simplified_invoice = status
		self.simplified_debit_note = status
		self.simplified_credit_note = status

	def decode_certificate(self, compliance_certificate):
		"""Decode the compliance certificate from base64."""
		decoded_compliance_certificate = base64.b64decode(compliance_certificate.encode('utf-8'))
		return decoded_compliance_certificate.decode('utf-8')
	
def generate_debit_note_xml(invoiceType, invoiceNumber, seller, buyer, originalinvoiceNumber, originalinvoiceDeliveryDate, previousInvoiceHash):
    
    # Global Unique Identifier
    uniqueInvoiceIdentifier = str(uuid.uuid4())
    # Counter Value, once used cannot be used even for same invoice
    invoiceCounterValue  = int(time.time())

    # Invoice Date and Time
    invoice_date = datetime.date.today().strftime("%Y-%m-%d")
    invoice_time = datetime.datetime.now().strftime("%H:%M:%S")

    if invoiceType == "standard":
        template_file = "zatca_integration/templates/zatca/compliance/Standard_Debit_Note.xml"
    elif invoiceType == "simplified":
        template_file = "zatca_integration/templates/zatca/compliance/Simplified_Debit_Note.xml"
    else:
        frappe.throw("Invalid Invoice Type")


    standard_debit_note_xml = frappe.render_template(template_file, {
        "originalinvoiceNumber": originalinvoiceNumber,
        "previousInvoiceHash": previousInvoiceHash,
        "invoiceNumber": invoiceNumber,
        "uniqueInvoiceIdentifier": uniqueInvoiceIdentifier,
        "invoiceCounterValue": invoiceCounterValue,
        "invoice_date": invoice_date,
        "invoice_time": invoice_time,
        "seller": seller,
        "buyer": buyer,
        "invoiceDeliveryDate": originalinvoiceDeliveryDate,
    })
    standard_debit_note = {
        "invoiceNumber": invoiceNumber,
        "uniqueInvoiceIdentifier": uniqueInvoiceIdentifier,
        "invoiceCounterValue": invoiceCounterValue,
        "invoiceDeliveryDate": originalinvoiceDeliveryDate,
        "xml": standard_debit_note_xml,
    }
    return standard_debit_note

def generate_credit_note_xml(invoiceType, invoiceNumber, seller, buyer, originalinvoiceNumber, originalinvoiceDeliveryDate, previousInvoiceHash):
    
    # Global Unique Identifier
    uniqueInvoiceIdentifier = str(uuid.uuid4())
    # Counter Value, once used cannot be used even for same invoice
    invoiceCounterValue  = int(time.time())

    # Invoice Date and Time
    invoice_date = datetime.date.today().strftime("%Y-%m-%d")
    invoice_time = datetime.datetime.now().strftime("%H:%M:%S")

    if invoiceType == "standard":
        template_file = "zatca_integration/templates/zatca/compliance/Standard_Credit_Note.xml"
    elif invoiceType == "simplified":
        template_file = "zatca_integration/templates/zatca/compliance/Simplified_Credit_Note.xml"
    else:
        frappe.throw("Invalid Invoice Type")

    standard_credit_note_xml = frappe.render_template(template_file, {
        "originalinvoiceNumber": originalinvoiceNumber,
        "previousInvoiceHash": previousInvoiceHash,
        "invoiceNumber": invoiceNumber,
        "uniqueInvoiceIdentifier": uniqueInvoiceIdentifier,
        "invoiceCounterValue": invoiceCounterValue,
        "invoice_date": invoice_date,
        "invoice_time": invoice_time,
        "seller": seller,
        "buyer": buyer,
        "invoiceDeliveryDate": originalinvoiceDeliveryDate,
    })
    standard_credit_note = {
        "invoiceNumber": invoiceNumber,
        "uniqueInvoiceIdentifier": uniqueInvoiceIdentifier,
        "invoiceCounterValue": invoiceCounterValue,
        "invoiceDeliveryDate": originalinvoiceDeliveryDate,
        "xml": standard_credit_note_xml,
    }
    return standard_credit_note

def generate_tax_invoice_xml(invoiceType, invoiceNumber, seller, buyer, previousInvoiceHash):
    
    # Global Unique Identifier
    uniqueInvoiceIdentifier = str(uuid.uuid4())
    # Counter Value, once used cannot be used even for same invoice
    invoiceCounterValue  = int(time.time())

    # Invoice Date and Time
    invoice_date = datetime.date.today().strftime("%Y-%m-%d")
    invoice_time = datetime.datetime.now().strftime("%H:%M:%S")

    # Invoice Delivery Date
    invoiceDeliveryDate = (datetime.date.today() + datetime.timedelta(days=10)).strftime("%Y-%m-%d")

    if invoiceType == "standard":
        template_file = "zatca_integration/templates/zatca/compliance/Standard_Invoice.xml"
    elif invoiceType == "simplified":
        template_file = "zatca_integration/templates/zatca/compliance/Simplified_Invoice.xml"
    else:
        frappe.throw("Invalid Invoice Type, type: " + invoiceType)

    standard_invoice_xml = frappe.render_template(template_file, {
        "previousInvoiceHash": previousInvoiceHash,
        "invoiceNumber": invoiceNumber,
        "uniqueInvoiceIdentifier": uniqueInvoiceIdentifier,
        "invoiceCounterValue": invoiceCounterValue,
        "invoice_date": invoice_date,
        "invoice_time": invoice_time,
        "seller": seller,
        "buyer": buyer,
        "invoiceDeliveryDate": invoiceDeliveryDate,
        "qr_code":generate_qr_code(
    seller.get("organization_name"),
    seller.get("vat_number"),
    invoice_date,
    invoice_time,
    "0.00",  # Replace with actual total amount
    "0.00",  # Replace with actual tax amount
    previousInvoiceHash
)
    })
    standard_invoice = {
        "invoiceNumber": invoiceNumber,
        "uniqueInvoiceIdentifier": uniqueInvoiceIdentifier,
        "invoiceCounterValue": invoiceCounterValue,
        "invoiceDeliveryDate": invoiceDeliveryDate,
        "xml": standard_invoice_xml,
    }
    return standard_invoice

def get_buyer_information():
	return {
		"organizationName": "Panda Retail Company",
		"vatNumber": "300056521610003",
		"streetName": "Taha Khasiyfan",
		"buildingNumber": "2444",
		"citySubdivisionName": "Ash Shati",
		"cityName": "Jeddah",
		"postalZone": "23511",
		"countryCode": "SA"
	}

def get_seller_information(csr_settings):
    return {
        "organizationName": csr_settings.csrorganizationname,
        "vatNumber": csr_settings.csrorganizationidentifier,
        "streetName": csr_settings.street_name,
        "buildingNumber": csr_settings.building_number,
        "citySubdivisionName": csr_settings.city_subdivision_name,
        "cityName": csr_settings.city_name,
        "postalZone": csr_settings.postal_zone,
        "countryCode": csr_settings.csrcountryname,
        "registrationNumber": csr_settings.registration_number,
		"registrationScheme": get_registration_scheme_code(csr_settings.registration_scheme),
		"registration_scheme": csr_settings.registration_scheme
    }

def get_registration_scheme_code(registration_scheme):
    # Find the start and end indices of the parentheses
    start = registration_scheme.find('(')
    end = registration_scheme.find(')')

    # Extract and return the text inside the parentheses
    if start != -1 and end != -1:
        return registration_scheme[start + 1:end]
    else:
        frappe.throw("Invalid Registration Scheme")
        
import qrcode
import base64
from io import BytesIO

def generate_qr_code(seller_name, vat_number, invoice_date, invoice_time, total_amount, tax_amount, previous_hash):
    """
    Generate a QR code for ZATCA (Saudi Arabian tax authority) e-invoicing
    """
    # Format the QR code data according to ZATCA requirements
    qr_data = f"""
{seller_name}
{vat_number}
{invoice_date}
{invoice_time}
{total_amount}
{tax_amount}
{previous_hash}
""".strip()
    
    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to base64
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    
    return img_str