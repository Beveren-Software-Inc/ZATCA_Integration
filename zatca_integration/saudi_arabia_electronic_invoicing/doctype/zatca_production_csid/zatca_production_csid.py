# Copyright (c) 2023, Shakir PM and contributors
# For license information, please see license.txt

import frappe
import requests
from requests.auth import HTTPBasicAuth
from frappe.model.document import Document


class ZatcaProductionCSID(Document):

	def before_save(self):
		self.genereate_zatca_production_csid()

	#TODO: Add button Generate CSID
	#TODO: Validate Complaince CSID is validated
	def genereate_zatca_production_csid(self):
		
		# Get ZATCA Settings and ZATCA Environment
		zatca_settings = frappe.get_doc("Zatca Settings", 'Zatca Settings')
		zatca_environment = frappe.get_doc("Zatca Environment", zatca_settings.zatca_environment)
		zatca_compliance_csid = frappe.get_doc("Zatca Compliance CSID", "Zatca Compliance CSID")

		# Make Call to ZATCA Production CSID API to get Production CSID
		headers = {
			'accept': 'application/json',
			'Accept-Version': 'V2',
			'Content-Type': 'application/json'
		}
		data = {
			"compliance_request_id": zatca_compliance_csid.request_id
		}
		response = requests.post(
			zatca_environment.production_csid_api, 
			headers=headers,
			auth=HTTPBasicAuth(zatca_compliance_csid.binary_security_token, zatca_compliance_csid.secret), 
			json=data
		)
		
		response = response.json()
		
		self.request_id = response['requestID']
		self.disposition_message = response['dispositionMessage']
		self.binary_security_token = response['binarySecurityToken']
		self.token_type = response['tokenType']
		self.secret = response['secret']
		self.errors = response.get('errors', '{}')


