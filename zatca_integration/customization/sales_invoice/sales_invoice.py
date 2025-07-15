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

def set_base_retention_amount(doc, method):
	if not doc.custom_retention_amount:
		return
	if not doc.conversion_rate:
		frappe.throw(_('Please set Exchange Rate First'))
	doc.custom_base_retention_amount = doc.conversion_rate * doc.custom_retention_amount

def set_grand_total_with_retention(doc, method):
	from erpnext.controllers.taxes_and_totals import calculate_taxes_and_totals

	if not doc.doctype == 'Sales Invoice':
		return
	if not doc.custom_retention_account or not doc.custom_retention_amount:
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

	# Make Grand Total Less Retention
	if (self.doc.doctype == "Sales Invoice" 
		and self.doc.custom_retention_account 
		and self.doc.custom_retention_amount):
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


@frappe.whitelist()
def get_batch(customer,sales_invoice,item):
	values = {'customer': customer,'sales_invoice': sales_invoice,'item':item}
	batch_list = frappe.db.sql("""
    SELECT `tabSales Invoice`.NAME,
       `tabSales Invoice`.customer,
       `tabSales Invoice Item`.qty
    FROM `tabSales Invoice`
    JOIN `tabSales Invoice Item`
    ON `tabSales Invoice`.NAME = `tabSales Invoice Item`.parent
    WHERE `tabSales Invoice`.customer = %(customer)s
    AND `tabSales Invoice`.NAME = %(sales_invoice)s
    AND `tabSales Invoice Item`.item_code = %(item)s
    AND `tabSales Invoice`.docstatus = 1
    AND `tabSales Invoice`.status != "Cancelled"
            """,
    values=values, as_dict = 1)
	return batch_list




@frappe.whitelist()
def returned_qty(customer, sales_invoice, item):
    values = {
        'customer': customer,
        'sales_invoice': sales_invoice,
        'item': item
    }

    total_returned = frappe.db.sql("""
        SELECT 
            `tabCredit Details`.sales_invoice,
            `tabSales Invoice`.customer,
            SUM(`tabCredit Details`.qtr) AS total_returned_qty
        FROM 
            `tabSales Invoice`
        JOIN 
            `tabCredit Details` ON `tabSales Invoice`.name = `tabCredit Details`.parent
        WHERE 
            `tabSales Invoice`.customer = %(customer)s 
            AND `tabCredit Details`.sales_invoice = %(sales_invoice)s 
            AND `tabCredit Details`.item = %(item)s
            AND `tabSales Invoice`.docstatus = 1
            AND `tabSales Invoice`.status != 'Cancelled'
        GROUP BY 
            `tabCredit Details`.sales_invoice, `tabSales Invoice`.customer
    """, values=values, as_dict=True)

    if not total_returned:
        return {'total_returned_qty': 0}
    
    return total_returned[0]


@frappe.whitelist()
def get_valid_sales_invoices(doctype, txt, searchfield, start, page_len, filters=None):
    filters = filters or {}

    customer = filters.get("customer")
    shipping_address = filters.get("shipping_address")
    item_code = filters.get("item_code")
    start_date = filters.get("start_date")

    if not customer or not item_code or not start_date:
        return []

    # Build dynamic conditions
    conditions = ["si.docstatus = 1", "si.is_return = 0"]
    query_params = {
        "txt": f"%{txt}%",
        "start": start,
        "page_len": page_len,
    }

    if customer:
        conditions.append("si.customer = %(customer)s")
        query_params["customer"] = customer

    if shipping_address:
        conditions.append("si.shipping_address_name = %(shipping_address)s")
        query_params["shipping_address"] = shipping_address

    if item_code:
        conditions.append("sii.item_code = %(item_code)s")
        query_params["item_code"] = item_code

    if start_date:
        conditions.append("si.posting_date >= %(start_date)s")
        query_params["start_date"] = start_date

    # Add logic for returned quantities dynamically in SQL
    conditions.append("""
        (sii.qty + COALESCE((
            SELECT SUM(cd.qtr)
            FROM `tabCredit Details` cd
            JOIN `tabSales Invoice` rsi ON cd.parent = rsi.name
            WHERE cd.sales_invoice = si.name
            AND cd.item = sii.item_code
            AND rsi.customer = si.customer
            AND rsi.docstatus = 1
            AND rsi.status != 'Cancelled'
        ), 0)) > 0
    """)

    # Construct query
    where_clause = " AND ".join(conditions)
    query = f"""
        SELECT DISTINCT si.name,si.posting_date,sii.qty
        FROM `tabSales Invoice` si
        JOIN `tabSales Invoice Item` sii ON si.name = sii.parent
        WHERE {where_clause}
        AND si.name LIKE %(txt)s
        LIMIT %(start)s, %(page_len)s
    """

    return frappe.db.sql(query, query_params)