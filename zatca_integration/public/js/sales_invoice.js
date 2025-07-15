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
        check_zatca_enabled(frm, (enabled) => {
            frm.zatca_enabled = enabled;
            if (!enabled){
                return;
            }
            frm.toggle_display("custom_zatca_submit_status", enabled);
            frm.toggle_display("custom_zatca_submit_time", enabled);
            frm.trigger('add_submit_button');
        });

        check_multi_sales_invoice_enabled(frm, (enabled) => {
        frm.zatca_enabled = enabled;
        frm.toggle_display("custom_credit_details", enabled);
        frm.toggle_display("custom_cn_ref", enabled);
        frm.toggle_display("custom_days_count", enabled);
        frm.toggle_display("custom_get_all_items", enabled);
        frm.toggle_display("custom_customer", enabled);
        frm.toggle_display("custom_shipping_address", enabled);
        frm.trigger('get_valid_sales_invoices');
    });
},

    validate: frm => {
        if (frm.is_new() && frm.doc.custom_retention_account && frm.doc.custom_retention_amount) {
            frm.set_value(
                'grand_total', 
                (frm.doc.net_total + frm.doc.total_taxes_and_charges - frm.doc.custom_retention_amount)            );
            frm.refresh_field('grand_total');
            console.log('Retention amount deducted from grand total');
        }
        create_missing_cn_reference(frm);

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
            let percentage = (frm.doc.custom_retention_amount / frm.doc.net_total) * 100;
            frm.set_value('custom_retention_percentage', percentage);
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
       if (frm.zatca_enabled === false) {
        return;
    }
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
            console.log("Printing here",item.sales_invoice)
            if (Math.abs(remaining_qty) > 0) {
                let new_row = frm.add_child("custom_credit_details");
                new_row.sales_invoice = item.sales_invoice || '';  
                new_row.item = item.item_code;
                new_row.qtr = remaining_qty;  
            }
        });
        frm.refresh_field('custom_credit_details');
    },

    get_valid_sales_invoices: frm => {
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
    }
       
});

function check_zatca_enabled(frm, callback) {
    if (frm.doc.company) {
        frappe.call({
            method: "frappe.client.get_value",
            args: {
                doctype: "Company",
                filters: { name: frm.doc.company },
                fieldname: "custom_enable_zatca_e_invoicing"
            },
            callback: function(r) {
                const enabled = !!r.message?.custom_enable_zatca_e_invoicing ? 1 : 0;
                frm.zatca_enabled = enabled;

                frm.toggle_display("custom_zatca_submit_status", !!enabled);
                frm.toggle_display("custom_zatca_submit_time", !!enabled);

                if (callback) callback(enabled);
            }
        });
    } else {
        if (callback) callback(0);
    }
}

function check_multi_sales_invoice_enabled(frm, callback) {
    if (frm.doc.company) {
        frappe.call({
            method: "frappe.client.get_value",
            args: {
                doctype: "Company",
                filters: { name: frm.doc.company },
                fieldname: [
                    "custom_enable_zatca_e_invoicing",
                    "custom_enable_multisales_invoice_on_credit_note"
                ]
            },
            callback: function(r) {
                const values = r.message || {};
                const zatca_enabled = !!values.custom_enable_zatca_e_invoicing;
                const multi_invoice_enabled = !!values.custom_enable_multisales_invoice_on_credit_note;
                const enabled = zatca_enabled && multi_invoice_enabled ? 1 : 0;

                frm.zatca_enabled = enabled;

                if (callback) callback(enabled);
            }
        });
    } else {
        if (callback) callback(0);
    }
}

// New feature from al-kneel
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

function create_missing_cn_reference(frm){
     if (frm.doc.is_return === 1) {
            let selected_invoices = [];
            (frm.doc.custom_credit_details || []).forEach(row => {
                if (row.sales_invoice) {
                    selected_invoices.push(row.sales_invoice);
                }
            });
            frm.set_value('custom_cn_ref', selected_invoices.join(', '));
        }
}
