"""TEMPORARY helper: SAR-amount QR for foreign-currency invoices.

The button ``Temp: Generate SAR QR`` on the Company form
(``public/js/company.js``) and on the Sales Invoice form
(``public/js/sales_invoice.js``) — both driven by the shared dialog in
``public/js/temp_sar_qr.js`` — rebuilds the ZATCA QR of a USD B2B invoice
(``INV-20135424``, the invoice this backfill is for) so that QR tags 4 & 5 carry
the SAR base amounts instead of the USD totals.

The one-click buttons (``Temp: Generate QR (INV-20135424)``) skip the dialog and
always generate for that single invoice through ``generate_default_temp_qr``, so
no invoice name, payload or amount is ever typed in the browser.

This module changes **nothing but the amount**: the original QR is parsed and
only tags 4 (invoice total with VAT) and 5 (VAT total) are replaced — tags
1, 2, 3, 6, 7, 8 and 9 (seller, VAT number, timestamp, invoice hash, signature,
public key, certificate signature) are copied byte for byte. This is exactly
what ``clearence_util.build_sar_qr_code_base64`` does during clearance, so the
new QR keeps the same hash and signature as the currency QR.

The original QR is resolved in this order:

1. an explicit ``original_qr`` passed by the caller (base64 TLV payload or the
   whole signed XML — pasting still works);
2. the invoice's own ``custom_invoice_xml`` when that invoice exists on the site
   where the button is clicked, so any new foreign-currency invoice works
   without a code change;
3. a baked-in snapshot of the one known live invoice (``SAMPLE_INVOICE``), which
   is what the dialog prefills when the invoice only exists on production.
"""

from __future__ import annotations

import base64
import io

import frappe
import qrcode
from frappe import _
from frappe.utils import flt

from zatca_integration.clearence_util import (
    _encode_tlv_fields,
    _extract_qr_code_payload,
    _parse_tlv_fields,
)

# Static snapshot of the live INV-20135424 (MAZARE ALNAKHEEL NORTH AMERICA LTD,
# USD B2B) — the only invoice this tool knows about. It prefills the dialog and
# verifies the pasted QR when the invoice cannot be read from the site the
# button is clicked on.
SAMPLE_INVOICE = {
    "invoice": "INV-20135424",
    "seller_name": "Mazare Al Nakheel Company for Dates",
    "vat_number": "310460471100003",
    # QR tag 3 of the live signed XML (cbc:IssueTime).
    "timestamp": "2026-09-28T09:38:36",
    "document_currency": "USD",
    "conversion_rate": "3.73",
    "usd_total": "60116.40",
    "usd_vat": "0.00",
    "sar_total": "224234.17",
    "sar_vat": "0.00",
    "customer": "MAZARE ALNAKHEEL NORTH AMERICA LTD",
    # QR tag 6 of the live signed XML (same as its ds:DigestValue) — the hash the
    # QR must keep. This is NOT Sales Invoice.custom_invoice_hash, which holds the
    # hash of the cleared invoice and is only used by the app's PIH chain.
    "qr_hash": "A2DyeY9egOu2eunsNrZGS0k701hDEB+snVLK9ZnezOQ=",
    # Original QR (base64 TLV) of INV-20135424 as embedded in the live signed
    # XML (/files/INV-20135424.xml). Only tags 4 & 5 are ever rewritten.
    "original_qr": (
        "ASNNYXphcmUgQWwgTmFraGVlbCBDb21wYW55IGZvciBEYXRlcwIPMzEwNDYwNDcxMTAwMDAzAxMyMDI2LTA5"
        "LTI4VDA5OjM4OjM2BAg2MDExNi40MAUEMC4wMAYsQTJEeWVZOWVnT3UyZXVuc05yWkdTMGs3MDFoREVCK3Nu"
        "VkxLOVpuZXpPUT0HYE1FVUNJUURIbG9pdnAzb0RZYXpLSzFJVnVRSGpnUTdrNFVnTmVJaVBzdGIrdG9QZTF"
        "RSWdQUmJ1Z1RyMVU2QjAxaW1YcGJ5R0ZobUJuRSt0dlV0OXJsYVFWTC9ocXJzPQhYMFYwEAYHKoZIzj0CAQYF"
        "K4EEAAoDQgAEhN9PYKVISaQGkAOncoaHqiLsltBJLW6uDuFXXyJxNvUcxnM/XCwLojCcO8gPWLPYm5iW2lEz"
        "5Ot194j4N6WodglGMEQCIAVho+hkZLUcQZnW5FdgN8BaOY5n4nZOHlzDqWBieeSMAiBCnFSzHKm+pVaY1W0e"
        "MXffhNWFBuEf40vAaoS311zl1w=="
    ),
}

# The known live invoices the temp tool can prefill without a site lookup: the
# key is the Sales Invoice name, the value its static snapshot. Exactly one
# invoice is registered on purpose — the recent one the backfill is for — so
# nothing can fall back to another invoice's QR.
SAMPLE_INVOICES = {SAMPLE_INVOICE["invoice"]: SAMPLE_INVOICE}
# The invoice the blank dialog and the one-click buttons always use.
DEFAULT_INVOICE = SAMPLE_INVOICE["invoice"]

# ZATCA Phase-2 QR (TLV) tags — only the two totals are rewritten.
QR_TAG_SELLER_NAME = 1
QR_TAG_VAT_NUMBER = 2
QR_TAG_TIMESTAMP = 3
QR_TAG_TOTAL_WITH_VAT = 4
QR_TAG_VAT_TOTAL = 5
QR_TAG_INVOICE_HASH = 6
QR_TAG_SIGNATURE = 7
QR_TAG_PUBLIC_KEY = 8
QR_TAG_CERT_SIGNATURE = 9

# Tags that must stay byte-identical to the signed (currency) QR.
PRESERVED_TAGS = (
    QR_TAG_SELLER_NAME,
    QR_TAG_VAT_NUMBER,
    QR_TAG_TIMESTAMP,
    QR_TAG_INVOICE_HASH,
    QR_TAG_SIGNATURE,
    QR_TAG_PUBLIC_KEY,
    QR_TAG_CERT_SIGNATURE,
)

# Sentinel so ``describe_qr_change`` can tell "caller did not pass a hash" (fall
# back to the snapshot hash of the known invoice, preserving the original
# behaviour) apart from "caller explicitly passed None" (unknown invoice — do
# not warn).
_HASH_UNSET = object()


def _format_amount(amount) -> str:
    """ZATCA QR amounts are plain decimal strings (no currency code)."""
    return f"{flt(amount):.2f}"


def _as_qr_payload(qr_or_xml) -> str | None:
    """Return the base64 TLV payload from a QR payload or a signed invoice XML."""
    if not qr_or_xml:
        return None

    text = qr_or_xml.decode("utf-8", "replace") if isinstance(qr_or_xml, bytes) else str(qr_or_xml)
    # Pasted XML can carry a BOM and base64 pastes can be line-wrapped.
    text = text.lstrip("\ufeff").strip()
    if not text:
        return None

    if text.startswith("<"):
        return _extract_qr_code_payload(text)

    return "".join(text.split())


def parse_qr_tags(qr_or_xml) -> dict:
    """Return the ZATCA QR TLV tags as ``{tag: text}`` (empty when no QR)."""
    payload = _as_qr_payload(qr_or_xml)
    if not payload:
        return {}

    try:
        fields = _parse_tlv_fields(base64.b64decode(payload))
    except Exception:
        return {}

    return {tag: value.decode("utf-8", "replace") for tag, value in fields}


def build_sar_qr_from_original(original_qr, sar_total, sar_vat) -> str | None:
    """Rewrite tags 4 & 5 of ``original_qr`` with the SAR amounts.

    ``original_qr`` is either the base64 QR TLV payload or the signed XML that
    embeds it. Every other tag is copied byte for byte, so the hash, signature,
    public key and certificate signature stay exactly as ZATCA signed them —
    only the amount changes. Returns ``None`` when there is no usable QR.
    """
    payload = _as_qr_payload(original_qr)
    if not payload:
        return None

    try:
        fields = _parse_tlv_fields(base64.b64decode(payload))
    except Exception:
        return None

    if not fields:
        return None

    if QR_TAG_TOTAL_WITH_VAT not in {tag for tag, _ in fields}:
        return None

    sar_amounts = {
        QR_TAG_TOTAL_WITH_VAT: _format_amount(sar_total),
        QR_TAG_VAT_TOTAL: _format_amount(sar_vat),
    }
    sar_fields = [(tag, sar_amounts.get(tag, value)) for tag, value in fields]

    return base64.b64encode(_encode_tlv_fields(sar_fields)).decode("utf-8")


def describe_qr_change(original_qr, sar_qr_base64, expected_hash=_HASH_UNSET) -> dict:
    """Summarise which tags differ between the currency QR and the SAR QR.

    ``expected_hash`` is the invoice hash (QR tag 6) that ``original_qr`` should
    carry — the snapshot's ``qr_hash`` for the known live invoice, or ``None``
    when the invoice is unknown so the check is skipped instead of warning.
    Called without it, it falls back to the known invoice's snapshot hash.
    """
    original_tags = parse_qr_tags(original_qr)
    sar_tags = parse_qr_tags(sar_qr_base64)

    changed_tags = sorted(tag for tag in sar_tags if original_tags.get(tag) != sar_tags[tag])
    amount_tags = {QR_TAG_TOTAL_WITH_VAT, QR_TAG_VAT_TOTAL}

    resolved_hash = SAMPLE_INVOICE["qr_hash"] if expected_hash is _HASH_UNSET else expected_hash

    return {
        "changed_tags": changed_tags,
        # Tag 5 only shows up here when the VAT really differs (e.g. both 0.00
        # stay byte-identical), so this checks that nothing *else* changed.
        "only_amounts_changed": set(changed_tags) <= amount_tags,
        "preserved_tags_ok": all(
            sar_tags.get(tag) == original_tags.get(tag) for tag in PRESERVED_TAGS
        ),
        "original_total": original_tags.get(QR_TAG_TOTAL_WITH_VAT),
        "original_vat": original_tags.get(QR_TAG_VAT_TOTAL),
        "sar_total": sar_tags.get(QR_TAG_TOTAL_WITH_VAT),
        "sar_vat": sar_tags.get(QR_TAG_VAT_TOTAL),
        "hash": sar_tags.get(QR_TAG_INVOICE_HASH),
        # Compares QR tag 6 against the hash embedded in the invoice's own
        # signed XML — not Sales Invoice.custom_invoice_hash.
        "hash_matches_invoice": resolved_hash is None
        or sar_tags.get(QR_TAG_INVOICE_HASH) == resolved_hash,
        "seller_name": sar_tags.get(QR_TAG_SELLER_NAME),
        "vat_number": sar_tags.get(QR_TAG_VAT_NUMBER),
        "timestamp": sar_tags.get(QR_TAG_TIMESTAMP),
    }


def _qr_png_bytes(data: str) -> bytes:
    """Render the QR base64 payload as PNG bytes."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _invoice_qr_from_site(invoice):
    """Read ``invoice``'s signed XML on this site and return its QR snapshot.

    Returns ``None`` (never raises) when the invoice is not on this site, has no
    ``custom_invoice_xml``, or that file holds no QR code payload.
    """
    try:
        if not frappe.db.exists("Sales Invoice", invoice):
            return None

        invoice_doc = frappe.get_doc("Sales Invoice", invoice)
        xml_url = invoice_doc.get("custom_invoice_xml")
        if not xml_url:
            return None

        xml = frappe.get_doc("File", {"file_url": xml_url}).get_content()
        if isinstance(xml, bytes):
            xml = xml.decode("utf-8", "replace")

        payload = _extract_qr_code_payload(xml)
        if not payload:
            return None

        tags = parse_qr_tags(payload)
        return {
            "invoice": invoice,
            "seller_name": tags.get(QR_TAG_SELLER_NAME),
            "vat_number": tags.get(QR_TAG_VAT_NUMBER),
            "timestamp": tags.get(QR_TAG_TIMESTAMP),
            "document_currency": invoice_doc.get("currency"),
            "conversion_rate": str(invoice_doc.get("conversion_rate") or ""),
            "usd_total": tags.get(QR_TAG_TOTAL_WITH_VAT),
            "usd_vat": tags.get(QR_TAG_VAT_TOTAL),
            # The invoice's currency QR holds the transaction amounts; the base
            # amounts are the SAR amounts ZATCA expects for a USD invoice.
            "sar_total": _format_amount(invoice_doc.get("base_grand_total")),
            "sar_vat": _format_amount(invoice_doc.get("base_total_taxes_and_charges")),
            "customer": invoice_doc.get("customer"),
            "qr_hash": tags.get(QR_TAG_INVOICE_HASH),
            "original_qr": payload,
            "source": "site",
        }
    except Exception:
        frappe.log_error(
            title=f"ZATCA temp QR: cannot read the QR of {invoice}",
            message=frappe.get_traceback(),
        )
        return None


def get_invoice_defaults(invoice=None) -> dict:
    """Resolve the temp-QR dialog defaults for ``invoice``.

    Order: static snapshot of a known live invoice, else the invoice's own
    ``custom_invoice_xml`` when it exists on this site, else a blank template so
    the user can paste the QR by hand.
    """
    invoice = (invoice or "").strip() or DEFAULT_INVOICE

    snapshot = SAMPLE_INVOICES.get(invoice)
    if snapshot:
        return {**snapshot, "source": "snapshot"}

    live = _invoice_qr_from_site(invoice)
    if live:
        return live

    return {
        "invoice": invoice,
        "seller_name": "",
        "vat_number": "",
        "timestamp": "",
        "document_currency": "",
        "conversion_rate": "",
        "usd_total": "",
        "usd_vat": "",
        "sar_total": "",
        "sar_vat": "",
        "customer": "",
        # Blank on purpose: an unknown invoice cannot be hash-checked, so
        # ``generate_temp_invoice_qr`` passes ``None`` and skips the warning.
        "qr_hash": "",
        "original_qr": "",
        "source": "manual",
    }


@frappe.whitelist()
def get_temp_qr_defaults(invoice=None):
    """Prefill the dialog for ``invoice`` (known snapshot, live site or manual).

    With no ``invoice`` the one known invoice (``DEFAULT_INVOICE`` — the recent
    ``INV-20135424``) is used, so the Company form needs no typing at all.
    """
    defaults = get_invoice_defaults(invoice)
    defaults["known_invoices"] = list(SAMPLE_INVOICES)
    defaults["default_invoice"] = DEFAULT_INVOICE
    return defaults


@frappe.whitelist()
def generate_temp_invoice_qr(
    company=None,
    invoice=None,
    original_qr=None,
    sar_total=None,
    sar_vat=None,
    attach_to_doctype=None,
    attach_to_name=None,
):
    """TEMPORARY: rewrite QR tags 4 & 5 of ``invoice`` with the SAR amounts.

    ``original_qr`` is used when given (the payload pasted in the dialog, base64
    TLV or the whole signed XML). Otherwise it is read from the invoice's own
    ``custom_invoice_xml`` on this site, and only then from the baked-in snapshot
    of the known live invoice (``SAMPLE_INVOICE``). Tags 1, 2, 3, 6, 7, 8 and 9
    are left byte-identical, so only the amount changes and the hash stays the
    same as the currency QR.

    The PNG is attached to ``attach_to_doctype``/``attach_to_name`` (the form the
    button was clicked on); without them it falls back to ``company``, which is
    what the Company form passes.
    """
    invoice = (invoice or "").strip() or DEFAULT_INVOICE
    defaults = get_invoice_defaults(invoice)

    original_qr = original_qr or defaults.get("original_qr")
    if _is_blank(sar_total):
        sar_total = defaults.get("sar_total")
    if _is_blank(sar_vat):
        sar_vat = defaults.get("sar_vat")

    qr_base64 = build_sar_qr_from_original(original_qr, sar_total, sar_vat)
    if not qr_base64:
        frappe.throw(
            _(
                "Paste the original ZATCA QR of {0} (base64 TLV or the signed XML) that has "
                "QR tag 4, then try again."
            ).format(invoice)
        )

    png = _qr_png_bytes(qr_base64)
    file_name = f"TEMP-{invoice}-QR-SAR-{frappe.generate_hash(length=6)}.png"

    # Attach the PNG to the form the button was clicked on (Sales Invoice or
    # Company). Both parts are required; anything partial falls back to the
    # company, which keeps the original Company-form behaviour.
    if not (attach_to_doctype and attach_to_name):
        attach_to_doctype = "Company" if company else None
        attach_to_name = company or None

    file_doc = frappe.get_doc(
        {
            "doctype": "File",
            "file_name": file_name,
            "is_private": 0,
            "content": png,
            "attached_to_doctype": attach_to_doctype,
            "attached_to_name": attach_to_name,
        }
    )
    file_doc.save(ignore_permissions=True)

    return {
        "invoice": invoice,
        "company": company,
        "attach_to_doctype": attach_to_doctype,
        "attach_to_name": attach_to_name,
        "source": defaults.get("source"),
        "qr_base64": qr_base64,
        "image_data_url": f"data:image/png;base64,{base64.b64encode(png).decode()}",
        "file_url": file_doc.file_url,
        # ``qr_hash`` is "" for an unknown invoice: passing None skips the
        # "hash belongs to another invoice" warning instead of raising a false
        # alarm for a payload the backend simply cannot verify.
        **describe_qr_change(
            original_qr,
            qr_base64,
            expected_hash=defaults.get("qr_hash") or None,
        ),
    }


@frappe.whitelist()
def generate_default_temp_qr(company=None, attach_to_doctype=None, attach_to_name=None):
    """TEMPORARY: one-click SAR QR for ``DEFAULT_INVOICE`` (the recent invoice).

    This is what the ``Temp: Generate QR (INV-20135424)`` buttons call. Unlike
    the dialog it takes no invoice name, payload or amount from the browser:
    all three are resolved here from the snapshot of the one live invoice, so
    the button cannot put another invoice's QR under this invoice's name.

    The PNG belongs to ``DEFAULT_INVOICE``, so it is never attached to another
    Sales Invoice's record by accident: it goes to that invoice's own record
    when this site has it, else to the form the button was clicked on (the
    Company form) and finally to ``company``.
    """
    if frappe.db.exists("Sales Invoice", DEFAULT_INVOICE):
        # On the real site the file belongs on the invoice's own record.
        attach_to_doctype, attach_to_name = "Sales Invoice", DEFAULT_INVOICE
    elif attach_to_doctype == "Sales Invoice":
        # The invoice is not on this site, so do not hang its QR on whichever
        # Sales Invoice happened to be open: leave it on the company instead.
        attach_to_doctype, attach_to_name = None, None

    return generate_temp_invoice_qr(
        company=company,
        invoice=DEFAULT_INVOICE,
        attach_to_doctype=attach_to_doctype,
        attach_to_name=attach_to_name,
    )
