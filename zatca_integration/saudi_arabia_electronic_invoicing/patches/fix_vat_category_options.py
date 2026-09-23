"""Clean the VAT Category Select options and the values already stored.

The field (``custom_vat_category`` on Customer / Supplier / Address) shipped with
a trailing TAB and a U+2060 WORD JOINER in its options, so values that carried
those characters (or a legacy spelling) no longer matched an option. A Select
only displays a value that is byte-identical to one of its options, which made
the field render blank and save blank.

Two things matter about the order of a ``bench migrate``:

* fixtures are synced *after* the post-model-sync patches, so a field (and even
  its column) may not exist here yet — both cases are handled; and
* the VAT Category option list itself is refreshed from
  ``fixtures/custom_field.json`` right after this patch, so values that look
  "unmatched" now may match again once the fixtures land.
"""

from collections import Counter

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

# Values found on records created before the option list was cleaned up, keyed by
# normalized name. The "VAT Category" doctype spells it "Oversees", while the
# Select option is "Overseas".
LEGACY_ALIASES = {
    "oversees": "Overseas",
}

MAX_REPORTED_VALUES = 5


def execute():
    rewrite_select_options()
    # options changed in the DB — drop the meta cache before reading them back
    frappe.clear_cache()
    fix_stored_values()
    frappe.clear_cache()


def rewrite_select_options():
    """Strip tabs / invisible characters and duplicates from the field options."""
    for doctype, fieldname in DOCTYPE_FIELD:
        custom_field = f"{doctype}-{fieldname}"
        current = frappe.db.get_value("Custom Field", custom_field, "options")
        if not current:
            continue  # field not present on this site

        options = []
        for option in current.split("\n"):
            cleaned = clean_vat_category(option)
            if cleaned and cleaned not in options:
                options.append(cleaned)
        if not options:
            continue

        cleaned_options = "\n" + "\n".join(options)
        if cleaned_options == current:
            continue

        frappe.db.set_value(
            "Custom Field", custom_field, "options", cleaned_options, update_modified=False
        )
        print(f"{custom_field}: options cleaned -> {options}")


def fix_stored_values():
    """Map stored values back onto an option so the Select keeps showing them."""
    fixed = 0
    unmatched = Counter()
    skipped = []

    for doctype, fieldname in DOCTYPE_FIELD:
        # The column only exists once the Custom Field is installed — fixtures are
        # synced after this patch, so never assume it is there.
        if not frappe.db.exists("DocType", doctype) or not frappe.db.has_column(doctype, fieldname):
            skipped.append(f"{doctype}.{fieldname}")
            continue

        allowed = get_vat_category_options(doctype, fieldname)
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
                unmatched[value] += 1

    if skipped:
        print(f"skipped (field/column not installed yet): {', '.join(skipped)}")
    print(f"VAT Category values normalised: {fixed}")

    if unmatched:
        total = sum(unmatched.values())
        sample = ", ".join(
            f"{value!r} x{count}" for value, count in unmatched.most_common(MAX_REPORTED_VALUES)
        )
        more = len(unmatched) - MAX_REPORTED_VALUES
        suffix = f" (+{more} more distinct value(s))" if more > 0 else ""
        print(
            f"VAT Category values that match no current option: {total} record(s) -> "
            f"{sample}{suffix}. Left untouched — the options are refreshed from fixtures "
            "right after this patch, so re-check any value that is still blank."
        )
