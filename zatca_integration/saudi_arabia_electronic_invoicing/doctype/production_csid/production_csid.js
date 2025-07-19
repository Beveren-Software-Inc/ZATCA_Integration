// // Copyright (c) 2024, Shakir PM and contributors
// // For license information, please see license.txt

frappe.ui.form.on("Production CSID", {
    refresh: frm => {
        if (!frm.is_new()) {
            frm.trigger("re_generate_production_csid");

            // Only show Generate button if is_active != 1
            if (!frm.doc.is_active) {
                frm.trigger("genereate_zatca_production_csid");
            }
            
            if(frm.doc.binary_security_token && (!frm.doc.certificate || !frm.doc.public_key)) {
                frm.trigger("re_build_production_csid");
            }
        }
    },

    genereate_zatca_production_csid: frm => {
        frm.add_custom_button(__('Generate Production CSID'), function() {
            frappe.show_progress(__('Generating Production CSID...'));

            frappe.call({
                method: "generate_zatca_production_csid",
                doc: frm.doc,
                callback: function(r) {
                    frappe.hide_progress();
                    if (!r.exc) {
                        frappe.show_alert({
                            message: __('Production CSID Generated Successfully!'),
                            indicator: 'green'
                        });
                        frm.reload_doc();
                    }
                }
            });
        });
    },

    re_generate_production_csid: frm => {
        frm.add_custom_button(__('Renew Production CSID'), function () {
            frappe.call({
                method: 'renew_zatca_production_csid',
                doc: frm.doc,
                callback(r) {
                    if (r.message) {
                        frappe.msgprint(`ZATCA XML File created: <a href="${r.message}" target="_blank">${r.message}</a>`);
                    } else {
                        frappe.msgprint("Something went wrong. No file URL returned.");
                    }
                }
            });
        });
    },

    re_build_production_csid: frm => {
        frm.add_custom_button(__('Re-build Certificate'), function () {
            frappe.call({
                    method: "zatca_integration.saudi_arabia_electronic_invoicing.utils.get_certificate_and_public_key",
                    args: {
                        binary_security_token: frm.doc.binary_security_token,
                        created_on: frm.doc.created_time
                    },
                    callback: function(r) {
                        if (r.message) {
                            frm.set_value("certificate", r.message.certificate);
                            frm.set_value("public_key", r.message.public_key);
                            frm.set_value("expiry_date", r.message.expiry_date);
                            frm.save()
                            frappe.msgprint("Certificate and public key extracted successfully");
                        }
                    }
                });
        });
    }
});
