# Copyright (c) 2025, Shakir PM and contributors
# For license information, please see license.txt

# import frappe


import frappe
from frappe.utils import now_datetime, add_days

def execute(filters=None):
    # Define status groups
    status_groups = {
        "REPORTED": ["REPORTED"],
        "CLEARED": ["CLEARED"],
        "FAILED": ["NOT CLEARED", "NOT REPORTED"],
        "DRAFT": ["DRAFT", "PENDING"],
    }

    # Initialize counters
    counters = {
        "REPORTED": 0,
        "CLEARED": 0,
        "FAILED": 0,
        "DRAFT": 0,
        "TOTAL": 0,
    }

    # Date range: last 30 days from today
    start_date = add_days(now_datetime(), -30)

    # Query Sales Invoices from the last 30 days
    results = frappe.db.sql("""
        SELECT custom_zatca_submit_status, COUNT(*) AS total
        FROM `tabSales Invoice`
        WHERE custom_zatca_submit_status IS NOT NULL
          AND posting_date >= %s
        GROUP BY custom_zatca_submit_status
    """, (start_date,), as_dict=True)

    for row in results:
        status = row["custom_zatca_submit_status"]
        count = row["total"]

        for group, valid_statuses in status_groups.items():
            if status in valid_statuses:
                counters[group] += count
                counters["TOTAL"] += count
                break

    # Define report columns
    columns = [
        {"fieldname": "doctype", "label": "Document Type", "fieldtype": "Data", "width": 200},
        {"fieldname": "reported", "label": "REPORTED", "fieldtype": "Int", "width": 100},
        {"fieldname": "cleared", "label": "CLEARED", "fieldtype": "Int", "width": 100},
        {"fieldname": "failed", "label": "FAILED", "fieldtype": "Int", "width": 100},
        {"fieldname": "draft", "label": "DRAFT", "fieldtype": "Int", "width": 100},
        {"fieldname": "total", "label": "TOTAL", "fieldtype": "Int", "width": 100},
    ]

    # One row: Sales Invoice summary
    data = [{
        "doctype": "Sales Invoice",
        "reported": counters["REPORTED"],
        "cleared": counters["CLEARED"],
        "failed": counters["FAILED"],
        "draft": counters["DRAFT"],
        "total": counters["TOTAL"],
    }]

    return columns, data
