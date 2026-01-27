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

    # ✅ No data case – avoid NoneType errors
    if not result:
        columns = ["Metric", "Value"]
        data = [
            ["Min Time", None],
            ["Max Time", None],
            ["Avg Time", None],
        ]
        return columns, data

    # ✅ Get the first (and only) row safely
    row = result[0] or {}

    min_time = row.get("min_time")
    max_time = row.get("max_time")
    avg_time = row.get("avg_time")

    # `avg_time` can be None if there is no data; guard before rounding
    avg_time_rounded = round(avg_time, 2) if avg_time is not None else None

    data = [
        ["Min Time", min_time],
        ["Max Time", max_time],
        ["Avg Time", avg_time_rounded],
    ]

    columns = ["Metric", "Value"]
    return columns, data
