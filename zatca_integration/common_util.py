import base64
import hashlib
import re
import xml.etree.ElementTree as ET

import frappe
from frappe import _
from frappe.utils import cint

# Single DocType holding the VAT Number validation switches
ZATCA_SETTINGS = "Zatca Settings"

# Switches that control whether a Company customer must carry a VAT Number
VAT_VALIDATION_FIELDS = (
    "validate_vat_no_against_all_company",
    "validate_vat_no_against_registered_company",
)

# ---------------------------------------------------------------- VAT Category
# Two fields carry a "VAT Category" in this app, and both are understood here:
#   * ``custom_vat_category`` — Select on Customer / Supplier / Address:
#     Registered, Unregistered, Overseas, Government, Exempt
#   * ``tax_category`` — Link to ERPNext "Tax Category", seeded by
#     ``vat_setup.TAX_CATEGORIES``: B2B, B2C, B2G, Export / Non-Resident,
#     Exempt Entity
# ``get_customer_vat_category`` prefers the link, then falls back to the select.
#
# Names are matched case-insensitively and ignoring extra spaces, so renaming an
# option ("registered", "Overseas ") can never silently break the VAT checks.

# Party IS VAT-registered: a VAT Number is expected when the
# "Validate VAT No Against Registered Company" switch is on.
REGISTERED_VAT_CATEGORIES = {
    "Registered",  # select
    "B2B",  # tax_category
    "B2G",  # tax_category
    "Tax Deductors",  # VAT Category record
    "Tax Deductor",
}

# Party is NOT VAT-registered: a VAT Number is never forced (switch or not).
UNREGISTERED_VAT_CATEGORIES = {
    "Unregistered",  # select
    "B2C",  # tax_category (consumer)
    "Government",  # select
    "Exempt",  # select
    "Exempt Entity",  # tax_category
}

# Overseas / export-style: buyer VAT is not mandatory and the full Saudi
# national address is not required (ZATCA Annex 5.3-5.4).
EXPORT_VAT_CATEGORIES = {
    "Overseas",  # select
    "Oversees",  # VAT Category record spelling
    "Deemed Export",  # VAT Category record
    "Export / Non-Resident",  # tax_category
    "Export",
}


# Zero-width / invisible characters that sneak into Select option strings and
# stored values: U+2060 WORD JOINER, U+200B ZWSP, U+FEFF BOM, U+200C/U+200D.
# They make a stored value stop matching its option, which makes the Select show
# blank and save blank.
INVISIBLE_VAT_CHARS = dict.fromkeys(map(ord, "\u2060\u200b\ufeff\u200c\u200d"))


def normalize_vat_category(value) -> str:
    """Case-folded, whitespace- and invisible-character-insensitive form."""
    return clean_vat_category(value).casefold()


def clean_vat_category(value) -> str:
    """
    Drop invisible characters and collapse/trim whitespace.

    The Select options once shipped with a U+2060 WORD JOINER before
    "Unregistered", "Overseas", "Government" and "Exempt" and a trailing TAB on
    some of them. A Select field whose stored value is not byte-identical to an
    option renders blank and then saves blank, so these never survive here.
    """
    text = str(value or "").translate(INVISIBLE_VAT_CHARS)
    return re.sub(r"\s+", " ", text).strip()


def get_vat_category_options(doctype="Customer", fieldname="custom_vat_category"):
    """Select options of the VAT Category field, cleaned and de-duplicated."""
    meta = frappe.get_meta(doctype)
    df = meta.get_field(fieldname) if meta else None
    if not df or not df.options:
        return []

    options = []
    for option in df.options.split("\n"):
        cleaned = clean_vat_category(option).strip()
        if cleaned and cleaned not in options:
            options.append(cleaned)
    return options


def canonical_vat_category(value, options):
    """Return the exact Select option matching ``value`` (case/space/invisible safe)."""
    if value in (None, ""):
        return None

    normalized = normalize_vat_category(value)
    for option in options or []:
        if normalize_vat_category(option) == normalized:
            return option
    return None


def canonicalize_vat_category_field(doc, fieldname="custom_vat_category"):
    """
    Rewrite ``doc.<fieldname>`` to the exact Select option when it matches.

    Guards the "VAT Category goes blank on save" problem: Select fields only show
    a value that is byte-identical to one of their options. Returns the new value
    when it was rewritten, ``None`` when nothing changed (values that match no
    option are left untouched so nothing is lost silently).
    """
    value = doc.get(fieldname)
    if not value:
        return None

    doctype = getattr(doc, "doctype", None) or doc.get("doctype")
    canonical = canonical_vat_category(value, get_vat_category_options(doctype, fieldname))
    if canonical and canonical != value:
        # Document objects expose .set(); plain dicts only support item assignment
        if hasattr(doc, "set"):
            doc.set(fieldname, canonical)
        else:
            doc[fieldname] = canonical
        return canonical
    return None


_REGISTERED_VAT_NORMALIZED = {normalize_vat_category(name) for name in REGISTERED_VAT_CATEGORIES}
_EXPORT_VAT_NORMALIZED = {normalize_vat_category(name) for name in EXPORT_VAT_CATEGORIES}


def is_registered_vat_category(value) -> bool:
    """True when the VAT Category marks the party as VAT-registered."""
    return normalize_vat_category(value) in _REGISTERED_VAT_NORMALIZED


def is_export_vat_category(value) -> bool:
    """True for Overseas / Export / Deemed Export style VAT Categories."""
    return normalize_vat_category(value) in _EXPORT_VAT_NORMALIZED


def validate_sales_invoice(doc, method):
    if not doc.taxes_and_charges:
        frappe.throw("Sales Taxes and Charges Template must be provided.")

    if doc.is_return and (not doc.return_against and not doc.custom_cn_ref):
        frappe.throw("Go to credit note details and fetch return invoices")


def validate_pos_invoice(doc, method):
    if doc.is_pos == 1:
        doc.custom_delivery_date = doc.posting_date


def decode_invoice(encoded_invoice):
    encoded_bytes = encoded_invoice.encode("utf-8")
    decoded_bytes = base64.b64decode(encoded_bytes)
    decoded_string = decoded_bytes.decode("utf-8")
    return decoded_string


def is_foreign_customer(customer) -> bool:
    """Buyer outside KSA, or an Overseas / Export / Deemed Export VAT category."""
    if is_export_vat_category(get_customer_vat_category(customer)):
        return True

    country = str(customer.get("custom_country") or "").strip()
    return bool(country) and country.casefold() != "saudi arabia"


def validate_ksa_vat_number(vat_number, field_label=None):
    """
    KSA VAT / Group VAT Registration Number:
    exactly 15 digits and must start with 3.
    """
    vat = (vat_number or "").strip()
    if not vat:
        return

    label = field_label or _("VAT Number")
    if not (vat.isdigit() and len(vat) == 15 and vat.startswith("3")):
        frappe.throw(
            _("{0} must be exactly 15 digits and start with 3.").format(label),
            title=_("Invalid VAT Number"),
        )


def get_customer_vat_category(customer) -> str:
    """VAT Category of a Customer (Document or dict), Tax Category taking precedence."""
    return (customer.get("tax_category") or customer.get("custom_vat_category") or "").strip()


def is_vat_registered_customer(customer) -> bool:
    """True when the customer's VAT Category marks them as VAT-registered."""
    return is_registered_vat_category(get_customer_vat_category(customer))


def get_vat_validation_settings() -> dict:
    """
    Read the VAT Number validation switches from "Zatca Settings".

    - validate_vat_no_against_all_company: a VAT Number is mandatory for every
      Company customer (in scope of ZATCA rules).
    - validate_vat_no_against_registered_company: a VAT Number is mandatory only
      when the customer's VAT Category is a registered one.

    Missing DocType / record / empty values fall back to 0 (validation off), so
    unregistered companies below the VAT threshold are never blocked by default.
    """
    values = frappe.db.get_singles_dict(ZATCA_SETTINGS) or {}
    return {fieldname: cint(values.get(fieldname)) for fieldname in VAT_VALIDATION_FIELDS}


def is_vat_number_required(customer) -> bool:
    """
    Whether this customer must provide a VAT Number (or registration details).

    Companies outside Saudi Arabia / Export category are never forced (ZATCA
    Annex 5.3-5.4). Individuals are never forced. Everything else is decided by
    the switches on "Zatca Settings".
    """
    if customer.get("customer_type") != "Company":
        return False

    if is_foreign_customer(customer):
        return False

    settings = get_vat_validation_settings()
    if settings["validate_vat_no_against_all_company"]:
        return True

    if settings["validate_vat_no_against_registered_company"]:
        return is_vat_registered_customer(customer)

    return False


def validate_company_buyer_identification(customer):
    """
    ZATCA E-Invoicing Resolution Annex 5.3–5.4:
    - Individual: buyer company identification not required.
    - Export / non-KSA buyer: buyer VAT not mandatory.
    - Saudi B2B/company: VAT if applicable, or registration scheme + number.
      Whether a VAT Number is mandatory is controlled by "Zatca Settings".
    """
    if customer.customer_type != "Company":
        return

    if is_foreign_customer(customer):
        return

    has_vat = bool(customer.custom_vat_number or customer.get("tax_id"))
    has_registration = bool(
        customer.custom_registration_scheme and customer.custom_registration_number
    )
    if has_vat:
        validate_ksa_vat_number(
            customer.custom_vat_number or customer.get("tax_id"),
            field_label=_("VAT Number"),
        )
    if not is_vat_number_required(customer):
        return
    if not (has_vat or has_registration):
        frappe.throw(
            "Saudi company customers must have a VAT Number or both "
            "Registration Scheme and Registration Number."
        )


def get_buyer_information(customer_name):
    customer = frappe.get_doc("Customer", customer_name)
    country_code = get_country_code(customer.custom_country)

    if customer.customer_type == "Company":
        address = frappe.get_doc("Address", customer.customer_primary_address)
        if not address:
            frappe.throw("Customer must have a primary address")

        validate_company_buyer_identification(customer)

        # ZATCA Address Validation
        # Address Line 1 is required
        if not address.address_line1:
            frappe.throw("Street Name is required for Company type customer")

        # Building Number is required
        # Building Number must be 4 digits if country_code is SA
        if not address.address_line2:
            frappe.throw("Building Number is required for Company type customer")
        if country_code == "SA" and len(address.address_line2) != 4:
            frappe.throw(
                "Building Number must be 4 digits for Company type customer in Saudi Arabia"
            )

        # City Subdivision Name is required
        if not address.city:
            frappe.throw("City Subdivision Name is required for Company type customer")

        # City Name is required
        if not address.county:
            frappe.throw("City Name is required for Company type customer")

        # Postal Zone is required
        # Postal Zone must be 5 digits if country_code is SA
        if not address.pincode:
            frappe.throw("Postal Zone is required for Company type customer")
        if country_code == "SA" and len(address.pincode) != 5:
            frappe.throw("Postal Zone must be 5 digits for Company type customer in Saudi Arabia")

        full_address = f"{address.address_line2}, {address.address_line1},\n"
        full_address += f"{address.city},\n"
        full_address += f"{address.county},\n"
        full_address += f"{address.pincode}, {country_code}"

        return {
            "organizationName": customer.customer_name,
            "vatNumber": customer.custom_vat_number,
            "registrationScheme": (
                get_registration_scheme_code(customer.custom_registration_scheme)
                if customer.custom_registration_scheme
                else ""
            ),
            "registrationNumber": customer.custom_registration_number or "",
            "streetName": address.address_line1,
            "buildingNumber": address.address_line2,
            "citySubdivisionName": address.city,
            "cityName": address.county,
            "postalZone": address.pincode,
            "countryCode": country_code,
            "full_address": full_address,
        }
    elif customer.customer_type == "Individual":
        return {"organizationName": customer.customer_name}
    else:
        frappe.throw("Invalid Customer Type")


def get_seller_information(csr_settings):
    full_address = f"{csr_settings.building_number}, {csr_settings.street_name},\n"
    full_address += f"{csr_settings.city_subdivision_name},\n"
    full_address += f"{csr_settings.city_name},\n"
    full_address += f"{csr_settings.postal_zone}, {csr_settings.csrcountryname}"

    return {
        "organizationName": csr_settings.csrorganizationname,
        "vatNumber": csr_settings.csrorganizationidentifier,
        # "vatNumber": "399999999900003",
        "streetName": csr_settings.street_name,
        "buildingNumber": csr_settings.building_number,
        "citySubdivisionName": csr_settings.city_subdivision_name,
        "cityName": csr_settings.city_name,
        "postalZone": csr_settings.postal_zone,
        "countryCode": csr_settings.csrcountryname,
        "full_address": full_address,
        "registrationScheme": get_registration_scheme_code(csr_settings.registration_scheme),
        "registrationNumber": csr_settings.registration_number,
    }


def get_country_code(country_name):
    country_code = frappe.get_value("Country", filters={"name": country_name}, fieldname="code")
    if country_code:
        return country_code.upper()
    else:
        frappe.throw("Invalid Country Name")


def get_registration_scheme_code(registration_scheme):
    # If the registration_scheme is empty, return an empty string
    if registration_scheme is None or registration_scheme == "":
        return ""
    # Find the start and end indices of the parentheses
    start = registration_scheme.find("(")
    end = registration_scheme.find(")")

    # Extract and return the text inside the parentheses
    if start != -1 and end != -1:
        return registration_scheme[start + 1 : end]
    else:
        frappe.throw("Invalid Registration Scheme")


# Implementing new compliance
def generate_invoice_payload_from_xml(xml_content: bytes) -> dict:
    import base64
    import xml.etree.ElementTree as ET

    namespaces = {
        "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
        "sig": "urn:oasis:names:specification:ubl:schema:xsd:CommonSignatureComponents-2",
        "sac": "urn:oasis:names:specification:ubl:schema:xsd:SignatureAggregateComponents-2",
        "xades": "http://uri.etsi.org/01903/v1.3.2#",
        "ds": "http://www.w3.org/2000/09/xmldsig#",
        "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    }

    root = ET.fromstring(xml_content)

    # Find the first DigestValue inside SignedInfo (more flexible)
    digest_value_element = root.find(".//ds:SignedInfo/ds:Reference/ds:DigestValue", namespaces)
    if digest_value_element is None or not digest_value_element.text:
        raise Exception("DigestValue not found in the XML.")
    encoded_hash = digest_value_element.text.strip()

    # Extract UUID
    uuid_element = root.find("cbc:UUID", namespaces)
    if uuid_element is None or not uuid_element.text:
        raise Exception("UUID not found in the XML.")
    uuid_value = uuid_element.text.strip()

    # Encode full XML
    xml_base64_encoded = base64.b64encode(xml_content).decode("utf-8")
    return {
        "uuid": uuid_value,
        "invoiceHash": encoded_hash,
        "invoice": xml_base64_encoded,
    }


# Not tested
def extract_canonical_xml(xml_file):
    """
    Remove ZATCA signature-related nodes and return the cleaned XML string.
    Used to generate a hash for the current invoice.
    """
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()

        namespaces = {
            "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
            "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
            "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
        }

        for ext_elem in root.findall(".//ext:UBLExtensions", namespaces):
            root.remove(ext_elem)

        for sig_elem in root.findall(".//cac:Signature", namespaces):
            root.remove(sig_elem)

        # Remove <cac:AdditionalDocumentReference> with cbc:ID == "QR"
        for doc_ref in root.findall(".//cac:AdditionalDocumentReference", namespaces):
            id_node = doc_ref.find(".//cbc:ID", namespaces)
            if id_node is not None and id_node.text == "QR":
                root.remove(doc_ref)

        return ET.tostring(root, encoding="unicode")
    except Exception as e:
        print(f"Error canonicalizing XML: {e}")
        return None


def generate_invoice_hash(xml_file=None):
    """
    Generate SHA-256 base64-encoded hash for invoice content.
    - If xml_file is provided, it extracts canonical XML and hashes it.
    - If xml_file is None or extraction fails, it defaults to hash of "0" (first invoice case).
    """
    content = None

    if xml_file:
        content = extract_canonical_xml(xml_file)

    if not content or str(content).strip() == "":
        content = "0"

    return base64.b64encode(hashlib.sha256(content.encode("utf-8")).digest()).decode("utf-8")
