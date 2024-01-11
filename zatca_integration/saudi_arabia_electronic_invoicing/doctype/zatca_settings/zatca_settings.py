# Copyright (c) 2024, Shakir PM and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ZatcaSettings(Document):
	def before_save(self):
		production_csid = frappe.get_doc("Production CSID", self.default_production_csid)
		if production_csid.is_active == False:
			frappe.throw("Default Production CSID is not active")