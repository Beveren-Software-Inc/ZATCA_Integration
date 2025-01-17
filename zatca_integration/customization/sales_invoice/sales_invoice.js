frappe.ui.form.on('Sales Invoice', {
    onload: frm => {
        frm.trigger('set_custom_payment_method')
        frm.trigger('set_delivery_date')
        frm.trigger('filter_custom_shipping_address')
        
    },
    refresh: frm => {
        frm.trigger('set_custom_payment_method')
        frm.trigger('set_delivery_date')
        frm.trigger('filter_custom_shipping_address')
        
        // Fetch valid sales invoices
        frm.fields_dict['custom_credit_details'].grid.get_field('sales_invoice').get_query = function (doc, cdt, cdn) {
            let row = locals[cdt][cdn];
            const today = frappe.datetime.get_today();
            const days = frm.doc.custom_days_count || 360; // Default to 360 days
            const start_date = frappe.datetime.add_days(today, -days);

            return {
                query: "zatca_integration.customization.sales_invoice.sales_invoice.get_valid_sales_invoices",
                filters: {
                    customer: frm.doc.customer,
                    shipping_address: frm.doc.custom_shipping_address || null,
                    item_code: row.item,
                    start_date: start_date
                }
            };
        };
        
    },
    validate: frm => {
        if (frm.doc.is_return === 1) {
            let selected_invoices = [];
            (frm.doc.custom_credit_details || []).forEach(row => {
                if (row.sales_invoice) {
                    selected_invoices.push(row.sales_invoice);
                }
            });
            frm.set_value('custom_cn_ref', selected_invoices.join(', '));
        }
    },
    shipping_address_name: function (frm) {
        frm.set_value('custom_shipping_address', frm.doc.shipping_address_name);
    },
    custom_shipping_address: function (frm) {
        frm.set_value('shipping_address_name', frm.doc.custom_shipping_address);
    },
    custom_get_all_items: frm => {
        frm.trigger('map_items_to_credit_details')
    },

    set_custom_payment_method: frm => {
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
            const items = frm.doc.items || [];
            const deliveryNotes = [...new Set(items.map(item => item.delivery_note).filter(Boolean))];

            if (deliveryNotes.length > 0) {
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
    filter_custom_shipping_address: frm => {
        frm.fields_dict['custom_shipping_address'].get_query = function(doc) {
            return {
                filters: {
                    link_doctype: 'Customer',
                    link_name: doc.customer
                }

            };
        };
    },
    map_items_to_credit_details: frm => {
        const existing_qtr_map = {};
    
        if (frm.doc.custom_credit_details) {
            frm.doc.custom_credit_details.forEach(row => {
                if (!existing_qtr_map[row.item]) {
                    existing_qtr_map[row.item] = 0;
                }
                existing_qtr_map[row.item] += row.qtr;
            });
        }
    
        frm.doc.items.forEach(item => {
            const total_existing_qtr = existing_qtr_map[item.item_code] || 0;
            const remaining_qty = item.qty - total_existing_qtr;
    
            if (Math.abs(remaining_qty) > 0) {
                let new_row = frm.add_child("custom_credit_details");
                new_row.sales_invoice = item.sales_invoice || '';  
                new_row.item = item.item_code;
                new_row.qtr = remaining_qty;  
            }
        });
        frm.refresh_field('custom_credit_details');
    }
    
});

frappe.ui.form.on("Sales Invoice Item", {
    item_code(frm, cdt, cdn) {
        let row = frappe.get_doc(cdt, cdn);
        if (frm.doc.is_return) {
            frappe.model.set_value(cdt, cdn, 'qty', -Math.abs(row.qty)); 
        }
    },
    qty(frm, cdt, cdn) {
        let row = frappe.get_doc(cdt, cdn);
        if (frm.doc.is_return && row.qty > 0) {
            frappe.model.set_value(cdt, cdn, 'qty', -Math.abs(row.qty)); 
        }
    },
    
});


frappe.ui.form.on("Credit Details", {
    sales_invoice(frm, cdt, cdn) {
        fetch_sold_qty(frm, cdt, cdn);  
        fetch_returned_qty(frm, cdt, cdn);  
        fetch_available_qty(frm, cdt, cdn);  
    },
    already_returned_qty(frm, cdt, cdn) {
        fetch_available_qty(frm, cdt, cdn);  
    },
    item(frm, cdt, cdn) {
        let row = frappe.get_doc(cdt, cdn); 
        
        if (frm.doc.custom_credit_details) {
            frappe.model.set_value(cdt, cdn, 'qtr', -Math.abs(row.qtr)); 
        }
    },
    qtr(frm, cdt, cdn) {
        let row = frappe.get_doc(cdt, cdn);
        
        if (frm.doc.custom_credit_details) {
            frappe.model.set_value(cdt, cdn, 'qtr', -Math.abs(row.qtr)); // Ensure qty is negative
        }
    }
});

// HELPER FUNCTIONS To FETCH QUANTITIES IN CREDIT DETAILS TABLE
function fetch_sold_qty(frm, cdt, cdn) {
    let row = frappe.get_doc(cdt, cdn);
    if (row.item) {
        frappe.call({
            method: "zatca_integration.customization.sales_invoice.sales_invoice.get_batch",
            args: {
                customer: frm.doc.customer,
                sales_invoice: row.sales_invoice,
                item: row.item
            },
            callback: function (r) {
                if (r.message) {
                    r.message.forEach(item => {
                        frappe.model.set_value(cdt, cdn, "sold_qty", item.qty);
                        frappe.model.set_value(cdt, cdn, "available_qty_to_return", item.qty-row.total_returned_qty);
                    });
                    frm.refresh_field('custom_credit_details');
                }
            }
        });
    }
}
function fetch_returned_qty(frm, cdt, cdn) {
    let row = frappe.get_doc(cdt, cdn);
    if (row.item && row.sales_invoice) {
        frappe.call({
            method: "zatca_integration.customization.sales_invoice.sales_invoice.returned_qty",
            args: {
                customer: frm.doc.customer,
                sales_invoice: row.sales_invoice,
                item: row.item
            },
            callback: function (r) {
                if (r.message) {
                    frappe.model.set_value(cdt, cdn, "already_returned_qty", r.message.total_returned_qty);
                }
            }
        });
    }
}
function fetch_available_qty(frm, cdt, cdn) {
    let row = frappe.get_doc(cdt, cdn);
    if (row.item && row.sales_invoice) {
        frappe.call({
            method: "zatca_integration.customization.sales_invoice.sales_invoice.returned_qty",
            args: {
                customer: frm.doc.customer,
                sales_invoice: row.sales_invoice,
                item: row.item
            },
            callback: function (r) {
                if (r.message) {
                    let total_qtr = 0;
                    (frm.doc.custom_credit_details || []).forEach(function (child_row) {
                        if (
                            child_row.sales_invoice === row.sales_invoice &&
                            child_row.item === row.item &&
                            child_row.name !== row.name 
                        ) {
                            total_qtr += child_row.qtr || 0;
                        }
                    });
                    frappe.model.set_value(cdt, cdn, "available_qty_to_return", row.sold_qty + r.message.total_returned_qty + total_qtr);
                }
            }
        });
    }
}
