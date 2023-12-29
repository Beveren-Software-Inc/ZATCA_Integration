# Copyright (c) 2023, Shakir PM and contributors
# For license information, please see license.txt

import json
import base64
import frappe
import requests
from requests.auth import HTTPBasicAuth
from frappe.model.document import Document
from zatca_integration.util import generate_compliance_invoice_xml


class ZatcaComplianceCSID(Document):

	def before_save(self):
		pass
		# self.genereate_zatca_compliance_csid()
		# self.invoke_zatca_compliance_invoice()

	#TODO: Add button Generate CSID
	@frappe.whitelist()
	def genereate_zatca_compliance_csid(self):

		# Get ZATCA Settings and ZATCA Environment
		zatca_settings = frappe.get_doc("Zatca Settings", 'Zatca Settings')
		zatca_environment = frappe.get_doc("Zatca Environment", zatca_settings.zatca_environment)

		# Make Call to ZATCA Compliance CSID API to get Compliance CSID
		headers = {
			'accept': 'application/json',
			'OTP': self.otp,
			'Accept-Version': 'V2',
			'Content-Type': 'application/json'
		}
		data = {
			"csr": zatca_settings.csr
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

			# Raise an exception with the error message	
			frappe.throw("Error in generating ZATCA Compliance CSID")

	#TODO: Add button Vallidate CSID
	@frappe.whitelist()
	def invoke_zatca_compliance_invoice(self):

		# Get ZATCA Settings and ZATCA Environment
		zatca_settings = frappe.get_doc("Zatca Settings", 'Zatca Settings')
		zatca_environment = frappe.get_doc("Zatca Environment", zatca_settings.zatca_environment)

		# Get Invoice Request Body
		uuid, invoice_xml = generate_compliance_invoice_xml()
		invoice_request = self.get_invoice_request(
			zatca_environment.csr_generate_api, 
			zatca_environment.client_id, 
			zatca_environment.client_secret, 
			invoice_xml
		)

		# Post Invoice Request to Zatca Compliance Invoice API
		headers = {
        'accept': 'application/json',
        'Accept-Language': 'en',
        'Accept-Version': 'V2',
        'Content-Type': 'application/json'
    	}
		response = requests.post(
			zatca_environment.compliance_invoice_api, 
			headers=headers, 
			auth=HTTPBasicAuth(self.binary_security_token, self.secret), 
			data=json.dumps(invoice_request)
		)
		print(response.json())
		
		# Update Zatca Compliance CSID Status TODO All Types
		self.reset_compliance_csid_status(True)
		self.save()
		
	def get_invoice_request(self, url, clientId, clientSecret, invoice):
		url = url + 'generateInvoiceRequest'
		# Set the headers
		headers = {
			'clientId': clientId,
			'clientSecret': clientSecret,
			'Content-Type': 'application/json'
		}

		# Encode the string into bytes, then encode it using base64
		data = {
			'invoice': self.encode_invoice(invoice)
		}

		# Make the POST request
		response = requests.post(url, headers=headers, json=data)

		return response.json()

	def encode_invoice(self, invoice):
		input_bytes = invoice.encode('utf-8')
		encoded_bytes = base64.b64encode(input_bytes)
		encoded_string = encoded_bytes.decode('utf-8')
		return encoded_string
	
	def decode_invoice(self, encoded_invoice):
		encoded_bytes = encoded_invoice.encode('utf-8')
		decoded_bytes = base64.b64decode(encoded_bytes)
		decoded_string = decoded_bytes.decode('utf-8')
		return decoded_string
		
	def reset_compliance_csid_status(self, status):
		self.standard_invoice = status
		self.standard_debit_note = status
		self.standard_credit_note = status
		self.simplified_invoice = status
		self.simplified_debit_note = status
		self.simplified_credit_note = status
