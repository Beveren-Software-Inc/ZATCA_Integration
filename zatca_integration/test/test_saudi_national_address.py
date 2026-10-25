"""Saudi National Address city / postal code rules (BR-KSA-67 and City Name).

ZATCA rejected sico's address data as "Inaccurate Seller/Buyer Address Data,
specifically the Postal Zone (Postal Code) and City Names". Reference invoice
ACC-SINV-2026-03376:

    * the buyer is Bahraini, so the Address carries the Bahraini postal code
      "5021" - valid, because BR-KSA-67 only applies when the country is SA
      (the old mapping sent SA for every address and triggered the warning)
    * City Name (Address.county -> cbc:CityName) must be a Saudi National
      Address city; sico's data holds "dammam", "AL KHUBAR", "Ad Dammam",
      "AL HAFUF", "SAYHAT", "TARUT", "Riyad" ...

Pure unit tests: no site and no database.
"""

import unittest
from unittest.mock import patch

import frappe

from zatca_integration.overrides import address as address_override
from zatca_integration.saudi_arabia_electronic_invoicing.doctype.zatca_csr_settings import (
    zatca_csr_settings,
)
from zatca_integration.saudi_arabia_electronic_invoicing.saudi_national_address import (
    SAUDI_CITIES,
    canonical_city_name,
    city_options,
    is_saudi_country,
    is_valid_saudi_postal_code,
    normalize_city_name,
    suggest_saudi_cities,
    validate_postal_address_for_zatca,
    validate_zatca_city_name,
)


class TestCityNames(unittest.TestCase):
    def test_official_name_is_kept(self):
        self.assertEqual(canonical_city_name("Riyadh"), "Riyadh")
        self.assertEqual(canonical_city_name("Al Khobar"), "Al Khobar")

    def test_letter_case_is_canonicalised(self):
        self.assertEqual(canonical_city_name("dammam"), "Dammam")
        self.assertEqual(canonical_city_name("DAMMAM"), "Dammam")
        self.assertEqual(canonical_city_name("AL MUBARRAZ"), "Al Mubarraz")

    def test_articles_and_city_suffix_are_ignored(self):
        self.assertEqual(canonical_city_name("Ad Dammam"), "Dammam")
        self.assertEqual(canonical_city_name("Al Dammam"), "Dammam")
        self.assertEqual(canonical_city_name("AR RIYADH"), "Riyadh")
        self.assertEqual(canonical_city_name("RIYADH CITY"), "Riyadh")

    def test_transliteration_variants(self):
        self.assertEqual(canonical_city_name("Al khober"), "Al Khobar")
        self.assertEqual(canonical_city_name("AL KHUBAR"), "Al Khobar")
        self.assertEqual(canonical_city_name("KHOBAR"), "Al Khobar")
        self.assertEqual(canonical_city_name("AL HAFUF"), "Hofuf")
        self.assertEqual(canonical_city_name("Buqayq"), "Abqaiq")
        self.assertEqual(canonical_city_name("SAYHAT"), "Saihat")
        self.assertEqual(canonical_city_name("TARUT"), "Tarut")
        self.assertEqual(canonical_city_name("Riyad"), "Riyadh")
        self.assertEqual(canonical_city_name("KHAMIS MUSHAYT"), "Khamis Mushait")
        self.assertEqual(canonical_city_name("AL JUBAIL"), "Jubail")
        self.assertEqual(canonical_city_name("AR RASS"), "Ar Rass")

    def test_small_typos_are_corrected(self):
        self.assertEqual(canonical_city_name("Damam"), "Dammam")
        self.assertEqual(canonical_city_name("DAMMA"), "Dammam")

    def test_arabic_city_name(self):
        self.assertEqual(canonical_city_name("الرياض"), "Riyadh")
        self.assertEqual(canonical_city_name("جدة"), "Jeddah")

    def test_non_saudi_city_is_unknown(self):
        # A Bahraini town stored in the City Name of a Saudi address, or a
        # district ("Al Mishael Dist.") instead of the city, is not a city.
        self.assertIsNone(canonical_city_name("HIDD"))
        self.assertIsNone(canonical_city_name("Al Mishael Dist"))
        self.assertIsNone(canonical_city_name(""))

    def test_normalize_strips_punctuation_and_spaces(self):
        self.assertEqual(normalize_city_name("  Al   Khobar - KSA "), "al khobar ksa")

    def test_suggestions_point_at_the_official_city(self):
        suggestions = suggest_saudi_cities("Damamm")
        self.assertIn("Dammam", suggestions)

    def test_suggestions_are_ranked_by_how_the_name_starts(self):
        self.assertEqual(suggest_saudi_cities("Kho"), ["Al Khobar"])
        self.assertEqual(suggest_saudi_cities("Dammam")[0], "Dammam")
        # Arabic input is answered with the official English name.
        self.assertEqual(suggest_saudi_cities("الدم"), ["Dammam"])

    def test_suggestions_never_offer_unrelated_cities(self):
        # The complaint that started this: typing "Mana" answered with
        # "Did you mean: Anak, Madinah, Marat?".
        for value in ("Mana", "HIDD", "Atlantis", "zzzz"):
            with self.subTest(value=value):
                suggestions = suggest_saudi_cities(value)
                for unrelated in ("Anak", "Madinah", "Marat"):
                    self.assertNotIn(unrelated, suggestions)
        self.assertEqual(suggest_saudi_cities("Atlantis"), [])
        self.assertEqual(suggest_saudi_cities("HIDD"), [])

    def test_suggestions_use_each_word_of_the_field(self):
        self.assertIn("Madinah", suggest_saudi_cities("madinah brida"))

    def test_suggestions_are_limited(self):
        self.assertLessEqual(len(suggest_saudi_cities("A")), 3)

    def test_postal_code_typed_after_the_city_name_is_ignored(self):
        self.assertEqual(canonical_city_name("Al Jubail 35717-7459"), "Jubail")

    def test_arabic_and_english_in_one_field(self):
        self.assertEqual(canonical_city_name("الدمام Dammam"), "Dammam")

    def test_local_variants_seen_on_sico(self):
        self.assertEqual(canonical_city_name("AN NU'AYRIYAH"), "An Nairyah")
        self.assertEqual(canonical_city_name("'INAK"), "Anak")
        self.assertEqual(canonical_city_name("Buqaya"), "Abqaiq")
        self.assertEqual(canonical_city_name("Afif"), "Afif")

    def test_district_names_are_not_cities(self):
        for value in ("Al Mishael Dist.", "Ad Dabab dist", "Nakhil", "Salwa"):
            with self.subTest(value=value):
                self.assertIsNone(canonical_city_name(value))


class TestCityOptions(unittest.TestCase):
    """The list behind the City Name type-ahead (get_saudi_city_options)."""

    def test_every_official_city_is_offered_once(self):
        options = city_options()
        values = [option["value"] for option in options]

        self.assertEqual(len(values), len(set(values)))
        self.assertEqual(set(values), set(SAUDI_CITIES))

    def test_option_carries_the_region_and_the_arabic_name(self):
        option = next(item for item in city_options() if item["value"] == "Dammam")

        self.assertEqual(option["label"], "Dammam")
        self.assertEqual(option["region"], "Eastern Province")
        self.assertEqual(option["arabic"], "الدمام")

    def test_extra_cities_from_settings_are_offered(self):
        fake_db = frappe._dict(
            get_singles_dict=lambda doctype: {"extra_saudi_cities": "Hawtat Sudair"}
        )
        patcher = patch.object(frappe, "db", fake_db)
        patcher.start()
        self.addCleanup(patcher.stop)

        values = [option["value"] for option in city_options()]

        self.assertIn("Hawtat Sudair", values)


class TestPostalCode(unittest.TestCase):
    def test_five_digit_codes(self):
        self.assertTrue(is_valid_saudi_postal_code("14328"))
        self.assertTrue(is_valid_saudi_postal_code(" 32242 "))

    def test_invalid_codes(self):
        for value in ("5021", "1234", "123456", "01234", "", None, "1432a"):
            with self.subTest(value=value):
                self.assertFalse(is_valid_saudi_postal_code(value))

    def test_saudi_country_name_or_iso_code(self):
        for value in ("Saudi Arabia", "saudi arabia", "SA", " sa "):
            with self.subTest(value=value):
                self.assertTrue(is_saudi_country(value))
        for value in ("Bahrain", "BH", "", None):
            with self.subTest(value=value):
                self.assertFalse(is_saudi_country(value))


class ValidationTestCase(unittest.TestCase):
    """Records frappe.throw / frappe.msgprint instead of needing a site."""

    def setUp(self):
        self.thrown = []
        self.thrown_titles = []
        self.msgprints = []

        def record_throw(message, *args, **kwargs):
            self.thrown.append(str(message))
            self.thrown_titles.append(kwargs.get("title"))
            raise frappe.ValidationError(str(message))

        def record_msgprint(message, *args, **kwargs):
            self.msgprints.append((str(message), kwargs))

        for patcher in (
            patch.object(frappe, "throw", side_effect=record_throw),
            patch.object(frappe, "msgprint", side_effect=record_msgprint),
            patch(
                "zatca_integration.saudi_arabia_electronic_invoicing.saudi_national_address._",
                side_effect=lambda text, *a, **k: text,
            ),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def address(self, **overrides):
        values = {
            "address_line1": "18th Street",
            "address_line2": "1234",
            "city": "Al Mishael Dist.",
            "county": "Riyadh",
            "state": "Riyadh",
            "pincode": "14328",
            "country": "Saudi Arabia",
            "links": [],
        }
        values.update(overrides)
        return frappe._dict(values)

    def validate_address(self, doc, entity_type="Company"):
        party = {"entity_type": entity_type, "tax_category": None, "custom_vat_category": None}
        with patch.object(address_override, "_get_linked_party_values", return_value=party):
            address_override.validate_address_by_party(doc)


class TestPostalAddressForZatca(ValidationTestCase):
    def test_foreign_address_keeps_its_own_postal_format(self):
        # BR-KSA-67 is about the buyer Country Code being SA; a Bahraini postal
        # code is neither 5 digits nor a Saudi city and must pass untouched.
        city = validate_postal_address_for_zatca(
            {"country_code": "BH", "postal_zone": "5021", "city_name": "HIDD"},
            "Buyer address",
        )

        self.assertEqual(city, "HIDD")
        self.assertEqual(self.thrown, [])

    def test_saudi_postal_zone_must_be_five_digits(self):
        with self.assertRaises(frappe.ValidationError):
            validate_postal_address_for_zatca(
                {"country_code": "SA", "postal_zone": "5021", "city_name": "Riyadh"},
                "Buyer address",
            )

        self.assertIn("Postal Zone must be 5 digits", self.thrown[0])

    def test_saudi_city_is_sent_the_official_way(self):
        city = validate_postal_address_for_zatca(
            {"country_code": "SA", "postal_zone": "34421", "city_name": "AL KHOBAR"},
            "Buyer address",
        )

        self.assertEqual(city, "Al Khobar")

    def test_unknown_saudi_city_is_refused(self):
        with self.assertRaises(frappe.ValidationError):
            validate_postal_address_for_zatca(
                {"country_code": "SA", "postal_zone": "14328", "city_name": "HIDD"},
                "Buyer address",
            )

        self.assertIn("not a Saudi National Address city name", self.thrown[0])
        self.assertIn("Additional Saudi City Names", self.thrown[0])

    def test_missing_city_is_refused(self):
        with self.assertRaises(frappe.ValidationError):
            validate_zatca_city_name("", "Buyer address")

        self.assertIn("City Name is required", self.thrown[0])


class TestCityValidationSettings(ValidationTestCase):
    """Zatca Settings can extend the list or downgrade the check to a warning."""

    def patch_settings(self, **values):
        fake_db = frappe._dict(get_singles_dict=lambda doctype: values)
        patcher = patch.object(frappe, "db", fake_db)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_extra_city_from_settings_is_accepted(self):
        self.patch_settings(extra_saudi_cities="Hawtat Sudair\nAl Aflaj")

        self.assertEqual(canonical_city_name("Hawtat Sudair"), "Hawtat Sudair")
        self.assertIsNone(canonical_city_name("Atlantis"))

    def test_skipping_validation_only_warns(self):
        self.patch_settings(skip_saudi_city_validation=1)

        city = validate_zatca_city_name("Atlantis", "Buyer address")

        self.assertEqual(city, "Atlantis")
        self.assertEqual(self.thrown, [])
        self.assertEqual(self.msgprints[0][1].get("title"), "Unverified City Name")


class TestAddressDoctype(ValidationTestCase):
    """The Address DocType validates the National Address when it is saved."""

    def test_city_name_is_saved_with_the_official_spelling(self):
        doc = self.address(county="AL KHOBAR", pincode="34421")

        self.validate_address(doc)

        self.assertEqual(doc.county, "Al Khobar")
        self.assertEqual(self.thrown, [])

    def test_corrected_city_is_reported_to_the_user(self):
        doc = self.address(county="Ad Dammam", pincode="32242")

        self.validate_address(doc)

        self.assertEqual(doc.county, "Dammam")
        self.assertEqual(self.msgprints[0][1].get("title"), "City Name Corrected")

    def test_unknown_city_blocks_the_save(self):
        doc = self.address(county="Atlantis", pincode="14328")

        with self.assertRaises(frappe.ValidationError):
            self.validate_address(doc)

        self.assertIn("not a Saudi National Address city name", self.thrown[0])
        self.assertEqual(self.thrown_titles[0], "Invalid City Name")

    def test_postal_code_must_be_five_digits(self):
        doc = self.address(pincode="1234")

        with self.assertRaises(frappe.ValidationError):
            self.validate_address(doc)

        self.assertIn("Postal Code must be exactly 5 digits", self.thrown[0])

    def test_foreign_address_is_not_checked(self):
        doc = self.address(
            country="Bahrain",
            county="HIDD",
            city="Block 117",
            state="Manama",
            pincode="5021",
        )

        self.validate_address(doc)

        self.assertEqual(self.thrown, [])
        self.assertEqual(doc.county, "HIDD")

    def test_individual_address_keeps_the_old_requirements(self):
        # Individuals only need a country: a B2C invoice carries no buyer postal
        # address, so the National Address rules do not apply.
        doc = self.address(county="HIDD", pincode="5021")

        self.validate_address(doc, entity_type="Individual")

        self.assertEqual(self.thrown, [])


class TestCsrSettings(ValidationTestCase):
    """The seller City Name (cbc:CityName) is validated where it is captured."""

    def settings(self, **overrides):
        values = {
            "csrserialnumber": "1-ERPNext|2-V15|3-test",
            "street_name": "Mathan",
            "building_number": 3545,
            "city_subdivision_name": "Al Mishael Dist.",
            "city_name": "Riyadh",
            "postal_zone": 14328,
            "csrcountryname": "SA",
            "csrorganizationidentifier": "300000000000003",
        }
        values.update(overrides)
        return frappe._dict(values)

    def test_seller_city_is_corrected_to_the_official_name(self):
        doc = self.settings(city_name="AL KHOBAR")

        ZatcaCSRSettings = zatca_csr_settings.ZatcaCSRSettings

        ZatcaCSRSettings.before_save(doc)

        self.assertEqual(doc.city_name, "Al Khobar")
        self.assertEqual(self.thrown, [])

    def test_unknown_seller_city_blocks_the_save(self):
        doc = self.settings(city_name="Atlantis")

        with self.assertRaises(frappe.ValidationError):
            zatca_csr_settings.ZatcaCSRSettings.before_save(doc)

        self.assertIn("not a Saudi National Address city name", self.thrown[0])


if __name__ == "__main__":
    unittest.main()
