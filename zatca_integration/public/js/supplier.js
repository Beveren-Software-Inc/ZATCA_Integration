frappe.ui.form.on("Supplier", {
	refresh(frm) {
		toggle_supplier_tax_id_requirement(frm);
	},

	supplier_type(frm) {
		toggle_supplier_tax_id_requirement(frm);
	},

	country(frm) {
		toggle_supplier_tax_id_requirement(frm);
		validate_supplier_tax_id_input(frm);
	},

	tax_category(frm) {
		toggle_supplier_tax_id_requirement(frm);
		if (frm.doc.__islocal) {
			return;
		}
		frappe.show_alert({
			message: __("Linked addresses will update VAT Category on save."),
			indicator: "blue",
		});
	},

	custom_vat_category(frm) {
		toggle_supplier_tax_id_requirement(frm);
	},

	tax_id(frm) {
		validate_supplier_tax_id_input(frm);
	},
});

function get_vat_category(frm) {
	return (frm.doc.tax_category || frm.doc.custom_vat_category || "").trim();
}

// Keep in sync with zatca_integration/common_util.py:
// - custom_vat_category select: Registered / Unregistered / Overseas / Government / Exempt
// - tax_category link: B2B / B2C / B2G / Export / Non-Resident / Exempt Entity
function normalize_vat_category(value) {
	return String(value || "")
		.trim()
		.replace(/\s+/g, " ")
		.toLowerCase();
}

const ZATCA_REGISTERED_VAT_CATEGORIES = ["Registered", "B2B", "B2G", "Tax Deductors", "Tax Deductor"];

function is_registered_vat_category(value) {
	const category = normalize_vat_category(value);
	return ZATCA_REGISTERED_VAT_CATEGORIES.some(
		(name) => normalize_vat_category(name) === category
	);
}

// Mirrors zatca_integration.overrides.supplier.validate: a VAT registered
// supplier must carry a Tax ID (VAT Number); every other category is optional.
function toggle_supplier_tax_id_requirement(frm) {
	if (!frm.fields_dict.tax_id) {
		return;
	}
	frm.toggle_reqd("tax_id", is_registered_vat_category(get_vat_category(frm)));
}

function validate_supplier_tax_id_input(frm) {
	const country = (frm.doc.country || "").trim();
	const tax_id = (frm.doc.tax_id || "").trim();
	if (!tax_id || country.toLowerCase() !== "saudi arabia") {
		return;
	}
	if (!/^\d{15}$/.test(tax_id) || !tax_id.startsWith("3")) {
		frappe.msgprint({
			title: __("Invalid Tax ID"),
			indicator: "red",
			message: __("Tax ID (VAT Number) must be exactly 15 digits and start with 3."),
		});
	}
}
