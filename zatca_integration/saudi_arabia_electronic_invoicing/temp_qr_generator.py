"""Temporary Company helper: rebuild Phase-2 ZATCA QR with SAR amounts."""

from __future__ import annotations

import base64
import io

import frappe
import qrcode
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from frappe.utils import flt

# Snapshot from INV-20133496 (Individual / simplified 0200000)
# QR tags 4 & 5 use company-currency (SAR) base amounts — not USD.
SAMPLE_INVOICE = {
    "seller_name": "Mazare Al Nakheel Company for Dates",
    "vat_number": "310460471100003",
    "timestamp": "2026-09-16T10:33:22",
    "sar_total": "220210.25",
    "sar_vat": "0.00",
    "usd_total": "59037.60",
    "usd_vat": "0.00",
    "invoice_hash": "2obSEzlf6TaxgBkjCTNfR6v3HgfF6+iUVbBI7ensVuQ=",
    "signature_value": (
        "MEUCIQDR/7L1GBDAdAkfobVYjjYOE9wUpTQWvYNUfXTFGQ8RwwIgVDAbWop/"
        "jdlil/uBIW/4GEsWxd/5yVysdKM9lLW2CeE="
    ),
    "certificate": (
        "MIIFPzCCBOagAwIBAgITWwACHGPs3oRLVaEXEgABAAIcYzAKBggqhkjOPQQDAjBiMRUwEwYK"
        "CZImiZPyLGQBGRYFbG9jYWwxEzARBgoJkiaJk/IsZAEZFgNnb3YxFzAVBgoJkiaJk/IsZAEZ"
        "FgdleHRnYXp0MRswGQYDVQQDExJQUlpFSU5WT0lDRVNDQTQtQ0EwHhcNMjYwMzIwMTMwNTQ1"
        "WhcNMzAwNDAyMDMzMTEzWjCBiTELMAkGA1UEBhMCU0ExLDAqBgNVBAoTI01hemFyZSBBbCBO"
        "YWtoZWVsIENvbXBhbnkgZm9yIERhdGVzMSAwHgYDVQQLExdNLUFsbmFraGVlbCBNYWluIEJy"
        "YW5jaDEqMCgGA1UEAxMhTWF6YXJlLUFsbmFraGVlbCBNYWluIE9mZmljZSAyMDI2MFYwEAYH"
        "KoZIzj0CAQYFK4EEAAoDQgAEhN9PYKVISaQGkAOncoaHqiLsltBJLW6uDuFXXyJxNvUcxnM/"
        "XCwLojCcO8gPWLPYm5iW2lEz5Ot194j4N6WodqOCA1QwggNQMIG+BgNVHREEgbYwgbOkgbAw"
        "ga0xPzA9BgNVBAQMNjEtRVJQTmV4dHwyLVYxNXwzLTM1MDgwMzc3LWQyZWUtNDI4NC1hMDgy"
        "LTNmMDg3NTIwNTBkZDEfMB0GCgmSJomT8ixkAQEMDzMxMDQ2MDQ3MTEwMDAwMzENMAsGA1UE"
        "DAwEMTEwMDEgMB4GA1UEGgwXaHR0cHM6Ly9tLWFsbmFraGVlbC5jb20xGDAWBgNVBA8MD1Jl"
        "dGFpbCBCdXNpbmVzczAdBgNVHQ4EFgQUqePLF4VyuLwdPn0/qI7gfHmEkp8wHwYDVR0jBBgw"
        "FoAUm8qqou2arCyQgXNW+k/Y/FP702cwgeUGA1UdHwSB3TCB2jCB16CB1KCB0YaBzmxkYXA6"
        "Ly8vQ049UFJaRUlOVk9JQ0VTQ0E0LUNBKDEpLENOPVBSWkVJTlZPSUNFU0NBNCxDTj1DRFAs"
        "Q049UHVibGljJTIwS2V5JTIwU2VydmljZXMsQ049U2VydmljZXMsQ049Q29uZmlndXJhdGlv"
        "bixEQz1leHR6YXRjYSxEQz1nb3YsREM9bG9jYWw/Y2VydGlmaWNhdGVSZXZvY2F0aW9uTGlz"
        "dD9iYXNlP29iamVjdENsYXNzPWNSTERpc3RyaWJ1dGlvblBvaW50MIHOBggrBgEFBQcBAQSB"
        "wTCBvjCBuwYIKwYBBQUHMAKGga5sZGFwOi8vL0NOPVBSWkVJTlZPSUNFU0NBNC1DQSxDTj1B"
        "SUEsQ049UHVibGljJTIwS2V5JTIwU2VydmljZXMsQ049U2VydmljZXMsQ049Q29uZmlndXJh"
        "dGlvbixEQz1leHR6YXRjYSxEQz1nb3YsREM9bG9jYWw/Y0FDZXJ0aWZpY2F0ZT9iYXNlP29i"
        "amVjdENsYXNzPWNlcnRpZmljYXRpb25BdXRob3JpdHkwDgYDVR0PAQH/BAQDAgeAMDwGCSsG"
        "AQQBgjcVBwQvMC0GJSsGAQQBgjcVCIGGqB2E0PsShu2dJIfO+xnTwFVmh/qlZYXZhD4CAWQC"
        "AQ4wHQYDVR0lBBYwFAYIKwYBBQUHAwMGCCsGAQUFBwMCMCcGCSsGAQQBgjcVCgQaMBgwCgYI"
        "KwYBBQUHAwMwCgYIKwYBBQUHAwIwCgYIKoZIzj0EAwIDRwAwRAIgBWGj6GRktRxBmdbkV2A3"
        "wFo5jmfidk4eXMOpYGJ55IwCIEKcVLMcqb6lVpjVbR4xd9+E1YUG4R/jS8BqhLfXXOXX"
    ),
}


def _tlv(tag: int, value) -> bytes:
    if isinstance(value, str):
        value_bytes = value.encode("utf-8")
    else:
        value_bytes = value
    length = len(value_bytes)
    if length < 256:
        return bytes([tag, length]) + value_bytes
    return bytes([tag, 0xFF, (length >> 8) & 0xFF, length & 0xFF]) + value_bytes


def _load_certificate(certificate_b64: str):
    content = (certificate_b64 or "").strip().replace("\n", "")
    pem = "-----BEGIN CERTIFICATE-----\n"
    pem += "\n".join(content[i : i + 64] for i in range(0, len(content), 64))
    pem += "\n-----END CERTIFICATE-----\n"
    return x509.load_pem_x509_certificate(pem.encode("utf-8"), default_backend())


def _public_key_bytes(cert) -> bytes:
    return cert.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _format_amount(amount) -> str:
    """ZATCA QR amounts as plain decimal strings (no currency code)."""
    return f"{flt(amount):.2f}"


def build_phase2_qr_base64(
    seller_name: str,
    vat_number: str,
    timestamp: str,
    sar_total: str | float,
    sar_vat: str | float,
    invoice_hash: str,
    signature_value: str,
    certificate_b64: str,
) -> str:
    cert = _load_certificate(certificate_b64)
    tlv = b"".join(
        [
            _tlv(1, seller_name),
            _tlv(2, vat_number),
            _tlv(3, timestamp),
            _tlv(4, _format_amount(sar_total)),
            _tlv(5, _format_amount(sar_vat)),
            _tlv(6, invoice_hash),
            _tlv(7, signature_value),
            _tlv(8, _public_key_bytes(cert)),
            _tlv(9, cert.signature),
        ]
    )
    return base64.b64encode(tlv).decode("utf-8")


def _qr_png_bytes(data: str) -> bytes:
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@frappe.whitelist()
def get_temp_qr_defaults():
    """Prefill dialog from the sample INV-20133496 snapshot."""
    return dict(SAMPLE_INVOICE)


@frappe.whitelist()
def generate_temp_invoice_qr(
    company=None,
    seller_name=None,
    vat_number=None,
    timestamp=None,
    sar_total=None,
    sar_vat=None,
    invoice_hash=None,
    signature_value=None,
    certificate=None,
):
    """
    Temporary: build Phase-2 QR for Individual invoice with amounts in SAR.

    Use base_grand_total / base taxes (SAR) directly — do not convert from USD.
    """
    seller_name = seller_name or SAMPLE_INVOICE["seller_name"]
    vat_number = vat_number or SAMPLE_INVOICE["vat_number"]
    timestamp = timestamp or SAMPLE_INVOICE["timestamp"]
    invoice_hash = invoice_hash or SAMPLE_INVOICE["invoice_hash"]
    signature_value = signature_value or SAMPLE_INVOICE["signature_value"]
    certificate = certificate or SAMPLE_INVOICE["certificate"]

    if sar_total in (None, ""):
        sar_total = SAMPLE_INVOICE["sar_total"]
    if sar_vat in (None, ""):
        sar_vat = SAMPLE_INVOICE["sar_vat"]

    qr_b64 = build_phase2_qr_base64(
        seller_name=seller_name,
        vat_number=vat_number,
        timestamp=timestamp,
        sar_total=sar_total,
        sar_vat=sar_vat,
        invoice_hash=invoice_hash,
        signature_value=signature_value,
        certificate_b64=certificate,
    )
    png = _qr_png_bytes(qr_b64)

    file_name = f"TEMP-QR-SAR-{frappe.generate_hash(length=6)}.png"
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
        "qr_base64": qr_b64,
        "sar_total": _format_amount(sar_total),
        "sar_vat": _format_amount(sar_vat),
        "file_url": file_doc.file_url,
        "image_data_url": f"data:image/png;base64,{base64.b64encode(png).decode()}",
        "tags": {
            "1_seller": seller_name,
            "2_vat": vat_number,
            "3_timestamp": timestamp,
            "4_total_sar": _format_amount(sar_total),
            "5_vat_sar": _format_amount(sar_vat),
            "6_hash": invoice_hash,
        },
    }
