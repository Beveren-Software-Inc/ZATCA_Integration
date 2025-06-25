import frappe
import base64
from frappe import _
import hashlib
from datetime import datetime
from xml import etree 
import lxml.etree as MyTree
from cryptography import x509
from cryptography.hazmat._oid import NameOID
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.bindings._rust import ObjectIdentifier
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import ec
import asn1
from base64 import b64encode
from io import BytesIO
import qrcode
import base64
from io import BytesIO
from pyzbar.pyzbar import decode
from PIL import Image
from frappe import _

@frappe.whitelist()
def generate_private_keys(doc_name):
    """Create and store an EC SECP256K1 private key for a given Zatca CSR Settings document."""
    try:
        doc = frappe.get_doc("Zatca CSR Settings", doc_name)
        private_key = ec.generate_private_key(ec.SECP256K1(), backend=default_backend())
        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )

        private_key = private_key_pem.decode("utf-8")
        return private_key_pem

    except Exception as e:
        frappe.log_error(title="Private Key Generation Failed", message=frappe.get_traceback())

        frappe.throw(
            _("Failed to generate private key for document: {0}. Please check the error log.").format(doc)
        )

        return None

@frappe.whitelist(allow_guest=False)
def generate_csr(doc_name):
    """Main function to generate CSR"""
    try:
        doc = frappe.get_doc("Zatca CSR Settings", doc_name)
        private_key_pem, private_key = get_private_key(doc)
        csr = build_certificate_signing_request(doc, private_key)
        return save_and_return_csr(doc,private_key_pem, csr)
        
    except Exception as e:
        handle_csr_error(doc_name, e)
        frappe.throw(_("CSR generation failed. Please check error logs."))

def get_private_key(doc):
    """Generate and load private key"""
    private_key_pem = generate_private_keys(doc.name)
    serialized_key_pem = serialization.load_pem_private_key(
        private_key_pem, password=None, backend=default_backend()
    )
    return private_key_pem, serialized_key_pem


def build_certificate_signing_request(doc, private_key):
    """Construct and sign the CSR"""
    csr_values = get_csr_data(doc)
    subject = build_csr_subject(csr_values)
    extensions = build_csr_extensions(csr_values, doc.zatca_environment)
    
    builder = x509.CertificateSigningRequestBuilder()
    builder = builder.subject_name(subject)
    
    for ext, critical in extensions:
        builder = builder.add_extension(ext, critical)
    
    return builder.sign(private_key, hashes.SHA256(), default_backend())

def build_csr_subject(csr_values):
    """Build the CSR subject name"""
    return x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, csr_values["csr.country.name"]),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, csr_values["csr.organization.unit.name"]),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, csr_values["csr.organization.name"]),
        x509.NameAttribute(NameOID.COMMON_NAME, csr_values["csr.common.name"]),
    ])

def build_csr_extensions(csr_values, environment):
    """Build all required CSR extensions"""
    custom_oid = ObjectIdentifier("1.3.6.1.4.1.311.20.2")
    
    oid_value = (
        "TESTZATCA-Code-Signing" if environment == "Sandbox Portal" else
        "PREZATCA-Code-Signing" if environment == "Simulation Portal" else
        "ZATCA-Code-Signing"
    )
    
    custom_extension = x509.UnrecognizedExtension(custom_oid, encode_custom_oid_value(oid_value))
    
    alt_name = x509.SubjectAlternativeName([
        x509.DirectoryName(x509.Name([
            x509.NameAttribute(NameOID.SURNAME, csr_values["csr.serial.number"]),
            x509.NameAttribute(NameOID.USER_ID, csr_values["csr.organization.identifier"]),
            x509.NameAttribute(NameOID.TITLE, csr_values["csr.invoice.type"]),
            x509.NameAttribute(ObjectIdentifier("2.5.4.26"), csr_values["csr.location.address"]),
            x509.NameAttribute(NameOID.BUSINESS_CATEGORY, csr_values["csr.industry.business.category"]),
        ]))
    ])
    
    return [
        (custom_extension, False),
        (alt_name, False)
    ]

def save_and_return_csr(doc, private_key_pem, csr):
    """Save CSR to document and return base64 encoded result"""
    csr_pem = csr.public_bytes(serialization.Encoding.PEM)
    base64csr = base64.b64encode(csr_pem).decode("utf-8")
    # frappe.throw(str(private_key_pem))
    doc.private_key = private_key_pem.decode("utf-8")
    doc.private_key_pem_format = str(private_key_pem)
    doc.csr = base64csr.strip()
    doc.csr_pem_format = csr_pem.decode("utf-8")
    doc.save(ignore_permissions=True)
    frappe.msgprint(
            _("CSR and Private Key were generated successfully and saved to the document.<br><br>"
              "<b>Next Step:</b> Create and generate CSID"),
            title="CSR Generation Complete",
            indicator="green"
        )
    return base64csr

def handle_csr_error(doc_name, error):
    """Log CSR generation errors"""
    error_message = f"CSR generation failed for doc: {doc_name}"
    frappe.log_error(title="CSR Generation Failed", message=f"{error_message}\n\n{frappe.get_traceback()}")


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

def build_certificate_data(binary_security_token):
    return base64.b64decode(binary_security_token).decode('utf-8')

def create_public_key(certificate):
    '''Create a public key from the certificate data provided in the compliance csid'''
    try:
       
        certificate_data_str = certificate
       
        if not certificate_data_str:
            frappe.throw(_("No certificate data generated."))

        # Build the PEM certificate
        cert_base64 = f"""
        -----BEGIN CERTIFICATE-----
        {certificate_data_str.strip()}
        -----END CERTIFICATE-----
        """
        # Load the certificate and extract the public key
        cert = x509.load_pem_x509_certificate(cert_base64.encode(), default_backend())
        public_key = cert.public_key()
        public_key_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
       
        return public_key_pem
        # Ensure data is committed to the database
        # frappe.db.commit()

    except (ValueError, KeyError, TypeError, frappe.ValidationError) as e:
        frappe.throw(_("Error occurred while creating public key: " + str(e)))


def get_api_url(prod_csid):
    """
    Get the URL for the Production CSID based on the environment.
    """
    compliance_csid = frappe.get_doc("Compliance CSID", prod_csid.compliance_csid)
    
    zatca_settings = frappe.get_doc("Zatca CSR Settings", compliance_csid.csr_settings)
    zatca_environment = frappe.get_doc("Zatca Environment", zatca_settings.zatca_environment)
    
    if zatca_environment.environment == "Sandbox Portal":
        return zatca_environment.sandbox_production_csid_api
    elif zatca_environment.environment == "Simulation Portal":
        return zatca_environment.simulation_production_csid_api
    else:
        return zatca_environment.production_csid_api


def removetags(finalzatcaxml):
    """remove the unwanted tags from created xml"""
    try:
        # Code corrected by Farook K - ERPGulf
        xml_file = MyTree.fromstring(finalzatcaxml)
        xsl_file = MyTree.fromstring(
            """<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                                    xmlns:xs="http://www.w3.org/2001/XMLSchema"
                                    xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
                                    xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
                                    xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
                                    xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"
                                    exclude-result-prefixes="xs"
                                    version="2.0">
                                    <xsl:output omit-xml-declaration="yes" encoding="utf-8" indent="no"/>
                                    <xsl:template match="node() | @*">
                                        <xsl:copy>
                                            <xsl:apply-templates select="node() | @*"/>
                                        </xsl:copy>
                                    </xsl:template>
                                    <xsl:template match="//*[local-name()='Invoice']//*[local-name()='UBLExtensions']"></xsl:template>
                                    <xsl:template match="//*[local-name()='AdditionalDocumentReference'][cbc:ID[normalize-space(text()) = 'QR']]"></xsl:template>
                                        <xsl:template match="//*[local-name()='Invoice']/*[local-name()='Signature']"></xsl:template>
                                    </xsl:stylesheet>"""
        )
        transform = MyTree.XSLT(xsl_file.getroottree())
        transformed_xml = transform(xml_file.getroottree())
        return transformed_xml
    except (ValueError, KeyError, TypeError, frappe.ValidationError) as e:
        frappe.throw(_("error occurred win removing tags " + str(e)))
        return None


def canonicalize_xml(tag_removed_xml):
    """canonicalisation of the xml"""
    try:
        canonical_xml = etree.tostring(tag_removed_xml, method="c14n").decode()
        return canonical_xml
    except (ValueError, KeyError, TypeError, frappe.ValidationError) as e:
        frappe.throw(_("error occurred in canonicalise xml " + str(e)))
        return None


def getinvoicehash(canonicalized_xml):
    """Getting the invoice hash of the xml"""
    try:
        hash_object = hashlib.sha256(canonicalized_xml.encode())
        hash_hex = hash_object.hexdigest()
        # print(hash_hex)
        hash_base64 = base64.b64encode(bytes.fromhex(hash_hex)).decode("utf-8")
        return hash_hex, hash_base64
    except Exception as e:
        raise frappe.ValidationError(
            f"error occurred while invoice hash {str(e)}"
        ) from e


def digital_signature(hash1, invoice):
    """find digital signature of xml"""
    try:
        prod_csid = get_prod_csid(invoice)
        compliance_csid = frappe.get_doc("Compliance CSID", prod_csid.compliance_csid)
        private_key_data_str = compliance_csid
    
        private_key_bytes = private_key_data_str.encode("utf-8")
        private_key = serialization.load_pem_private_key(
            private_key_bytes, password=None, backend=default_backend()
        )
        hash_bytes = bytes.fromhex(hash1)
        signature = private_key.sign(hash_bytes, ec.ECDSA(hashes.SHA256()))
        encoded_signature = base64.b64encode(signature).decode()

        return encoded_signature

    except (ValueError, KeyError, TypeError, frappe.ValidationError) as e:
        frappe.throw(_)("eError in digital signature:" + str(e))
        return None


def extract_certificate_details(invoice):
    """extracting the certificate details from the certificate data"""
    try:
      
        prod_csid = get_prod_csid(invoice)
        certificate_data = (prod_csid.certificate).strip()
        # Format the certificate string to PEM format if not already in correct PEM format
        formatted_certificate = "-----BEGIN CERTIFICATE-----\n"
        formatted_certificate += "\n".join(
            certificate_data[i : i + 64]
            for i in range(0, len(certificate_data), 64)
        )
        formatted_certificate += "\n-----END CERTIFICATE-----\n"
        # Load the certificate using cryptography
        certificate_bytes = formatted_certificate.encode("utf-8")
        cert = x509.load_pem_x509_certificate(certificate_bytes, default_backend())
        formatted_issuer_name = cert.issuer.rfc4514_string()
        issuer_name = ", ".join([x.strip() for x in formatted_issuer_name.split(",")])
        serial_number = cert.serial_number
        return issuer_name, serial_number

    except (ValueError, KeyError, TypeError, frappe.ValidationError) as e:
        frappe.throw(_("Error inextracting certificate details" + str(e)))
        return None


def certificate_hash(invoice):
    """Find the certificate hash and returning the value"""
    try:
        prod_csid = get_prod_csid(invoice)
        certificate_data = (prod_csid.certificate).strip()
        
        # Calculate the SHA-256 hash of the certificate data
        certificate_data_bytes = certificate_data.encode("utf-8")
        sha256_hash = hashlib.sha256(certificate_data_bytes).hexdigest()
        # Encode the hash in base64
        base64_encoded_hash = base64.b64encode(sha256_hash.encode("utf-8")).decode(
            "utf-8"
        )
        return base64_encoded_hash

    except (ValueError, KeyError, TypeError, frappe.ValidationError) as e:
        frappe.throw(
            _("Error in obtaining certificate hash chcek cert data: " + str(e))
        )
        return None


def xml_base64_decode(signed_xmlfile_name):
    """xml base64 decode"""
    try:
        with open(signed_xmlfile_name, "r", encoding="utf-8") as file:
            xml = file.read().lstrip()
            base64_encoded = base64.b64encode(xml.encode("utf-8"))
            base64_decoded = base64_encoded.decode("utf-8")
            return base64_decoded
    except (ValueError, KeyError, TypeError, frappe.ValidationError) as e:
        frappe.msgprint(_("Error in xml base64:  " + str(e)))
        return None


def signxml_modify(invoice):
    """modify the signed xml by adding the values like signing time,serial number etc"""
    try:
        encoded_certificate_hash = certificate_hash(invoice)
        issuer_name, serial_number = extract_certificate_details(
            invoice
        )
        original_invoice_xml = etree.parse(
            frappe.local.site + "/private/files/finalzatcaxml.xml"
        )
        root = original_invoice_xml.getroot()
        namespaces = {
            "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
            "sig": "urn:oasis:names:specification:ubl:schema:xsd:CommonSignatureComponents-2",
            "sac": "urn:oasis:names:specification:ubl:schema:xsd:SignatureAggregateComponents-2",
            "xades": "http://uri.etsi.org/01903/v1.3.2#",
            "ds": "http://www.w3.org/2000/09/xmldsig#",
        }

        xpath_dv = "ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/sig:UBLDocumentSignatures/sac:SignatureInformation/ds:Signature/ds:Object/xades:QualifyingProperties/xades:SignedProperties/xades:SignedSignatureProperties/xades:SigningCertificate/xades:Cert/xades:CertDigest/ds:DigestValue"
        xpath_signtime = "ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/sig:UBLDocumentSignatures/sac:SignatureInformation/ds:Signature/ds:Object/xades:QualifyingProperties/xades:SignedProperties/xades:SignedSignatureProperties/xades:SigningTime"
        xpath_issuername = "ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/sig:UBLDocumentSignatures/sac:SignatureInformation/ds:Signature/ds:Object/xades:QualifyingProperties/xades:SignedProperties/xades:SignedSignatureProperties/xades:SigningCertificate/xades:Cert/xades:IssuerSerial/ds:X509IssuerName"
        xpath_serialnum = "ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/sig:UBLDocumentSignatures/sac:SignatureInformation/ds:Signature/ds:Object/xades:QualifyingProperties/xades:SignedProperties//xades:SignedSignatureProperties/xades:SigningCertificate/xades:Cert/xades:IssuerSerial/ds:X509SerialNumber"
        element_dv = root.find(xpath_dv, namespaces)
        element_st = root.find(xpath_signtime, namespaces)
        element_in = root.find(xpath_issuername, namespaces)
        element_sn = root.find(xpath_serialnum, namespaces)
        element_dv.text = encoded_certificate_hash
        element_st.text = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
        signing_time = element_st.text
        element_in.text = issuer_name
        element_sn.text = str(serial_number)
        with open(frappe.local.site + "/private/files/after_step_4.xml", "wb") as file:
            original_invoice_xml.write(
                file,
                encoding="utf-8",
                xml_declaration=True,
            )
        return namespaces, signing_time
    except (ValueError, KeyError, TypeError, frappe.ValidationError) as e:
        frappe.throw(_(" error in modification of xml sign part: " + str(e)))
        return None


def generate_signed_properties_hash(
    signing_time, issuer_name, serial_number, encoded_certificate_hash
):
    """generate the signed property hash of the xml using a part
    of the xml"""
    try:
        xml_string = """<xades:SignedProperties xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" Id="xadesSignedProperties">
                                    <xades:SignedSignatureProperties>
                                        <xades:SigningTime>{signing_time}</xades:SigningTime>
                                        <xades:SigningCertificate>
                                            <xades:Cert>
                                                <xades:CertDigest>
                                                    <ds:DigestMethod xmlns:ds="http://www.w3.org/2000/09/xmldsig#" Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
                                                    <ds:DigestValue xmlns:ds="http://www.w3.org/2000/09/xmldsig#">{certificate_hash}</ds:DigestValue>
                                                </xades:CertDigest>
                                                <xades:IssuerSerial>
                                                    <ds:X509IssuerName xmlns:ds="http://www.w3.org/2000/09/xmldsig#">{issuer_name}</ds:X509IssuerName>
                                                    <ds:X509SerialNumber xmlns:ds="http://www.w3.org/2000/09/xmldsig#">{serial_number}</ds:X509SerialNumber>
                                                </xades:IssuerSerial>
                                            </xades:Cert>
                                        </xades:SigningCertificate>
                                    </xades:SignedSignatureProperties>
                                </xades:SignedProperties>"""
        xml_string_rendered = xml_string.format(
            signing_time=signing_time,
            certificate_hash=encoded_certificate_hash,
            issuer_name=issuer_name,
            serial_number=str(serial_number),
        )
        utf8_bytes = xml_string_rendered.encode("utf-8")
        hash_object = hashlib.sha256(utf8_bytes)
        hex_sha256 = hash_object.hexdigest()
        signed_properties_base64 = base64.b64encode(hex_sha256.encode("utf-8")).decode(
            "utf-8"
        )
        return signed_properties_base64
    except (ValueError, KeyError, TypeError, frappe.ValidationError) as e:
        frappe.throw(_(" error in generating signed properties hash: " + str(e)))
        return None

def populate_the_ubl_extensions_output(
    encoded_signature,
    namespaces,
    signed_properties_base64,
    encoded_hash,
    invoice
):
    """populate the ubl extension output by giving the signature values and digest values"""
    try:
        updated_invoice_xml = etree.parse(
            frappe.local.site + "/private/files/after_step_4.xml"
        )
        root3 = updated_invoice_xml.getroot()
            
        prod_csid = get_prod_csid(invoice)
        content = (prod_csid.certificate).strip()

        xpath_signvalue = "ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/sig:UBLDocumentSignatures/sac:SignatureInformation/ds:Signature/ds:SignatureValue"
        xpath_x509certi = "ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/sig:UBLDocumentSignatures/sac:SignatureInformation/ds:Signature/ds:KeyInfo/ds:X509Data/ds:X509Certificate"
        xpath_digvalue = "ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/sig:UBLDocumentSignatures/sac:SignatureInformation/ds:Signature/ds:SignedInfo/ds:Reference[@URI='#xadesSignedProperties']/ds:DigestValue"
        xpath_digvalue2 = "ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/sig:UBLDocumentSignatures/sac:SignatureInformation/ds:Signature/ds:SignedInfo/ds:Reference[@Id='invoiceSignedData']/ds:DigestValue"

        signvalue6 = root3.find(xpath_signvalue, namespaces)
        x509certificate6 = root3.find(xpath_x509certi, namespaces)
        digestvalue6 = root3.find(xpath_digvalue, namespaces)
        digestvalue6_2 = root3.find(xpath_digvalue2, namespaces)

        signvalue6.text = encoded_signature
        x509certificate6.text = content
        digestvalue6.text = signed_properties_base64
        digestvalue6_2.text = encoded_hash

        with open(
            frappe.local.site + "/private/files/final_xml_after_sign.xml", "wb"
        ) as file:
            updated_invoice_xml.write(file, encoding="utf-8", xml_declaration=True)

    except (ValueError, KeyError, TypeError, frappe.ValidationError) as e:
        frappe.throw(_("Error in populating UBL extension output: " + str(e)))
        return

def get_prod_csid(invoice):
    company_doc = frappe.get_doc("Company", invoice.company)
    prod_csid = frappe.get_doc("Production CSID", company_doc.custom_production_csid)
        
    return prod_csid



def extract_public_key_data(invoice):
    """extract public key"""
    try:
        prod_csid = get_prod_csid(invoice)
        public_key_pem = (prod_csid.public_key).strip()

        lines = public_key_pem.splitlines()
        key_data = "".join(lines[1:-1])
        key_data = key_data.replace("-----BEGIN PUBLIC KEY-----", "").replace(
            "-----END PUBLIC KEY-----", ""
        )
        key_data = key_data.replace(" ", "").replace("\n", "")

        return key_data

    except (ValueError, KeyError, TypeError, frappe.ValidationError) as e:
        frappe.throw(_("Error in extracting public key data: " + str(e)))
        return None


def get_tlv_for_value(tag_num, tag_value):
    """get the tlv data value for teh qr"""
    try:
        tag_num_buf = bytes([tag_num])
        if tag_value is None:
            frappe.throw(f"Error: Tag value for tag number {tag_num} is None")
        if isinstance(tag_value, str):
            if len(tag_value) < 256:
                tag_value_len_buf = bytes([len(tag_value)])
            else:
                tag_value_len_buf = bytes(
                    [0xFF, (len(tag_value) >> 8) & 0xFF, len(tag_value) & 0xFF]
                )
            tag_value = tag_value.encode("utf-8")
        else:
            tag_value_len_buf = bytes([len(tag_value)])
        return tag_num_buf + tag_value_len_buf + tag_value
    except (ValueError, KeyError, TypeError, frappe.ValidationError) as e:
        frappe.throw(_(" error in getting the tlv data value: " + str(e)))
        return None

import binascii

def tag8_public_key(invoice):
    """tag 8 of qr from public key"""
    try:
        # create_public_key(company_abbr, source_doc)
        base64_encoded = extract_public_key_data(invoice)
        byte_data = base64.b64decode(base64_encoded)
        hex_data = binascii.hexlify(byte_data).decode("utf-8")
        chunks = [hex_data[i : i + 2] for i in range(0, len(hex_data), 2)]
        value = "".join(chunks)
        binary_data = bytes.fromhex(value)
        return binary_data
    except (ValueError, KeyError, TypeError, frappe.ValidationError) as e:
        frappe.throw(_("Error in tag 8 from public key: " + str(e)))
        return None


def tag9_signature_ecdsa(invoice):
    """tag 9 of signature"""
    try:
        prod_csid = get_prod_csid(invoice)
        certificate_content = (prod_csid.certificate).strip()
        formatted_certificate = "-----BEGIN CERTIFICATE-----\n"
        formatted_certificate += "\n".join(
            certificate_content[i : i + 64]
            for i in range(0, len(certificate_content), 64)
        )
        formatted_certificate += "\n-----END CERTIFICATE-----\n"

        certificate_bytes = formatted_certificate.encode("utf-8")
        cert = x509.load_pem_x509_certificate(certificate_bytes, default_backend())
        signature = cert.signature
        signature_hex = "".join("{:02x}".format(byte) for byte in signature)
        signature_bytes = bytes.fromhex(signature_hex)

        return signature_bytes

    except (ValueError, KeyError, TypeError, frappe.ValidationError) as e:
        frappe.throw(_("Error in tag 9 (signaturetag): " + str(e)))
        return None


def generate_tlv_xml(invoice):
    """generate xml by adding the tlv data"""
    try:

        with open(
            frappe.local.site + "/private/files/final_xml_after_sign.xml", "rb"
        ) as file:
            xml_data = file.read()
        root = etree.fromstring(xml_data)
        namespaces = {
            "ubl": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
            "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
            "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
            "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
            "sig": "urn:oasis:names:specification:ubl:schema:xsd:CommonSignatureComponents-2",
            "sac": "urn:oasis:names:specification:ubl:schema:xsd:SignatureAggregateComponents-2",
            "ds": "http://www.w3.org/2000/09/xmldsig#",
        }
        issue_date_xpath = "/ubl:Invoice/cbc:IssueDate"
        issue_time_xpath = "/ubl:Invoice/cbc:IssueTime"
        issue_date_results = root.xpath(issue_date_xpath, namespaces=namespaces)
        issue_time_results = root.xpath(issue_time_xpath, namespaces=namespaces)
        issue_date = (
            issue_date_results[0].text.strip() if issue_date_results else "Missing Data"
        )
        issue_time = (
            issue_time_results[0].text.strip() if issue_time_results else "Missing Data"
        )
        issue_date_time = issue_date + "T" + issue_time
        tags_xpaths = [
            (
                1,
                "/ubl:Invoice/cac:AccountingSupplierParty/cac:Party/cac:PartyLegalEntity/cbc:RegistrationName",
            ),
            (
                2,
                "/ubl:Invoice/cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID",
            ),
            (3, None),
            (4, "/ubl:Invoice/cac:LegalMonetaryTotal/cbc:TaxInclusiveAmount"),
            (5, "/ubl:Invoice/cac:TaxTotal/cbc:TaxAmount"),
            (
                6,
                "/ubl:Invoice/ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/sig:UBLDocumentSignatures/sac:SignatureInformation/ds:Signature/ds:SignedInfo/ds:Reference/ds:DigestValue",
            ),
            (
                7,
                "/ubl:Invoice/ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/sig:UBLDocumentSignatures/sac:SignatureInformation/ds:Signature/ds:SignatureValue",
            ),
            (8, None),
            (9, None),
        ]
        result_dict = {}
        for tag, xpath in tags_xpaths:
            if isinstance(xpath, str):
                elements = root.xpath(xpath, namespaces=namespaces)
                if elements:
                    value = (
                        elements[0].text
                        if isinstance(elements[0], etree._Element)
                        else elements[0]
                    )
                    result_dict[tag] = value
                else:
                    result_dict[tag] = "Not found"
            else:
                result_dict[tag] = xpath
        result_dict[3] = issue_date_time
        result_dict[8] = tag8_public_key(invoice)
        result_dict[9] = tag9_signature_ecdsa(invoice)
        result_dict[1] = result_dict[1].encode(
            "utf-8"
        )  # Handling Arabic company name in QR Code
        return result_dict
    except (ValueError, KeyError, TypeError, frappe.ValidationError) as e:
        frappe.throw(_("Error in getting the entire TLV data: " + str(e)))
        return None


def update_qr_toxml(qrcodeb64):
    """updating the  alla values of qr to xml"""
    try:
        xml_file_path = frappe.local.site + "/private/files/final_xml_after_sign.xml"
        xml_tree = etree.parse(xml_file_path)
        namespaces = {
            "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
            "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
        }
        qr_code_element = xml_tree.find(
            './/cac:AdditionalDocumentReference[cbc:ID="QR"]/cac:Attachment/cbc:EmbeddedDocumentBinaryObject',
            namespaces=namespaces,
        )
        if qr_code_element is not None:
            qr_code_element.text = qrcodeb64
        else:
            frappe.msgprint(
                _(f"QR code element not found in the XML")
            )
        xml_tree.write(xml_file_path, encoding="UTF-8", xml_declaration=True)
    except (ValueError, KeyError, TypeError, frappe.ValidationError) as e:
        frappe.throw(
            _(f"Error in saving TLV data to XML" + str(e))
        )

def structuring_signedxml():
    """structuring the signed xml"""
    try:
        with open(
            frappe.local.site + "/private/files/final_xml_after_sign.xml",
            "r",
            encoding="utf-8",
        ) as file:
            xml_content = file.readlines()
        indentations = {
            29: [
                '<xades:QualifyingProperties xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" Target="signature">',
                "</xades:QualifyingProperties>",
            ],
            33: [
                '<xades:SignedProperties Id="xadesSignedProperties">',
                "</xades:SignedProperties>",
            ],
            37: [
                "<xades:SignedSignatureProperties>",
                "</xades:SignedSignatureProperties>",
            ],
            41: [
                "<xades:SigningTime>",
                "<xades:SigningCertificate>",
                "</xades:SigningCertificate>",
            ],
            45: ["<xades:Cert>", "</xades:Cert>"],
            49: [
                "<xades:CertDigest>",
                "<xades:IssuerSerial>",
                "</xades:CertDigest>",
                "</xades:IssuerSerial>",
            ],
            53: [
                '<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>',
                "<ds:DigestValue>",
                "<ds:X509IssuerName>",
                "<ds:X509SerialNumber>",
            ],
        }

        def adjust_indentation(line):
            for col, tags in indentations.items():
                for tag in tags:
                    if line.strip().startswith(tag):
                        return " " * (col - 1) + line.lstrip()
            return line

        adjusted_xml_content = [adjust_indentation(line) for line in xml_content]
        with open(
            frappe.local.site + "/private/files/final_xml_after_indent.xml",
            "w",
            encoding="utf-8",
        ) as file:
            file.writelines(adjusted_xml_content)
        signed_xmlfile_name = (
            frappe.local.site + "/private/files/final_xml_after_indent.xml"
        )
        return signed_xmlfile_name
    except (ValueError, KeyError, TypeError, frappe.ValidationError) as e:
        frappe.throw(_(" error in structuring signed xml: " + str(e)))
        return None

def update_invoice(invoice, qr_code_data):
    frappe.db.set_value(
        "Sales Invoice",
        invoice.name,
        {
            "custom_qr_code": get_qr_code(qr_code_data),
            # "zatca_qr_code": qr_code_data,
        },
    )
    
@frappe.whitelist()
def get_qr_code(data: str) -> str:
    """Generate QR Code data

    Args:
        data (str): The information used to generate the QR Code

    Returns:
        str: The QR Code.
    """
    qr_code_bytes = get_qr_code_bytes(data, format="PNG")
    base_64_string = bytes_to_base64_string(qr_code_bytes)

    return add_file_info(base_64_string)


def add_file_info(data: str) -> str:
    """Add info about the file type and encoding.

    This is required so the browser can make sense of the data."""
    return f"data:image/png;base64, {data}"

def get_qr_code_bytes(data: bytes | str, format: str = "PNG") -> bytes:
    """Create a QR code and return the bytes."""
    img = qrcode.make(data)

    buffered = BytesIO()
    img.save(buffered, format=format)

    return buffered.getvalue()

def bytes_to_base64_string(data: bytes) -> str:
    """Convert bytes to a base64 encoded string."""
    return b64encode(data).decode("utf-8")

@frappe.whitelist()
def decode_qr_code(base64_string: str) -> str:
    """Decode base64 string back to QR Code and extract the encoded data."""
    
    base64_data = base64_string.split(',')[1]
    
    image_data = base64.b64decode(base64_data)
    
    img = Image.open(BytesIO(image_data))
    
    qr_code_data = decode(img)
    
    if qr_code_data:
        return qr_code_data[0].data.decode('utf-8') 
    
    return None  