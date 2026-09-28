// TEMPORARY — remove this file (and its entries in hooks.py) once the SAR QR
// backfill is done.
//
// Shared temp-QR dialog used by:
//   * the Company form        → public/js/company.js
//   * the Sales Invoice form  → public/js/sales_invoice.js
//
// It rebuilds a ZATCA Phase-2 QR where only tags 4 & 5 (total with VAT / VAT
// total) carry the SAR amounts. The seller, VAT number, timestamp, invoice hash,
// signature, public key and certificate signature are copied byte for byte from
// the invoice's own currency QR, so the QR stays bound to the invoice ZATCA
// signed. The original QR is resolved by the backend in this order: the payload
// pasted in the dialog, the invoice's ``custom_invoice_xml`` on this site, or the
// baked-in snapshot of a known live invoice.
//
// Everything lives on ``frappe.zatca_temp_qr`` so both forms can share it
// without leaking globals (a page can have both doctypes' scripts loaded).

frappe.provide("frappe.zatca_temp_qr");

frappe.zatca_temp_qr.methods = {
	get_defaults:
		"zatca_integration.saudi_arabia_electronic_invoicing.temp_qr_generator.get_temp_qr_defaults",
	generate:
		"zatca_integration.saudi_arabia_electronic_invoicing.temp_qr_generator.generate_temp_invoice_qr",
	// One-click path: the invoice, its original QR and the SAR amounts are all
	// resolved server-side, so the button has nothing to get wrong.
	quick_generate:
		"zatca_integration.saudi_arabia_electronic_invoicing.temp_qr_generator.generate_default_temp_qr",
};

frappe.zatca_temp_qr.get_defaults = async function (invoice) {
	try {
		return await frappe.xcall(
			frappe.zatca_temp_qr.methods.get_defaults,
			invoice ? { invoice: invoice } : {}
		);
	} catch (e) {
		return {};
	}
};

frappe.zatca_temp_qr.doc_value = function (frm, fieldname) {
	const value = frm && frm.doc ? frm.doc[fieldname] : null;
	return value === undefined || value === null ? "" : String(value);
};

frappe.zatca_temp_qr.company = function (frm) {
	if (!frm || !frm.doc) {
		return "";
	}
	// On the Company form the doc is the company itself.
	return frm.doctype === "Company" ? frm.doc.name : frm.doc.company || "";
};

// TEMPORARY: the one invoice this tool exists for. This name is only used for
// the button label — the invoice name, the original QR and the SAR amounts are
// resolved server-side by generate_default_temp_qr — so the button can never
// generate another invoice's QR. A backend test keeps this name equal to
// DEFAULT_INVOICE in temp_qr_generator.py.
frappe.zatca_temp_qr.quick_invoice = "INV-20135424";

frappe.zatca_temp_qr.quick_button_label = function () {
	return __("Temp: Generate QR ({0})", [frappe.zatca_temp_qr.quick_invoice]);
};

// One-click generation for quick_invoice: no dialog, nothing to type, and the
// result is shown exactly like the dialog's result (same tags, same hash line,
// same Download / Open buttons).
frappe.zatca_temp_qr.quick_generate = function (frm) {
	return frappe.call({
		method: frappe.zatca_temp_qr.methods.quick_generate,
		args: {
			company: frappe.zatca_temp_qr.company(frm),
			attach_to_doctype: frm ? frm.doctype : "",
			attach_to_name: frappe.zatca_temp_qr.doc_value(frm, "name"),
		},
		freeze: true,
		freeze_message: __("Generating QR for {0}…", [frappe.zatca_temp_qr.quick_invoice]),
		callback(r) {
			if (!r.message) {
				return;
			}
			frappe.zatca_temp_qr.show_result(r.message);
			if (!frappe.zatca_temp_qr.after_generate(r.message)) {
				// Must never happen: this QR was rebuilt from the invoice's own
				// snapshot, so a mismatch means the snapshot itself is wrong.
				frappe.msgprint({
					title: __("QR does not belong to {0}", [r.message.invoice]),
					indicator: "red",
					message: __(
						"Delete the generated file and report this: the snapshot of {0} is wrong.",
						[r.message.invoice]
					),
				});
			}
		},
	});
};

// The result view on its own (no input fields) — used by the one-click button.
frappe.zatca_temp_qr.show_result = function (m) {
	const d = new frappe.ui.Dialog({
		title: __("Temp: Phase-2 QR with SAR amounts"),
		size: "large",
		fields: [{ fieldname: "result_html", fieldtype: "HTML" }],
		primary_action_label: __("Close"),
		primary_action() {
			d.hide();
		},
	});
	d.show();
	frappe.zatca_temp_qr.render_result(d, m);
	return d;
};

// Green only when the rebuild really touched nothing but the two amounts: a
// foreign hash would otherwise look like a success.
frappe.zatca_temp_qr.after_generate = function (m) {
	const clean = m.only_amounts_changed && m.preserved_tags_ok && m.hash_matches_invoice;
	frappe.show_alert({
		message: clean
			? __("QR rebuilt — only tags 4 & 5 (amounts) changed")
			: __("QR rebuilt — check the changed tags"),
		indicator: clean ? "green" : "orange",
	});
	return clean;
};

frappe.zatca_temp_qr.reference_html = function (defaults) {
	const source_labels = {
		site: __("Prefilled from this invoice's XML on this site"),
		snapshot: __("Prefilled from the snapshot of a known live invoice"),
		manual: __("Not prefilled — paste this invoice's original QR below"),
	};

	const parts = [];
	if (source_labels[defaults.source]) {
		parts.push(source_labels[defaults.source]);
	}
	if (defaults.usd_total) {
		parts.push(`${__("QR tag 4")}: ${defaults.usd_total} → ${defaults.sar_total} SAR`);
	}
	if (defaults.qr_hash) {
		parts.push(`${__("QR hash (tag 6)")}: ${defaults.qr_hash}`);
	}
	if (!parts.length) {
		return "";
	}

	const text = parts.map((part) => frappe.utils.escape_html(part)).join(" &nbsp;|&nbsp; ");
	return `<p class="text-muted">${text}</p>`;
};

// Merge what the form itself knows into the backend defaults, so a Sales
// Invoice the backend does not know still gets its SAR amounts prefilled from
// base_grand_total / base_total_taxes_and_charges.
frappe.zatca_temp_qr.with_form_fallbacks = function (defaults, frm) {
	const merged = { ...(defaults || {}) };
	if (!merged.invoice) {
		merged.invoice = frappe.zatca_temp_qr.doc_value(frm, "name");
	}
	if (!merged.sar_total) {
		merged.sar_total = frappe.zatca_temp_qr.doc_value(frm, "base_grand_total");
	}
	if (!merged.sar_vat) {
		merged.sar_vat = frappe.zatca_temp_qr.doc_value(frm, "base_total_taxes_and_charges");
	}
	return merged;
};

// Fields the backend prefills and the user may type over.
frappe.zatca_temp_qr.prefilled_fields = ["original_qr", "sar_total", "sar_vat"];

// Remember that the user typed into a prefilled field, so a later re-prefill
// never silently overwrites their paste. Only real typing counts: set_value()
// does not fire "input".
frappe.zatca_temp_qr.track_manual_edits = function (d) {
	d._edited = {};
	frappe.zatca_temp_qr.prefilled_fields.forEach((fieldname) => {
		d.get_field(fieldname).$input.on("input", () => {
			d._edited[fieldname] = true;
		});
	});
};

frappe.zatca_temp_qr.apply_prefill = function (d, prefill) {
	d._prefill = prefill || {};
	d._edited = d._edited || {};
	frappe.zatca_temp_qr.prefilled_fields.forEach((fieldname) => {
		if (d._edited[fieldname]) {
			return; // keep what the user typed
		}
		// Also cleared when the new invoice has no prefill: one invoice's QR and
		// amounts must never survive under another invoice's name.
		d.set_value(fieldname, d._prefill[fieldname] || "");
		d._edited[fieldname] = false;
	});
	d.get_field("reference_html").$wrapper.html(
		frappe.zatca_temp_qr.reference_html(d._prefill)
	);
};

// Re-resolve the prefill for the invoice currently typed in the dialog, and skip
// the round trip when the prefill already belongs to that invoice.
frappe.zatca_temp_qr.refresh_prefill = async function (d, frm) {
	const name = String(d.get_value("invoice") || "").trim();
	if (!name || (d._prefill && d._prefill.invoice === name)) {
		return d._prefill;
	}
	const fresh = frappe.zatca_temp_qr.with_form_fallbacks(
		await frappe.zatca_temp_qr.get_defaults(name),
		frm
	);
	// The invoice typed in the dialog always wins over the form fallback.
	frappe.zatca_temp_qr.apply_prefill(d, { ...fresh, invoice: name });
	return d._prefill;
};

frappe.zatca_temp_qr.open_dialog = async function (frm, invoice) {
	const defaults = frappe.zatca_temp_qr.with_form_fallbacks(
		await frappe.zatca_temp_qr.get_defaults(invoice),
		frm
	);

	const known_invoices = (defaults.known_invoices || []).join(", ");
	const d = new frappe.ui.Dialog({
		title: __("Temp: Phase-2 QR with SAR amounts"),
		size: "large",
		fields: [
			{
				fieldname: "invoice",
				label: __("Invoice"),
				fieldtype: "Data",
				default: defaults.invoice || invoice || "",
				description: known_invoices
					? __("Known invoices: {0}", [known_invoices])
					: __("Sales Invoice name — used to look its QR up"),
				reqd: 1,
			},
			{
				fieldtype: "HTML",
				options: `<p class="text-muted">${__(
					"Only QR tags 4 & 5 (total with VAT / VAT total) are rewritten. Tags 1, 2, 3, 6, 7, 8 and 9 — seller, VAT number, timestamp, invoice hash, signature, public key and certificate signature — are copied byte for byte, so the hash stays the same as the currency QR."
				)}</p>`,
			},
			{ fieldtype: "Section Break", label: __("Original QR of the invoice") },
			{
				fieldname: "original_qr",
				label: __("Original QR (base64 TLV) or signed XML"),
				fieldtype: "Long Text",
				default: defaults.original_qr || "",
				description: __(
					"Resolved from the invoice's custom_invoice_xml on this site, else from the snapshot of a known live invoice. Only tags 4 & 5 are rewritten — paste a payload here only to override that."
				),
			},
			{ fieldtype: "Section Break", label: __("Amounts in SAR (tags 4 & 5)") },
			{
				fieldname: "sar_total",
				label: __("SAR Total — base_grand_total (QR Tag 4)"),
				fieldtype: "Data",
				default: defaults.sar_total || "",
				reqd: 1,
			},
			{
				fieldname: "sar_vat",
				label: __("SAR VAT — base_total_taxes_and_charges (QR Tag 5)"),
				fieldtype: "Data",
				default: defaults.sar_vat || "",
				reqd: 1,
			},
			{
				fieldname: "reference_html",
				fieldtype: "HTML",
				options: frappe.zatca_temp_qr.reference_html(defaults),
			},
			{ fieldtype: "Section Break", label: __("Result") },
			{ fieldname: "result_html", fieldtype: "HTML" },
		],
		primary_action_label: __("Generate QR"),
		async primary_action(values) {
			// The payload and the amounts must belong to the invoice in the
			// field: typing a new name and pressing Generate right away used to
			// send the previous invoice's QR under the new invoice's name.
			await frappe.zatca_temp_qr.refresh_prefill(d, frm);
			values = d.get_values();
			if (!values.original_qr || !String(values.original_qr).trim()) {
				frappe.msgprint({
					title: __("Original QR is required"),
					indicator: "orange",
					message: __(
						"No original QR was found for this invoice.<br><br>Open the invoice's <b>custom_invoice_xml</b> and copy either:<br>• the text inside the QR <b>&lt;cbc:EmbeddedDocumentBinaryObject&gt;</b>, or<br>• the entire XML file content.<br><br>The QR is needed because only tags 4 &amp; 5 (the amounts) may change — the hash, signature and certificate must stay exactly as ZATCA signed them."
					),
				});
				return;
			}
			frappe.zatca_temp_qr.generate(d, frm, values);
		},
	});
	d.show();

	// The dialog opens prefilled for one invoice: remember which one, so that
	// Generate always re-derives the payload and amounts from the invoice name.
	frappe.zatca_temp_qr.track_manual_edits(d);
	frappe.zatca_temp_qr.apply_prefill(d, defaults);

	// Typing another invoice name re-prefills the QR and the SAR amounts. The
	// promise is returned so callers (and tests) can await the re-prefill.
	d.get_field("invoice").$input.on("change", () =>
		frappe.zatca_temp_qr.refresh_prefill(d, frm)
	);
};

frappe.zatca_temp_qr.generate = function (d, frm, values) {
	frappe.call({
		method: frappe.zatca_temp_qr.methods.generate,
		args: {
			company: frappe.zatca_temp_qr.company(frm),
			invoice: values.invoice,
			original_qr: values.original_qr,
			sar_total: values.sar_total,
			sar_vat: values.sar_vat,
			attach_to_doctype: frm ? frm.doctype : "",
			attach_to_name: frappe.zatca_temp_qr.doc_value(frm, "name"),
		},
		freeze: true,
		freeze_message: __("Generating QR…"),
		callback(r) {
			if (!r.message) {
				return;
			}
			const m = r.message;
			frappe.zatca_temp_qr.render_result(d, m);
			// A foreign hash means the QR belongs to another invoice even when
			// the amounts happen to look untouched — never report that as green.
			frappe.zatca_temp_qr.after_generate(m);
		},
	});
};

frappe.zatca_temp_qr.render_result = function (d, m) {
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
		? `<p class="text-success">${__("QR tag 6 matches the {0} hash", [m.invoice])}</p>`
		: `<p class="text-danger"><b>${__(
				"QR tag 6 does not match the {0} hash — this QR belongs to another invoice",
				[m.invoice]
		  )}</b>: ${frappe.utils.escape_html(
				m.hash || ""
		  )}<br>${__(
				"Delete this file and paste the original QR of {0} instead.",
				[m.invoice]
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
};
