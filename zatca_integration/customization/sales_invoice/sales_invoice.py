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
