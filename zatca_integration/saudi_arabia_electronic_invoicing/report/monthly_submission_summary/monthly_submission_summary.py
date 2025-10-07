# Copyright (c) 2025, Shakir PM and contributors
# For license information, please see license.txt


import frappe
from frappe.utils import add_days, get_first_day, getdate, now_datetime


def execute(filters=None):
    filters = filters or {}
    timespan = filters.get("timespan", "Last 30 Days")
    start_date = get_start_date_from_timespan(timespan)

    # Define status groups
    status_groups = {
        "REPORTED": ["REPORTED"],
        "CLEARED": ["CLEARED"],
        "FAILED": ["NOT CLEARED", "NOT REPORTED"],
        "DRAFT": ["DRAFT", "PENDING"],
    }

    counters = {key: 0 for key in ["REPORTED", "CLEARED", "FAILED", "DRAFT", "TOTAL"]}

    results = frappe.db.sql(
        """
        SELECT custom_zatca_submit_status, COUNT(*) AS total
        FROM `tabSales Invoice`
        WHERE custom_zatca_submit_status IS NOT NULL
          AND creation >= %s
        GROUP BY custom_zatca_submit_status
    """,
        (start_date,),
        as_dict=True,
    )

    for row in results:
        status = row["custom_zatca_submit_status"]
        count = row["total"]
        for group, valid_statuses in status_groups.items():
            if status in valid_statuses:
                counters[group] += count
                counters["TOTAL"] += count
                break

    columns = [
        {"fieldname": "doctype", "label": "Document Type", "fieldtype": "Data", "width": 200},
        {"fieldname": "reported", "label": "REPORTED", "fieldtype": "Int", "width": 100},
        {"fieldname": "cleared", "label": "CLEARED", "fieldtype": "Int", "width": 100},
        {"fieldname": "failed", "label": "FAILED", "fieldtype": "Int", "width": 100},
        {"fieldname": "draft", "label": "DRAFT", "fieldtype": "Int", "width": 100},
        {"fieldname": "total", "label": "TOTAL", "fieldtype": "Int", "width": 100},
    ]

    data = [
        {
            "doctype": "Sales Invoice",
            "reported": counters["REPORTED"],
            "cleared": counters["CLEARED"],
            "failed": counters["FAILED"],
            "draft": counters["DRAFT"],
            "total": counters["TOTAL"],
        }
    ]

    return columns, data


def get_start_date_from_timespan(timespan):
    now = now_datetime()
    if timespan == "Last 7 Days":
        return add_days(now, -7)
    elif timespan == "Last 14 Days":
        return add_days(now, -14)
    elif timespan == "Last 30 Days":
        return add_days(now, -30)
    elif timespan == "Last 60 Days":
        return add_days(now, -60)
    elif timespan == "Last 90 Days":
        return add_days(now, -90)
    elif timespan == "This Month":
        return get_first_day(now)
    elif timespan == "This Year":
        return getdate(f"{now.year}-01-01")
    else:
        return add_days(now, -30)  # default fallback
