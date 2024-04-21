frappe.listview_settings['Sales Invoice'] = {
    formatters: {
        custom_zatca_submit_status: function (value, row, column, data) {
            const colorMapping = {
                "DRAFT": "gray",
                "CLEARED": "green",
                "REPORTED": "green",
                "NOT_CLEARED": "orange",
                "NOT_REPORTED": "orange",
                "FAILED": "red",
                "undefined": "blue" // This handles any undefined or unexpected status
            };

            // Default format for unspecified statuses
            if (!colorMapping[value]) {
                return value;
            }

            // Use the color from the mapping, or default to blue if it's not defined
            let colorClass = colorMapping[value] || "blue";

            // Build the HTML string with the appropriate color class
            return `<span class="indicator-pill ${colorClass} filterable no-indicator-dot ellipsis" data-filter="custom_zatca_submit_status,=,${value}">
                        <span class="ellipsis">${value}</span>
                    </span>`;
        }
    }
};
