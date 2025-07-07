"""
ZATCA E-Invoicing Integration for ERPNext
This module facilitates the generation, validation, and submission of
 ZATCA-compliant e-invoices for companies
using ERPNext. It supports compliance with the ZATCA requirements for Phase 2,
including the creation of UBL XML
invoices, signing, and submission to ZATCA servers for clearance and reporting.
"""

import os
import io
import base64
import json
import uuid
from frappe import _
import frappe
import requests
from pyqrcode import create as qr_create
from zatca_integration.saudi_arabia_electronic_invoicing.signing_engine.generate_invoice_xml import (
    xml_tags,
    salesinvoice_data,
    add_document_level_discount_with_tax_template,
    add_document_level_discount_with_tax,
    company_data,
    customer_data,
    get_address,
    invoice_typecode_compliance,
    add_nominal_discount_tax,
    doc_reference_compliance,
    doc_reference,
    additional_reference,
    delivery_and_payment_means,
    delivery_and_payment_means_for_compliance,
    invoice_typecode_simplified,
    invoice_typecode_standard,
)
from zatca_integration.saudi_arabia_electronic_invoicing.signing_engine.generate_tax_data import tax_data, tax_data_with_template
from zatca_integration.saudi_arabia_electronic_invoicing.signing_engine.generate_final_xml import (
    tax_data_nominal,
    tax_data_with_template_nominal,
    item_data,
    item_data_with_template,
    xml_structuring,
)
from zatca_integration.saudi_arabia_electronic_invoicing.signing_engine.initial_invoice_signing import (
    removetags,
    canonicalize_xml,
    getinvoicehash,
    digital_signature,
    extract_certificate_details,
    certificate_hash,
    signxml_modify,
    generate_signed_properties_hash,
    populate_the_ubl_extensions_output,
    generate_tlv_xml,
    structuring_signedxml,
    get_tlv_for_value,
    update_qr_toxml,
    compliance_api_call,
)

REPORTED_XML = "%Reported xml file%"


def xml_base64_decode(signed_xmlfile_name):
    """xml base64 decode"""
    try:
        with open(signed_xmlfile_name, "r", encoding="utf-8") as file:
            xml = file.read().lstrip()
            base64_encoded = base64.b64encode(xml.encode("utf-8"))
            base64_decoded = base64_encoded.decode("utf-8")
            return base64_decoded
    except (ValueError, TypeError, KeyError) as e:
        frappe.throw(_(("xml decode base64" f"error: {str(e)}")))
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
        frappe.throw(_(("get api url" f"error: {str(e)}")))
        return None


def get_reporting_status(result):
    """defining the reporting status"""
    try:
        reporting_status = result.text.strip()  # Strip any leading/trailing whitespace
        print("reportingStatus: " + reporting_status)
        return reporting_status
    except (ValueError, TypeError, KeyError, frappe.ValidationError) as e:
        frappe.throw(_(("error in reporting statu" f"error: {str(e)}")))
        return None


def success_log(response, uuid1, invoice_number):
    """defining the success log"""
    try:
        current_time = frappe.utils.now()
        #TODO: Update Zatca Transaction doctype
    except (ValueError, TypeError, KeyError, frappe.ValidationError) as e:
        frappe.throw(_(("error in success log" f"error: {str(e)}")))
        return None


def error_log():
    """defining the error log"""
    try:
        frappe.log_error(
            title="ZATCA invoice call failed in clearance status",
            message=frappe.get_traceback(),
        )
    except (ValueError, TypeError, KeyError, frappe.ValidationError) as e:
        frappe.throw(_(("error in error log" f"error: {str(e)}")))
        return None


def is_file_attached(file_url):
    """Check if a file is attached by verifying its existence in the database."""
    return file_url and frappe.db.exists("File", {"file_url": file_url})


def is_qr_and_xml_attached(sales_invoice_doc):
    """Check if both QR code and XML file are already"""

    # Get the QR Code field value
    qr_code = sales_invoice_doc.get("ksa_einv_qr")

    # Get the XML file if attached
    xml_file = frappe.db.get_value(
        "File",
        {
            "attached_to_doctype": sales_invoice_doc.doctype,
            "attached_to_name": sales_invoice_doc.name,
            "file_name": ["like", REPORTED_XML],
        },
        "file_url",
    )

    # Ensure both files exist before confirming attachment
    return is_file_attached(qr_code) and is_file_attached(xml_file)


@frappe.whitelist(allow_guest=False)
def zatca_call(
    invoice_number,
    compliance_type="0",
    any_item_has_tax_template=False
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
        
        invoice = doc_reference(invoice, sales_invoice_doc, invoice_number)
        invoice = additional_reference(invoice)
        invoice = company_data(invoice, sales_invoice_doc)
        invoice = customer_data(invoice, sales_invoice_doc)
        invoice = delivery_and_payment_means(
            invoice, sales_invoice_doc, sales_invoice_doc.is_return
        )

        if sales_invoice_doc.custom_zatca_nominal_invoice == 1:
            invoice = add_nominal_discount_tax(invoice, sales_invoice_doc)

        elif not any_item_has_tax_template:
            invoice = add_document_level_discount_with_tax(invoice, sales_invoice_doc)
        else:
            # Add document-level discount with tax template
            invoice = add_document_level_discount_with_tax_template(
                invoice, sales_invoice_doc
            )

        if sales_invoice_doc.custom_zatca_nominal_invoice == 1:
            if not any_item_has_tax_template:
                invoice = tax_data_nominal(invoice, sales_invoice_doc)
            else:
                invoice = tax_data_with_template_nominal(invoice, sales_invoice_doc)
        else:
            if not any_item_has_tax_template:
                invoice = tax_data(invoice, sales_invoice_doc)
            else:
                invoice = tax_data_with_template(invoice, sales_invoice_doc)
      
        if not any_item_has_tax_template:
            invoice = item_data(invoice, sales_invoice_doc)
        else:
            invoice = item_data_with_template(invoice, sales_invoice_doc)

        xml_structuring(invoice)
        
        try:
            with open(
                frappe.local.site + "/private/files/finalzatcaxml.xml",
                "r",
                encoding="utf-8",
            ) as file:
                file_content = file.read()
        except FileNotFoundError:
            frappe.throw("XML file not found")
        
        tag_removed_xml = removetags(file_content)
        
        canonicalized_xml = canonicalize_xml(tag_removed_xml)
        
        hash1, encoded_hash = getinvoicehash(canonicalized_xml)
        
        encoded_signature = digital_signature(hash1, sales_invoice_doc)
        issuer_name, serial_number = extract_certificate_details(sales_invoice_doc)
        
        encoded_certificate_hash = certificate_hash(sales_invoice_doc)
        namespaces, signing_time = signxml_modify(sales_invoice_doc)
        signed_properties_base64 = generate_signed_properties_hash(
            signing_time, issuer_name, serial_number, encoded_certificate_hash
        )
        populate_the_ubl_extensions_output(
            encoded_signature,
            namespaces,
            signed_properties_base64,
            encoded_hash,
           
        )
        tlv_data = generate_tlv_xml()

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


@frappe.whitelist(allow_guest=False)
def zatca_call_compliance(
    invoice_number,
    company_abbr,
    source_doc,
    compliance_type="0",
    any_item_has_tax_template=False,
):
    """zatca call compliance"""

    try:
        if source_doc:
            source_doc = frappe.get_doc(json.loads(source_doc))
        company_name = frappe.db.get_value("Company", {"abbr": company_abbr}, "name")

        if not company_name:
            frappe.throw(_(f"Company with abbreviation {company_abbr} not found."))

        company_doc = frappe.get_doc("Company", company_name)

        if company_doc.custom_validation_type == "Simplified Invoice":
            compliance_type = "1"
        elif company_doc.custom_validation_type == "Standard Invoice":
            compliance_type = "2"
        elif company_doc.custom_validation_type == "Simplified Credit Note":
            compliance_type = "3"
        elif company_doc.custom_validation_type == "Standard Credit Note":
            compliance_type = "4"
        elif company_doc.custom_validation_type == "Simplified Debit Note":
            compliance_type = "5"
        elif company_doc.custom_validation_type == "Standard Debit Note":
            compliance_type = "6"
        if not frappe.db.exists("Sales Invoice", invoice_number):
            frappe.throw(_("Invoice Number is NOT Valid: " + str(invoice_number)))
        invoice = xml_tags()
        invoice, uuid1, sales_invoice_doc = salesinvoice_data(invoice, invoice_number)
        any_item_has_tax_template = any(
            item.item_tax_template for item in sales_invoice_doc.items
        )
        if any_item_has_tax_template and not all(
            item.item_tax_template for item in sales_invoice_doc.items
        ):
            frappe.throw(
                _(
                    "If any one item has an Item Tax Template,"
                    " all items must have an Item Tax Template."
                )
            )
        invoice = invoice_typecode_compliance(invoice, compliance_type)
        invoice = doc_reference_compliance(
            invoice, sales_invoice_doc, invoice_number, compliance_type
        )
        invoice = additional_reference(invoice, company_abbr, sales_invoice_doc)
        invoice = company_data(invoice, sales_invoice_doc)
        invoice = customer_data(invoice, sales_invoice_doc)
        invoice = delivery_and_payment_means_for_compliance(
            invoice, sales_invoice_doc, compliance_type
        )

        if sales_invoice_doc.custom_zatca_nominal_invoice == 1:
            # Add document-level discount with tax
            invoice = add_nominal_discount_tax(invoice, sales_invoice_doc)
        elif not any_item_has_tax_template:
            invoice = add_document_level_discount_with_tax(invoice, sales_invoice_doc)
        else:
            # Add document-level discount with tax template
            invoice = add_document_level_discount_with_tax_template(
                invoice, sales_invoice_doc
            )
        if sales_invoice_doc.custom_zatca_nominal_invoice == 1:
            if not any_item_has_tax_template:
                invoice = tax_data_nominal(invoice, sales_invoice_doc)
            else:
                invoice = tax_data_with_template_nominal(invoice, sales_invoice_doc)
        else:
            if not any_item_has_tax_template:
                invoice = tax_data(invoice, sales_invoice_doc)
            else:
                invoice = tax_data_with_template(invoice, sales_invoice_doc)

        if not any_item_has_tax_template:
            invoice = item_data(invoice, sales_invoice_doc)

        else:
            item_data_with_template(invoice, sales_invoice_doc)
        # Generate and process the XML data
        xml_structuring(invoice)
        with open(
            frappe.local.site + "/private/files/finalzatcaxml.xml",
            "r",
            encoding="utf-8",
        ) as file:
            file_content = file.read()

        tag_removed_xml = removetags(file_content)
        canonicalized_xml = canonicalize_xml(tag_removed_xml)
        hash1, encoded_hash = getinvoicehash(canonicalized_xml)
        encoded_signature = digital_signature(hash1, sales_invoice_doc)
        issuer_name, serial_number = extract_certificate_details(
            sales_invoice_doc
        )
        encoded_certificate_hash = certificate_hash(sales_invoice_doc)
        namespaces, signing_time = signxml_modify(sales_invoice_doc)
        signed_properties_base64 = generate_signed_properties_hash(
            signing_time, issuer_name, serial_number, encoded_certificate_hash
        )
        populate_the_ubl_extensions_output(
            encoded_signature,
            namespaces,
            signed_properties_base64,
            encoded_hash,
        )
        # Generate the TLV data and QR code
        tlv_data = generate_tlv_xml(company_abbr, source_doc)
        tagsbufsarray = []
        for tag_num, tag_value in tlv_data.items():
            tagsbufsarray.append(get_tlv_for_value(tag_num, tag_value))

        qrcodebuf = b"".join(tagsbufsarray)
        qrcodeb64 = base64.b64encode(qrcodebuf).decode("utf-8")

        update_qr_toxml(qrcodeb64)
        signed_xmlfile_name = structuring_signedxml()
        value = compliance_api_call(
            uuid1, encoded_hash, signed_xmlfile_name, company_abbr, source_doc
        )
        return value

    except (ValueError, TypeError, KeyError, frappe.ValidationError) as e:
        frappe.log_error(
            title="ZATCA invoice call failed", message=frappe.get_traceback()
        )
        frappe.throw(_("Error in ZATCA invoice call: " + str(e)))
        return None

