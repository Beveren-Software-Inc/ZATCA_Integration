frappe.ui.form.on('Sales Invoice', {
    onload: frm => {
        frm.trigger('set_custom_payment_method')
        frm.trigger('set_delivery_date')

        // negate the retention amount if is_return and custom_retention_amount is set
        if (frm.doc.is_return && frm.doc.custom_retention_amount) {
            frm.set_value('custom_retention_amount', (-1 * frm.doc.custom_retention_amount));
        }
    },
    refresh: frm => {
        frm.trigger('set_custom_payment_method')
        frm.trigger('set_delivery_date')
    },
    validate: frm => {
        frm.trigger('set_retention_amount')

        if (frm.__islocal && frm.doc.custom_retention_amount) {
            let grand_total = frm.doc.grand_total;
            let retention_amount = frm.doc.custom_retention_amount;
            let new_grand_total = grand_total - retention_amount;
            frm.set_value('grand_total', new_grand_total);
        }
    },
    on_submit: frm => {
        // Reload to show Correct Status
        if(frm.doc.docstatus == 1 && frm.doc.custom_retention_amount) frm.reload_doc();
    },
    custom_retention_percentage: function(frm) {
        if (!frm.doc.custom_retention_account) {
            frappe.msgprint(__("Please select a Retention Account"));
            return
        }
        if ( frm.doc.custom_retention_account && frm.doc.custom_retention_percentage) {
            frm.trigger('set_retention_amount');
        }
    },
    set_retention_amount: function(frm) {
        const retention = (frm.doc.net_total * frm.doc.custom_retention_percentage / 100);
        frm.set_value('custom_retention_amount', retention);
        frm.refresh_field('custom_retention_amount');

        // Update the grand total
        let grand_total = frm.doc.grand_total;
        frm.set_value('grand_total', grand_total - retention);
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
    }
});
