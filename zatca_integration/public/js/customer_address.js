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

		let country_field = variant_fields.find(
			f => f.fieldname === "country_address"
		);

		// Make existing fields mandatory
		// [
		// 	"address_line1",
		// 	"address_line2",
		// 	"city",
		// 	// "state",
		// 	"country_address",
		// 	"pincode"
		// ].forEach(fieldname => {

		// 	let field = variant_fields.find(
		// 		f => f.fieldname === fieldname
		// 	);

		// 	if (field) {
		// 		field.reqd = 1;
		// 		delete field.mandatory_depends_on;
		// 	}
		// });

		// Change label
		let city_field = variant_fields.find(
			f => f.fieldname === "city"
		);

		if (city_field) {
			city_field.label = __("District Name");
			city_field.mandatory_depends_on = "eval:doc.country_address || doc.city || doc.address_line1 || doc.address_line2 || doc.pincode || doc.county";
		}

		let address_line1 = variant_fields.find(
			f => f.fieldname === "address_line1"
		);

		if (address_line1) {
			address_line1.label = __("Street Name");
			address_line1.mandatory_depends_on = "eval:doc.country_address || doc.city || doc.address_line1 || doc.address_line2 || doc.pincode || doc.county";
		}

		let address_line2 = variant_fields.find(
			f => f.fieldname === "address_line2"
		);

		if (address_line2) {
			address_line2.label = __("Building Number");
			address_line2.placeholder = __("Must be four number for KSA");
			address_line2.mandatory_depends_on = "eval:doc.country_address || doc.city || doc.address_line1 || doc.address_line2 || doc.pincode || doc.county";
		}

		let postal_code = variant_fields.find(
			f => f.fieldname === "pincode"
		);

		if (postal_code) {
			postal_code.label = __("Postal Code");
			postal_code.mandatory_depends_on = "eval:doc.country_address || doc.city || doc.address_line1 || doc.address_line2 || doc.pincode || doc.county";
		}

		if (city_index !== -1) {

			variant_fields.splice(city_index + 1, 0,
				{
					label: __("City Name"),
					fieldname: "county",
					fieldtype: "Data",
					mandatory_depends_on: "eval:doc.country_address || doc.city || doc.address_line1 || doc.address_line2 || doc.pincode || doc.county"
				}
			);
		}

		if (country_field) {
			delete country_field.mandatory_depends_on;
			country_field.hidden = 1;
			country_field.reqd = 0;
		}

		let street_index = variant_fields.findIndex(
			f => f.fieldname === "address_line1"
		);

		if (street_index !== -1) {
			variant_fields.splice(street_index + 1, 0,
				{
					label: __("Street (In Arabic)"),
					fieldname: "custom_street_arabic",
					fieldtype: "Data"
				}
			);
		}

		let district_index = variant_fields.findIndex(
			f => f.fieldname === "city"
		);

		if (district_index !== -1) {

			variant_fields.splice(district_index + 1, 0,
				{
					label: __("District (In Arabic)"),
					fieldname: "custom_district_arabic",
					fieldtype: "Data"
				}
			);
		}

		let city_name_index = variant_fields.findIndex(
			f => f.fieldname === "county"
		);

		if (city_name_index !== -1) {

			variant_fields.splice(city_name_index + 1, 0,
				{
					label: __("City (In Arabic)"),
					fieldname: "custom_city_arabic",
					fieldtype: "Data"
				}
			);
		}

		let postal_code_index = variant_fields.findIndex(
			f => f.fieldname === "pincode"
		);

		if (postal_code_index !== -1) {

			variant_fields.splice(postal_code_index + 1, 0,
				{
					label: __("Country (In Arabic)"),
					fieldname: "custom_country_arabic",
					fieldtype: "Data"
				}
			);
		}

		return variant_fields;
	}

	render_dialog() {

		super.render_dialog();

		const sync_country = () => {

			let value = this.dialog.get_value("custom_country");

			this.dialog.set_value(
				"country_address",
				value
			);

			// backend field
			this.dialog.doc.country = value;
		};

		// Initial sync for default value
		sync_country();

		// Sync on manual change
		this.dialog.fields_dict.custom_country.df.onchange =
			sync_country;
	}

	// insert() {

	// 	// IMPORTANT FIX
	// 	Object.assign(this.dialog.doc, this.dialog.get_values());

	// 	return super.insert();
	// }
};