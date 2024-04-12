# Copyright (c) 2024, Shakir PM and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ZatcaSettings(Document):
	def before_save(self):
		# If zatca_phase is ZATCA Phase 2, check if default_production_csid is active
		if not self.zatca_phase == "ZATCA Phase 1":
			production_csid = frappe.get_doc("Production CSID", self.default_production_csid)
			if production_csid.is_active == False:
				frappe.throw("Default Production CSID is not active")