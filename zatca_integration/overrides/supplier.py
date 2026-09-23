"""Supplier ZATCA field validation and client mandatory rules."""

from __future__ import annotations

import frappe
from frappe import _

from zatca_integration.common_util import (
    canonicalize_vat_category_field,
    is_registered_vat_category,
    validate_ksa_vat_number,
)

# Supplier fields that can carry the tax / VAT registration number.
TAX_NUMBER_FIELDS = ("tax_id", "custom_vat_number", "ksa_tax_id")


def get_supplier_vat_category(doc) -> str:
    """VAT Category of a Supplier (Document or dict), Tax Category taking precedence."""
    return (doc.get("tax_category") or doc.get("custom_vat_category") or "").strip()


def get_supplier_tax_number(doc) -> str:
    """First non-empty tax number on the supplier."""
    for fieldname in TAX_NUMBER_FIELDS:
        value = (doc.get(fieldname) or "").strip()
        if value:
            return value
    return ""


def is_saudi_supplier(doc) -> bool:
    country = str(doc.get("country") or "").strip()
    return bool(country) and country.casefold() == "saudi arabia"


def validate(doc, method=None):
    """Server-side Supplier rules for ZATCA identification fields."""
    # Keep the VAT Category Select matching its options (invisible characters or
    # a different case make the field render blank and save blank again).
    canonicalize_vat_category_field(doc)

    tax_number = get_supplier_tax_number(doc)
    if tax_number and is_saudi_supplier(doc):
        validate_ksa_vat_number(tax_number, field_label=_("Tax ID"))

    category = get_supplier_vat_category(doc)
    if not is_registered_vat_category(category):
        # Unregistered / Overseas / Government / Exempt suppliers must not carry
        # a VAT Number, so nothing is mandatory for them.
        return

    if not tax_number:
        frappe.throw(
            _(
                'Supplier VAT Category "{0}" means the supplier is VAT registered, '
                "so Tax ID (VAT Number) is mandatory."
            ).format(_(category)),
            title=_("VAT Number Required"),
        )
