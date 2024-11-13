from __future__ import unicode_literals
import json
import frappe.utils
import frappe,json
from frappe.utils import flt
from frappe.model.document import Document
from frappe.utils import add_days, nowdate
from frappe import _

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


#get "sold Qty" from sales invoice item table and "already Retrun Qty" from credit table.

@frappe.whitelist()
def get_batch(customer,sales_invoice,item):
	values = {'customer': customer,'sales_invoice': sales_invoice,'item':item}
	batch_list = frappe.db.sql("""
Select 
 `tabSales Invoice`.name,
 `tabSales Invoice`.customer,
 `tabSales Invoice Item`.qty
 from `tabSales Invoice` JOIN `tabSales Invoice Item` on `tabSales Invoice`.name = `tabSales Invoice Item`.parent
 where `tabSales Invoice`.customer = %(customer)s 
 and `tabSales Invoice`.name = %(sales_invoice)s 
 and `tabSales Invoice Item`.item_code = %(item)s
 and `tabSales Invoice`.docstatus =	1
 and  `tabSales Invoice`.status !=	"Cancelled"
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

