frappe.ui.form.on("Customer", {
	refresh(frm) {
		toggle_customer_zatca_requirements(frm);
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

function is_saudi_registered_company(frm) {
	return (
		frm.doc.customer_type === "Company" &&
		(frm.doc.custom_country || "").trim() === "Saudi Arabia" &&
		get_vat_category(frm) !== "Export / Non-Resident"
	);
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
	const sa_registered = is_saudi_registered_company(frm);

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

	if (sa_registered) {
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

	// Company with no country yet / edge cases
	["custom_vat_number", "custom_registration_scheme", "custom_registration_number"].forEach(
		(field) => {
			if (frm.fields_dict[field]) {
				frm.toggle_reqd(field, false);
			}
		}
	);
}
