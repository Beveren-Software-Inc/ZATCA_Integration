# Copyright (c) 2025, Simon Wanyama and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import cint, flt


@frappe.whitelist()
def update_payment_method(customer):
    if not frappe.db.exists("Customer", customer):
        frappe.throw(f"Customer with ID {customer} does not exist.")
    payment_method = frappe.db.get_value("Customer", customer, "custom_payment_method")
    customer_type = frappe.db.get_value("Customer", customer, "customer_type")
    if customer_type == "Individual":
        return "Cash"
    if payment_method is None:
        return "Cash"
    return payment_method


@frappe.whitelist()
def update_delivery_date(delivery_note):
    if not frappe.db.exists("Delivery Note", delivery_note):
        frappe.throw(f"Delivery Note with ID {delivery_note} does not exist.")
    delivery_date = frappe.db.get_value("Delivery Note", delivery_note, "posting_date")
    if delivery_date is None:
        frappe.msgprint(f"No posting date set for Delivery Note {delivery_note}.")
    return delivery_date


def sync_retention_from_percentage(doc, method=None):
    """Keep retention amount in sync when net total changes but percentage is set."""
    if not doc.custom_retention_account or not flt(doc.custom_retention_percentage):
        return
    if not flt(doc.net_total):
        return

    doc.custom_retention_amount = flt(
        flt(doc.net_total) * flt(doc.custom_retention_percentage) / 100,
        doc.precision("custom_retention_amount"),
    )


def set_base_retention_amount(doc, method):
    if not doc.custom_retention_amount:
        return
    if not doc.conversion_rate:
        frappe.throw(_("Please set Exchange Rate First"))
    doc.custom_base_retention_amount = doc.conversion_rate * doc.custom_retention_amount


def should_subtract_retention_from_outstanding():
    """Read Zatca Settings flag; default True to preserve existing behaviour."""
    try:
        value = frappe.db.get_single_value(
            "Zatca Settings", "subtract_retention_from_outstanding"
        )
    except Exception:
        return True
    # None = field not migrated / unset → keep historical subtract behaviour
    if value is None:
        return True
    return bool(cint(value))


def _ple_outstanding(doc, account=None):
    """Sum open Payment Ledger amount against this invoice (optionally one account)."""
    if doc.is_new() or not doc.name:
        return None

    from frappe.query_builder.functions import Sum

    ple = frappe.qb.DocType("Payment Ledger Entry")
    query = (
        frappe.qb.from_(ple)
        .select(Sum(ple.amount_in_account_currency).as_("outstanding"))
        .where(ple.against_voucher_type == "Sales Invoice")
        .where(ple.against_voucher_no == doc.name)
        .where(ple.party_type == "Customer")
        .where(ple.party == doc.customer)
        .where(ple.delinked == 0)
    )
    if account:
        query = query.where(ple.account == account)

    result = query.run(as_dict=True)
    if not result or result[0].outstanding is None:
        return None
    return flt(result[0].outstanding)


def get_invoice_receivable_outstanding(doc):
    """Open receivable across all party accounts against this invoice (Debtors + Retention)."""
    outstanding = _ple_outstanding(doc)
    if outstanding is None:
        return flt(doc.get("grand_total") or doc.get("outstanding_amount"))
    return outstanding


def get_retention_open_amount(doc):
    """How much retention is still open against this invoice."""
    retention = flt(doc.get("custom_retention_amount"))
    if not retention:
        return 0.0

    retention_account = doc.get("custom_retention_account")
    debit_to = doc.get("debit_to")

    # Separate retention account — use that account's PLE balance
    if retention_account and retention_account != debit_to:
        open_amt = _ple_outstanding(doc, account=retention_account)
        if open_amt is None:
            return retention
        return max(flt(open_amt), 0.0)

    # Same account as Debtors — treat retention as the last unpaid slice
    total_open = get_invoice_receivable_outstanding(doc)
    return min(retention, max(total_open, 0.0))


def get_outstanding_after_retention(doc):
    """
    Invoice outstanding that should be stored on the Sales Invoice.
    - Subtract ON: exclude open retention (amount currently due)
    - Subtract OFF: full open receivable including retention
    """
    precision = doc.precision("outstanding_amount") or 2
    total_open = get_invoice_receivable_outstanding(doc)

    if not should_subtract_retention_from_outstanding():
        return flt(total_open, precision)

    retention_open = get_retention_open_amount(doc)
    return flt(max(total_open - retention_open, 0.0), precision)


def adjust_outstanding_for_retention(doc, method=None):
    """Reduce outstanding by retention on validate (before PLE exists)."""
    if doc.doctype != "Sales Invoice":
        return
    if not doc.custom_retention_account or not doc.custom_retention_amount:
        return
    if not should_subtract_retention_from_outstanding():
        return

    doc.outstanding_amount = flt(
        doc.outstanding_amount - flt(doc.custom_retention_amount),
        doc.precision("outstanding_amount"),
    )


def sync_outstanding_for_retention(doc, method=None, update=False, update_modified=True):
    """
    Re-apply retention outstanding after Payment Ledger overwrites it on submit/payment.
    Must run for submitted invoices whenever outstanding is refreshed from PLE.
    """
    if doc.doctype != "Sales Invoice" or cint(doc.docstatus) != 1:
        return
    if not doc.get("custom_retention_account") or not flt(doc.get("custom_retention_amount")):
        return

    precision = doc.precision("outstanding_amount") or 2
    new_outstanding = get_outstanding_after_retention(doc)
    current = flt(doc.get("outstanding_amount"), precision)

    if current == new_outstanding:
        return

    doc.outstanding_amount = new_outstanding
    persist = update or method in ("on_submit", "on_cancel")
    if persist and doc.name:
        frappe.db.set_value(
            doc.doctype,
            doc.name,
            "outstanding_amount",
            new_outstanding,
            update_modified=update_modified,
        )
        # Status depends on outstanding — refresh after we correct it
        # Call parent method only to avoid CustomSalesInvoice.set_status recursion
        from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice

        SalesInvoice.set_status(doc, update=True, update_modified=update_modified)
        set_retention_status(doc, update=True, update_modified=update_modified)


def set_retention_status(doc, method=None, update=False, update_modified=True):
    """
    Retention Status stays Unpaid until every receivable against the invoice
    (including retention) is cleared, then Paid. Independent of ERPNext status.
    """
    if doc.doctype != "Sales Invoice":
        return
    if not frappe.get_meta("Sales Invoice").has_field("custom_retention_status"):
        return

    if doc.docstatus == 2 or not flt(doc.get("custom_retention_amount")):
        new_status = ""
    elif doc.docstatus == 0:
        new_status = "Unpaid"
    else:
        outstanding = get_invoice_receivable_outstanding(doc)
        precision = doc.precision("outstanding_amount") or 2
        new_status = "Paid" if flt(outstanding, precision) <= 0 else "Unpaid"

    if doc.get("custom_retention_status") == new_status:
        return

    doc.custom_retention_status = new_status
    # Persist after submit/cancel hooks and when ERPNext asks for update=True (payments)
    persist = update or method in ("on_submit", "on_cancel")
    if persist and doc.name:
        frappe.db.set_value(
            doc.doctype,
            doc.name,
            "custom_retention_status",
            new_status,
            update_modified=update_modified,
        )


@frappe.whitelist()
def get_batch(customer, sales_invoice, item):
    values = {"customer": customer, "sales_invoice": sales_invoice, "item": item}
    batch_list = frappe.db.sql(
        """
    SELECT `tabSales Invoice`.NAME,
       `tabSales Invoice`.customer,
       `tabSales Invoice Item`.qty
    FROM `tabSales Invoice`
    JOIN `tabSales Invoice Item`
    ON `tabSales Invoice`.NAME = `tabSales Invoice Item`.parent
    WHERE `tabSales Invoice`.customer = %(customer)s
    AND `tabSales Invoice`.NAME = %(sales_invoice)s
    AND `tabSales Invoice Item`.item_code = %(item)s
    AND `tabSales Invoice`.docstatus = 1
    AND `tabSales Invoice`.status != "Cancelled"
            """,
        values=values,
        as_dict=1,
    )
    return batch_list


@frappe.whitelist()
def returned_qty(customer, sales_invoice, item):
    values = {"customer": customer, "sales_invoice": sales_invoice, "item": item}

    total_returned = frappe.db.sql(
        """
        SELECT
            `tabCredit Details`.sales_invoice,
            `tabSales Invoice`.customer,
            SUM(`tabCredit Details`.qtr) AS total_returned_qty
        FROM
            `tabSales Invoice`
        JOIN
            `tabCredit Details` ON `tabSales Invoice`.name = `tabCredit Details`.parent
        WHERE
            `tabSales Invoice`.customer = %(customer)s
            AND `tabCredit Details`.sales_invoice = %(sales_invoice)s
            AND `tabCredit Details`.item = %(item)s
            AND `tabSales Invoice`.docstatus = 1
            AND `tabSales Invoice`.status != 'Cancelled'
        GROUP BY
            `tabCredit Details`.sales_invoice, `tabSales Invoice`.customer
    """,
        values=values,
        as_dict=True,
    )

    if not total_returned:
        return {"total_returned_qty": 0}

    return total_returned[0]


@frappe.whitelist()
def get_valid_sales_invoices(doctype, txt, searchfield, start, page_len, filters=None):
    filters = filters or {}

    customer = filters.get("customer")
    shipping_address = filters.get("shipping_address")
    item_code = filters.get("item_code")
    start_date = filters.get("start_date")

    if not customer or not item_code or not start_date:
        return []

    # Build dynamic conditions
    conditions = ["si.docstatus = 1", "si.is_return = 0"]
    query_params = {
        "txt": f"%{txt}%",
        "start": start,
        "page_len": page_len,
    }

    if customer:
        conditions.append("si.customer = %(customer)s")
        query_params["customer"] = customer

    if shipping_address:
        conditions.append("si.shipping_address_name = %(shipping_address)s")
        query_params["shipping_address"] = shipping_address

    if item_code:
        conditions.append("sii.item_code = %(item_code)s")
        query_params["item_code"] = item_code

    if start_date:
        conditions.append("si.posting_date >= %(start_date)s")
        query_params["start_date"] = start_date

    # Add logic for returned quantities dynamically in SQL
    conditions.append("""
        (sii.qty + COALESCE((
            SELECT SUM(cd.qtr)
            FROM `tabCredit Details` cd
            JOIN `tabSales Invoice` rsi ON cd.parent = rsi.name
            WHERE cd.sales_invoice = si.name
            AND cd.item = sii.item_code
            AND rsi.customer = si.customer
            AND rsi.docstatus = 1
            AND rsi.status != 'Cancelled'
        ), 0)) > 0
    """)

    # Construct query
    where_clause = " AND ".join(conditions)
    query = f"""
        SELECT DISTINCT si.name,si.posting_date,sii.qty
        FROM `tabSales Invoice` si
        JOIN `tabSales Invoice Item` sii ON si.name = sii.parent
        WHERE {where_clause}
        AND si.name LIKE %(txt)s
        LIMIT %(start)s, %(page_len)s
    """

    return frappe.db.sql(query, query_params)
