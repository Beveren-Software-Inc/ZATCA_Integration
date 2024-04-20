# Copyright (c) 2023, Shakir PM and contributors
# For license information, please see license.txt

import json
import frappe
import base64
import requests
from requests.auth import HTTPBasicAuth
from frappe.model.document import Document
from zatca_integration.compliance_util import generate_tax_invoice_xml, generate_credit_note_xml, generate_debit_note_xml
from zatca_integration.common_util import get_seller_information, get_buyer_information, generate_clearance_request, generate_reporting_request


class ComplianceCSID(Document):

	def before_save(self):
		csr_settings = frappe.get_doc("Zatca CSR Settings", self.csr_settings)
		if csr_settings.csr == "" or csr_settings.csr is None:
			frappe.throw("CSR is not generated. Please generate CSR")

	@frappe.whitelist()
	def genereate_zatca_compliance_csid(self):

		# Get ZATCA CSR Settings and ZATCA Environment
		csr_settings = frappe.get_doc("Zatca CSR Settings", self.csr_settings)
		zatca_environment = frappe.get_doc("Zatca Environment", csr_settings.zatca_environment)

		# Make Call to ZATCA Compliance CSID API to get Compliance CSID
		headers = {
			'accept': 'application/json',
			'OTP': self.otp,
			'Accept-Version': 'V2',
			'Content-Type': 'application/json'
		}
		data = {
			"csr": csr_settings.csr
		}
		response = requests.post(zatca_environment.compliance_csid_api, headers=headers, json=data)

		try:
			response_json = response.json()
			print(response_json)
		except ValueError:
			# Handle the case where response is not in JSON format
			response_json = None

		if response.status_code == 200 and response_json is not None:
			# If response is 200 OK and JSON format, extract the necessary data
			self.created_time = frappe.utils.now_datetime()
			self.request_id = response_json.get('requestID', '')
			self.disposition_message = response_json.get('dispositionMessage', '')
			self.binary_security_token = response_json.get('binarySecurityToken', '')
			self.secret = response_json.get('secret', '')
			self.errors = response_json.get('errors', '{}')

			# Update Zatca Compliance CSID Status False
			self.reset_compliance_csid_status(False)
			self.save()
		else:
			# If response is not 200 OK or not JSON, handle the error case
			if response_json:
				# If there is a JSON response, use it
				self.errors = response_json
			else:
				# If there is no JSON response, use the response text or a default error message
				self.errors = response.text if response.text else 'Error with no response data'
			self.save()
			print(response.status_code)
			print(self.errors)
			# Raise an exception with the error message	
			frappe.throw("Error in generating ZATCA Compliance CSID")

	@frappe.whitelist()
	def validate_zatca_compliance_csid(self):

		if self.binary_security_token is None or self.binary_security_token == "":
			frappe.throw("Binary Security Token is not generated. Please Generate ZATCA Compliance CSID")

		# Get ZATCA Settings
		csr_settings = frappe.get_doc("Zatca CSR Settings", self.csr_settings)

		# Seller Information
		seller = get_seller_information(csr_settings)

		# Buyer Information
		test_buyer = frappe.get_doc("Customer", self.buyer) 
		buyer = get_buyer_information(test_buyer)

		if csr_settings.csrinvoicetype == "1100":
			self.invoke_complaince_check("standard", csr_settings, seller, buyer)
			self.invoke_complaince_check("simplified", csr_settings, seller, buyer)
		elif csr_settings.csrinvoicetype == "1000":
			self.invoke_complaince_check("standard", csr_settings, seller, buyer)
		elif csr_settings.csrinvoicetype == "0100":
			self.invoke_complaince_check("simplified", csr_settings, seller, buyer)
		else:
			frappe.throw("Invalid Invoice Type in ZATCA CSR Settings : " + csr_settings.csrinvoicetype)
		
		# Update Zatca Compliance CSID Status
		self.save()

	def invoke_complaince_check(self, invoiceType, csr_settings, seller, buyer):

		first_invoice_hash = "NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRkNGU5MWI0NjcyOWQ3M2EyN2ZiNTdlOQ=="

		# Compliance Standard Invoice
		print("####  Tax Invoice START #### InvoiceType: " + invoiceType + " ####)")
		tax_invoice = generate_tax_invoice_xml(
			invoiceType, "INV-00001", seller, buyer,
			first_invoice_hash
		)
		print(tax_invoice["xml"])
		tax_invoice_status, tax_invoice_hash = self.invoke_compliance_invoice_api(invoiceType, csr_settings, tax_invoice["xml"])
		if invoiceType == "standard":
			self.standard_invoice = tax_invoice_status
		elif invoiceType == "simplified":
			self.simplified_invoice = tax_invoice_status
		print("####  Tax Invoice END #### InvoiceType: " + invoiceType + " ####)")

		# Compliance Standard Credit Note
		print("####  Credit Note START #### InvoiceType: " + invoiceType + " ####)")
		credit_note = generate_credit_note_xml(
			invoiceType, "INV-00002", seller, buyer, 
			tax_invoice["invoiceNumber"], 
			tax_invoice["invoiceDeliveryDate"], 
			tax_invoice_hash
		)
		print(credit_note["xml"])
		credit_note_status, credit_note_hash = self.invoke_compliance_invoice_api(invoiceType, csr_settings, credit_note["xml"])
		if invoiceType == "standard":
			self.standard_credit_note = credit_note_status
		elif invoiceType == "simplified":
			self.simplified_credit_note = credit_note_status
		print("####  Credit Note END #### InvoiceType: " + invoiceType + " ####)")

		# Compliance Standard Invoice
		print("####  Tax Invoice START #### InvoiceType: " + invoiceType + " ####)")
		tax_invoice = generate_tax_invoice_xml(
			invoiceType, "INV-00003", seller, buyer,
			credit_note_hash
		)
		print(tax_invoice["xml"])
		tax_invoice_status, tax_invoice_hash = self.invoke_compliance_invoice_api(invoiceType, csr_settings, tax_invoice["xml"])
		print("####  Tax Invoice END #### InvoiceType: " + invoiceType + " ####)")

		# Compliance Debit Note
		print("####  Debit Note START #### InvoiceType: " + invoiceType + " ####)")
		debit_note = generate_debit_note_xml(
			invoiceType, "INV-00004", seller, buyer, 
			tax_invoice["invoiceNumber"], 
			tax_invoice["invoiceDeliveryDate"], 
			tax_invoice_hash
		)
		print(credit_note["xml"])
		debit_note_status, debit_note_hash = self.invoke_compliance_invoice_api(invoiceType, csr_settings, debit_note["xml"])
		if invoiceType == "standard":
			self.standard_debit_note = debit_note_status
		elif invoiceType == "simplified":
			self.simplified_debit_note = debit_note_status
		print("####  Debit Note END #### InvoiceType: " + invoiceType + " ####)")

	def invoke_compliance_invoice_api(self, invoiceType, csr_settings, invoice_xml):

		zatca_environment = frappe.get_doc("Zatca Environment", csr_settings.zatca_environment)

		if invoiceType == "standard":
			# Generate Clearance Request from Backend
			invoice_request = generate_clearance_request(
				zatca_environment.csr_generate_api,
				zatca_environment.client_id,
				zatca_environment.client_secret,
				invoice_xml
			)
		elif invoiceType == "simplified":
			# Generate Reporting Request from Backend
			invoice_request = generate_reporting_request(
				zatca_environment.csr_generate_api,
				zatca_environment.client_id,
				zatca_environment.client_secret,
				csr_settings.private_key,
				self.decode_certificate(self.binary_security_token),
				invoice_xml
			)
		else:
			frappe.throw("Invalid Invoice Type, type: " + invoiceType)
		
		# Post Invoice Request to Zatca Compliance Invoice API
		headers = {
			'accept': 'application/json',
			'Accept-Language': 'en',
			'Accept-Version': 'V2',
			'Content-Type': 'application/json'
		}

		# Post Zatca Compliance Invoice API
		response = requests.post(
			zatca_environment.compliance_invoice_api, 
			headers=headers, 
			auth=HTTPBasicAuth(self.binary_security_token, self.secret), 
			data=json.dumps(invoice_request)
		)

		print(response.json())

		if response.status_code == 200:
			return True, invoice_request["invoiceHash"]
		else:
			return False, None
		
	def reset_compliance_csid_status(self, status):
		self.standard_invoice = status
		self.standard_debit_note = status
		self.standard_credit_note = status
		self.simplified_invoice = status
		self.simplified_debit_note = status
		self.simplified_credit_note = status

	def decode_certificate(self, compliance_certificate):
		decoded_compliance_certificate = base64.b64decode(compliance_certificate.encode('utf-8'))
		return decoded_compliance_certificate.decode('utf-8')