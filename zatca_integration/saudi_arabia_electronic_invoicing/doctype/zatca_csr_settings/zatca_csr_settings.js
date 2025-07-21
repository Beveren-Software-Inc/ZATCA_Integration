

frappe.ui.form.on('Zatca CSR Settings', {
    refresh: function(frm) {
        if (!frm.is_new() && frm.doc.zatca_phase === "ZATCA Phase 2") {

            if (!frm.doc.csr_generated) {  
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
        make_fields_read_only(frm);
    }
});


function make_fields_read_only(frm) {
    if (frm.doc.csr_generated) {
        frm.fields.forEach(function(field) {
            frm.set_df_property(field.df.fieldname, 'read_only', 1);
        });

        frm.disable_save();
    }
}