"""Address automation for ZATCA: Arabic autofill, SA validation, VAT Category sync."""

from __future__ import annotations

import json
import re

import frappe
from frappe import _

# Categories treated as VAT-registered for address rules — shared with
# ``common_util.REGISTERED_VAT_CATEGORIES`` so the VAT Number validation and the
# Address rules never drift apart.
from zatca_integration.common_util import REGISTERED_VAT_CATEGORIES

# English Address field → Arabic custom field
ARABIC_FIELD_MAP = {
    "address_line1": "custom_street_in_arabic",
    "city": "custom_district_in_arabic",  # Subdivision / District
    "county": "custom_city_in_arabic",  # City Name
    "country": "custom_country_in_arabic",
}

# SA National Address fields required for Company / Registered + Saudi Arabia
SA_REQUIRED_FIELDS = [
    ("address_line1", _("Street Name")),
    ("address_line2", _("Building Number")),
    ("city", _("District / Sub-Division")),
    ("county", _("City Name")),
    ("pincode", _("Postal Code")),
]

# VAT categories that mean overseas / export-style (full SA national address not required)
OVERSEAS_VAT_CATEGORIES = {
    "Oversees",
    "Overseas",
    "Export / Non-Resident",
    "Deemed Export",
}

COUNTRY_ARABIC = {
    "Saudi Arabia": "المملكة العربية السعودية",
    "United Arab Emirates": "الإمارات العربية المتحدة",
    "Bahrain": "البحرين",
    "Kuwait": "الكويت",
    "Oman": "عُمان",
    "Qatar": "قطر",
    "Egypt": "مصر",
    "Jordan": "الأردن",
    "Yemen": "اليمن",
    "Iraq": "العراق",
    "Lebanon": "لبنان",
    "Syria": "سوريا",
    "Sudan": "السودان",
    "Morocco": "المغرب",
    "Tunisia": "تونس",
    "Algeria": "الجزائر",
    "Libya": "ليبيا",
    "Palestine": "فلسطين",
    "India": "الهند",
    "Pakistan": "باكستان",
    "Bangladesh": "بنغلاديش",
    "United States": "الولايات المتحدة",
    "United Kingdom": "المملكة المتحدة",
    "China": "الصين",
    "Turkey": "تركيا",
}

SA_CITY_ARABIC = {
    "riyadh": "الرياض",
    "jeddah": "جدة",
    "makkah": "مكة المكرمة",
    "mecca": "مكة المكرمة",
    "madinah": "المدينة المنورة",
    "medina": "المدينة المنورة",
    "dammam": "الدمام",
    "khobar": "الخبر",
    "dhahran": "الظهران",
    "taif": "الطائف",
    "tabuk": "تبوك",
    "abha": "أبها",
    "khamis mushait": "خميس مشيط",
    "jubail": "الجبيل",
    "yanbu": "ينبع",
    "buraidah": "بريدة",
    "hail": "حائل",
    "najran": "نجران",
    "jazan": "جازان",
    "hofuf": "الهفوف",
    "al ahsa": "الأحساء",
}


def before_save(doc, method=None):
    """Legacy hook entry — prefer validate."""
    validate(doc, method)


def validate(doc, method=None):
    # Local maps only — never call external translate APIs during save
    autofill_arabic_fields(doc, allow_network=False)
    sync_tax_category_from_party(doc)
    validate_address_by_party(doc)


def autofill_arabic_fields(doc, force: bool = False, allow_network: bool = False):
    """Fill Arabic fields from English when Arabic is empty (manual edits preserved)."""
    for source, target in ARABIC_FIELD_MAP.items():
        if not hasattr(doc, target):
            continue
        english = (doc.get(source) or "").strip()
        arabic = (doc.get(target) or "").strip()
        if not english:
            continue
        if arabic and not force:
            continue
        translated = translate_to_arabic(english, field=source, allow_network=allow_network)
        if translated:
            doc.set(target, translated)


def sync_tax_category_from_party(doc):
    """Prefill Address VAT Category fields from linked Customer/Supplier when empty."""
    party = _get_linked_party_values(doc)
    if not party:
        return

    if not doc.get("tax_category") and party.get("tax_category"):
        doc.tax_category = party["tax_category"]

    if hasattr(doc, "custom_vat_category") and not doc.get("custom_vat_category"):
        if party.get("custom_vat_category"):
            doc.custom_vat_category = party["custom_vat_category"]


def get_address_vat_category(doc, party=None) -> str:
    """VAT Category on Address, falling back to linked party."""
    value = (doc.get("tax_category") or doc.get("custom_vat_category") or "").strip()
    if value:
        return value

    party = party if party is not None else _get_linked_party_values(doc)
    if not party:
        return ""
    return (party.get("tax_category") or party.get("custom_vat_category") or "").strip()


def get_party_entity_type(doc, party=None) -> str | None:
    """
    Return 'Company', 'Individual', or None when no Customer/Supplier is linked.
    Supplier Partnership / other non-Individual types are treated as Company.
    """
    party = party if party is not None else _get_linked_party_values(doc)
    if not party:
        return None
    return party.get("entity_type")


def requires_saudi_national_address(doc, party=None) -> bool:
    """
    Full SA national address when:
    - Address country is Saudi Arabia, and
    - linked party is Company, or VAT Category is Registered (or equivalent), and
    - VAT Category is not overseas / export-style.
    Individuals (unless Registered) do not require national address fields.
    """
    if (doc.get("country") or "").strip() != "Saudi Arabia":
        return False

    party = party if party is not None else _get_linked_party_values(doc)
    vat_category = get_address_vat_category(doc, party=party)
    if vat_category in OVERSEAS_VAT_CATEGORIES:
        return False

    entity_type = get_party_entity_type(doc, party=party)
    if entity_type == "Individual":
        return vat_category in REGISTERED_VAT_CATEGORIES

    if entity_type == "Company":
        return True

    # No party linked: require full SA address only when clearly Registered
    return vat_category in REGISTERED_VAT_CATEGORIES


def validate_address_by_party(doc):
    """Server-side Address rules by party type / VAT Category / country."""
    party = _get_linked_party_values(doc)
    entity_type = get_party_entity_type(doc, party=party)
    country = (doc.get("country") or "").strip()
    needs_national = requires_saudi_national_address(doc, party=party)

    # Individuals: only Country is mandatory
    if entity_type == "Individual":
        if not country:
            frappe.throw(
                _("Country is required for Individual customer/supplier addresses."),
                title=_("Missing Country"),
            )
        if not needs_national:
            return

    if not needs_national:
        return

    missing = []
    for fieldname, label in SA_REQUIRED_FIELDS:
        if not doc.get(fieldname):
            missing.append(str(label))

    if missing:
        frappe.throw(
            _("Saudi National Address is incomplete. Please fill: {0}").format(", ".join(missing)),
            title=_("National Address Required"),
        )

    building = str(doc.get("address_line2") or "").strip()
    if not building.isdigit() or len(building) != 4:
        frappe.throw(
            _("Building Number must be exactly 4 digits for Saudi Arabia addresses."),
            title=_("Invalid Building Number"),
        )

    additional = str(doc.get("custom_additional_no") or "").strip()
    if additional and (not additional.isdigit() or len(additional) != 4):
        frappe.throw(
            _("Additional Number must be exactly 4 digits for Saudi Arabia addresses."),
            title=_("Invalid Additional Number"),
        )

    postal = str(doc.get("pincode") or "").strip()
    if not postal.isdigit() or len(postal) != 5:
        frappe.throw(
            _("Postal Code must be exactly 5 digits for Saudi Arabia addresses."),
            title=_("Invalid Postal Code"),
        )


def get_linked_party(doc):
    """Return first Customer/Supplier linked on the Address."""
    for row in doc.get("links") or []:
        if row.get("link_doctype") in ("Customer", "Supplier") and row.get("link_name"):
            return row.link_doctype, row.link_name
    return None, None


def _get_linked_party_values(doc) -> dict | None:
    """Single DB round-trip for linked Customer/Supplier context (cached on doc)."""
    cached = getattr(doc, "_zatca_party_values", None)
    if cached is not None:
        return cached or None

    party_type, party_name = get_linked_party(doc)
    if not party_type or not party_name:
        doc._zatca_party_values = {}
        return None

    meta = frappe.get_meta(party_type)
    fields = []
    if party_type == "Customer":
        fields.append("customer_type")
    else:
        fields.append("supplier_type")
    if meta.has_field("tax_category"):
        fields.append("tax_category")
    if meta.has_field("custom_vat_category"):
        fields.append("custom_vat_category")

    values = frappe.db.get_value(party_type, party_name, fields, as_dict=True)
    if not values:
        doc._zatca_party_values = {}
        return None

    if party_type == "Customer":
        entity_type = values.get("customer_type")
    else:
        supplier_type = values.get("supplier_type") or ""
        entity_type = "Individual" if supplier_type == "Individual" else "Company"

    result = {
        "party_type": party_type,
        "party_name": party_name,
        "entity_type": entity_type,
        "tax_category": values.get("tax_category"),
        "custom_vat_category": values.get("custom_vat_category"),
    }
    doc._zatca_party_values = result
    return result


def sync_party_tax_category_to_addresses(doc, method=None):
    """When Customer/Supplier tax_category changes, update linked Addresses only."""
    if not frappe.get_meta(doc.doctype).has_field("tax_category"):
        return

    old_doc = doc.get_doc_before_save()
    old_value = old_doc.get("tax_category") if old_doc else None
    new_value = doc.get("tax_category")
    if old_value == new_value:
        return

    address_names = frappe.get_all(
        "Dynamic Link",
        filters={
            "link_doctype": doc.doctype,
            "link_name": doc.name,
            "parenttype": "Address",
        },
        pluck="parent",
    )
    for address_name in address_names:
        current = frappe.db.get_value("Address", address_name, "tax_category")
        if current == new_value:
            continue
        frappe.db.set_value(
            "Address", address_name, "tax_category", new_value, update_modified=False
        )


@frappe.whitelist()
def get_address_party_context(link_doctype=None, link_name=None):
    """Client helper: party type + VAT category for Address mandatory toggles."""
    result = {
        "entity_type": None,
        "tax_category": None,
        "custom_vat_category": None,
    }
    if not link_doctype or not link_name or link_doctype not in ("Customer", "Supplier"):
        return result
    if not frappe.db.exists(link_doctype, link_name):
        return result

    meta = frappe.get_meta(link_doctype)
    fields = []
    if link_doctype == "Customer":
        fields.append("customer_type")
    else:
        fields.append("supplier_type")
    if meta.has_field("tax_category"):
        fields.append("tax_category")
    if meta.has_field("custom_vat_category"):
        fields.append("custom_vat_category")

    values = frappe.db.get_value(link_doctype, link_name, fields, as_dict=True) or {}
    if link_doctype == "Customer":
        result["entity_type"] = values.get("customer_type")
    else:
        supplier_type = values.get("supplier_type") or ""
        result["entity_type"] = "Individual" if supplier_type == "Individual" else "Company"

    result["tax_category"] = values.get("tax_category")
    result["custom_vat_category"] = values.get("custom_vat_category")
    return result


@frappe.whitelist()
def translate_text_to_arabic(text: str, field: str | None = None) -> str:
    """Whitelisted helper for client-side Arabic autofill (may use network)."""
    return translate_to_arabic(text or "", field=field, allow_network=True)


def translate_to_arabic(text: str, field: str | None = None, allow_network: bool = True) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    if _contains_arabic(text):
        return text

    if field == "country" or text in COUNTRY_ARABIC:
        mapped = COUNTRY_ARABIC.get(text, "")
        if mapped:
            return mapped

    city_key = text.lower().strip()
    if field in ("county", "city") and city_key in SA_CITY_ARABIC:
        return SA_CITY_ARABIC[city_key]

    if not allow_network:
        return ""

    # Free-text: HTTP translate first (deep_translator often hits rate limits)
    translated = _translate_via_http(text)
    if translated:
        return translated

    return _translate_via_library(text) or ""


def _contains_arabic(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", text or ""))


def _translate_via_http(text: str) -> str:
    """Translate using Google's public gtx endpoint (no API key)."""
    try:
        from urllib.parse import quote
        from urllib.request import Request, urlopen

        url = (
            "https://translate.googleapis.com/translate_a/single"
            f"?client=gtx&sl=auto&tl=ar&dt=t&q={quote(text)}"
        )
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        # Keep timeout short so a flaky network cannot hang Address/Customer UX
        with urlopen(req, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        # payload[0] is a list of [translated, original, ...] segments
        parts = []
        for segment in payload[0] or []:
            if segment and segment[0]:
                parts.append(segment[0])
        return "".join(parts).strip()
    except Exception:
        return ""


def _translate_via_library(text: str) -> str:
    try:
        from deep_translator import GoogleTranslator

        return GoogleTranslator(source="auto", target="ar").translate(text) or ""
    except Exception:
        pass
    try:
        from googletrans import Translator

        result = Translator().translate(text, dest="ar")
        return (result.text if result else "") or ""
    except Exception:
        return ""
