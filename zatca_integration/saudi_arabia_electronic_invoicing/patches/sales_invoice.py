import frappe


def execute():
    # List of tuples: (DocType, fieldname)
    custom_fields = [
        ("Sales Invoice", "custom_credit_note_references"),
        ("Sales Invoice", "custom_cn_shipping_address"),
        ("Sales Invoice", "custom_cn_customer"),
        ("Sales Invoice", "custom_credit_details"),
        ("Sales Invoice", "custom_customer"),
        ("Sales Invoice", "custom_shipping_address"),
        ("Sales Invoice", "custom_days_count"),
        ("Sales Invoice", "custom_get_all_items"),
        ("Sales Invoice", "custom_cn_ref"),
    ]

    for doctype, fieldname in custom_fields:
        # ID format in Frappe is usually "<doctype>-<fieldname>"
        custom_field_id = f"{doctype}-{fieldname}"

        # Try deleting by name first
        if frappe.db.exists("Custom Field", custom_field_id):
            frappe.delete_doc("Custom Field", custom_field_id, force=True)
            frappe.logger().info(f"Deleted Custom Field by ID: {custom_field_id}")
            continue

        # If not found by ID, try finding by dt + fieldname
        cf_name = frappe.db.get_value(
            "Custom Field", {"dt": doctype, "fieldname": fieldname}, "name"
        )
        if cf_name:
            frappe.delete_doc("Custom Field", cf_name, force=True)
            frappe.logger().info(f"Deleted Custom Field by fieldname: {fieldname} on {doctype}")
        else:
            frappe.logger().info(f"Custom Field not found, skipping: {fieldname} on {doctype}")
