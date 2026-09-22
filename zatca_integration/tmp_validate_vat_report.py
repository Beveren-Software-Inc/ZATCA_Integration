"""TEMPORARY verification for the Zatca VAT Report fix - deleted after use.

Inserts a tiny synthetic dataset (raw SQL, inside a transaction), runs the
report's execute(), checks the numbers, then rolls everything back.
"""

import frappe

TEMPLATE = "_ZATCA VAT REPORT TEST TEMPLATE"
REPORT_PATH = (
    "zatca_integration.saudi_arabia_electronic_invoicing.report."
    "zatca_vat_report.zatca_vat_report"
)


def _insert_invoice(name, base_total, taxes, is_return, template):
    frappe.db.sql(
        """
        INSERT INTO `tabSales Invoice`
            (name, owner, creation, modified, modified_by, docstatus, is_return,
             base_total, base_total_taxes_and_charges, base_grand_total, taxes_and_charges)
        VALUES (%s, 'Administrator', NOW(), NOW(), 'Administrator', 1, %s, %s, %s, %s, %s)
        """,
        (name, is_return, base_total, taxes, base_total + taxes, template),
    )


def run():
    execute = frappe.get_attr(REPORT_PATH + ".execute")
    get_invoice_fields = frappe.get_attr(REPORT_PATH + ".get_invoice_fields")

    # 1. the SQL Frappe generates for our field/group_by definition
    frappe.db.sql(
        """
        INSERT INTO `tabSales Taxes and Charges Template`
            (name, owner, creation, modified, modified_by, docstatus, company, custom_tax_type)
        VALUES (%s, 'Administrator', NOW(), NOW(), 'Administrator', 1, %s, 'Standard Rate')
        """,
        (TEMPLATE, frappe.defaults.get_global_default("company") or "Test Company"),
    )
    _insert_invoice("_ZATCA-TEST-SI-1", 1000, 150, 0, TEMPLATE)
    _insert_invoice("_ZATCA-TEST-SI-2", 400, 60, 1, TEMPLATE)

    rows = frappe.get_all(
        "Sales Invoice",
        fields=get_invoice_fields(),
        group_by="custom_tax_type, is_return",
        ignore_permissions=True,
    )
    print("aggregated rows:", rows)

    columns, data = execute({})
    print("report rows:")
    for row in data:
        print("  ", row)

    standard_rate = [row for row in data if row["title"] == "Standard Rate"][0]
    assert standard_rate["sales_collected"] == 1000, standard_rate
    assert standard_rate["sales_credited"] == 400, standard_rate
    assert standard_rate["sales_total"] == 1400, standard_rate
    assert standard_rate["vat_collected"] == 150, standard_rate
    assert standard_rate["vat_credited"] == 60, standard_rate
    assert standard_rate["vat_total"] == 210, standard_rate
    print("Standard Rate row matches expected sums")

    frappe.db.rollback()
    print(
        "rolled back; test invoices still present:",
        frappe.db.exists("Sales Invoice", "_ZATCA-TEST-SI-1"),
    )
    return "VAT REPORT CHECK DONE"
