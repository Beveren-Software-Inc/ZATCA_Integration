

from decimal import Decimal, ROUND_DOWN
import xml.etree.ElementTree as ET
from xml.dom import minidom
from frappe.utils.data import get_time
from decimal import Decimal, ROUND_HALF_UP
import frappe
from frappe import _

from frappe.utils import flt
from zatca_integration.saudi_arabia_electronic_invoicing.utils import get_zatca_tax_category_details, get_exemption_reason_map


ITEM_TAX_TEMPLATE = "Item Tax Template"
CAC_TAX_TOTAL = "cac:TaxTotal"
CBC_TAX_AMOUNT = "cbc:TaxAmount"
CAC_TAX_SUBTOTAL = "cac:TaxSubtotal"
CBC_TAXABLE_AMOUNT = "cbc:TaxableAmount"
ZERO_RATED = "Zero Rated"
OUTSIDE_SCOPE = "Services outside scope of tax / Not subject to VAT"


def tax_data_nominal(invoice, sales_invoice_doc):
    """Generate ZATCA-compliant tax data for nominal invoices."""
    try:

        tax_category_totals = {}
        total_line_extension = 0

        # === Compute line extension amount if tax is included ===
        included_in_rate = (
            sales_invoice_doc.taxes[0].included_in_print_rate
            if sales_invoice_doc.taxes and sales_invoice_doc.taxes[0].included_in_print_rate
            else 0
        )
        tax_rate = (
            sales_invoice_doc.taxes[0].rate
            if sales_invoice_doc.taxes and sales_invoice_doc.taxes[0].rate
            else 15
        )

        if included_in_rate:
            for item in sales_invoice_doc.items:
                line_extension_amount = abs(round(item.amount / (1 + tax_rate / 100), 2))
                total_line_extension += line_extension_amount
        else:
            total_line_extension = sales_invoice_doc.net_total

        discount_amount = flt(sales_invoice_doc.discount_amount or 0.0)
        taxable_base = total_line_extension

        if abs(discount_amount - total_line_extension) == 0.01:
            taxable_base = total_line_extension
        elif included_in_rate:
            taxable_base = flt(sales_invoice_doc.base_discount_amount or 0.0)

        # === Group by Tax Type from Tax Template ===
        for tax in sales_invoice_doc.taxes:
            if not tax.tax_template:
                continue

            template = frappe.get_doc("Sales Taxes and Charges Template", tax.tax_template)
            tax_type = template.custom_tax_type or "Standard Rate"
            reason = ""
            if tax_type == "Zero Rate":
                reason = template.custom_zero_rate_reason or "Zero Rated"
            elif tax_type == "Except Rate":
                reason = template.custom_except_rate_reason or "Exempted"

            if tax_type not in tax_category_totals:
                tax_category_totals[tax_type] = {
                    "taxable_amount": 0,
                    "tax_amount": 0,
                    "tax_rate": tax.rate or 15,
                    "exemption_reason_code": reason,
                }

            tax_category_totals[tax_type]["taxable_amount"] += flt(taxable_base)
            tax_category_totals[tax_type]["tax_amount"] += (
                flt(taxable_base) * flt(tax.rate) / 100
            )

        # === Tax Total (SAR required by ZATCA) ===
        cac_taxtotal_sar = ET.SubElement(invoice, CAC_TAX_TOTAL)
        cbc_taxamount_sar = ET.SubElement(cac_taxtotal_sar, CBC_TAX_AMOUNT)
        cbc_taxamount_sar.set("currencyID", "SAR")

        total_tax_amount_sar = sum(t["tax_amount"] for t in tax_category_totals.values())
        cbc_taxamount_sar.text = f"{abs(round(total_tax_amount_sar, 2)):.2f}"

        # === Tax Total (Invoice Currency) ===
        cac_taxtotal_currency = ET.SubElement(invoice, CAC_TAX_TOTAL)
        cbc_taxamount_cur = ET.SubElement(cac_taxtotal_currency, CBC_TAX_AMOUNT)
        cbc_taxamount_cur.set("currencyID", sales_invoice_doc.currency)
        cbc_taxamount_cur.text = f"{abs(round(total_tax_amount_sar, 2)):.2f}"

        # === Add Tax Subtotals ===
        for category, data in tax_category_totals.items():
            cac_taxsubtotal = ET.SubElement(cac_taxtotal_currency, CAC_TAX_SUBTOTAL)

            cbc_taxableamount = ET.SubElement(cac_taxsubtotal, CBC_TAXABLE_AMOUNT)
            cbc_taxableamount.set("currencyID", sales_invoice_doc.currency)
            cbc_taxableamount.text = f"{round(data['taxable_amount'], 2):.2f}"

            cbc_taxamount = ET.SubElement(cac_taxsubtotal, CBC_TAX_AMOUNT)
            cbc_taxamount.set("currencyID", sales_invoice_doc.currency)
            cbc_taxamount.text = f"{abs(round(data['tax_amount'], 2)):.2f}"

            cac_taxcategory = ET.SubElement(cac_taxsubtotal, "cac:TaxCategory")
            cbc_id = ET.SubElement(cac_taxcategory, "cbc:ID")

            if category == "Standard Rate":
                cbc_id.text = "S"
            elif category == "Zero Rate":
                cbc_id.text = "Z"
            elif category == "Except Rate":
                cbc_id.text = "E"
            else:
                cbc_id.text = "O"

            cbc_percent = ET.SubElement(cac_taxcategory, "cbc:Percent")
            cbc_percent.text = f"{data['tax_rate']:.2f}"

            if category != "Standard Rate":
                cbc_code = ET.SubElement(cac_taxcategory, "cbc:TaxExemptionReasonCode")
                cbc_code.text = data["exemption_reason_code"]

                cbc_reason = ET.SubElement(cac_taxcategory, "cbc:TaxExemptionReason")
                reason_map = get_exemption_reason_map()
                cbc_reason.text = reason_map.get(data["exemption_reason_code"], "Other")

            cac_taxscheme = ET.SubElement(cac_taxcategory, "cac:TaxScheme")
            cbc_taxscheme_id = ET.SubElement(cac_taxscheme, "cbc:ID")
            cbc_taxscheme_id.text = "VAT"

        # === Out-of-Scope Placeholder Subtotal ===
        cac_taxsubtotal_2 = ET.SubElement(cac_taxtotal_currency, CAC_TAX_SUBTOTAL)
        cbc_taxableamount_2 = ET.SubElement(cac_taxsubtotal_2, CBC_TAXABLE_AMOUNT)
        cbc_taxableamount_2.set("currencyID", "SAR")
        cbc_taxableamount_2.text = str(-round(taxable_base, 2))

        cbc_taxamount_3 = ET.SubElement(cac_taxsubtotal_2, CBC_TAX_AMOUNT)
        cbc_taxamount_3.set("currencyID", "SAR")
        cbc_taxamount_3.text = "0.00"

        cac_taxcategory_2 = ET.SubElement(cac_taxsubtotal_2, "cac:TaxCategory")
        cbc_id_9 = ET.SubElement(cac_taxcategory_2, "cbc:ID")
        cbc_id_9.text = "O"

        cbc_percent_2 = ET.SubElement(cac_taxcategory_2, "cbc:Percent")
        cbc_percent_2.text = "0.00"

        cbc_ex_code = ET.SubElement(cac_taxcategory_2, "cbc:TaxExemptionReasonCode")
        cbc_ex_code.text = "VATEX-SA-OOS"

        cbc_ex_reason = ET.SubElement(cac_taxcategory_2, "cbc:TaxExemptionReason")
        cbc_ex_reason.text = "Nominal Invoice"

        cac_taxscheme_2 = ET.SubElement(cac_taxcategory_2, "cac:TaxScheme")
        cbc_id_10 = ET.SubElement(cac_taxscheme_2, "cbc:ID")
        cbc_id_10.text = "VAT"

        # === Legal Monetary Total ===
        cac_legalmonetarytotal = ET.SubElement(invoice, "cac:LegalMonetaryTotal")

        cbc_lineextensionamount = ET.SubElement(
            cac_legalmonetarytotal, "cbc:LineExtensionAmount"
        )
        cbc_lineextensionamount.set("currencyID", sales_invoice_doc.currency)
        cbc_lineextensionamount.text = f"{round(taxable_base, 2):.2f}"

        cbc_taxexclusiveamount = ET.SubElement(
            cac_legalmonetarytotal, "cbc:TaxExclusiveAmount"
        )
        cbc_taxexclusiveamount.set("currencyID", sales_invoice_doc.currency)
        cbc_taxexclusiveamount.text = f"{round(taxable_base, 2):.2f}"

        cbc_taxinclusiveamount = ET.SubElement(
            cac_legalmonetarytotal, "cbc:TaxInclusiveAmount"
        )
        cbc_taxinclusiveamount.set("currencyID", sales_invoice_doc.currency)
        cbc_taxinclusiveamount.text = f"{abs(round(sales_invoice_doc.grand_total, 2)):.2f}"
        cbc_allowancetotalamount = ET.SubElement(
            cac_legalmonetarytotal, "cbc:AllowanceTotalAmount"
        )
        cbc_allowancetotalamount.set("currencyID", sales_invoice_doc.currency)
        cbc_allowancetotalamount.text = f"{round(discount_amount, 2):.2f}"

        cbc_payableamount = ET.SubElement(cac_legalmonetarytotal, "cbc:PayableAmount")
        cbc_payableamount.set("currencyID", sales_invoice_doc.currency)
        cbc_payableamount.text = f"{abs(round(sales_invoice_doc.grand_total, 2)):.2f}"

        return invoice

    except Exception as e:
        frappe.throw(_("Error in nominal tax data: {0}").format(e))
        return None

def add_line_item_discount(cac_price, single_item, sales_invoice_doc):
    """
    Adds a line item discount and related details to the XML structure.
    """
    try:
        cac_allowance_charge = ET.SubElement(cac_price, "cac:AllowanceCharge")

        cbc_charge_indicator = ET.SubElement(
            cac_allowance_charge, "cbc:ChargeIndicator"
        )
        cbc_charge_indicator.text = "false"  # Indicates a discount

        cbc_allowance_charge_reason_code = ET.SubElement(
            cac_allowance_charge, "cbc:AllowanceChargeReasonCode"
        )
        cbc_allowance_charge_reason_code.text = "95"

        cbc_allowance_charge_reason = ET.SubElement(
            cac_allowance_charge, "cbc:AllowanceChargeReason"
        )
        cbc_allowance_charge_reason.text = "Discount"

        cbc_amount = ET.SubElement(
            cac_allowance_charge, "cbc:Amount", currencyID=sales_invoice_doc.currency
        )
        cbc_amount.text = str(abs(single_item.discount_amount))

        cbc_base_amount = ET.SubElement(
            cac_allowance_charge,
            "cbc:BaseAmount",
            currencyID=sales_invoice_doc.currency,
        )
        cbc_base_amount.text = str(
            abs(single_item.rate) + abs(single_item.discount_amount)
        )

        return cac_price

    except (ValueError, KeyError, AttributeError) as error:
        frappe.throw(_(f"Error occurred while adding line item discount: {str(error)}"))
        return None


def item_data(invoice, sales_invoice_doc):
    """
    Create UBL-compliant item-level XML lines without using Item Tax Template.
    Uses `get_zatca_tax_category_details`.
    """
    try:
        tax_details = get_zatca_tax_category_details(sales_invoice_doc)
        rate = Decimal(str(tax_details["rate"]))
        code = tax_details["code"]

        for item in sales_invoice_doc.items:
            tax_rate = Decimal(str(sales_invoice_doc.taxes[0].rate))
            included = sales_invoice_doc.taxes[0].included_in_print_rate

            cac_invoiceline = ET.SubElement(invoice, "cac:InvoiceLine")

            # ID and Quantity
            ET.SubElement(cac_invoiceline, "cbc:ID").text = str(item.idx)
            invoiced_quantity = ET.SubElement(cac_invoiceline, "cbc:InvoicedQuantity")
            invoiced_quantity.set("unitCode", str(item.uom))
            invoiced_quantity.text = str(abs(item.qty))

            # Line Extension Amount
            line_ext_amt = ET.SubElement(cac_invoiceline, "cbc:LineExtensionAmount")
            line_ext_amt.set("currencyID", sales_invoice_doc.currency)
            if included:
                base = item.base_amount if sales_invoice_doc.currency == "SAR" else item.amount
                line_ext_amt.text = str(round(abs(base / (1 + float(tax_rate) / 100)), 2))
            else:
                base = item.base_amount if sales_invoice_doc.currency == "SAR" else item.amount
                line_ext_amt.text = str(abs(base))

            # Tax Total per Item
            cac_taxtotal = ET.SubElement(cac_invoiceline, "cac:TaxTotal")
            tax_amount_elem = ET.SubElement(cac_taxtotal, "cbc:TaxAmount")
            tax_amount_elem.set("currencyID", sales_invoice_doc.currency)

            item_base_amount = Decimal(str(item.base_amount))
            item_amount = Decimal(str(item.amount))

            if included:
                tax_amount = item_base_amount * tax_rate / (Decimal("100") + tax_rate)
            else:
                tax_amount = item_amount * tax_rate / Decimal("100")


            tax_amount_elem.text = str(abs(Decimal(tax_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)))

            # Optional Rounding Amount
            rounding = ET.SubElement(cac_taxtotal, "cbc:RoundingAmount")
            rounding.set("currencyID", sales_invoice_doc.currency)
            rounding.text = str(round(float(line_ext_amt.text) + float(tax_amount_elem.text), 2))

            # Item Info
            cac_item = ET.SubElement(cac_invoiceline, "cac:Item")
            name = ET.SubElement(cac_item, "cbc:Name")
            name.text = f"{item.item_code}:{item.item_name}"

            # Classified Tax Category
            classified = ET.SubElement(cac_item, "cac:ClassifiedTaxCategory")
            ET.SubElement(classified, "cbc:ID").text = code
            ET.SubElement(classified, "cbc:Percent").text = f"{float(tax_rate):.2f}"

            if tax_details["category"] != "Standard Rate":
                reason_code = ET.SubElement(classified, "cbc:TaxExemptionReasonCode")
                reason_code.text = tax_details["exemption_reason_code"] or ""
                reason_text = ET.SubElement(classified, "cbc:TaxExemptionReason")
                reason_text.text = tax_details["exemption_reason_text"] or ""

            tax_scheme = ET.SubElement(classified, "cac:TaxScheme")
            ET.SubElement(tax_scheme, "cbc:ID").text = "VAT"

            # Price
            cac_price = ET.SubElement(cac_invoiceline, "cac:Price")
            price_amt = ET.SubElement(cac_price, "cbc:PriceAmount")
            price_amt.set("currencyID", sales_invoice_doc.currency)

            # Handle price according to nominal flag and included_in_print_rate
            rate_to_use = item.rate
            if included:
                rate_to_use = item.rate / (1 + float(tax_rate) / 100)

            price_amt.text = str(round(abs(rate_to_use), 2))

            base_quantity = ET.SubElement(
                cac_price, "cbc:BaseQuantity", unitCode=str(item.uom)
            )
            base_quantity.text = "1"

        return invoice

    except Exception as e:
        frappe.throw(_("Error occurred in item data processing: {0}").format(str(e)))
        return None

# --- Helper Function ---
def get_tax_code(category):
    """get tax code"""
    return {"Standard": "S", "Exempted": "E", ZERO_RATED: "Z", OUTSIDE_SCOPE: "O"}.get(
        category, "S"
    )


def get_time_string(posting_time):
    """get time string"""
    try:
        return get_time(posting_time).strftime("%H:%M:%S")
    except:
        return "00:00:00"


def custom_round(value):
    """Rounding CCording to our need"""
    # Convert the value to a Decimal for accurate handling
    decimal_value = Decimal(str(value))

    # Check if the number has less than 3 decimal places
    if decimal_value.as_tuple().exponent >= -2:
        # If there are less than 3 decimal places, return the original value as float
        return float(decimal_value)

    # Extract the third decimal digit accurately
    third_digit = int((decimal_value * 1000) % 10)

    # Check if the third digit is strictly greater than 5
    if third_digit > 5:
        # Increment the rounded result by 0.01 to ensure rounding up
        return float(decimal_value.quantize(Decimal("0.01")))
    elif third_digit == 5:
        # If the third digit is exactly 5, ensure we round down as desired
        return float(decimal_value.quantize(Decimal("0.01"), rounding=ROUND_DOWN))
    else:
        # Otherwise, round normally to 2 decimal places using ROUND_DOWN
        return float(decimal_value.quantize(Decimal("0.01"), rounding=ROUND_DOWN))
   

def save_formatted_zatca_xml(invoice):
    """
    Xml structuring and final saving of the xml into private files
    """
    try:

        tree = ET.ElementTree(invoice)
        xml_file_path = frappe.local.site + "/private/files/xml_files.xml"
        # Save the XML tree to a file
        with open(xml_file_path, "wb") as file:
            tree.write(file, encoding="utf-8", xml_declaration=True)

        # Read the XML file and format it
        with open(xml_file_path, "r", encoding="utf-8") as file:
            xml_string = file.read()
        # Format the XML string to make it pretty
        xml_dom = minidom.parseString(xml_string)
        pretty_xml_string = xml_dom.toprettyxml(indent="  ")

        # Write the formatted XML to the final file
        final_xml_path = frappe.local.site + "/private/files/zatca_invoice_final.xml"

        with open(final_xml_path, "w", encoding="utf-8") as file:
            file.write(pretty_xml_string)

    except (FileNotFoundError, IOError):
        frappe.throw(
            _(
                "File operation error occurred while structuring the XML. "
                "Please contact your system administrator."
            )
        )

    except ET.ParseError:
        frappe.throw(
            _(
                "Error occurred in XML parsing or formatting. "
                "Please check the XML structure for errors. "
                "If the problem persists, contact your system administrator."
            )
        )
    except UnicodeDecodeError:
        frappe.throw(
            _(
                "Encoding error occurred while processing the XML file. "
                "Please contact your system administrator."
            )
        )
