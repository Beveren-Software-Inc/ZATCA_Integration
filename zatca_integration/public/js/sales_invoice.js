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
        frm.trigger('add_submit_button')
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

    add_submit_button: frm => {
       
        if (
            frm.doc.docstatus === 1 &&
            frm.doc.custom_zatca_submit_status !== 'REPORTED' &&
            frm.doc.custom_zatca_submit_status !== 'CLEARED'
        ){
            
        frm.add_custom_button(__('Re-submit'), () => {
                // Custom loader
                const loader = frappe.msgprint({
                    message: `<div class="flex items-center gap-4 text-blue-700">
                                <span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
                                Resubmitting to ZATCA...
                              </div>`,
                    title: __('Please Wait'),
                    indicator: 'blue',
                    wide: true,
                    hide_on_page_change: true,
                });
            
                frappe.call({
                    method: 'zatca_integration.clearence_util.resend_einvoice',
                    args: {
                        doc: frm.doc
                    },
                    callback: function(response) {
                        frappe.msgprint(__('ZATCA Invoice Resubmission Successful'));
                        frm.reload_doc();
                    },
                    error: function(err) {
                        frappe.msgprint(__('ZATCA Resubmission Failed'));
                    },
                    always: function() {
                        loader.hide();
                    }
                });
            }, __('ZATCA Actions'));
            
        }
        
    }
});
