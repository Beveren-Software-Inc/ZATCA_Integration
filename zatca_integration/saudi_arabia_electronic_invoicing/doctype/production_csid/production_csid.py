# Copyright (c) 2023, Shakir PM and contributors
# For license information, please see license.txt
import base64
import json
from textwrap import wrap

import frappe
import requests
from frappe.model.document import Document
from requests.auth import HTTPBasicAuth

from zatca_integration.saudi_arabia_electronic_invoicing.utils import (
    build_certificate_data,
    calculation_expiry_date,
    create_public_key,
)


class ProductionCSID(Document):
    def before_save(self):
        compliance_csid = frappe.get_doc("Compliance CSID", self.compliance_csid)
        csr_settings = frappe.get_doc("Zatca CSR Settings", compliance_csid.csr_settings)

        if csr_settings.csrinvoicetype == "1100":
            if not (
                compliance_csid.standard_invoice
                and compliance_csid.standard_debit_note
                and compliance_csid.standard_credit_note
                and compliance_csid.simplified_invoice
                and compliance_csid.simplified_debit_note
                and compliance_csid.simplified_credit_note
            ):
                frappe.throw(
                    "All standard and simplified invoices, debit notes, and credit notes must be validated for type 1100."
                )
        elif csr_settings.csrinvoicetype == "1000":
            if not (
                compliance_csid.standard_invoice
                and compliance_csid.standard_debit_note
                and compliance_csid.standard_credit_note
            ):
                frappe.throw(
                    "All standard invoices, debit notes, and credit notes must be validated for type 1000."
                )
        elif csr_settings.csrinvoicetype == "0100":
            if not (
                compliance_csid.simplified_invoice
                and compliance_csid.simplified_debit_note
                and compliance_csid.simplified_credit_note
            ):
                frappe.throw(
                    "All simplified invoices, debit notes, and credit notes must be validated for type 0100."
                )
        else:
            frappe.throw(
                "Invalid Invoice Type in ZATCA CSR Settings: " + csr_settings.csrinvoicetype
            )

    @frappe.whitelist()
    def generate_zatca_production_csid(self):
        compliance_csid = frappe.get_doc("Compliance CSID", self.compliance_csid)
        zatca_settings = frappe.get_doc("Zatca CSR Settings", compliance_csid.csr_settings)
        zatca_environment = frappe.get_doc("Zatca Environment", zatca_settings.zatca_environment)

        headers = {
            "accept": "application/json",
            "Accept-Version": "V2",
            "Content-Type": "application/json",
        }
        data = {"compliance_request_id": compliance_csid.request_id}

        try:
            response = requests.post(
                zatca_environment.production_csid_api,
                headers=headers,
                auth=HTTPBasicAuth(compliance_csid.binary_security_token, compliance_csid.secret),
                json=data,
            )

            response.raise_for_status()
            response_json = response.json()
            # frappe.throw(str(response_json))
            self.is_active = True
            self.created_time = frappe.utils.now_datetime()
            self.expiry_date = calculation_expiry_date(self.created_time)
            self.request_id = response_json.get("requestID", "")
            self.disposition_message = response_json.get("dispositionMessage", "")
            self.binary_security_token = response_json.get("binarySecurityToken", "")
            self.token_type = response_json.get("tokenType", "")
            self.secret = response_json.get("secret", "")
            self.errors = response_json.get("errors", "{}")
            self.certificate = build_certificate_data(response_json.get("binarySecurityToken", ""))
            self.public_key = create_public_key(self.certificate)

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

        frappe.throw(f"Error in generating ZATCA Production CSID: {self.errors}")

    @frappe.whitelist()
    def renew_zatca_production_csid(self):
        """
        Renews the ZATCA Production CSID using PATCH request with given CSR and OTP.
        """
        compliance_csid = frappe.get_doc("Compliance CSID", self.compliance_csid)
        zatca_settings = frappe.get_doc("Zatca CSR Settings", compliance_csid.csr_settings)
        zatca_environment = frappe.get_doc("Zatca Environment", zatca_settings.zatca_environment)
        otp = compliance_csid.otp

        data = json.dumps({"csr": f"{get_cert_pem(compliance_csid)}"})

        try:
            response = requests.patch(
                url=zatca_environment.production_csid_api,
                headers=get_renewal_headers(otp),
                json=data,
            )

            if response.status_code == 200:
                response_json = response.json()
                self.created_time = frappe.utils.now_datetime()
                self.expiry_date = calculation_expiry_date(self.created_time)
                self.request_id = response_json.get("requestID", "")
                self.disposition_message = response_json.get("dispositionMessage", "")
                self.binary_security_token = response_json.get("binarySecurityToken", "")
                self.token_type = response_json.get("tokenType", "")
                self.secret = response_json.get("secret", "")
                self.errors = response_json.get("errors", "{}")

                self.certificate = build_certificate_data(self.binary_security_token)
                self.public_key = create_public_key(self.certificate)

                self.save()
                return "Production CSID renewed successfully"
            else:
                handle_error(response)

        except requests.exceptions.RequestException as req_err:
            frappe.throw(
                f"Request error: {str(req_err)}\n{response.text if 'response' in locals() else ''}"
            )
        except Exception:
            frappe.log_error(frappe.get_traceback(), "ZATCA Renewal Error")


def get_renewal_headers(otp):
    headers = {
        "accept": "application/json",
        "OTP": otp,
        "accept-language": "en",
        "Accept-Version": "V2",
        "Content-Type": "application/json",
    }
    return headers


def get_cert_pem(compliance_csid):
    der_bytes = base64.b64decode(compliance_csid.certificate)

    pem_lines = [
        "-----BEGIN CERTIFICATE REQUEST-----",
        *wrap(base64.b64encode(der_bytes).decode(), 64),
        "-----END CERTIFICATE REQUEST-----",
    ]
    pem_csr = "\n".join(pem_lines)

    csr_for_zatca = base64.b64encode(pem_csr.encode()).decode()
    return csr_for_zatca


def handle_error(response):
    error_data = response.json()
    error_code = error_data.get("code", "").replace("-", " ").title()
    error_message = error_data.get("message", "")
    html_output = f"<b>ZATCA Error {response.status_code} - {error_code}</b><br><br>{error_message}"

    return frappe.msgprint(title="ZATCA Submission Failed", msg=html_output, indicator="red")
