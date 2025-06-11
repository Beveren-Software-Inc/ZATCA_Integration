
import hashlib
import base64
import json
import binascii
from datetime import datetime
from lxml import etree
import lxml.etree as MyTree
from frappe import _
import frappe
from cryptography import x509
from cryptography.hazmat._oid import NameOID
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.bindings._rust import ObjectIdentifier
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import ec
import requests
import asn1


@frappe.whitelist()
def create_private_keys(doc_name):
    """Create and store an EC SECP256K1 private key for a given Zatca CSR Settings document."""
    try:
        doc = frappe.get_doc("Zatca CSR Settings", doc_name)
        private_key = ec.generate_private_key(ec.SECP256K1(), backend=default_backend())
        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )

        doc.private_key = private_key_pem.decode("utf-8")
        
        # doc.private_key_pem_format = str(private_key_pem)
        # doc.save(ignore_permissions=True)

        return private_key_pem

    except Exception as e:
        frappe.log_error(title="Private Key Generation Failed", message=frappe.get_traceback())

        frappe.throw(
            _("Failed to generate private key for document: {0}. Please check the error log.").format(doc)
        )

        return None

@frappe.whitelist(allow_guest=False)
def generate_csr(doc_name):
    """
    Generate a Certificate Signing Request (CSR) for ZATCA integration
    based on company configuration stored in Zatca CSR Settings.
    """
    try:
        doc = frappe.get_doc("Zatca CSR Settings", doc_name)

        portal_type = doc.zatca_environment
        csr_values = get_csr_data(doc)

        # Extract CSR fields
        company_csr_data = csr_values
        csr_common_name = company_csr_data.get("csr.common.name")
        csr_serial_number = company_csr_data.get("csr.serial.number")
        csr_organization_identifier = company_csr_data.get("csr.organization.identifier")
        csr_organization_unit_name = company_csr_data.get("csr.organization.unit.name")
        csr_organization_name = company_csr_data.get("csr.organization.name")
        csr_country_name = company_csr_data.get("csr.country.name")
        csr_invoice_type = company_csr_data.get("csr.invoice.type")
        csr_location_address = company_csr_data.get("csr.location.address")
        csr_industry_business_category = company_csr_data.get("csr.industry.business.category")

        # Determine portal environment OID
        if portal_type == "Sandbox Portal":
            customoid = encode_custom_oid_value("TESTZATCA-Code-Signing")
        elif portal_type == "Simulation Portal":
            customoid = encode_custom_oid_value("PREZATCA-Code-Signing")
        else:
            customoid = encode_custom_oid_value("ZATCA-Code-Signing")

        # Generate private key and load it
        private_key_pem = create_private_keys(doc)
        private_key = serialization.load_pem_private_key(
            private_key_pem, password=None, backend=default_backend()
        )

        # Construct CSR subject and extensions
        custom_oid_string = "1.3.6.1.4.1.311.20.2"
        oid = ObjectIdentifier(custom_oid_string)
        custom_extension = x509.extensions.UnrecognizedExtension(oid, customoid)
        dn = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, csr_country_name),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, csr_organization_unit_name),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, csr_organization_name),
            x509.NameAttribute(NameOID.COMMON_NAME, csr_common_name),
        ])
        alt_name = x509.SubjectAlternativeName([
            x509.DirectoryName(x509.Name([
                x509.NameAttribute(NameOID.SURNAME, csr_serial_number),
                x509.NameAttribute(NameOID.USER_ID, csr_organization_identifier),
                x509.NameAttribute(NameOID.TITLE, csr_invoice_type),
                x509.NameAttribute(ObjectIdentifier("2.5.4.26"), csr_location_address),
                x509.NameAttribute(NameOID.BUSINESS_CATEGORY, csr_industry_business_category),
            ])),
        ])

        # Build and sign the CSR
        csr = (
            x509.CertificateSigningRequestBuilder()
            .subject_name(dn)
            .add_extension(custom_extension, critical=False)
            .add_extension(alt_name, critical=False)
            .sign(private_key, hashes.SHA256(), backend=default_backend())
        )

        mycsr = csr.public_bytes(serialization.Encoding.PEM)
        base64csr = base64.b64encode(mycsr).decode("utf-8")

        doc.csr = base64csr.strip()
        doc.csr_pem_format = mycsr.decode("utf-8")
        doc.save(ignore_permissions=True)

        return base64csr

    except Exception as e:
        error_message = f"CSR generation failed for doc: {doc_name}"
        frappe.log_error(title="CSR Generation Failed", message=frappe.get_traceback())

        frappe.throw(_("Something went wrong while generating the CSR. Please check the error log for more details."))



def get_csr_data(doc):
    """Getting csr data from the config for multiple"""
    try:
        
        csr_values = {
            "csr.common.name": doc.csrcommonname,
            "csr.serial.number": doc.csrserialnumber,
            "csr.organization.identifier": doc.csrorganizationidentifier,
            "csr.organization.unit.name": doc.csrorganizationunitname,
            "csr.organization.name": doc.csrorganizationname,
            "csr.country.name": doc.csrcountryname,
            "csr.invoice.type": doc.csrinvoicetype,
            "csr.location.address": doc.csrlocationaddress,
            "csr.industry.business.category": doc.csrindustrybusinesscategory,
        }
        
        return csr_values

    except (frappe.ValidationError, frappe.DoesNotExistError) as e:
        frappe.throw(_(f"Error in fetching CSR data multipe: {e}"))
        return None
    
def encode_custom_oid_value(custom_string):
    """Encoding of a custom string"""
    # Create an encoder
    encoder = asn1.Encoder()
    encoder.start()
    encoder.write(custom_string, asn1.Numbers.UTF8String)
    return encoder.output()

def parse_csr_config(csr_config_string):
    """Parse the csr config data"""
    csr_config = {}
    lines = csr_config_string.splitlines()
    for line in lines:
        key, value = line.split("=", 1)
        csr_config[key.strip()] = value.strip()
    return csr_config




# @frappe.whitelist(allow_guest=False)
# def generate_csid(zatca_doc, company_abbr):
#     """creating csid"""
#     try:
#         if isinstance(zatca_doc, str):
#             zatca_doc = json.loads(zatca_doc)
#         # frappe.msgprint(f"Using OTP (Company): {zatca_doc}")
#         # Validate zatca_doc structure
#         if (
#             not isinstance(zatca_doc, dict)
#             or "doctype" not in zatca_doc
#             or "name" not in zatca_doc
#         ):
#             frappe.throw(
#                 _("Invalid 'zatca_doc' format. Must include 'doctype' and 'name'.")
#             )
#         # Fetch the document based on doctype and name
#         doc = frappe.get_doc(zatca_doc.get("doctype"), zatca_doc.get("name"))
#         if doc.doctype == "ZATCA Multiple Setting":
#             multiple_setting_doc = frappe.get_doc("ZATCA Multiple Setting", doc.name)
#             csr_data_str = multiple_setting_doc.get("custom_csr_data", "")
#         elif doc.doctype == "Company":
#             company_name = frappe.db.get_value(
#                 "Company", {"abbr": company_abbr}, "name"
#             )

#             company_doc = frappe.get_doc("Company", company_name)
#             csr_data_str = company_doc.get("custom_csr_data", "")

#             # frappe.msgprint(f"Using OTP (Company): {csr_values}")
#         else:
#             frappe.throw(_("Unsupported document type for CSR creation."))

#         csr_contents = csr_data_str.strip()

#         if not csr_contents:
#             frappe.throw(_(f"No valid CSR data found for company {company_name}"))

#         payload = json.dumps({"csr": csr_contents})
#         # frappe.msgprint(f"Using OTP: {company_doc.custom_otp}")
#         if doc.doctype == "ZATCA Multiple Setting":
#             otp = multiple_setting_doc.get("custom_otp", "")
#             # frappe.msgprint(f"Using OTP (Multiple Setting): {csr_values}")
#         elif doc.doctype == "Company":
#             otp = company_doc.get("custom_otp", "")

#             # frappe.msgprint(f"Using OTP (Company): {csr_values}")
#         else:
#             frappe.throw(_("no otp."))
#         headers = {
#             "accept": "application/json",
#             "OTP": otp,
#             "Accept-Version": "V2",
#             "Content-Type": "application/json",
#             "Cookie": "TS0106293e=0132a679c07382ce7821148af16b99da546c13ce1dcddbef0e19802eb470e539a4d39d5ef63d5c8280b48c529f321e8b0173890e4f",
#         }

#         frappe.publish_realtime(
#             "show_gif",
#             {"gif_url": "/assets/zatca_erpgulf/js/loading.gif"},
#             user=frappe.session.user,
#         )
#         response = requests.post(
#             url=get_api_url(company_abbr, base_url="compliance"),
#             headers=headers,
#             data=payload,
#             timeout=300,
#         )
#         frappe.publish_realtime("hide_gif", user=frappe.session.user)

#         if response.status_code == 400:
#             frappe.throw(_("Error: OTP is not valid. " + response.text))
#         if response.status_code != 200:
#             frappe.throw(_("Error: Issue with Certificate or OTP. " + response.text))
#         frappe.msgprint(_(str(response.text)))
#         data = json.loads(response.text)

#         concatenated_value = data["binarySecurityToken"] + ":" + data["secret"]
#         encoded_value = base64.b64encode(concatenated_value.encode()).decode()
#         if doc.doctype == "ZATCA Multiple Setting":
#             multiple_setting_doc.custom_certficate = base64.b64decode(
#                 data["binarySecurityToken"]
#             ).decode("utf-8")
#             multiple_setting_doc.custom_basic_auth_from_csid = encoded_value
#             multiple_setting_doc.custom_compliance_request_id_ = data["requestID"]
#             multiple_setting_doc.save(ignore_permissions=True)
#         elif doc.doctype == "Company":
#             company_doc.custom_certificate = base64.b64decode(
#                 data["binarySecurityToken"]
#             ).decode("utf-8")
#             company_doc.custom_basic_auth_from_csid = encoded_value
#             company_doc.custom_compliance_request_id_ = data["requestID"]
#             company_doc.save(ignore_permissions=True)
#         return response.text

#     except (ValueError, KeyError, TypeError, frappe.ValidationError) as e:
#         frappe.throw(_("Error in creating CSID: " + str(e)))
#         return None