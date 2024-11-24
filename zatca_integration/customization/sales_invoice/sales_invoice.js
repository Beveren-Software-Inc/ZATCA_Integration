frappe.ui.form.on('Sales Invoice', {
    onload: frm => {
        frm.trigger('set_custom_payment_method')
        frm.trigger('set_delivery_date')
    },
    refresh: frm => {
        frm.trigger('set_custom_payment_method')
        frm.trigger('set_delivery_date')
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



// additional customisations for CN.
frappe.ui.form.on('Sales Invoice', {
    onload: function(frm) {
        frm.fields_dict['custom_shipping_address'].get_query = function(doc) {
            return {
                filters: {
                    link_doctype: 'Customer',
                    link_name: doc.customer
                }

            };
        };
    }
});


// frappe.ui.form.on('Sales Invoice', {
//     onload(frm) {
//         frm.fields_dict['custom_credit_details'].grid.get_field('sales_invoice').get_query = function(doc, cdt, cdn) {
//             let row = locals[cdt][cdn];
//             const today = frappe.datetime.get_today();
//             const days = frm.doc.custom_days_count;
//             const fifteen_days_ago = frappe.datetime.add_days(today, -(days));
//     if(!frm.doc.custom_shipping_address){
//             return {
//                 filters: [
//                     ["Sales Invoice", "status", "!=", "Cancelled"],
//                     ["Sales Invoice", "status", "!=", "Credit Note Issued"],
//                     ["Sales Invoice", "status", "!=", "Draft"],
//                     ["Sales Invoice", "is_return", "!=", "1"],
//                     ["Sales Invoice", "customer", "=", frm.doc.customer],
//                     ["Sales Invoice", "posting_date", ">=", fifteen_days_ago],
//                     ["Sales Invoice Item", "item_code", "=", row.item]
//                 ]
//             };
//         }
//         else if(frm.doc.custom_shipping_address){
//             return {
//                 filters: [
//                     ["Sales Invoice", "status", "!=", "Cancelled"],
//                     ["Sales Invoice", "status", "!=", "Credit Note Issued"],
//                     ["Sales Invoice", "status", "!=", "Draft"],
//                     ["Sales Invoice", "is_return", "!=", "1"],
//                     ["Sales Invoice", "customer", "=", frm.doc.customer],
//                     ["Sales Invoice", "shipping_address_name", "=", frm.doc.custom_shipping_address],
//                     ["Sales Invoice", "posting_date", ">=", fifteen_days_ago],
//                     ["Sales Invoice Item", "item_code", "=", row.item]
//                 ]
//             };


//         }

//         else{


//         }
//         };
//     },

    
// });

frappe.ui.form.on('Sales Invoice', {
    onload(frm) {
        frm.fields_dict['custom_credit_details'].grid.get_field('sales_invoice').get_query = function (doc, cdt, cdn) {
            let row = locals[cdt][cdn];
            const today = frappe.datetime.get_today();
            const days = frm.doc.custom_days_count || 15; // Default to 15 days
            const start_date = frappe.datetime.add_days(today, -days);

            return {
                query: "zatca_integration.customization.sales_invoice.sales_invoice.get_valid_sales_invoices",
                filters: {
                    customer: frm.doc.customer,
                    shipping_address: frm.doc.custom_shipping_address || null,
                    item_code: row.item,
                    start_date: start_date
                },
                callback: function (r) {
                    // Ensure r.message is not undefined
                    if (r) {
                        console.log("Valid Sales Invoices:", r); // Log the result for debugging
                    } else {
                        console.error("Error: No data returned from the server.");
                    }
                }
            };
        };
    }
});





frappe.ui.form.on('Sales Invoice', {
    custom_get_all_items: function(frm) {
        map_items_to_credit_details(frm);
    }
});
    
    // function map_items_to_credit_details(frm) {
    //     frm.clear_table("custom_credit_details");
    //     frm.doc.items.forEach(item => {
    //         let new_row = frm.add_child("custom_credit_details");
    //         new_row.item = item.item_code;
    //         new_row.qtr = item.qty;
    //     });
    //     frm.refresh_field('custom_credit_details');
    // }
    function map_items_to_credit_details(frm) {
        frm.doc.items.forEach(item => {
            // Calculate the sum of existing rows' qtr for the same item_code and sales_invoice
            let total_existing_qtr = frm.doc.custom_credit_details
                .filter(row => row.item === item.item_code && row.sales_invoice)
                .reduce((sum, row) => sum + row.qtr, 0);
    
            // Only add a new row if the total_existing_qtr is less than item.qty
            if (Math.abs(total_existing_qtr) < Math.abs(item.qty)) {
                let remaining_qty = item.qty - total_existing_qtr; // Do not use Math.abs() for remaining qty
                if (remaining_qty !== 0) {
                    let new_row = frm.add_child("custom_credit_details");
                    new_row.sales_invoice = item.sales_invoice || ''; // Ensure sales_invoice is assigned correctly
                    new_row.item = item.item_code;
                    new_row.qtr = remaining_qty; // Keep the negative sign if needed
                }
            }
        });
    
        frm.refresh_field("custom_credit_details");
    }
    
    
    
    
    



// Function to validate quantity for a single row
function validate_qty(row) {
    if (row.sold_qty < (-(row.qtr + row.already_returned_qty))) {
        frappe.throw(`Row ${row.idx} Item ${row.item} from Sales Invoice ${row.sales_invoice} cannot be returned more than the sold quantity (${row.sold_qty}). Difference qty: ${row.sold_qty + (row.qtr + row.already_returned_qty)}.`);
    }
}

// Fetch and set sold quantity for an item in a sales invoice
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

// Fetch and set already returned quantity for an item in a sales invoice
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
                if (r.message && r.message.total_returned_qty !== undefined) {
                    frappe.model.set_value(cdt, cdn, "already_returned_qty", r.message.total_returned_qty);
                    frappe.model.set_value(cdt, cdn, "available_qty_to_return", row.sold_qty+r.message.total_returned_qty);
                    frm.refresh_field('custom_credit_details');
                } else {
                    console.error("Unexpected response:", r.message);
                }
            }
        });
    }
}


frappe.ui.form.on("Credit Details", {
    sales_invoice(frm, cdt, cdn) {
        fetch_sold_qty(frm, cdt, cdn);  
        fetch_returned_qty(frm, cdt, cdn);  
    }
});

// Validate quantities in 'Sales Invoice'
frappe.ui.form.on('Sales Invoice', {
    validate(frm) {
        if (frm.doc.is_return === 1) {
            frm.doc.custom_credit_details.forEach(row => {
                validate_qty(row);  
            });
        }
    }
});

frappe.ui.form.on('Sales Invoice', {
    validate: function (frm) {
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
});
frappe.ui.form.on("Sales Invoice Item", {
    item_code(frm, cdt, cdn) {
        let row = frappe.get_doc(cdt, cdn); // Get the current row object
        
        // Check if the Sales Invoice is a return and update qty accordingly
        if (frm.doc.is_return) {
            frappe.model.set_value(cdt, cdn, 'qty', -Math.abs(row.qty)); // Ensure qty is negative
        }
    },

    qty(frm, cdt, cdn) {
        let row = frappe.get_doc(cdt, cdn); // Get the current row object
        
        // Ensure qty is negative if the Sales Invoice is a return
        if (frm.doc.is_return && row.qty > 0) {
            frappe.model.set_value(cdt, cdn, 'qty', -Math.abs(row.qty)); // Convert to negative if positive
        }
    },
    
});

