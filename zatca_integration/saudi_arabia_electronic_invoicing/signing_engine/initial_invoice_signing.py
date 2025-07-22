

import hashlib
import base64
import binascii
from datetime import datetime
from lxml import etree
import lxml.etree as MyTree
from frappe import _
import frappe
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import ec
import asn1
from zatca_integration.saudi_arabia_electronic_invoicing.utils import get_pem_details, get_pem_compliance_details


def encode_customoid(custom_string):
    """Encoding of a custom string"""
    # Create an encoder
    encoder = asn1.Encoder()
    encoder.start()
    encoder.write(custom_string, asn1.Numbers.UTF8String)
    return encoder.output()

def removetags(finalzatcaxml):
    """remove the unwanted tags from created xml"""
    try:
       
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



# def digital_signature(hash1, sales_invoice_doc, is_zatca_test=0, compliance_csid=None):
#     if is_zatca_test:
#         pem_details = get_pem_compliance_details(compliance_csid)
#     else:
#         pem_details = get_pem_details(sales_invoice_doc)
#     private_key_pem = pem_details.get("private_key")
    
#     if isinstance(private_key_pem, str):
#         private_key_pem = private_key_pem.encode('utf-8')
#     frappe.throw(str(private_key_pem))
#     private_key = serialization.load_pem_private_key(
#         private_key_pem,
#         password=None,
#         backend=default_backend()
#     )

#     hash_bytes = bytes.fromhex(hash1)
#     signature = private_key.sign(hash_bytes, ec.ECDSA(hashes.SHA256()))
#     encoded_signature = base64.b64encode(signature).decode()
#     return encoded_signature
def digital_signature(hash1, sales_invoice_doc, is_zatca_test=0, compliance_csid=None):
    if is_zatca_test:
        pem_details = get_pem_compliance_details(compliance_csid)
    else:
        pem_details = get_pem_details(sales_invoice_doc)
    
    private_key_pem = pem_details.get("private_key")
    
    if not private_key_pem:
        frappe.throw("Private key is empty or None")
    
    # Convert to string first, then clean
    if isinstance(private_key_pem, bytes):
        key_string = private_key_pem.decode('utf-8')
    else:
        key_string = str(private_key_pem)
    
    # Clean the key string
    key_string = key_string.strip()
    key_string = key_string.replace('\r\n', '\n').replace('\r', '\n')
    
    # Validate PEM format
    if not key_string.startswith('-----BEGIN'):
        frappe.throw(f"Invalid PEM format: Key doesn't start with -----BEGIN. Starts with: {key_string[:50]}")
    
    if not key_string.endswith('-----'):
        # Try to fix missing newline at end
        if key_string.endswith('-----END EC PRIVATE KEY-----'):
            key_string += '\n'
        else:
            frappe.throw(f"Invalid PEM format: Key doesn't end with -----. Ends with: {key_string[-50:]}")
    
    # Validate base64 content between headers
    try:
        lines = key_string.split('\n')
        base64_content = []
        in_key_section = False
        
        for line in lines:
            line = line.strip()
            if line.startswith('-----BEGIN'):
                in_key_section = True
                continue
            elif line.startswith('-----END'):
                in_key_section = False
                continue
            elif in_key_section and line:
                # Validate this line is valid base64
                import base64
                try:
                    base64.b64decode(line, validate=True)
                    base64_content.append(line)
                except Exception as b64_error:
                    frappe.throw(f"Invalid base64 content in key line: {line}. Error: {str(b64_error)}")
        
        # Reconstruct clean key
        clean_key = "-----BEGIN EC PRIVATE KEY-----\n" + "\n".join(base64_content) + "\n-----END EC PRIVATE KEY-----\n"
        
    except Exception as validation_error:
        frappe.logger().error(f"Key validation failed: {str(validation_error)}")
        clean_key = key_string  # Fall back to original cleaned key
    
    # Debug: Log the actual key for inspection
    frappe.logger().error(f"Key content length: {len(clean_key)}")
    frappe.logger().error(f"Key preview: {clean_key[:100]}...{clean_key[-50:]}")
    
    # Convert back to bytes
    private_key_pem = clean_key.encode('utf-8')
    try:
        private_key = serialization.load_pem_private_key(
            private_key_pem,
            password=None,
            backend=default_backend()
        )
    except ValueError as ve:
        if "Could not deserialize key data" in str(ve):
            # Try alternative approaches
            frappe.logger().error("Primary key loading failed, trying alternatives...")
            
            # Alternative 1: Try with empty byte password
            try:
                private_key = serialization.load_pem_private_key(
                    private_key_pem,
                    password=b'',
                    backend=default_backend()
                )
                frappe.logger().error("Success with empty byte password")
            except Exception:
                # Alternative 2: Try loading as DER if it might be wrongly formatted
                try:
                    # Extract base64 content and try as DER
                    import re
                    base64_only = re.sub(r'-----[^-]+-----', '', clean_key).replace('\n', '').replace(' ', '')
                    der_data = base64.b64decode(base64_only)
                    private_key = serialization.load_der_private_key(
                        der_data,
                        password=None,
                        backend=default_backend()
                    )
                    frappe.logger().error("Success with DER loading")
                except Exception:
                    # Final fallback: detailed error message
                    frappe.throw(f"""
Failed to load private key after trying multiple methods.

Original error: {str(ve)}

Possible causes:
1. Key uses unsupported EC curve (try secp256k1 or secp256r1)
2. Key is corrupted or truncated
3. Key is password-protected (not supported)
4. Key format is not standard PEM

Key details:
- Length: {len(clean_key)} characters
- Starts with: {clean_key[:50]}
- Ends with: {clean_key[-50:]}

Please verify your private key is in correct format:
-----BEGIN EC PRIVATE KEY-----
[base64 encoded key data]
-----END EC PRIVATE KEY-----
                    """)
        else:
            raise ve
    except Exception as e:
        frappe.throw(f"Unexpected error loading private key: {str(e)}\nKey preview: {clean_key[:100]}")
    
    # Generate signature
    try:
        hash_bytes = bytes.fromhex(hash1)
        signature = private_key.sign(hash_bytes, ec.ECDSA(hashes.SHA256()))
        encoded_signature = base64.b64encode(signature).decode()
        return encoded_signature
    except Exception as sign_error:
        frappe.throw(f"Error generating signature: {str(sign_error)}")


def extract_certificate_details(sales_invoice_doc, is_zatca_test=0, compliance_csid=None):
    if is_zatca_test:
        perm_details = get_pem_compliance_details(compliance_csid)
    else:
        perm_details = get_pem_details(sales_invoice_doc)
    certificate_data_str = perm_details.get("certificate")
    """extracting the certificate details from the certificate data"""
    # try:
    certificate_content = certificate_data_str.strip()
    
    # Format the certificate string to PEM format if not already in correct PEM format
    formatted_certificate = "-----BEGIN CERTIFICATE-----\n"
    formatted_certificate += "\n".join(
        certificate_content[i : i + 64]
        for i in range(0, len(certificate_content), 64)
    )
    formatted_certificate += "\n-----END CERTIFICATE-----\n"
    # Load the certificate using cryptography
    certificate_bytes = formatted_certificate.encode("utf-8")
    cert = x509.load_pem_x509_certificate(certificate_bytes, default_backend())
    formatted_issuer_name = cert.issuer.rfc4514_string()
    issuer_name = ", ".join([x.strip() for x in formatted_issuer_name.split(",")])
    serial_number = cert.serial_number
    return issuer_name, serial_number


def certificate_hash(sales_invoice_doc, is_zatca_test=0, compliance_csid=None):
    """Find the certificate hash and returning the value"""
    try:
        if is_zatca_test:

            perm_details = get_pem_compliance_details(compliance_csid)
        else:
            perm_details = get_pem_details(sales_invoice_doc)
        # perm_details = get_pem_details(sales_invoice_doc)
        certificate_data_str = perm_details.get("certificate")
        certificate_data = certificate_data_str.strip()

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


def signxml_modify(sales_invoice_doc, is_zatca_test=0, compliance_csid=None):
    """modify the signed xml by adding the values like signing time,serial number etc"""
    
    encoded_certificate_hash = certificate_hash(sales_invoice_doc,is_zatca_test=is_zatca_test, compliance_csid=compliance_csid)
    issuer_name, serial_number = extract_certificate_details(sales_invoice_doc, is_zatca_test=is_zatca_test, compliance_csid=compliance_csid)
    original_invoice_xml = etree.parse(
        frappe.local.site + "/private/files/zatca_invoice_final.xml"
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
    with open(frappe.local.site + "/private/files/zatca_signed_with_cert_info.xml", "wb") as file:
        original_invoice_xml.write(
            file,
            encoding="utf-8",
            xml_declaration=True,
        )
    return namespaces, signing_time
   

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
    sales_invoice_doc,
    is_zatca_test=0,
    compliance_csid=None
   
):
    """populate the ubl extension output by giving the signature values and digest values"""
    try:
        updated_invoice_xml = etree.parse(
            frappe.local.site + "/private/files/zatca_signed_with_cert_info.xml"
        )
        root3 = updated_invoice_xml.getroot()
        if is_zatca_test:

            perm_details = get_pem_compliance_details(compliance_csid)
        else:
            perm_details = get_pem_details(sales_invoice_doc)
        certificate_data_str=perm_details.get("certificate")
      
        content = certificate_data_str.strip()

       

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
            frappe.local.site + "/private/files/final_signed_invoice.xml", "wb"
        ) as file:
            updated_invoice_xml.write(file, encoding="utf-8", xml_declaration=True)

    except (ValueError, KeyError, TypeError, frappe.ValidationError) as e:
        frappe.throw(_("Error in populating UBL extension output: " + str(e)))
        return


def extract_public_key_data(sales_invoice_doc, is_zatca_test=0, compliance_csid=None):
    """extract public key"""
    if is_zatca_test:
        pem_details = get_pem_compliance_details(compliance_csid)
    else:
        pem_details = get_pem_details(sales_invoice_doc)
    # pem_details = get_pem_details(sales_invoice_doc)
    
    key_data = pem_details.get("public_key")
    # frappe.throw(str(key_data))
    return key_data


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


def tag8_publickey(sales_invoice_doc, is_zatca_test=0, compliance_csid=None):
    """tag 8 of qr from public key"""
    try:
        # create_public_key(company_abbr, source_doc)
        base64_encoded = extract_public_key_data(sales_invoice_doc,is_zatca_test=is_zatca_test, compliance_csid=compliance_csid)
        byte_data = base64.b64decode(base64_encoded)
        hex_data = binascii.hexlify(byte_data).decode("utf-8")
        chunks = [hex_data[i : i + 2] for i in range(0, len(hex_data), 2)]
        value = "".join(chunks)
        binary_data = bytes.fromhex(value)
        return binary_data
    except (ValueError, KeyError, TypeError, frappe.ValidationError) as e:
        frappe.throw(_("Error in tag 8 from public key: " + str(e)))
        return None


def tag9_signature_ecdsa(sales_invoice_doc,is_zatca_test=0,compliance_csid=None):
    """tag 9 of signature"""
    try:
        
        if is_zatca_test:

            perm_details = get_pem_compliance_details(compliance_csid)
        else:
            perm_details = get_pem_details(sales_invoice_doc)
        certificate_content=perm_details.get("certificate")
        
        # certificate_content ="MIID3jCCA4SgAwIBAgITEQAAOAPF90Ajs/xcXwABAAA4AzAKBggqhkjOPQQDAjBiMRUwEwYKCZImiZPyLGQBGRYFbG9jYWwxEzARBgoJkiaJk/IsZAEZFgNnb3YxFzAVBgoJkiaJk/IsZAEZFgdleHRnYXp0MRswGQYDVQQDExJQUlpFSU5WT0lDRVNDQTQtQ0EwHhcNMjQwMTExMDkxOTMwWhcNMjkwMTA5MDkxOTMwWjB1MQswCQYDVQQGEwJTQTEmMCQGA1UEChMdTWF4aW11bSBTcGVlZCBUZWNoIFN1cHBseSBMVEQxFjAUBgNVBAsTDVJpeWFkaCBCcmFuY2gxJjAkBgNVBAMTHVRTVC04ODY0MzExNDUtMzk5OTk5OTk5OTAwMDAzMFYwEAYHKoZIzj0CAQYFK4EEAAoDQgAEoWCKa0Sa9FIErTOv0uAkC1VIKXxU9nPpx2vlf4yhMejy8c02XJblDq7tPydo8mq0ahOMmNo8gwni7Xt1KT9UeKOCAgcwggIDMIGtBgNVHREEgaUwgaKkgZ8wgZwxOzA5BgNVBAQMMjEtVFNUfDItVFNUfDMtZWQyMmYxZDgtZTZhMi0xMTE4LTliNTgtZDlhOGYxMWU0NDVmMR8wHQYKCZImiZPyLGQBAQwPMzk5OTk5OTk5OTAwMDAzMQ0wCwYDVQQMDAQxMTAwMREwDwYDVQQaDAhSUlJEMjkyOTEaMBgGA1UEDwwRU3VwcGx5IGFjdGl2aXRpZXMwHQYDVR0OBBYEFEX+YvmmtnYoDf9BGbKo7ocTKYK1MB8GA1UdIwQYMBaAFJvKqqLtmqwskIFzVvpP2PxT+9NnMHsGCCsGAQUFBwEBBG8wbTBrBggrBgEFBQcwAoZfaHR0cDovL2FpYTQuemF0Y2EuZ292LnNhL0NlcnRFbnJvbGwvUFJaRUludm9pY2VTQ0E0LmV4dGdhenQuZ292LmxvY2FsX1BSWkVJTlZPSUNFU0NBNC1DQSgxKS5jcnQwDgYDVR0PAQH/BAQDAgeAMDwGCSsGAQQBgjcVBwQvMC0GJSsGAQQBgjcVCIGGqB2E0PsShu2dJIfO+xnTwFVmh/qlZYXZhD4CAWQCARIwHQYDVR0lBBYwFAYIKwYBBQUHAwMGCCsGAQUFBwMCMCcGCSsGAQQBgjcVCgQaMBgwCgYIKwYBBQUHAwMwCgYIKwYBBQUHAwIwCgYIKoZIzj0EAwIDSAAwRQIhALE/ichmnWXCUKUbca3yci8oqwaLvFdHVjQrveI9uqAbAiA9hC4M8jgMBADPSzmd2uiPJA6gKR3LE03U75eqbC/rXA=="
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


def generate_tlv_xml(sales_invoice_doc, is_zatca_test=0, compliance_csid=None):
    """generate xml by adding the tlv data"""
    with open(
        frappe.local.site + "/private/files/final_signed_invoice.xml", "rb"
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
    result_dict[8] = tag8_publickey(sales_invoice_doc, is_zatca_test=is_zatca_test, compliance_csid=compliance_csid)
    result_dict[9] = tag9_signature_ecdsa(sales_invoice_doc, is_zatca_test=is_zatca_test, compliance_csid=compliance_csid)
    result_dict[1] = result_dict[1].encode(
        "utf-8"
    )  # Handling Arabic company name in QR Code
    return result_dict
  

def update_qr_toxml(qrcodeb64):
    """updating the  alla values of qr to xml"""
    try:
        xml_file_path = frappe.local.site + "/private/files/final_signed_invoice.xml"
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
                _(f"QR code element not found in the XML for company")
            )
        xml_tree.write(xml_file_path, encoding="UTF-8", xml_declaration=True)
    except (ValueError, KeyError, TypeError, frappe.ValidationError) as e:
        frappe.throw(
            _(f"Error in saving TLV data to XML for company: " + str(e))
        )


def structuring_signedxml():
    """structuring the signed xml"""
    try:
        with open(
            frappe.local.site + "/private/files/final_signed_invoice.xml",
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
            frappe.local.site + "/private/files/zatca_signed_output.xml",
            "w",
            encoding="utf-8",
        ) as file:
            file.writelines(adjusted_xml_content)
        signed_xmlfile_name = (
            frappe.local.site + "/private/files/zatca_signed_output.xml"
        )
        return signed_xmlfile_name
    except (ValueError, KeyError, TypeError, frappe.ValidationError) as e:
        frappe.throw(_(" error in structuring signed xml: " + str(e)))
        return None

