# Copyright (c) 2023, Shakir PM and contributors
# For license information, please see license.txt

import frappe
import requests
from frappe.model.document import Document


class ZatcaSettings(Document):

	def before_save(self):
		self.genereate_zatca_compliance_csid()

	#TODO: Add button Generate CSR
	def genereate_zatca_compliance_csid(self):
		
		zatca_settings = frappe.get_doc("Zatca Settings", 'Zatca Settings')
		zatca_environment = frappe.get_doc("Zatca Environment", zatca_settings.zatca_environment)

		# Beveren Zatca Backend URL
		url = zatca_environment.csr_generate_api + 'generateCSR'
		print(url)
		
		# Set the headers
		headers = {
			'clientId': zatca_environment.client_id,
			'clientSecret': zatca_environment.client_secret,
			'isNonPrd': str(zatca_environment.non_production),
			'isSim': str(zatca_environment.simulation),
			'Content-Type': 'application/json'
		}
		print(headers)

		# Encode the string into bytes, then encode it using base64
		data = {
			'commonName': zatca_settings.csrcommonname,
			'serialNumber': zatca_settings.csrserialnumber,
			'organizationIdentifier': zatca_settings.csrorganizationidentifier,
			'organizationUnitName': zatca_settings.csrorganizationunitname,
			'organizationName': zatca_settings.csrorganizationname,
			'countryName': zatca_settings.csrcountryname,
			'invoiceType': zatca_settings.csrinvoicetype,
			'location': zatca_settings.csrlocationaddress,
			'industry': zatca_settings.csrindustrybusinesscategory,
		}
		print(data)

		# Make the POST request
		response = requests.post(url, headers=headers, json=data)
		response = response.json()
		print(response)

		# Save the CSR and Private Key
		self.csr = response['csr']
		self.private_key = response['privateKey']

		# Save zatca_settings DocType updates
		# zatca_settings.save()
