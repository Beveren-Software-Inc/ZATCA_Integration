import base64
import re
import unittest
from pathlib import Path
from unittest import mock

from zatca_integration.clearence_util import (
    _encode_tlv_fields,
    _needs_sar_qr_code,
    _parse_tlv_fields,
    build_sar_qr_code_base64,
)
from zatca_integration.saudi_arabia_electronic_invoicing import temp_qr_generator
from zatca_integration.saudi_arabia_electronic_invoicing.temp_qr_generator import (
    DEFAULT_INVOICE,
    SAMPLE_INVOICE,
    SAMPLE_INVOICES,
    _format_amount,
    build_sar_qr_from_original,
    describe_qr_change,
    get_invoice_defaults,
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
        # The synthetic QR carries INV-20133496's hash, not the known invoice's.
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

    def test_live_inv_20135424_qr_is_parsed_correctly(self):
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

        self.assertEqual(after[4], b"224234.17")
        for tag in (1, 2, 3, 5, 6, 7, 8, 9):
            self.assertEqual(after[tag], before[tag], f"tag {tag} must stay identical")

        change = describe_qr_change(original_qr, sar_qr)
        self.assertEqual(change["changed_tags"], [4])
        self.assertTrue(change["only_amounts_changed"])
        self.assertTrue(change["preserved_tags_ok"])
        self.assertTrue(change["hash_matches_invoice"])
        self.assertEqual(change["original_total"], "60116.40")
        self.assertEqual(change["original_vat"], "0.00")
        self.assertEqual(change["sar_total"], "224234.17")
        self.assertEqual(change["hash"], SAMPLE_INVOICE["qr_hash"])

    def test_qr_hash_is_the_signed_xml_digest(self):
        """Tag 6 is the signed XML's digest, never Sales Invoice.custom_invoice_hash.

        ``custom_invoice_hash`` holds the hash of the *cleared* invoice and is
        only used by the app's PIH chain, so it must never reach the snapshot.
        """
        tags = parse_qr_tags(SAMPLE_INVOICE["original_qr"])
        self.assertEqual(tags[6], SAMPLE_INVOICE["qr_hash"])
        self.assertNotIn("custom_invoice_hash", SAMPLE_INVOICE)


class TestTempSarQrSingleKnownInvoice(unittest.TestCase):
    """Only the recent live invoice (INV-20135424) is registered.

    The temp tool used to know two invoices, which is how one invoice's QR
    could end up in a file named after another one. Now a single snapshot is
    registered, the dialog falls back to it and the one-click buttons use it —
    an invoice the tool does not know is never prefilled from a snapshot.
    """

    def test_only_the_recent_invoice_is_known(self):
        self.assertEqual(list(SAMPLE_INVOICES), ["INV-20135424"])
        self.assertEqual(DEFAULT_INVOICE, "INV-20135424")
        self.assertEqual(SAMPLE_INVOICE["invoice"], DEFAULT_INVOICE)
        self.assertEqual(SAMPLE_INVOICES[DEFAULT_INVOICE], SAMPLE_INVOICE)

    def test_known_invoices_hint_lists_only_that_invoice(self):
        stub = mock.MagicMock()
        stub.db.exists.return_value = False  # not on this site -> manual

        with mock.patch.object(temp_qr_generator, "frappe", stub):
            defaults = temp_qr_generator.get_temp_qr_defaults("INV-NOT-HERE")

        self.assertEqual(defaults["known_invoices"], ["INV-20135424"])
        self.assertEqual(defaults["default_invoice"], "INV-20135424")

    def test_another_invoice_is_not_prefilled_from_the_snapshot(self):
        """The invoice the mix-up came from must not be prefilled any more."""
        stub = mock.MagicMock()
        stub.db.exists.return_value = False

        with mock.patch.object(temp_qr_generator, "frappe", stub):
            defaults = get_invoice_defaults("INV-20134837")

        self.assertEqual(defaults["source"], "manual")
        self.assertEqual(defaults["invoice"], "INV-20134837")
        self.assertEqual(defaults["original_qr"], "")
        self.assertEqual(defaults["sar_total"], "")
        self.assertEqual(defaults["qr_hash"], "")

    def test_sar_total_is_the_usd_total_converted(self):
        usd_total = float(SAMPLE_INVOICE["usd_total"])
        rate = float(SAMPLE_INVOICE["conversion_rate"])
        self.assertAlmostEqual(
            usd_total * rate,
            float(SAMPLE_INVOICE["sar_total"]),
            places=2,
        )

    def test_known_invoice_defaults_come_from_the_snapshot(self):
        defaults = get_invoice_defaults("INV-20135424")
        self.assertEqual(defaults["source"], "snapshot")
        self.assertEqual(defaults["invoice"], "INV-20135424")
        self.assertEqual(defaults["sar_total"], "224234.17")
        self.assertEqual(defaults["sar_vat"], "0.00")
        self.assertEqual(defaults["original_qr"], SAMPLE_INVOICE["original_qr"])
        self.assertEqual(defaults["qr_hash"], SAMPLE_INVOICE["qr_hash"])

    def test_blank_invoice_falls_back_to_the_default_snapshot(self):
        self.assertEqual(get_invoice_defaults()["invoice"], DEFAULT_INVOICE)
        self.assertEqual(get_invoice_defaults("")["invoice"], DEFAULT_INVOICE)
        self.assertEqual(get_invoice_defaults("   ")["invoice"], DEFAULT_INVOICE)

    def test_unknown_hash_skips_the_warning(self):
        """An invoice the backend cannot verify must not raise a false alarm."""
        original_qr = SAMPLE_INVOICE["original_qr"]
        change = describe_qr_change(
            original_qr,
            build_sar_qr_from_original(original_qr, "1.00", "0.00"),
            None,
        )
        self.assertTrue(change["hash_matches_invoice"])

    def test_a_foreign_hash_is_still_flagged(self):
        original_qr = SAMPLE_INVOICE["original_qr"]
        change = describe_qr_change(
            original_qr,
            build_sar_qr_from_original(original_qr, "1.00", "0.00"),
            "another-invoice-hash=",
        )
        self.assertFalse(change["hash_matches_invoice"])

    def test_quick_button_label_names_the_backend_invoice(self):
        """The button label and the invoice the backend generates for agree."""
        js_file = Path(temp_qr_generator.__file__).parents[1] / "public" / "js" / "temp_sar_qr.js"
        match = re.search(r'quick_invoice\s*=\s*"([^"]+)"', js_file.read_text(encoding="utf-8"))
        self.assertIsNotNone(match, "temp_sar_qr.js must define frappe.zatca_temp_qr.quick_invoice")
        self.assertEqual(match.group(1), DEFAULT_INVOICE)


class _StubDoc:
    """Minimal stand-in for a frappe document (no DB needed for these tests)."""

    def __init__(self, **values):
        self._values = values

    def get(self, fieldname):
        return self._values.get(fieldname)


class _StubFile:
    def __init__(self, content):
        self._content = content

    def get_content(self):
        return self._content


def _stub_frappe(invoice_doc, xml):
    """A frappe whose ``get_doc`` returns ``invoice_doc`` and the XML File."""
    stub = mock.MagicMock()
    stub.db.exists.return_value = True
    stub.get_doc.side_effect = lambda doctype, *args: (
        invoice_doc if doctype == "Sales Invoice" else _StubFile(xml)
    )
    return stub


class TestInvoiceQrFromSite(unittest.TestCase):
    """The site branch: any invoice that carries its own ``custom_invoice_xml``.

    These tests stub out ``frappe``, so they run without a bench/site; the real
    end-to-end path is checked against a live site separately.
    """

    @staticmethod
    def _invoice_doc():
        return _StubDoc(
            custom_invoice_xml="/files/INV-20135424.xml",
            currency="USD",
            conversion_rate=3.73,
            base_grand_total=224234.172,
            base_total_taxes_and_charges=0.0,
            customer="Mazare Al Nakheel Company for Dates",
        )

    def test_site_invoice_is_read_from_its_own_xml(self):
        payload = SAMPLE_INVOICE["original_qr"]
        stub = _stub_frappe(self._invoice_doc(), _wrap_in_invoice_xml(payload))

        with mock.patch.object(temp_qr_generator, "frappe", stub):
            defaults = temp_qr_generator.get_invoice_defaults("INV-XYZ-0001")

        self.assertEqual(defaults["source"], "site")
        self.assertEqual(defaults["invoice"], "INV-XYZ-0001")
        self.assertEqual(defaults["original_qr"], payload)
        self.assertEqual(defaults["seller_name"], SAMPLE_INVOICE["seller_name"])
        self.assertEqual(defaults["vat_number"], SAMPLE_INVOICE["vat_number"])
        self.assertEqual(defaults["timestamp"], SAMPLE_INVOICE["timestamp"])
        self.assertEqual(defaults["document_currency"], "USD")
        self.assertEqual(defaults["conversion_rate"], "3.73")
        self.assertEqual(defaults["usd_total"], SAMPLE_INVOICE["usd_total"])
        self.assertEqual(defaults["usd_vat"], SAMPLE_INVOICE["usd_vat"])
        self.assertEqual(defaults["sar_total"], SAMPLE_INVOICE["sar_total"])
        self.assertEqual(defaults["sar_vat"], SAMPLE_INVOICE["sar_vat"])
        self.assertEqual(defaults["qr_hash"], SAMPLE_INVOICE["qr_hash"])

    def test_site_defaults_can_be_generated_without_an_explicit_qr(self):
        """The dialog may post only the invoice: the QR then comes from the site."""
        payload = SAMPLE_INVOICE["original_qr"]
        stub = _stub_frappe(self._invoice_doc(), _wrap_in_invoice_xml(payload))

        with mock.patch.object(temp_qr_generator, "frappe", stub):
            defaults = temp_qr_generator.get_temp_qr_defaults("INV-XYZ-0005")

        self.assertEqual(defaults["source"], "site")
        self.assertEqual(defaults["known_invoices"], list(SAMPLE_INVOICES))
        self.assertEqual(defaults["default_invoice"], DEFAULT_INVOICE)

    def test_invoice_without_qr_xml_falls_back_to_manual(self):
        invoice_doc = _StubDoc(custom_invoice_xml=None, currency="USD")
        stub = _stub_frappe(invoice_doc, "")

        with mock.patch.object(temp_qr_generator, "frappe", stub):
            defaults = temp_qr_generator.get_invoice_defaults("INV-XYZ-0002")

        self.assertEqual(defaults["source"], "manual")
        self.assertEqual(defaults["original_qr"], "")
        # Blank on purpose: an unverifiable payload must not warn about the hash.
        self.assertEqual(defaults["qr_hash"], "")

    def test_invoice_that_is_not_on_this_site_falls_back_to_manual(self):
        stub = mock.MagicMock()
        stub.db.exists.return_value = False

        with mock.patch.object(temp_qr_generator, "frappe", stub):
            defaults = temp_qr_generator.get_invoice_defaults("INV-XYZ-0003")

        self.assertEqual(defaults["source"], "manual")
        self.assertEqual(defaults["original_qr"], "")
        stub.get_doc.assert_not_called()
        stub.log_error.assert_not_called()

    def test_unreadable_xml_is_logged_and_falls_back_to_manual(self):
        stub = _stub_frappe(self._invoice_doc(), None)  # get_content() -> None

        with mock.patch.object(temp_qr_generator, "frappe", stub):
            defaults = temp_qr_generator.get_invoice_defaults("INV-XYZ-0004")

        self.assertEqual(defaults["source"], "manual")
        self.assertEqual(defaults["original_qr"], "")
        stub.log_error.assert_called_once()


class _StubGeneratedFile:
    """Stands in for the File doc ``frappe.get_doc({...})`` builds."""

    def __init__(self, file_url):
        self.file_url = file_url
        self.saved = False

    def save(self, **kwargs):
        self.saved = True
        self.save_kwargs = kwargs


class TestGenerateDefaultTempQr(unittest.TestCase):
    """The one-click button (INV-20135424): nothing is typed in the browser.

    ``generate_default_temp_qr`` resolves the invoice, its original QR and the
    SAR amounts itself, so the button cannot produce another invoice's QR.
    """

    def _generate(self, invoice_on_site, **kwargs):
        self.file_doc = _StubGeneratedFile("/files/TEMP-INV-20135424-QR-SAR-abc123.png")
        self.spec = {}

        def _get_doc(spec, *_args, **_ignored):
            if isinstance(spec, dict):
                self.spec = spec
            return self.file_doc

        stub = mock.MagicMock()
        stub.db.exists.return_value = invoice_on_site
        stub.generate_hash.return_value = "abc123"
        stub.get_doc.side_effect = _get_doc

        with mock.patch.object(temp_qr_generator, "frappe", stub):
            result = temp_qr_generator.generate_default_temp_qr(**kwargs)

        self.stub = stub
        return result

    def test_no_input_is_needed(self):
        result = self._generate(False, company="Rqeem Ltd")

        self.assertEqual(result["invoice"], "INV-20135424")
        self.assertEqual(result["source"], "snapshot")
        self.assertEqual(result["sar_total"], "224234.17")
        self.assertEqual(result["sar_vat"], "0.00")
        self.assertEqual(result["hash"], SAMPLE_INVOICE["qr_hash"])
        self.assertTrue(result["hash_matches_invoice"])
        self.assertTrue(result["only_amounts_changed"])
        self.assertTrue(result["preserved_tags_ok"])
        self.assertEqual(result["changed_tags"], [4])

    def test_only_tags_4_and_5_differ_from_the_invoice_qr(self):
        result = self._generate(False)
        before = dict(_parse_tlv_fields(base64.b64decode(SAMPLE_INVOICE["original_qr"])))
        after = dict(_parse_tlv_fields(base64.b64decode(result["qr_base64"])))

        self.assertEqual(after[4], b"224234.17")
        for tag in (1, 2, 3, 6, 7, 8, 9):
            self.assertEqual(after[tag], before[tag], f"tag {tag} must stay identical")

        self.assertTrue(result["image_data_url"].startswith("data:image/png;base64,"))
        self.assertTrue(result["file_url"].endswith(".png"))
        self.assertTrue(self.file_doc.saved)

    def test_file_name_names_the_invoice(self):
        self._generate(False)

        self.assertEqual(self.spec["file_name"], "TEMP-INV-20135424-QR-SAR-abc123.png")
        self.assertEqual(self.spec["is_private"], 0)

    def test_file_goes_to_the_invoice_when_the_site_has_it(self):
        # Clicked on the Company form, but the invoice exists here: the file
        # belongs on the invoice.
        result = self._generate(
            True,
            company="Rqeem Ltd",
            attach_to_doctype="Company",
            attach_to_name="Rqeem Ltd",
        )

        self.assertEqual(result["attach_to_doctype"], "Sales Invoice")
        self.assertEqual(result["attach_to_name"], "INV-20135424")
        self.assertEqual(self.spec["attached_to_name"], "INV-20135424")

    def test_file_never_lands_on_another_sales_invoice(self):
        result = self._generate(
            False,
            company="Rqeem Ltd",
            attach_to_doctype="Sales Invoice",
            attach_to_name="INV-XYZ-0001",
        )

        self.assertEqual(result["attach_to_doctype"], "Company")
        self.assertEqual(result["attach_to_name"], "Rqeem Ltd")
        self.assertEqual(self.spec["attached_to_name"], "Rqeem Ltd")

    def test_file_falls_back_to_the_company(self):
        result = self._generate(False, company="Rqeem Ltd")

        self.assertEqual(result["attach_to_doctype"], "Company")
        self.assertEqual(result["attach_to_name"], "Rqeem Ltd")
        self.assertEqual(self.spec["attached_to_doctype"], "Company")
        self.assertEqual(self.spec["attached_to_name"], "Rqeem Ltd")
