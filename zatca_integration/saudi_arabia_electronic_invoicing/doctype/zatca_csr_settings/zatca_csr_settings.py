# Copyright (c) 2024, Shakir PM and contributors
# For license information, please see license.txt

import frappe
import requests
from frappe.model.document import Document
import uuid
from typing import Optional
from zatca_integration.saudi_arabia_electronic_invoicing.background_task import (
    send_multiple_signed_compliance_invoices_to_zatca, prod_csid_auto_renew
)
from zatca_integration.saudi_arabia_electronic_invoicing.utils import get_or_create_scheduled_job
class ZatcaCSRSettings(Document):
	def before_save(self):
		if not self.csrserialnumber:
			self.csrserialnumber = self.generate_serial_number()

		if not isinstance(self.building_number, int) or not (1000 <= self.building_number <= 9999):
			frappe.throw("Building Number must be a 4-digit integer")

		if not isinstance(self.postal_zone, int) or not (10000 <= self.postal_zone <= 99999):
			frappe.throw("Postal Zone must be a 5-digit integer")
		
	def generate_serial_number(self):
		serial_number = str(uuid.uuid4())
		return "1-ERPNext|2-V15|3-" + serial_number

	@frappe.whitelist()
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
	
		response = requests.post(url, headers=headers, json=data)
		
		try:
			response_json = response.json()
		except ValueError:
			# Handle the case where response is not in JSON format
			response_json = None

		if response.status_code == 200 and response_json is not None:
			# Save the CSR and Private Key
			self.csr = response_json['csr']
			self.csr_pem_format = response_json['csrPemFormat']
			self.private_key = response_json['privateKey']
			self.private_key_pem_format = response_json['privateKeyPemFormat']
			self.created_time = frappe.utils.now_datetime()
			self.save()
		else:
			frappe.throw(f"Error in generating CSR: {response.text}")
	def on_update(self):
		on_update_create_schedulers(self)

            
def on_update_create_schedulers(doc):
    if doc.b2c_auto_sales_submission_enabled:
        get_or_create_scheduled_job(
			f"{send_multiple_signed_compliance_invoices_to_zatca.__module__}.{send_multiple_signed_compliance_invoices_to_zatca.__name__}",
			doc.sales_information_submission_frequency, 
			(
				doc.sales_info_cron_format
			if doc.sales_information_submission_frequency == "Cron"
			else None
			),

		)
        
    if doc.allow_auto_renewal_production_csid:
        get_or_create_scheduled_job(
			f"{prod_csid_auto_renew.__module__}.{prod_csid_auto_renew.__name__}",
			doc.auto_renewal_frequency, 
			(
				doc.production_csid_cron_format
			if doc.auto_renewal_frequency == "Cron"
			else None
			),

		)
        