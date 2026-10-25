"""Postal address mapping for ZATCA <cac:PostalAddress> (seller and buyer).

Pure unit tests (no site / database): ``build_zatca_address`` only reads plain
Address values plus the Country code, ``add_postal_address`` only writes XML and
``get_buyer_information`` is exercised with a fake Customer / Address.

Regression guard for the "inaccurate seller/buyer address data" warnings:

    * the buyer Country is the Address country (Bahrain -> BH), never SA
    * CitySubdivisionName is the district (Address.city) and CityName the city
      (Address.county) - never the building number or a repeated street name
    * a postal code that is not 5 digits is only rejected for Saudi addresses
      (BR-KSA-67)
    * the Registration Number fits its Registration Scheme - a CRN is exactly 10
      digits, otherwise ZATCA reports "There is a mismatch between the 'Buyer ID
      Type' and the 'ID Number' provided"
"""

import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

import frappe

from zatca_integration.common_util import (
    build_zatca_address,
    get_buyer_information,
    validate_company_buyer_identification,
    validate_registration_number,
)
from zatca_integration.overrides.customer import validate as customer_validate
from zatca_integration.saudi_arabia_electronic_invoicing.signing_engine import (
    generate_invoice_xml,
)

COUNTRY_CODES = {"Saudi Arabia": "SA", "Bahrain": "BH", "United Arab Emirates": "AE"}


class FakeDB:
    """Just enough of frappe.db / frappe.get_value for Country lookups."""

    def __init__(self, country_codes=None):
        self.country_codes = country_codes or COUNTRY_CODES

    def get_value(self, doctype, filters=None, fieldname=None, *args, **kwargs):
        if doctype != "Country":
            return None
        if isinstance(filters, dict):
            return self.country_codes.get(filters.get("code") or filters.get("name"))
        return self.country_codes.get(filters)

    def exists(self, doctype, filters=None, *args, **kwargs):
        if doctype == "Country" and isinstance(filters, dict):
            return filters.get("code") in self.country_codes.values()
        return False


def address(**overrides):
    """A Bahraini company address, as stored on the Address doctype."""
    values = {
        "doctype": "Address",
        "address_line1": "Road 1734",
        "address_line2": "2122",
        "city": "Block 117",
        "county": "HIDD",
        "state": "Manama",
        "pincode": "5021",
        "country": "Bahrain",
        "custom_additional_no": "8037",
    }
    values.update(overrides)
    return frappe._dict(values)


def fake_throw(message, *args, **kwargs):
    raise AssertionError(message)


class AddressTestCase(unittest.TestCase):
    """Patches the DB / message plumbing so no site is needed."""

    def setUp(self):
        self.db = FakeDB()
        patchers = (
            patch.object(frappe, "db", self.db),
            patch.object(frappe, "get_value", self.db.get_value),
            patch.object(frappe, "throw", side_effect=fake_throw),
            patch("zatca_integration.common_util._", side_effect=lambda text, *a, **k: text),
        )
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

        self.msgprints = []
        msgprint = patch.object(
            frappe,
            "msgprint",
            side_effect=lambda message=None, **kwargs: self.msgprints.append((message, kwargs)),
        )
        msgprint.start()
        self.addCleanup(msgprint.stop)


class TestBuildZatcaAddress(AddressTestCase):
    def test_maps_every_address_field_to_its_ubl_element(self):
        fields = build_zatca_address(address())

        self.assertEqual(
            fields,
            {
                "street_name": "Road 1734",
                "building_number": "2122",
                "plot_identification": "8037",
                "city_subdivision_name": "Block 117",
                "city_name": "HIDD",
                "postal_zone": "5021",
                "country_subentity": "Manama",
                "country": "Bahrain",
                "country_code": "BH",
            },
        )

    def test_missing_fields_stay_empty_instead_of_copying_another_field(self):
        fields = build_zatca_address(
            address(
                address_line2=None,
                city=None,
                county=None,
                state=None,
                pincode=None,
                country=None,
                custom_additional_no=None,
            )
        )

        self.assertEqual(fields["street_name"], "Road 1734")
        self.assertEqual(fields["building_number"], "")
        self.assertEqual(fields["plot_identification"], "")
        self.assertEqual(fields["city_subdivision_name"], "")
        self.assertEqual(fields["city_name"], "")
        self.assertEqual(fields["postal_zone"], "")
        self.assertEqual(fields["country_subentity"], "")
        self.assertEqual(fields["country"], "")
        self.assertEqual(fields["country_code"], "")

    def test_country_saved_as_iso_code_is_accepted(self):
        fields = build_zatca_address(address(country="bh"))

        self.assertEqual(fields["country_code"], "BH")

    def test_values_are_trimmed(self):
        fields = build_zatca_address(address(address_line1="  Road 1734  ", pincode=" 5021 "))

        self.assertEqual(fields["street_name"], "Road 1734")
        self.assertEqual(fields["postal_zone"], "5021")


class TestAddPostalAddress(AddressTestCase):
    def _tags(self, postal_address):
        return [element.tag for element in postal_address]

    def _child(self, parent, tag):
        return next((element for element in parent if element.tag == tag), None)

    def test_writes_the_buyer_address_in_schema_order(self):
        postal_address = ET.Element("cac:PostalAddress")

        generate_invoice_xml.add_postal_address(postal_address, build_zatca_address(address()))

        self.assertEqual(
            self._tags(postal_address),
            [
                "cbc:StreetName",
                "cbc:BuildingNumber",
                "cbc:PlotIdentification",
                "cbc:CitySubdivisionName",
                "cbc:CityName",
                "cbc:PostalZone",
                "cbc:CountrySubentity",
                "cac:Country",
            ],
        )
        values = {element.tag: element.text for element in postal_address}
        self.assertEqual(values["cbc:StreetName"], "Road 1734")
        self.assertEqual(values["cbc:PlotIdentification"], "8037")
        self.assertEqual(values["cbc:CitySubdivisionName"], "Block 117")
        self.assertEqual(values["cbc:CityName"], "HIDD")
        self.assertEqual(values["cbc:PostalZone"], "5021")
        country = self._child(postal_address, "cac:Country")
        self.assertEqual(self._child(country, "cbc:IdentificationCode").text, "BH")

    def test_omits_empty_seller_fields(self):
        postal_address = ET.Element("cac:PostalAddress")
        seller_address = {
            "street_name": "Mathan",
            "building_number": "3545",
            "plot_identification": "",
            "city_subdivision_name": "Al Mishael Dist.",
            "city_name": "Riyadh",
            "postal_zone": "14328",
            "country_subentity": "",
            "country_code": "SA",
        }

        generate_invoice_xml.add_postal_address(postal_address, seller_address)

        self.assertEqual(
            self._tags(postal_address),
            [
                "cbc:StreetName",
                "cbc:BuildingNumber",
                "cbc:CitySubdivisionName",
                "cbc:CityName",
                "cbc:PostalZone",
                "cac:Country",
            ],
        )
        self.assertIsNone(self._child(postal_address, "cbc:PlotIdentification"))
        self.assertIsNone(self._child(postal_address, "cbc:CountrySubentity"))


class TestBuyerInformation(AddressTestCase):
    def _customer(self, **overrides):
        values = {
            "doctype": "Customer",
            "name": "ALKOB",
            "customer_name": "Alkobaisi General Trading",
            "customer_type": "Company",
            "custom_country": "Bahrain",
            "custom_vat_number": None,
            "custom_registration_scheme": None,
            "custom_registration_number": None,
        }
        values.update(overrides)
        return frappe._dict(values)

    def _buyer(self, customer, customer_address):
        def get_doc(doctype, name=None):
            self.assertEqual((doctype, name), ("Customer", customer.name))
            return customer

        with (
            patch.object(frappe, "get_doc", side_effect=get_doc),
            patch(
                "zatca_integration.common_util.get_customer_billing_address",
                return_value=customer_address,
            ),
            patch("zatca_integration.common_util.validate_company_buyer_identification"),
        ):
            return get_buyer_information(customer.name)

    def test_bahraini_buyer_keeps_the_address_country(self):
        buyer = self._buyer(self._customer(), address())

        self.assertEqual(buyer["countryCode"], "BH")
        self.assertEqual(buyer["citySubdivisionName"], "Block 117")
        self.assertEqual(buyer["cityName"], "HIDD")
        self.assertEqual(buyer["plotIdentification"], "8037")
        self.assertEqual(
            buyer["full_address"],
            "2122, Road 1734,\nBlock 117,\nHIDD,\n5021, BH",
        )
        self.assertEqual(self.msgprints, [])

    def test_four_digit_postal_code_is_allowed_outside_saudi_arabia(self):
        # BR-KSA-67 only applies when the buyer country is SA.
        buyer = self._buyer(self._customer(), address(pincode="5021"))

        self.assertEqual(buyer["postalZone"], "5021")

    def test_saudi_buyer_requires_a_five_digit_postal_code(self):
        customer_address = address(country="Saudi Arabia", pincode="5021")

        with self.assertRaises(AssertionError) as context:
            self._buyer(self._customer(custom_country="Saudi Arabia"), customer_address)

        self.assertIn("Postal Zone must be 5 digits", str(context.exception))

    def test_saudi_buyer_with_a_national_address_passes(self):
        customer_address = address(country="Saudi Arabia", pincode="12345")

        buyer = self._buyer(self._customer(custom_country="Saudi Arabia"), customer_address)

        self.assertEqual(buyer["countryCode"], "SA")
        self.assertEqual(buyer["postalZone"], "12345")

    def test_customer_country_mismatch_is_reported_but_the_address_wins(self):
        buyer = self._buyer(self._customer(custom_country="Saudi Arabia"), address())

        self.assertEqual(buyer["countryCode"], "BH")
        self.assertEqual(len(self.msgprints), 1)
        self.assertEqual(self.msgprints[0][1].get("title"), "Customer Country Mismatch")

    def test_address_without_country_falls_back_to_the_customer(self):
        buyer = self._buyer(self._customer(), address(country=None))

        self.assertEqual(buyer["countryCode"], "BH")

    def test_individual_buyer_has_no_postal_address(self):
        customer = frappe._dict(
            doctype="Customer",
            name="WALKIN",
            customer_name="Walk-in Customer",
            customer_type="Individual",
        )

        buyer = self._buyer(customer, None)

        self.assertEqual(buyer, {"organizationName": "Walk-in Customer"})


class TestBuyerIdentification(AddressTestCase):
    def _customer(self, **overrides):
        values = {
            "customer_type": "Company",
            "custom_country": "Bahrain",
            "custom_vat_number": None,
            "tax_id": None,
            "custom_registration_scheme": None,
            "custom_registration_number": None,
        }
        values.update(overrides)
        return frappe._dict(values)

    def test_scheme_without_a_number_is_reported(self):
        validate_company_buyer_identification(
            self._customer(custom_registration_scheme="MOMRAH(MOM)")
        )

        self.assertEqual(len(self.msgprints), 1)
        message, kwargs = self.msgprints[0]
        self.assertEqual(kwargs.get("title"), "Incomplete Buyer Registration")
        self.assertIn("Registration Number", message)

    def test_number_without_a_scheme_is_reported(self):
        validate_company_buyer_identification(self._customer(custom_registration_number="1234"))

        self.assertEqual(len(self.msgprints), 1)
        self.assertIn("Registration Scheme", self.msgprints[0][0])

    def test_complete_identification_is_quiet(self):
        validate_company_buyer_identification(
            self._customer(
                custom_registration_scheme="MOMRAH(MOM)",
                custom_registration_number="3434434324242",
            )
        )

        self.assertEqual(self.msgprints, [])

    def test_individual_buyers_are_not_checked(self):
        validate_company_buyer_identification(
            self._customer(customer_type="Individual", custom_registration_number="1234")
        )

        self.assertEqual(self.msgprints, [])


class TestRegistrationNumber(AddressTestCase):
    """The ID number must belong to its Registration Scheme.

    ZATCA rejected ACC-SINV-2026-03751 with "There is a mismatch between the
    'Buyer ID Type' and the 'ID Number' provided": customer CUS06152 sent
    schemeID="CRN" with the 5-digit value 17788.
    """

    CRN = "Commercial Registration number(CRN)"

    def setUp(self):
        super().setUp()
        # Record the refused values instead of losing them in a bare exception.
        self.thrown = []

        def record_throw(message, *args, **kwargs):
            self.thrown.append(str(message))
            raise frappe.ValidationError(str(message))

        patcher = patch.object(frappe, "throw", side_effect=record_throw)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _customer(self, **overrides):
        values = {
            "doctype": "Customer",
            "customer_type": "Company",
            "custom_country": "Bahrain",
            "custom_vat_number": None,
            "tax_id": None,
            "custom_registration_scheme": None,
            "custom_registration_number": None,
        }
        values.update(overrides)
        return frappe._dict(values)

    def test_five_digit_number_is_refused_for_a_crn(self):
        with self.assertRaises(frappe.ValidationError):
            validate_registration_number(self.CRN, "17788")

        self.assertIn("17788", self.thrown[0])
        self.assertIn("10-digit Commercial Registration number", self.thrown[0])
        self.assertIn("Commercial Registration number(CRN)", self.thrown[0])

    def test_ten_digit_crn_is_accepted(self):
        validate_registration_number(self.CRN, "1010123456")

        self.assertEqual(self.thrown, [])

    def test_crn_length_must_be_exactly_ten_digits(self):
        for number in ("101012345", "10101234567"):
            with self.assertRaises(frappe.ValidationError, msg=number):
                validate_registration_number(self.CRN, number)

    def test_crn_with_letters_is_refused(self):
        with self.assertRaises(frappe.ValidationError):
            validate_registration_number(self.CRN, "10101234AB")

    def test_surrounding_spaces_are_ignored(self):
        validate_registration_number(self.CRN, "  1010123456\n")

        self.assertEqual(self.thrown, [])

    def test_seven_hundred_numbers_are_ten_digits(self):
        validate_registration_number("700(700)", "7001234567")
        self.assertEqual(self.thrown, [])

        with self.assertRaises(frappe.ValidationError):
            validate_registration_number("700(700)", "1234567")

    def test_numeric_schemes_without_a_published_length_require_digits(self):
        for scheme, number in (
            ("MOMRAH(MOM)", "1234567"),
            ("MHRSD(MLS)", "1234567890"),
            ("MISA(SAG)", "1010123456"),
        ):
            validate_registration_number(scheme, number)

        self.assertEqual(self.thrown, [])

        with self.assertRaises(frappe.ValidationError):
            validate_registration_number("MOMRAH(MOM)", "MOM-123")

    def test_other_od_keeps_free_text_ids(self):
        validate_registration_number("Other OD(OTH)", "BH-17788")

        self.assertEqual(self.thrown, [])

    def test_missing_values_are_left_to_the_presence_checks(self):
        validate_registration_number(None, "17788")
        validate_registration_number(self.CRN, None)
        validate_registration_number(self.CRN, "   ")

        self.assertEqual(self.thrown, [])

    def test_scheme_without_a_code_is_left_to_the_xml_builder(self):
        # get_registration_scheme_code() reports the missing "(CODE)" on its own;
        # the number check must not add a second, more confusing message.
        validate_registration_number("Legacy scheme", "17788")

        self.assertEqual(self.thrown, ["Invalid Registration Scheme"])

    def test_buyer_identification_is_refused_for_a_bad_crn(self):
        customer = self._customer(
            custom_registration_scheme=self.CRN,
            custom_registration_number="17788",
        )

        with self.assertRaises(frappe.ValidationError):
            validate_company_buyer_identification(customer)

        self.assertIn("17788", self.thrown[0])

    def test_buyer_identification_passes_a_valid_crn(self):
        validate_company_buyer_identification(
            self._customer(
                custom_registration_scheme=self.CRN,
                custom_registration_number="1010123456",
            )
        )

        self.assertEqual(self.thrown, [])
        self.assertEqual(self.msgprints, [])

    def test_customer_save_is_refused_for_a_bad_crn(self):
        customer = self._customer(
            custom_registration_scheme=self.CRN,
            custom_registration_number="17788",
        )

        with (
            patch("zatca_integration.overrides.customer.canonicalize_vat_category_field"),
            patch("zatca_integration.overrides.customer.stash_quick_entry_address_values"),
            self.assertRaises(frappe.ValidationError),
        ):
            customer_validate(customer)

        self.assertIn("10-digit Commercial Registration number", self.thrown[0])

    def test_customer_save_accepts_a_valid_crn(self):
        customer = self._customer(
            custom_registration_scheme=self.CRN,
            custom_registration_number="1010123456",
        )

        with (
            patch("zatca_integration.overrides.customer.canonicalize_vat_category_field"),
            patch("zatca_integration.overrides.customer.stash_quick_entry_address_values"),
        ):
            customer_validate(customer)

        self.assertEqual(self.thrown, [])
