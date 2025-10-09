# Copyright (c) 2025, Shakir PM and contributors
# For license information, please see license.txt

import frappe


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

    # ✅ Get the first (and only) row
    row = result[0]

    data = [
        ["Min Time", row["min_time"]],
        ["Max Time", row["max_time"]],
        ["Avg Time", round(row["avg_time"], 2)],
    ]

    columns = ["Metric", "Value"]
    return columns, data
