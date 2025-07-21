
import frappe
from frappe.utils import now
from frappe.utils import nowdate, add_to_date
import frappe
from frappe.utils import flt

import frappe
from frappe.utils import now
from frappe.utils import nowdate, add_to_date


@frappe.whitelist()
def create_test_sales_invoice(csr):
	
	if frappe.db.exists("Sales Invoice", "TEST-SINV-2025-00281"):
		frappe.throw("Sales Invoice ACC-SINV-2025-00212 already exists.")
		
	item = {
		"item_code": "Test Item 1",
		"item_name": "Test Item 1",
		"description": "Barcode, Self-Adhesive, 3in Wide x 1in Height x 2mm Thick, White, Polyethylene, Roll of 2000, For Intermec Easy Coder PM4iLABEL:Barcode,Self-Adh,3in Wx1in Hx2mm",
		"item_group": "All Item Groups",
		"brand": "Others",
		"qty": 16,
		"uom": "Each",
		"rate": 375,
		"amount": 6000,
		"net_rate": 375,
		"net_amount": 6000,
		"income_account": "6100001 - Trade Sales - STCL",
		"expense_account": "7200008 - Goods Purchases - STCL",
		"warehouse": "Cab1-Down",
	}
	
	create_item_if_missing(item)
	csr_data = get_csr_data(csr)
	
	today = nowdate()
	tomorrow = add_to_date(today, days=1)
	customer_name = "TEST-1 Customer"        
	
	if not frappe.db.exists("Customer", customer_name):
		customer = frappe.get_doc({
			"doctype": "Customer",
			"customer_name": customer_name,
			"customer_group": "All Customer Groups",
			"territory": "Saudi Arabia",
			"custom_country": "Saudi Arabia",
			# "payment_terms":payment_template,
			"customer_name_short": "S-CHEM",
			"customer_name_in_arabic":"العميل رقم 1",
			"disabled": 0,
			"tax_id": "300450349600003",
			"custom_vat_number": "300450349600003",
		}).insert(ignore_permissions=True)        
		create_customer_address(customer.name)
	
	invoice = frappe.get_doc({
		"doctype": "Sales Invoice",
		"name": "TEST-SINV-2025-00212",
		"customer": customer ,
		"customer_name": customer_name,
		"custom_customer_short_name": "S-CHEM",
		"tax_id": "300450349600003",
		"company": "Space Top Co. Ltd",
		"company_tax_id": csr_data.csrorganizationidentifier,
		"custom_delivery_date": tomorrow,
		"custom_payment_means": "Bank Payment",
		"posting_date": today,
		"posting_time": "11:25:04",
		"due_date": tomorrow,
		"is_pos": 0,
		"currency": "SAR",
		"conversion_rate": 1,
		"selling_price_list": "Standard Selling",
		"price_list_currency": "SAR",
		"update_stock": 0,
		"total_qty": 16,
		"base_total": 6000,
		"base_net_total": 6000,
		"total": 6000,
		"net_total": 6000,
		"taxes_and_charges": "KSA VAT 15% - STCL",
		"base_total_taxes_and_charges": 900,
		"total_taxes_and_charges": 900,
		"base_grand_total": 6900,
		"grand_total": 6900,
		"in_words": "SAR Six Thousand, Nine Hundred only.",
		"base_in_words": "SAR Six Thousand, Nine Hundred only.",
		"outstanding_amount": 6900,
		"apply_discount_on": "Grand Total",
		"po_date": "2025-03-09",
		"party_account_currency": "SAR",
		# "against_income_account": "6100001 - Trade Sales - STCL",
		"amount_eligible_for_commission": 6000,
		# "letter_head": "SpaceTop - M",
		"status": "Unpaid",
		"customer_group": "All Customer Groups",
		"tc_name":"NET 60",
		"payment_terms_template": "Bank Advice",

		"items": [
			{
				"item_code":item["item_code"],
				"item_name": item["item_name"],
				"description": "Barcode, Self-Adhesive, 3in Wide x 1in Height x 2mm Thick, White, Polyethylene, Roll of 2000, For Intermec Easy Coder PM4iLABEL:Barcode,Self-Adh,3in Wx1in Hx2mm",
				"item_group": "All Item Groups",
				"brand": "Others",
				"qty": 16,
				"uom": "Each",
				"rate": 375,
				"amount": 6000,
				"net_rate": 375,
				"net_amount": 6000,
				"income_account": "6100001 - Trade Sales - STCL",
				"expense_account": "7200008 - Goods Purchases - STCL",
				"warehouse": "Cab1-Down",
				
			}
		],

		"taxes": [
			{
				"charge_type": "On Net Total",
				"account_head": "300001 - VAT on Sales - 15% - STCL",
				"description": "VAT Taxable",
				"rate": 15,
				"tax_amount": 900,
				"base_tax_amount": 900,
			}
		],

		"payment_schedule": [
			{
				"due_date": tomorrow,
				"invoice_portion": 100,
				"payment_amount": 6900,
				"base_payment_amount": 6900
			}
		]
	})
	
	invoice.autoname = None
	invoice.name = "TEST-SINV-2025-000281"
	invoice.set_new_name = lambda **kwargs: "TEST-INV-001"

	invoice.insert(ignore_permissions=True)
	frappe.db.commit()
	invoice.submit()
	frappe.msgprint("Sales Invoice ACC-SINV-2025-00212 created and submitted successfully.")

def get_csr_data(csr):
	csr_data = frappe.get_doc("Zatca CSR Settings", csr)
	return csr_data


def create_item_if_missing(item_data):
	if not frappe.db.exists("Item", item_data["item_code"]):
		frappe.get_doc({
			"doctype": "Item",
			"item_code": item_data["item_code"],
			"item_name": item_data["item_name"],
			"description": item_data["description"],
			"item_group": item_data.get("item_group", "All Item Groups"),
			"brand": item_data.get("brand", "Others"),
			"stock_uom": item_data.get("uom", "Each"),
			"is_stock_item": 1,
			"disabled": 0,
		}).insert(ignore_permissions=True)
		frappe.db.commit()
		
def create_customer_address(customer_name):
	existing_addresses = frappe.db.sql("""
		SELECT addr.name
		FROM `tabAddress` AS addr
		INNER JOIN `tabDynamic Link` AS dl ON dl.parent = addr.name
		WHERE dl.link_doctype = 'Customer'
		  AND dl.link_name = %s
		  AND dl.parenttype = 'Address'
	""", (customer_name,), as_dict=True)

	if existing_addresses:
		return existing_addresses[0]["name"]


	address = frappe.get_doc({
		"doctype": "Address",
		"address_title": customer_name,
		"address_type": "Billing",
		"address_line1": "Test Street 123",
		"address_line2": "1267",
		"county": "Jazan",
		"city": "Riyadh",
		"state": "Riyadh",
		"pincode": "11411",
		"country": "Saudi Arabia",
		"links": [{
			"link_doctype": "Customer",
			"link_name": customer_name
		}]
	})
	address.insert(ignore_permissions=True)
	frappe.db.set_value("Customer", customer_name, "customer_primary_address", address.name)
