


# Copyright (c) 2023, Shakir PM and contributors
# For license information, please see license.txt

import frappe
import requests
from requests.auth import HTTPBasicAuth
from frappe.model.document import Document


class ProductionCSID(Document):

	def before_save(self):
		compliance_csid = frappe.get_doc("Compliance CSID", self.compliance_csid)
		csr_settings = frappe.get_doc("Zatca CSR Settings", compliance_csid.csr_settings)

		if csr_settings.csrinvoicetype == "1100":
			if not (compliance_csid.standard_invoice and compliance_csid.standard_debit_note and compliance_csid.standard_credit_note and
					compliance_csid.simplified_invoice and compliance_csid.simplified_debit_note and compliance_csid.simplified_credit_note):
				frappe.throw("All standard and simplified invoices, debit notes, and credit notes must be validated for type 1100.")
		elif csr_settings.csrinvoicetype == "1000":
			if not (compliance_csid.standard_invoice and compliance_csid.standard_debit_note and compliance_csid.standard_credit_note):
				frappe.throw("All standard invoices, debit notes, and credit notes must be validated for type 1000.")
		elif csr_settings.csrinvoicetype == "0100":
			if not (compliance_csid.simplified_invoice and compliance_csid.simplified_debit_note and compliance_csid.simplified_credit_note):
				frappe.throw("All simplified invoices, debit notes, and credit notes must be validated for type 0100.")
		else:
			frappe.throw("Invalid Invoice Type in ZATCA CSR Settings: " + csr_settings.csrinvoicetype)
	
	@frappe.whitelist()
	def generate_zatca_production_csid(self):
		
		compliance_csid = frappe.get_doc("Compliance CSID", self.compliance_csid)
		zatca_settings = frappe.get_doc("Zatca CSR Settings", compliance_csid.csr_settings)
		zatca_environment = frappe.get_doc("Zatca Environment", zatca_settings.zatca_environment)

		headers = {
			'accept': 'application/json',
			'Accept-Version': 'V2',
			'Content-Type': 'application/json'
		}
		data = {
			"compliance_request_id": compliance_csid.request_id
		}

		try:
			response = requests.post(zatca_environment.production_csid_api, headers=headers, auth=HTTPBasicAuth(compliance_csid.binary_security_token, compliance_csid.secret), json=data)
			response.raise_for_status()
			response_json = response.json()
			
			self.is_active = True
			self.created_time = frappe.utils.now_datetime()
			self.request_id = response_json.get('requestID', '')
			self.disposition_message = response_json.get('dispositionMessage', '')
			self.binary_security_token = response_json.get('binarySecurityToken', '')
			self.token_type = response_json.get('tokenType', '')
			self.secret = response_json.get('secret', '')
			self.errors = response_json.get('errors', '{}')
			from zatca_integration.saudi_arabia_electronic_invoicing.utils import build_certificate_data, create_public_key
			self.certificate = build_certificate_data(response_json.get('binarySecurityToken', ''))
			self.public_key = create_public_key(self.certificate)
			
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

		frappe.throw(f"Error in generating ZATCA Production CSID: {self.errors}")


