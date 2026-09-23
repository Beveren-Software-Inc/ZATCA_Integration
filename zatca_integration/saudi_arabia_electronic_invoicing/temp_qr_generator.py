"""TEMPORARY Company helper: SAR-amount QR for INV-20134837.

The Company form button ``Temp: Generate SAR QR`` (see ``public/js/company.js``)
rebuilds the ZATCA QR of the live invoice ``INV-20134837`` (USD B2B) so that QR
tags 4 & 5 carry the SAR base amounts instead of the USD totals.

This module changes **nothing but the amount**: the original QR is parsed and
only tags 4 (invoice total with VAT) and 5 (VAT total) are replaced — tags
1, 2, 3, 6, 7, 8 and 9 (seller, VAT number, timestamp, invoice hash, signature,
public key, certificate signature) are copied byte for byte. This is exactly
what ``clearence_util.build_sar_qr_code_base64`` does during clearance, so the
new QR keeps the same hash and signature as the currency QR.

The invoice only exists on the production site, so nothing is read from this
system: ``SAMPLE_INVOICE["original_qr"]`` holds the QR base64 TLV copied from the
live ``/files/INV-20134837.xml`` and is prefilled in the dialog. Pasting another
payload (QR base64 or the whole signed XML) still works.
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

# Static snapshot of the live INV-20134837 (EDGE WORLDWIDE SHIPPING L.L.C) —
# used to prefill the dialog and to verify the pasted QR.
SAMPLE_INVOICE = {
    "invoice": "INV-20134837",
    "seller_name": "Mazare Al Nakheel Company for Dates",
    "vat_number": "310460471100003",
    # QR tag 3 of the live signed XML (cbc:IssueTime).
    "timestamp": "2026-09-21T14:42:16",
    "document_currency": "USD",
    "conversion_rate": "3.73",
    "usd_total": "44052.78",
    "usd_vat": "0.00",
    "sar_total": "164316.87",
    "sar_vat": "0.00",
    "customer": "EDGE WORLDWIDE SHIPPING L.L.C",
    # QR tag 6 of the live signed XML (same as its ds:DigestValue). This is the
    # hash the QR must keep — it is NOT Sales Invoice.custom_invoice_hash,
    # which holds the hash of the cleared invoice (KZpJY3uNAnGpNG3XTKC6dOYAEQw+
    # VBqiJb2FyU2gaas=) and is only used by the app's PIH chain.
    "qr_hash": "eaRKg0HihYzHb04bMVRRhob7PPpyhC9fg1EJJEYT6BQ=",
    # Original QR (base64 TLV) of INV-20134837 as embedded in the live signed
    # XML (/files/INV-20134837.xml). Prefilled in the dialog so the button is
    # one-click; only tags 4 & 5 are ever rewritten.
    "original_qr": (
        "ASNNYXphcmUgQWwgTmFraGVlbCBDb21wYW55IGZvciBEYXRlcwIPMzEwNDYwNDcxMTAwMDAzAxMyMDI2LTA5"
        "LTIxVDE0OjQyOjE2BAg0NDA1Mi43OAUEMC4wMAYsZWFSS2cwSGloWXpIYjA0Yk1WUlJob2I3UFBweWhDOWZn"
        "MUVKSkVZVDZCUT0HYE1FUUNJRXRaMnJwcmpjNEYyYjhKUWtxcm56dDcweGRqZWEzNXpRMGRpT0JuS0FVUUFp"
        "QWRtTEQ1TlVuWHdWZ01vRVBFS1VrVzZQZS96UFZpN0FTU2ZhWnBkSitmVVE9PQhYMFYwEAYHKoZIzj0CAQYF"
        "K4EEAAoDQgAEhN9PYKVISaQGkAOncoaHqiLsltBJLW6uDuFXXyJxNvUcxnM/XCwLojCcO8gPWLPYm5iW2lEz"
        "5Ot194j4N6WodglGMEQCIAVho+hkZLUcQZnW5FdgN8BaOY5n4nZOHlzDqWBieeSMAiBCnFSzHKm+pVaY1W0e"
        "MXffhNWFBuEf40vAaoS311zl1w=="
    ),
}

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


def describe_qr_change(original_qr, sar_qr_base64) -> dict:
    """Summarise which tags differ between the currency QR and the SAR QR."""
    original_tags = parse_qr_tags(original_qr)
    sar_tags = parse_qr_tags(sar_qr_base64)

    changed_tags = sorted(tag for tag in sar_tags if original_tags.get(tag) != sar_tags[tag])
    amount_tags = {QR_TAG_TOTAL_WITH_VAT, QR_TAG_VAT_TOTAL}

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
        # Compares against the hash embedded in the live original QR (tag 6),
        # not Sales Invoice.custom_invoice_hash.
        "hash_matches_invoice": sar_tags.get(QR_TAG_INVOICE_HASH) == SAMPLE_INVOICE["qr_hash"],
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


@frappe.whitelist()
def get_temp_qr_defaults():
    """Prefill the dialog from the static INV-20134837 snapshot."""
    return dict(SAMPLE_INVOICE)


@frappe.whitelist()
def generate_temp_invoice_qr(
    company=None,
    invoice=None,
    original_qr=None,
    sar_total=None,
    sar_vat=None,
):
    """TEMPORARY: rewrite QR tags 4 & 5 of INV-20134837 with the SAR amounts.

    ``original_qr`` defaults to the QR baked into ``SAMPLE_INVOICE`` (copied from
    the live ``/files/INV-20134837.xml``); it may also be that payload pasted
    directly, or the whole signed XML. Nothing is read from this site. Tags
    1, 2, 3, 6, 7, 8 and 9 are left byte-identical, so only the amount changes
    and the hash stays the same as the currency QR.
    """
    invoice = invoice or SAMPLE_INVOICE["invoice"]
    original_qr = original_qr or SAMPLE_INVOICE["original_qr"]
    if sar_total in (None, ""):
        sar_total = SAMPLE_INVOICE["sar_total"]
    if sar_vat in (None, ""):
        sar_vat = SAMPLE_INVOICE["sar_vat"]

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
    file_doc = frappe.get_doc(
        {
            "doctype": "File",
            "file_name": file_name,
            "is_private": 0,
            "content": png,
            "attached_to_doctype": "Company" if company else None,
            "attached_to_name": company or None,
        }
    )
    file_doc.save(ignore_permissions=True)

    return {
        "invoice": invoice,
        "company": company,
        "qr_base64": qr_base64,
        "image_data_url": f"data:image/png;base64,{base64.b64encode(png).decode()}",
        "file_url": file_doc.file_url,
        **describe_qr_change(original_qr, qr_base64),
    }
