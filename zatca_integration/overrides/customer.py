"""Customer ZATCA field validation and client mandatory rules."""

from __future__ import annotations

import frappe
from frappe import _

from zatca_integration.common_util import validate_ksa_vat_number

EXPORT_VAT_CATEGORIES = {"Export / Non-Resident"}


def get_customer_vat_category(doc) -> str:
    """Prefer Tax Category (labeled VAT Category); fall back to custom select if present."""
    return (doc.get("tax_category") or doc.get("custom_vat_category") or "").strip()


def is_overseas_customer(doc) -> bool:
    country = (doc.get("custom_country") or "").strip()
    vat_category = get_customer_vat_category(doc)
    return (bool(country) and country != "Saudi Arabia") or vat_category in EXPORT_VAT_CATEGORIES


def is_saudi_registered_company(doc) -> bool:
    """Company in KSA with a domestic / registered VAT category (not Export)."""
    if doc.get("customer_type") != "Company":
        return False
    if (doc.get("custom_country") or "").strip() != "Saudi Arabia":
        return False
    return get_customer_vat_category(doc) not in EXPORT_VAT_CATEGORIES


def has_vat_number(doc) -> bool:
    return bool((doc.get("custom_vat_number") or doc.get("tax_id") or "").strip())


def has_registration(doc) -> bool:
    return bool(
        (doc.get("custom_registration_scheme") or "").strip()
        and (doc.get("custom_registration_number") or "").strip()
    )


def validate(doc, method=None):
    """Server-side Customer rules for ZATCA identification fields."""
    # Format-check VAT whenever provided for Saudi Arabia customers
    country = (doc.get("custom_country") or "").strip()
    vat_value = (doc.get("custom_vat_number") or "").strip() or (doc.get("tax_id") or "").strip()
    if vat_value and country == "Saudi Arabia":
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
                    "This company customer is outside Saudi Arabia (or Export / Non-Resident). "
                    "No Registration Number was entered. You can still save, but adding a "
                    "Registration Scheme and Registration Number is recommended for ZATCA."
                ),
                title=_("Registration Number Recommended"),
                indicator="orange",
            )
        return

    # Saudi Arabia + Company + domestic/registered VAT category
    if is_saudi_registered_company(doc) and not (has_vat_number(doc) or has_registration(doc)):
        frappe.throw(
            _(
                "Saudi company customers must have a VAT Number, or both "
                "Registration Scheme and Registration Number."
            ),
            title=_("ZATCA Details Required"),
        )
