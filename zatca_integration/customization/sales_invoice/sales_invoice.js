frappe.ui.form.on('Sales Invoice', {
    onload: frm => {
        frm.trigger('set_custom_payment_method')
        frm.trigger('set_delivery_date')

        // negate the retention amount if is_return and custom_retention_amount is set
        if (frm.doc.is_return && frm.doc.custom_retention_account && frm.doc.custom_retention_amount && frm.is_new()) {
            frm.set_value('custom_retention_amount', (-1 * frm.doc.custom_retention_amount));
        }
    },
    refresh: frm => {
        frm.trigger('set_custom_payment_method')
        frm.trigger('set_delivery_date')
        frm.trigger('zatca_manual_reporting')
        
    },
    validate: frm => {
        if (frm.is_new() && frm.doc.custom_retention_account && frm.doc.custom_retention_amount) {
            frm.set_value(
                'grand_total', 
                (frm.doc.net_total + frm.doc.total_taxes_and_charges - frm.doc.custom_retention_amount)            );
            frm.refresh_field('grand_total');
            console.log('Retention amount deducted from grand total');
        }
    },
    on_submit: frm => {
        // Reload to show Correct Status
        if (frm.doc.docstatus === 1 && frm.doc.custom_retention_amount) {
            frm.reload_doc();
        }
    },
    custom_retention_account: function(frm) {
        frm.set_df_property('custom_retention_amount', 'reqd', 1);
    },
    custom_retention_percentage: function(frm) {
        if (!frm.doc.custom_retention_account) {
            frappe.throw(__("Please select a Retention Account"));
        }
        if ( frm.doc.custom_retention_account && frm.doc.custom_retention_percentage) {
            frm.trigger('set_retention_amount');
        }
    },
    custom_retention_amount: function(frm) {
        if (!frm.doc.custom_retention_account) {
            frappe.throw(__("Please select a Retention Account"));
        }else {
            // Update the grand total
            frm.set_value('grand_total', (frm.doc.net_total + frm.doc.total_taxes_and_charges - frm.doc.custom_retention_amount));
            frm.refresh_field('grand_total');
        }
    },
    set_retention_amount: frm => {
        let retention = frm.doc.custom_retention_percentage 
            ? (frm.doc.net_total * frm.doc.custom_retention_percentage / 100) 
            : frm.doc.custom_retention_amount;

        frm.set_value('custom_retention_amount', retention);
        frm.refresh_field('custom_retention_amount');

        // Update the grand total
        frm.set_value('grand_total', (frm.doc.net_total + frm.doc.total_taxes_and_charges - retention));
        frm.refresh_field('grand_total');
    },
    set_custom_payment_method: frm => {
        //check the frm is submitted or not
        if(frm.doc.docstatus == 1 || frm.doc.docstatus == 2){
            return;
        }
        if(frm.doc.customer){
            frappe.call({
                method: "zatca_integration.customization.sales_invoice.sales_invoice.update_payment_method",
                args: {
                    customer: frm.doc.customer,
                },
                callback: function(r) {
                    if (r.message) {
                        console.log(r.message);
                        // Set the payment method to the invoice
                        frm.set_value('custom_payment_means', r.message);
                    }
                }
            });
        }
    },
    set_delivery_date: frm => {
        if(frm.doc.docstatus == 1 || frm.doc.docstatus == 2){
            return;
        }
        if(!frm.doc.custom_delivery_date){
            // check if items array has some items
            const items = frm.doc.items || [];
            const deliveryNotes = [...new Set(items.map(item => item.delivery_note).filter(Boolean))];

            console.log(deliveryNotes);

            if (deliveryNotes.length > 0) {
                // Fetch the delivery date from the of the notes
                frappe.call({
                    method: "zatca_integration.customization.sales_invoice.sales_invoice.update_delivery_date",
                    args: {
                    delivery_note: deliveryNotes[0]
                    },
                    callback: function(r) {
                        if (r.message) {
                            // Set the delivery date to the invoice
                            frm.set_value('custom_delivery_date', r.message);
                        }
                    }
                });
            }
        }
    },
    zatca_manual_reporting: frm => {
        // Add ZATCA button for submitted invoices
        if (frm.doc.docstatus === 1) {
            // Only show the button if ZATCA Phase 2 is enabled and the company is in Saudi Arabia
            frappe.db.get_value('Company', frm.doc.company, ['country', 'custom_enable_zatca_e_invoicing', 'custom_zatca_phase', 'custom_use_manual_reporting'])
                .then(r => {
                    let values = r.message;
                    console.log('values', values);
                    
                    if (values && values.country === 'Saudi Arabia' && 
                        values.custom_enable_zatca_e_invoicing === 1 && 
                        values.custom_zatca_phase === 'ZATCA Phase 2' &&
                        values.custom_use_manual_reporting === 1) {
                        
                        // Check if the invoice has been reported to ZATCA successfully
                        const is_reported = frm.doc.custom_zatca_submit_status && 
                                          frm.doc.custom_zatca_submit_status !== 'DRAFT' && 
                                          frm.doc.custom_zatca_submit_status !== 'NOT_CLEARED';
                        
                        // Only show the Report button if not yet reported to ZATCA or failed
                        if (!is_reported) {
                            console.log('reported', is_reported);
                            frm.add_custom_button(__('Report to ZATCA'), function() {
                                frappe.confirm(
                                    __('Are you sure you want to report this invoice to ZATCA?'),
                                    function() {
                                        frappe.show_alert({message: __('Reporting to ZATCA...'), indicator: 'blue'});
                                        frappe.call({
                                            method: 'zatca_integration.clearence_util.generate_einvoice',
                                            args: {
                                                doc: frm.doc,
                                                method: null
                                            },
                                            callback: function(r) {
                                                console.log('r', r.message);
                                                
                                                if (r.message && r.message.custom_zatca_submit_status === 'CLEARED') {
                                                    frm.reload_doc();
                                                    frappe.show_alert({message: __('Successfully Reported to ZATCA!'), indicator: 'green'});
                                                }
                                            }
                                        });
                                    }
                                );
                            }, __('ZATCA'));
                        }
                    }
                });
        }
    }
});
