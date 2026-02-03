# Copyright (c) 2024, Beveren Software Inc and contributors
# For license information, please see license.txt
# ruff: noqa: E501

import frappe
from frappe import _


def execute(filters=None):
    columns = columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {
            "fieldname": "title",
            "label": _("Title (Tax Reason)"),
            "fieldtype": "Data",
            "width": 300,
        },
        {
            "fieldname": "custom_tax_type",
            "label": _("Tax Type"),
            "fieldtype": "Data",
            "width": 110,
        },
        {
            "fieldname": "collected_amount",
            "label": _("Sales/Purchases Collected (SAR)"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 200,
        },
        {
            "fieldname": "credited_amount",
            "label": _("Sales/Purchases Credited (SAR)"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 200,
        },
        {
            "fieldname": "total_amount",
            "label": _("Total Sales/Purchases (SAR)"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150,
        },
        {
            "fieldname": "vat_collected",
            "label": _("VAT Collected (SAR)"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150,
        },
        {
            "fieldname": "vat_credited",
            "label": _("VAT Credited (SAR)"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150,
        },
        {
            "fieldname": "total_vat",
            "label": _("Total VAT (SAR)"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150,
        },
        {
            "fieldname": "currency",
            "label": _("Currency"),
            "fieldtype": "Currency",
            "width": 150,
            "hidden": 1,
        },
    ]


def get_data(filters):
    data = []
    # Get Company and Currency
    company = filters.get("company")
    company_currency = frappe.get_cached_value("Company", company, "default_currency")

    from_date = filters.get("from_date")
    to_date = filters.get("to_date")

    # Get Journal Entry VAT data once (used for both sales and purchases)
    je_vat_data = get_journal_entry_vat_by_type(company, from_date, to_date)

    # Sales Heading
    append_data(data, "Sales", "", "", "", "", "", "", "", company_currency)

    total_collected = 0
    total_credited = 0
    grand_total = 0
    total_vat_collected = 0
    total_vat_credited = 0
    grand_total_vat = 0

    sales_data = fetch_and_aggregate_data(
        company, "tabSales Invoice", "tabSales Taxes and Charges Template", filters
    )

    for row in sales_data:
        data.append(
            {
                "title": _(row.tax_reason) if row.tax_reason else None,
                "custom_tax_type": row.custom_tax_type,
                "collected_amount": row.collected_amount,
                "credited_amount": row.credited_amount,
                "total_amount": row.total_base_total,
                "vat_collected": row.vat_collected,
                "vat_credited": row.vat_credited,
                "total_vat": row.total_taxes_and_charges,
                "currency": company_currency,
            }
        )

        total_collected += row.collected_amount
        total_credited += row.credited_amount
        grand_total += row.total_base_total
        total_vat_collected += row.vat_collected
        total_vat_credited += row.vat_credited
        grand_total_vat += row.total_taxes_and_charges

    # Add Journal Entry VAT - Output VAT (VAT on Sales)
    for tax_type, data_dict in je_vat_data["sales"].items():
        vat_amount = data_dict.get("vat_amount", 0)
        base_amount = data_dict.get("base_amount", 0)
        if not vat_amount:
            continue
        data.append(
            {
                "title": _("Journal Entries"),
                "custom_tax_type": tax_type,
                "collected_amount": base_amount,
                "credited_amount": 0,
                "total_amount": base_amount,
                "vat_collected": vat_amount,
                "vat_credited": 0,
                "total_vat": vat_amount,
                "currency": company_currency,
            }
        )
        total_collected += base_amount
        grand_total += base_amount
        total_vat_collected += vat_amount
        grand_total_vat += vat_amount

    # Sales Grand Total
    append_data(
        data,
        "Grand Total",
        "",
        total_collected,
        total_credited,
        grand_total,
        total_vat_collected,
        total_vat_credited,
        grand_total_vat,
        company_currency,
    )

    # Blank Line
    append_data(data, "", "", "", "", "", "", "", "", company_currency)

    # # Purchase Heading
    append_data(data, "Purchases", "", "", "", "", "", "", "", company_currency)

    total_collected = 0
    total_credited = 0
    grand_total = 0
    total_vat_collected = 0
    total_vat_credited = 0
    grand_total_vat = 0

    purchase_data = fetch_and_aggregate_data(
        company, "tabPurchase Invoice", "tabPurchase Taxes and Charges Template", filters
    )
    for row in purchase_data:
        data.append(
            {
                "title": _(row.tax_reason) if row.tax_reason else None,
                "custom_tax_type": row.custom_tax_type,
                "collected_amount": row.collected_amount,
                "credited_amount": row.credited_amount,
                "total_amount": row.total_base_total,
                "vat_collected": row.vat_collected,
                "vat_credited": row.vat_credited,
                "total_vat": row.total_taxes_and_charges,
                "currency": company_currency,
            }
        )

        total_collected += row.collected_amount
        total_credited += row.credited_amount
        grand_total += row.total_base_total
        total_vat_collected += row.vat_collected
        total_vat_credited += row.vat_credited
        grand_total_vat += row.total_taxes_and_charges

    # Add VAT from Expense Claims (always treated as purchases/input VAT)
    expense_claim_vat_by_type = get_expense_claim_vat_by_type(company, from_date, to_date)
    for tax_type, data_dict in expense_claim_vat_by_type.items():
        vat_amount = data_dict.get("vat_amount", 0)
        base_amount = data_dict.get("base_amount", 0)
        if not vat_amount:
            continue
        data.append(
            {
                "title": _("Expense Claims"),
                "custom_tax_type": tax_type,
                "collected_amount": base_amount,
                "credited_amount": 0,
                "total_amount": base_amount,
                "vat_collected": vat_amount,
                "vat_credited": 0,
                "total_vat": vat_amount,
                "currency": company_currency,
            }
        )

        total_collected += base_amount
        grand_total += base_amount
        total_vat_collected += vat_amount
        grand_total_vat += vat_amount

    # Add Journal Entry VAT - Input VAT (VAT on Purchases)
    for tax_type, data_dict in je_vat_data["purchases"].items():
        vat_amount = data_dict.get("vat_amount", 0)
        base_amount = data_dict.get("base_amount", 0)
        if not vat_amount:
            continue
        data.append(
            {
                "title": _("Journal Entries"),
                "custom_tax_type": tax_type,
                "collected_amount": base_amount,
                "credited_amount": 0,
                "total_amount": base_amount,
                "vat_collected": vat_amount,
                "vat_credited": 0,
                "total_vat": vat_amount,
                "currency": company_currency,
            }
        )
        total_collected += base_amount
        grand_total += base_amount
        total_vat_collected += vat_amount
        grand_total_vat += vat_amount

    # Purchase Grand Total
    append_data(
        data,
        "Grand Total",
        "",
        total_collected,
        total_credited,
        grand_total,
        total_vat_collected,
        total_vat_credited,
        grand_total_vat,
        company_currency,
    )

    return data


def append_data(
    data,
    title,
    tax_type,
    collected_amount,
    credited_amount,
    total_amount,
    vat_collected,
    vat_credited,
    total_vat,
    company_currency,
):
    """Returns data with appended value."""
    data.append(
        {
            "title": title,
            "custom_tax_type": tax_type,
            "collected_amount": collected_amount,
            "credited_amount": credited_amount,
            "total_amount": total_amount,
            "vat_collected": vat_collected,
            "vat_credited": vat_credited,
            "total_vat": total_vat,
            "currency": company_currency,
        }
    )


def fetch_and_aggregate_data(company, doctype_table, tax_template_table, filters):
    from_date = filters["from_date"]  # Assuming filters is a dict
    to_date = filters["to_date"]

    # Validate or ensure doctype_table is safe to use
    allowed_doctype_tables = ["tabSales Invoice", "tabPurchase Invoice"]
    if doctype_table not in allowed_doctype_tables:
        frappe.throw(_("Invalid Database Table Name!"))

    # Validate or ensure doctype_table is safe to use
    allowed_tax_template_tables = [
        "tabSales Taxes and Charges Template",
        "tabPurchase Taxes and Charges Template",
    ]
    if tax_template_table not in allowed_tax_template_tables:
        frappe.throw(_("Invalid Database Table Name!"))

    # Safe to format the table name here since it's controlled or validated
    # Use base_* fields so amounts and VAT are always in company currency (SAR) and match Zatca VAT report
    sql_query = f"""
        SELECT
			stct.custom_tax_type,
			CASE
				WHEN stct.custom_tax_type = 'Zero Rate' THEN stct.custom_zero_rate_reason
				WHEN stct.custom_tax_type = 'Except Rate' THEN stct.custom_except_rate_reason
				ELSE 'Standard Rate'
			END as tax_reason,
			SUM(si.base_grand_total) as total_grand_total,
			SUM(si.base_total_taxes_and_charges) as total_taxes_and_charges,
			SUM(si.base_total) as total_base_total,
			SUM(CASE WHEN si.is_return = 0 THEN si.base_total ELSE 0 END) as collected_amount,
			SUM(CASE WHEN si.is_return = 0 THEN si.base_total_taxes_and_charges ELSE 0 END) as vat_collected,
			SUM(CASE WHEN si.is_return = 1 THEN si.base_total ELSE 0 END) as credited_amount,
			SUM(CASE WHEN si.is_return = 1 THEN si.base_total_taxes_and_charges ELSE 0 END) as vat_credited
		FROM
			`{doctype_table}` si
		LEFT JOIN
			`{tax_template_table}` stct ON stct.name = si.taxes_and_charges
		WHERE
			si.docstatus = 1 AND
			si.company = %(company)s AND
			stct.company = %(company)s AND
			si.posting_date BETWEEN %(from_date)s AND %(to_date)s
		GROUP BY
			stct.custom_tax_type, tax_reason
		ORDER BY
			stct.custom_tax_type, tax_reason
    """

    fetched_data = frappe.db.sql(
        sql_query, {"company": company, "from_date": from_date, "to_date": to_date}, as_dict=1
    )

    return fetched_data


def get_expense_claim_vat_by_type(company, from_date, to_date):
    """Return VAT from Expense Claims grouped by Account.custom_tax_type.

    Expense Claims are always treated as purchases (input VAT).
    Returns: dict with tax_type as key and dict with 'vat_amount' and 'base_amount' as values.
    """
    if not from_date or not to_date:
        return {}

    sql = """
        SELECT
            acc.custom_tax_type,
            SUM(IFNULL(ect.tax_amount, 0)) AS vat_amount,
            -- Get base amount per expense claim (to avoid double counting when multiple tax types exist)
            SUM(
                CASE 
                    WHEN ect.idx = (
                        SELECT MIN(ect2.idx) 
                        FROM `tabExpense Taxes and Charges` ect2 
                        WHERE ect2.parent = ec.name AND ect2.tax_amount > 0
                    )
                    THEN IFNULL(ec.total_sanctioned_amount, 0) - IFNULL(ec.total_taxes_and_charges, 0)
                    ELSE 0
                END
            ) AS base_amount
        FROM `tabExpense Claim` ec
        JOIN `tabExpense Taxes and Charges` ect ON ect.parent = ec.name
        JOIN `tabAccount` acc ON acc.name = ect.account_head
        WHERE
            ec.docstatus = 1
            AND ec.company = %(company)s
            AND ec.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND acc.account_type = 'Tax'
            AND IFNULL(ect.tax_amount, 0) != 0
        GROUP BY acc.custom_tax_type
    """

    results = frappe.db.sql(
        sql,
        {"company": company, "from_date": from_date, "to_date": to_date},
        as_dict=True,
    )

    return {
        row.custom_tax_type or "Standard Rate": {
            "vat_amount": row.vat_amount,
            "base_amount": row.base_amount,
        }
        for row in results
    }


def get_journal_entry_vat_by_type(company, from_date, to_date):
    """Return VAT from Journal Entries grouped by Account.custom_tax_type.

    Logic:
    - Tax account with debit > 0 → Input VAT (VAT on Purchases)
    - Tax account with credit > 0 → Output VAT (VAT on Sales)
    - Base amount is extracted from related expense/income accounts in the same JE

    Returns: dict with 'sales' and 'purchases' keys, each containing tax_type dicts.
    """
    if not from_date or not to_date:
        return {"sales": {}, "purchases": {}}

    sql = """
        SELECT
            je.name as je_name,
            je.posting_date,
            tax_acc.custom_tax_type,
            tax_jea.debit_in_account_currency as tax_debit,
            tax_jea.credit_in_account_currency as tax_credit,
            tax_jea.account as tax_account,
            -- Get base amount from expense/income accounts in same JE
            SUM(CASE 
                WHEN base_jea.account_type = 'Expense' AND base_jea.debit_in_account_currency > 0 
                THEN base_jea.debit_in_account_currency 
                WHEN base_jea.account_type = 'Income' AND base_jea.credit_in_account_currency > 0 
                THEN base_jea.credit_in_account_currency 
                ELSE 0 
            END) as base_amount
        FROM `tabJournal Entry` je
        JOIN `tabJournal Entry Account` tax_jea ON tax_jea.parent = je.name
        JOIN `tabAccount` tax_acc ON tax_acc.name = tax_jea.account
        LEFT JOIN `tabJournal Entry Account` base_jea ON base_jea.parent = je.name
            AND base_jea.name != tax_jea.name
            AND base_jea.account_type IN ('Expense', 'Income')
        WHERE
            je.docstatus = 1
            AND je.company = %(company)s
            AND je.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND je.voucher_type != 'Vat SetOff'
            AND tax_acc.account_type = 'Tax'
            AND (tax_jea.debit_in_account_currency > 0 OR tax_jea.credit_in_account_currency > 0)
        GROUP BY je.name, tax_acc.custom_tax_type, tax_jea.debit_in_account_currency, tax_jea.credit_in_account_currency
    """

    results = frappe.db.sql(sql, {"company": company, "from_date": from_date, "to_date": to_date}, as_dict=True)

    sales_data = {}
    purchases_data = {}

    for row in results:
        tax_type = row.custom_tax_type or "Standard Rate"
        base_amount = row.base_amount or 0

        # Tax account credited → Output VAT (VAT on Sales)
        if row.tax_credit and row.tax_credit > 0:
            if tax_type not in sales_data:
                sales_data[tax_type] = {"vat_amount": 0, "base_amount": 0}
            sales_data[tax_type]["vat_amount"] += row.tax_credit
            sales_data[tax_type]["base_amount"] += base_amount

        # Tax account debited → Input VAT (VAT on Purchases)
        if row.tax_debit and row.tax_debit > 0:
            if tax_type not in purchases_data:
                purchases_data[tax_type] = {"vat_amount": 0, "base_amount": 0}
            purchases_data[tax_type]["vat_amount"] += row.tax_debit
            purchases_data[tax_type]["base_amount"] += base_amount

    return {"sales": sales_data, "purchases": purchases_data}
