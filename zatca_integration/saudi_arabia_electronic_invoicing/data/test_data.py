import frappe
from frappe.utils import now, nowdate, add_to_date, flt
import re
import random

# Constants
TEST_ITEM_DATA = {
    "item_code": "Test Item 1",
    "item_name": "Test Item 1", 
    "description": "Barcode, Self-Adhesive, 3in Wide x 1in Height x 2mm Thick, White, Polyethylene, Roll of 2000, For Intermec Easy Coder PM4iLABEL:Barcode,Self-Adh,3in Wx1in Hx2mm",
    "item_group": "All Item Groups",
    "qty": 16,
    "uom": "Nos",
    "rate": 375,
    "amount": 6000,
    "net_rate": 375,
    "net_amount": 6000
}

TEST_CUSTOMER_DATA = {
    "customer_name": "TEST-1 Customer",
    "customer_group": "All Customer Groups",
    # "territory": "Saudi Arabia",
    "custom_country": "Saudi Arabia",
    "customer_name_short": "S-CHEM",
    "customer_name_in_arabic": "العميل رقم 1",
    "disabled": 0
}

INVOICE_BASE_DATA = {
    "custom_delivery_date": None,
    "custom_payment_means": "Bank Payment",
    "posting_time": "11:25:04",
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
    "amount_eligible_for_commission": 6000,
    "custom_is_zatca_test": 1
}

def create_test_item(company):
    """Create and return item data with company-specific accounts"""
    item_data = TEST_ITEM_DATA.copy()
    item_data.update({
        "income_account": get_income_account(company),
        "expense_account": get_expense_account(company),
        "warehouse": create_zatca_test_warehouse(company)
    })
    
    create_item_if_missing(item_data)
    return item_data

def create_test_customer(customer_type="Individual", tax_id="300450349600003", vat_number="300450349600003"):
    """Create test customer if it doesn't exist"""
    customer_name = TEST_CUSTOMER_DATA["customer_name"]
    
    if not frappe.db.exists("Customer", customer_name):
        customer_data = TEST_CUSTOMER_DATA.copy()
        customer_data.update({
            "doctype": "Customer",
            "customer_type": customer_type,
            "tax_id": tax_id,
            "custom_vat_number": vat_number
        })
        
        customer = frappe.get_doc(customer_data).insert(ignore_permissions=True)
        create_customer_address(customer.name)
        return customer
    else:
        return frappe.get_doc("Customer", customer_name)

def create_base_invoice_data(company, csr_data, compliance_name, customer, item_data):
    """Create base invoice data structure"""
    today = nowdate()
    tomorrow = add_to_date(today, days=1)
    
    invoice_data = INVOICE_BASE_DATA.copy()
    invoice_data.update({
        "doctype": "Sales Invoice",
        "customer": customer,
        "customer_name": customer.customer_name,
        "company": company,
        "company_tax_id": csr_data.csrorganizationidentifier,
        "custom_delivery_date": today,
        "posting_date": today,
        "due_date": tomorrow,
        "taxes_and_charges": get_tax_template_with_15_percent(company),
        "cost_center": get_cost_center(company),
        "custom_compliance": compliance_name,
        "items": [create_invoice_item(item_data)],
        "taxes": get_15_percent_tax_row(get_tax_template_with_15_percent(company)),
        "payment_schedule": [{
            "due_date": tomorrow,
            "invoice_portion": 100,
            "payment_amount": 6900,
            "base_payment_amount": 6900
        }]
    })
    
    if field_exists("Sales Invoice", "naming_series"):
        invoice_data["naming_series"] = "ACC-SINV-.YYYY.-"
    if field_exists("Sales Invoice", "reference_no"):
        invoice_data["reference_no"] = random_number_upto_10m()
    
    
    return invoice_data

def random_number_upto_10m():
    return random.randint(0, 10_000_000)

#Check if teh fields exist, if not then go jump
def field_exists(doctype, fieldname):
    meta = frappe.get_meta(doctype)
    return any(df.fieldname == fieldname for df in meta.fields)

def create_invoice_item(item_data):
    """Create invoice item from item data"""
    return {
        "item_code": item_data["item_code"],
        "item_name": item_data["item_name"],
        "description": item_data["description"],
        "item_group": item_data["item_group"],
        "qty": item_data["qty"],
        "uom": item_data["uom"],
        "rate": item_data["rate"],
        "amount": item_data["amount"],
        "net_rate": item_data["net_rate"],
        "net_amount": item_data["net_amount"],
        "income_account": item_data["income_account"],
        "expense_account": item_data["expense_account"],
        "warehouse": item_data["warehouse"]
    }

def create_and_submit_invoice(invoice_data, invoice_name):
    """Create, configure and submit invoice"""
    invoice = frappe.get_doc(invoice_data)
    invoice.autoname = None
    invoice.name = invoice_name
    invoice.set_new_name = lambda **kwargs: "TEST-INV-001"
    
    invoice.insert(ignore_permissions=True)
    invoice.submit()
    return invoice.name

@frappe.whitelist()
def create_test_sales_invoice(csr_data, compliance_name, is_debit=0):
    """Create test sales invoice (Individual customer)"""
    company = sanitize_company_name(csr_data)
    # frappe.throw(str(csr))
    # company = csr_data.csrorganizationname
  
    
    invoice_name = "TEST-SINV-2025-200"
    if frappe.db.exists("Sales Invoice", invoice_name):
        return invoice_name
    
    # Create components
    item_data = create_test_item(company)
    customer = create_test_customer(
        customer_type="Individual",
        tax_id="300450349600004",
        vat_number="300450349600003"
    )
    
    # Create invoice data
    invoice_data = create_base_invoice_data(company, csr_data, compliance_name, customer, item_data)
    invoice_data.update({
        "name": "TEST-SINV-2025-00212",
        "po_no": "12345",
        "is_debit_note":is_debit,
    })
    
    return create_and_submit_invoice(invoice_data, invoice_name)

@frappe.whitelist()
def create_test_simplified_debit_sales_invoice(csr_data, compliance_name):
    """Create test sales invoice (Individual customer)"""
    company = sanitize_company_name(csr_data)
    # frappe.throw(str(csr))
    # company = csr_data.csrorganizationname
  
    
    invoice_name = "TEST-SINV-2025-205"
    if frappe.db.exists("Sales Invoice", invoice_name):
        return invoice_name
    
    # Create components
    item_data = create_test_item(company)
    customer = create_test_customer(
        customer_type="Individual",
        tax_id="300450349600004",
        vat_number="300450349600003"
    )
    
    # Create invoice data
    invoice_data = create_base_invoice_data(company, csr_data, compliance_name, customer, item_data)
    invoice_data.update({
        "name": "TEST-SINV-2025-00216",
        "po_no": "12345",
       
    })
    
    return create_and_submit_invoice(invoice_data, invoice_name)


@frappe.whitelist()
def create_standard_test_debit_sales_invoice(csr_data, compliance_name):
    """Create standard test sales invoice (Company customer)"""
    company = sanitize_company_name(csr_data)
    
    invoice_name = "TEST-SINV-2025-105"
    if frappe.db.exists("Sales Invoice", invoice_name):
        return invoice_name
    
    # Create components
    item_data = create_test_item(company)
    customer = create_test_customer(
        customer_type="Company",
        tax_id="300450349600003",
        vat_number="300450349600003"
    )
    
    # Create invoice data
    invoice_data = create_base_invoice_data(company, csr_data, compliance_name, customer, item_data)
    invoice_data.update({
        "name": "TEST-SINV-2025-00215",
        # "custom_customer_short_name": "S-CHEM",
        "tax_id": "300450349600003",
        "po_no": "123456",
        "is_debit_note":1,
    })
    
    return create_and_submit_invoice(invoice_data, invoice_name)

@frappe.whitelist()
def create_standard_test_sales_invoice(csr_data, compliance_name):
    """Create standard test sales invoice (Company customer)"""
    company = sanitize_company_name(csr_data)
    
    invoice_name = "TEST-SINV-2025-100"
    if frappe.db.exists("Sales Invoice", invoice_name):
        return invoice_name
    
    # Create components
    item_data = create_test_item(company)
    customer = create_test_customer(
        customer_type="Company",
        tax_id="300450349600003",
        vat_number="300450349600003"
    )
    
    # Create invoice data
    invoice_data = create_base_invoice_data(company, csr_data, compliance_name, customer, item_data)
    invoice_data.update({
        "name": "TEST-SINV-2025-00212",
        # "custom_customer_short_name": "S-CHEM",
        "tax_id": "300450349600003",
        "po_no": "123456",
        
    })
    
    return create_and_submit_invoice(invoice_data, invoice_name)

def create_return_invoice_from_original(original_invoice_name, return_invoice_name, compliance_name):
    """Generic function to create return invoice from original"""
    if not frappe.db.exists("Sales Invoice", original_invoice_name):
        frappe.throw(f"Original Sales Invoice {original_invoice_name} does not exist.")
    
    original_invoice = frappe.get_doc("Sales Invoice", original_invoice_name)
    return_invoice = frappe.copy_doc(original_invoice)
    
    # Configure return invoice
    return_invoice.name = None
    return_invoice.is_return = 1
    return_invoice.return_against = original_invoice.name
    return_invoice.posting_date = nowdate()
    return_invoice.posting_time = now()
    return_invoice.custom_is_zatca_test = 1
    return_invoice.custom_compliance = compliance_name
    return_invoice.outstanding_amount = 0
    
    # Reverse item quantities and amounts
    for item in return_invoice.items:
        item.qty = -item.qty
        item.amount = -item.amount
        item.net_amount = -item.net_amount
        item.custom_return_reason = "Expired"
    
    # Reverse taxes
    for tax in return_invoice.taxes:
        tax.tax_amount = -tax.tax_amount
        tax.base_tax_amount = -tax.base_tax_amount
    
    # Recalculate totals
    return_invoice.total = -original_invoice.total
    return_invoice.net_total = -original_invoice.net_total
    return_invoice.grand_total = -original_invoice.grand_total
    return_invoice.base_total = -original_invoice.base_total
    return_invoice.base_net_total = -original_invoice.base_net_total
    return_invoice.base_grand_total = -original_invoice.base_grand_total
    
    # Submit return invoice
    return_invoice.autoname = None
    return_invoice.name = return_invoice_name
    return_invoice.set_new_name = lambda **kwargs: "TEST-INV-001"
    return_invoice.insert(ignore_permissions=True)
    return_invoice.submit()
    
    frappe.msgprint(f"Return Invoice {return_invoice.name} created and submitted successfully.")
    return return_invoice.name

@frappe.whitelist()
def create_return_invoice(compliance_name):
    """Create return invoice for individual customer"""
    return create_return_invoice_from_original(
        "TEST-SINV-2025-200", 
        "TEST-SINV-2025-201", 
        compliance_name
    )

@frappe.whitelist()
def create_standard_return_invoice(compliance_name):
    """Create return invoice for company customer"""
    return create_return_invoice_from_original(
        "TEST-SINV-2025-100", 
        "TEST-SINV-2025-101", 
        compliance_name
    )

# Utility functions (keeping existing implementations)
def get_15_percent_tax_row(tax_template):
    template = frappe.get_doc("Sales Taxes and Charges Template", tax_template)
    
    for tax in template.taxes:
        if tax.rate == 15 and tax.charge_type == "On Net Total":
            return [{
                "charge_type": "On Net Total",
                "account_head": tax.account_head,
                "description": tax.description or "VAT Taxable",
                "rate": tax.rate,
                "tax_amount": 0,
                "base_tax_amount": 0
            }]
    
    frappe.throw(f"No 15% On Net Total tax found in template: {tax_template}")

def get_tax_template_with_15_percent(company):
    tax_templates = frappe.get_all(
        "Sales Taxes and Charges Template",
        filters={"company": company},
        fields=["name"]
    )
    
    for template in tax_templates:
        taxes = frappe.get_all(
            "Sales Taxes and Charges",
            filters={"parent": template.name},
            fields=["rate"]
        )
        for tax in taxes:
            if float(tax.rate) == 15.0:
                return template.name
    
    frappe.throw("No Taxes and Charges Template found with 15% rate.")

def sanitize_company_name(csr_data):
    company_name = csr_data.csrorganizationname

    # Clean unwanted characters
    if company_name:
        company_name = re.sub(r'[.,]', '', company_name).strip()

    # Get list of existing company names
    existing_companies = [c.name for c in frappe.get_all("Company", fields=["name"])]

    # If company_name is missing or doesn't exist in the system, use the first available one
    if not company_name or company_name not in existing_companies:
        company_name = existing_companies[0]
    return company_name
   

def create_item_if_missing(item_data):
    if not frappe.db.exists("Item", item_data["item_code"]):
        frappe.get_doc({
            "doctype": "Item",
            "item_code": item_data["item_code"],
            "item_name": item_data["item_name"],
            "description": item_data["description"],
            "item_group": item_data.get("item_group", "All Item Groups"),
            "stock_uom": item_data.get("uom", "Nos"),
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

def get_income_account(company):
    try:
        company_doc = frappe.get_doc("Company", company)
        if company_doc.default_income_account:
            return company_doc.default_income_account
        
        account = frappe.get_value("Account",
            filters={
                "company": company,
                "account_type": "Income Account",
                "is_group": 0
            },
            fieldname="name"
        )
        
        if account:
            return account
        
        frappe.throw(f"No income account found for company '{company}'")
    
    except Exception as e:
        frappe.throw(f"Error fetching income account for company '{company}': {e}")

def get_expense_account(company):
    try:
        company_doc = frappe.get_doc("Company", company)
        if company_doc.default_expense_account:
            return company_doc.default_expense_account
        
        account = frappe.get_value("Account",
            filters={
                "company": company,
                "account_type": "Expense Account",
                "is_group": 0
            },
            fieldname="name"
        )
        
        if account:
            return account
        
        frappe.throw(f"No expense account found for company '{company}'")
    
    except Exception as e:
        frappe.throw(f"Error fetching expense account for company '{company}': {e}")

def create_zatca_test_warehouse(company):
    warehouse_name = "Zatca Test Warehouse"
    company_abbr = frappe.get_value("Company", company, "abbr")
    full_name = f"{warehouse_name} - {company_abbr}"
    
    if frappe.db.exists("Warehouse", full_name):
        return full_name
    
    warehouse = frappe.get_doc({
        "doctype": "Warehouse",
        "warehouse_name": warehouse_name,
        "company": company,
        "is_group": 0,
        "disabled": 0
    }).insert(ignore_permissions=True)
    
    return warehouse.name

def get_cost_center(company):
    try:
        cost_center = frappe.get_value("Cost Center", {
            "company": company,
            "is_group": 0
        }, "name")
        
        if cost_center:
            return cost_center
        
        frappe.throw(f"No cost center found for company '{company}'.")
    
    except Exception as e:
        frappe.throw(f"Error fetching cost center for company '{company}': {e}")