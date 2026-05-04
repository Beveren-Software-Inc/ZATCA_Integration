frappe.listview_settings['Sales Invoice'] = {
    onload: function (listview) {
        listview.page.add_inner_button(__('ZATCA Report'), function () {
            const names = listview.get_checked_items(true) || [];
            if (!names.length) {
                frappe.msgprint(__('Select at least one Sales Invoice by ticking the checkboxes.'));
                return;
            }
            frappe.confirm(
                __('Report {0} selected invoice(s) to ZATCA? This runs the same action as ZATCA Actions → Report on each invoice.', [
                    names.length,
                ]),
                () => {
                    frappe.dom.freeze(__('Reporting to ZATCA...'));
                    frappe.call({
                        method: 'zatca_integration.clearence_util.bulk_resend_einvoices',
                        args: { invoice_names: names },
                        callback: function (r) {
                            frappe.dom.unfreeze();
                            const result = r.message || {};
                            const parts = [];
                            if (result.success && result.success.length) {
                                parts.push(
                                    '<p><strong>' +
                                        __('Succeeded') +
                                        ` (${result.success.length})</strong><br>` +
                                        frappe.utils.escape_html(result.success.join(', ')) +
                                        '</p>'
                                );
                            }
                            if (result.skipped && result.skipped.length) {
                                const skipLines = result.skipped
                                    .map(
                                        (row) =>
                                            frappe.utils.escape_html(row.name) +
                                            ': ' +
                                            frappe.utils.escape_html(row.message || '')
                                    )
                                    .join('<br>');
                                parts.push(
                                    '<p><strong>' +
                                        __('Skipped') +
                                        ` (${result.skipped.length})</strong><br>${skipLines}</p>`
                                );
                            }
                            if (result.failed && result.failed.length) {
                                const failLines = result.failed
                                    .map(
                                        (row) =>
                                            frappe.utils.escape_html(row.name) +
                                            ': ' +
                                            frappe.utils.escape_html(row.message || '')
                                    )
                                    .join('<br>');
                                parts.push(
                                    '<p><strong>' +
                                        __('Failed') +
                                        ` (${result.failed.length})</strong><br>${failLines}</p>`
                                );
                            }
                            frappe.msgprint({
                                title: __('ZATCA bulk report'),
                                message: parts.join('<hr>') || __('Finished'),
                                wide: true,
                            });
                            listview.refresh();
                        },
                        error: function () {
                            frappe.dom.unfreeze();
                        },
                    });
                }
            );
        });
    },
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
                "PENDING": "blue",
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
