"""Quick-entry Address hand-over (Customer / Supplier → primary Address).

Pure unit tests: the helpers only use ``doc.get`` / ``doc.set`` / ``doc.is_new``
and ``frappe.flags``, so no site or database is needed.

ERPNext's ``Customer.make_address`` / ``Supplier.make_address`` copy the standard
address fields but not City Name (``county``) or the Arabic fields. The party
``validate`` hooks therefore stash those values in ``frappe.flags`` and the
Address ``validate`` hook puts them on the new, linked Address.
"""

import unittest
from unittest.mock import patch

import frappe

from zatca_integration.overrides import customer, supplier
from zatca_integration.overrides.address import (
    apply_quick_entry_address_values,
    requires_saudi_national_address,
)
from zatca_integration.overrides.customer import stash_quick_entry_address_values

FLAG = "zatca_quick_entry_address"


class FakeDoc:
    """Minimal stand-in for a Frappe Document (get / set / is_new)."""

    def __init__(self, doctype="Address", name="ADDR-0001", is_new=True, links=None, **values):
        self.doctype = doctype
        self.name = name
        self._is_new = is_new
        self._values = dict(values)
        self._values.setdefault("links", list(links or ()))

    def get(self, fieldname, default=None):
        return self._values.get(fieldname, default)

    def set(self, fieldname, value):
        self._values[fieldname] = value

    def is_new(self):
        return self._is_new

    def __getitem__(self, key):
        return self._values[key]


class FlagsTestCase(unittest.TestCase):
    def setUp(self):
        # frappe.flags is request-bound; a plain dict gives the same behaviour
        # (attribute + .get) without a site, and isolates every test.
        self.flags = frappe._dict()
        patcher = patch.object(frappe, "flags", self.flags)
        patcher.start()
        self.addCleanup(patcher.stop)

    def stash(self):
        return self.flags.get(FLAG)


class TestStashQuickEntryAddressValues(FlagsTestCase):
    def test_new_party_keeps_city_name_and_arabic_values(self):
        doc = FakeDoc(
            doctype="Customer",
            name="CUST-0001",
            address_line1="King Fahd Road",
            county="Riyadh",
            custom_city_in_arabic="الرياض",
            custom_street_in_arabic="",
            pincode="12345",
        )

        stash_quick_entry_address_values(doc)

        self.assertEqual(
            self.stash(),
            {
                "link_doctype": "Customer",
                "link_name": "CUST-0001",
                "values": {"county": "Riyadh", "custom_city_in_arabic": "الرياض"},
            },
        )

    def test_india_compliance_street_alias_is_accepted(self):
        doc = FakeDoc(
            doctype="Customer",
            name="CUST-0002",
            _address_line1="King Fahd Road",
            county="Jeddah",
        )

        stash_quick_entry_address_values(doc)

        self.assertEqual(self.stash()["values"], {"county": "Jeddah"})

    def test_existing_party_is_ignored(self):
        doc = FakeDoc(
            name="CUST-0003",
            is_new=False,
            address_line1="King Fahd Road",
            county="Riyadh",
        )

        stash_quick_entry_address_values(doc)

        self.assertIsNone(self.stash())

    def test_party_without_a_street_is_ignored(self):
        # No street means ERPNext does not create a primary Address at all.
        doc = FakeDoc(doctype="Customer", name="CUST-0004", county="Riyadh")

        stash_quick_entry_address_values(doc)

        self.assertIsNone(self.stash())

    def test_street_only_stashes_nothing(self):
        doc = FakeDoc(doctype="Customer", name="CUST-0005", address_line1="King Fahd Road")

        stash_quick_entry_address_values(doc)

        self.assertIsNone(self.stash())

    def test_customer_validate_wires_the_stash(self):
        doc = FakeDoc(
            doctype="Customer",
            name="CUST-0006",
            customer_type="Individual",
            address_line1="King Fahd Road",
            county="Riyadh",
        )

        with patch("zatca_integration.overrides.customer.canonicalize_vat_category_field"):
            customer.validate(doc)

        self.assertEqual(self.stash()["link_name"], "CUST-0006")
        self.assertEqual(self.stash()["values"], {"county": "Riyadh"})

    def test_supplier_validate_wires_the_stash(self):
        doc = FakeDoc(
            doctype="Supplier",
            name="SUP-0001",
            custom_vat_category="Unregistered",
            address_line1="King Fahd Road",
            county="Dammam",
            custom_city_in_arabic="الدمام",
        )

        with patch("zatca_integration.overrides.supplier.canonicalize_vat_category_field"):
            supplier.validate(doc)

        self.assertEqual(self.stash()["link_doctype"], "Supplier")
        self.assertEqual(
            self.stash()["values"],
            {"county": "Dammam", "custom_city_in_arabic": "الدمام"},
        )


class TestApplyQuickEntryAddressValues(FlagsTestCase):
    def setUp(self):
        super().setUp()
        self.flags[FLAG] = {
            "link_doctype": "Customer",
            "link_name": "CUST-0001",
            "values": {"county": "Riyadh", "custom_city_in_arabic": "الرياض"},
        }

    def _address(self, **kwargs):
        kwargs.setdefault("links", [frappe._dict(link_doctype="Customer", link_name="CUST-0001")])
        return FakeDoc(**kwargs)

    def test_fills_empty_fields_on_the_new_linked_address(self):
        address = self._address(address_line1="King Fahd Road")

        apply_quick_entry_address_values(address)

        self.assertEqual(address.get("county"), "Riyadh")
        self.assertEqual(address.get("custom_city_in_arabic"), "الرياض")
        self.assertIsNone(self.stash())

    def test_values_typed_in_the_address_form_win(self):
        address = self._address(county="Jeddah", custom_city_in_arabic="جدة")

        apply_quick_entry_address_values(address)

        self.assertEqual(address.get("county"), "Jeddah")
        self.assertEqual(address.get("custom_city_in_arabic"), "جدة")
        self.assertIsNone(self.stash())

    def test_address_for_another_party_is_left_alone(self):
        address = FakeDoc(
            links=[frappe._dict(link_doctype="Supplier", link_name="SUP-0001")],
        )

        apply_quick_entry_address_values(address)

        self.assertIsNone(address.get("county"))
        # The stash stays available for the Address of the party that set it.
        self.assertIsNotNone(self.stash())

    def test_saved_address_is_left_alone(self):
        address = self._address(is_new=False)

        apply_quick_entry_address_values(address)

        self.assertIsNone(address.get("county"))

    def test_no_stash_is_a_no_op(self):
        self.flags[FLAG] = None
        address = self._address()

        apply_quick_entry_address_values(address)

        self.assertIsNone(address.get("county"))


class TestRequiresSaudiNationalAddress(unittest.TestCase):
    def _needs(self, country="Saudi Arabia", category="Registered", entity_type="Company"):
        doc = FakeDoc(country=country, custom_vat_category=category)
        party = frappe._dict(entity_type=entity_type, custom_vat_category=category)
        return requires_saudi_national_address(doc, party=party)

    def test_saudi_company_always_needs_the_national_address(self):
        self.assertTrue(self._needs())
        self.assertTrue(self._needs(category="Unregistered"))

    def test_overseas_category_never_needs_it(self):
        self.assertFalse(self._needs(category="Overseas"))

    def test_individuals_need_it_only_when_registered(self):
        self.assertTrue(self._needs(entity_type="Individual"))
        self.assertFalse(self._needs(entity_type="Individual", category="Unregistered"))

    def test_other_countries_never_need_it(self):
        self.assertFalse(self._needs(country="United Arab Emirates"))
