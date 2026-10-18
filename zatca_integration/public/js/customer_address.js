frappe.provide("frappe.ui.form");

// Saudi National Address fields on the shortcut modal are mandatory only when
// Customer Country is Saudi Arabia. Read the field on screen: the hidden
// `country_address` mirror keeps the site default (Saudi Arabia) and would
// keep these fields required after the user picks another country.
const ZATCA_SAUDI_ADDRESS_FIELDS = [
	"address_line1",
	"address_line2",
	"pincode",
	"city",
	"county",
];

// The country the user sees. Link get_value() keeps returning the previous
// value (often the Saudi Arabia default) after the input has changed.
function zatca_shortcut_selected_country(dialog) {
	const field = dialog && dialog.fields_dict && dialog.fields_dict.custom_country;
	if (!field) {
		return "";
	}
	if (field.$input) {
		return String(field.$input.val() || "").trim();
	}
	return String((dialog.doc && dialog.doc.custom_country) || "").trim();
}

function zatca_apply_shortcut_address_requirements(dialog) {
	const country = zatca_shortcut_selected_country(dialog);
	const saudi = country.toLowerCase() === "saudi arabia";

	if (dialog.doc) {
		dialog.doc.country_address = country;
		dialog.doc.country = country;
	}

	ZATCA_SAUDI_ADDRESS_FIELDS.forEach((fieldname) => {
		const field = dialog.fields_dict[fieldname];
		if (!field) {
			return;
		}
		// Drop the dependency so a later refresh cannot turn these back on
		// from the hidden country_address value.
		field.df.mandatory_depends_on = "";
		field.df.reqd = saudi ? 1 : 0;
		field.set_required && field.set_required();
		field.set_bold && field.set_bold();
		if (!saudi && field.$wrapper) {
			field.$wrapper.removeClass("has-error has-error-mandatory");
		}
	});
}

// Ask for the country as soon as any address detail is entered, so the Saudi
// Arabia rule can be evaluated.
const ZATCA_ADDRESS_COUNTRY_MANDATORY_DEPENDS_ON =
	"eval:doc.city || doc.address_line1 || doc.address_line2 || doc.pincode || doc.county";

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

		// Change label
		let city_field = variant_fields.find(
			f => f.fieldname === "city"
		);

		if (city_field) {
			city_field.label = __("District Name");
			city_field.mandatory_depends_on = "";
		}

		let address_line1 = variant_fields.find(
			f => f.fieldname === "address_line1"
		);

		if (address_line1) {
			address_line1.label = __("Street Name");
			address_line1.mandatory_depends_on = "";
		}

		let address_line2 = variant_fields.find(
			f => f.fieldname === "address_line2"
		);

		if (address_line2) {
			address_line2.label = __("Building Number");
			address_line2.placeholder = __("Must be four number for KSA");
			address_line2.mandatory_depends_on = "";
		}

		let postal_code = variant_fields.find(
			f => f.fieldname === "pincode"
		);

		if (postal_code) {
			postal_code.label = __("Postal Code");
			postal_code.mandatory_depends_on = "";
		}

		if (city_index !== -1) {

			variant_fields.splice(city_index + 1, 0,
				{
					label: __("City Name"),
					fieldname: "county",
					fieldtype: "Data",
					mandatory_depends_on: ""
				}
			);
		}

		if (country_field) {
			// `country_address` mirrors `custom_country` and stays hidden; the
			// visible Customer Country field carries the requirement instead, so
			// never leave a hidden required field behind.
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
					fieldname: "custom_street_in_arabic",
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
					fieldname: "custom_district_in_arabic",
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
					fieldname: "custom_city_in_arabic",
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
					fieldname: "custom_country_in_arabic",
					fieldtype: "Data"
				}
			);
		}

		return variant_fields;
	}

	render_dialog() {

		super.render_dialog();

		const apply = () => zatca_apply_shortcut_address_requirements(this.dialog);

		const original_refresh = this.dialog.refresh_dependency.bind(this.dialog);
		this.dialog.refresh_dependency = () => {
			original_refresh();
			apply();
		};

		const country_selector = this.dialog.fields_dict.custom_country;

		if (country_selector) {
			country_selector.df.mandatory_depends_on =
				ZATCA_ADDRESS_COUNTRY_MANDATORY_DEPENDS_ON;

			country_selector.df.onchange = apply;
			if (country_selector.$input) {
				country_selector.$input.on("change awesomplete-selectcomplete input", apply);
			}
		}

		apply();
		// Defaults land asynchronously after the dialog opens.
		setTimeout(apply, 0);
		setTimeout(apply, 300);
	}

	// insert() {

	// 	// IMPORTANT FIX
	// 	Object.assign(this.dialog.doc, this.dialog.get_values());

	// 	return super.insert();
	// }
};
