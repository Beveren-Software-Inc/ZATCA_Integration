// Copyright (c) 2024, Shakir PM and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Zatca CSR Settings", {
// 	refresh(frm) {

// 	},
// });

frappe.ui.form.on('Zatca CSR Settings', {
    refresh: function(frm) {
        // Only add the "Generate CSR" button if the document is not a new document
        if(!frm.is_new()) {
                frm.add_custom_button(__('Generate CSR'), function() {
                // Show a loading indicator
                frappe.show_progress(__('Generating CSR...'));
                // Call the server side function
                frappe.call({
                    method: "genereate_csr",
                    doc: frm.doc,
                    callback: function(r) {
                        frappe.hide_progress();
                        if(!r.exc) {
                            // Show a success message
                            frappe.show_alert({message:__('CSR Generated Successfully!'), indicator:'green'});
                            // Success message or action
                            frm.reload_doc();
                        } else {
                            // Show an error message
                            frappe.show_alert({message:__('CSR Generation Failed!'), indicator:'red'});
                        }
                    }
                });
            });
        }
    }
});