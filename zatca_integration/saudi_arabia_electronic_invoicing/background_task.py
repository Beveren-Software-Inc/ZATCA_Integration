import frappe
from zatca_integration.saudi_arabia_electronic_invoicing.utils import get_or_create_scheduled_job, delete_scheduled_job
from zatca_integration.clearence_util import generate_einvoice, bg_generate_einvoice

from frappe.utils import now_datetime, add_to_date, add_days

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
                bg_generate_einvoice(invoice)
            except Exception as e:
                frappe.log_error(f"Error generating einvoice for {invoice_data.name}: {str(e)}")
                continue

    return results


# Notify user on the expiry of the production csid
def notify_expiring_csids():
    today = now_datetime()
    expiry_threshold = add_days(today, 7)

    expiring_csids = frappe.get_all(
        "Production CSID", 
        filters={"docstatus": ["!=", 2]},
        fields=["name", "created_time"]
    )

    for csid in expiring_csids:
        renewal_date = csid.created_time
        expiry_date = add_days(renewal_date, 365)

        if expiry_date <= expiry_threshold:
            send_csid_expiry_email(csid.name, expiry_date)

def send_csid_expiry_email(csid_name, expiry_date):
    subject = "ZATCA CSID Expiring Soon"
    message = f"""
        <p><b>Compliance CSID:</b> {csid_name}</p>
        <p><b>Expiry Date:</b> {expiry_date.strftime('%d-%m-%Y')}</p>
        <p>Please renew your ZATCA Production CSID before it expires to ensure uninterrupted compliance.</p>
    """

    recipients = get_emails_for_roles(["System Manager", "Sales User"])

    if recipients:
        frappe.sendmail(
            recipients=recipients,
            subject=subject,
            message=message
        )

def get_emails_for_roles(roles):
    emails = set()
    for role in roles:
        users = frappe.get_all("Has Role", filters={"role": role}, fields=["parent"])
        for user in users:
            user_email = frappe.db.get_value("User", user.parent, "email")
            if user_email:
                emails.add(user_email)
    return list(emails)


def prod_csid_auto_renew():
    companies = frappe.get_all("Company", filters={"custom_enable_zatca_e_invoicing":1}, fields=["name"])
    
    results = []
    for company in companies:
        try:
            company_doc = frappe.get_doc("Company", company.name)
            prod_csid = frappe.get_doc("Production CSID", company_doc.custom_production_csid)
            result = prod_csid.renew_zatca_production_csid()
            results.append((company.name, "Success", result))
        except Exception as e:
            results.append((company.name, "Failed", str(e)))

    return results


def on_update(doc, method=None):
    on_update_create_schedulers(doc)
    

def on_update_create_schedulers(doc):
    schedulers = [
        {
            "enabled_field": "custom_b2c_auto_sales_submission_enabled",
            "method": send_multiple_signed_compliance_invoices_to_zatca,
            "frequency_field": "custom_sales_information_submission_frequency",
            "cron_field": "custom_sales_info_cron_format"
        },
        {
            "enabled_field": "custom_allow_auto_renewal_production_csid",
            "method": prod_csid_auto_renew,
            "frequency_field": "custom_auto_renewal_frequency",
            "cron_field": "custom_production_csid_cron_format"
        }
    ]

    old_doc = doc.get_doc_before_save()

    for scheduler in schedulers:
        enabled_now = getattr(doc, scheduler["enabled_field"], False)
        enabled_before = getattr(old_doc, scheduler["enabled_field"], False) if old_doc else False

        job_name = f"{scheduler['method'].__module__}.{scheduler['method'].__name__}"

        if enabled_now:
            frequency = getattr(doc, scheduler["frequency_field"], None)
            cron_format = getattr(doc, scheduler["cron_field"], None) if frequency == "Cron" else None

            get_or_create_scheduled_job(
                job_name,
                frequency,
                cron_format
            )
        elif enabled_before and not enabled_now:
            # Previously enabled but now disabled — delete job
            delete_scheduled_job(job_name)