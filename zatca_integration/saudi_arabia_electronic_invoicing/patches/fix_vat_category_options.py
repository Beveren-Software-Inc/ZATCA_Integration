"""Clean the VAT Category Select options and the values already stored.

The options shipped with a trailing TAB and a U+2060 WORD JOINER
('\\nRegistered\\t\\n\u2060Unregistered\\t\\n\u2060Overseas\\t\\n\u2060Government\\n\u2060Exempt').
A Select only displays a value that is byte-identical to one of its options, so
values that kept those characters (or the legacy "Oversees" spelling) rendered
blank and were cleared on the next save.
"""

import frappe

from zatca_integration.common_util import (
    clean_vat_category,
    get_vat_category_options,
    normalize_vat_category,
)

DOCTYPE_FIELD = (
    ("Customer", "custom_vat_category"),
    ("Supplier", "custom_vat_category"),
    ("Address", "custom_vat_category"),
)

CLEAN_OPTIONS = "\nRegistered\nUnregistered\nOverseas\nGovernment\nExempt"

# Values found on records created before the option list was cleaned up, keyed by
# normalized name. The "VAT Category" doctype spells it "Oversees", while the
# Select option is "Overseas".
LEGACY_ALIASES = {
    "oversees": "Overseas",
}


def execute():
    rewrite_select_options()
    # options changed in the DB — drop the meta cache before reading them back
    frappe.clear_cache()
    fix_stored_values()
    frappe.clear_cache()


def rewrite_select_options():
    """Strip tabs / invisible characters from the Custom Field options."""
    for doctype, fieldname in DOCTYPE_FIELD:
        name = f"{doctype}-{fieldname}"
        current = frappe.db.get_value("Custom Field", name, "options")
        if not current:
            continue

        options = [clean_vat_category(part).strip() for part in current.split("\n")]
        cleaned = "\n" + "\n".join(dict.fromkeys(option for option in options if option))
        if cleaned == current:
            continue

        frappe.db.set_value("Custom Field", name, "options", cleaned, update_modified=False)
        print(f"{name}: options cleaned")


def fix_stored_values():
    """Map stored values back onto an option so the Select keeps showing them."""
    fixed, unmapped = 0, 0
    for doctype, fieldname in DOCTYPE_FIELD:
        if not frappe.db.exists("DocType", doctype):
            continue

        allowed = get_vat_category_options(doctype, fieldname) or CLEAN_OPTIONS.strip().split("\n")
        by_normalized = {normalize_vat_category(option): option for option in allowed}

        rows = frappe.get_all(
            doctype,
            filters={fieldname: ["is", "set"]},
            fields=["name", fieldname],
            limit_page_length=0,
        )
        for row in rows:
            value = row.get(fieldname) or ""
            if not value:
                continue

            normalized = normalize_vat_category(value)
            canonical = by_normalized.get(normalized) or LEGACY_ALIASES.get(normalized)
            if canonical and canonical != value:
                frappe.db.set_value(
                    doctype, row["name"], fieldname, canonical, update_modified=False
                )
                fixed += 1
            elif canonical is None:
                unmapped += 1
                print(f"  ! {doctype} {row['name']}: {value!r} matches no option {allowed}")

    print(f"values fixed: {fixed}; unmatched (left untouched): {unmapped}")
