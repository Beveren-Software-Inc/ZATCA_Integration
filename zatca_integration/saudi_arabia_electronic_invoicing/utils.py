import base64
from lxml import etree
from frappe import _
import frappe
from cryptography import x509
from cryptography.hazmat._oid import NameOID
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.bindings._rust import ObjectIdentifier
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import ec
import asn1


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
    
