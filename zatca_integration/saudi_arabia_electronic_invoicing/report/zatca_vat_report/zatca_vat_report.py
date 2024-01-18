# Copyright (c) 2024, Shakir PM and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):

	columns = get_columns()
	data = []

	# Sales Invoices Sales and VAT
	append_heading("Sales Invoices and VAT", data)
	sales_invoices = frappe.get_all('Sales Invoice', 
							fields=["SUM(base_total) AS base_total", 
									"SUM(base_total_taxes_and_charges) AS base_total_taxes_and_charges", 
									"SUM(base_grand_total) AS base_grand_total", 
									"is_return", 
									'taxes_and_charges.custom_tax_type'], 
							group_by='custom_tax_type, is_return')
		
	standard_rate = [invoice for invoice in sales_invoices if invoice['custom_tax_type'] == 'Standard Rate' and invoice['is_return'] == 0]
	standard_rate_sum = get_tax_sum(standard_rate)
	standard_rate_adjustment = [invoice for invoice in sales_invoices if invoice['custom_tax_type'] == 'Standard Rate' and invoice['is_return'] == 1]
	standard_rate_adjustment_sum = get_tax_sum(standard_rate_adjustment)
	append_data("Standard Rate", data, standard_rate_sum, standard_rate_adjustment_sum)

	except_rate = [invoice for invoice in sales_invoices if invoice['custom_tax_type'] == 'Except Rate' and invoice['is_return'] == 0]
	except_rate_sum = get_tax_sum(except_rate)
	except_rate_adjustment = [invoice for invoice in sales_invoices if invoice['custom_tax_type'] == 'Except Rate' and invoice['is_return'] == 1]
	except_rate_adjustment_sum = get_tax_sum(except_rate_adjustment)
	append_data("Except Rate", data, except_rate_sum, except_rate_adjustment_sum)

	zero_rate = [invoice for invoice in sales_invoices if invoice['custom_tax_type'] == 'Zero Rate' and invoice['is_return'] == 0]
	zero_rate_sum = get_tax_sum(zero_rate)
	zero_rate_adjustment = [invoice for invoice in sales_invoices if invoice['custom_tax_type'] == 'Zero Rate' and invoice['is_return'] == 1]
	zero_rate_adjustment_sum = get_tax_sum(zero_rate_adjustment)
	append_data("Zero Rate", data, zero_rate_sum, zero_rate_adjustment_sum)

	# Purchase Invoices Sales and VAT
	append_heading(" ", data)
	append_heading("Purchase Invoices and VAT", data)
	purchase_invoices = frappe.get_all('Purchase Invoice', 
							fields=["SUM(base_total) AS base_total", 
									"SUM(base_total_taxes_and_charges) AS base_total_taxes_and_charges", 
									"SUM(base_grand_total) AS base_grand_total", 
									"is_return", 
									'taxes_and_charges.custom_tax_type'], 
							group_by='custom_tax_type, is_return')
	
	standard_rate = [invoice for invoice in purchase_invoices if invoice['custom_tax_type'] == 'Standard Rate' and invoice['is_return'] == 0]
	standard_rate_sum = get_tax_sum(standard_rate)
	standard_rate_adjustment = [invoice for invoice in purchase_invoices if invoice['custom_tax_type'] == 'Standard Rate' and invoice['is_return'] == 1]
	standard_rate_adjustment_sum = get_tax_sum(standard_rate_adjustment)
	append_data("Standard Rate", data, standard_rate_sum, standard_rate_adjustment_sum)

	except_rate = [invoice for invoice in purchase_invoices if invoice['custom_tax_type'] == 'Except Rate' and invoice['is_return'] == 0]
	except_rate_sum = get_tax_sum(except_rate)
	except_rate_adjustment = [invoice for invoice in purchase_invoices if invoice['custom_tax_type'] == 'Except Rate' and invoice['is_return'] == 1]
	except_rate_adjustment_sum = get_tax_sum(except_rate_adjustment)
	append_data("Except Rate", data, except_rate_sum, except_rate_adjustment_sum)

	zero_rate = [invoice for invoice in purchase_invoices if invoice['custom_tax_type'] == 'Zero Rate' and invoice['is_return'] == 0]
	zero_rate_sum = get_tax_sum(zero_rate)
	zero_rate_adjustment = [invoice for invoice in purchase_invoices if invoice['custom_tax_type'] == 'Zero Rate' and invoice['is_return'] == 1]
	zero_rate_adjustment_sum = get_tax_sum(zero_rate_adjustment)
	append_data("Zero Rate", data, zero_rate_sum, zero_rate_adjustment_sum)

	return columns, data

def get_tax_sum(input):
	return  {
		"base_total_sum": sum(invoice["base_total"] for invoice in input),
		"base_total_taxes_and_charges_sum": sum(invoice["base_total_taxes_and_charges"] for invoice in input),
		"base_grand_total_sum": sum(invoice["base_grand_total"] for invoice in input)
	}

def append_data(title, data, sales_sum, crdit_sum):
	data.append(
		{
			"title": title,
			"sales_collected": sales_sum['base_total_sum'], 
			"sales_credited": crdit_sum['base_total_sum'], 
			"sales_total": sales_sum['base_total_sum'] + crdit_sum['base_total_sum'],
			"vat_collected": sales_sum['base_total_taxes_and_charges_sum'], 
			"vat_credited": crdit_sum['base_total_taxes_and_charges_sum'],
			"vat_total": sales_sum['base_total_taxes_and_charges_sum'] + crdit_sum['base_total_taxes_and_charges_sum']
		}
	)

def append_heading(title, data):
	data.append(
		{
			"title": title,
			"sales_collected": "", 
			"sales_credited": "", 
			"sales_total": "",
			"vat_collected": "", 
			"vat_credited": "",
			"vat_total": ""
		}
	)

def get_columns():
	return [
		{
			"fieldname": "title",
			"label": ("Title"),
			"fieldtype": "Data",
			"width": 200
		},
		{
			"fieldname": "sales_collected",
			"label": ("Sales Collected (SAR)"),
			"fieldtype": "Currency",
		},
		{
			"fieldname": "sales_credited",
			"label": ("Sales Credited (SAR)"),
			"fieldtype": "Currency",
		},
		{
			"fieldname": "sales_total",
			"label": ("Total Sales (SAR)"),
			"fieldtype": "Currency",
		},
		{
			"fieldname": "vat_collected",
			"label": ("VAT Collected (SAR)"),
			"fieldtype": "Currency",
		},
		{
			"fieldname": "vat_credited",
			"label": ("VAT Credited (SAR)"),
			"fieldtype": "Currency",
		},
		{
			"fieldname": "vat_total",
			"label": ("Total VAT (SAR)"),
			"fieldtype": "Currency",
		}
	]