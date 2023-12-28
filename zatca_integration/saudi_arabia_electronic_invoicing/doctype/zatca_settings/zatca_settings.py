# Copyright (c) 2023, Shakir PM and contributors
# For license information, please see license.txt

import frappe
import requests
from frappe.model.document import Document


class ZatcaSettings(Document):

	def before_save(self):
		pass
		#self.genereate_csr()

	#TODO: Add button Generate CSR
	def genereate_csr(self):
		
		# Get ZATCA Environment
		zatca_environment = frappe.get_doc("Zatca Environment", self.zatca_environment)

		# Beveren Zatca Backend URL
		url = zatca_environment.csr_generate_api + 'generateCSR'
		
		# Set the headers
		headers = {
			'clientId': zatca_environment.client_id,
			'clientSecret': zatca_environment.client_secret,
			'isNonPrd': str(zatca_environment.non_production),
			'isSim': str(zatca_environment.simulation),
			'Content-Type': 'application/json'
		}

		# Encode the string into bytes, then encode it using base64
		data = {
			'commonName': self.csrcommonname,
			'serialNumber': self.csrserialnumber,
			'organizationIdentifier': self.csrorganizationidentifier,
			'organizationUnitName': self.csrorganizationunitname,
			'organizationName': self.csrorganizationname,
			'countryName': self.csrcountryname,
			'invoiceType': self.csrinvoicetype,
			'location': self.csrlocationaddress,
			'industry': self.csrindustrybusinesscategory,
		}

		# Make the POST request
		response = requests.post(url, headers=headers, json=data)
		
		try:
			response_json = response.json()
		except ValueError:
			# Handle the case where response is not in JSON format
			response_json = None

		if response.status_code == 200 and response_json is not None:
			# Save the CSR and Private Key
			self.csr = response_json['csr']
			self.private_key = response_json['privateKey']
		else:
			# Raise an exception
			frappe.throw("Error in generating CSR")
