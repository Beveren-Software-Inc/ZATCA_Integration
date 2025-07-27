// Copyright (c) 2025, Shakir PM and contributors
// For license information, please see license.txt
frappe.query_reports["Monthly Submission Summary"] = {
	"filters": [
		{
			fieldname: "timespan",
			label: __("Timespan"),
			fieldtype: "Select",
			options: [
				"Last 7 Days",
				"Last 14 Days",
				"Last 30 Days",
				"Last 60 Days",
				"Last 90 Days",
				"This Month",
				"This Year"
			],
			default: "Last 30 Days"
		}
	]
};
