// Copyright (c) 2023, Shakir PM and contributors
// For license information, please see license.txt

frappe.ui.form.on("Zatca Production CSID", {
	refresh: frm => {
        frm.trigger("genereate_zatca_production_csid");
        frm.trigger('validate_production_csid');
	},
    genereate_zatca_production_csid: frm => {
        frm.add_custom_button(__('Generate Production CSID'), function() {
            // Call the server side function
            frappe.call({
                method: "genereate_zatca_production_csid",
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
    validate_production_csid: frm => {
        // add button called Validate CSID
        frm.add_custom_button(__('Validate Production CSID'), function() {
            frappe.msgprint('Implement the validate method')
        })
    }
});
