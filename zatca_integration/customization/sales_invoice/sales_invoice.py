import frappe

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
