# Copyright (c) 2025, Simon Wanyama and contributors
# For license information, please see license.txt

import json
import frappe
from frappe.model.document import Document
from frappe.utils import flt

import erpnext

@frappe.whitelist()
def update_payment_method(customer):
	if not frappe.db.exists('Customer', customer):
		frappe.throw(f"Customer with ID {customer} does not exist.")
	payment_method = frappe.db.get_value('Customer', customer, 'custom_payment_method')
	customer_type = frappe.db.get_value('Customer', customer, 'customer_type')
	if customer_type == "Individual":
		return "Cash"
	if payment_method is None:
		return "Cash"
	return payment_method

@frappe.whitelist()
def update_delivery_date(delivery_note):
	if not frappe.db.exists('Delivery Note', delivery_note):
		frappe.throw(f"Delivery Note with ID {delivery_note} does not exist.")
	delivery_date = frappe.db.get_value('Delivery Note', delivery_note, 'posting_date')
	if delivery_date is None:
		frappe.msgprint(f"No posting date set for Delivery Note {delivery_note}.")
	return delivery_date


def set_grand_total_with_retention(doc, method):
	from erpnext.controllers.taxes_and_totals import calculate_taxes_and_totals

	if not doc.custom_retention_amount:
		return

	# Monkey Patch calculate_totals method
	calculate_taxes_and_totals.calculate_totals = custom_calculate_totals

def custom_calculate_totals(self):
	if self.doc.get("taxes"):
		self.doc.grand_total = flt(self.doc.get("taxes")[-1].total) + flt(
			self.doc.get("grand_total_diff")
		)
	else:
		self.doc.grand_total = flt(self.doc.net_total)

	if self.doc.get("taxes"):
		self.doc.total_taxes_and_charges = flt(
			self.doc.grand_total - self.doc.net_total - flt(self.doc.get("grand_total_diff")),
			self.doc.precision("total_taxes_and_charges"),
		)
	else:
		self.doc.total_taxes_and_charges = 0.0

	if self.doc.custom_retention_amount:
		self.doc.grand_total -= self.doc.custom_retention_amount

	self._set_in_company_currency(self.doc, ["total_taxes_and_charges", "rounding_adjustment"])

	if self.doc.doctype in [
		"Quotation",
		"Sales Order",
		"Delivery Note",
		"Sales Invoice",
		"POS Invoice",
	]:
		self.doc.base_grand_total = (
			flt(self.doc.grand_total * self.doc.conversion_rate, self.doc.precision("base_grand_total"))
			if self.doc.total_taxes_and_charges
			else self.doc.base_net_total
		)
	else:
		self.doc.taxes_and_charges_added = self.doc.taxes_and_charges_deducted = 0.0
		for tax in self.doc.get("taxes"):
			if tax.category in ["Valuation and Total", "Total"]:
				if tax.add_deduct_tax == "Add":
					self.doc.taxes_and_charges_added += flt(tax.tax_amount_after_discount_amount)
				else:
					self.doc.taxes_and_charges_deducted += flt(tax.tax_amount_after_discount_amount)

		self.doc.round_floats_in(self.doc, ["taxes_and_charges_added", "taxes_and_charges_deducted"])

		self.doc.base_grand_total = (
			flt(self.doc.grand_total * self.doc.conversion_rate)
			if (self.doc.taxes_and_charges_added or self.doc.taxes_and_charges_deducted)
			else self.doc.base_net_total
		)

		self._set_in_company_currency(self.doc, ["taxes_and_charges_added", "taxes_and_charges_deducted"])

	self.doc.round_floats_in(self.doc, ["grand_total", "base_grand_total"])

	self.set_rounded_total()

