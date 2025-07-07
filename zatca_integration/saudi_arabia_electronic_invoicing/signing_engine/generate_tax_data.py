

import json
import xml.etree.ElementTree as ET
from frappe import _
import frappe
from decimal import Decimal, ROUND_HALF_UP

TAX_CALCULATION_ERROR = "Tax Calculation Error"
CAC_TAX_TOTAL = "cac:TaxTotal"

from zatca_integration.saudi_arabia_electronic_invoicing.utils import get_exemption_reason_map , get_zatca_tax_category_details


def get_tax_for_item(full_string, item):
    """
    Extracts the tax amount and tax percentage for a specific item from a JSON-encoded string.
    """
    try:  # getting tax percentage and tax amount
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


def get_tax_total_from_items(sales_invoice_doc):
    """Getting tax total for items"""
    try:
        total_tax = 0
        for single_item in sales_invoice_doc.items:
            _item_tax_amount, tax_percent = get_tax_for_item(
                sales_invoice_doc.taxes[0].item_wise_tax_detail, single_item.item_code
            )
            total_tax = total_tax + (single_item.net_amount * (tax_percent / 100))
        return total_tax
    except AttributeError as e:
        frappe.throw(
            _(
                f"AttributeError in get_tax_total_from_items: {str(e)}",
                TAX_CALCULATION_ERROR,
            )
        )
        return None
    except KeyError as e:
        frappe.throw(
            _(f"KeyError in get_tax_total_from_items: {str(e)}", TAX_CALCULATION_ERROR)
        )

        return None
    except TypeError as e:
        frappe.throw(
            _(f"KeyError in get_tax_total_from_items: {str(e)}", TAX_CALCULATION_ERROR)
        )

        return None

def tax_data(invoice, sales_invoice_doc):
    """Extract ZATCA-compliant tax data into UBL XML format"""
    
    try:
        details = get_zatca_tax_category_details(sales_invoice_doc)

        # Calculate Tax Amount
        tax_amount = Decimal(str(abs(get_tax_total_from_items(sales_invoice_doc)))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        # Calculate Taxable Amount
        if sales_invoice_doc.taxes[0].included_in_print_rate == 0:
            taxable_amount = Decimal(str(sales_invoice_doc.base_total)) - Decimal(str(sales_invoice_doc.get("base_discount_amount", 0.0)))
        else:
            taxable_amount = Decimal(str(sales_invoice_doc.base_net_total)) - Decimal(str(sales_invoice_doc.get("base_discount_amount", 0.0)))


        # Tax Total (SAR only if SAR)
        if sales_invoice_doc.currency == "SAR":
            sar_taxtotal = ET.SubElement(invoice, "cac:TaxTotal")
            sar_taxamount = ET.SubElement(sar_taxtotal, "cbc:TaxAmount")
            sar_taxamount.set("currencyID", "SAR")
            sar_taxamount.text = str(tax_amount)

        # General Tax Total
        taxtotal = ET.SubElement(invoice, "cac:TaxTotal")
        taxamount = ET.SubElement(taxtotal, "cbc:TaxAmount")
        taxamount.set("currencyID", sales_invoice_doc.currency)
        taxamount.text = str(tax_amount)

        # Tax Subtotal
        tax_subtotal = ET.SubElement(taxtotal, "cac:TaxSubtotal")
        taxable_amt_elem = ET.SubElement(tax_subtotal, "cbc:TaxableAmount")
        taxable_amt_elem.set("currencyID", sales_invoice_doc.currency)
        taxable_amt_elem.text = str(abs(round(taxable_amount, 2)))

        subtotal_tax_amt = ET.SubElement(tax_subtotal, "cbc:TaxAmount")
        subtotal_tax_amt.set("currencyID", sales_invoice_doc.currency)
        subtotal_tax_amt.text = str(tax_amount)

        # Tax Category
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

        # Legal Monetary Total
        legal_total = ET.SubElement(invoice, "cac:LegalMonetaryTotal")

        line_ext_amt = ET.SubElement(legal_total, "cbc:LineExtensionAmount")
        line_ext_amt.set("currencyID", sales_invoice_doc.currency)
        line_ext_amt.text = str(round(
            abs(sales_invoice_doc.total if sales_invoice_doc.taxes[0].included_in_print_rate == 0 else sales_invoice_doc.base_net_total),
            2
        ))

        tax_exclusive = ET.SubElement(legal_total, "cbc:TaxExclusiveAmount")
        tax_exclusive.set("currencyID", sales_invoice_doc.currency)
        tax_exclusive.text = str(abs(round(taxable_amount, 2)))

        tax_inclusive = ET.SubElement(legal_total, "cbc:TaxInclusiveAmount")
        tax_inclusive.set("currencyID", sales_invoice_doc.currency)
        tax_inclusive.text = str(round(taxable_amount + tax_amount, 2))

        allowance = ET.SubElement(legal_total, "cbc:AllowanceTotalAmount")
        allowance.set("currencyID", sales_invoice_doc.currency)
        allowance.text = str(abs(sales_invoice_doc.get("discount_amount", 0.0)))

        total_amount = taxable_amount + tax_amount

        # Advance Adjustment
        if (
            "claudion4saudi" in frappe.get_installed_apps()
            and hasattr(sales_invoice_doc, "custom_advances_copy")
            and sales_invoice_doc.custom_advances_copy
            and sales_invoice_doc.custom_advances_copy[0].reference_name
        ):
            advance_amount = sum(
                advance.advance_amount for advance in sales_invoice_doc.custom_advances_copy
            )
            prepaid = ET.SubElement(legal_total, "cbc:PrepaidAmount")
            prepaid.set("currencyID", sales_invoice_doc.currency)
            prepaid.text = str(advance_amount)
            total_amount -= advance_amount

        payable = ET.SubElement(legal_total, "cbc:PayableAmount")
        payable.set("currencyID", sales_invoice_doc.currency)
        payable.text = str(round(total_amount, 2))

        return invoice

    except Exception as e:
        frappe.throw(_("Data processing error in tax_data: {0}").format(str(e)))
        return None


def tax_data_with_template(invoice, sales_invoice_doc):
    """Generate ZATCA-compliant tax data using Sales Taxes and Charges Template"""
    try:
        tax_details = get_zatca_tax_category_details(sales_invoice_doc)

        # Calculate taxable amount
        if sales_invoice_doc.taxes[0].included_in_print_rate == 0:
            taxable_amount = Decimal(str(sales_invoice_doc.total - sales_invoice_doc.get("discount_amount", 0.0)))
        else:
            taxable_amount = Decimal(str(sales_invoice_doc.base_net_total - sales_invoice_doc.get("discount_amount", 0.0)))

        taxable_amount = taxable_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Calculate tax amount
        tax_amount = (taxable_amount * Decimal(str(tax_details["rate"])) / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Add TaxTotal (SAR)
        if sales_invoice_doc.currency == "SAR":
            sar_taxtotal = ET.SubElement(invoice, "cac:TaxTotal")
            sar_taxamount = ET.SubElement(sar_taxtotal, "cbc:TaxAmount")
            sar_taxamount.set("currencyID", "SAR")
            sar_taxamount.text = str(tax_amount)

        # Add General TaxTotal
        taxtotal = ET.SubElement(invoice, "cac:TaxTotal")
        taxamount = ET.SubElement(taxtotal, "cbc:TaxAmount")
        taxamount.set("currencyID", sales_invoice_doc.currency)
        taxamount.text = str(tax_amount)

        # Add TaxSubtotal
        tax_subtotal = ET.SubElement(taxtotal, "cac:TaxSubtotal")

        taxable_amt_elem = ET.SubElement(tax_subtotal, "cbc:TaxableAmount")
        taxable_amt_elem.set("currencyID", sales_invoice_doc.currency)
        taxable_amt_elem.text = str(taxable_amount)

        tax_amt_elem = ET.SubElement(tax_subtotal, "cbc:TaxAmount")
        tax_amt_elem.set("currencyID", sales_invoice_doc.currency)
        tax_amt_elem.text = str(tax_amount)

        # Add TaxCategory
        tax_category = ET.SubElement(tax_subtotal, "cac:TaxCategory")
        tax_id = ET.SubElement(tax_category, "cbc:ID")
        tax_id.text = tax_details["code"]

        tax_percent = ET.SubElement(tax_category, "cbc:Percent")
        tax_percent.text = f"{Decimal(str(tax_details['rate'])).quantize(Decimal('0.01'))}"

        if tax_details["category"] != "Standard Rate":
            exemption_code = ET.SubElement(tax_category, "cbc:TaxExemptionReasonCode")
            exemption_code.text = tax_details["exemption_reason_code"]

            exemption_text = ET.SubElement(tax_category, "cbc:TaxExemptionReason")
            exemption_text.text = tax_details["exemption_reason_text"]

        # Add TaxScheme
        tax_scheme = ET.SubElement(tax_category, "cac:TaxScheme")
        tax_scheme_id = ET.SubElement(tax_scheme, "cbc:ID")
        tax_scheme_id.text = "VAT"

        # Add LegalMonetaryTotal
        legal_total = ET.SubElement(invoice, "cac:LegalMonetaryTotal")

        line_ext_amt = ET.SubElement(legal_total, "cbc:LineExtensionAmount")
        line_ext_amt.set("currencyID", sales_invoice_doc.currency)
        base_amount = sales_invoice_doc.total if sales_invoice_doc.taxes[0].included_in_print_rate == 0 else sales_invoice_doc.base_net_total
        line_ext_amt.text = str(round(abs(base_amount), 2))

        tax_exclusive = ET.SubElement(legal_total, "cbc:TaxExclusiveAmount")
        tax_exclusive.set("currencyID", sales_invoice_doc.currency)
        tax_exclusive.text = str(taxable_amount)

        tax_inclusive = ET.SubElement(legal_total, "cbc:TaxInclusiveAmount")
        tax_inclusive.set("currencyID", sales_invoice_doc.currency)
        tax_inclusive.text = str((taxable_amount + tax_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

        allowance = ET.SubElement(legal_total, "cbc:AllowanceTotalAmount")
        allowance.set("currencyID", sales_invoice_doc.currency)
        allowance.text = str(abs(Decimal(str(sales_invoice_doc.get("discount_amount", 0.0)))))

        # Advance payments (optional)
        total_amount = taxable_amount + tax_amount
    
        # PayableAmount
        payable = ET.SubElement(legal_total, "cbc:PayableAmount")
        payable.set("currencyID", sales_invoice_doc.currency)
        payable.text = str(total_amount.quantize(Decimal("0.01")))

        return invoice

    except Exception as e:
        frappe.throw(_("Data processing error in tax_data_with_template: {0}").format(str(e)))
        return None
