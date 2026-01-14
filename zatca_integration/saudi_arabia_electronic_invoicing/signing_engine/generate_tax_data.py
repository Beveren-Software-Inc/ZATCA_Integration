# ruff: noqa: E501
import json
import xml.etree.ElementTree as ET
from decimal import ROUND_HALF_UP, Decimal

import frappe
from frappe import _

from zatca_integration.saudi_arabia_electronic_invoicing.utils import (
    get_zatca_tax_category_details,
    get_zatca_tax_category_for_item,
)


def extract_tax_details_for_item(full_string, item):
    """
    Extracts the tax amount and tax percentage for a specific item from a JSON-encoded string.
    """
    try:
        data = json.loads(full_string)
        tax_percentage = data.get(item, [0, 0])[0]
        tax_amount = data.get(item, [0, 0])[1]
        return tax_amount, tax_percentage
    except json.JSONDecodeError as e:
        frappe.throw(_("JSON decoding error occurred in tax for item: " + str(e)))
        return None
    except KeyError as e:
        frappe.throw(_(f"Key error occurred while accessing item '{item}': " + str(e)))
        return None
    except TypeError as e:
        frappe.throw(_("Type error occurred in tax for item: " + str(e)))
        return None


def calculate_total_item_tax(sales_invoice_doc):
    """Getting tax total for items"""
    TAX_ERROR_MESSAGE = "Tax Calculation Error"
    try:
        total_tax = 0
        for single_item in sales_invoice_doc.items:
            _item_tax_amount, tax_percent = extract_tax_details_for_item(
                sales_invoice_doc.taxes[0].item_wise_tax_detail, single_item.item_code
            )
            total_tax = total_tax + (single_item.net_amount * (tax_percent / 100))
        return total_tax
    except AttributeError as e:
        frappe.throw(
            _(
                f"AttributeError in get_tax_total_from_items: {str(e)}",
                TAX_ERROR_MESSAGE,
            )
        )
        return None
    except KeyError as e:
        frappe.throw(_(f"KeyError in get_tax_total_from_items: {str(e)}", TAX_ERROR_MESSAGE))

        return None
    except TypeError as e:
        frappe.throw(_(f"KeyError in get_tax_total_from_items: {str(e)}", TAX_ERROR_MESSAGE))

        return None


# def build_zatca_tax_section(invoice, sales_invoice_doc):
#     """Extract ZATCA-compliant tax data into UBL XML format"""
#     try:
#         details = get_zatca_tax_category_details(sales_invoice_doc)

#         # Calculate Tax Amount
#         tax_amount = Decimal(str(abs(calculate_total_item_tax(sales_invoice_doc)))).quantize(
#             Decimal("0.01"), rounding=ROUND_HALF_UP
#         )

#         # Calculate Taxable Amount- changes
#         # if sales_invoice_doc.taxes[0].included_in_print_rate == 0:
#         #     taxable_amount = Decimal(str(sales_invoice_doc.base_total)) - Decimal(str(sales_invoice_doc.get("base_discount_amount", 0.0)))
#         # else:
#         #     taxable_amount = Decimal(str(sales_invoice_doc.base_net_total)) - Decimal(str(sales_invoice_doc.get("base_discount_amount", 0.0)))
#         if sales_invoice_doc.taxes[0].included_in_print_rate == 0:
#             taxable_amount = Decimal(str(sales_invoice_doc.total)) - Decimal(str(sales_invoice_doc.get("discount_amount", 0.0)))
#         else:
#             taxable_amount = Decimal(str(sales_invoice_doc.net_total)) - Decimal(str(sales_invoice_doc.get("discount_amount", 0.0)))


#         # Tax Total (SAR only if SAR)
#         if sales_invoice_doc.currency == "SAR":
#             sar_taxtotal = ET.SubElement(invoice, "cac:TaxTotal")
#             sar_taxamount = ET.SubElement(sar_taxtotal, "cbc:TaxAmount")
#             sar_taxamount.set("currencyID", "SAR")
#             sar_taxamount.text = str(tax_amount)

#         # General Tax Total
#         taxtotal = ET.SubElement(invoice, "cac:TaxTotal")
#         taxamount = ET.SubElement(taxtotal, "cbc:TaxAmount")
#         taxamount.set("currencyID", sales_invoice_doc.currency)
#         taxamount.text = str(tax_amount)

#         # Tax Subtotal

#         tax_subtotal = ET.SubElement(taxtotal, "cac:TaxSubtotal")
#         taxable_amt_elem = ET.SubElement(tax_subtotal, "cbc:TaxableAmount")
#         taxable_amt_elem.set("currencyID", sales_invoice_doc.currency)
#         taxable_amt_elem.text = str(abs(round(taxable_amount, 2)))

#         subtotal_tax_amt = ET.SubElement(tax_subtotal, "cbc:TaxAmount")
#         subtotal_tax_amt.set("currencyID", sales_invoice_doc.currency)
#         subtotal_tax_amt.text = str(tax_amount)

#         # Tax Category
#         tax_category = ET.SubElement(tax_subtotal, "cac:TaxCategory")
#         tax_id = ET.SubElement(tax_category, "cbc:ID")
#         tax_id.text = details["code"]

#         tax_percent = ET.SubElement(tax_category, "cbc:Percent")
#         tax_percent.text = f"{float(details['rate']):.2f}"

#         if details["category"] != "Standard Rate":
#             exemption_code = ET.SubElement(tax_category, "cbc:TaxExemptionReasonCode")
#             exemption_code.text = details["exemption_reason_code"]

#             exemption_text = ET.SubElement(tax_category, "cbc:TaxExemptionReason")
#             exemption_text.text = details["exemption_reason_text"]

#         tax_scheme = ET.SubElement(tax_category, "cac:TaxScheme")
#         tax_scheme_id = ET.SubElement(tax_scheme, "cbc:ID")
#         tax_scheme_id.text = "VAT"

#         # Legal Monetary Total
#         legal_total = ET.SubElement(invoice, "cac:LegalMonetaryTotal")

#         line_ext_amt = ET.SubElement(legal_total, "cbc:LineExtensionAmount")
#         line_ext_amt.set("currencyID", sales_invoice_doc.currency)
#         line_ext_amt.text = str(round(
#             abs(sales_invoice_doc.total if sales_invoice_doc.taxes[0].included_in_print_rate == 0 else sales_invoice_doc.base_net_total),
#             2
#         ))

#         tax_exclusive = ET.SubElement(legal_total, "cbc:TaxExclusiveAmount")
#         tax_exclusive.set("currencyID", sales_invoice_doc.currency)
#         tax_exclusive.text = str(abs(round(taxable_amount, 2)))

#         tax_inclusive = ET.SubElement(legal_total, "cbc:TaxInclusiveAmount")
#         tax_inclusive.set("currencyID", sales_invoice_doc.currency)
#         tax_inclusive.text = str(abs(round(abs(taxable_amount) + abs(tax_amount), 2)))

#         allowance = ET.SubElement(legal_total, "cbc:AllowanceTotalAmount")
#         allowance.set("currencyID", sales_invoice_doc.currency)
#         allowance.text = str(abs(sales_invoice_doc.get("discount_amount", 0.0)))

#         total_amount = abs(taxable_amount) + abs(tax_amount)

#         payable = ET.SubElement(legal_total, "cbc:PayableAmount")
#         payable.set("currencyID", sales_invoice_doc.currency)
#         payable.text = str(abs(round(total_amount, 2)))

#         return invoice

#     except Exception as e:
#         frappe.throw(_("Data processing error in tax_data: {0}").format(str(e)))
#         return None


def build_zatca_tax_section(invoice, sales_invoice_doc):
    """Extract ZATCA-compliant tax data into UBL XML format with support for mixed tax categories"""
    try:
        # Document currency code (BT-5)
        doc_currency = sales_invoice_doc.currency
        included_in_rate = (
            sales_invoice_doc.taxes[0].included_in_print_rate
            if sales_invoice_doc.taxes and sales_invoice_doc.taxes[0].included_in_print_rate
            else 0
        )

        # Group items by tax category
        tax_category_totals = {}
        total_tax_amount = Decimal("0")
        total_taxable_amount = Decimal("0")

        # Get item-wise tax details
        item_wise_tax_detail = (
            json.loads(sales_invoice_doc.taxes[0].item_wise_tax_detail)
            if sales_invoice_doc.taxes
            and sales_invoice_doc.taxes[0].item_wise_tax_detail
            else {}
        )

        for item in sales_invoice_doc.items:
            # Get tax category for this item
            item_tax_details = get_zatca_tax_category_for_item(sales_invoice_doc, item)
            category_key = item_tax_details["category"]

            # Calculate item taxable amount
            if included_in_rate:
                # Tax included: extract base amount
                item_tax_rate = Decimal(str(item_tax_details["rate"]))
                item_base_amount = Decimal(str(item.net_amount)) / (
                    Decimal("1") + item_tax_rate / Decimal("100")
                )
            else:
                # Tax excluded: use net_amount directly
                item_base_amount = Decimal(str(item.net_amount))

            # Get tax amount for this item from item_wise_tax_detail
            item_tax_amount = Decimal("0")
            if item.item_code in item_wise_tax_detail:
                item_tax_amount = Decimal(str(abs(item_wise_tax_detail[item.item_code][1])))

            # Initialize category if not exists
            if category_key not in tax_category_totals:
                tax_category_totals[category_key] = {
                    "details": item_tax_details,
                    "taxable_amount": Decimal("0"),
                    "tax_amount": Decimal("0"),
                }

            # Accumulate amounts for this category
            tax_category_totals[category_key]["taxable_amount"] += item_base_amount
            tax_category_totals[category_key]["tax_amount"] += item_tax_amount
            total_taxable_amount += item_base_amount
            total_tax_amount += item_tax_amount

        # Apply document-level discount proportionally (if any)
        discount_amount = Decimal(str(sales_invoice_doc.get("discount_amount", 0.0)))
        if discount_amount and total_taxable_amount:
            discount_ratio = discount_amount / total_taxable_amount
            for category_key in tax_category_totals:
                category_discount = tax_category_totals[category_key]["taxable_amount"] * discount_ratio
                tax_category_totals[category_key]["taxable_amount"] -= category_discount
            total_taxable_amount -= discount_amount

        # --- Main TaxTotal in Document Currency (BT-110) ---
        # First, recalculate tax amounts for each category to ensure BT-117 = BT-116 × (BT-119 / 100)
        recalculated_total_tax_amount = Decimal("0")
        for category_key, category_data in tax_category_totals.items():
            taxable_amount = abs(category_data["taxable_amount"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            tax_rate = Decimal(str(category_data["details"]["rate"]))
            calculated_tax_amount = taxable_amount * tax_rate / Decimal("100")
            calculated_tax_amount = calculated_tax_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            recalculated_total_tax_amount += abs(calculated_tax_amount)
        
        taxtotal = ET.SubElement(invoice, "cac:TaxTotal")
        taxamount_elem = ET.SubElement(taxtotal, "cbc:TaxAmount")
        taxamount_elem.set("currencyID", doc_currency)
        # Use recalculated total to ensure BT-110 matches sum of all category tax amounts
        taxamount_elem.text = str(recalculated_total_tax_amount)

        # Create TaxSubtotal for each category (BG-23)
        for category_key, category_data in tax_category_totals.items():
            tax_subtotal = ET.SubElement(taxtotal, "cac:TaxSubtotal")

            taxable_amt_elem = ET.SubElement(tax_subtotal, "cbc:TaxableAmount")
            taxable_amt_elem.set("currencyID", doc_currency)
            taxable_amount = abs(category_data["taxable_amount"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            taxable_amt_elem.text = str(taxable_amount)

            # ZATCA Requirement: BT-117 (TaxAmount) = BT-116 (TaxableAmount) × (BT-119 (Percent) / 100)
            # Recalculate to ensure exact match per ZATCA validation rules
            tax_rate = Decimal(str(category_data["details"]["rate"]))
            calculated_tax_amount = taxable_amount * tax_rate / Decimal("100")
            calculated_tax_amount = calculated_tax_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            subtotal_tax_amt = ET.SubElement(tax_subtotal, "cbc:TaxAmount")
            subtotal_tax_amt.set("currencyID", doc_currency)
            subtotal_tax_amt.text = str(abs(calculated_tax_amount))

            tax_category = ET.SubElement(tax_subtotal, "cac:TaxCategory")
            tax_id = ET.SubElement(tax_category, "cbc:ID")
            tax_id.text = category_data["details"]["code"]

            tax_percent = ET.SubElement(tax_category, "cbc:Percent")
            tax_percent.text = f"{float(category_data['details']['rate']):.2f}"

            if category_data["details"]["category"] != "Standard Rate":
                if category_data["details"]["exemption_reason_code"]:
                    exemption_code = ET.SubElement(tax_category, "cbc:TaxExemptionReasonCode")
                    exemption_code.text = category_data["details"]["exemption_reason_code"]

                if category_data["details"]["exemption_reason_text"]:
                    exemption_text = ET.SubElement(tax_category, "cbc:TaxExemptionReason")
                    exemption_text.text = category_data["details"]["exemption_reason_text"]

            tax_scheme = ET.SubElement(tax_category, "cac:TaxScheme")
            tax_scheme_id = ET.SubElement(tax_scheme, "cbc:ID")
            tax_scheme_id.text = "VAT"

        # --- VAT accounting currency (SAR) total (BT-111) ---
        if doc_currency != "SDAR":
            sar_taxtotal = ET.SubElement(invoice, "cac:TaxTotal")
            sar_taxamount = ET.SubElement(sar_taxtotal, "cbc:TaxAmount")
            sar_taxamount.set("currencyID", "SAR")

            # Convert VAT to SAR using conversion_rate from invoice
            conversion_rate = Decimal(str(sales_invoice_doc.get("conversion_rate", 1))) or Decimal(
                "1"
            )
            # Use recalculated total tax amount for consistency
            sar_vat_amount = (recalculated_total_tax_amount * conversion_rate).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            sar_taxamount.text = str(sar_vat_amount)

        # --- Legal Monetary Total ---
        legal_total = ET.SubElement(invoice, "cac:LegalMonetaryTotal")

        line_ext_amt = ET.SubElement(legal_total, "cbc:LineExtensionAmount")
        line_ext_amt.set("currencyID", doc_currency)
        line_ext_amt.text = str(
            round(
                abs(
                    sales_invoice_doc.total
                    if included_in_rate == 0
                    else sales_invoice_doc.net_total
                ),
                2,
            )
        )

        tax_exclusive = ET.SubElement(legal_total, "cbc:TaxExclusiveAmount")
        tax_exclusive.set("currencyID", doc_currency)
        tax_exclusive.text = str(abs(total_taxable_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)))

        tax_inclusive = ET.SubElement(legal_total, "cbc:TaxInclusiveAmount")
        tax_inclusive.set("currencyID", doc_currency)
        # BT-112: Use recalculated total tax amount to ensure consistency
        tax_inclusive_amount = (total_taxable_amount + recalculated_total_tax_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        tax_inclusive.text = str(abs(tax_inclusive_amount))

        allowance = ET.SubElement(legal_total, "cbc:AllowanceTotalAmount")
        allowance.set("currencyID", doc_currency)
        allowance.text = str(abs(discount_amount))

        # Use recalculated total tax amount for payable amount
        total_amount = total_taxable_amount + recalculated_total_tax_amount

        payable = ET.SubElement(legal_total, "cbc:PayableAmount")
        payable.set("currencyID", doc_currency)
        payable.text = str(abs(total_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)))

        return invoice

    except Exception as e:
        frappe.throw(_("Data processing error in tax_data: {0}").format(str(e)))
        return None


def fix_tax_amounts(sales_invoice_doc, taxable_amount):
    """Ensure TaxExclusiveAmount, LineExtensionAmount, and TaxableAmount are aligned."""
    # Sum of all line extension amounts
    line_sum = sum(
        Decimal(str(item.get("amount", 0.0))) for item in sales_invoice_doc.items
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    taxable_amount = Decimal(str(taxable_amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if line_sum != taxable_amount:
        frappe.logger().warning(f"Fixing taxable_amount: was {taxable_amount}, set to {line_sum}")
        taxable_amount = line_sum

    return taxable_amount, line_sum


# def build_zatca_tax_section(invoice, sales_invoice_doc):
#     """Extract ZATCA-compliant tax data into UBL XML format"""
#     try:
#         details = get_zatca_tax_category_details(sales_invoice_doc)

#         # Calculate Tax Amount
#         tax_amount = Decimal(str(abs(calculate_total_item_tax(sales_invoice_doc)))).quantize(
#             Decimal("0.01"), rounding=ROUND_HALF_UP
#         )

#         # Calculate Taxable Amount- changes
#         # if sales_invoice_doc.taxes[0].included_in_print_rate == 0:
#         #     taxable_amount = Decimal(str(sales_invoice_doc.base_total)) - Decimal(str(sales_invoice_doc.get("base_discount_amount", 0.0)))
#         # else:
#         #     taxable_amount = Decimal(str(sales_invoice_doc.base_net_total)) - Decimal(str(sales_invoice_doc.get("base_discount_amount", 0.0)))
#         if sales_invoice_doc.taxes[0].included_in_print_rate == 0:
#             taxable_amount = Decimal(str(sales_invoice_doc.total)) - Decimal(str(sales_invoice_doc.get("discount_amount", 0.0)))
#         else:
#             taxable_amount = Decimal(str(sales_invoice_doc.net_total)) - Decimal(str(sales_invoice_doc.get("discount_amount", 0.0)))


#         # Tax Total (SAR only if SAR)
#         if sales_invoice_doc.currency == "SAR":
#             sar_taxtotal = ET.SubElement(invoice, "cac:TaxTotal")
#             sar_taxamount = ET.SubElement(sar_taxtotal, "cbc:TaxAmount")
#             sar_taxamount.set("currencyID", "SAR")
#             sar_taxamount.text = str(tax_amount)

#         # General Tax Total
#         taxtotal = ET.SubElement(invoice, "cac:TaxTotal")
#         taxamount = ET.SubElement(taxtotal, "cbc:TaxAmount")
#         taxamount.set("currencyID", sales_invoice_doc.currency)
#         taxamount.text = str(tax_amount)

#         # Tax Subtotal

#         if sales_invoice_doc.tax_currency != "SAR" or sales_invoice_doc.tax_currency == sales_invoice_doc.currency:
#             tax_subtotal = ET.SubElement(taxtotal, "cac:TaxSubtotal")
#             taxable_amt_elem = ET.SubElement(tax_subtotal, "cbc:TaxableAmount")
#             taxable_amt_elem.set("currencyID", sales_invoice_doc.currency)
#             taxable_amt_elem.text = str(abs(round(taxable_amount, 2)))

#             subtotal_tax_amt = ET.SubElement(tax_subtotal, "cbc:TaxAmount")
#             subtotal_tax_amt.set("currencyID", sales_invoice_doc.currency)
#             subtotal_tax_amt.text = str(tax_amount)

#         # Tax Category
#         tax_category = ET.SubElement(tax_subtotal, "cac:TaxCategory")
#         tax_id = ET.SubElement(tax_category, "cbc:ID")
#         tax_id.text = details["code"]

#         tax_percent = ET.SubElement(tax_category, "cbc:Percent")
#         tax_percent.text = f"{float(details['rate']):.2f}"

#         if details["category"] != "Standard Rate":
#             exemption_code = ET.SubElement(tax_category, "cbc:TaxExemptionReasonCode")
#             exemption_code.text = details["exemption_reason_code"]

#             exemption_text = ET.SubElement(tax_category, "cbc:TaxExemptionReason")
#             exemption_text.text = details["exemption_reason_text"]

#         tax_scheme = ET.SubElement(tax_category, "cac:TaxScheme")
#         tax_scheme_id = ET.SubElement(tax_scheme, "cbc:ID")
#         tax_scheme_id.text = "VAT"

#         # Legal Monetary Total
#         legal_total = ET.SubElement(invoice, "cac:LegalMonetaryTotal")

#         line_ext_amt = ET.SubElement(legal_total, "cbc:LineExtensionAmount")
#         line_ext_amt.set("currencyID", sales_invoice_doc.currency)
#         line_ext_amt.text = str(round(
#             abs(sales_invoice_doc.total if sales_invoice_doc.taxes[0].included_in_print_rate == 0 else sales_invoice_doc.base_net_total),
#             2
#         ))

#         tax_exclusive = ET.SubElement(legal_total, "cbc:TaxExclusiveAmount")
#         tax_exclusive.set("currencyID", sales_invoice_doc.currency)
#         tax_exclusive.text = str(abs(round(taxable_amount, 2)))

#         tax_inclusive = ET.SubElement(legal_total, "cbc:TaxInclusiveAmount")
#         tax_inclusive.set("currencyID", sales_invoice_doc.currency)
#         tax_inclusive.text = str(abs(round(abs(taxable_amount) + abs(tax_amount), 2)))

#         allowance = ET.SubElement(legal_total, "cbc:AllowanceTotalAmount")
#         allowance.set("currencyID", sales_invoice_doc.currency)
#         allowance.text = str(abs(sales_invoice_doc.get("discount_amount", 0.0)))

#         total_amount = abs(taxable_amount) + abs(tax_amount)

#         payable = ET.SubElement(legal_total, "cbc:PayableAmount")
#         payable.set("currencyID", sales_invoice_doc.currency)
#         payable.text = str(abs(round(total_amount, 2)))

#         return invoice

#     except Exception as e:
#         frappe.throw(_("Data processing error in tax_data: {0}").format(str(e)))
#         return None
