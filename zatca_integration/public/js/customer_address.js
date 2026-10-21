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
	"eval:doc.city || doc.address_line1 || doc.address_line2 || doc.pincode || doc._pincode || doc.county";

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
			// A mandatory_depends_on on this Link makes Frappe refresh it and
			// restore Saudi Arabia while the user is editing.
			country_selector.df.mandatory_depends_on = "";
			country_selector.df.read_only = 0;
			country_selector.df.onchange = apply;
			if (country_selector.$input) {
				country_selector.$input.on("change awesomplete-selectcomplete input", apply);
			}
		}
		zatca_hide_duplicate_address_country(this.dialog);

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

// ---------------------------------------------------------------------------
// Address quick-entry dialogs (Address / Customer / Supplier)
//
// ERPNext quick-entry dialogs do not run public/js/address.js: they render
// their own field list. The Saudi national-address fields must therefore be
// made mandatory here as well, based on the Country selected *inside* the
// dialog. The wrapper also fills gaps in the ERPNext / India Compliance field
// lists (most importantly county -> "City Name") so the values reach the
// Address instead of being dropped.
// ---------------------------------------------------------------------------

const ZATCA_ADDRESS_QUICK_ENTRY_LABELS = {
	address_line1: __("Street Name"),
	address_line2: __("Building Number"),
	city: __("Subdivision Name"),
	county: __("City Name"),
	pincode: __("Postal Code"),
};

// India Compliance suffixes pincode with "_" so Layout does not override it.
const ZATCA_ADDRESS_QUICK_ENTRY_ALIASES = {
	pincode: ["pincode", "_pincode"],
};

const ZATCA_ADDRESS_QUICK_ENTRY_COUNTRY_FIELDS = [
	// ZATCA Customer shortcut
	"custom_country",
	// ContactAddressQuickEntryForm (ERPNext Customer / Supplier)
	"country_address",
	// AddressQuickEntryForm / India Compliance party shortcut
	"country",
];

function zatca_quick_entry_field_names(fieldname) {
	return ZATCA_ADDRESS_QUICK_ENTRY_ALIASES[fieldname] || [fieldname];
}

function zatca_quick_entry_field_exists(fields, fieldname) {
	return zatca_quick_entry_field_names(fieldname).some((name) =>
		(fields || []).some((df) => df.fieldname === name)
	);
}

function zatca_quick_entry_address_label(fieldname) {
	// India Compliance renders pincode as `_pincode`.
	const canonical = fieldname === "_pincode" ? "pincode" : fieldname;
	return ZATCA_ADDRESS_QUICK_ENTRY_LABELS[canonical];
}

function zatca_is_india_quick_entry_dependency(condition) {
	return /\bIndia\b/.test(String(condition || ""));
}

function zatca_normalize_quick_entry_address_labels(fields) {
	return fields.map((df) => {
		const label = zatca_quick_entry_address_label(df.fieldname);
		if (!label) {
			return df;
		}

		// QuickEntryForm holds references to frappe.meta fields. Always copy the
		// five national-address fields: the requirement handler writes
		// df.reqd / df.mandatory_depends_on, and mutating the meta objects would
		// leak (for example) "Postal Code is required" into the full Address form.
		const normalized = Object.assign({}, df, { label });

		// ERPNext's ContactAddressQuickEntryForm marks Street/City required once
		// any address detail is present. That would keep them required after the
		// country is switched away from Saudi Arabia. Requirements for these five
		// fields are country-driven here; only India Compliance's pincode rule
		// (and any other explicitly India-based rule) is left to Frappe.
		if (
			normalized.mandatory_depends_on &&
			!zatca_is_india_quick_entry_dependency(normalized.mandatory_depends_on)
		) {
			normalized.mandatory_depends_on = "";
		}

		return normalized;
	});
}

function zatca_make_quick_entry_address_field(fieldname) {
	const meta = frappe.meta.get_docfield("Address", fieldname) || {};
	return {
		fieldname,
		fieldtype: meta.fieldtype || "Data",
		label:
			(meta.label && __(meta.label)) ||
			ZATCA_ADDRESS_QUICK_ENTRY_LABELS[fieldname] ||
			__(fieldname),
		options: meta.options || undefined,
		description: meta.description || undefined,
		// Requirements are country-driven and applied in
		// zatca_apply_quick_entry_address_requirements().
		reqd: 0,
	};
}

function zatca_insert_quick_entry_address_field(fields, fieldname, anchors) {
	if (zatca_quick_entry_field_exists(fields, fieldname)) {
		return;
	}

	const df = zatca_make_quick_entry_address_field(fieldname);
	let index = -1;
	for (const anchor of anchors) {
		index = fields.findIndex((field) => field.fieldname === anchor);
		if (index !== -1) {
			break;
		}
	}

	if (index === -1) {
		fields.push(df);
	} else {
		fields.splice(index + 1, 0, df);
	}
}

function zatca_ensure_quick_entry_address_fields(fields) {
	fields = fields || [];

	// Only touch dialogs that actually collect an address.
	const has_address_field = fields.some((df) =>
		[
			"address_line1",
			"address_line2",
			"city",
			"county",
			"pincode",
			"_pincode",
		].includes(df.fieldname)
	);
	if (!has_address_field) {
		return fields;
	}

	fields = zatca_normalize_quick_entry_address_labels(fields);

	zatca_insert_quick_entry_address_field(fields, "address_line1", [
		"address_type",
		"address_title",
	]);
	zatca_insert_quick_entry_address_field(fields, "address_line2", [
		"address_line1",
	]);
	zatca_insert_quick_entry_address_field(fields, "city", [
		"address_line2",
		"address_line1",
	]);
	zatca_insert_quick_entry_address_field(fields, "county", [
		"city",
		"address_line2",
		"address_line1",
	]);
	zatca_insert_quick_entry_address_field(fields, "pincode", [
		"county",
		"city",
		"address_line2",
		"address_line1",
		"_pincode",
	]);

	return zatca_normalize_quick_entry_address_labels(fields);
}

function zatca_quick_entry_country(dialog) {
	const fields = ZATCA_ADDRESS_QUICK_ENTRY_COUNTRY_FIELDS.map(
		(fieldname) => dialog.fields_dict[fieldname]
	).filter(Boolean);

	if (!fields.length) {
		return null;
	}

	const field =
		fields.find(
			(df) => !df.df.hidden && df.$wrapper && df.$wrapper.is(":visible")
		) ||
		fields.find((df) => !df.df.hidden) ||
		fields[0];

	let value = "";
	if (field.$input && typeof field.$input.val === "function") {
		value = field.$input.val();
	}
	if (!value) {
		value = dialog.doc[field.df.fieldname];
	}

	return {
		field,
		fieldname: field.df.fieldname,
		value: String(value || "").trim(),
	};
}

function zatca_apply_quick_entry_address_requirements(form) {
	const dialog = form.dialog || form;
	if (!dialog || !dialog.fields_dict) {
		return;
	}

	const country = zatca_quick_entry_country(dialog);
	if (!country) {
		return;
	}
	const is_saudi = country.value.toLowerCase() === "saudi arabia";

	// The Customer shortcut shows custom_country, but ERPNext's make_address()
	// and the server-side expressions read country_address.
	if (country.fieldname === "custom_country") {
		dialog.doc.country_address = country.value;
		dialog.doc.country = country.value;
	}

	// Country is required as soon as any address detail is entered.
	// Do not put mandatory_depends_on on the country Link. Frappe refreshes the
	// control to apply it, and that writes the saved value (Saudi Arabia) back
	// into the input, so the user cannot clear or change it.
	if (country.field) {
		country.field.df.mandatory_depends_on = "";
		country.field.df.read_only = 0;
		const address_started = ZATCA_SAUDI_ADDRESS_FIELDS.some((fieldname) =>
			zatca_quick_entry_field_names(fieldname).some((name) => {
				const field = dialog.fields_dict[name];
				if (!field || !field.$input) {
					return false;
				}
				return String(field.$input.val() || "").trim();
			})
		);
		country.field.df.reqd = address_started ? 1 : 0;
		country.field.set_required && country.field.set_required();
	}

	ZATCA_SAUDI_ADDRESS_FIELDS.forEach((fieldname) => {
		zatca_quick_entry_field_names(fieldname).forEach((name) => {
			const field = dialog.fields_dict[name];
			if (!field) {
				return;
			}

			if (is_saudi) {
				// Saudi national address: all five fields are mandatory.
				field.df.reqd = 1;
			} else if (!field.df.mandatory_depends_on) {
				// Outside Saudi Arabia these fields are never globally required.
				// A non-empty mandatory_depends_on (for example India's pincode
				// rule) is left to Frappe's dependency evaluator.
				field.df.reqd = 0;
			}

			field.set_required && field.set_required();
			field.set_bold && field.set_bold();
			if (!is_saudi && field.$wrapper) {
				field.$wrapper.removeClass("has-error has-error-mandatory");
			}
		});
	});
}

function zatca_setup_quick_entry_address_requirements(form) {
	const dialog = form.dialog || form;
	if (!dialog || !dialog.fields_dict) {
		return;
	}

	const apply = () => zatca_apply_quick_entry_address_requirements(form);

	// Re-apply after every dependency pass so a country change cannot leave the
	// old required/optional state behind.
	if (!dialog.__zatca_address_requirements_bound) {
		dialog.__zatca_address_requirements_bound = true;
		const original_refresh = dialog.refresh_dependency;
		if (typeof original_refresh === "function") {
			dialog.refresh_dependency = function () {
				original_refresh.apply(dialog, arguments);
				apply();
			};
		}
	}

	const country = zatca_quick_entry_country(dialog);
	if (country && country.field.$input) {
		country.field.$input.off(".zatcaAddressRequirements");
		country.field.$input.on(
			"change.zatcaAddressRequirements awesomplete-selectcomplete.zatcaAddressRequirements input.zatcaAddressRequirements",
			() => {
				// Refreshing the dialog here reloads the Link from the document
				// and puts Saudi Arabia back as soon as the user deletes it.
				apply();
			}
		);
	}

	zatca_hide_duplicate_address_country(dialog);
	apply();

	// Defaults land asynchronously after the dialog opens.
	setTimeout(() => {
		zatca_hide_duplicate_address_country(dialog);
		apply();
	}, 0);
	setTimeout(() => {
		zatca_hide_duplicate_address_country(dialog);
		apply();
	}, 300);
}

function zatca_drop_duplicate_country_fields(fields, doctype) {
	// Customer Country (`custom_country`) is the only country on the Customer
	// shortcut. ERPNext adds `country_address` and India Compliance adds
	// `country` in the address section. Both are the same value.
	if (doctype !== "Customer") {
		return fields || [];
	}
	return (fields || []).filter(
		(df) => df.fieldname !== "country" && df.fieldname !== "country_address"
	);
}

function zatca_hide_duplicate_address_country(dialog) {
	if (!dialog || !dialog.fields_dict || !dialog.fields_dict.custom_country) {
		return;
	}
	["country", "country_address"].forEach((fieldname) => {
		const extra = dialog.fields_dict[fieldname];
		if (!extra) {
			return;
		}
		extra.df.hidden = 1;
		extra.df.reqd = 0;
		extra.df.mandatory_depends_on = "";
		if (extra.$wrapper) {
			extra.$wrapper.addClass("hide-control").hide();
		}
	});
}

function zatca_wrap_quick_entry_form(form_name) {
	const Base = frappe.ui && frappe.ui.form && frappe.ui.form[form_name];
	// Check for an own property: Customer/Supplier quick entry aliases the same
	// base class, and a subclass must not inherit the wrapped marker.
	if (
		!Base ||
		Object.prototype.hasOwnProperty.call(Base, "ZATCA_ADDRESS_QUICK_ENTRY_WRAPPED")
	) {
		return;
	}

	class ZatcaAddressQuickEntryForm extends Base {
		render_dialog() {
			const result = super.render_dialog();
			const setup = () => zatca_setup_quick_entry_address_requirements(this);
			setup();

			// India Compliance's Address render_dialog is async.
			if (result && typeof result.then === "function") {
				result.then(setup);
			}
			return result;
		}

		get_address_fields() {
			const base = super.get_address_fields;
			return zatca_drop_duplicate_country_fields(
				zatca_ensure_quick_entry_address_fields(base ? base.call(this) : []),
				this.doctype
			);
		}

		get_variant_fields() {
			const base = super.get_variant_fields;
			return zatca_drop_duplicate_country_fields(
				zatca_ensure_quick_entry_address_fields(base ? base.call(this) : []),
				this.doctype
			);
		}

		update_doc() {
			const doc = super.update_doc();
			const selected =
				(this.dialog && this.dialog.get_value("custom_country")) ||
				(doc && doc.custom_country);
			if (selected) {
				doc.country = selected;
				doc.country_address = selected;
			}
			return doc;
		}

		set_meta_and_mandatory_fields() {
			super.set_meta_and_mandatory_fields();
			if (
				this.doctype === "Address" &&
				!super.get_address_fields &&
				!super.get_variant_fields
			) {
				this.docfields = zatca_ensure_quick_entry_address_fields(
					this.docfields
				);
			}
		}
	}

	ZatcaAddressQuickEntryForm.ZATCA_ADDRESS_QUICK_ENTRY_WRAPPED = true;
	frappe.ui.form[form_name] = ZatcaAddressQuickEntryForm;
}

function zatca_install_quick_entry_address_requirements() {
	zatca_wrap_quick_entry_form("AddressQuickEntryForm");
	zatca_wrap_quick_entry_form("CustomerQuickEntryForm");
	zatca_wrap_quick_entry_form("SupplierQuickEntryForm");
}

// ERPNext and India Compliance replace CustomerQuickEntryForm after this file
// runs. Wrap again at the moment the shortcut opens, so the class they left
// in place is the one that drops the extra Country field.
function zatca_wrap_make_quick_entry() {
	const make_quick_entry = frappe.ui && frappe.ui.form && frappe.ui.form.make_quick_entry;
	if (!make_quick_entry || make_quick_entry.__zatca_wrapped) {
		return;
	}
	const wrapped = function () {
		zatca_install_quick_entry_address_requirements();
		return make_quick_entry.apply(this, arguments);
	};
	wrapped.__zatca_wrapped = true;
	frappe.ui.form.make_quick_entry = wrapped;
}

zatca_install_quick_entry_address_requirements();
zatca_wrap_make_quick_entry();
if (document.readyState === "loading") {
	document.addEventListener("DOMContentLoaded", () => {
		zatca_install_quick_entry_address_requirements();
		zatca_wrap_make_quick_entry();
	});
}
