


# Copyright (c) 2023, Shakir PM and contributors
# For license information, please see license.txt

import frappe
import requests
from requests.auth import HTTPBasicAuth
from frappe.model.document import Document


class ProductionCSID(Document):

	def before_save(self):
		pass
	
	@frappe.whitelist()
	def genereate_zatca_production_csid(self):
		
		# Get ZATCA Settings and ZATCA Environment
		compliance_csid = frappe.get_doc("Compliance CSID", self.compliance_csid)
		zatca_settings = frappe.get_doc("Zatca CSR Settings", compliance_csid.csr_settings)
		zatca_environment = frappe.get_doc("Zatca Environment", zatca_settings.zatca_environment)
		

		# Make Call to ZATCA Production CSID API to get Production CSID
		headers = {
			'accept': 'application/json',
			'Accept-Version': 'V2',
			'Content-Type': 'application/json'
		}
		data = {
			"compliance_request_id": compliance_csid.request_id
		}
		response = requests.post(
			zatca_environment.production_csid_api, 
			headers=headers,
			auth=HTTPBasicAuth(compliance_csid.binary_security_token, compliance_csid.secret), 
			json=data
		)

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
			self.token_type = response_json.get('tokenType', '')
			self.secret = response_json.get('secret', '')
			self.errors = response_json.get('errors', '{}')
			self.zatca_environment = zatca_environment.name
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
			frappe.throw("Error in generating ZATCA Production CSID")


