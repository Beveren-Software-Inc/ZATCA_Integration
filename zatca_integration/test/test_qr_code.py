import base64
import unittest

from zatca_integration.clearence_util import (
    _encode_tlv_fields,
    _needs_sar_qr_code,
    _parse_tlv_fields,
    build_sar_qr_code_base64,
)
from zatca_integration.saudi_arabia_electronic_invoicing.temp_qr_generator import (
    SAMPLE_INVOICE,
    _format_amount,
    build_sar_qr_from_original,
    describe_qr_change,
    parse_qr_tags,
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


class TestTempSarQrGenerator(unittest.TestCase):
    """TEMPORARY Company tool: only QR tags 4 & 5 change — nothing else.

    Covers the pure helpers used by ``temp_qr_generator`` (no site/DB needed).
    """

    def _original_qr(self):
        """A currency QR (tags 4 & 5 in USD) shaped like the real B2B QR."""
        return base64.b64encode(_sample_usd_tlv()).decode("utf-8")

    def _sar_qr(self, sar_total="164316.87", sar_vat="0.00"):
        return build_sar_qr_from_original(self._original_qr(), sar_total, sar_vat)

    def _sar_tags(self, source=None, sar_total="164316.87", sar_vat="0.00"):
        source = self._original_qr() if source is None else source
        sar_qr = build_sar_qr_from_original(source, sar_total, sar_vat)
        return dict(_parse_tlv_fields(base64.b64decode(sar_qr)))

    def test_sar_amounts_replace_tags_4_and_5(self):
        fields = self._sar_tags()
        self.assertEqual(fields[4], b"164316.87")
        self.assertEqual(fields[5], b"0.00")

    def test_every_other_tag_is_byte_identical(self):
        original = dict(_parse_tlv_fields(_sample_usd_tlv()))
        fields = self._sar_tags()
        for tag in (1, 2, 3, 6, 7, 8, 9):
            self.assertEqual(fields[tag], original[tag], f"tag {tag} must stay identical")

    def test_hash_stays_the_same_as_the_currency_qr(self):
        original = dict(_parse_tlv_fields(_sample_usd_tlv()))
        fields = self._sar_tags()
        self.assertEqual(fields[6], original[6])
        self.assertEqual(fields[6], b"2obSEzlf6TaxgBkjCTNfR6v3HgfF6+iUVbBI7ensVuQ=")

    def test_signature_and_certificate_are_untouched(self):
        original = dict(_parse_tlv_fields(_sample_usd_tlv()))
        fields = self._sar_tags()
        self.assertEqual(fields[7], original[7])
        self.assertEqual(fields[8], original[8])
        self.assertEqual(fields[9], original[9])

    def test_document_currency_totals_do_not_survive(self):
        fields = self._sar_tags()
        self.assertNotEqual(fields[4].decode(), "59037.60")

    def test_signed_xml_can_be_used_as_the_source(self):
        source = _wrap_in_invoice_xml(self._original_qr())
        fields = self._sar_tags(source=source)
        self.assertEqual(fields[4], b"164316.87")
        self.assertEqual(fields[6], b"2obSEzlf6TaxgBkjCTNfR6v3HgfF6+iUVbBI7ensVuQ=")

    def test_amounts_are_always_two_decimals(self):
        fields = self._sar_tags(sar_total="164316.8694", sar_vat="15")
        self.assertEqual(fields[4], b"164316.87")
        self.assertEqual(fields[5], b"15.00")

    def test_parse_qr_tags_reads_all_nine_tags(self):
        tags = parse_qr_tags(self._original_qr())
        self.assertEqual(sorted(tags), [1, 2, 3, 4, 5, 6, 7, 8, 9])
        self.assertEqual(tags[4], "59037.60")

    def test_describe_qr_change_reports_only_the_amounts(self):
        change = describe_qr_change(self._original_qr(), self._sar_qr())
        # VAT is 0.00 in both currencies, so only tag 4 differs byte-wise.
        self.assertEqual(change["changed_tags"], [4])
        self.assertTrue(change["only_amounts_changed"])
        self.assertTrue(change["preserved_tags_ok"])
        self.assertEqual(change["original_total"], "59037.60")
        self.assertEqual(change["original_vat"], "0.00")
        self.assertEqual(change["sar_total"], "164316.87")
        self.assertEqual(change["sar_vat"], "0.00")

    def test_describe_qr_change_reports_tag_5_when_vat_differs(self):
        change = describe_qr_change(self._original_qr(), self._sar_qr(sar_vat="8400.00"))
        self.assertEqual(change["changed_tags"], [4, 5])
        self.assertTrue(change["only_amounts_changed"])

    def test_describe_qr_change_flags_non_amount_differences(self):
        other = _tlv(1, "Other Seller") + _tlv(4, "1.00") + _tlv(5, "0.00")
        change = describe_qr_change(self._original_qr(), base64.b64encode(other).decode("utf-8"))
        self.assertFalse(change["only_amounts_changed"])
        self.assertFalse(change["preserved_tags_ok"])

    def test_describe_qr_change_flags_a_foreign_hash(self):
        change = describe_qr_change(self._original_qr(), self._sar_qr())
        # The sample QR carries the INV-20133496 hash, not INV-20134837's.
        self.assertFalse(change["hash_matches_invoice"])

    def test_missing_or_unusable_qr_returns_none(self):
        self.assertIsNone(build_sar_qr_from_original("", 1, 1))
        self.assertIsNone(build_sar_qr_from_original("   ", 1, 1))
        self.assertIsNone(build_sar_qr_from_original("not-base64", 1, 1))
        self.assertIsNone(
            build_sar_qr_from_original(
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"/>',
                1,
                1,
            )
        )

    def test_line_wrapped_base64_paste_is_accepted(self):
        original = self._original_qr()
        wrapped = "\n".join(original[i : i + 64] for i in range(0, len(original), 64))
        fields = self._sar_tags(source=wrapped)
        self.assertEqual(fields[4], b"164316.87")

    def test_bytes_and_bom_xml_pastes_are_accepted(self):
        fields = self._sar_tags(source=base64.b64encode(_sample_usd_tlv()))
        self.assertEqual(fields[4], b"164316.87")

        bom_xml = "\ufeff" + _wrap_in_invoice_xml(self._original_qr())
        fields = self._sar_tags(source=bom_xml)
        self.assertEqual(fields[4], b"164316.87")

    def test_qr_without_tag_4_returns_none(self):
        tlv = _tlv(1, "seller") + _tlv(2, "300000000000003") + _tlv(5, "0.00")
        self.assertIsNone(build_sar_qr_from_original(base64.b64encode(tlv).decode("utf-8"), 10, 0))

    def test_amounts_are_formatted_to_two_decimals(self):
        self.assertEqual(_format_amount(164316.8694), "164316.87")
        self.assertEqual(_format_amount(164316), "164316.00")
        self.assertEqual(_format_amount("0"), "0.00")
        self.assertEqual(_format_amount(None), "0.00")
        self.assertEqual(_format_amount("44052.78"), "44052.78")

    def test_live_inv_20134837_qr_is_parsed_correctly(self):
        """The baked-in payload is the real QR from the live signed XML."""
        tags = parse_qr_tags(SAMPLE_INVOICE["original_qr"])
        self.assertEqual(sorted(tags), [1, 2, 3, 4, 5, 6, 7, 8, 9])
        self.assertEqual(tags[1], SAMPLE_INVOICE["seller_name"])
        self.assertEqual(tags[2], SAMPLE_INVOICE["vat_number"])
        self.assertEqual(tags[3], SAMPLE_INVOICE["timestamp"])
        self.assertEqual(tags[4], SAMPLE_INVOICE["usd_total"])
        self.assertEqual(tags[5], SAMPLE_INVOICE["usd_vat"])
        self.assertEqual(tags[6], SAMPLE_INVOICE["qr_hash"])

    def test_live_qr_only_changes_tag_4(self):
        original_qr = SAMPLE_INVOICE["original_qr"]
        sar_qr = build_sar_qr_from_original(original_qr, SAMPLE_INVOICE["sar_total"], "0.00")
        before = dict(_parse_tlv_fields(base64.b64decode(original_qr)))
        after = dict(_parse_tlv_fields(base64.b64decode(sar_qr)))

        self.assertEqual(after[4], b"164316.87")
        for tag in (1, 2, 3, 5, 6, 7, 8, 9):
            self.assertEqual(after[tag], before[tag], f"tag {tag} must stay identical")

        change = describe_qr_change(original_qr, sar_qr)
        self.assertEqual(change["changed_tags"], [4])
        self.assertTrue(change["only_amounts_changed"])
        self.assertTrue(change["preserved_tags_ok"])
        self.assertTrue(change["hash_matches_invoice"])
        self.assertEqual(change["original_total"], "44052.78")
        self.assertEqual(change["original_vat"], "0.00")
        self.assertEqual(change["sar_total"], "164316.87")
        self.assertEqual(change["hash"], SAMPLE_INVOICE["qr_hash"])

    def test_qr_hash_is_not_the_recorded_invoice_hash(self):
        """custom_invoice_hash holds the cleared-invoice hash, not QR tag 6."""
        tags = parse_qr_tags(SAMPLE_INVOICE["original_qr"])
        self.assertNotEqual(tags[6], "KZpJY3uNAnGpNG3XTKC6dOYAEQw+VBqiJb2FyU2gaas=")
