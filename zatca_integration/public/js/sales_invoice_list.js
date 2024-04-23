frappe.listview_settings['Sales Invoice'] = {
    get_indicator: function (doc) {
		const status_colors = {
			Draft: "grey",
			Unpaid: "orange",
			Paid: "green",
			Return: "gray",
			"Credit Note Issued": "gray",
			"Unpaid and Discounted": "orange",
			"Partly Paid and Discounted": "yellow",
			"Overdue and Discounted": "red",
			Overdue: "red",
			"Partly Paid": "yellow",
			"Internal Transfer": "darkgrey",
		};
		return [__(doc.status), status_colors[doc.status], "status,=," + doc.status];
	},
    formatters: {
        custom_zatca_submit_status: function (value, row, column, data) {
            const colorMapping = {
                "DRAFT": "gray",
                "CLEARED": "green",
                "REPORTED": "cyan",
                "NOT_CLEARED": "orange",
                "NOT_REPORTED": "orange",
                "FAILED": "red",
                "undefined": "red" // This handles any undefined or unexpected status
            };

            // Default format for unspecified statuses
            if (!colorMapping[value]) {
                return value;
            }

            // Use the color from the mapping, or default to blue if it's not defined
            let colorClass = colorMapping[value] || "gray";

            // Build the HTML string with the appropriate color class
            return `<span class="indicator-pill ${colorClass} filterable no-indicator-dot ellipsis" data-filter="custom_zatca_submit_status,=,${value}">
                        <span class="ellipsis">${value}</span>
                    </span>`;
        }
    }
};
