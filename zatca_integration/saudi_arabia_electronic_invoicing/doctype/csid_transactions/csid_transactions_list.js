frappe.listview_settings['CSID Transactions'] = {
    onload: function(listview) {
        // Hide the "Add" button
        listview.page.btn_primary.hide();
    }
};