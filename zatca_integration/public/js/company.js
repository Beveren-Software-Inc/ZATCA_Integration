// TEMPORARY — remove after the SAR QR backfill is done.
const TEMP_SAR_INVOICE = "INV-20134837";

frappe.ui.form.on("Company", {
	refresh(frm) {
		// TEMPORARY — remove after QR currency check
		if (!frm.is_new()) {
			frm.add_custom_button(__("Temp: Generate SAR QR"), () => {
				open_temp_sar_qr_dialog(frm);
			});
		}
	},

	custom_zatca_setup(frm) {
		run_zatca_vat_setup(frm);
	},
});

async function open_temp_sar_qr_dialog(frm) {
	let defaults = {};
	try {
		defaults = await frappe.xcall(
			"zatca_integration.saudi_arabia_electronic_invoicing.temp_qr_generator.get_temp_qr_defaults"
		);
	} catch (e) {
		defaults = {};
	}

	const d = new frappe.ui.Dialog({
		title: __("Temp: Phase-2 QR with SAR amounts"),
		size: "large",
		fields: [
			{
				fieldname: "invoice",
				label: __("Invoice (reference only)"),
				fieldtype: "Data",
				default: defaults.invoice || TEMP_SAR_INVOICE,
				reqd: 1,
			},
			{
				fieldtype: "HTML",
				options: `<p class="text-muted">${__(
					"Only QR tags 4 & 5 (total with VAT / VAT total) are rewritten. Tags 1, 2, 3, 6, 7, 8 and 9 — seller, VAT number, timestamp, invoice hash, signature, public key and certificate signature — are copied byte for byte, so the hash stays the same as the currency QR."
				)}</p>`,
			},
			{ fieldtype: "Section Break", label: __("Original QR of the live invoice") },
			{
				fieldname: "original_qr",
				label: __("Original QR (base64 TLV) or signed XML"),
				fieldtype: "Long Text",
				default: defaults.original_qr || "",
				description: __(
					"Prefilled with the QR embedded in the live /files/INV-20134837.xml. Only tags 4 & 5 are rewritten — tags 1, 2, 3, 6, 7, 8 and 9 are kept byte for byte, so paste a different payload only to override it."
				),
			},
			{ fieldtype: "Section Break", label: __("Amounts in SAR (tags 4 & 5)") },
			{
				fieldname: "sar_total",
				label: __("SAR Total — base_grand_total (QR Tag 4)"),
				fieldtype: "Data",
				default: defaults.sar_total || "164316.87",
				reqd: 1,
			},
			{
				fieldname: "sar_vat",
				label: __("SAR VAT — base_total_taxes_and_charges (QR Tag 5)"),
				fieldtype: "Data",
				default: defaults.sar_vat || "0.00",
				reqd: 1,
			},
			{
				fieldtype: "HTML",
				options: `<p class="text-muted">${__(
					"Reference for INV-20134837"
				)}: USD ${defaults.usd_total || "44052.78"} → SAR ${
					defaults.sar_total || "164316.87"
				} &nbsp;|&nbsp; ${__("QR hash (tag 6)")}: ${frappe.utils.escape_html(
					defaults.qr_hash || ""
				)}</p>`,
			},
			{ fieldtype: "Section Break", label: __("Result") },
			{ fieldname: "result_html", fieldtype: "HTML" },
		],
		primary_action_label: __("Generate QR"),
		primary_action(values) {
			if (!values.original_qr || !String(values.original_qr).trim()) {
				frappe.msgprint({
					title: __("Original QR is required"),
					indicator: "orange",
					message: __(
						"Paste INV-20134837's original QR first.<br><br>On live, open the invoice's <b>custom_invoice_xml</b> (<b>/files/INV-20134837.xml</b>) and copy either:<br>• the text inside the QR <b>&lt;cbc:EmbeddedDocumentBinaryObject&gt;</b>, or<br>• the entire XML file content.<br><br>The QR is needed because only tags 4 &amp; 5 (the amounts) may change — the hash, signature and certificate must stay exactly as ZATCA signed them."
					),
				});
				return;
			}
			generate_temp_sar_qr(d, frm, values);
		},
	});
	d.show();
}


function generate_temp_sar_qr(d, frm, values) {
	frappe.call({
		method:
			"zatca_integration.saudi_arabia_electronic_invoicing.temp_qr_generator.generate_temp_invoice_qr",
		args: {
			company: frm.doc.name,
			invoice: values.invoice,
			original_qr: values.original_qr,
			sar_total: values.sar_total,
			sar_vat: values.sar_vat,
		},
		freeze: true,
		freeze_message: __("Generating QR…"),
		callback(r) {
			if (!r.message) {
				return;
			}
			render_temp_qr_result(d, r.message);
			frappe.show_alert({
				message: r.message.only_amounts_changed
					? __("QR rebuilt — only tags 4 & 5 (amounts) changed")
					: __("QR rebuilt — check the changed tags"),
				indicator: r.message.only_amounts_changed ? "green" : "orange",
			});
		},
	});
}

function render_temp_qr_result(d, m) {
	const file_name = `${m.invoice}-QR-SAR-${m.sar_total}.png`;
	const changed_tags = (m.changed_tags || []).join(", ");
	const tags_note = m.only_amounts_changed
		? `<p class="text-success">${__("Only tags 4 & 5 changed — hash and signature untouched")}</p>`
		: `<p class="text-danger">${__("Changed tags")}: ${frappe.utils.escape_html(changed_tags)}</p>`;
	const preserved_note = m.preserved_tags_ok
		? `<p class="text-success">${__(
				"Tags 1, 2, 3, 6, 7, 8, 9 are byte-identical to the original QR"
			)}</p>`
		: `<p class="text-danger">${__("Some preserved tags differ from the original QR")}</p>`;
	const hash_note = m.hash_matches_invoice
		? `<p class="text-success">${__("QR tag 6 matches INV-20134837 hash")}</p>`
		: `<p class="text-warning">${__("QR tag 6 does not match INV-20134837 hash")}: ${frappe.utils.escape_html(
				m.hash || ""
			)}</p>`;

	d.get_field("result_html").$wrapper.html(`
		<div style="text-align:center;margin-top:12px;">
			<img src="${m.image_data_url}" style="max-width:280px;border:1px solid #ddd;padding:8px;"/>
			<p><b>${__("QR Tag 4 (total)")}:</b> ${m.original_total} → <b>${m.sar_total}</b> SAR &nbsp;|&nbsp;
			<b>${__("QR Tag 5 (VAT)")}:</b> ${m.original_vat} → <b>${m.sar_vat}</b> SAR</p>
			<p class="text-muted">${__("Hash (QR Tag 6)")}: ${frappe.utils.escape_html(
				m.hash || ""
			)}</p>
			${tags_note}
			${preserved_note}
			${hash_note}
			<p style="margin-top:12px;">
				<button class="btn btn-primary btn-sm" id="temp-qr-download-btn">
					${__("Download QR PNG")}
				</button>
				<a class="btn btn-default btn-sm" href="${m.file_url}" target="_blank" style="margin-left:8px;">
					${__("Open in browser")}
				</a>
			</p>
			<details style="text-align:left;margin-top:8px;">
				<summary>${__("QR Base64 payload")}</summary>
				<code style="word-break:break-all;font-size:11px;">${frappe.utils.escape_html(
					m.qr_base64
				)}</code>
			</details>
		</div>
	`);

	d.get_field("result_html")
		.$wrapper.find("#temp-qr-download-btn")
		.on("click", () => {
			const link = document.createElement("a");
			link.href = m.image_data_url;
			link.download = file_name;
			document.body.appendChild(link);
			link.click();
			document.body.removeChild(link);
		});
}

async function run_zatca_vat_setup(frm) {
	if (frm.is_new()) {
		frappe.msgprint({
			title: __("Save Required"),
			message: __("Please save the company before running ZATCA setup."),
			indicator: "orange",
		});
		return;
	}

	if (frm.doc.country !== "Saudi Arabia") {
		frappe.msgprint({
			title: __("Not Applicable"),
			message: __("ZATCA VAT setup is only available for companies in Saudi Arabia."),
			indicator: "orange",
		});
		return;
	}

	const already_done = cint(frm.doc.custom_zatca_vat_setup_done);
	if (already_done) {
		frappe.confirm(
			__(
				"ZATCA VAT setup was already completed for this company. Run again to create any missing items?"
			),
			() => start_zatca_vat_setup(frm, 1),
			() => {}
		);
		return;
	}

	start_zatca_vat_setup(frm, 0);
}

async function start_zatca_vat_setup(frm, force) {
	let steps;
	try {
		steps = await frappe.xcall(
			"zatca_integration.saudi_arabia_electronic_invoicing.vat_setup.get_ksa_vat_setup_steps"
		);
	} catch (e) {
		return;
	}

	const dialog = build_progress_dialog(steps);
	dialog.show();

	frm.dashboard.set_headline_alert(
		`<div class="form-message blue"><strong>${__("ZATCA Setup")}</strong>: ${__(
			"Running…"
		)}</div>`
	);

	for (let i = 0; i < steps.length; i++) {
		const step = steps[i];
		set_step_state(dialog, step.name, "running");
		frappe.show_progress(__("ZATCA Setup"), i + 1, steps.length, __(step.label));

		try {
			const result = await frappe.xcall(
				"zatca_integration.saudi_arabia_electronic_invoicing.vat_setup.run_ksa_vat_setup_step",
				{
					company: frm.doc.name,
					step: step.name,
					force: force,
				}
			);

			if (result && result.skipped && result.reason === "already_done") {
				set_step_state(dialog, step.name, "skipped", result.message);
				finish_setup_dialog(dialog, frm, "blue", result.message || __("Setup already completed."));
				return;
			}

			set_step_state(dialog, step.name, "done", result && result.message);
		} catch (e) {
			set_step_state(dialog, step.name, "failed", e.message || __("Failed"));
			finish_setup_dialog(dialog, frm, "red", __("ZATCA setup failed. Check the Error Log."));
			return;
		}
	}

	finish_setup_dialog(
		dialog,
		frm,
		"green",
		__("KSA VAT accounts, tax templates, categories, and tax rules are configured.")
	);
	frm.reload_doc();
}

function finish_setup_dialog(dialog, frm, indicator, message) {
	frappe.hide_progress();
	dialog._can_close = true;
	dialog.set_secondary_action_label(__("Close"));
	dialog.$wrapper.find(".modal-header .btn-modal-close").show();

	const headline_color = indicator === "green" ? "green" : indicator === "red" ? "red" : "blue";
	const headline_label =
		indicator === "green" ? __("Completed") : indicator === "red" ? __("Failed") : __("Skipped");
	frm.dashboard.set_headline_alert(
		`<div class="form-message ${headline_color}"><strong>${__("ZATCA Setup")}</strong>: ${headline_label}</div>`
	);
	frappe.show_alert({ message: message, indicator: indicator });
}

function build_progress_dialog(steps) {
	const rows = steps
		.map(
			(step) => `
			<div class="zatca-setup-step" data-step="${frappe.utils.escape_html(step.name)}"
				style="display:flex;align-items:flex-start;gap:10px;padding:8px 0;border-bottom:1px solid var(--border-color);">
				<span class="zatca-setup-indicator" style="min-width:18px;margin-top:2px;font-weight:600;">○</span>
				<div style="flex:1;">
					<div class="zatca-setup-label" style="font-weight:500;">${frappe.utils.escape_html(__(step.label))}</div>
					<div class="zatca-setup-detail text-muted small" style="margin-top:2px;"></div>
				</div>
			</div>`
		)
		.join("");

	const dialog = new frappe.ui.Dialog({
		title: __("ZATCA VAT Setup"),
		size: "large",
		static: true,
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "progress",
				options: `<div class="zatca-setup-progress">${rows}</div>`,
			},
		],
		secondary_action_label: __("Please wait…"),
		secondary_action() {
			if (dialog._can_close) {
				dialog.hide();
			}
		},
	});

	dialog._can_close = false;
	dialog.$wrapper.find(".modal-header .btn-modal-close").hide();
	return dialog;
}

function set_step_state(dialog, step_name, state, detail) {
	const $row = dialog.$wrapper.find(`.zatca-setup-step[data-step="${step_name}"]`);
	if (!$row.length) {
		return;
	}

	const $indicator = $row.find(".zatca-setup-indicator");
	const $detail = $row.find(".zatca-setup-detail");

	const styles = {
		pending: { text: "○", color: "var(--text-muted)" },
		running: { text: "●", color: "var(--blue-500)" },
		done: { text: "✓", color: "var(--green-500)" },
		skipped: { text: "–", color: "var(--text-muted)" },
		failed: { text: "✕", color: "var(--red-500)" },
	};
	const style = styles[state] || styles.pending;

	$indicator.text(style.text).css("color", style.color);
	if (detail) {
		$detail.text(detail);
	} else if (state === "running") {
		$detail.text(__("Creating…"));
	} else if (state === "done") {
		$detail.text(__("Done"));
	}
}
