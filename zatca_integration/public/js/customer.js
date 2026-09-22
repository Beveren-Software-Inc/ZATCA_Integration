frappe.ui.form.on("Customer", {
	refresh(frm) {
		// Always re-read the switches so a settings change is picked up on next open
		zatca_vat_settings = null;
		toggle_customer_zatca_requirements(frm);
		load_zatca_vat_settings(frm);
		set_vat_number_input_limits(frm);
	},

	before_save(frm) {
		warn_overseas_missing_registration(frm);
	},

	customer_type(frm) {
		toggle_customer_zatca_requirements(frm);
	},

	custom_country(frm) {
		toggle_customer_zatca_requirements(frm);
		warn_overseas_missing_registration(frm);
	},

	tax_category(frm) {
		toggle_customer_zatca_requirements(frm);
		warn_overseas_missing_registration(frm);
		if (!frm.doc.__islocal) {
			frappe.show_alert({
				message: __("Linked addresses will update VAT Category on save."),
				indicator: "blue",
			});
		}
	},

	custom_vat_category(frm) {
		toggle_customer_zatca_requirements(frm);
		warn_overseas_missing_registration(frm);
	},

	custom_vat_number(frm) {
		toggle_customer_zatca_requirements(frm);
		validate_customer_vat_number_input(frm);
	},

	custom_registration_scheme(frm) {
		toggle_customer_zatca_requirements(frm);
	},

	custom_registration_number(frm) {
		toggle_customer_zatca_requirements(frm);
	},
});

function get_vat_category(frm) {
	return (frm.doc.tax_category || frm.doc.custom_vat_category || "").trim();
}

function is_overseas(frm) {
	const country = (frm.doc.custom_country || "").trim();
	const vat_category = get_vat_category(frm);
	return (country && country !== "Saudi Arabia") || vat_category === "Export / Non-Resident";
}

// Keep in sync with zatca_integration/common_util.py REGISTERED_VAT_CATEGORIES
const ZATCA_REGISTERED_VAT_CATEGORIES = [
	"Registered",
	"Registered Regular",
	"Registered Composition",
	"B2B",
	"B2G",
	"Tax Deductors",
	"Tax Deductor",
	"Tax Collector",
	"SEZ",
	"UIN Holders",
	"Input Service Distributor",
];

let zatca_vat_settings = null;
let zatca_vat_settings_request = null;

// Switches live on "Zatca Settings":
// - validate_vat_no_against_all_company: every Company customer needs a VAT No
// - validate_vat_no_against_registered_company: only VAT-registered companies do
function load_zatca_vat_settings(frm) {
	return fetch_zatca_vat_settings().then(() => {
		toggle_customer_zatca_requirements(frm);
		return zatca_vat_settings;
	});
}

function fetch_zatca_vat_settings() {
	if (zatca_vat_settings) {
		return Promise.resolve(zatca_vat_settings);
	}
	if (!zatca_vat_settings_request) {
		zatca_vat_settings_request = frappe
			.xcall("zatca_integration.overrides.customer.get_customer_vat_validation_settings")
			.then((settings) => {
				zatca_vat_settings = settings || {};
				return zatca_vat_settings;
			})
			.catch(() => {
				zatca_vat_settings = {};
				return zatca_vat_settings;
			})
			.then((settings) => {
				zatca_vat_settings_request = null;
				return settings;
			});
	}
	return zatca_vat_settings_request;
}

function is_vat_number_validation_enabled(frm) {
	const settings = zatca_vat_settings || {};
	if (Number(settings.validate_vat_no_against_all_company)) {
		return true;
	}
	if (Number(settings.validate_vat_no_against_registered_company)) {
		return ZATCA_REGISTERED_VAT_CATEGORIES.includes(get_vat_category(frm));
	}
	return false;
}

function is_valid_ksa_vat_number(value) {
	const vat = (value || "").trim();
	if (!vat) {
		return true;
	}
	return /^\d{15}$/.test(vat) && vat.startsWith("3");
}

function set_vat_number_input_limits(frm) {
	if (!frm.fields_dict.custom_vat_number) {
		return;
	}
	frm.set_df_property(
		"custom_vat_number",
		"description",
		__("Exactly 15 digits, starting with 3")
	);
	const $input = frm.get_field("custom_vat_number").$input;
	if ($input && $input.length) {
		$input.attr("maxlength", 15);
	}
}

function validate_customer_vat_number_input(frm) {
	const country = (frm.doc.custom_country || "").trim();
	const vat = (frm.doc.custom_vat_number || "").trim();
	if (!vat || country !== "Saudi Arabia") {
		return;
	}
	if (!is_valid_ksa_vat_number(vat)) {
		frappe.msgprint({
			title: __("Invalid VAT Number"),
			indicator: "red",
			message: __("VAT Number must be exactly 15 digits and start with 3."),
		});
	}
}

function warn_overseas_missing_registration(frm) {
	if (frm.doc.customer_type !== "Company" || !is_overseas(frm)) {
		return;
	}
	const registration_number = (frm.doc.custom_registration_number || "").trim();
	if (registration_number) {
		return;
	}
	frappe.show_alert({
		message: __(
			"Overseas / Export company: Registration Number is recommended. You can still save without it."
		),
		indicator: "orange",
	});
}

function toggle_customer_zatca_requirements(frm) {
	const is_company = frm.doc.customer_type === "Company";
	const overseas = is_overseas(frm);

	const has_vat = !!(frm.doc.custom_vat_number || frm.doc.tax_id);
	const has_reg_scheme = !!(frm.doc.custom_registration_scheme || "").trim();
	const has_reg_number = !!(frm.doc.custom_registration_number || "").trim();
	const has_registration = has_reg_scheme && has_reg_number;

	// Individuals: nothing ZATCA-mandatory
	if (!is_company) {
		[
			"custom_country",
			"custom_vat_number",
			"custom_registration_scheme",
			"custom_registration_number",
			"tax_id",
		].forEach((field) => {
			if (frm.fields_dict[field]) {
				frm.toggle_reqd(field, false);
			}
		});
		return;
	}

	// Company: country always required
	if (frm.fields_dict.custom_country) {
		frm.toggle_reqd("custom_country", true);
	}

	if (overseas) {
		// Overseas / Export: VAT not mandatory; registration recommended only (server warns)
		if (frm.fields_dict.custom_vat_number) {
			frm.toggle_reqd("custom_vat_number", false);
		}
		if (frm.fields_dict.custom_registration_scheme) {
			frm.toggle_reqd("custom_registration_scheme", false);
		}
		if (frm.fields_dict.custom_registration_number) {
			frm.toggle_reqd("custom_registration_number", false);
		}
		return;
	}

	// VAT Number is mandatory only when switched on in "Zatca Settings".
	// Wait for the switches before deciding, otherwise leave the current state untouched.
	if (!zatca_vat_settings) {
		load_zatca_vat_settings(frm);
		return;
	}

	if (is_vat_number_validation_enabled(frm)) {
		// Need VAT OR (scheme + number). Require whichever side is still missing.
		if (frm.fields_dict.custom_vat_number) {
			frm.toggle_reqd("custom_vat_number", !has_registration);
		}
		if (frm.fields_dict.custom_registration_scheme) {
			frm.toggle_reqd("custom_registration_scheme", !has_vat);
		}
		if (frm.fields_dict.custom_registration_number) {
			frm.toggle_reqd("custom_registration_number", !has_vat && has_reg_scheme);
		}
		return;
	}

	// Validation switched off: VAT Number / registration details stay optional
	["custom_vat_number", "custom_registration_scheme", "custom_registration_number"].forEach(
		(field) => {
			if (frm.fields_dict[field]) {
				frm.toggle_reqd(field, false);
			}
		}
	);
}
