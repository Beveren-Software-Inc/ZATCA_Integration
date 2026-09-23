frappe.ui.form.on("Address", {
	setup(frm) {
		// Keep last auto-filled values so we can refresh Arabic when English changes
		frm._zatca_arabic_autofilled = frm._zatca_arabic_autofilled || {};
		frm._zatca_party_context = frm._zatca_party_context || {};
	},

	refresh(frm) {
		prefill_tax_category_from_party(frm);
		frm.add_custom_button(__("Translate Arabic Fields"), () => {
			translate_all_arabic_fields(frm, true);
		});
	},

	country(frm) {
		toggle_saudi_address_requirements(frm);
		autofill_arabic(frm, "country", "custom_country_in_arabic");
	},

	tax_category(frm) {
		toggle_saudi_address_requirements(frm);
	},

	custom_vat_category(frm) {
		toggle_saudi_address_requirements(frm);
	},

	address_line1(frm) {
		autofill_arabic(frm, "address_line1", "custom_street_in_arabic");
	},

	city(frm) {
		autofill_arabic(frm, "city", "custom_district_in_arabic");
	},

	county(frm) {
		autofill_arabic(frm, "county", "custom_city_in_arabic");
	},

	links_add(frm) {
		prefill_tax_category_from_party(frm, true);
	},
});

frappe.ui.form.on("Dynamic Link", {
	link_name(frm) {
		prefill_tax_category_from_party(frm, true);
	},
	link_doctype(frm) {
		prefill_tax_category_from_party(frm, true);
	},
});

const SA_ADDRESS_FIELDS = [
	"address_line1",
	"address_line2",
	"city",
	"county",
	"pincode",
	"custom_additional_no",
];

// Keep in sync with zatca_integration/common_util.py:
// - custom_vat_category select: Registered / Unregistered / Overseas / Government / Exempt
// - tax_category link: B2B / B2C / B2G / Export / Non-Resident / Exempt Entity
function normalize_vat_category(value) {
	return String(value || "")
		.trim()
		.replace(/\s+/g, " ")
		.toLowerCase();
}

// VAT-registered buyers (national address required for Individuals)
const ZATCA_REGISTERED_VAT_CATEGORIES = ["Registered", "B2B", "B2G", "Tax Deductors", "Tax Deductor"];

// Overseas / export-style buyers: full Saudi national address not required
const ZATCA_EXPORT_VAT_CATEGORIES = [
	"Overseas",
	"Oversees",
	"Deemed Export",
	"Export / Non-Resident",
	"Export",
];

function is_registered_vat_category(value) {
	const category = normalize_vat_category(value);
	return ZATCA_REGISTERED_VAT_CATEGORIES.some(
		(name) => normalize_vat_category(name) === category
	);
}

function is_export_vat_category(value) {
	const category = normalize_vat_category(value);
	return ZATCA_EXPORT_VAT_CATEGORIES.some((name) => normalize_vat_category(name) === category);
}

function get_linked_party(frm) {
	const link = (frm.doc.links || []).find(
		(row) => ["Customer", "Supplier"].includes(row.link_doctype) && row.link_name
	);
	return link || null;
}

function get_vat_category(frm) {
	return (frm.doc.tax_category || frm.doc.custom_vat_category || "").trim();
}

function requires_saudi_national_address(frm) {
	if ((frm.doc.country || "").trim() !== "Saudi Arabia") {
		return false;
	}

	const vat_category = get_vat_category(frm);
	if (is_export_vat_category(vat_category)) {
		return false;
	}

	const entity_type = (frm._zatca_party_context || {}).entity_type;
	if (entity_type === "Individual") {
		return is_registered_vat_category(vat_category);
	}
	if (entity_type === "Company") {
		return true;
	}
	return is_registered_vat_category(vat_category);
}

function toggle_saudi_address_requirements(frm) {
	const entity_type = (frm._zatca_party_context || {}).entity_type;
	const is_individual = entity_type === "Individual";
	const national_required = requires_saudi_national_address(frm);

	// Individuals: only Country is mandatory (unless Registered + SA)
	if (frm.fields_dict.country) {
		frm.toggle_reqd("country", true);
	}

	SA_ADDRESS_FIELDS.forEach((field) => {
		if (!frm.fields_dict[field]) {
			return;
		}
		if (is_individual && !national_required) {
			frm.toggle_reqd(field, false);
			return;
		}
		frm.toggle_reqd(field, national_required && field !== "custom_additional_no");
	});

	if (frm.fields_dict.custom_national_address) {
		frm.toggle_reqd("custom_national_address", false);
	}
}

function translate_all_arabic_fields(frm, force) {
	const pairs = [
		["address_line1", "custom_street_in_arabic"],
		["city", "custom_district_in_arabic"],
		["county", "custom_city_in_arabic"],
		["country", "custom_country_in_arabic"],
	];
	pairs.forEach(([source, target]) => autofill_arabic(frm, source, target, force));
}

function autofill_arabic(frm, source_field, target_field, force = false) {
	if (!frm.fields_dict[target_field]) {
		return;
	}

	const english = (frm.doc[source_field] || "").trim();
	if (!english) {
		return;
	}

	const arabic = (frm.doc[target_field] || "").trim();
	const previously_autofilled = (frm._zatca_arabic_autofilled || {})[target_field];

	// Do not overwrite a manual Arabic value unless user forced translate
	// or the current Arabic value was from our previous autofill for an older English value
	if (arabic && !force && arabic !== previously_autofilled) {
		return;
	}

	frappe.call({
		method: "zatca_integration.overrides.address.translate_text_to_arabic",
		args: { text: english, field: source_field },
		freeze: false,
		callback(r) {
			const translated = (r.message || "").trim();
			if (!translated) {
				frappe.show_alert({
					message: __("Could not translate {0} to Arabic. You can enter it manually.", [
						__(frm.fields_dict[source_field].df.label || source_field),
					]),
					indicator: "orange",
				});
				return;
			}
			// Skip if user typed Arabic meanwhile
			const current = (frm.doc[target_field] || "").trim();
			if (current && !force && current !== previously_autofilled) {
				return;
			}
			frm.set_value(target_field, translated);
			frm._zatca_arabic_autofilled[target_field] = translated;
		},
		error() {
			frappe.show_alert({
				message: __("Arabic translation request failed."),
				indicator: "red",
			});
		},
	});
}

function prefill_tax_category_from_party(frm, force = false) {
	const link = get_linked_party(frm);
	if (!link) {
		return;
	}

	frappe.call({
		method: "zatca_integration.overrides.address.get_address_party_context",
		args: {
			link_doctype: link.link_doctype,
			link_name: link.link_name,
		},
		callback(r) {
			const ctx = r.message || {};
			frm._zatca_party_context = ctx;

			if (ctx.tax_category && (force || !frm.doc.tax_category)) {
				frm.set_value("tax_category", ctx.tax_category);
			}
			if (
				frm.fields_dict.custom_vat_category &&
				ctx.custom_vat_category &&
				(force || !frm.doc.custom_vat_category)
			) {
				frm.set_value("custom_vat_category", ctx.custom_vat_category);
			}

			toggle_saudi_address_requirements(frm);
		},
	});
}
