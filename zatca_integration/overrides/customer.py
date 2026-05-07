# custom_app/overrides/customer.py

import frappe

from erpnext.selling.doctype.customer.customer import Customer
# from erpnext.selling.doctype.customer.customer import make_address

from frappe.contacts.doctype.address.address import get_address_display


class CustomCustomer(Customer):

	def create_primary_address(self):
		from frappe.contacts.doctype.address.address import get_address_display

		if self.flags.is_new_doc and self.get("address_line1"):
			address = make_address(self)
			address_display = get_address_display(address.name)

			self.db_set("customer_primary_address", address.name)
			self.db_set("primary_address", address_display)
		elif self.customer_primary_address:
			frappe.set_value("Address", self.customer_primary_address, "is_primary_address", 1)  # ensure



def make_address(args, is_primary_address=1, is_shipping_address=1):
	reqd_fields = []
	for field in ["city", "country"]:
		if not args.get(field):
			reqd_fields.append("<li>" + field.title() + "</li>")

	if reqd_fields:
		msg = _("Following fields are mandatory to create address:")
		frappe.throw(
			"{} <br><br> <ul>{}</ul>".format(msg, "\n".join(reqd_fields)),
			title=_("Missing Values Required"),
		)

	party_name_key = "customer_name" if args.doctype == "Customer" else "supplier_name"

	address = frappe.get_doc(
		{
			"doctype": "Address",
			"address_title": args.get(party_name_key),
			"address_line1": args.get("address_line1"),
			"address_line2": args.get("address_line2"),
			"city": args.get("city"),
			"state": args.get("state"),
			"pincode": args.get("pincode"),
            "county": args.get("county"), # new field
			"country": args.get("country"),
			"is_primary_address": is_primary_address,
			"is_shipping_address": is_shipping_address,
			"links": [{"link_doctype": args.get("doctype"), "link_name": args.get("name")}],
		}
	)

	if flags := args.get("flags"):
		address.insert(ignore_permissions=flags.get("ignore_permissions"))
	else:
		address.insert()

	return address