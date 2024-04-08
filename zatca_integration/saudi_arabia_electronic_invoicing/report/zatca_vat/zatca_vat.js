// Copyright (c) 2024, Shakir PM and contributors
// For license information, please see license.txt

frappe.query_reports["Zatca VAT"] = {
	onload(report) {
		frappe.breadcrumbs.add('Accounts');
		// Add Button for detailed Report
		report.page.add_inner_button(__("Detailed VAT Report"), function() {
			frappe.set_route('query-report', 'Zatca VAT Detailed Report');
		}).removeClass('btn-default').addClass("btn btn-primary");;
	},
	"filters": [
		{
			"fieldname": "company",
			"label": __("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"reqd": 1,
			"default": frappe.defaults.get_user_default("Company")
		},
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"reqd": 1,
			"default": frappe.datetime.add_months(frappe.datetime.get_today(), -1),
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"reqd": 1,
			"default": frappe.datetime.get_today()
		}
	],
	"formatter": function(value, row, column, data, default_formatter) {
		if (data
			&& (data.title=='VAT on Sales' || data.title=='VAT on Purchases')
			&& data.title==value) {
			value = $(`<span>${value}</span>`);
			var $value = $(value).css("font-weight", "bold");
			value = $value.wrap("<p></p>").parent().html();
			return value
		}else if (data && data.title=='Grand Total'){
			if (data.title==value) {
				value = $(`<span>${value}</span>`);
				var $value = $(value).css("font-weight", "bold");
				value = $value.wrap("<p></p>").parent().html();
				return value
			}else{
				value = default_formatter(value, row, column, data);
				value = $(`<span>${value}</span>`);
				var $value = $(value).css("font-weight", "bold");
				value = $value.wrap("<p></p>").parent().html();
				return value
			}
		}else{
			value = default_formatter(value, row, column, data);
			return value;
		}
	},
};
