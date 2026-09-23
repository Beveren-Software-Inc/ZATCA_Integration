"""VAT Category classification used by the VAT Number / address validation.

Pure unit tests (no site/DB): ``common_util`` and ``overrides.customer`` resolve
categories through plain ``.get()``, so dicts stand in for documents.
"""

import unittest

import frappe

from zatca_integration.common_util import (
    EXPORT_VAT_CATEGORIES,
    REGISTERED_VAT_CATEGORIES,
    UNREGISTERED_VAT_CATEGORIES,
    canonical_vat_category,
    clean_vat_category,
    get_customer_vat_category,
    is_export_vat_category,
    is_foreign_customer,
    is_registered_vat_category,
    is_vat_registered_customer,
    normalize_vat_category,
)
from zatca_integration.overrides.customer import (
    get_overseas_reason,
    is_overseas_customer,
    is_saudi_registered_company,
)
from zatca_integration.overrides.supplier import (
    get_supplier_tax_number,
)
from zatca_integration.overrides.supplier import (
    validate as supplier_validate,
)


class TestNormalizeVatCategory(unittest.TestCase):
    def test_trims_collapses_spaces_and_folds_case(self):
        self.assertEqual(normalize_vat_category("  Overseas  "), "overseas")
        self.assertEqual(normalize_vat_category("Registered   Regular"), "registered regular")
        self.assertEqual(normalize_vat_category(None), "")
        self.assertEqual(normalize_vat_category("   "), "")


class TestRegisteredVatCategories(unittest.TestCase):
    def test_current_categories_are_recognised(self):
        for name in ("Registered", "B2B", "B2G", "Tax Deductors", "Tax Deductor"):
            self.assertTrue(is_registered_vat_category(name), name)

    def test_matching_is_case_and_space_insensitive(self):
        self.assertTrue(is_registered_vat_category("registered"))
        self.assertTrue(is_registered_vat_category(" B2B "))
        self.assertTrue(is_registered_vat_category("b2g"))

    def test_other_categories_are_not_registered(self):
        for name in ("Unregistered", "Government", "Exempt", "Exempt Entity", "B2C", "", None):
            self.assertFalse(is_registered_vat_category(name), repr(name))

    def test_removed_legacy_names_are_no_longer_registered(self):
        for name in (
            "Registered Regular",
            "Registered Composition",
            "SEZ",
            "UIN Holders",
            "Input Service Distributor",
            "Tax Collector",
        ):
            self.assertFalse(is_registered_vat_category(name), name)


class TestExportVatCategories(unittest.TestCase):
    def test_export_categories_are_recognised(self):
        for name in ("Overseas", "Oversees", "Deemed Export", "Export / Non-Resident", "Export"):
            self.assertTrue(is_export_vat_category(name), name)

    def test_matching_is_case_and_space_insensitive(self):
        self.assertTrue(is_export_vat_category("overseas"))
        self.assertTrue(is_export_vat_category("  export / non-resident "))

    def test_domestic_categories_are_not_export(self):
        for name in ("Registered", "Unregistered", "Government", "Exempt", "B2B", "B2G", ""):
            self.assertFalse(is_export_vat_category(name), repr(name))


class TestVanishingVatCategoryDefect(unittest.TestCase):
    """'VAT Category goes blank on save': options/values must match byte for byte.

    The options once shipped as '\\nRegistered\\t\\n\u2060Unregistered\\t\\n\u2060Overseas\\t\\n'
    ... — trailing TABs plus a U+2060 WORD JOINER. A Select field only renders a
    value that is byte-identical to one of its options, so such values showed
    blank and were cleared on the next save.
    """

    def test_clean_drops_invisible_characters_and_tabs(self):
        self.assertEqual(clean_vat_category("\u2060Unregistered\t"), "Unregistered")
        self.assertEqual(clean_vat_category("\u200bRegistered\ufeff"), "Registered")
        self.assertEqual(clean_vat_category(None), "")

    def test_dirty_option_and_value_normalize_identically(self):
        self.assertEqual(
            normalize_vat_category("\u2060Unregistered\t"),
            normalize_vat_category("Unregistered"),
        )
        self.assertEqual(normalize_vat_category("Overseas\t"), normalize_vat_category(" Overseas "))

    def test_canonical_vat_category_returns_the_exact_option(self):
        options = ["Registered", "Unregistered", "Overseas", "Government", "Exempt"]
        self.assertEqual(canonical_vat_category("\u2060Unregistered\t", options), "Unregistered")
        self.assertEqual(canonical_vat_category("registered", options), "Registered")
        self.assertEqual(canonical_vat_category("  OVERSEAS ", options), "Overseas")
        self.assertIsNone(canonical_vat_category("Oversees", options))
        self.assertIsNone(canonical_vat_category("", options))

    def test_dirty_values_are_still_classified_correctly(self):
        # Trailing tabs / word joiners must not change the classification.
        self.assertTrue(is_registered_vat_category("Registered\t"))
        self.assertTrue(is_registered_vat_category("\u2060B2B "))
        self.assertFalse(is_registered_vat_category("\u2060Unregistered\t"))
        self.assertTrue(is_export_vat_category("\u2060Overseas\t"))
        self.assertFalse(is_export_vat_category("\u2060Registered\t"))


class TestCategorySetsDoNotOverlap(unittest.TestCase):
    def test_no_category_belongs_to_two_groups(self):
        registered = {normalize_vat_category(n) for n in REGISTERED_VAT_CATEGORIES}
        unregistered = {normalize_vat_category(n) for n in UNREGISTERED_VAT_CATEGORIES}
        export = {normalize_vat_category(n) for n in EXPORT_VAT_CATEGORIES}

        self.assertEqual(registered & export, set())
        self.assertEqual(registered & unregistered, set())
        self.assertEqual(unregistered & export, set())


class TestCustomerCategoryHelpers(unittest.TestCase):
    def test_tax_category_link_wins_over_the_select(self):
        customer = {"tax_category": "B2B", "custom_vat_category": "Unregistered"}
        self.assertEqual(get_customer_vat_category(customer), "B2B")
        self.assertTrue(is_vat_registered_customer(customer))

    def test_select_is_used_when_the_link_is_empty(self):
        customer = {"tax_category": "", "custom_vat_category": "Registered"}
        self.assertEqual(get_customer_vat_category(customer), "Registered")
        self.assertTrue(is_vat_registered_customer(customer))

    def test_unregistered_government_and_exempt_are_not_registered(self):
        for category in ("Unregistered", "Government", "Exempt", "Exempt Entity", "B2C"):
            customer = {"custom_vat_category": category}
            self.assertFalse(is_vat_registered_customer(customer), category)

    def test_overseas_categories_are_never_forced_a_vat_number(self):
        # Regression: only "Export / Non-Resident" counted as export, so a Saudi
        # buyer with VAT Category "Overseas" was still asked for a VAT Number.
        for customer in (
            {"custom_country": "Saudi Arabia", "custom_vat_category": "Overseas"},
            {"custom_country": "Saudi Arabia", "custom_vat_category": "Oversees"},
            {"custom_country": "Saudi Arabia", "tax_category": "Deemed Export"},
            {"custom_country": "Saudi Arabia", "tax_category": "Export / Non-Resident"},
        ):
            self.assertTrue(is_foreign_customer(customer), customer)
            self.assertTrue(is_overseas_customer(customer), customer)

    def test_domestic_registered_company_is_not_foreign(self):
        customer = {"custom_country": "Saudi Arabia", "custom_vat_category": "Registered"}
        self.assertFalse(is_foreign_customer(customer))
        self.assertTrue(is_saudi_registered_company({**customer, "customer_type": "Company"}))

    def test_overseas_company_is_not_a_saudi_registered_company(self):
        doc = {
            "customer_type": "Company",
            "custom_country": "Saudi Arabia",
            "custom_vat_category": "Overseas",
        }
        self.assertTrue(is_overseas_customer(doc))
        self.assertFalse(is_saudi_registered_company(doc))

    def test_non_saudi_country_is_foreign(self):
        self.assertTrue(is_foreign_customer({"custom_country": "United Arab Emirates"}))
        self.assertTrue(is_overseas_customer({"custom_country": "United Arab Emirates"}))

    def test_country_and_category_matching_ignore_case(self):
        self.assertFalse(is_foreign_customer({"custom_country": "saudi arabia"}))
        self.assertTrue(
            is_foreign_customer(
                {"custom_country": "Saudi Arabia", "custom_vat_category": "overseas"}
            )
        )

    def test_overseas_reason_names_the_category_for_saudi_customers(self):
        reason = get_overseas_reason(
            {"custom_country": "Saudi Arabia", "custom_vat_category": "Overseas"}
        )
        self.assertIn("Overseas", reason)
        self.assertNotIn("outside Saudi Arabia", reason)

    def test_overseas_reason_names_the_country_when_abroad(self):
        reason = get_overseas_reason({"custom_country": "United Arab Emirates"})
        self.assertIn("United Arab Emirates", reason)
        self.assertIn("outside Saudi Arabia", reason)


class TestSupplierVatCategory(unittest.TestCase):
    """A VAT registered supplier must carry a Tax ID (VAT Number)."""

    def _supplier(self, category, **extra):
        doc = {"doctype": "Supplier", "supplier_name": "Test Supplier"}
        doc.update(extra)
        if category is not None:
            doc["custom_vat_category"] = category
        return doc

    def test_registered_supplier_without_tax_id_is_rejected(self):
        doc = self._supplier("Registered")
        with self.assertRaises(frappe.exceptions.ValidationError) as context:
            supplier_validate(doc)
        self.assertIn("Tax ID", str(context.exception))

    def test_registered_supplier_with_a_tax_id_passes(self):
        supplier_validate(self._supplier("Registered", tax_id="310460471100003"))

    def test_tax_category_link_registered_also_requires_a_tax_id(self):
        doc = {"doctype": "Supplier", "supplier_name": "Test Supplier", "tax_category": "B2B"}
        with self.assertRaises(frappe.exceptions.ValidationError):
            supplier_validate(doc)

    def test_other_categories_never_require_a_tax_id(self):
        for category in ("Unregistered", "Overseas", "Government", "Exempt", ""):
            supplier_validate(
                self._supplier(category),
            )

    def test_overseas_and_non_registered_suppliers_keep_saving(self):
        for category in ("Overseas", "Unregistered"):
            doc = self._supplier(category, country="United Arab Emirates", tax_id="AE123")
            supplier_validate(doc)

    def test_dirty_category_is_canonicalized_on_save(self):
        doc = self._supplier("\u2060Unregistered\t")
        supplier_validate(doc)
        self.assertEqual(doc["custom_vat_category"], "Unregistered")

    def test_malformed_tax_id_for_a_saudi_supplier_is_rejected(self):
        doc = self._supplier("Registered", country="Saudi Arabia", tax_id="12345")
        with self.assertRaises(frappe.exceptions.ValidationError) as context:
            supplier_validate(doc)
        self.assertIn("Tax ID", str(context.exception))

    def test_tax_number_lookup_order(self):
        self.assertEqual(
            get_supplier_tax_number({"tax_id": " 310460471100003 "}), "310460471100003"
        )
        self.assertEqual(get_supplier_tax_number({"custom_vat_number": "X"}), "X")
        self.assertEqual(get_supplier_tax_number({}), "")
