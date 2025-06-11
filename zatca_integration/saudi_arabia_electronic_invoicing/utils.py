
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
        doc.private_key_pem_format = private_key_pem
        doc.save(ignore_permissions=True)

        return private_key_pem

    except Exception as e:
        frappe.log_error(title="Private Key Generation Failed", message=frappe.get_traceback())

        frappe.throw(
            _("Failed to generate private key for document: {0}. Please check the error log.").format(doc_name)
        )

        return None


