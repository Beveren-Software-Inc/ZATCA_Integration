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


def create_je_for_retention_amount(doc, method):
	'''
		On Submit: Create a JE for the retention amount with Reference to this Sales Invoice
		Check the Outstanding Amount for this Retention Amount in Account Receivables Report	
	'''
	doc = frappe.parse_json(doc)
	je = frappe.new_doc('Journal Entry')
	je.company = doc.company
	je.posting_date = doc.posting_date
	je.append('accounts', {
		'account': doc.custom_retention_account,
		'debit_in_account_currency': doc.custom_retention_amount,
		'credit_in_account_currency': 0,
		'party_type': 'Customer',
		'party': doc.customer
	})
	je.append('accounts', {
		'account': doc.debit_to,
		'debit_in_account_currency': 0,
		'credit_in_account_currency': doc.custom_retention_amount,
		'party_type': 'Customer',
		'party': doc.customer,
		'reference_type': doc.doctype,
		'reference_name': doc.name,
		'reference_due_date': doc.due_date
	})
	je.insert()
	je.submit()