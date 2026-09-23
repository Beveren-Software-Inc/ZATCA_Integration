"""Customer ZATCA field validation and client mandatory rules."""

from __future__ import annotations

import frappe
from frappe import _

from zatca_integration.common_util import (
    canonicalize_vat_category_field,
    get_customer_vat_category,
    get_vat_validation_settings,
    is_export_vat_category,
    is_vat_number_required,
    validate_ksa_vat_number,
)


def is_overseas_customer(doc) -> bool:
    """Buyer outside KSA, or an Overseas / Export / Deemed Export VAT category."""
    if is_export_vat_category(get_customer_vat_category(doc)):
        return True

    country = str(doc.get("custom_country") or "").strip()
    return bool(country) and country.casefold() != "saudi arabia"


def get_overseas_reason(doc) -> str:
    """
    Why the overseas / export rules apply, as a message fragment.

    The country is checked first, so a Saudi Arabia customer is never described
    as being abroad — for those the Overseas / Export VAT Category is named.
    """
    country = str(doc.get("custom_country") or "").strip()
    if country and country.casefold() != "saudi arabia":
        return _("is outside Saudi Arabia (Country: {0})").format(_(country))

    category = get_customer_vat_category(doc)
    return _('has the overseas / export VAT Category "{0}"').format(_(category) or _("Overseas"))


def is_saudi_registered_company(doc) -> bool:
    """Company in KSA with a domestic (non-Overseas/Export) VAT category."""
    if doc.get("customer_type") != "Company":
        return False
    if str(doc.get("custom_country") or "").strip().casefold() != "saudi arabia":
        return False
    return not is_export_vat_category(get_customer_vat_category(doc))


def has_vat_number(doc) -> bool:
    return bool((doc.get("custom_vat_number") or doc.get("tax_id") or "").strip())


def has_registration(doc) -> bool:
    return bool(
        (doc.get("custom_registration_scheme") or "").strip()
        and (doc.get("custom_registration_number") or "").strip()
    )


def validate(doc, method=None):
    """Server-side Customer rules for ZATCA identification fields."""
    # Keep the VAT Category Select matching its options (invisible characters or
    # a different case make the field render blank and save blank again).
    canonicalize_vat_category_field(doc)

    # Format-check VAT whenever provided for Saudi Arabia customers
    country = (doc.get("custom_country") or "").strip()
    vat_value = (doc.get("custom_vat_number") or "").strip() or (doc.get("tax_id") or "").strip()
    if vat_value and country.casefold() == "saudi arabia":
        validate_ksa_vat_number(vat_value, field_label=_("VAT Number"))

    # Individuals: ZATCA company identification is not required
    if doc.get("customer_type") == "Individual":
        return

    if doc.get("customer_type") != "Company":
        return

    if not country:
        frappe.throw(
            _("Customer Country is required for Company customers."),
            title=_("Missing Country"),
        )

    if is_overseas_customer(doc):
        # VAT number not mandatory for overseas / Export category.
        # Allow save without registration number, but warn so users can fill it.
        registration_number = (doc.get("custom_registration_number") or "").strip()
        if not registration_number:
            frappe.msgprint(
                _(
                    "This company customer {0}. No Registration Number was entered. You can "
                    "still save, but adding a Registration Scheme and Registration Number is "
                    "recommended for ZATCA."
                ).format(get_overseas_reason(doc)),
                title=_("Registration Number Recommended"),
                indicator="orange",
            )
        return

    # Saudi Arabia + Company + domestic VAT category.
    # Whether a VAT Number is mandatory is controlled by "Zatca Settings":
    # - Validate VAT No Against All Company: every company must provide one
    # - Validate VAT No Against Registered Company: only VAT-registered companies
    if (
        is_saudi_registered_company(doc)
        and is_vat_number_required(doc)
        and not (has_vat_number(doc) or has_registration(doc))
    ):
        frappe.throw(
            _(
                "Saudi company customers must have a VAT Number, or both "
                "Registration Scheme and Registration Number."
            ),
            title=_("ZATCA Details Required"),
        )


@frappe.whitelist()
def get_customer_vat_validation_settings():
    """Expose the VAT Number validation switches to the Customer form."""
    return get_vat_validation_settings()
