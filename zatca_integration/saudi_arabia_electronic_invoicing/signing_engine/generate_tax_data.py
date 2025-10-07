import json
import xml.etree.ElementTree as ET
from decimal import ROUND_HALF_UP, Decimal

import frappe
from frappe import _

from zatca_integration.saudi_arabia_electronic_invoicing.utils import get_zatca_tax_category_details


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
    """Extract ZATCA-compliant tax data into UBL XML format"""
    try:
        details = get_zatca_tax_category_details(sales_invoice_doc)

        # Calculate total VAT amount (BT-110)
        tax_amount = Decimal(str(abs(calculate_total_item_tax(sales_invoice_doc)))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        # Calculate taxable amount (net of discounts)
        if sales_invoice_doc.taxes[0].included_in_print_rate == 0:
            taxable_amount = Decimal(str(sales_invoice_doc.total)) - Decimal(
                str(sales_invoice_doc.get("discount_amount", 0.0))
            )
        else:
            taxable_amount = Decimal(str(sales_invoice_doc.net_total)) - Decimal(
                str(sales_invoice_doc.get("discount_amount", 0.0))
            )

        # Document currency code (BT-5)
        doc_currency = sales_invoice_doc.currency

        # --- Main TaxTotal in Document Currency (BT-110) ---
        taxtotal = ET.SubElement(invoice, "cac:TaxTotal")
        taxamount_elem = ET.SubElement(taxtotal, "cbc:TaxAmount")
        taxamount_elem.set("currencyID", doc_currency)
        taxamount_elem.text = str(tax_amount)

        # VAT breakdown (BG-23)
        tax_subtotal = ET.SubElement(taxtotal, "cac:TaxSubtotal")

        taxable_amt_elem = ET.SubElement(tax_subtotal, "cbc:TaxableAmount")
        taxable_amt_elem.set("currencyID", doc_currency)
        taxable_amt_elem.text = str(abs(round(taxable_amount, 2)))

        subtotal_tax_amt = ET.SubElement(tax_subtotal, "cbc:TaxAmount")
        subtotal_tax_amt.set("currencyID", doc_currency)
        subtotal_tax_amt.text = str(tax_amount)

        tax_category = ET.SubElement(tax_subtotal, "cac:TaxCategory")
        tax_id = ET.SubElement(tax_category, "cbc:ID")
        tax_id.text = details["code"]

        tax_percent = ET.SubElement(tax_category, "cbc:Percent")
        tax_percent.text = f"{float(details['rate']):.2f}"

        if details["category"] != "Standard Rate":
            exemption_code = ET.SubElement(tax_category, "cbc:TaxExemptionReasonCode")
            exemption_code.text = details["exemption_reason_code"]

            exemption_text = ET.SubElement(tax_category, "cbc:TaxExemptionReason")
            exemption_text.text = details["exemption_reason_text"]

        tax_scheme = ET.SubElement(tax_category, "cac:TaxScheme")
        tax_scheme_id = ET.SubElement(tax_scheme, "cbc:ID")
        tax_scheme_id.text = "VAT"

        # --- VAT accounting currency (SAR) total (BT-111) ---
        # Check o this
        if doc_currency != "SDAR":
            sar_taxtotal = ET.SubElement(invoice, "cac:TaxTotal")
            sar_taxamount = ET.SubElement(sar_taxtotal, "cbc:TaxAmount")
            sar_taxamount.set("currencyID", "SAR")

            # Convert VAT to SAR using conversion_rate from invoice
            conversion_rate = Decimal(str(sales_invoice_doc.get("conversion_rate", 1))) or Decimal(
                "1"
            )
            sar_vat_amount = (tax_amount * conversion_rate).quantize(
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
                    if sales_invoice_doc.taxes[0].included_in_print_rate == 0
                    else sales_invoice_doc.net_total
                ),
                2,
            )
        )

        tax_exclusive = ET.SubElement(legal_total, "cbc:TaxExclusiveAmount")
        tax_exclusive.set("currencyID", doc_currency)
        tax_exclusive.text = str(abs(round(taxable_amount, 2)))

        tax_inclusive = ET.SubElement(legal_total, "cbc:TaxInclusiveAmount")
        tax_inclusive.set("currencyID", doc_currency)
        tax_inclusive.text = str(abs(round(abs(taxable_amount) + abs(tax_amount), 2)))

        allowance = ET.SubElement(legal_total, "cbc:AllowanceTotalAmount")
        allowance.set("currencyID", doc_currency)
        allowance.text = str(abs(sales_invoice_doc.get("discount_amount", 0.0)))

        total_amount = abs(taxable_amount) + abs(tax_amount)

        payable = ET.SubElement(legal_total, "cbc:PayableAmount")
        payable.set("currencyID", doc_currency)
        payable.text = str(abs(round(total_amount, 2)))

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
