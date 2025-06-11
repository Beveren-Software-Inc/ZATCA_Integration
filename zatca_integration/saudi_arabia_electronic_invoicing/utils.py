
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
def create_private_keys(doc):
    """Create and store an EC SECP256K1 private key for a given Zatca CSR Settings document."""
    try:
        doc = doc
        private_key = ec.generate_private_key(ec.SECP256K1(), backend=default_backend())
        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )

        doc.private_key = private_key_pem.decode("utf-8")
        
        doc.private_key_pem_format = str(private_key_pem)
        doc.save(ignore_permissions=True)

        return private_key_pem

    except Exception as e:
        frappe.log_error(title="Private Key Generation Failed", message=frappe.get_traceback())

        frappe.throw(
            _("Failed to generate private key for document: {0}. Please check the error log.").format(doc_name)
        )

        return None

@frappe.whitelist(allow_guest=False)
def generate_csr(doc):
    """
    Function defining the create csr method with the config csr data
    """
    
    doc = doc
    try:

        portal_type = doc.zatca_environment
        csr_values = get_csr_data(doc)
          
        company_csr_data = csr_values

        csr_common_name = company_csr_data.get("csr.common.name")
        csr_serial_number = company_csr_data.get("csr.serial.number")
        csr_organization_identifier = company_csr_data.get(
            "csr.organization.identifier"
        )
        csr_organization_unit_name = company_csr_data.get("csr.organization.unit.name")
        csr_organization_name = company_csr_data.get("csr.organization.name")
        csr_country_name = company_csr_data.get("csr.country.name")
        csr_invoice_type = company_csr_data.get("csr.invoice.type")
        csr_location_address = company_csr_data.get("csr.location.address")
        csr_industry_business_category = company_csr_data.get(
            "csr.industry.business.category"
        )

        if portal_type == "Sandbox Portal":
            customoid = encode_custom_oid_value("TESTZATCA-Code-Signing")
        elif portal_type == "Simulation Portal":
            customoid = encode_custom_oid_value("PREZATCA-Code-Signing")
        else:
            customoid = encode_custom_oid_value("ZATCA-Code-Signing")
        
        private_key_pem = create_private_keys(doc)

        private_key = serialization.load_pem_private_key(
            private_key_pem, password=None, backend=default_backend()
        )

        custom_oid_string = "1.3.6.1.4.1.311.20.2"
        oid = ObjectIdentifier(custom_oid_string)
        custom_extension = x509.extensions.UnrecognizedExtension(oid, customoid)
        dn = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, csr_country_name),
                x509.NameAttribute(
                    NameOID.ORGANIZATIONAL_UNIT_NAME, csr_organization_unit_name
                ),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, csr_organization_name),
                x509.NameAttribute(NameOID.COMMON_NAME, csr_common_name),
            ]
        )
        alt_name = x509.SubjectAlternativeName(
            [
                x509.DirectoryName(
                    x509.Name(
                        [
                            x509.NameAttribute(NameOID.SURNAME, csr_serial_number),
                            x509.NameAttribute(
                                NameOID.USER_ID, csr_organization_identifier
                            ),
                            x509.NameAttribute(NameOID.TITLE, csr_invoice_type),
                            x509.NameAttribute(
                                ObjectIdentifier("2.5.4.26"), csr_location_address
                            ),
                            x509.NameAttribute(
                                NameOID.BUSINESS_CATEGORY,
                                csr_industry_business_category,
                            ),
                        ]
                    )
                ),
            ]
        )

        csr = (
            x509.CertificateSigningRequestBuilder()
            .subject_name(dn)
            .add_extension(custom_extension, critical=False)
            .add_extension(alt_name, critical=False)
            .sign(private_key, hashes.SHA256(), backend=default_backend())
        )
        mycsr = csr.public_bytes(serialization.Encoding.PEM)
        base64csr = base64.b64encode(mycsr)
        encoded_string = base64csr.decode("utf-8")
        
        doc.custom_csr_data = encoded_string.strip()
        doc.save(ignore_permissions=True)
        return encoded_string
    except (ValueError, KeyError, TypeError, frappe.ValidationError) as e:
        frappe.throw(
            _("error occurred while creating csr for company {company_abbr} " + str(e))
        )
        return None


def get_csr_data(zatca_doc):
    """Getting csr data from the config for multiple"""
    try:
        csr_config_string = zatca_doc.custom_csr_config

        if not csr_config_string:
            frappe.throw(_("No CSR config found in company settings"))

        csr_config = parse_csr_config(csr_config_string)

        csr_values = {
            "csr.common.name": csr_config.get("csr.common.name"),
            "csr.serial.number": csr_config.get("csr.serial.number"),
            "csr.organization.identifier": csr_config.get(
                "csr.organization.identifier"
            ),
            "csr.organization.unit.name": csr_config.get("csr.organization.unit.name"),
            "csr.organization.name": csr_config.get("csr.organization.name"),
            "csr.country.name": csr_config.get("csr.country.name"),
            "csr.invoice.type": csr_config.get("csr.invoice.type"),
            "csr.location.address": csr_config.get("csr.location.address"),
            "csr.industry.business.category": csr_config.get(
                "csr.industry.business.category"
            ),
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