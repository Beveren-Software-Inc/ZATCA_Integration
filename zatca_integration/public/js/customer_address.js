frappe.provide("frappe.ui.form");

frappe.ui.form.CustomerQuickEntryForm = class CustomerQuickEntryForm extends (
	frappe.ui.form.ContactAddressQuickEntryForm
) {

	constructor(doctype, after_insert, init_callback, doc, force) {
		super(doctype, after_insert, init_callback, doc, force);
		this.skip_redirect_on_error = true;
	}

	get_variant_fields() {

		let variant_fields = super.get_variant_fields();

		// Find city field
		let city_index = variant_fields.findIndex(
			f => f.fieldname === "city"
		);

		// Make existing fields mandatory
		[
			"address_line1",
			"address_line2",
			"city",
			"state",
			"country_address",
			"pincode"
		].forEach(fieldname => {

			let field = variant_fields.find(
				f => f.fieldname === fieldname
			);

			if (field) {
				field.reqd = 1;
				delete field.mandatory_depends_on;
			}
		});

		// Change label
		let city_field = variant_fields.find(
			f => f.fieldname === "city"
		);

		if (city_field) {
			city_field.label = __("Subdivision Name");
			city_field.reqd = 1;
		}

		let address_line1 = variant_fields.find(
			f => f.fieldname === "address_line1"
		);

		if (address_line1) {
			address_line1.label = __("Street Name");
			address_line1.reqd = 1;
		}

		let address_line2 = variant_fields.find(
			f => f.fieldname === "address_line2"
		);

		if (address_line2) {
			address_line2.label = __("Building Number");
			address_line2.reqd = 1;
		}

		let postal_code = variant_fields.find(
			f => f.fieldname === "pincode"
		);

		if (postal_code) {
			postal_code.label = __("Postal Code");
			postal_code.reqd = 1;
		}

		if (city_index !== -1) {

			variant_fields.splice(city_index + 1, 0,
				{
					label: __("City Name"),
					fieldname: "county",
					fieldtype: "Data",
					reqd: 1,
				}
			);
		}

		return variant_fields;
	}

	// insert() {

	// 	// IMPORTANT FIX
	// 	Object.assign(this.dialog.doc, this.dialog.get_values());

	// 	return super.insert();
	// }
};