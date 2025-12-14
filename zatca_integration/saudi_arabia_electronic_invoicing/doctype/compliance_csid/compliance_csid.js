
frappe.ui.form.on("Compliance CSID", {
    refresh: frm => {
        if (!frm.is_new()) {
            if (!frm.doc.binary_security_token && !frm.doc.renewal_pcsid) {
                frm.trigger("genereate_zatca_compliance_csid");

            }
            if (!are_all_flags_true(frm) && frm.doc.binary_security_token) {
                frm.trigger("validate_zatca_compliance_csid");

            }
            if(frm.doc.renewal_pcsid){
                frm.trigger('re_generate_production_csid');
            }
        }
        make_fields_read_only(frm);

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
        // Check if required validations are complete based on CSR invoice type
        if (!frm.doc.csr_settings) {
            // If no CSR settings, show button
            add_validate_button(frm);
            return;
        }

        // Fetch CSR Settings invoice type asynchronously
        frappe.db.get_value('Zatca CSR Settings', frm.doc.csr_settings, 'csrinvoicetype', (r) => {
            if (r && r.csrinvoicetype) {
                const invoiceType = r.csrinvoicetype;
                const isComplete = are_required_validations_complete(frm, invoiceType);

                if (!isComplete) {
                    add_validate_button(frm);
                }
            } else {
                // If unable to fetch, show button to be safe
                add_validate_button(frm);
            }
        });
    },

       re_generate_production_csid: frm => {
        // Hide button if renewal is complete (renewal_pcsid is ticked, certificate exists, and binary_security_token exists)
        const hasCertificate = frm.doc.certificate && String(frm.doc.certificate).trim() !== '';
        const hasBinarySecurityToken = frm.doc.binary_security_token && String(frm.doc.binary_security_token).trim() !== '';

        if (frm.doc.renewal_pcsid && hasCertificate && hasBinarySecurityToken) {
            return; // Don't show the button if renewal is already complete
        }

        frm.add_custom_button(__('Renew Production CSID'), function () {
            frappe.show_progress(__('Renewing Production CSID...'));
            frappe.call({
                method: 'renew_zatca_production_csid',
                doc: frm.doc,
                callback(r) {
                    frappe.hide_progress();
                    if (!r.exc) {
                        frappe.show_alert({
                            message: __('Production CSID Renewed Successfully!'),
                            indicator: 'green'
                        });
                        frm.reload_doc();
                    }
                }
            });
        });
    },

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

// Helper function to add the Validate Compliance CSID button
function add_validate_button(frm) {
    frm.add_custom_button(__('Validate Compliance CSID'), function() {
        frappe.show_progress(__('Validating Compliance CSID...'));
        frappe.call({
            method: "validate_zatca_compliance_csid",
            doc: frm.doc,
            invoice: "TEST-SINV-2025-000281",
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

// Helper function to check required validations based on CSR invoice type
function are_required_validations_complete(frm, invoiceType) {
    if (invoiceType === '1100') {
        // Both B2B and B2C - need all 6 checkboxes
        return frm.doc.standard_invoice &&
               frm.doc.standard_debit_note &&
               frm.doc.standard_credit_note &&
               frm.doc.simplified_invoice &&
               frm.doc.simplified_debit_note &&
               frm.doc.simplified_credit_note;
    } else if (invoiceType === '1000') {
        // B2B only - need standard invoices (left 3 checkboxes)
        return frm.doc.standard_invoice &&
               frm.doc.standard_debit_note &&
               frm.doc.standard_credit_note;
    } else if (invoiceType === '0100') {
        // B2C only - need simplified invoices (right 3 checkboxes)
        return frm.doc.simplified_invoice &&
               frm.doc.simplified_debit_note &&
               frm.doc.simplified_credit_note;
    }

    return false; // Unknown type, show button
}

function make_fields_read_only(frm) {
    if (frm.doc.binary_security_token) {
        frm.fields.forEach(function(field) {
            frm.set_df_property(field.df.fieldname, 'read_only', 1);
        });

        frm.disable_save();
    }
}
