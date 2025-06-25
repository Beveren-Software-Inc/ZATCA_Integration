// Copyright (c) 2024, Shakir PM and contributors
// For license information, please see license.txt

frappe.ui.form.on("Production CSID", {
    refresh: frm => {
        if(!frm.is_new()) {
            frm.trigger("genereate_zatca_production_csid");
            test_button_invoice(frm);
            test_sign_invoice(frm);
        }
    },
    genereate_zatca_production_csid: frm => {
        frm.add_custom_button(__('Generate Production CSID'), function() {
            // Show a progress message
            frappe.show_progress(__('Generating Production CSID...'));
            // Call the server side function
            frappe.call({
                method: "generate_zatca_production_csid",
                doc: frm.doc,
                callback: function(r) {
                    frappe.hide_progress();
                    if(!r.exc) {
                        // Show a success message
                        frappe.show_alert({message:__('Production CSID Generated Successfully!'), indicator:'green'});
                        // Success message or action
                        frm.reload_doc();
                    }
                }
            });
        });
    }
});

function test_button_invoice(frm){
    frm.add_custom_button('Test ZATCA Invoice', async function () {
           

            frappe.call({
                method: 'zatca_integration.saudi_arabia_electronic_invoicing.data.create_xml.test_the_invoice',
                callback(r) {
                    if (r.message) {
                        frappe.msgprint(`ZATCA XML File created: <a href="${r.message}" target="_blank">${r.message}</a>`);
                    } else {
                        frappe.msgprint("Something went wrong. No file URL returned.");
                    }
                }
            });
        });
    }

function test_sign_invoice(frm){
    frm.add_custom_button('Test Sign Invoice', async function () {
           
            frappe.call({
                method: 'zatca_integration.saudi_arabia_electronic_invoicing.sign_invoice.test_sign_invoice',
                args:{
                    invoice: "SIN00004"
                },
                callback(r) {
                    if (r.message) {
                        frappe.msgprint(`ZATCA XML File created: <a href="${r.message}" target="_blank">${r.message}</a>`);
                    } else {
                        frappe.msgprint("Something went wrong. No file URL returned.");
                    }
                }
            });
        });
    }