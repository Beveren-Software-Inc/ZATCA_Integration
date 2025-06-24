import frappe
import json
import requests
from zatca_integration.saudi_arabia_electronic_invoicing.sign_invoice_util import xml_base64_decode, get_prod_csid
from zatca_integration.saudi_arabia_electronic_invoicing.utils import get_api_url

from frappe.utils import now_datetime, get_datetime, add_to_date

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


def send_signed_compliance_invoice_to_zatca(uuid1, encoded_hash, signed_xmlfile_name, invoice, compliance_csid_doc):
    """
    Send a single signed invoice to ZATCA Compliance API.
    """
    url = get_api_url(get_prod_csid(invoice))
    try:
        payload = json.dumps({
            "invoiceHash": encoded_hash,
            "uuid": uuid1,
            "invoice": xml_base64_decode(signed_xmlfile_name),
        })

        headers = {
            "accept": "application/json",
            "Accept-Language": "en",
            "Accept-Version": "V2",
            "Authorization": "Basic " + compliance_csid_doc.binary_security_token,
            "Content-Type": "application/json",
        }

        response = requests.post(
            url=url,
            headers=headers,
            data=payload,
            timeout=300,
        )

        if response.status_code == 202:
            return response.json()
        else:
            frappe.throw(_(f"ZATCA Compliance API Error {response.status_code}: {response.text}"))

    except requests.exceptions.RequestException as e:
        frappe.log_error(str(e), "ZATCA Request Error")
        return None
    except Exception as e:
        frappe.throw(_(f"ZATCA Compliance Error: {str(e)}"))
        return None


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
        compliance_csid_doc, error = is_zatca_compliance_ready(company.name)
        if error:
            frappe.log_error(f"{company.name} - {error}")
            continue

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
            fields=["name", "custom_invoice_uuid", "custom_invoice_hash", "custom_signed_xml_file"]
        )

        for invoice_data in invoices:
            try:
                invoice = frappe.get_doc("Sales Invoice", invoice_data.name)

                # Ensure all fields are present
                if not invoice.custom_invoice_uuid or not invoice.custom_invoice_hash or not invoice.custom_signed_xml_file:
                    frappe.log_error(f"Missing ZATCA fields in invoice {invoice.name}")
                    continue

                response = send_signed_compliance_invoice_to_zatca(
                    uuid1=invoice.custom_invoice_uuid,
                    encoded_hash=invoice.custom_invoice_hash,
                    signed_xmlfile_name=invoice.custom_signed_xml_file,
                    invoice=invoice,
                    compliance_csid_doc=compliance_csid_doc
                )

                results.append({
                    "invoice": invoice.name,
                    "status": "Success",
                    "response": response
                })

            except Exception as e:
                results.append({
                    "invoice": invoice_data.name,
                    "status": "Failed",
                    "error": str(e)
                })

    return results
