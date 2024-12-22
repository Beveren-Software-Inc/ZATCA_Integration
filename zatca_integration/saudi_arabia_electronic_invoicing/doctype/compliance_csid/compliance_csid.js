// Copyright (c) 2024, Shakir PM and contributors
// For license information, please see license.txt

frappe.ui.form.on("Compliance CSID", {
	refresh: frm => {
        if(!frm.is_new()) {
            frm.trigger("genereate_zatca_compliance_csid");
            frm.trigger("validate_zatca_compliance_csid");
        }
    },
    genereate_zatca_compliance_csid: frm => {
            frm.add_custom_button(__('Generate Compliance CSID'), function() {
            // Show a progress message
            frappe.show_progress(__('Generating Compliance CSID...'));
            // Call the server side function
            frappe.call({
                method: "genereate_zatca_compliance_csid",
                doc: frm.doc,
                callback: function(r) {
                    frappe.hide_progress();
                    if(!r.exc) {
                        frappe.show_alert({message:__('Compliance CSID Generated Successfully!'), indicator:'green'});
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
            // Show a progress message            
            frappe.show_progress(__('Validating Compliance CSID...'));
            // Call the server side function
            frappe.call({
                method: "validate_zatca_compliance_csid",
                doc: frm.doc,
                callback: function(r) {
                    frappe.hide_progress();
                    if(!r.exc) {
                        frappe.show_alert({message:__('Compliance CSID Validated Successfully!'), indicator:'green'});
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
        })
    }
});
