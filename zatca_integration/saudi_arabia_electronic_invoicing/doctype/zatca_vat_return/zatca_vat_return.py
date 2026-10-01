import frappe
from frappe.model.document import Document


class ZATCAVATReturn(Document):
    def validate(self):
        if frappe.utils.getdate(self.from_date) > frappe.utils.getdate(self.to_date):
            frappe.throw(frappe._("From Date cannot be after To Date"))
