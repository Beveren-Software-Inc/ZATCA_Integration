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
		# self.genereate_zatca_compliance_csid()
		self.invoke_zatca_compliance_invoice()

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
		response = response.json()
		
		self.request_id = response['requestID']
		self.disposition_message = response['dispositionMessage']
		self.binary_security_token = response['binarySecurityToken']
		self.secret = response['secret']
		self.errors = response['errors']
		

	def invoke_zatca_compliance_invoice(self):

		# Get ZATCA Settings and ZATCA Environment
		zatca_settings = frappe.get_doc("Zatca Settings", 'Zatca Settings')
		zatca_environment = frappe.get_doc("Zatca Environment", zatca_settings.zatca_environment)
		zatca_compliance_csid = frappe.get_doc("Zatca Compliance CSID", "Zatca Compliance CSID")

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
			auth=HTTPBasicAuth(zatca_compliance_csid.binary_security_token, zatca_compliance_csid.secret), 
			data=json.dumps(invoice_request)
		)
		print(response.json())
		
		# TODO Update Zatca Compliance CSID Status
		# zatca_compliance_csid.standard_invoice = True
		# zatca_compliance_csid.save()

		return response.json()
		
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
		

	
    
  
