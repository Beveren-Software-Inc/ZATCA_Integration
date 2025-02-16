# Copyright (c) 2025, Beveren Software Inc and contributors
# For license information, please see license.txt

import frappe
import erpnext

from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice

class CustomSalesInvoice(SalesInvoice):
	def get_gl_entries(self, warehouse_account=None):
		from erpnext.accounts.general_ledger import merge_similar_entries

		gl_entries = []

		self.make_retention_gl_entry(gl_entries)

		self.make_customer_gl_entry(gl_entries)

		self.make_tax_gl_entries(gl_entries)
		self.make_internal_transfer_gl_entries(gl_entries)

		self.make_item_gl_entries(gl_entries)
		self.make_precision_loss_gl_entry(gl_entries)
		self.make_discount_gl_entries(gl_entries)

		gl_entries = make_regional_gl_entries(gl_entries, self)

		# merge gl entries before adding pos entries
		gl_entries = merge_similar_entries(gl_entries)

		self.make_loyalty_point_redemption_gle(gl_entries)
		self.make_pos_gl_entries(gl_entries)

		self.make_write_off_gl_entry(gl_entries)
		self.make_gle_for_rounding_adjustment(gl_entries)

		return gl_entries

	
	def make_retention_gl_entry(self, gl_entries):
		if self.custom_retention_account and self.custom_retention_amount:
			against_voucher = self.name
			gl_entries.append(
				self.get_gl_dict(
					{
						"account": self.custom_retention_account,
						"party_type": "Customer",
						"party": self.customer,
						"due_date": self.due_date,
						"against": against_voucher,
						"debit": self.custom_retention_amount,
						"debit_in_account_currency": self.custom_retention_amount,
						"against_voucher": against_voucher,
						"against_voucher_type": self.doctype,
						"cost_center": self.cost_center,
						"project": self.project,
					},
					self.party_account_currency,
					item=self,
				)
			)

@erpnext.allow_regional
def make_regional_gl_entries(gl_entries, doc):
	return gl_entries