# Copyright (c) 2023, Shakir PM and contributors
# For license information, please see license.txt

import base64
import json
import struct
import time
import uuid
from datetime import timedelta

import frappe
import qrcode
import requests
from frappe.model.document import Document
from requests.auth import HTTPBasicAuth

from zatca_integration.common_util import generate_invoice_hash, generate_invoice_payload_from_xml
from zatca_integration.saudi_arabia_electronic_invoicing.data.test_data import (
    create_return_invoice,
    create_standard_return_invoice,
    create_standard_test_debit_sales_invoice,
    create_standard_test_sales_invoice,
    create_test_sales_invoice,
    create_test_simplified_debit_sales_invoice,
)
from zatca_integration.saudi_arabia_electronic_invoicing.utils import (
    build_certificate_data,
    calculation_expiry_date,
    create_public_key,
    delete_zatca_test_invoices_and_related_docs,
)


class ComplianceCSID(Document):
    def before_save(self):
        csr_settings = frappe.get_doc("Zatca CSR Settings", self.csr_settings)
        if csr_settings.csr == "" or csr_settings.csr is None:
            frappe.throw("CSR is not generated. Please generate CSR")

    @frappe.whitelist()
    def genereate_zatca_compliance_csid(self):
        csr_settings = frappe.get_doc("Zatca CSR Settings", self.csr_settings)
        zatca_environment = frappe.get_doc("Zatca Environment", csr_settings.zatca_environment)

        headers = {
            "accept": "application/json",
            "OTP": self.otp,
            "Accept-Version": "V2",
            "Content-Type": "application/json",
        }
        data = {"csr": csr_settings.csr}

        try:
            response = requests.post(
                zatca_environment.compliance_csid_api, headers=headers, json=data
            )
            response.raise_for_status()
            response_json = response.json()

            self.created_time = frappe.utils.now_datetime()
            self.request_id = response_json.get("requestID", "")
            self.disposition_message = response_json.get("dispositionMessage", "")
            self.binary_security_token = response_json.get("binarySecurityToken", "")
            self.secret = response_json.get("secret", "")
            self.errors = response_json.get("errors", "{}")
            self.certificate = build_certificate_data(response_json.get("binarySecurityToken", ""))
            self.public_key = create_public_key(self.certificate)
            self.reset_compliance_csid_status(False)
            self.save()

        except requests.exceptions.RequestException as req_err:
            self.handle_error(response, f"An error occurred: {req_err}")
        except ValueError as json_err:
            self.handle_error(response, f"JSON parsing error: {json_err}")

    def handle_error(self, response, error_message):
        """Handle errors by logging and raising an exception."""
        error_details = [error_message]

        if response is not None:
            error_details.append(
                f"Response Text: {response.text if response.text else 'No response text'}"
            )

        self.errors = "\n".join(error_details)
        self.save()
        frappe.db.commit()

        frappe.throw(f"Error in generating ZATCA Compliance CSID: {error_message}")

    @frappe.whitelist()
    def validate_zatca_compliance_csid(self, invoice):
        """Validate ZATCA Compliance CSID."""
        if not self.binary_security_token:
            frappe.throw(
                "Binary Security Token is not generated. Please Generate ZATCA Compliance CSID"
            )

        csr_settings = frappe.get_doc("Zatca CSR Settings", self.csr_settings)
        seller = get_seller_information(csr_settings)
        buyer = get_buyer_information()

        if csr_settings.csrinvoicetype == "1100":
            if self._is_standard_validation_pending():
                self.invoke_complaince_check("standard", csr_settings, seller, buyer)

            if self._is_simplified_validation_pending():
                self.invoke_complaince_check("simplified", csr_settings, seller, buyer)

            if not (
                self.standard_invoice
                and self.standard_credit_note
                and self.standard_debit_note
                and self.simplified_invoice
                and self.simplified_credit_note
                and self.simplified_debit_note
            ):
                self.save()
                frappe.db.commit()
                frappe.throw(
                    "Failed to Validate Compliance CSID, Review CSID TRANSACTIONS for more details"
                )
            failed = []

            if not self.standard_invoice:
                failed.append("Standard Invoice")
            if not self.standard_credit_note:
                failed.append("Standard Credit Note")
            if not self.standard_debit_note:
                failed.append("Standard Debit Note")
            if not self.simplified_invoice:
                failed.append("Simplified Invoice")
            if not self.simplified_credit_note:
                failed.append("Simplified Credit Note")
            if not self.simplified_debit_note:
                failed.append("Simplified Debit Note")

            if failed:
                self.save()
                frappe.db.commit()
                frappe.throw(
                    f"Failed to Validate Compliance CSID for: {', '.join(failed)}. "
                    "Review CSID TRANSACTIONS for more details."
                )
        elif csr_settings.csrinvoicetype == "1000":
            if self._is_standard_validation_pending():
                self.invoke_complaince_check("standard", csr_settings, seller, buyer)
            if not (
                self.standard_invoice and self.standard_credit_note and self.standard_debit_note
            ):
                self.save()
                frappe.db.commit()
                frappe.throw(
                    "Failed to Validate Compliance CSID, Review CSID TRANSACTIONS for more details"
                )
        elif csr_settings.csrinvoicetype == "0100":
            if self._is_simplified_validation_pending():
                self.invoke_complaince_check("simplified", csr_settings, seller, buyer)
            if not (self.simplified_invoice):
                frappe.db.commit()
                frappe.throw(
                    "Failed to Validate Compliance CSID, Review CSID TRANSACTIONS for more details"
                )
        else:
            frappe.throw(
                "Invalid Invoice Type in ZATCA CSR Settings : " + csr_settings.csrinvoicetype
            )

        self.save()
        delete_zatca_test_invoices_and_related_docs()

    def set_invoice_status(self, invoice_type, status, note_type):
        """Set the status of the invoice or note."""
        if invoice_type == "standard":
            if note_type == "invoice":
                self.standard_invoice = status
            elif note_type == "credit_note":
                self.standard_credit_note = status
            elif note_type == "debit_note":
                self.standard_debit_note = status
        elif invoice_type == "simplified":
            if note_type == "invoice":
                self.simplified_invoice = status
            elif note_type == "credit_note":
                self.simplified_credit_note = status
            elif note_type == "debit_note":
                self.simplified_debit_note = status

    def invoke_complaince_check(self, invoice_type, csr_settings, seller, buyer):
        """Invoke compliance check for the given invoice type."""
        """Dynamically generate first invoice hash to ensure unique hash for each run."""
        first_invoice_hash = generate_invoice_hash()
        compliance_name = str(self.name)

        # Issue Invoice
        tax_invoice = generate_tax_invoice_xml(
            compliance_name,
            csr_settings,
            invoice_type,
            "INV-00001",
            seller,
            buyer,
            first_invoice_hash,
        )

        tax_invoice_status, tax_invoice_hash = self.invoke_compliance_invoice_api(
            invoice_type, csr_settings, tax_invoice["xml"]
        )
        if invoice_type == "standard":
            self.standard_invoice = tax_invoice_status
        if invoice_type == "simplified":
            self.simplified_invoice = tax_invoice_status

        # Issue Credit Note
        credit_note = generate_credit_note_xml(
            compliance_name,
            invoice_type,
            "INV-00002",
            seller,
            buyer,
            tax_invoice["invoiceNumber"],
            tax_invoice["invoiceDeliveryDate"],
            tax_invoice_hash,
        )
        credit_note_status, credit_note_hash = self.invoke_compliance_invoice_api(
            invoice_type, csr_settings, credit_note["xml"]
        )
        if invoice_type == "standard":
            self.standard_credit_note = credit_note_status
        elif invoice_type == "simplified":
            self.simplified_credit_note = credit_note_status

        # Issue Invoice
        tax_invoice = generate_tax_invoice_xml(
            compliance_name,
            csr_settings,
            invoice_type,
            "INV-00003",
            seller,
            buyer,
            credit_note_hash,
        )
        tax_invoice_status, tax_invoice_hash = self.invoke_compliance_invoice_api(
            invoice_type, csr_settings, tax_invoice["xml"]
        )

        # Issue Debit Note
        debit_note = generate_debit_note_xml(
            compliance_name,
            csr_settings,
            invoice_type,
            "INV-00004",
            seller,
            buyer,
            tax_invoice["invoiceNumber"],
            tax_invoice["invoiceDeliveryDate"],
            tax_invoice_hash,
        )
        debit_note_status, debit_note_hash = self.invoke_compliance_invoice_api(
            invoice_type, csr_settings, debit_note["xml"]
        )

        if invoice_type == "standard":
            self.standard_debit_note = debit_note_status
        elif invoice_type == "simplified":
            self.simplified_debit_note = debit_note_status

    def invoke_compliance_invoice_api(self, invoice_type, csr_settings, invoice_xml):
        """Invoke compliance invoice API."""
        zatca_environment = frappe.get_doc("Zatca Environment", csr_settings.zatca_environment)

        if invoice_type == "standard":
            invoice_request = generate_invoice_payload_from_xml(invoice_xml.encode("utf-8"))
        elif invoice_type == "simplified":
            invoice_request = generate_invoice_payload_from_xml(invoice_xml.encode("utf-8"))
        else:
            frappe.throw(f"Invalid Invoice Type: {invoice_type}")

        headers = {
            "accept": "application/json",
            "Accept-Language": "en",
            "Accept-Version": "V2",
            "Content-Type": "application/json",
        }
        response_json = None
        try:
            response = requests.post(
                zatca_environment.compliance_invoice_api,
                headers=headers,
                auth=HTTPBasicAuth(self.binary_security_token, self.secret),
                data=json.dumps(invoice_request),
            )
            response_code = response.status_code
            response_text = response.text
            response_headers = dict(response.headers)
            try:
                _response_json = response.json()
            except ValueError:
                _response_json = None
        except requests.exceptions.RequestException as e:
            response_code = None
            response_text = str(e)
            response_headers = {}
        # Save the request and response details
        transaction = frappe.get_doc(
            {
                "doctype": "CSID Transactions",
                "compliance_csid": self.name,
                "request_url": zatca_environment.compliance_invoice_api,
                "request_header": json.dumps(headers),
                "request_body": json.dumps(invoice_request),
                "response_code": response_code,
                "response_header": json.dumps(response_headers),
                "response_body": response_text,
                "transaction_time": frappe.utils.now_datetime(),
            }
        )
        transaction.insert()

        if response.status_code == 200 or response.status_code == 202:
            return True, invoice_request["invoiceHash"]
        if response.status_code == 406:
            frappe.log_error(
                title="ZATCA Compliance Invoice Already Submitted",
                message=f"Invoice with hash {invoice_request['invoiceHash']} was already submitted.",
            )
            # ZATCA returns 406 when the exact payload was already validated;
            # treat it as a success so downstream steps keep running.
            return True, invoice_request["invoiceHash"]
        return False, None

    def _is_compliance_already_completed(self, response_json):
        """Return True if ZATCA indicates the document was already submitted."""
        if not response_json:
            return False
        validation_results = response_json.get("validationResults", {})
        error_messages = validation_results.get("errorMessages", [])
        for error in error_messages:
            message = (error or {}).get("message", "")
            if isinstance(message, str) and "submitted before" in message.lower():
                return True
        return False

    def _is_standard_validation_pending(self):
        return not all(
            [
                self.standard_invoice,
                self.standard_credit_note,
                self.standard_debit_note,
            ]
        )

    def _is_simplified_validation_pending(self):
        return not all(
            [
                self.simplified_invoice,
                self.simplified_credit_note,
                self.simplified_debit_note,
            ]
        )

    def reset_compliance_csid_status(self, status):
        """Reset the compliance CSID status."""
        self.standard_invoice = status
        self.standard_debit_note = status
        self.standard_credit_note = status
        self.simplified_invoice = status
        self.simplified_debit_note = status
        self.simplified_credit_note = status

    def decode_certificate(self, compliance_certificate):
        """Decode the compliance certificate from base64."""
        decoded_compliance_certificate = base64.b64decode(compliance_certificate.encode("utf-8"))
        return decoded_compliance_certificate.decode("utf-8")

    def _prepare_renewal_request(self):
        """Prepare renewal request data, headers, and get required documents."""
        if not self.production_csid:
            frappe.throw(
                "Please select the Production CSID you want to renew in the production_csid field."
            )

        production_csid = frappe.get_doc("Production CSID", self.production_csid)
        zatca_settings = frappe.get_doc("Zatca CSR Settings", self.csr_settings)
        zatca_environment = frappe.get_doc("Zatca Environment", zatca_settings.zatca_environment)

        # ZATCA renewal requires:
        # 1. NEW CSR in the request body
        # 2. Renewal OTP in the header
        # 3. PCSID credentials for authorization
        # Reference: https://zatca1.discourse.group/t/how-to-renew-expired-pcsid/524
        data = {"csr": zatca_settings.csr}
        headers = {
            "accept": "application/json",
            "OTP": self.otp,  # Renewal OTP from Fatoora portal
            "Accept-Version": "V2",
            "Content-Type": "application/json",
        }

        return production_csid, zatca_environment, data, headers

    def _handle_renewal_success_200(self, production_csid, response_json):
        """Handle 200 response - Production CSID directly renewed and ready to use."""
        disposition_message = response_json.get("dispositionMessage", "")

        # Update Production CSID with new credentials
        production_csid.created_time = frappe.utils.now_datetime()
        production_csid.expiry_date = calculation_expiry_date(production_csid.created_time)
        production_csid.request_id = response_json.get("requestID", "")
        production_csid.disposition_message = disposition_message
        production_csid.binary_security_token = response_json.get("binarySecurityToken", "")
        production_csid.token_type = response_json.get("tokenType", "")
        production_csid.secret = response_json.get("secret", "")
        production_csid.errors = response_json.get("errors", "{}")
        production_csid.certificate = build_certificate_data(production_csid.binary_security_token)
        production_csid.public_key = create_public_key(production_csid.certificate)
        production_csid.save()

        # Mark production_csid_success as passed
        self.production_csid_success = 1
        self.save()

        message = (
            "Renewal successful! The Production CSID has been updated with new credentials.<br><br>"
            "<b>Status:</b> " + disposition_message + "<br><br>"
            "You can now use the renewed Production CSID for invoice clearance and reporting."
        )
        frappe.msgprint(message, indicator="green", title="Production CSID Renewed Successfully")
        return "Production CSID renewed successfully"

    def _handle_renewal_success_428(self, response_json):
        if "value" in response_json:
            response_data = response_json.get("value", {})
        else:
            response_data = response_json

        disposition_message = response_data.get("dispositionMessage", "")

        if disposition_message != "NOT_COMPLIANT":
            # 428 but not NOT_COMPLIANT - treat as error
            error_text = f"Status 428: {disposition_message}"
            self._save_and_throw_error(error_text, "ZATCA Renewal Failed")

        # Update Compliance CSID with new credentials
        self.created_time = frappe.utils.now_datetime()
        self.request_id = response_data.get("requestID", "")
        self.disposition_message = disposition_message
        self.binary_security_token = response_data.get("binarySecurityToken", "")
        self.token_type = response_data.get("tokenType", "")
        self.secret = response_data.get("secret", "")
        self.errors = response_data.get("errors", "{}")
        self.certificate = build_certificate_data(self.binary_security_token)
        self.public_key = create_public_key(self.certificate)
        self.save()

        message = (
            "Renewal successful! The Compliance CSID has been updated with new credentials.<br><br>"
            "<b>Status:</b> NOT_COMPLIANT<br><br>"
            "<b>Next Steps:</b><br>"
            "1. Complete compliance checks for invoices<br>"
            "2. Generate a new Production CSID from the renewed Compliance CSID<br>"
            "3. Use the new Production CSID for clearance/reporting APIs"
        )
        frappe.msgprint(
            message, indicator="orange", title="Renewal Successful - Compliance Required"
        )
        return "Renewal successful - Compliance checks required"

    def _parse_error_response(self, response):
        """Parse error response and return formatted error text."""
        error_text = response.text if response.text else f"Status {response.status_code}"

        try:
            error_data = response.json()
            # Handle errors array format
            if "errors" in error_data and isinstance(error_data["errors"], list):
                error_messages = []
                for err in error_data["errors"]:
                    code = err.get("code", "")
                    msg = err.get("message", "")
                    error_messages.append(f"{code}: {msg}")
                error_text = "<br>".join(
                    [f"• {frappe.utils.escape_html(msg)}" for msg in error_messages]
                )
            else:
                error_code = error_data.get("code", "")
                error_message = error_data.get("message", "")
                if error_code or error_message:
                    error_text = f"{error_code}: {error_message}" if error_code else error_message
                else:
                    error_text = json.dumps(error_data, indent=2)
        except (ValueError, json.JSONDecodeError):
            pass

        return error_text

    def _save_and_throw_error(self, error_text, title="ZATCA Renewal Failed"):
        """Save error to document and throw exception."""
        self.errors = error_text
        self.save()
        frappe.db.commit()
        frappe.throw(frappe.utils.escape_html(error_text), title=title)

    @frappe.whitelist()
    def renew_zatca_production_csid(self):
        # Mania: I have attached the reference just incase the
        # next developer will need clarification
        """
        Renews the ZATCA Production CSID using PATCH request.
        According to ZATCA docs (https://zatca1.discourse.group/t/how-to-renew-expired-pcsid/524),
        renewal requires a NEW CSR in the request body.
        Handles both 200 (success) and 428 (NOT_COMPLIANT - renewal successful
        but needs compliance checks) responses.
        """
        production_csid, zatca_environment, data, headers = self._prepare_renewal_request()

        try:
            # For renewal, use Production CSID credentials (the one being renewed)
            # Reference: https://zatca1.discourse.group/t/renew-csid-401-unauthorized-error/3034
            response = requests.patch(
                url=zatca_environment.production_csid_api,
                headers=headers,
                auth=HTTPBasicAuth(production_csid.binary_security_token, production_csid.secret),
                json=data,
            )

            # Handle both 200 (ISSUED - Production CSID directly updated) and
            # 428 (NOT_COMPLIANT - new Compliance CSID)
            # Reference: https://zatca1.discourse.group/t/how-to-renew-expired-pcsid/524/8
            if response.status_code == 200:
                response_json = response.json()
                return self._handle_renewal_success_200(production_csid, response_json)

            elif response.status_code == 428:
                try:
                    response_json = response.json()
                    return self._handle_renewal_success_428(response_json)
                except (ValueError, json.JSONDecodeError):
                    error_text = (
                        response.text if response.text else f"Status {response.status_code}"
                    )
                    self._save_and_throw_error(error_text, "ZATCA Renewal Failed")
            else:
                # Handle other error responses
                error_text = self._parse_error_response(response)
                self._save_and_throw_error(error_text, "ZATCA Renewal Failed")

        except requests.exceptions.RequestException as req_err:
            error_msg = str(req_err)
            if "response" in locals() and response:
                error_msg += f"\n\nResponse: {response.text}"
            self._save_and_throw_error(error_msg, "ZATCA Renewal Request Error")
        except Exception as e:
            self._save_and_throw_error(str(e), "ZATCA Renewal Error")


def generate_debit_note_xml(
    compliance_name,
    csr_settings,
    invoiceType,
    invoiceNumber,
    seller,
    buyer,
    originalinvoiceNumber,
    originalinvoiceDeliveryDate,
    previousInvoiceHash,
):
    # Global Unique Identifier
    uniqueInvoiceIdentifier = str(uuid.uuid4())
    invoiceCounterValue = int(time.time())

    # Invoice Date and Time
    # Removed unused invoice_date and invoice_time variables

    # if invoiceType == "standard":
    if invoiceType == "standard":
        invoice_name = create_standard_test_debit_sales_invoice(csr_settings, compliance_name)
    elif invoiceType == "simplified":
        invoice_name = create_test_simplified_debit_sales_invoice(csr_settings, compliance_name)

    standard_debit_note_xml = render_template(invoice_name)

    standard_debit_note = {
        "invoiceNumber": invoiceNumber,
        "uniqueInvoiceIdentifier": uniqueInvoiceIdentifier,
        "invoiceCounterValue": invoiceCounterValue,
        "invoiceDeliveryDate": originalinvoiceDeliveryDate,
        "xml": standard_debit_note_xml,
    }
    return standard_debit_note


def generate_credit_note_xml(
    compliance_name,
    invoiceType,
    invoiceNumber,
    seller,
    buyer,
    originalinvoiceNumber,
    originalinvoiceDeliveryDate,
    previousInvoiceHash,
):
    # Global Unique Identifier
    uniqueInvoiceIdentifier = str(uuid.uuid4())
    # Counter Value, once used cannot be used even for same invoice
    invoiceCounterValue = int(time.time())

    # Invoice Date and Time
    # Removed unused invoice_date and invoice_time variables

    if invoiceType == "standard":
        invoice_name = create_standard_return_invoice(compliance_name)
    elif invoiceType == "simplified":
        invoice_name = create_return_invoice(compliance_name)

    standard_credit_note_xml = render_template(invoice_name)

    standard_credit_note = {
        "invoiceNumber": invoiceNumber,
        "uniqueInvoiceIdentifier": uniqueInvoiceIdentifier,
        "invoiceCounterValue": invoiceCounterValue,
        "invoiceDeliveryDate": originalinvoiceDeliveryDate,
        "xml": standard_credit_note_xml,
    }
    return standard_credit_note


def generate_tax_invoice_xml(
    compliance_name, csr_settings, invoiceType, invoiceNumber, seller, buyer, previousInvoiceHash
):
    # Global Unique Identifier
    uniqueInvoiceIdentifier = str(uuid.uuid4())
    # Counter Value, once used cannot be used even for same invoice
    invoiceCounterValue = int(time.time())

    # Invoice Date and Time
    # Removed unused invoice_date and invoice_time variables

    # Invoice Delivery Date
    invoiceDeliveryDate = (
        frappe.utils.getdate(frappe.utils.today()) + timedelta(days=10)
    ).strftime("%Y-%m-%d")
    if invoiceType == "standard":
        invoice_name = create_standard_test_sales_invoice(csr_settings, compliance_name)
    elif invoiceType == "simplified":
        invoice_name = create_test_sales_invoice(csr_settings, compliance_name)

    standard_invoice_xml = render_template(invoice_name)
    standard_invoice = {
        "invoiceNumber": invoiceNumber,
        "uniqueInvoiceIdentifier": uniqueInvoiceIdentifier,
        "invoiceCounterValue": invoiceCounterValue,
        "invoiceDeliveryDate": invoiceDeliveryDate,
        "xml": standard_invoice_xml,
    }
    return standard_invoice


def render_template(invoice_name):
    file_url = frappe.get_doc("Sales Invoice", invoice_name).custom_invoice_xml

    file_doc = frappe.get_doc("File", {"file_url": file_url})

    file_path = frappe.get_site_path("public", file_doc.file_url.lstrip("/"))

    with open(file_path, encoding="utf-8") as f:
        xml_template = f.read()

    return xml_template


def get_buyer_information():
    return {
        "organizationName": "Panda Retail Company",
        "vatNumber": "300056521610003",
        "streetName": "Taha Khasiyfan",
        "buildingNumber": "2444",
        "citySubdivisionName": "Ash Shati",
        "cityName": "Jeddah",
        "postalZone": "23511",
        "countryCode": "SA",
    }


def get_seller_information(csr_settings):
    return {
        "organizationName": csr_settings.csrorganizationname,
        "vatNumber": csr_settings.csrorganizationidentifier,
        "streetName": csr_settings.street_name,
        "buildingNumber": csr_settings.building_number,
        "citySubdivisionName": csr_settings.city_subdivision_name,
        "cityName": csr_settings.city_name,
        "postalZone": csr_settings.postal_zone,
        "countryCode": csr_settings.csrcountryname,
        "registrationNumber": csr_settings.registration_number,
        "registrationScheme": get_registration_scheme_code(csr_settings.registration_scheme),
        "registration_scheme": csr_settings.registration_scheme,
    }


def get_registration_scheme_code(registration_scheme):
    # Find the start and end indices of the parentheses
    start = registration_scheme.find("(")
    end = registration_scheme.find(")")

    # Extract and return the text inside the parentheses
    if start != -1 and end != -1:
        return registration_scheme[start + 1 : end]
    else:
        frappe.throw("Invalid Registration Scheme")


def create_tlv_data(tag, value):
    """Create TLV (Tag-Length-Value) data for ZATCA QR code"""
    value_bytes = value.encode("utf-8")
    length = len(value_bytes)
    return struct.pack("B", tag) + struct.pack("B", length) + value_bytes


def generate_zatca_qr_data(seller_name, vat_number, timestamp, total_amount, vat_amount):
    """Generate ZATCA QR code data in TLV format"""
    TAG_SELLER_NAME = 1
    TAG_VAT_NUMBER = 2
    TAG_TIMESTAMP = 3
    TAG_TOTAL_AMOUNT = 4
    TAG_VAT_AMOUNT = 5

    # Create TLV data for each field
    tlv_data = b""
    tlv_data += create_tlv_data(TAG_SELLER_NAME, seller_name)
    tlv_data += create_tlv_data(TAG_VAT_NUMBER, vat_number)
    tlv_data += create_tlv_data(TAG_TIMESTAMP, timestamp)
    tlv_data += create_tlv_data(TAG_TOTAL_AMOUNT, total_amount)
    tlv_data += create_tlv_data(TAG_VAT_AMOUNT, vat_amount)

    # Encode to base64
    return base64.b64encode(tlv_data).decode("utf-8")


def generate_qr_code(data, filename):
    """Generate QR code image"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    img.save(filename)
    return filename
