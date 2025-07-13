

// frappe.ui.form.on('Zatca CSR Settings', {
//     refresh: function(frm) {
//         // Only add the buttons if the document is not new and phase is ZATCA Phase 2
//         if (!frm.is_new() && frm.doc.zatca_phase === "ZATCA Phase 2") {

//             // Button to Generate CSR
//             // frm.add_custom_button(__('Generate CSR'), function() {
//             //     frappe.show_progress(__('Generating CSR...'));
//             //     frappe.call({
//             //         method: "genereate_csr",
//             //         doc: frm.doc,
//             //         callback: function(r) {
//             //             frappe.hide_progress();
//             //             if (!r.exc) {
//             //                 frappe.show_alert({message: __('CSR Generated Successfully!'), indicator: 'green'});
//             //                 frm.reload_doc();
//             //             } else {
//             //                 frappe.show_alert({message: __('CSR Generation Failed!'), indicator: 'red'});
//             //             }
//             //         }
//             //     });
//             // });

//              frm.add_custom_button(__('Generate CSR'), function() {
//                 // frappe.show_progress(__('Generating CSR...'));
//                 frappe.call({
//                     method: "zatca_integration.saudi_arabia_electronic_invoicing.utils.generate_csr",
//                     args: {
//                         doc_name: frm.doc.name
//                     },
//                     callback: function(r) {
//                         frappe.hide_progress();
//                         if (!r.exc) {
//                             frappe.show_alert({message: __('CSR Generated Successfully!'), indicator: 'green'});
//                             frm.reload_doc();
//                         } else {
//                             frappe.show_alert({message: __('CSR Generation Failed!'), indicator: 'red'});
//                         }
//                     }
//                 });
//             });
//         }
//     }
// });

frappe.ui.form.on('Zatca CSR Settings', {
    refresh: function(frm) {
        if (!frm.is_new() && frm.doc.zatca_phase === "ZATCA Phase 2") {

            if (!frm.doc.csr_generated) {  // Only show button if CSR not yet generated
                frm.add_custom_button(__('Generate CSR'), function() {
                    frappe.call({
                        method: "zatca_integration.saudi_arabia_electronic_invoicing.utils.generate_csr",
                        args: {
                            doc_name: frm.doc.name
                        },
                        callback: function(r) {
                            frappe.hide_progress();
                            if (!r.exc) {
                                frappe.show_alert({message: __('CSR Generated Successfully!'), indicator: 'green'});
                                frm.reload_doc();  // Reload so button disappears
                            } else {
                                frappe.show_alert({message: __('CSR Generation Failed!'), indicator: 'red'});
                            }
                        }
                    });
                });
            }
        }
    }
});
