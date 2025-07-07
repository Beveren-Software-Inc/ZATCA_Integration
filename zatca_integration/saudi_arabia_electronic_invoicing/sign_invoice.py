import hashlib
import base64
import binascii
from datetime import datetime
# import xml.etree.ElementTree as etree
from lxml import etree  # ✅ Use lxml for canonicalization and exclusive=True
from lxml.builder import ElementMaker
from frappe import _
import lxml.etree as MyTree
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import ec
from frappe.utils.file_manager import save_file
import frappe
from frappe.utils import get_site_path

from cryptography.hazmat.primitives.serialization import load_der_private_key
from cryptography.hazmat.backends import default_backend
import base64
from zatca_integration.saudi_arabia_electronic_invoicing.utils import get_prod_csid, update_invoice
from zatca_integration.saudi_arabia_electronic_invoicing.data.create_xml import prepare_invoice_payload, save_xml_to_erpnext_file
import re

E = ElementMaker(
    namespace="http://uri.etsi.org/01903/v1.3.2#",
    nsmap={
        "xades": "http://uri.etsi.org/01903/v1.3.2#",
        "ds": "http://www.w3.org/2000/09/xmldsig#"
    }
)

DS = ElementMaker(namespace="http://www.w3.org/2000/09/xmldsig#", nsmap=None)

class ZATCAInvoiceSigner:
    def __init__(self, private_key_str, certificate_str, public_key_str=None):
        self.private_key = self._load_private_key_from_string(private_key_str)
        self.certificate = self._load_certificate_from_string(certificate_str)
        self.public_key = base64.b64decode(public_key_str) if public_key_str else None
        self.certificate_data = certificate_str

        if public_key_str:
                self.public_key = serialization.load_der_public_key(
                    base64.b64decode(public_key_str),
                    backend=default_backend()
                )
        else:
                self.public_key = self.certificate.public_key()
                
    def _load_private_key_from_string(self, base64_str):
        try:
            key_bytes = base64.b64decode(base64_str)
            return load_der_private_key(key_bytes, password=None, backend=default_backend())
        except Exception as e:
            raise Exception(f"Failed to load private key from string: {str(e)}")

    def _load_certificate_from_string(self, base64_str):
        try:
            cert_bytes = base64.b64decode(base64_str)
            return x509.load_der_x509_certificate(cert_bytes, default_backend())
        except Exception as e:
            raise Exception(f"Failed to load certificate from string: {str(e)}")
        
    def removetags(self, finalzatcaxml):
        """remove the unwanted tags from created xml"""
        try:
            # Convert str to bytes to avoid XML declaration error
            xml_file = MyTree.fromstring(finalzatcaxml.encode("utf-8"))

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
                <xsl:template match="//*[local-name()='Invoice']//*[local-name()='UBLExtensions']"/>
                <xsl:template match="//*[local-name()='AdditionalDocumentReference'][cbc:ID[normalize-space(text()) = 'QR']]"/>
                <xsl:template match="//*[local-name()='Invoice']/*[local-name()='Signature']"/>
                </xsl:stylesheet>"""
            )

            transform = MyTree.XSLT(xsl_file.getroottree())
            transformed_xml = transform(xml_file.getroottree())
            return transformed_xml

        except (ValueError, KeyError, TypeError, frappe.ValidationError) as e:
            frappe.throw(_("error occurred while removing tags: " + str(e)))
            return None

   
    def canonicalize_xml(self, tag_removed_xml):
        # frappe.throw(str(tag_removed_xml))
        """canonicalisation of the xml"""
        try:
            canonical_xml = etree.tostring(tag_removed_xml, method="c14n").decode()
            return canonical_xml
        except (ValueError, KeyError, TypeError, frappe.ValidationError) as e:
            frappe.throw(_("error occurred in canonicalise xml " + str(e)))
            return None
        # """Canonicalisation of the xml"""
        # try:
        #     if isinstance(tag_removed_xml, MyTree._XSLTResultTree):
        #         xml_string = str(tag_removed_xml)
        #     else:
        #         xml_string = MyTree.tostring(tag_removed_xml, encoding='utf-8').decode('utf-8')
            
        #     # Parse with lxml and canonicalize with simple c14n
        #     parser = MyTree.XMLParser(remove_blank_text=True)
        #     xml_tree = MyTree.fromstring(xml_string.encode('utf-8'), parser)
        #     canonical_xml = MyTree.tostring(xml_tree, method="c14n").decode('utf-8')
        #     frappe.throw(str(canonical_xml))
        #     return canonical_xml
        # except Exception as e:
        #     raise Exception(f"Error occurred in canonicalise xml: {str(e)}")

    def getinvoicehash(self, canonicalized_xml):
        try:
            hash_object = hashlib.sha256(canonicalized_xml.encode())
            hash_hex = hash_object.hexdigest()
            #frappe.throw(str(hash_hex))
            hash_base64 = base64.b64encode(bytes.fromhex(hash_hex)).decode("utf-8")
            return hash_hex, hash_base64
        except Exception as e:
            raise Exception(f"Error occurred while invoice hash: {str(e)}")

    def digital_signature(self, hash_hex):
        """Find digital signature of xml"""
        try:
            hash_bytes = bytes.fromhex(hash_hex)
            signature = self.private_key.sign(hash_bytes, ec.ECDSA(hashes.SHA256()))
            encoded_signature = base64.b64encode(signature).decode()
            # frappe.throw(str(encoded_signature))
            return encoded_signature
        except Exception as e:
            raise Exception(f"Error in digital signature: {str(e)}")

    def extract_certificate_details(self):
        """Extracting the certificate details from the certificate"""
        try:
            formatted_issuer_name = self.certificate.issuer.rfc4514_string()
            issuer_name = ", ".join([x.strip() for x in formatted_issuer_name.split(",")])
            serial_number = self.certificate.serial_number
            return issuer_name, serial_number
        except Exception as e:
            raise Exception(f"Error in extracting certificate details: {str(e)}")

    def certificate_hash(self):
        """Find the certificate hash and returning the value"""
        """Alternative certificate hash method"""
        try:
            certificate_data = self.certificate_data.strip()
            
            # Get the public key from certificate
            # Calculate the SHA-256 hash of the certificate data
            certificate_data_bytes = certificate_data.encode("utf-8")
            sha256_hash = hashlib.sha256(certificate_data_bytes).hexdigest()
            # Encode the hash in base64
            base64_encoded_hash = base64.b64encode(sha256_hash.encode("utf-8")).decode(
                "utf-8"
            )
            return base64_encoded_hash
        except Exception as e:
            raise Exception(f"Error in obtaining certificate hash: {str(e)}")

    def extract_public_key_data(self):
        """Extract public key data"""
        try:
            public_key_pem = self.public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            ).decode('utf-8')
            
            lines = public_key_pem.splitlines()
            key_data = "".join(lines[1:-1])
            key_data = key_data.replace("-----BEGIN PUBLIC KEY-----", "").replace(
                "-----END PUBLIC KEY-----", ""
            )
            key_data = key_data.replace(" ", "").replace("\n", "")
            return key_data
        except Exception as e:
            raise Exception(f"Error in extracting public key data: {str(e)}")

    
    def create_ubl_signature_template(self):
        return """
<sig:UBLDocumentSignatures
    xmlns:sig="urn:oasis:names:specification:ubl:schema:xsd:CommonSignatureComponents-2"
    xmlns:sac="urn:oasis:names:specification:ubl:schema:xsd:SignatureAggregateComponents-2"
    xmlns:sbc="urn:oasis:names:specification:ubl:schema:xsd:SignatureBasicComponents-2"
    xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <sac:SignatureInformation>
    <cbc:ID>urn:oasis:names:specification:ubl:signature:1</cbc:ID>
    <sbc:ReferencedSignatureID>urn:oasis:names:specification:ubl:signature:Invoice</sbc:ReferencedSignatureID>
    <ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#" Id="signature">
      <ds:SignedInfo>
        <ds:CanonicalizationMethod Algorithm="http://www.w3.org/2006/12/xml-c14n11"/>
        <ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#ecdsa-sha256"/>
        <ds:Reference Id="invoiceSignedData" URI="">
          <ds:Transforms>
            <ds:Transform Algorithm="http://www.w3.org/TR/1999/REC-xpath-19991116">
              <ds:XPath>not(//ancestor-or-self::ext:UBLExtensions)</ds:XPath>
            </ds:Transform>
            <ds:Transform Algorithm="http://www.w3.org/TR/1999/REC-xpath-19991116">
              <ds:XPath>not(//ancestor-or-self::cac:Signature)</ds:XPath>
            </ds:Transform>
            <ds:Transform Algorithm="http://www.w3.org/TR/1999/REC-xpath-19991116">
              <ds:XPath>not(//ancestor-or-self::cac:AdditionalDocumentReference[cbc:ID='QR'])</ds:XPath>
            </ds:Transform>
            <ds:Transform Algorithm="http://www.w3.org/2006/12/xml-c14n11"/>
          </ds:Transforms>
          <ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
          <ds:DigestValue></ds:DigestValue>
        </ds:Reference>
        <ds:Reference Type="http://www.w3.org/2000/09/xmldsig#SignatureProperties" URI="#xadesSignedProperties">
          <ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
          <ds:DigestValue></ds:DigestValue>
        </ds:Reference>
      </ds:SignedInfo>
      <ds:SignatureValue></ds:SignatureValue>
      <ds:KeyInfo>
        <ds:X509Data>
          <ds:X509Certificate></ds:X509Certificate>
        </ds:X509Data>
      </ds:KeyInfo>
      <ds:Object>
        <xades:QualifyingProperties xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" Target="signature">
          <xades:SignedProperties Id="xadesSignedProperties">
            <xades:SignedSignatureProperties>
              <xades:SigningTime></xades:SigningTime>
              <xades:SigningCertificate>
                <xades:Cert>
                  <xades:CertDigest>
                    <ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
                    <ds:DigestValue></ds:DigestValue>
                  </xades:CertDigest>
                  <xades:IssuerSerial>
                    <ds:X509IssuerName></ds:X509IssuerName>
                    <ds:X509SerialNumber></ds:X509SerialNumber>
                  </xades:IssuerSerial>
                </xades:Cert>
              </xades:SigningCertificate>
            </xades:SignedSignatureProperties>
          </xades:SignedProperties>
        </xades:QualifyingProperties>
      </ds:Object>
    </ds:Signature>
  </sac:SignatureInformation>
</sig:UBLDocumentSignatures>
""".strip()




    def add_signature_to_xml(self, xml_content):
        """Add signature template to XML"""
        try:
            root = etree.fromstring(xml_content.encode('utf-8'))
            
            # Find UBLExtensions
            namespaces = {
                'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2'
            }
            
            ubl_extensions = root.find('.//ext:UBLExtensions', namespaces)
            if ubl_extensions is not None:
                # Find the UBLExtension with signature
                for ubl_extension in ubl_extensions.findall('ext:UBLExtension', namespaces):
                    extension_content = ubl_extension.find('ext:ExtensionContent', namespaces)
                    if extension_content is not None:
                        # Clear existing content and add signature template
                        extension_content.clear()
                        signature_xml = self.create_ubl_signature_template()
                        signature_element = etree.fromstring(signature_xml)
                        extension_content.append(signature_element)
                        break
            
            return etree.tostring(root, encoding='utf-8', xml_declaration=True).decode('utf-8')
        except Exception as e:
            raise Exception(f"Error adding signature to XML: {str(e)}")


    def populate_signature_values(self, xml_content, encoded_signature, signed_properties_base64, invoice_hash_base64):
        """Populate the signature values in XML"""
        try:
            # Use lxml for XPath support
            root = MyTree.fromstring(xml_content.encode('utf-8'))
            # print("Hello+++++====", str(root))
            # frappe.throw(str(root))
            namespaces = {
                "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
                "sig": "urn:oasis:names:specification:ubl:schema:xsd:CommonSignatureComponents-2",
                "sac": "urn:oasis:names:specification:ubl:schema:xsd:SignatureAggregateComponents-2",
                "xades": "http://uri.etsi.org/01903/v1.3.2#",
                "ds": "http://www.w3.org/2000/09/xmldsig#",
            }

            # Get certificate in PEM format and clean it
            certificate_pem = self.certificate.public_bytes(
                encoding=serialization.Encoding.PEM
            ).decode('utf-8')
            cert_lines = certificate_pem.strip().split('\n')
            cert_content = ''.join(cert_lines[1:-1])  # Remove headers

            # Update the essential signature values
            xpath_signvalue = "ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/sig:UBLDocumentSignatures/sac:SignatureInformation/ds:Signature/ds:SignatureValue"
            xpath_x509certi = "ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/sig:UBLDocumentSignatures/sac:SignatureInformation/ds:Signature/ds:KeyInfo/ds:X509Data/ds:X509Certificate"
            xpath_digvalue = "ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/sig:UBLDocumentSignatures/sac:SignatureInformation/ds:Signature/ds:SignedInfo/ds:Reference[@URI='#xadesSignedProperties']/ds:DigestValue"
            xpath_digvalue2 = "ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/sig:UBLDocumentSignatures/sac:SignatureInformation/ds:Signature/ds:SignedInfo/ds:Reference[@Id='invoiceSignedData']/ds:DigestValue"

            # Update the core elements 
            signvalue = root.find(xpath_signvalue, namespaces)
            x509certificate = root.find(xpath_x509certi, namespaces)
            digestvalue = root.find(xpath_digvalue, namespaces)
            digestvalue2 = root.find(xpath_digvalue2, namespaces)

            if None in [signvalue, x509certificate, digestvalue, digestvalue2]:
                raise Exception("Could not find all required signature elements in XML")

            signvalue.text = encoded_signature
            x509certificate.text = cert_content
            digestvalue.text = signed_properties_base64
            digestvalue2.text = invoice_hash_base64
            # frappe.throw(str(signed_properties_base64))
            # Additional signed properties (your custom additions)
            issuer_name, serial_number = self.extract_certificate_details()
            encoded_certificate_hash = self.certificate_hash()
            signing_time = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
            # frappe.throw(str(signing_time))
            xpath_signtime = "ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/sig:UBLDocumentSignatures/sac:SignatureInformation/ds:Signature/ds:Object/xades:QualifyingProperties/xades:SignedProperties/xades:SignedSignatureProperties/xades:SigningTime"
            xpath_cert_digest = "ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/sig:UBLDocumentSignatures/sac:SignatureInformation/ds:Signature/ds:Object/xades:QualifyingProperties/xades:SignedProperties/xades:SignedSignatureProperties/xades:SigningCertificate/xades:Cert/xades:CertDigest/ds:DigestValue"
            xpath_issuer_name = "ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/sig:UBLDocumentSignatures/sac:SignatureInformation/ds:Signature/ds:Object/xades:QualifyingProperties/xades:SignedProperties/xades:SignedSignatureProperties/xades:SigningCertificate/xades:Cert/xades:IssuerSerial/ds:X509IssuerName"
            xpath_serial_num = "ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/sig:UBLDocumentSignatures/sac:SignatureInformation/ds:Signature/ds:Object/xades:QualifyingProperties/xades:SignedProperties/xades:SignedSignatureProperties/xades:SigningCertificate/xades:Cert/xades:IssuerSerial/ds:X509SerialNumber"

            # Update additional elements
            additional_elements = [
                (xpath_signtime, signing_time),
                (xpath_cert_digest, encoded_certificate_hash),
                (xpath_issuer_name, issuer_name),
                (xpath_serial_num, str(serial_number))
            ]

            for xpath, value in additional_elements:
                element = root.find(xpath, namespaces)
                if element is not None:
                    element.text = value

            # Clean up namespace declarations
            signed_props = root.find('.//xades:SignedProperties', namespaces)
            if signed_props is not None and 'Id' in signed_props.attrib:
                id_value = signed_props.attrib.pop('Id')
                signed_props.attrib.clear()
                signed_props.set('Id', id_value)

                for elem in signed_props.iter():
                    if elem.tag.startswith('{http://www.w3.org/2000/09/xmldsig#}'):
                        if '{http://www.w3.org/2000/xmlns/}ds' in elem.attrib:
                            del elem.attrib['{http://www.w3.org/2000/xmlns/}ds']

            # Return just the XML string (not a tuple)
            return MyTree.tostring(root, encoding='utf-8', xml_declaration=True).decode('utf-8')

        except Exception as e:
            raise Exception(f"Error in populating signature values: {str(e)}")

    def get_tlv_for_value(self, tag_num, tag_value):
        """Get the tlv data value for the qr"""
        try:
            tag_num_buf = bytes([tag_num])
            if tag_value is None:
                raise Exception(f"Error: Tag value for tag number {tag_num} is None")
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
        except Exception as e:
            raise Exception(f"Error in getting the tlv data value: {str(e)}")

    def tag8_public_key(self):
        """Tag 8 of qr from public key"""
        try:
            base64_encoded = self.extract_public_key_data()
            byte_data = base64.b64decode(base64_encoded)
            hex_data = binascii.hexlify(byte_data).decode("utf-8")
            chunks = [hex_data[i : i + 2] for i in range(0, len(hex_data), 2)]
            value = "".join(chunks)
            binary_data = bytes.fromhex(value)
            return binary_data
        except Exception as e:
            raise Exception(f"Error in tag 8 from public key: {str(e)}")

    def tag9_signature_ecdsa(self):
        """Tag 9 of signature"""
        try:
            signature = self.certificate.signature
            signature_hex = "".join("{:02x}".format(byte) for byte in signature)
            signature_bytes = bytes.fromhex(signature_hex)
            return signature_bytes
        except Exception as e:
            raise Exception(f"Error in tag 9 (signature tag): {str(e)}")

    def generate_qr_code(self, xml_content):
        """Generate QR code for the invoice"""
        try:
            # Use lxml for XPath support
            root = MyTree.fromstring(xml_content.encode('utf-8'))
            namespaces = {
                "ubl": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
                "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
                "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
                "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
                "sig": "urn:oasis:names:specification:ubl:schema:xsd:CommonSignatureComponents-2",
                "sac": "urn:oasis:names:specification:ubl:schema:xsd:SignatureAggregateComponents-2",
                "ds": "http://www.w3.org/2000/09/xmldsig#",
            }

            # Extract required data for QR
            issue_date_xpath = "/ubl:Invoice/cbc:IssueDate"
            issue_time_xpath = "/ubl:Invoice/cbc:IssueTime"
            issue_date_results = root.xpath(issue_date_xpath, namespaces=namespaces)
            issue_time_results = root.xpath(issue_time_xpath, namespaces=namespaces)
            issue_date = issue_date_results[0].text.strip() if issue_date_results else "Missing Data"
            issue_time = issue_time_results[0].text.strip() if issue_time_results else "Missing Data"
            issue_date_time = issue_date + "T" + issue_time

            tags_xpaths = [
                (1, "/ubl:Invoice/cac:AccountingSupplierParty/cac:Party/cac:PartyLegalEntity/cbc:RegistrationName"),
                (2, "/ubl:Invoice/cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID"),
                (3, None),
                (4, "/ubl:Invoice/cac:LegalMonetaryTotal/cbc:TaxInclusiveAmount"),
                (5, "/ubl:Invoice/cac:TaxTotal/cbc:TaxAmount"),
                (6, "/ubl:Invoice/ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/sig:UBLDocumentSignatures/sac:SignatureInformation/ds:Signature/ds:SignedInfo/ds:Reference/ds:DigestValue"),
                (7, "/ubl:Invoice/ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/sig:UBLDocumentSignatures/sac:SignatureInformation/ds:Signature/ds:SignatureValue"),
                (8, None),
                (9, None),
            ]

            result_dict = {}
            for tag, xpath in tags_xpaths:
                if isinstance(xpath, str):
                    elements = root.xpath(xpath, namespaces=namespaces)
                    if elements:
                        value = elements[0].text if hasattr(elements[0], 'text') else str(elements[0])
                        result_dict[tag] = value
                    else:
                        result_dict[tag] = "Not found"
                else:
                    result_dict[tag] = xpath

            result_dict[3] = issue_date_time
            result_dict[8] = self.tag8_public_key()
            result_dict[9] = self.tag9_signature_ecdsa()
            result_dict[1] = result_dict[1].encode("utf-8")

            # Generate TLV data
            tlv_data = b""
            for tag in range(1, 10):
                if tag in result_dict:
                    tlv_data += self.get_tlv_for_value(tag, result_dict[tag])

            # Encode to base64
            qr_code_b64 = base64.b64encode(tlv_data).decode("utf-8")
            return qr_code_b64

        except Exception as e:
            raise Exception(f"Error in generating QR code: {str(e)}")

    def update_qr_in_xml(self, xml_content, qr_code_b64):
        """Update QR code in XML"""
        try:
            # Use lxml for XPath support
            root = MyTree.fromstring(xml_content.encode('utf-8'))
            namespaces = {
                "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
                "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
            }

            qr_code_element = root.find(
                './/cac:AdditionalDocumentReference[cbc:ID="QR"]/cac:Attachment/cbc:EmbeddedDocumentBinaryObject',
                namespaces=namespaces,
            )
            if qr_code_element is not None:
                qr_code_element.text = qr_code_b64
            else:
                print("Warning: QR code element not found in the XML")

            return MyTree.tostring(root, encoding='utf-8', xml_declaration=True).decode('utf-8')
        except Exception as e:
            raise Exception(f"Error in updating QR code in XML: {str(e)}")
        
    

    def sign_invoice(self, input_xml_path, invoice):
        try:
            # 1. Read the input XML
            with open(input_xml_path, 'r', encoding='utf-8') as f:
                xml_content = f.read()
            
            # 2. Remove unwanted tags and canonicalize
            tag_removed_xml = self.removetags(xml_content)
            # frappe.throw(str(tag_removed_xml))
            canonical_xml = self.canonicalize_xml(tag_removed_xml)
            
            # 3. Compute invoice hash
            invoice_hash_hex, invoice_hash_base64 = self.getinvoicehash(canonical_xml)
            
            # 4. Generate digital signature
            encoded_signature = self.digital_signature(invoice_hash_hex)
            
            # 5. Extract certificate details
            issuer_name, serial_number = self.extract_certificate_details()
            encoded_certificate_hash = self.certificate_hash()
            signing_time = "2025-07-06T06:05:19Z" #datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
            
            signed_properties_base64 = generate_signed_properties_hash(signing_time, issuer_name, serial_number, encoded_certificate_hash)
            # frappe.throw(str(signed_properties_base64))
            # frappe.throw(f"Time {signing_time} and encoded Hash {encoded_certificate_hash} and Issuername {issuer_name} and serialnumber {serial_number}")
            # 6. Generate signed properties hash
            
            # 7. Add signature template to XML
            xml_with_template = self.add_signature_to_xml(xml_content)
            
            # 8. Populate all signature values
            signed_xml = self.populate_signature_values(
                xml_with_template,
                encoded_signature,
                signed_properties_base64,
                invoice_hash_base64
            )
            # frappe.throw(str(signed_properties_base64))
            # 9. Generate QR code
            qr_code_b64 = self.generate_qr_code(signed_xml)
            
            # 10. Update invoice with QR code and hash
            update_invoice(invoice, qr_code_b64, invoice_hash_base64)
            
            # 11. Update XML with QR code
            final_signed_xml = self.update_qr_in_xml(signed_xml, qr_code_b64)
            
            # 12. Save the signed XML
            base_filename = f"ZATCA-Signed-{invoice.name}.xml"
            content = final_signed_xml.encode('utf-8')

            file_doc = save_file(
                base_filename,
                content,
                dt="Sales Invoice",
                dn=invoice.name,
                folder="Home/Attachments",
                is_private=1
            )
            
            return file_doc.file_url
                
        except Exception as e:
            print(f"❌ Error signing invoice: {str(e)}")
            raise

def clean_pem_key(pem_key: str, keyword: str) -> str:
    """Remove PEM headers and newlines from a key."""
    if not pem_key:
        return ""
    lines = pem_key.strip().splitlines()
    return "".join(line for line in lines if keyword not in line)


@frappe.whitelist()
def get_pem_details(invoice):
    production_csid = get_prod_csid(invoice)
    compliance_csid = frappe.get_doc("Compliance CSID", production_csid.compliance_csid)
    csr_settings = frappe.get_doc("Zatca CSR Settings", compliance_csid.csr_settings)

    private_key = clean_pem_key(csr_settings.private_key, "PRIVATE KEY")
    public_key = clean_pem_key(production_csid.public_key, "PUBLIC KEY")
    certificate = (production_csid.certificate or "").strip().replace("\n", "")

    return {
        "private_key": private_key,
        "public_key": public_key,
        "certificate": certificate
    }

@frappe.whitelist()
def create_and_sign_xml_from_invoice(invoice):
    """
    Test and sign the ZATCA unsigned invoice using local XML path
    """
    invoice = frappe.get_doc("Sales Invoice", invoice)
    xml_file_name = create_xml(invoice)
    private_key = get_pem_details(invoice).get("private_key")
    certificate_ = get_pem_details(invoice).get("certificate")
    public_key_str = get_pem_details(invoice).get("publickey")

    # Get full absolute path to input XML file
    input_path = get_site_path("private", "files", xml_file_name)

    signer = ZATCAInvoiceSigner(private_key, certificate_, public_key_str=public_key_str)

    signed_file_url = signer.sign_invoice(input_path, invoice)
    file_name = signed_file_url.rsplit("/", 1)[-1]
    return file_name
    # Show result
    # frappe.msgprint(f"✅ Signed Invoice Saved: <a href='{signed_file_url}' target='_blank'>{signed_file_url}</a>", title="ZATCA Invoice")

@frappe.whitelist()
def create_xml(invoice):
    sample_data = prepare_invoice_payload(invoice)
    file = save_xml_to_erpnext_file(sample_data, attached_to_doctype="Sales Invoice", attached_to_name=sample_data["name"])
    
    return file.file_name

def remove_ds_namespace_from_children(xml_str):
    # Remove xmlns:ds="..." from all <ds:*> except <ds:Signature>
    return re.sub(r'(<ds:(?!Signature)[^>]+) xmlns:ds="http://www.w3.org/2000/09/xmldsig#"', r'\1', xml_str)

def generate_signed_properties_hash(
    signing_time, issuer_name, serial_number, encoded_certificate_hash
):
    # signing_time = "2025-07-06T06:05:19Z"
    # encoded_certificate_hash = "ZDMwMmI0MTE1NzVjOTU2NTk4YzVlODhhYmI0ODU2NDUyNTU2YTVhYjhhMDFmN2FjYjk1YTA2OWQ0NjY2MjQ4NQ=="
    # serial_number = "379112742831380471835263969587287663520528387"
    # issuer_name = "CN=PRZEINVOICESCA4-CA, DC=extgazt, DC=gov, DC=local"
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
        # frappe.throw(f"Nop its wrong {signed_properties_base64}")
        return signed_properties_base64
    except (ValueError, KeyError, TypeError, frappe.ValidationError) as e:
        frappe.throw(_(" error in generating signed properties hash: " + str(e)))
        return None