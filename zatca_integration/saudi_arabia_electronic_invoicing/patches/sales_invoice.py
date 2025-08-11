import frappe

def execute():
    custom_field_ids = [
        "Sales Invoice-custom_credit_note_references",
        "Sales Invoice-custom_cn_shipping_address",
        "Sales Invoice-custom_cn_customer",
        "Sales Invoice-custom_credit_details",
        "Sales Invoice-custom_customer",
        "Sales Invoice-custom_shipping_address"
        "Sales Invoice-custom_days_count",
        "Sales Invoice-custom_get_all_items",
        "Sales Invoice-custom_cn_ref",
        "Sales Invoice-custom_credit_shipping_address",
        "Sales Invoice-custom_credit_customer",
      
        
    ]

    for field_id in custom_field_ids:
        if frappe.db.exists("Custom Field", field_id):
            frappe.delete_doc("Custom Field", field_id, force=True)
            frappe.logger().info(f"Deleted Custom Field: {field_id}")
        else:
            frappe.logger().info(f"Custom Field not found, skipping: {field_id}")