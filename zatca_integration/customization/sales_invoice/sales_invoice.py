import frappe

@frappe.whitelist()
def update_payment_mode(customer):
    if not frappe.db.exists('Customer', customer):
        frappe.throw(f"Customer with ID {customer} does not exist.")
    mode_of_payment = frappe.db.get_value('Customer', customer, 'custom_mode_of_payment')
    if mode_of_payment is None:
        frappe.msgprint(f"No mode of payment set for Customer {customer}.")
    return mode_of_payment

@frappe.whitelist()
def update_delivery_date(delivery_note):
    if not frappe.db.exists('Delivery Note', delivery_note):
        frappe.throw(f"Delivery Note with ID {delivery_note} does not exist.")
    delivery_date = frappe.db.get_value('Delivery Note', delivery_note, 'posting_date')
    if delivery_date is None:
        frappe.msgprint(f"No posting date set for Delivery Note {delivery_note}.")
    return delivery_date
