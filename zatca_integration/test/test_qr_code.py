import base64
import unittest

from zatca_integration.clearence_util import (
    _encode_tlv_fields,
    _needs_sar_qr_code,
    _parse_tlv_fields,
    build_sar_qr_code_base64,
)


def _tlv(tag, value):
    """Build a single ZATCA TLV field (mirrors the signing engine encoding)."""
    if isinstance(value, str):
        value = value.encode("utf-8")
    if len(value) < 256:
        return bytes([tag, len(value)]) + value
    return bytes([tag, 0xFF]) + len(value).to_bytes(2, "big") + value


def _wrap_in_invoice_xml(qr_base64):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cac:AdditionalDocumentReference>
    <cbc:ID>QR</cbc:ID>
    <cac:Attachment>
      <cbc:EmbeddedDocumentBinaryObject>{qr_base64}</cbc:EmbeddedDocumentBinaryObject>
    </cac:Attachment>
  </cac:AdditionalDocumentReference>
</Invoice>"""


def _sample_usd_tlv():
    """Phase-2 QR of a USD B2B invoice: tags 4 & 5 hold document-currency amounts."""
    return b"".join(
        [
            _tlv(1, "Mazare Al Nakheel Company for Dates"),
            _tlv(2, "310460471100003"),
            _tlv(3, "2026-09-16T10:33:22"),
            _tlv(4, "59037.60"),
            _tlv(5, "0.00"),
            _tlv(6, "2obSEzlf6TaxgBkjCTNfR6v3HgfF6+iUVbBI7ensVuQ="),
            _tlv(7, "MEUCIQDR/7L1GBDAdAkfobVYjjYOE9wUpTQWvYNUfXTFGQ8RwwIgVDAbWop="),
            _tlv(8, bytes([0x30, 0x59, 0x30, 0x13])),
            _tlv(9, bytes([0x30, 0x45, 0x02, 0x21])),
        ]
    )


class TestNeedsSarQrCode(unittest.TestCase):
    """The SAR QR is only for foreign-currency invoices (document != tax currency)."""

    def test_foreign_currency_needs_sar_qr(self):
        self.assertTrue(_needs_sar_qr_code("USD", "SAR"))
        self.assertTrue(_needs_sar_qr_code("EUR", "SAR"))

    def test_sar_invoice_does_not_need_sar_qr(self):
        self.assertFalse(_needs_sar_qr_code("SAR", "SAR"))

    def test_missing_document_currency_does_not_need_sar_qr(self):
        self.assertFalse(_needs_sar_qr_code(None, "SAR"))
        self.assertFalse(_needs_sar_qr_code("", "SAR"))

    def test_tax_currency_falls_back_to_sar(self):
        self.assertTrue(_needs_sar_qr_code("USD", None))
        self.assertFalse(_needs_sar_qr_code("SAR", None))


class TestSarQrCode(unittest.TestCase):
    """Tests for the B2B SAR (company-currency) QR code generation.

    These cover pure TLV helpers, so they intentionally avoid FrappeTestCase
    (no site/DB is required to run them).
    """

    def test_tlv_round_trip(self):
        tlv_bytes = _sample_usd_tlv()
        fields = _parse_tlv_fields(tlv_bytes)
        self.assertEqual(len(fields), 9)
        self.assertEqual(fields[3], (4, b"59037.60"))
        self.assertEqual(_encode_tlv_fields(fields), tlv_bytes)

    def test_sar_amounts_replace_tags_4_and_5(self):
        xml = _wrap_in_invoice_xml(base64.b64encode(_sample_usd_tlv()).decode("utf-8"))
        sar_qr = build_sar_qr_code_base64(xml, 220210.25, 0.00)
        self.assertTrue(sar_qr)

        sar_fields = dict(_parse_tlv_fields(base64.b64decode(sar_qr)))
        self.assertEqual(sar_fields[4], b"220210.25")
        self.assertEqual(sar_fields[5], b"0.00")

    def test_signed_tags_are_preserved(self):
        tlv_bytes = _sample_usd_tlv()
        expected = dict(_parse_tlv_fields(tlv_bytes))
        xml = _wrap_in_invoice_xml(base64.b64encode(tlv_bytes).decode("utf-8"))
        sar_qr = build_sar_qr_code_base64(xml, 220210.25, 0.00)

        sar_fields = dict(_parse_tlv_fields(base64.b64decode(sar_qr)))
        for tag in (1, 2, 3, 6, 7, 8, 9):
            self.assertEqual(sar_fields[tag], expected[tag], f"tag {tag} must be unchanged")

    def test_multibyte_length_is_handled(self):
        long_value = "A" * 300
        tlv_bytes = _tlv(1, "seller") + _tlv(4, long_value) + _tlv(5, "0.00")
        xml = _wrap_in_invoice_xml(base64.b64encode(tlv_bytes).decode("utf-8"))
        sar_qr = build_sar_qr_code_base64(xml, "100.5", "15")

        sar_fields = dict(_parse_tlv_fields(base64.b64decode(sar_qr)))
        self.assertEqual(sar_fields[1], b"seller")
        self.assertEqual(sar_fields[4], b"100.50")
        self.assertEqual(sar_fields[5], b"15.00")

    def test_missing_qr_returns_none(self):
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"/>'
        )
        self.assertIsNone(build_sar_qr_code_base64(xml, 1, 1))
