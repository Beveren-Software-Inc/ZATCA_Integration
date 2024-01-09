# Copyright (c) 2023, Shakir PM and contributors
# For license information, please see license.txt

import json
import base64
import frappe
import requests
from requests.auth import HTTPBasicAuth
from frappe.model.document import Document
from zatca_integration.compliance_util import generate_compliance_standard_invoice, generate_compliance_standard_credit_note


class ComplianceCSID(Document):

	def before_save(self):
		pass

	@frappe.whitelist()
	def genereate_zatca_compliance_csid(self):

		# Get ZATCA CSR Settings and ZATCA Environment
		zatca_settings = frappe.get_doc("Zatca CSR Settings", self.csr_settings)
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
			self.save()
			print(response.status_code)
			print(self.errors)
			# Raise an exception with the error message	
			frappe.throw("Error in generating ZATCA Compliance CSID")

	@frappe.whitelist()
	def invoke_zatca_compliance_invoice(self):

		# Get ZATCA Settings and ZATCA Environment
		zatca_settings = frappe.get_doc("Zatca CSR Settings", self.csr_settings)
		zatca_environment = frappe.get_doc("Zatca Environment", zatca_settings.zatca_environment)

		# Seller Information
		seller = self.get_seller_information(zatca_settings)

		# Buyer Information
		test_buyer = frappe.get_doc("Customer", self.buyer) 
		buyer = self.get_buyer_information(frappe.get_doc("Customer", test_buyer) )

		# Issue Compliance for Invoice, Credit Note and Debit Note
		self.invoke_complaince_check(zatca_environment, seller, buyer)
		
		# Update Zatca Compliance CSID Status
		self.reset_compliance_csid_status(True)
		self.save()

	def invoke_complaince_check(self, zatca_environment, seller, buyer):

		first_invoice_hash = "NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRkNGU5MWI0NjcyOWQ3M2EyN2ZiNTdlOQ=="

		# Compliance Standard Invoice
		print("#################### Compliance Standard Invoice START ####################")
		standard_invoice_number  = "INV-00001"
		standard_invoice = generate_compliance_standard_invoice(
			standard_invoice_number, seller, buyer,
			first_invoice_hash
		)
		print(standard_invoice["xml"])
		standard_invoice_hash = self.invoke_compliance_invoice_api(zatca_environment, standard_invoice["xml"])
		print("#################### Compliance Standard Invoice END ####################")

		# Compliance Standard Credit Note
		print("#################### Compliance Standard Credit Note START ####################")
		credit_note_invoice_number = "INV-00002"
		standard_credit_note = generate_compliance_standard_credit_note(
			credit_note_invoice_number, seller, buyer, 
			standard_invoice["invoiceNumber"], 
			standard_invoice["invoiceDeliveryDate"], 
			standard_invoice_hash
		)
		print(standard_credit_note["xml"])
		standard_credit_note_hash = self.invoke_compliance_invoice_api(zatca_environment, standard_credit_note["xml"])
		print("#################### Compliance Standard Credit Note END ####################")

		# Compliance Standard Invoice
		print("#################### Compliance Standard Invoice START ####################")
		standard_invoice_number  = "INV-00003"
		standard_invoice = generate_compliance_standard_invoice(
			standard_invoice_number, seller, buyer,
			standard_credit_note_hash
		)
		print(standard_invoice["xml"])
		standard_invoice_hash = self.invoke_compliance_invoice_api(zatca_environment, standard_invoice["xml"])
		print("#################### Compliance Standard Invoice END ####################")

		# Compliance Standard Debit Note
		print("#################### Compliance Standard Debit Note START ####################")
		debit_note_invoice_number = "INV-00004"
		standard_credit_note = generate_compliance_standard_credit_note(
			debit_note_invoice_number, seller, buyer, 
			standard_invoice["invoiceNumber"], 
			standard_invoice["invoiceDeliveryDate"], 
			standard_invoice_hash
		)
		print(standard_credit_note["xml"])
		standard_debit_note_hash = self.invoke_compliance_invoice_api(zatca_environment, standard_credit_note["xml"])
		print("#################### Compliance Standard Debit Note END ####################")

	def invoke_compliance_invoice_api(self, zatca_environment, invoice_xml):
		# Get Invoice Request Body from Backend
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

		# Post Zapca Compliance Invoice API
		response = requests.post(
			zatca_environment.compliance_invoice_api, 
			headers=headers, 
			auth=HTTPBasicAuth(self.binary_security_token, self.secret), 
			data=json.dumps(invoice_request)
		)
		print(response.status_code)
		print(response.json())

		return invoice_request["invoiceHash"]
	
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

		try:
			# Make the POST request
			response = requests.post(url, headers=headers, json=data)
			response_json = response.json()
		except requests.exceptions.JSONDecodeError:
			frappe.throw("Error in generating invoice request from backend")

		return response_json

	def get_seller_information(self, zatca_settings):
		return {
			"registrationScheme": zatca_settings.registration_scheme,
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

	def get_buyer_information(self, customer):
		return {
            "organizationName":  customer.custom_organization_name,
            "vatNumber":  customer.custom_vat_number,
			"streetName": customer.custom_street_name,
			"buildingNumber":  customer.custom_building_number,
			"citySubdivisionName":  customer.custom_city_subdivision_name,
			"cityName":  customer.custom_city_name,
			"postalZone":  customer.custom_postal_zone,
			"countryCode":  customer.custom_country_code
		}	
	
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
