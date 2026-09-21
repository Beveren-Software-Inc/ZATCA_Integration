# Copyright (c) 2025, Shakir PM and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt


# Report Script (Python)
def execute(filters=None):
    result = frappe.db.sql(
        """
	SELECT
		MIN(`zatca_elapsed_time`) as min_time,
		MAX(`zatca_elapsed_time`) as max_time,
		AVG(`zatca_elapsed_time`) as avg_time
	FROM `tabZatca Transactions`
	WHERE `zatca_elapsed_time` IS NOT NULL
	""",
        as_dict=True,
    )

    # ✅ Get the first (and only) row.
    # Aggregates are NULL when no transaction has a recorded elapsed time,
    # so fall back to 0 to keep the report (and its dashboard chart) working.
    row = result[0] if result else {}

    data = [
        ["Min Time", int(flt(row.get("min_time")))],
        ["Max Time", int(flt(row.get("max_time")))],
        ["Avg Time", round(flt(row.get("avg_time")), 2)],
    ]

    columns = ["Metric", "Value"]
    return columns, data
