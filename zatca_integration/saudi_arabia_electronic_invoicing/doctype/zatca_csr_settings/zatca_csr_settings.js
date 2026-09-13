frappe.ui.form.on("Zatca CSR Settings", {
	refresh: function (frm) {
		if (!frm.is_new() && frm.doc.zatca_phase === "ZATCA Phase 2") {
			if (!frm.doc.csr_generated) {
				frm.add_custom_button(__("Generate CSR"), function () {
					frappe.call({
						method: "zatca_integration.saudi_arabia_electronic_invoicing.utils.generate_csr",
						args: {
							doc_name: frm.doc.name,
						},
						callback: function (r) {
							frappe.hide_progress();
							if (!r.exc) {
								frappe.show_alert({
									message: __("CSR Generated Successfully!"),
									indicator: "green",
								});
								frm.reload_doc(); // Reload so button disappears
							} else {
								frappe.show_alert({
									message: __("CSR Generation Failed!"),
									indicator: "red",
								});
							}
						},
					});
				});
			}
		}
		make_fields_read_only(frm);
		set_vat_identifier_input_limits(frm);
	},

	csrorganizationidentifier: function (frm) {
		validate_csr_vat_number_input(frm);
	},
});

function make_fields_read_only(frm) {
	if (frm.doc.csr_generated) {
		frm.fields.forEach(function (field) {
			frm.set_df_property(field.df.fieldname, "read_only", 1);
		});

		frm.disable_save();
	}
}

function set_vat_identifier_input_limits(frm) {
	if (!frm.fields_dict.csrorganizationidentifier) {
		return;
	}
	frm.set_df_property(
		"csrorganizationidentifier",
		"description",
		__("Exactly 15 digits, starting with 3")
	);
	const $input = frm.get_field("csrorganizationidentifier").$input;
	if ($input && $input.length) {
		$input.attr("maxlength", 15);
	}
}

function validate_csr_vat_number_input(frm) {
	const vat = (frm.doc.csrorganizationidentifier || "").trim();
	if (!vat) {
		return;
	}
	if (!/^\d{15}$/.test(vat) || !vat.startsWith("3")) {
		frappe.msgprint({
			title: __("Invalid VAT Number"),
			indicator: "red",
			message: __(
				"VAT or Group VAT Registration Number must be exactly 15 digits and start with 3."
			),
		});
	}
}
