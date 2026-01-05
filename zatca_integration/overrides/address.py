import frappe


def before_save(doc, method):
    if doc.country == "Saudi Arabia":
        if not doc.address_line2 or not doc.address_line2.isdigit() or len(doc.address_line2) != 4:
            frappe.throw(
                "Building Number must be exactly 4 digits for Company type customer in Saudi Arabia"
            )
