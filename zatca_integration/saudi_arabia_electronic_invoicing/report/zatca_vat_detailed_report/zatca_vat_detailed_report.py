# Copyright (c) 2024, Beveren Software Inc and contributors
# For license information, please see license.txt
import json

import frappe
from frappe import _
from frappe.utils import get_url_to_list


def execute(filters=None):
	columns = columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{
			"fieldname": "title",
			"label": _("Title"),
			"fieldtype": "Data",
			"width": 300,
		},
		{
			"fieldname": "custom_tax_type",
			"label": _("Tax Type"),
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"fieldname": "collected_amount",
			"label": _("Sales/Purchases Collected (SAR)"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 200,
		},
		{
			"fieldname": "credited_amount",
			"label": _("Sales/Purchases Credited (SAR)"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 200,
		},
		{
			"fieldname": "total_amount",
			"label": _("Total Sales/Purchases (SAR)"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		},
		{
			"fieldname": "vat_collected",
			"label": _("VAT Collected (SAR)"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		},
		{
			"fieldname": "vat_credited",
			"label": _("VAT Credited (SAR)"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		},
		{
			"fieldname": "total_vat",
			"label": _("Total VAT (SAR)"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		},
		{
			"fieldname": "currency",
			"label": _("Currency"),
			"fieldtype": "Currency",
			"width": 150,
			"hidden": 1,
		},
	]


def get_data(filters):
	data = []
	# Get Company and Currency
	company = filters.get("company")
	company_currency = frappe.get_cached_value("Company", company, "default_currency")

	# Sales Heading
	append_data(data, "Sales", "", "", "", "", "", "", "", company_currency)

	total_collected = 0
	total_credited = 0
	grand_total = 0
	total_vat_collected = 0
	total_vat_credited = 0
	grand_total_vat = 0
	
	sales_data = fetch_and_aggregate_data(company, "tabSales Invoice", filters)

	for row in sales_data:
		data.append({
			"title": _(row.tax_reason) if row.tax_reason else None,
			"custom_tax_type": row.custom_tax_type,
			"collected_amount": row.collected_amount,
			"credited_amount": row.credited_amount,
			"total_amount": row.total_base_total,
			"vat_collected": row.vat_collected,
			"vat_credited": row.vat_credited,
			"total_vat": row.total_taxes_and_charges,
			"currency": company_currency
		})

		total_collected += row.collected_amount
		total_credited += row.credited_amount
		grand_total += row.total_base_total
		total_vat_collected += row.vat_collected
		total_vat_credited += row.vat_credited
		grand_total_vat += row.total_taxes_and_charges
	
	
	# Sales Grand Total
	append_data(
		data,
		"Grand Total",
		"",
		total_collected,
		total_credited,
		grand_total,
		total_vat_collected,
		total_vat_credited,
		grand_total_vat,
		company_currency
	)

	# Blank Line
	append_data(data, "", "", "", "", "", "", "", "", company_currency)

	# # Purchase Heading
	append_data(data, "Purchases", "", "", "", "", "", "", "", company_currency)

	total_collected = 0
	total_credited = 0
	grand_total = 0
	total_vat_collected = 0
	total_vat_credited = 0
	grand_total_vat = 0

	purchase_data = fetch_and_aggregate_data(company, "tabPurchase Invoice", filters)
	for row in purchase_data:
		data.append({
			"title": _(row.tax_reason) if row.tax_reason else None,
			"custom_tax_type": row.custom_tax_type,
			"collected_amount": row.collected_amount,
			"credited_amount": row.credited_amount,
			"total_amount": row.total_base_total,
			"vat_collected": row.vat_collected,
			"vat_credited": row.vat_credited,
			"total_vat": row.total_taxes_and_charges,
			"currency": company_currency
		})

		total_collected += row.collected_amount
		total_credited += row.credited_amount
		grand_total += row.total_base_total
		total_vat_collected += row.vat_collected
		total_vat_credited += row.vat_credited
		grand_total_vat += row.total_taxes_and_charges
	

	# Purchase Grand Total
	append_data(
		data,
		"Grand Total",
		"",
		total_collected,
		total_credited,
		grand_total,
		total_vat_collected,
		total_vat_credited,
		grand_total_vat,
		company_currency
	)

	return data


def append_data(data, title, tax_type, collected_amount, credited_amount, total_amount, vat_collected, vat_credited, total_vat, company_currency):
	"""Returns data with appended value."""
	data.append(
		{
			"title": title,
			"custom_tax_type": tax_type,
			"collected_amount": collected_amount,
			"credited_amount": credited_amount,
			"total_amount": total_amount,
			"vat_collected": vat_collected,
			"vat_credited": vat_credited,
			"total_vat": total_vat,
			"currency": company_currency
		}
	)

def fetch_and_aggregate_data(company, doctype_table, filters):
    from_date = filters['from_date']  # Assuming filters is a dict
    to_date = filters['to_date']
    
    # Validate or ensure doctype_table is safe to use
    allowed_tables = ['tabSales Invoice', 'tabPurchase Invoice']
    if doctype_table not in allowed_tables:
        frappe.throw(_("Invalid Database Table Name!"))
    
    # Safe to format the table name here since it's controlled or validated
    sql_query = f'''
        SELECT
			stct.custom_tax_type,
			CASE
				WHEN stct.custom_tax_type = 'Zero Rate' THEN stct.custom_zero_rate_reason
				WHEN stct.custom_tax_type = 'Except Rate' THEN stct.custom_except_rate_reason
				ELSE 'Standard Tax'
			END as tax_reason,
			SUM(si.grand_total) as total_grand_total,
			SUM(si.total_taxes_and_charges) as total_taxes_and_charges,
			SUM(si.base_total) as total_base_total,
			SUM(CASE WHEN si.is_return = 0 THEN si.base_total ELSE 0 END) as collected_amount,
			SUM(CASE WHEN si.is_return = 0 THEN si.total_taxes_and_charges ELSE 0 END) as vat_collected,
			SUM(CASE WHEN si.is_return = 1 THEN si.base_total ELSE 0 END) as credited_amount,
			SUM(CASE WHEN si.is_return = 1 THEN si.total_taxes_and_charges ELSE 0 END) as vat_credited
		FROM
			`{doctype_table}` si
		LEFT JOIN
			`tabSales Taxes and Charges Template` stct ON stct.name = si.taxes_and_charges
		WHERE
			si.docstatus = 1 AND
			si.company = %(company)s AND
			stct.company = %(company)s AND
			si.posting_date BETWEEN %(from_date)s AND %(to_date)s
		GROUP BY
			stct.custom_tax_type, tax_reason
		ORDER BY
			stct.custom_tax_type, tax_reason
    '''
    
    fetched_data = frappe.db.sql(sql_query, {
        'company': company, 
        'from_date': from_date, 
        'to_date': to_date
    }, as_dict=1)

    return fetched_data

	