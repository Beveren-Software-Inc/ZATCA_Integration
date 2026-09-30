import frappe
from frappe.utils import flt

# VATEX reason codes (Sales/Purchase Taxes and Charges Template.custom_zero_rate_reason)
# that represent an export / international-transport supply rather than a
# domestic zero-rated supply.
EXPORT_ZERO_RATE_REASON_PREFIXES = ("VATEX-SA-32", "VATEX-SA-33", "VATEX-SA-34")

ROW_META = {
	"std_sales": {"no": "1", "desc": "Standard rated sales (15%)"},
	"govt_sales": {"no": "2", "desc": "Sales on which the government bears the VAT"},
	"zero_sales": {"no": "3", "desc": "Zero rated domestic sales"},
	"export_sales": {"no": "4", "desc": "Exports"},
	"exempt_sales": {"no": "5", "desc": "Exempt sales"},
	"std_purch": {"no": "6", "desc": "Standard rated domestic purchases (15%)"},
	"import_paid": {"no": "7", "desc": "Imports subject to VAT paid on import (15%)"},
	"import_rcm": {
		"no": "8",
		"desc": "Imports subject to VAT accounted for through the reverse charge mechanism (15%)",
	},
	"zero_purch": {"no": "9", "desc": "Zero rated purchases"},
	"exempt_purch": {"no": "10", "desc": "Exempt purchases"},
}

SALES_ROW_KEYS = ["std_sales", "govt_sales", "zero_sales", "export_sales", "exempt_sales"]
PURCHASE_ROW_KEYS = ["std_purch", "import_paid", "import_rcm", "zero_purch", "exempt_purch"]


def _empty_rows():
	rows = {}
	for key in SALES_ROW_KEYS + PURCHASE_ROW_KEYS:
		rows[key] = {"desc": ROW_META[key]["desc"], "amount": 0.0, "vat": 0.0, "adjustment": 0.0, "count": 0}
	return rows


@frappe.whitelist()
def get_vat_return_summary(company, from_date, to_date, tax_id=None):
	rows = _empty_rows()
	row_docs = {k: set() for k in rows}

	for entry in get_invoice_row_contributions(company, from_date, to_date, tax_id):
		row_id = entry["row_id"]
		rows[row_id]["amount"] += entry["taxable_value"]
		rows[row_id]["vat"] += entry["vat_amount"]
		row_docs[row_id].add(entry["invoice_no"])

	for key in rows:
		rows[key]["count"] = len(row_docs[key])

	total_sales_amount = sum(rows[k]["amount"] for k in SALES_ROW_KEYS)
	total_sales_vat = sum(rows[k]["vat"] for k in SALES_ROW_KEYS)
	total_purch_amount = sum(rows[k]["amount"] for k in PURCHASE_ROW_KEYS)
	total_purch_vat = sum(rows[k]["vat"] for k in PURCHASE_ROW_KEYS)

	row_vat_due = total_sales_vat - total_purch_vat

	return {
		"rows": rows,
		"total_sales_amount": total_sales_amount,
		"total_sales_vat": total_sales_vat,
		"total_purch_amount": total_purch_amount,
		"total_purch_vat": total_purch_vat,
		"row_vat_due": row_vat_due,
		"row_correction_amount": 0.0,
		"row_credit_carried_forward": 0.0,
		"row_net_due": row_vat_due,
	}


@frappe.whitelist()
def get_invoice_list(row_id, company, from_date, to_date, tax_id=None):
	invoices = [
		_public_entry(entry)
		for entry in get_invoice_row_contributions(company, from_date, to_date, tax_id)
		if entry["row_id"] == row_id
	]
	return sorted(invoices, key=lambda x: x["date"])


@frappe.whitelist()
def get_all_contributing_invoices(company, from_date, to_date, tax_id=None):
	invoices = []
	for entry in get_invoice_row_contributions(company, from_date, to_date, tax_id):
		row = _public_entry(entry)
		row["box"] = ROW_META[entry["row_id"]]["no"]
		invoices.append(row)
	return sorted(invoices, key=lambda x: x["date"])


def _public_entry(entry):
	return {k: entry[k] for k in ("invoice_no", "doctype", "party", "date", "taxable_value", "vat_amount")}


def get_invoice_row_contributions(company, from_date, to_date, tax_id=None):
	"""One entry per (invoice, VAT return row).

	Every invoice item line is classified on its own (Item Tax Template first,
	then the invoice's Taxes and Charges Template) and its VAT is taken from the
	invoice's item-wise tax breakup, so an invoice mixing standard, zero rated
	and exempt items is split across the matching rows.
	"""
	contributions = {}

	for doctype, lines, classify in (
		("Sales Invoice", get_sales_invoice_lines(company, from_date, to_date, tax_id), classify_sales_line),
		(
			"Purchase Invoice",
			get_purchase_invoice_lines(company, from_date, to_date, tax_id),
			classify_purchase_line,
		),
	):
		for line in lines:
			row_id = classify(line)
			if not row_id:
				continue

			key = (doctype, line.name, row_id)
			if key not in contributions:
				contributions[key] = {
					"row_id": row_id,
					"invoice_no": line.name,
					"doctype": doctype,
					"party": line.party_name or line.party,
					"date": line.posting_date,
					"taxable_value": 0.0,
					"vat_amount": 0.0,
				}
			contributions[key]["taxable_value"] += flt(line.base_net_amount)
			contributions[key]["vat_amount"] += flt(line.vat_amount)

	return list(contributions.values())


def get_sales_invoice_lines(company, from_date, to_date, tax_id=None):
	return _get_invoice_lines(
		"Sales Invoice",
		company,
		from_date,
		to_date,
		tax_id,
		extra_fields="inv.customer AS party, inv.customer_name AS party_name",
		tax_template="Sales Taxes and Charges Template",
	)


def get_purchase_invoice_lines(company, from_date, to_date, tax_id=None):
	return _get_invoice_lines(
		"Purchase Invoice",
		company,
		from_date,
		to_date,
		tax_id,
		extra_fields="inv.supplier AS party, inv.supplier_name AS party_name, tt.custom_country",
		tax_template="Purchase Taxes and Charges Template",
	)


def _get_invoice_lines(doctype, company, from_date, to_date, tax_id, extra_fields, tax_template):
	"""Item lines of submitted invoices with their line VAT from Item Wise Tax Detail."""
	params = {"company": company, "from_date": from_date, "to_date": to_date, "doctype": doctype}
	condition = ""
	if tax_id:
		condition = "AND (SELECT tax_id FROM `tabCompany` WHERE name = inv.company) = %(tax_id)s"
		params["tax_id"] = tax_id

	lines = frappe.db.sql(
		f"""
		SELECT
			inv.name, inv.posting_date, {extra_fields},
			item.name AS item_row, item.base_net_amount,
			tt.custom_tax_type, tt.custom_zero_rate_reason, tt.custom_except_rate_reason,
			item.item_tax_template, itt.title AS item_tax_template_title
		FROM `tab{doctype}` inv
		INNER JOIN `tab{doctype} Item` item
			ON item.parent = inv.name AND item.parenttype = %(doctype)s
		LEFT JOIN `tab{tax_template}` tt ON tt.name = inv.taxes_and_charges
		LEFT JOIN `tabItem Tax Template` itt ON itt.name = item.item_tax_template
		WHERE inv.company = %(company)s
		  AND inv.docstatus = 1
		  AND inv.posting_date BETWEEN %(from_date)s AND %(to_date)s
		  {condition}
		ORDER BY inv.posting_date, inv.name, item.idx
		""",
		params,
		as_dict=True,
	)

	# Item-wise tax breakup (company currency); summed over all tax rows of each item line.
	item_tax = {
		row.item_row: row
		for row in frappe.db.sql(
			f"""
			SELECT iwtd.item_row, SUM(iwtd.amount) AS amount, MAX(iwtd.rate) AS rate
			FROM `tabItem Wise Tax Detail` iwtd
			INNER JOIN `tab{doctype}` inv ON inv.name = iwtd.parent
			WHERE iwtd.parenttype = %(doctype)s
			  AND inv.company = %(company)s
			  AND inv.docstatus = 1
			  AND inv.posting_date BETWEEN %(from_date)s AND %(to_date)s
			  {condition}
			GROUP BY iwtd.item_row
			""",
			params,
			as_dict=True,
		)
	}

	for line in lines:
		tax = item_tax.get(line.item_row)
		line.vat_amount = flt(tax.amount) if tax else 0.0
		line.vat_rate = flt(tax.rate) if tax else 0.0
	return lines


def get_line_tax_category(line):
	"""(tax_type, zero_rate_reason) of an item line.

	A line without an Item Tax Template follows the invoice's Sales/Purchase
	Taxes and Charges Template. A line with one is categorised by the VAT rate
	actually applied to it in the item-wise tax breakup: a positive rate is
	standard rated; a 0% line is exempt when its Item Tax Template title says so,
	otherwise zero rated (keeping the invoice template's zero rate reason when
	the invoice itself is zero rated).
	"""
	invoice_tax_type = line.get("custom_tax_type")
	invoice_zero_rate_reason = line.get("custom_zero_rate_reason") or ""

	if not line.get("item_tax_template") or invoice_tax_type == "Out of Scope":
		return invoice_tax_type, invoice_zero_rate_reason

	if flt(line.get("vat_rate")) > 0:
		return "Standard Rate", ""
	if "exempt" in (line.get("item_tax_template_title") or line.item_tax_template).lower():
		return "Except Rate", ""
	if invoice_tax_type == "Zero Rate":
		return "Zero Rate", invoice_zero_rate_reason
	return "Zero Rate", ""


def classify_sales_line(line):
	tax_type, zero_rate_reason = get_line_tax_category(line)

	if tax_type == "Standard Rate":
		return "std_sales"
	if tax_type == "Zero Rate":
		# Reasons are stored as "Export of goods(VATEX-SA-32)"; match on the code.
		reason_code = zero_rate_reason.rsplit("(", 1)[-1].rstrip(")").strip()
		if reason_code.startswith(EXPORT_ZERO_RATE_REASON_PREFIXES):
			return "export_sales"
		return "zero_sales"
	if tax_type == "Except Rate":
		return "exempt_sales"

	return None


def classify_purchase_line(line):
	tax_type, _zero_rate_reason = get_line_tax_category(line)
	if tax_type == "Standard Rate":
		country = line.get("custom_country") or "Saudi Arabia"
		return "import_paid" if country != "Saudi Arabia" else "std_purch"
	if tax_type == "Zero Rate":
		return "zero_purch"
	if tax_type == "Except Rate":
		return "exempt_purch"

	return None


# @frappe.whitelist()
# def get_company_vat_numbers(company):
# 	addresses = frappe.db.sql(
# 		"""
# 		SELECT DISTINCT addr.tax_id FROM `tabAddress` addr
# 		INNER JOIN `tabDynamic Link` link ON link.parent = addr.name
# 		WHERE link.link_doctype = 'Company' AND link.link_name = %s
# 		  AND addr.tax_id IS NOT NULL AND addr.tax_id != ''
# 		""",
# 		(company,),
# 		as_dict=True,
# 	)

# 	vat_numbers = [a.tax_id for a in addresses]

# 	comp_tax_id = frappe.db.get_value("Company", company, "tax_id")
# 	if comp_tax_id and comp_tax_id not in vat_numbers:
# 		vat_numbers.append(comp_tax_id)

# 	return vat_numbers

@frappe.whitelist()
def get_company_vat_numbers(company):
    comp_tax_id = frappe.db.get_value("Company", company, "tax_id")
    return [comp_tax_id] if comp_tax_id else []

@frappe.whitelist()
def download_vat_excel(company, from_date, to_date, tax_id=None):
	summary = get_vat_return_summary(company, from_date, to_date, tax_id)
	rows = summary["rows"]

	import openpyxl
	from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
	from io import BytesIO

	wb = openpyxl.Workbook()
	ws = wb.active
	ws.title = "VAT Return Form ZATCA"
	ws.views.sheetView[0].showGridLines = True

	ws.merge_cells("A1:D1")
	ws["A1"] = "VAT Return Form"
	ws["A1"].font = Font(name="Calibri", size=16, bold=True)
	ws["A1"].alignment = Alignment(horizontal="center", vertical="center")

	ws.merge_cells("A2:D2")
	ws["A2"] = f"For the period from {from_date} to {to_date}"
	ws["A2"].font = Font(name="Calibri", size=11, italic=True)
	ws["A2"].alignment = Alignment(horizontal="center", vertical="center")

	ws.row_dimensions[1].height = 30
	ws.row_dimensions[2].height = 20

	ws.merge_cells("A4:A5")
	ws["A4"] = "Particulars"
	ws.merge_cells("B4:B5")
	ws["B4"] = "Amount (SR)"
	ws.merge_cells("C4:C5")
	ws["C4"] = "Adjustments (SR)"
	ws.merge_cells("D4:D5")
	ws["D4"] = "VAT Amount (SR)"

	header_fill = PatternFill(start_color="E5E7EB", end_color="E5E7EB", fill_type="solid")
	header_font = Font(name="Calibri", size=11, bold=True)
	center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

	thin_border = Border(
		left=Side(style="thin", color="B0B0B0"),
		right=Side(style="thin", color="B0B0B0"),
		top=Side(style="thin", color="B0B0B0"),
		bottom=Side(style="thin", color="B0B0B0"),
	)

	for r in range(4, 6):
		for c in range(1, 5):
			cell = ws.cell(row=r, column=c)
			cell.font = header_font
			cell.fill = header_fill
			cell.alignment = center_align
			cell.border = thin_border

	ws.row_dimensions[4].height = 20
	ws.row_dimensions[5].height = 20

	row_configs = [
		("Section", None, "VAT on Sales:", True, True),
		("Data", "std_sales", "Standard rated sales (15%)", False, False),
		("Data", "govt_sales", "Sales on which the government bears the VAT", False, False),
		("Data", "zero_sales", "Zero rated domestic sales", False, False),
		("Data", "export_sales", "Exports", False, False),
		("Data", "exempt_sales", "Exempt sales", False, False),
		("Total", None, "Total Sales", True, False),
		("Section", None, "VAT on Purchases:", True, True),
		("Data", "std_purch", "Standard rated domestic purchases (15%)", False, False),
		("Data", "import_paid", "Imports subject to VAT paid on import (15%)", False, False),
		(
			"Data",
			"import_rcm",
			"Imports subject to VAT accounted for through the reverse charge mechanism (15%)",
			False,
			False,
		),
		("Data", "zero_purch", "Zero rated purchases", False, False),
		("Data", "exempt_purch", "Exempt purchases", False, False),
		("Total", None, "Total purchases", True, False),
		("NetData", "vat_due", "Total VAT due for current period", False, False),
		("NetData", "correction", "Corrections from previous period ( between SAR ± 15000.00 )", False, False),
		("NetData", "credit_cf", "VAT credit carried forward from previous period(s)", False, False),
		("NetData", "net_due", "Net VAT due (or reclaimed)", True, True),
	]

	current_row = 6
	for row_type, key, label, is_bold, has_fill in row_configs:
		if row_type == "Section":
			ws.cell(row=current_row, column=1, value=label)
			ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=4)
			section_fill = PatternFill(start_color="D1D5DB", end_color="D1D5DB", fill_type="solid")
			section_font = Font(name="Calibri", size=11, bold=True)
			for c in range(1, 5):
				cell = ws.cell(row=current_row, column=c)
				cell.fill = section_fill
				cell.font = section_font
				cell.border = thin_border
			ws.row_dimensions[current_row].height = 24

		elif row_type == "Data":
			r_data = rows[key]
			ws.cell(row=current_row, column=1, value=label)
			ws.cell(row=current_row, column=2, value=flt(r_data.get("amount", 0.0)))
			ws.cell(row=current_row, column=3, value=flt(r_data.get("adjustment", 0.0)))
			ws.cell(row=current_row, column=4, value=flt(r_data.get("vat", 0.0)))

			cell_font = Font(name="Calibri", size=11, bold=is_bold)
			ws.cell(row=current_row, column=1).alignment = Alignment(horizontal="left", vertical="center")
			ws.cell(row=current_row, column=1).font = cell_font
			ws.cell(row=current_row, column=1).border = thin_border
			for c in range(2, 5):
				cell = ws.cell(row=current_row, column=c)
				cell.font = cell_font
				cell.border = thin_border
				cell.number_format = "#,##0.00"
				cell.alignment = Alignment(horizontal="right", vertical="center")
			ws.row_dimensions[current_row].height = 20

		elif row_type == "Total":
			row_keys = SALES_ROW_KEYS if "Sales" in label else PURCHASE_ROW_KEYS
			total_amount = sum(rows[k]["amount"] for k in row_keys)
			total_vat = sum(rows[k]["vat"] for k in row_keys)

			ws.cell(row=current_row, column=1, value=label)
			ws.cell(row=current_row, column=2, value=flt(total_amount))
			ws.cell(row=current_row, column=3, value=0.0)
			ws.cell(row=current_row, column=4, value=flt(total_vat))

			cell_font = Font(name="Calibri", size=11, bold=True)
			ws.cell(row=current_row, column=1).alignment = Alignment(horizontal="left", vertical="center")
			ws.cell(row=current_row, column=1).font = cell_font
			ws.cell(row=current_row, column=1).border = thin_border
			for c in range(2, 5):
				cell = ws.cell(row=current_row, column=c)
				cell.font = cell_font
				cell.border = thin_border
				cell.number_format = "#,##0.00"
				cell.alignment = Alignment(horizontal="right", vertical="center")
			ws.row_dimensions[current_row].height = 20

		elif row_type == "NetData":
			ws.cell(row=current_row, column=1, value=label)
			ws.cell(row=current_row, column=2, value="")
			ws.cell(row=current_row, column=3, value="")

			val = {
				"vat_due": summary["row_vat_due"],
				"correction": summary["row_correction_amount"],
				"credit_cf": summary["row_credit_carried_forward"],
				"net_due": summary["row_net_due"],
			}[key]

			ws.cell(row=current_row, column=4, value=flt(val))

			cell_font = Font(name="Calibri", size=11, bold=is_bold)
			ws.cell(row=current_row, column=1).alignment = Alignment(horizontal="left", vertical="center")
			ws.cell(row=current_row, column=1).font = cell_font
			ws.cell(row=current_row, column=1).border = thin_border
			for c in range(2, 5):
				cell = ws.cell(row=current_row, column=c)
				cell.font = cell_font
				cell.border = thin_border
				if c == 4:
					cell.number_format = "#,##0.00"
					cell.alignment = Alignment(horizontal="right", vertical="center")
				else:
					cell.alignment = Alignment(horizontal="center", vertical="center")

			if has_fill:
				net_fill = PatternFill(start_color="EBF8FF", end_color="EBF8FF", fill_type="solid")
				for c in range(1, 5):
					ws.cell(row=current_row, column=c).fill = net_fill

			ws.row_dimensions[current_row].height = 20

		current_row += 1

	ws.column_dimensions["A"].width = 85
	ws.column_dimensions["B"].width = 20
	ws.column_dimensions["C"].width = 20
	ws.column_dimensions["D"].width = 20

	out_buf = BytesIO()
	wb.save(out_buf)
	out_buf.seek(0)

	frappe.response["filename"] = f"ZATCA_VAT_Return_{company}_{from_date}_to_{to_date}.xlsx"
	frappe.response["filecontent"] = out_buf.getvalue()
	frappe.response["type"] = "download"
