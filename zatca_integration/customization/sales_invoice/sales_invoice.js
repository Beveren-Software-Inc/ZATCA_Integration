frappe.ui.form.on('Sales Invoice', {
    onload: frm => {
        frm.trigger('set_custom_payment_method')
        frm.trigger('set_delivery_date')
    },
    refresh: frm => {
        frm.trigger('set_custom_payment_method')
        // Trigger update when item is added or removed
        // frm.fields_dict['items'].grid.get_field('delivery_note').get_query = function(doc) {
        //     frm.trigger('set_delivery_date')
        // }
    },
    set_custom_payment_method: frm => {
        if(frm.doc.customer){
            frappe.call({
                method: "zatca_integration.customization.sales_invoice.sales_invoice.update_payment_method",
                args: {
                    customer: frm.doc.customer,
                },
                callback: function(r) {
                    if (r.message) {
                        console.log(r.message);
                        // Set the earliest delivery date to the invoice
                        frm.set_value('custom_payment_method', r.message);
                    }
                }
            });
        }
    },
    set_delivery_date: frm => {
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
});
