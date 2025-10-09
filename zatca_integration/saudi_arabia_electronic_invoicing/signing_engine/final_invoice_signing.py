# ruff: noqa: E501
import base64

import frappe
from frappe import _

from zatca_integration.saudi_arabia_electronic_invoicing.signing_engine.generate_final_xml import (
    item_data,
    save_formatted_zatca_xml,
)
from zatca_integration.saudi_arabia_electronic_invoicing.signing_engine.generate_invoice_xml import (
    add_document_level_discount_with_tax,
    add_document_level_discount_with_tax_template,
    additional_reference,
    company_data,
    customer_data,
    delivery_and_payment_means,
    doc_reference,
    invoice_typecode_compliance,
    invoice_typecode_simplified,
    invoice_typecode_standard,
    salesinvoice_data,
    xml_tags,
)
from zatca_integration.saudi_arabia_electronic_invoicing.signing_engine.generate_tax_data import (
    build_zatca_tax_section,
)
from zatca_integration.saudi_arabia_electronic_invoicing.signing_engine.initial_invoice_signing import (
    canonicalize_xml,
    certificate_hash,
    digital_signature,
    extract_certificate_details,
    generate_signed_properties_hash,
    generate_tlv_xml,
    get_tlv_for_value,
    getinvoicehash,
    populate_the_ubl_extensions_output,
    removetags,
    signxml_modify,
    structuring_signedxml,
    update_qr_toxml,
)

REPORTED_XML = "%Reported xml file%"


def xml_base64_decode(signed_xmlfile_name):
    """xml base64 decode"""
    try:
        with open(signed_xmlfile_name, encoding="utf-8") as file:
            xml = file.read().lstrip()

            base64_encoded = base64.b64encode(xml.encode("utf-8"))
            base64_decoded = base64_encoded.decode("utf-8")
            return base64_decoded
    except (ValueError, TypeError, KeyError) as e:
        frappe.throw(_("xml decode base64" f"error: {str(e)}"))
        return None


def get_api_url(company_abbr, base_url):
    """There are many api susing in zatca which can be defined by a feild in settings"""
    try:
        company_doc = frappe.get_doc("Company", {"abbr": company_abbr})
        if company_doc.custom_select == "Sandbox":
            url = company_doc.custom_sandbox_url + base_url
        elif company_doc.custom_select == "Simulation":
            url = company_doc.custom_simulation_url + base_url
        else:
            url = company_doc.custom_production_url + base_url

        return url

    except (ValueError, TypeError, KeyError) as e:
        frappe.throw(_("get api url" f"error: {str(e)}"))
        return None


def get_reporting_status(result):
    """defining the reporting status"""
    try:
        reporting_status = result.text.strip()  # Strip any leading/trailing whitespace
        return reporting_status
    except (ValueError, TypeError, KeyError, frappe.ValidationError) as e:
        frappe.throw(_("error in reporting statu" f"error: {str(e)}"))
        return None


def error_log():
    """defining the error log"""
    try:
        frappe.log_error(
            title="ZATCA invoice call failed in clearance status",
            message=frappe.get_traceback(),
        )
    except (ValueError, TypeError, KeyError, frappe.ValidationError) as e:
        frappe.throw(_("error in error log" f"error: {str(e)}"))
        return None


def is_file_attached(file_url):
    """Check if a file is attached by verifying its existence in the database."""
    return file_url and frappe.db.exists("File", {"file_url": file_url})


@frappe.whitelist(allow_guest=False)
def process_invoice_for_zatca_submission(
    invoice_number,
    compliance_type="0",
    any_item_has_tax_template=False,
    is_zatca_test=0,
    compliance_csid=None,
):
    """zatca call which includes the function calling and validation reguarding the api and
    based on this the zATCA output and message is getting"""
    try:
        if not frappe.db.exists("Sales Invoice", invoice_number):
            frappe.throw(_("Invoice Number is NOT Valid: " + str(invoice_number)))
        invoice = xml_tags()

        invoice, uuid1, sales_invoice_doc = salesinvoice_data(invoice, invoice_number)

        customer_doc = frappe.get_doc("Customer", sales_invoice_doc.customer)
        if compliance_type == "0":
            if customer_doc.customer_type == "Individual":
                invoice = invoice_typecode_simplified(invoice, sales_invoice_doc)
            else:
                invoice = invoice_typecode_standard(invoice, sales_invoice_doc)
        else:
            invoice = invoice_typecode_compliance(invoice, compliance_type)

        invoice = doc_reference(invoice, sales_invoice_doc)
        # frappe.throw("Uko")
        invoice = additional_reference(invoice, sales_invoice_doc)

        invoice = company_data(invoice, sales_invoice_doc)
        invoice = customer_data(invoice, sales_invoice_doc)

        invoice = delivery_and_payment_means(
            invoice, sales_invoice_doc, sales_invoice_doc.is_return
        )
        # if sales_invoice_doc.custom_zatca_nominal_invoice == 1:
        #     invoice = add_nominal_discount_tax(invoice, sales_invoice_doc)

        if not any_item_has_tax_template:
            invoice = add_document_level_discount_with_tax(invoice, sales_invoice_doc)
        else:
            # Add document-level discount with tax template
            invoice = add_document_level_discount_with_tax_template(invoice, sales_invoice_doc)

        if not any_item_has_tax_template:
            invoice = build_zatca_tax_section(invoice, sales_invoice_doc)

        if not any_item_has_tax_template:
            invoice = item_data(invoice, sales_invoice_doc)

        save_formatted_zatca_xml(invoice)

        try:
            with open(
                frappe.local.site + "/private/files/zatca_invoice_final.xml",
                encoding="utf-8",
            ) as file:
                file_content = file.read()
        except FileNotFoundError:
            frappe.throw("XML file not found")

        tag_removed_xml = removetags(file_content)

        canonicalized_xml = canonicalize_xml(tag_removed_xml)

        hash1, encoded_hash = getinvoicehash(canonicalized_xml)

        encoded_signature = digital_signature(
            hash1, sales_invoice_doc, is_zatca_test=is_zatca_test, compliance_csid=compliance_csid
        )
        issuer_name, serial_number = extract_certificate_details(
            sales_invoice_doc, is_zatca_test=is_zatca_test, compliance_csid=compliance_csid
        )

        encoded_certificate_hash = certificate_hash(
            sales_invoice_doc, is_zatca_test=is_zatca_test, compliance_csid=compliance_csid
        )
        namespaces, signing_time = signxml_modify(
            sales_invoice_doc, is_zatca_test=is_zatca_test, compliance_csid=compliance_csid
        )
        signed_properties_base64 = generate_signed_properties_hash(
            signing_time, issuer_name, serial_number, encoded_certificate_hash
        )

        populate_the_ubl_extensions_output(
            encoded_signature,
            namespaces,
            signed_properties_base64,
            encoded_hash,
            sales_invoice_doc,
            is_zatca_test=is_zatca_test,
            compliance_csid=compliance_csid,
        )
        tlv_data = generate_tlv_xml(
            sales_invoice_doc, is_zatca_test=is_zatca_test, compliance_csid=compliance_csid
        )

        tagsbufsarray = []
        for tag_num, tag_value in tlv_data.items():
            tagsbufsarray.append(get_tlv_for_value(tag_num, tag_value))

        qrcodebuf = b"".join(tagsbufsarray)
        qrcodeb64 = base64.b64encode(qrcodebuf).decode("utf-8")
        update_qr_toxml(qrcodeb64)
        signed_xmlfile_name = structuring_signedxml()

        return signed_xmlfile_name, uuid1, encoded_hash

    except (ValueError, TypeError, KeyError, frappe.ValidationError) as e:
        frappe.log_error(
            title="ZATCA invoice call failed",
            message=f"{frappe.get_traceback()}\nError: {str(e)}",
        )
        raise
