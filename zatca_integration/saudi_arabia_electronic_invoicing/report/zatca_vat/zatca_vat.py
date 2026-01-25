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
            "label": _("Title"),
            "fieldtype": "Data",
            "width": 300,
        },
        {
            "fieldname": "amount",
            "label": _("Amount (SAR)"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150,
        },
        {
            "fieldname": "adjustment_amount",
            "label": _("Adjustment (SAR)"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150,
        },
        {
            "fieldname": "vat_amount",
            "label": _("VAT Amount (SAR)"),
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
    company = filters.get("company")
    company_currency = frappe.get_cached_value("Company", company, "default_currency")

    from_date = filters.get("from_date")
    to_date = filters.get("to_date")

    # Get Journal Entry VAT data once (used for both sales and purchases)
    je_vat_data = get_journal_entry_vat_by_type(company, from_date, to_date)

    # --- VAT on Sales (Output VAT) ---
    append_data(data, "VAT on Sales", "", "", "", company_currency)

    grand_total_taxable_amount = 0
    grand_total_taxable_adjustment_amount = 0
    grand_total_tax = 0

    sales_tax_types = frappe.get_all(
        "Sales Taxes and Charges Template",
        filters={"company": company},
        fields=["name", "custom_tax_type"],
    )
    sales_data = []
    for tax_type in sales_tax_types:
        (
            total_taxable_amount,
            total_taxable_adjustment_amount,
            total_tax,
        ) = get_tax_data_for_each_tax_type(tax_type.name, filters, "Sales Invoice")

        sales_data.append(
            {
                "title": _(tax_type.custom_tax_type),
                "amount": total_taxable_amount,
                "adjustment_amount": total_taxable_adjustment_amount,
                "vat_amount": total_tax,
                "currency": company_currency,
            }
        )

        grand_total_taxable_amount += total_taxable_amount
        grand_total_taxable_adjustment_amount += total_taxable_adjustment_amount
        grand_total_tax += total_tax

    # Journal Entry VAT - Output VAT (VAT on Sales)
    for tax_type, data_dict in je_vat_data["sales"].items():
        vat_amount = data_dict.get("vat_amount", 0)
        base_amount = data_dict.get("base_amount", 0)
        if not vat_amount:
            continue
        sales_data.append(
            {
                "title": _(tax_type),
                "amount": base_amount,
                "adjustment_amount": 0,
                "vat_amount": vat_amount,
                "currency": company_currency,
            }
        )
        grand_total_taxable_amount += base_amount
        grand_total_tax += vat_amount

    # Aggregate Sales Data
    aggregated_sales_data = aggregate_data(sales_data)

    # Add Sales Data
    data.extend(aggregated_sales_data)

    # Sales Grand Total
    append_data(
        data,
        "Grand Total",
        grand_total_taxable_amount,
        grand_total_taxable_adjustment_amount,
        grand_total_tax,
        company_currency,
    )

    # Blank Line
    append_data(data, " ", " ", " ", " ", company_currency)

    # --- VAT on Purchases (Input VAT) ---
    append_data(data, "VAT on Purchases", "", "", "", company_currency)

    grand_total_taxable_amount = 0
    grand_total_taxable_adjustment_amount = 0
    grand_total_tax = 0

    purchase_tax_types = frappe.get_all(
        "Purchase Taxes and Charges Template",
        filters={"company": company},
        fields=["name", "custom_tax_type"],
    )
    purchase_data = []
    for tax_type in purchase_tax_types:
        (
            total_taxable_amount,
            total_taxable_adjustment_amount,
            total_tax,
        ) = get_tax_data_for_each_tax_type(tax_type.name, filters, "Purchase Invoice")

        purchase_data.append(
            {
                "title": _(tax_type.custom_tax_type),
                "amount": total_taxable_amount,
                "adjustment_amount": total_taxable_adjustment_amount,
                "vat_amount": total_tax,
                "currency": company_currency,
            }
        )

        grand_total_taxable_amount += total_taxable_amount
        grand_total_taxable_adjustment_amount += total_taxable_adjustment_amount
        grand_total_tax += total_tax

    # Additional input VAT sources:
    # Expense Claims – always treated as purchases, grouped by tax account.custom_tax_type
    expense_claim_vat_by_type = get_expense_claim_vat_by_type(company, from_date, to_date)
    # Merge Expense Claim VAT into purchase_data before aggregation
    for tax_type, data_dict in expense_claim_vat_by_type.items():
        vat_amount = data_dict.get("vat_amount", 0)
        base_amount = data_dict.get("base_amount", 0)
        if not vat_amount:
            continue
        purchase_data.append(
            {
                "title": _(tax_type),
                "amount": base_amount,
                "adjustment_amount": 0,
                "vat_amount": vat_amount,
                "currency": company_currency,
            }
        )
        grand_total_taxable_amount += base_amount
        grand_total_tax += vat_amount
    
    # Journal Entry VAT - Input VAT (VAT on Purchases)
    for tax_type, data_dict in je_vat_data["purchases"].items():
        vat_amount = data_dict.get("vat_amount", 0)
        base_amount = data_dict.get("base_amount", 0)
        
        if not vat_amount:
            continue
        purchase_data.append(
            {
                "title": _(tax_type),
                "amount": base_amount,
                "adjustment_amount": 0,
                "vat_amount": vat_amount,
                "currency": company_currency,
            }
        )
        grand_total_taxable_amount += base_amount
        grand_total_tax += vat_amount

    # Aggregate Purchase Data
    aggregated_purchase_data = aggregate_data(purchase_data)
    # Add Purchase Data
    data.extend(aggregated_purchase_data)

    # Purchase Grand Total
    append_data(
        data,
        "Grand Total",
        grand_total_taxable_amount,
        grand_total_taxable_adjustment_amount,
        grand_total_tax,
        company_currency,
    )

    return data


def get_tax_data_for_each_tax_type(tax_type, filters, doctype):
    """
    (KSA, {filters}, 'Sales Invoice') => 500, 153, 10 \n
    calculates and returns \n
    total_taxable_amount, total_taxable_adjustment_amount, total_tax"""
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")

    # Initiate variables
    total_taxable_amount = 0
    total_taxable_adjustment_amount = 0
    total_tax = 0
    # Fetch All Invoices
    invoices = frappe.get_all(
        doctype,
        filters={
            "docstatus": 1,
            "posting_date": ["between", [from_date, to_date]],
            "taxes_and_charges": tax_type,
        },
        fields=[
            "name",
            "taxes_and_charges",
            "is_return",
            "base_total_taxes_and_charges",
            "base_total",
        ],
    )

    for invoice in invoices:
        total_tax += invoice.base_total_taxes_and_charges

        # Summing up total taxable amount
        if invoice.is_return == 0:
            total_taxable_amount += invoice.base_total

        if invoice.is_return == 1:
            total_taxable_adjustment_amount += invoice.base_total

    return total_taxable_amount, total_taxable_adjustment_amount, total_tax


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


def append_data(data, title, amount, adjustment_amount, vat_amount, company_currency):
    """Returns data with appended value."""
    data.append(
        {
            "title": _(title),
            "amount": amount,
            "adjustment_amount": adjustment_amount,
            "vat_amount": vat_amount,
            "currency": company_currency,
        }
    )


def aggregate_data(data):
    # Create a dictionary to hold the totals for Standard Rate, Except Rate, and Zero Rate
    totals = {
        "Standard Rate": {"amount": 0, "adjustment_amount": 0, "vat_amount": 0},
        "Except Rate": {"amount": 0, "adjustment_amount": 0, "vat_amount": 0},
        "Zero Rate": {"amount": 0, "adjustment_amount": 0, "vat_amount": 0},
    }

    # Iterate through the data and sum up the values for the respective categories
    for entry in data:
        if entry["title"] in totals:
            totals[entry["title"]]["amount"] += entry["amount"] if entry["amount"] else 0
            totals[entry["title"]]["adjustment_amount"] += (
                entry["adjustment_amount"] if entry["adjustment_amount"] else 0
            )
            totals[entry["title"]]["vat_amount"] += (
                entry["vat_amount"] if entry["vat_amount"] else 0
            )

    # Convert the totals dictionary back to the desired output format
    aggregated_data = [
        {
            "title": key,
            "amount": totals[key]["amount"],
            "adjustment_amount": totals[key]["adjustment_amount"],
            "vat_amount": totals[key]["vat_amount"],
            "currency": "SAR",
        }
        for key in totals
    ]

    return aggregated_data
