
frappe.ui.form.on("Compliance CSID", {
    refresh: frm => {
        if (!frm.is_new()) {
            if (!are_all_flags_true(frm)) {
                frm.trigger("genereate_zatca_compliance_csid");
                frm.trigger("validate_zatca_compliance_csid");
            }
        }
    },

    genereate_zatca_compliance_csid: frm => {
        frm.add_custom_button(__('Generate Compliance CSID'), function() {
            frappe.show_progress(__('Generating Compliance CSID...'));
            frappe.call({
                method: "genereate_zatca_compliance_csid",
                doc: frm.doc,
                callback: function(r) {
                    frappe.hide_progress();
                    if (!r.exc) {
                        frappe.show_alert({ message: __('Compliance CSID Generated Successfully!'), indicator: 'green' });
                        frm.reload_doc();
                    } else {
                        frappe.show_alert({ message: __('Failed to Generate Compliance CSID'), indicator: 'red' });
                    }
                },
                error: function(r) {
                    frappe.hide_progress();
                    frappe.show_alert({ message: __('Failed to Generate Compliance CSID'), indicator: 'red' });
                }
            });
        });
    },

    validate_zatca_compliance_csid: frm => {
        frm.add_custom_button(__('Validate Compliance CSID'), function() {
            frappe.show_progress(__('Validating Compliance CSID...'));
            frappe.call({
                method: "validate_zatca_compliance_csid",
                doc: frm.doc,
                callback: function(r) {
                    frappe.hide_progress();
                    if (!r.exc) {
                        frappe.show_alert({ message: __('Compliance CSID Validated Successfully!'), indicator: 'green' });
                        frm.reload_doc();
                    } else {
                        frappe.show_alert({ message: __('Failed to Validate Compliance CSID'), indicator: 'red' });
                    }
                },
                error: function(r) {
                    frappe.hide_progress();
                    frappe.show_alert({ message: __('Failed to Validate Compliance CSID'), indicator: 'red' });
                }
            });
        });
    }
});

// Helper function to check all fields
function are_all_flags_true(frm) {
    return frm.doc.standard_invoice &&
           frm.doc.standard_debit_note &&
           frm.doc.standard_credit_note &&
           frm.doc.simplified_invoice &&
           frm.doc.simplified_debit_note &&
           frm.doc.simplified_credit_note;
}

