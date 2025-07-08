import frappe
from zatca_integration.saudi_arabia_electronic_invoicing.utils import get_api_url
from zatca_integration.clearence_util import generate_einvoice

from frappe.utils import now_datetime, add_to_date

def is_zatca_compliance_ready(company_name):
    """
    Validate if a company is ZATCA-ready and return the compliance CSID doc.
    """
    production_csid = frappe.db.get_value("Company", company_name, "custom_production_csid")
    if not production_csid:
        return None, "Company not registered for ZATCA e-invoicing"

    production_doc = frappe.get_doc("Production CSID", production_csid)
    if not production_doc or not production_doc.compliance_csid:
        return None, "Compliance CSID not found for Production CSID"

    compliance_doc = frappe.get_doc("Compliance CSID", production_doc.compliance_csid)
    if not compliance_doc.binary_security_token:
        return None, "Binary security token missing for compliance CSID"

    return compliance_doc, None


def send_multiple_signed_compliance_invoices_to_zatca():
    """
    Automatically send all signed B2C invoices (not yet reported) to ZATCA compliance API.
    """
    results = []

    companies = frappe.get_all(
        "Company",
        filters={"custom_enable_zatca_e_invoicing": 1},
        fields=["name"]
    )

    for company in companies:
        is_zatca_compliance_ready(company.name)
        # Only include invoices posted in the last 24 hours
        cutoff_time = add_to_date(now_datetime(), hours=-24)

        invoices = frappe.get_all(
            "Sales Invoice",
            filters={
                "company": company.name,
                "custom_zatca_submit_status": ["not in", ["REPORTED", "CLEARED"]],
                "docstatus": 1,
                "posting_date": [">=", cutoff_time.date()],
            },
            fields=["name"]
        )

        for invoice_data in invoices:
            try:
                invoice = frappe.get_doc("Sales Invoice", invoice_data.name)
                generate_einvoice(invoice)
            except Exception as e:
                frappe.log_error(f"Error generating einvoice for {invoice_data.name}: {str(e)}")
                continue

    return results
