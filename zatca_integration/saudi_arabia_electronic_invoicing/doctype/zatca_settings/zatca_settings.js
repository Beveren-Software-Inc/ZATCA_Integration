// Copyright (c) 2023, Shakir PM and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Zatca Settings", {
// 	refresh(frm) {

// 	},
// });

frappe.ui.form.on("Zatca Settings", {
	refresh: frm => {
        frm.trigger("genereate_csr");
	},
    genereate_csr: frm => {
        frm.add_custom_button(__('Generate CSR'), function() {
            // Call the server side function
            frappe.call({
                method: "genereate_csr",
                doc: frm.doc,
                callback: function(r) {
                    if(!r.exc) {
                        // Success message or action
                        frm.reload_doc();
                    }
                }
            });
        });
    }
});
