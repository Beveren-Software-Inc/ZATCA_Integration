// Copyright (c) 2023, Shakir PM and contributors
// For license information, please see license.txt

frappe.ui.form.on("Zatca Compliance CSID", {
	refresh: frm => {
        frm.trigger("genereate_zatca_compliance_csid");
        frm.trigger("invoke_zatca_compliance_invoice");
	},
    genereate_zatca_compliance_csid: frm => {
        frm.add_custom_button(__('Generate Compliance CSID'), function() {
            // Call the server side function
            frappe.call({
                method: "genereate_zatca_compliance_csid",
                doc: frm.doc,
                callback: function(r) {
                    if(!r.exc) {
                        // Success message or action
                        // frm.reload_doc();
                        console.log('Retuned Somethng')
                    }
                }
            });
        });
    },
    invoke_zatca_compliance_invoice: frm => {
        frm.add_custom_button(__('Validate Compliance CSID'), function() {
            // Call the server side function
            frappe.call({
                method: "invoke_zatca_compliance_invoice",
                doc: frm.doc,
                callback: function(r) {
                    if(!r.exc) {
                        // Success message or action
                        // frm.reload_doc();
                        console.log('Retuned Somethng')
                    }
                }
            });
        })
    }
});
