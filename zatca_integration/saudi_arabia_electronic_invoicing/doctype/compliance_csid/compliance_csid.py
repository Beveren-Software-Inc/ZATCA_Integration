# Copyright (c) 2023, Shakir PM and contributors
# For license information, please see license.txt

import uuid
import time
import json
import frappe
import base64
import requests
from requests.auth import HTTPBasicAuth
from frappe.model.document import Document
from zatca_integration.common_util import generate_clearance_request, generate_reporting_request, generate_invoice_payload_from_xml
 
from datetime import datetime, timedelta


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
			self.invoke_complaince_check("standard", csr_settings, seller, buyer)
			
			self.invoke_complaince_check("simplified", csr_settings, seller, buyer)
			
			if not (self.standard_invoice and self.standard_credit_note and self.standard_debit_note and self.simplified_invoice and self.simplified_credit_note and self.simplified_debit_note):
				self.save(); frappe.db.commit()
				frappe.throw("Failed to Validate Compliance CSID, Review CSID TRANSACTIONS for more details")
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
			if not (self.simplified_invoice):
				frappe.db.commit()
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
		# first_invoice_hash = "NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRkNGU5MWI0NjcyOWQ3M2EyN2ZiNTdlOQ=="
		'''FIRST INVOICE if there is none sent, use base64 encoded '0' as the first invoice hash.'''
		first_invoice_hash = "X+zrZv/IbzjZUnhsbWlsecLbwjndTpG0ZynXOif7V+k="

		# Issue Invoice
		tax_invoice = generate_tax_invoice_xml(invoice_type, "INV-00001", seller, buyer, first_invoice_hash)
		tax_invoice_status, tax_invoice_hash = self.invoke_compliance_invoice_api(invoice_type, csr_settings, tax_invoice["xml"])
		if invoice_type == "standard":
			self.standard_invoice = tax_invoice_status
		elif invoice_type == "simplified":
			self.simplified_invoice = tax_invoice_status

		# Issue Credit Note
		credit_note = generate_credit_note_xml(invoice_type, "INV-00002", seller, buyer, "test", "tesr", "jnj")
		credit_note_status, credit_note_hash = self.invoke_compliance_invoice_api(invoice_type, csr_settings, credit_note["xml"])
		if invoice_type == "standard":
			self.standard_credit_note = credit_note_status
		elif invoice_type == "simplified":
      
			self.simplified_credit_note = credit_note_status
		
		# Issue Invoice
		tax_invoice = generate_tax_invoice_xml(invoice_type, "INV-00003", seller, buyer, credit_note_hash)
		tax_invoice_status, tax_invoice_hash = self.invoke_compliance_invoice_api(invoice_type, csr_settings, tax_invoice["xml"])
		
		# Issue Debit Note
		debit_note = generate_debit_note_xml(invoice_type, "INV-00004", seller, buyer, "koko", "tax_invoice[invoiceDeliveryDate]", "tax_invoice_hash")
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
			invoice_request = generate_invoice_payload_from_xml(invoice_xml.encode("utf-8"))
		else:
			frappe.throw(f"Invalid Invoice Type: {invoice_type}")

		headers = {
			'accept': 'application/json',
			'Accept-Language': 'en',
			'Accept-Version': 'V2',
			'Content-Type': 'application/json'
		}
		try:
			
			response = requests.post(zatca_environment.compliance_invoice_api, headers=headers, auth=HTTPBasicAuth(self.binary_security_token, self.secret), data=json.dumps(invoice_request))
			print(f"{response.status_code} then Response: {response.text}")
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
		
		if response.status_code == 200 or response.status_code == 202:
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
	invoice_date = datetime.strptime(frappe.utils.today(), "%Y-%m-%d").strftime("%Y-%m-%d")
	invoice_time = datetime.strptime(frappe.utils.now(), "%Y-%m-%d %H:%M:%S.%f").strftime("%H:%M:%S")

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
	invoice_date = datetime.strptime(frappe.utils.today(), "%Y-%m-%d").strftime("%Y-%m-%d")
	invoice_time = datetime.strptime(frappe.utils.now(), "%Y-%m-%d %H:%M:%S.%f").strftime("%H:%M:%S")

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
    invoice_date = datetime.strptime(frappe.utils.today(), "%Y-%m-%d").strftime("%Y-%m-%d")
    invoice_time = datetime.strptime(frappe.utils.now(), "%Y-%m-%d %H:%M:%S.%f").strftime("%H:%M:%S")

    # Invoice Delivery Date
    invoiceDeliveryDate = (frappe.utils.getdate(frappe.utils.today()) + timedelta(days=10)).strftime("%Y-%m-%d")


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
        "qr_code":""
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
  
  
# def generate_credit_invoice_xml(invoiceType, invoiceNumber, seller, buyer, previousInvoiceHash,
# 							 invoice_lines=None, total_amount="0.00", tax_amount="0.00"):
# 	"""
# 	Generate ZATCA compliant invoice XML using two-pass generation.
# 	Ensures proper decimal math and validated fields.
# 	"""
# 	uniqueInvoiceIdentifier = str(uuid.uuid4())
# 	invoiceCounterValue = int(time.time())

# 	now = datetime.now()
# 	invoice_date = now.strftime("%Y-%m-%d")
# 	invoice_time = now.strftime("%H:%M:%S")
# 	invoiceDeliveryDate = (frappe.utils.getdate(frappe.utils.today()) + timedelta(days=10)).strftime("%Y-%m-%d")
# 	timestamp = f"{invoice_date}T{invoice_time}Z"

# 	if not invoice_lines:
# 		invoice_lines = [{
# 			"quantity": "1.0",
# 			"unitPrice": "100.00",
# 			"itemName": "Test Item",
# 			"taxCategoryId": "S",
# 			"taxPercent": "15.00",
# 		}]

# 	# Validate & recalculate all totals based on line items
# 	validated_result = calculate_invoice_totals(invoice_lines)
# 	invoice_lines = validated_result["invoice_lines"]
# 	total_amount = validated_result["total_amount"]
# 	tax_amount = validated_result["tax_amount"]
# 	line_extension_amount = validated_result["line_extension_amount"]

# 	qr_code_base64 = generate_qr_code(
# 		seller.get("organizationName", ""),
# 		seller.get("vatNumber", ""),
# 		timestamp,
# 		str(total_amount),
# 		str(tax_amount)
# 	)

# 	# First pass XML generation (without hash)
# 	xml_pass1 = generate_simplified_invoice_xml(
# 		previousInvoiceHash="",
# 		invoiceNumber=invoiceNumber,
# 		uniqueInvoiceIdentifier=uniqueInvoiceIdentifier,
# 		invoiceCounterValue=invoiceCounterValue,
# 		invoice_date=invoice_date,
# 		invoice_time=invoice_time,
# 		seller=seller,
# 		buyer=buyer,
# 		invoiceDeliveryDate=invoiceDeliveryDate,
# 		qr_code_base64=qr_code_base64,

		
# 	)

# 	# Calculate hash
# 	invoice_hash = calculate_invoice_hash(xml_pass1)

# 	# Second pass XML generation (with hash)
# 	xml_pass2 = generate_simplified_invoice_xml(
# 		previousInvoiceHash=invoice_hash,
# 		invoiceNumber=invoiceNumber,
# 		uniqueInvoiceIdentifier=uniqueInvoiceIdentifier,
# 		invoiceCounterValue=invoiceCounterValue,
# 		invoice_date=invoice_date,
# 		invoice_time=invoice_time,
# 		seller=seller,
# 		buyer=buyer,
# 		invoiceDeliveryDate=invoiceDeliveryDate,
# 		qr_code_base64=qr_code_base64,
		
# 		# invoice_hash=invoice_hash
# 	)

# 	return {
# 		"invoiceNumber": invoiceNumber,
# 		"uniqueInvoiceIdentifier": uniqueInvoiceIdentifier,
# 		"invoiceCounterValue": invoiceCounterValue,
# 		"invoiceDate": invoice_date,
# 		"invoiceTime": invoice_time,
# 		"invoiceDeliveryDate": invoiceDeliveryDate,
# 		"totalAmount": total_amount,
# 		"taxAmount": tax_amount,
# 		"qrCode": qr_code_base64,
# 		"invoiceHash": invoice_hash,
# 		"xml": xml_pass2
# 	}

# def calculate_invoice_totals(invoice_lines):
# 	from decimal import Decimal, ROUND_HALF_UP

# 	total_line_extension = Decimal("0.00")
# 	total_tax = Decimal("0.00")
# 	validated_lines = []

# 	for line in invoice_lines:
# 		quantity = Decimal(str(line.get("quantity", "1.0")))
# 		unit_price = Decimal(str(line.get("unitPrice", "0.00")))
# 		tax_percent = Decimal(str(line.get("taxPercent", "15.00")))

# 		line_extension_amount = (quantity * unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
# 		tax_amount = (line_extension_amount * tax_percent / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
# 		line_total_with_vat = (line_extension_amount + tax_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

# 		total_line_extension += line_extension_amount
# 		total_tax += tax_amount

# 		validated_line = {
# 			**line,
# 			"lineExtensionAmount": str(line_extension_amount),
# 			"taxAmount": str(tax_amount),
# 			"unitPrice": str(unit_price),
# 			"quantity": str(quantity),
# 			"lineTotalWithVAT": str(line_total_with_vat),  # 👈 Add this for BR-KSA-51
# 		}
# 		validated_lines.append(validated_line)

# 	total_amount = (total_line_extension + total_tax).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

# 	return {
# 		"invoice_lines": validated_lines,
# 		"line_extension_amount": str(total_line_extension),
# 		"tax_amount": str(total_tax),
# 		"total_amount": str(total_amount),
# 	}



# #New function also
# def generate_simplified_invoice_xml(previousInvoiceHash, invoiceNumber, uniqueInvoiceIdentifier,
#                                     invoiceCounterValue, invoice_date, invoice_time, seller, buyer,
#                                     invoiceDeliveryDate, qr_code_base64,
#                                     digest_value_invoice="", digest_value_properties="", signature_value="",
#                                     x509_certificate="", signing_time=""):
#     """Generate simplified invoice XML with values and signature structure, ensuring no validation warnings"""

#     from decimal import Decimal, ROUND_HALF_UP

#     # Helper for rounding
#     def rounded(val):
#         return str(Decimal(val).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

#     digest_value_invoice = digest_value_invoice or "NcyZN9X773QAKhihjS17EbnQh18n4on+UPTNJ7nWu7Y="
#     digest_value_properties = digest_value_properties or "ZTVmNDc2Y2IwNmFkMGQ2MWI0Njc5ODJhN2IyNDRkNTJhM2MzM2Q5ODU3Njg0M2RjYzgyYzZmOGU5NDY3NGQxZA=="
#     signature_value = signature_value or "MEYCIQDly89Ty2oDHEkiDHPUYFxoIKFMPG0CjxlvQpMZ1FyoWgIhAIMyLDDFxRJsiA/4/LceQl9GvnTmBfjQrHUBdQSzyYDk"
#     x509_certificate = x509_certificate or "MIID3jCCA4SgAwIBAgITEQAAOAPF90Ajs/xcXwABAAA4AzAKBggqhkjOPQQDAjBiMRUwEwYKCZImiZPyLGQBGRYFbG9jYWwxEzARBgoJkiaJk/IsZAEZFgNnb3YxFzAVBgoJkiaJk/IsZAEZFgdleHRnYXp0MRswGQYDVQQDExJQUlpFSU5WT0lDRVNDQTQtQ0EwHhcNMjQwMTExMDkxOTMwWhcNMjkwMTA5MDkxOTMwWjB1MQswCQYDVQQGEwJTQTEmMCQGA1UEChMdTWF4aW11bSBTcGVlZCBUZWNoIFN1cHBseSBMVEQxFjAUBgNVBAsTDVJpeWFkaCBCcmFuY2gxJjAkBgNVBAMTHVRTVC04ODY0MzExNDUtMzk5OTk5OTk5OTAwMDAzMFYwEAYHKoZIzj0CAQYFK4EEAAoDQgAEoWCKa0Sa9FIErTOv0uAkC1VIKXxU9nPpx2vlf4yhMejy8c02XJblDq7tPydo8mq0ahOMmNo8gwni7Xt1KT9UeKOCAgcwggIDMIGtBgNVHREEgaUwgaKkgZ8wgZwxOzA5BgNVBAQMMjEtVFNUfDItVFNUfDMtZWQyMmYxZDgtZTZhMi0xMTE4LTliNTgtZDlhOGYxMWU0NDVmMR8wHQYKCZImiZPyLGQBAQwPMzk5OTk5OTk5OTAwMDAzMQ0wCwYDVQQMDAQxMTAwMREwDwYDVQQaDAhSUlJEMjkyOTEaMBgGA1UEDwwRU3VwcGx5IGFjdGl2aXRpZXMwHQYDVR0OBBYEFEX+YvmmtnYoDf9BGbKo7ocTKYK1MB8GA1UdIwQYMBaAFJvKqqLtmqwskIFzVvpP2PxT+9NnMHsGCCsGAQUFBwEBBG8wbTBrBggrBgEFBQcwAoZfaHR0cDovL2FpYTQuemF0Y2EuZ292LnNhL0NlcnRFbnJvbGwvUFJaRUludm9pY2VTQ0E0LmV4dGdhenQuZ292LmxvY2FsX1BSWkVJTlZPSUNFU0NBNC1DQSgxKS5jcnQwDgYDVR0PAQH/BAQDAgeAMDwGCSsGAQQBgjcVBwQvMC0GJSsGAQQBgjcVCIGGqB2E0PsShu2dJIfO+xnTwFVmh/qlZYXZhD4CAWQCARIwHQYDVR0lBBYwFAYIKwYBBQUHAwMGCCsGAQUFBwMCMCcGCSsGAQQBgjcVCgQaMBgwCgYIKwYBBQUHAwMwCgYIKwYBBQUHAwIwCgYIKoZIzj0EAwIDSAAwRQIhALE/ichmnWXCUKUbca3yci8oqwaLvFdHVjQrveI9uqAbAiA9hC4M8jgMBADPSzmd2uiPJA6gKR3LE03U75eqbC/rXA=="
#     signing_time = signing_time or f"{invoice_date}T{invoice_time}"

#     # Generate signature extension content
#     signature_content = ""
#     if digest_value_invoice and digest_value_properties and signature_value and x509_certificate:
#         signature_content = f"""<sig:UBLDocumentSignatures xmlns:sig="urn:oasis:names:specification:ubl:schema:xsd:CommonSignatureComponents-2" xmlns:sac="urn:oasis:names:specification:ubl:schema:xsd:SignatureAggregateComponents-2" xmlns:sbc="urn:oasis:names:specification:ubl:schema:xsd:SignatureBasicComponents-2">
#           <sac:SignatureInformation>
#             <cbc:ID>urn:oasis:names:specification:ubl:signature:1</cbc:ID>
#             <sbc:ReferencedSignatureID>urn:oasis:names:specification:ubl:signature:Invoice</sbc:ReferencedSignatureID>
#             <ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#" Id="signature">
#               <ds:SignedInfo>
#                 <ds:CanonicalizationMethod Algorithm="http://www.w3.org/2006/12/xml-c14n11"/>
#                 <ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#ecdsa-sha256"/>
#                 <ds:Reference Id="invoiceSignedData" URI="">
#                   <ds:Transforms>
#                     <ds:Transform Algorithm="http://www.w3.org/TR/1999/REC-xpath-19991116">
#                       <ds:XPath>not(//ancestor-or-self::ext:UBLExtensions)</ds:XPath>
#                     </ds:Transform>
#                     <ds:Transform Algorithm="http://www.w3.org/TR/1999/REC-xpath-19991116">
#                       <ds:XPath>not(//ancestor-or-self::cac:Signature)</ds:XPath>
#                     </ds:Transform>
#                     <ds:Transform Algorithm="http://www.w3.org/TR/1999/REC-xpath-19991116">
#                       <ds:XPath>not(//ancestor-or-self::cac:AdditionalDocumentReference[cbc:ID='QR'])</ds:XPath>
#                     </ds:Transform>
#                     <ds:Transform Algorithm="http://www.w3.org/2006/12/xml-c14n11"/>
#                   </ds:Transforms>
#                   <ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
#                   <ds:DigestValue>{digest_value_invoice}</ds:DigestValue>
#                 </ds:Reference>
#                 <ds:Reference URI="#xadesSignedProperties" Type="http://www.w3.org/2000/09/xmldsig#SignatureProperties">
#                   <ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
#                   <ds:DigestValue>{digest_value_properties}</ds:DigestValue>
#                 </ds:Reference>
#               </ds:SignedInfo>
#               <ds:SignatureValue>{signature_value}</ds:SignatureValue>
#               <ds:KeyInfo>
#                 <ds:X509Data>
#                   <ds:X509Certificate>{x509_certificate}</ds:X509Certificate>
#                 </ds:X509Data>
#               </ds:KeyInfo>
#               <ds:Object>
#                 <xades:QualifyingProperties xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" Target="signature">
#                   <xades:SignedProperties Id="xadesSignedProperties">
#                     <xades:SignedSignatureProperties>
#                       <xades:SigningTime>{signing_time}</xades:SigningTime>
#                       <xades:SigningCertificate>
#                         <xades:Cert>
#                           <xades:CertDigest>
#                             <ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
#                             <ds:DigestValue>ZDMwMmI0MTE1NzVjOTU2NTk4YzVlODhhYmI0ODU2NDUyNTU2YTVhYjhhMDFmN2FjYjk1YTA2OWQ0NjY2MjQ4NQ==</ds:DigestValue>
#                           </xades:CertDigest>
#                           <xades:IssuerSerial>
#                             <ds:X509IssuerName>CN=PRZEINVOICESCA4-CA, DC=extgazt, DC=gov, DC=local</ds:X509IssuerName>
#                             <ds:X509SerialNumber>379112742831380471835263969587287663520528387</ds:X509SerialNumber>
#                           </xades:IssuerSerial>
#                         </xades:Cert>
#                       </xades:SigningCertificate>
#                     </xades:SignedSignatureProperties>
#                   </xades:SignedProperties>
#                 </xades:QualifyingProperties>
#               </ds:Object>
#             </ds:Signature>
#           </sac:SignatureInformation>
#         </sig:UBLDocumentSignatures>"""
#     else:
#         signature_content = "<!-- Digital signature will be added here -->"

#     # Build invoice lines
#     invoice_lines_xml = f"""
#   <cac:InvoiceLine>
#     <cbc:ID>1</cbc:ID>
#     <cbc:InvoicedQuantity unitCode="Nos">50.0</cbc:InvoicedQuantity>
#     <cbc:LineExtensionAmount currencyID="SAR">182.5</cbc:LineExtensionAmount>
#     <cac:TaxTotal>
#       <cbc:TaxAmount currencyID="SAR">0.0</cbc:TaxAmount>
#       <cbc:RoundingAmount currencyID="SAR">182.5</cbc:RoundingAmount>
#     </cac:TaxTotal>
#     <cac:Item>
#       <cbc:Name>SKU001</cbc:Name>
#       <cac:ClassifiedTaxCategory>
#         <cbc:ID>Z</cbc:ID>
#         <cbc:Percent>0.00</cbc:Percent>
#         <cac:TaxScheme>
#           <cbc:ID>VAT</cbc:ID>
#         </cac:TaxScheme>
#       </cac:ClassifiedTaxCategory>
#     </cac:Item>
#     <cac:Price>
#       <cbc:PriceAmount currencyID="SAR">3.650000</cbc:PriceAmount>
#     </cac:Price>
#   </cac:InvoiceLine>
#   <cac:InvoiceLine>
#     <cbc:ID>2</cbc:ID>
#     <cbc:InvoicedQuantity unitCode="Nos">30.0</cbc:InvoicedQuantity>
#     <cbc:LineExtensionAmount currencyID="SAR">109.5</cbc:LineExtensionAmount>
#     <cac:TaxTotal>
#       <cbc:TaxAmount currencyID="SAR">0.0</cbc:TaxAmount>
#       <cbc:RoundingAmount currencyID="SAR">109.5</cbc:RoundingAmount>
#     </cac:TaxTotal>
#     <cac:Item>
#       <cbc:Name>SKU001</cbc:Name>
#       <cac:ClassifiedTaxCategory>
#         <cbc:ID>Z</cbc:ID>
#         <cbc:Percent>0.00</cbc:Percent>
#         <cac:TaxScheme>
#           <cbc:ID>VAT</cbc:ID>
#         </cac:TaxScheme>
#       </cac:ClassifiedTaxCategory>
#     </cac:Item>
#     <cac:Price>
#       <cbc:PriceAmount currencyID="SAR">3.650000</cbc:PriceAmount>
#     </cac:Price>
#   </cac:InvoiceLine>"""

#     # XML envelope
#     xml_template = f"""<?xml version="1.0" encoding="UTF-8"?>
# <Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"><ext:UBLExtensions>
#     <ext:UBLExtension>
#         <ext:ExtensionURI>urn:oasis:names:specification:ubl:dsig:enveloped:xades</ext:ExtensionURI>
#         <ext:ExtensionContent>
#             <sig:UBLDocumentSignatures xmlns:sig="urn:oasis:names:specification:ubl:schema:xsd:CommonSignatureComponents-2" xmlns:sac="urn:oasis:names:specification:ubl:schema:xsd:SignatureAggregateComponents-2" xmlns:sbc="urn:oasis:names:specification:ubl:schema:xsd:SignatureBasicComponents-2">
#                 <sac:SignatureInformation> 
#                     <cbc:ID>urn:oasis:names:specification:ubl:signature:1</cbc:ID>
#                     <sbc:ReferencedSignatureID>urn:oasis:names:specification:ubl:signature:Invoice</sbc:ReferencedSignatureID>
#                     <ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#" Id="signature">
#                         <ds:SignedInfo>
#                             <ds:CanonicalizationMethod Algorithm="http://www.w3.org/2006/12/xml-c14n11"/>
#                             <ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#ecdsa-sha256"/>
#                             <ds:Reference Id="invoiceSignedData" URI="">
#                                 <ds:Transforms>
#                                     <ds:Transform Algorithm="http://www.w3.org/TR/1999/REC-xpath-19991116">
#                                         <ds:XPath>not(//ancestor-or-self::ext:UBLExtensions)</ds:XPath>
#                                     </ds:Transform>
#                                     <ds:Transform Algorithm="http://www.w3.org/TR/1999/REC-xpath-19991116">
#                                         <ds:XPath>not(//ancestor-or-self::cac:Signature)</ds:XPath>
#                                     </ds:Transform>
#                                     <ds:Transform Algorithm="http://www.w3.org/TR/1999/REC-xpath-19991116">
#                                         <ds:XPath>not(//ancestor-or-self::cac:AdditionalDocumentReference[cbc:ID='QR'])</ds:XPath>
#                                     </ds:Transform>
#                                     <ds:Transform Algorithm="http://www.w3.org/2006/12/xml-c14n11"/>
#                                 </ds:Transforms>
#                                 <ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
#                                 <ds:DigestValue>Ei+ecyKDNMzw7ilYWGD2/KsVXpvh08bJ020sYkv+cuo=</ds:DigestValue>
#                             </ds:Reference>
#                             <ds:Reference Type="http://www.w3.org/2000/09/xmldsig#SignatureProperties" URI="#xadesSignedProperties">
#                                 <ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
#                                 <ds:DigestValue>Mjk0YWI1ZTk0Mzg3Y2QzODY2YzVmOTcyMjZjZjc1MDg5ZjE1NjE2NGViZjVkZWViZmM0MzI1ZDlhNjY3NDlkMQ==</ds:DigestValue>
#                             </ds:Reference>
#                         </ds:SignedInfo>
#                         <ds:SignatureValue>MEYCIQCaqenkwY9S9LlecTOIyCT3ELBCH0fLpPEeJBQq38OGagIhAKzLohfl4nm1cnO7hOGkfDkuBqrNnmF1w5hYk4ABYsj3</ds:SignatureValue>
#                         <ds:KeyInfo>
#                             <ds:X509Data>
#                                 <ds:X509Certificate>MIID3jCCA4SgAwIBAgITEQAAOAPF90Ajs/xcXwABAAA4AzAKBggqhkjOPQQDAjBiMRUwEwYKCZImiZPyLGQBGRYFbG9jYWwxEzARBgoJkiaJk/IsZAEZFgNnb3YxFzAVBgoJkiaJk/IsZAEZFgdleHRnYXp0MRswGQYDVQQDExJQUlpFSU5WT0lDRVNDQTQtQ0EwHhcNMjQwMTExMDkxOTMwWhcNMjkwMTA5MDkxOTMwWjB1MQswCQYDVQQGEwJTQTEmMCQGA1UEChMdTWF4aW11bSBTcGVlZCBUZWNoIFN1cHBseSBMVEQxFjAUBgNVBAsTDVJpeWFkaCBCcmFuY2gxJjAkBgNVBAMTHVRTVC04ODY0MzExNDUtMzk5OTk5OTk5OTAwMDAzMFYwEAYHKoZIzj0CAQYFK4EEAAoDQgAEoWCKa0Sa9FIErTOv0uAkC1VIKXxU9nPpx2vlf4yhMejy8c02XJblDq7tPydo8mq0ahOMmNo8gwni7Xt1KT9UeKOCAgcwggIDMIGtBgNVHREEgaUwgaKkgZ8wgZwxOzA5BgNVBAQMMjEtVFNUfDItVFNUfDMtZWQyMmYxZDgtZTZhMi0xMTE4LTliNTgtZDlhOGYxMWU0NDVmMR8wHQYKCZImiZPyLGQBAQwPMzk5OTk5OTk5OTAwMDAzMQ0wCwYDVQQMDAQxMTAwMREwDwYDVQQaDAhSUlJEMjkyOTEaMBgGA1UEDwwRU3VwcGx5IGFjdGl2aXRpZXMwHQYDVR0OBBYEFEX+YvmmtnYoDf9BGbKo7ocTKYK1MB8GA1UdIwQYMBaAFJvKqqLtmqwskIFzVvpP2PxT+9NnMHsGCCsGAQUFBwEBBG8wbTBrBggrBgEFBQcwAoZfaHR0cDovL2FpYTQuemF0Y2EuZ292LnNhL0NlcnRFbnJvbGwvUFJaRUludm9pY2VTQ0E0LmV4dGdhenQuZ292LmxvY2FsX1BSWkVJTlZPSUNFU0NBNC1DQSgxKS5jcnQwDgYDVR0PAQH/BAQDAgeAMDwGCSsGAQQBgjcVBwQvMC0GJSsGAQQBgjcVCIGGqB2E0PsShu2dJIfO+xnTwFVmh/qlZYXZhD4CAWQCARIwHQYDVR0lBBYwFAYIKwYBBQUHAwMGCCsGAQUFBwMCMCcGCSsGAQQBgjcVCgQaMBgwCgYIKwYBBQUHAwMwCgYIKwYBBQUHAwIwCgYIKoZIzj0EAwIDSAAwRQIhALE/ichmnWXCUKUbca3yci8oqwaLvFdHVjQrveI9uqAbAiA9hC4M8jgMBADPSzmd2uiPJA6gKR3LE03U75eqbC/rXA==</ds:X509Certificate>
#                             </ds:X509Data>
#                         </ds:KeyInfo>
#                         <ds:Object>
#                             <xades:QualifyingProperties xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" Target="signature">
#                                 <xades:SignedProperties Id="xadesSignedProperties">
#                                     <xades:SignedSignatureProperties>
#                                         <xades:SigningTime>2025-06-22T15:01:39</xades:SigningTime>
#                                         <xades:SigningCertificate>
#                                             <xades:Cert>
#                                                 <xades:CertDigest>
#                                                     <ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
#                                                     <ds:DigestValue>ZDMwMmI0MTE1NzVjOTU2NTk4YzVlODhhYmI0ODU2NDUyNTU2YTVhYjhhMDFmN2FjYjk1YTA2OWQ0NjY2MjQ4NQ==</ds:DigestValue>
#                                                 </xades:CertDigest>
#                                                 <xades:IssuerSerial>
#                                                     <ds:X509IssuerName>CN=PRZEINVOICESCA4-CA, DC=extgazt, DC=gov, DC=local</ds:X509IssuerName>
#                                                     <ds:X509SerialNumber>379112742831380471835263969587287663520528387</ds:X509SerialNumber>
#                                                 </xades:IssuerSerial>
#                                             </xades:Cert>
#                                         </xades:SigningCertificate>
#                                     </xades:SignedSignatureProperties>
#                                 </xades:SignedProperties>
#                             </xades:QualifyingProperties>
#                         </ds:Object>
#                     </ds:Signature>
#                 </sac:SignatureInformation>
#             </sig:UBLDocumentSignatures>
#         </ext:ExtensionContent>
#     </ext:UBLExtension>
# </ext:UBLExtensions>
#   <cbc:ProfileID>reporting:1.0</cbc:ProfileID>
#   <cbc:ID>ACC-SINV-2024-00028</cbc:ID>
#   <cbc:UUID>f00d178e-c686-11ef-a83e-020017019f27</cbc:UUID>
#   <cbc:IssueDate>2024-08-21</cbc:IssueDate>
#   <cbc:IssueTime>09:58:53</cbc:IssueTime>
#   <cbc:InvoiceTypeCode name="0200000">388</cbc:InvoiceTypeCode>
#   <cbc:DocumentCurrencyCode>SAR</cbc:DocumentCurrencyCode>
#   <cbc:TaxCurrencyCode>SAR</cbc:TaxCurrencyCode>
#   <cac:AdditionalDocumentReference>
#     <cbc:ID>ICV</cbc:ID>
#     <cbc:UUID>202400028</cbc:UUID>
#   </cac:AdditionalDocumentReference>
#   <cac:AdditionalDocumentReference>
#     <cbc:ID>PIH</cbc:ID>
#     <cac:Attachment>
#       <cbc:EmbeddedDocumentBinaryObject mimeCode="text/plain">NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRkNGU5MWI0NjcyOWQ3M2EyN2ZiNTdlOQ==</cbc:EmbeddedDocumentBinaryObject>
#     </cac:Attachment>
#   </cac:AdditionalDocumentReference>
  
  
#   <cac:AdditionalDocumentReference>
#         <cbc:ID>QR</cbc:ID>
#         <cac:Attachment>
#             <cbc:EmbeddedDocumentBinaryObject mimeCode="text/plain">AQtaYXRjYShEZW1vKQIPMzk5OTk5OTk5OTAwMDAzAxMyMDI0LTA4LTIxVDA5OjU4OjUzBAUyOTIuMAUDMC4wBixFaStlY3lLRE5Nenc3aWxZV0dEMi9Lc1ZYcHZoMDhiSjAyMHNZa3YrY3VvPQdgTUVZQ0lRQ2FxZW5rd1k5UzlMbGVjVE9JeUNUM0VMQkNIMGZMcFBFZUpCUXEzOE9HYWdJaEFLekxvaGZsNG5tMWNuTzdoT0drZkRrdUJxck5ubUYxdzVoWWs0QUJZc2ozCFgwVjAQBgcqhkjOPQIBBgUrgQQACgNCAAShYIprRJr0UgStM6/S4CQLVUgpfFT2c+nHa+V/jKEx6PLxzTZcluUOru0/J2jyarRqE4yY2jyDCeLte3UpP1R4CUcwRQIhALE/ichmnWXCUKUbca3yci8oqwaLvFdHVjQrveI9uqAbAiA9hC4M8jgMBADPSzmd2uiPJA6gKR3LE03U75eqbC/rXA==</cbc:EmbeddedDocumentBinaryObject>
#         </cac:Attachment>
# </cac:AdditionalDocumentReference><cac:Signature>
#       <cbc:ID>urn:oasis:names:specification:ubl:signature:Invoice</cbc:ID>
#       <cbc:SignatureMethod>urn:oasis:names:specification:ubl:dsig:enveloped:xades</cbc:SignatureMethod>
# </cac:Signature><cac:AccountingSupplierParty>
#     <cac:Party>
#       <cac:PartyIdentification>
#         <cbc:ID schemeID="CRN">1234567</cbc:ID>
#       </cac:PartyIdentification>
#       <cac:PostalAddress>
#         <cbc:StreetName>riyadh</cbc:StreetName>
#         <cbc:BuildingNumber>4444</cbc:BuildingNumber>
#         <cbc:PlotIdentification>riyadh</cbc:PlotIdentification>
#         <cbc:CitySubdivisionName>riyadh</cbc:CitySubdivisionName>
#         <cbc:CityName>riyadh</cbc:CityName>
#         <cbc:PostalZone>87695</cbc:PostalZone>
#         <cbc:CountrySubentity>Saudi Arabia</cbc:CountrySubentity>
#         <cac:Country>
#           <cbc:IdentificationCode>SA</cbc:IdentificationCode>
#         </cac:Country>
#       </cac:PostalAddress>
#       <cac:PartyTaxScheme>
#         <cbc:CompanyID>399999999900003</cbc:CompanyID>
#         <cac:TaxScheme>
#           <cbc:ID>VAT</cbc:ID>
#         </cac:TaxScheme>
#       </cac:PartyTaxScheme>
#       <cac:PartyLegalEntity>
#         <cbc:RegistrationName>Zatca(Demo)</cbc:RegistrationName>
#       </cac:PartyLegalEntity>
#     </cac:Party>
#   </cac:AccountingSupplierParty>
#   <cac:AccountingCustomerParty>
#     <cac:Party>
#       <cac:PartyIdentification>
#         <cbc:ID schemeID="NAT">1070279888</cbc:ID>
#       </cac:PartyIdentification>
#       <cac:PostalAddress>
#         <cbc:StreetName>wdegtrhjm</cbc:StreetName>
#         <cbc:BuildingNumber>2222</cbc:BuildingNumber>
#         <cbc:PlotIdentification>wdegtrhjm</cbc:PlotIdentification>
#         <cbc:CitySubdivisionName>king abdul azeez road</cbc:CitySubdivisionName>
#         <cbc:CityName>rfgthyuj</cbc:CityName>
#         <cbc:PostalZone>78945</cbc:PostalZone>
#         <cbc:CountrySubentity>Saudi Arabia</cbc:CountrySubentity>
#         <cac:Country>
#           <cbc:IdentificationCode>SA</cbc:IdentificationCode>
#         </cac:Country>
#       </cac:PostalAddress>
#       <cac:PartyTaxScheme>
#         <cac:TaxScheme>
#           <cbc:ID>VAT</cbc:ID>
#         </cac:TaxScheme>
#       </cac:PartyTaxScheme>
#       <cac:PartyLegalEntity>
#         <cbc:RegistrationName>Grant Plastics Ltd.</cbc:RegistrationName>
#       </cac:PartyLegalEntity>
#     </cac:Party>
#   </cac:AccountingCustomerParty>
#   <cac:Delivery>
#     <cbc:ActualDeliveryDate>2024-08-22</cbc:ActualDeliveryDate>
#   </cac:Delivery>
#   <cac:PaymentMeans>
#     <cbc:PaymentMeansCode>30</cbc:PaymentMeansCode>
#   </cac:PaymentMeans>
#   <cac:AllowanceCharge>
#     <cbc:ChargeIndicator>false</cbc:ChargeIndicator>
#     <cbc:AllowanceChargeReasonCode>None</cbc:AllowanceChargeReasonCode>
#     <cbc:AllowanceChargeReason>None</cbc:AllowanceChargeReason>
#     <cbc:Amount currencyID="SAR">0.00</cbc:Amount>
#     <cac:TaxCategory>
#       <cbc:ID>Z</cbc:ID>
#       <cbc:Percent>0.00</cbc:Percent>
#       <cac:TaxScheme>
#         <cbc:ID>VAT</cbc:ID>
#       </cac:TaxScheme>
#     </cac:TaxCategory>
#   </cac:AllowanceCharge>
#   <cac:TaxTotal>
#     <cbc:TaxAmount currencyID="SAR">0.0</cbc:TaxAmount>
#   </cac:TaxTotal>
#   <cac:TaxTotal>
#     <cbc:TaxAmount currencyID="SAR">0.0</cbc:TaxAmount>
#     <cac:TaxSubtotal>
#       <cbc:TaxableAmount currencyID="SAR">292.0</cbc:TaxableAmount>
#       <cbc:TaxAmount currencyID="SAR">0.0</cbc:TaxAmount>
#       <cac:TaxCategory>
#         <cbc:ID>Z</cbc:ID>
#         <cbc:Percent>0.00</cbc:Percent>
#         <cbc:TaxExemptionReasonCode>VATEX-SA-HEA</cbc:TaxExemptionReasonCode>
#         <cbc:TaxExemptionReason>Private healthcare to citizen.</cbc:TaxExemptionReason>
#         <cac:TaxScheme>
#           <cbc:ID>VAT</cbc:ID>
#         </cac:TaxScheme>
#       </cac:TaxCategory>
#     </cac:TaxSubtotal>
#   </cac:TaxTotal>
#   <cac:LegalMonetaryTotal>
#     <cbc:LineExtensionAmount currencyID="SAR">292.0</cbc:LineExtensionAmount>
#     <cbc:TaxExclusiveAmount currencyID="SAR">292.0</cbc:TaxExclusiveAmount>
#     <cbc:TaxInclusiveAmount currencyID="SAR">292.0</cbc:TaxInclusiveAmount>
#     <cbc:AllowanceTotalAmount currencyID="SAR">0.0</cbc:AllowanceTotalAmount>
#     <cbc:PayableAmount currencyID="SAR">292.0</cbc:PayableAmount>
#   </cac:LegalMonetaryTotal>
#   <cac:InvoiceLine>
#     <cbc:ID>1</cbc:ID>
#     <cbc:InvoicedQuantity unitCode="Nos">50.0</cbc:InvoicedQuantity>
#     <cbc:LineExtensionAmount currencyID="SAR">182.5</cbc:LineExtensionAmount>
#     <cac:TaxTotal>
#       <cbc:TaxAmount currencyID="SAR">0.0</cbc:TaxAmount>
#       <cbc:RoundingAmount currencyID="SAR">182.5</cbc:RoundingAmount>
#     </cac:TaxTotal>
#     <cac:Item>
#       <cbc:Name>SKU001</cbc:Name>
#       <cac:ClassifiedTaxCategory>
#         <cbc:ID>Z</cbc:ID>
#         <cbc:Percent>0.00</cbc:Percent>
#         <cac:TaxScheme>
#           <cbc:ID>VAT</cbc:ID>
#         </cac:TaxScheme>
#       </cac:ClassifiedTaxCategory>
#     </cac:Item>
#     <cac:Price>
#       <cbc:PriceAmount currencyID="SAR">3.650000</cbc:PriceAmount>
#     </cac:Price>
#   </cac:InvoiceLine>
#   <cac:InvoiceLine>
#     <cbc:ID>2</cbc:ID>
#     <cbc:InvoicedQuantity unitCode="Nos">30.0</cbc:InvoicedQuantity>
#     <cbc:LineExtensionAmount currencyID="SAR">109.5</cbc:LineExtensionAmount>
#     <cac:TaxTotal>
#       <cbc:TaxAmount currencyID="SAR">0.0</cbc:TaxAmount>
#       <cbc:RoundingAmount currencyID="SAR">109.5</cbc:RoundingAmount>
#     </cac:TaxTotal>
#     <cac:Item>
#       <cbc:Name>SKU001</cbc:Name>
#       <cac:ClassifiedTaxCategory>
#         <cbc:ID>Z</cbc:ID>
#         <cbc:Percent>0.00</cbc:Percent>
#         <cac:TaxScheme>
#           <cbc:ID>VAT</cbc:ID>
#         </cac:TaxScheme>
#       </cac:ClassifiedTaxCategory>
#     </cac:Item>
#     <cac:Price>
#       <cbc:PriceAmount currencyID="SAR">3.650000</cbc:PriceAmount>
#     </cac:Price>
#   </cac:InvoiceLine>
# </Invoice>
# """
#     return xml_template


# import hashlib
# import re

# def calculate_invoice_hash(xml_string):
# 	# Strip XML of redundant whitespace, normalize content
# 	normalized_xml = re.sub(r">\s+<", "><", xml_string.strip())  # remove whitespaces between tags
# 	normalized_xml = normalized_xml.replace("\n", "").replace("\r", "").replace("\t", "")
# 	return hashlib.sha256(normalized_xml.encode("utf-8")).hexdigest()

import base64
import struct
import qrcode

def create_tlv_data(tag, value):
    """Create TLV (Tag-Length-Value) data for ZATCA QR code"""
    value_bytes = value.encode('utf-8')
    length = len(value_bytes)
    return struct.pack('B', tag) + struct.pack('B', length) + value_bytes

def generate_zatca_qr_data(seller_name, vat_number, timestamp, total_amount, vat_amount):
    """Generate ZATCA QR code data in TLV format"""
    TAG_SELLER_NAME = 1
    TAG_VAT_NUMBER = 2
    TAG_TIMESTAMP = 3
    TAG_TOTAL_AMOUNT = 4
    TAG_VAT_AMOUNT = 5
    
    # Create TLV data for each field
    tlv_data = b''
    tlv_data += create_tlv_data(TAG_SELLER_NAME, seller_name)
    tlv_data += create_tlv_data(TAG_VAT_NUMBER, vat_number)
    tlv_data += create_tlv_data(TAG_TIMESTAMP, timestamp)
    tlv_data += create_tlv_data(TAG_TOTAL_AMOUNT, total_amount)
    tlv_data += create_tlv_data(TAG_VAT_AMOUNT, vat_amount)
    
    # Encode to base64
    return base64.b64encode(tlv_data).decode('utf-8')

def generate_qr_code(data, filename):
    """Generate QR code image"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(filename)
    return filename
