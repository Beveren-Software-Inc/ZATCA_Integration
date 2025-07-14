# Copyright (c) 2025, Shakir PM and contributors
# For license information, please see license.txt

import frappe

def execute(filters=None):
    results = frappe.db.sql("""
        SELECT custom_zatca_submit_status, COUNT(*) as total
        FROM `tabSales Invoice`
        WHERE custom_zatca_submit_status IS NOT NULL
        GROUP BY custom_zatca_submit_status
        ORDER BY custom_zatca_submit_status
    """, as_dict=True)

    columns = ["Submission Status", "Count"]
    data = [[row["custom_zatca_submit_status"], row["total"]] for row in results]

    return columns, data
