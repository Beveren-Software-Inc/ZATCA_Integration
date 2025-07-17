import frappe

def execute(filters=None):
    # Define known statuses and custom labels
    status_label_map = {
        "DRAFT": "DRAFT",
        "CLEARED": "CLEARED",
        "NOT CLEARED": "FAILED CLEARED",
"PENDING": "PENDING",
        "REPORTED": "REPORTED",
        "NOT REPORTED": "FAILED REPORTED",
        
    }

    # Initialize counts for each status
    counters = {status: 0 for status in status_label_map}
    counters["total"] = 0

    # Fetch status counts from database
    results = frappe.db.sql("""
        SELECT custom_zatca_submit_status, COUNT(*) as total
        FROM `tabSales Invoice`
        WHERE custom_zatca_submit_status IS NOT NULL
        GROUP BY custom_zatca_submit_status
    """, as_dict=True)

    for row in results:
        status = row["custom_zatca_submit_status"]
        count = row["total"]

        if status in counters:
            counters[status] += count
            counters["total"] += count

    # Define report columns with custom labels
    columns = [
        {"fieldname": "doctype", "label": "Document Type", "fieldtype": "Data", "width": 300},
    ] + [
        {
            "fieldname": status.lower().replace(" ", "_"),
            "label": status_label_map[status],
            "fieldtype": "Int",
            "width": 150
        }
        for status in status_label_map
    ] + [
        {"fieldname": "total", "label": "Total", "fieldtype": "Int", "width": 150},
    ]

    # Format data row
    data = [{
        "doctype": "Sales Invoice",
        **{status.lower().replace(" ", "_"): counters[status] for status in status_label_map},
        "total": counters["total"],
    }]

    return columns, data
