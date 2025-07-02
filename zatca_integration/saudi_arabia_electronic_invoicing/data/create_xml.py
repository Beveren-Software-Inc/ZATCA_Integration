
import uuid
from datetime import datetime
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom
import frappe
from frappe.utils.file_manager import save_file
from frappe.utils import cint

def create_ubl_extensions(invoice_element):
    """
    Creates UBL Extensions section for digital signature placeholder.
    This section will be populated during the signing process.
    
    Args:
        invoice_element: Root invoice XML element
    """
    ubl_extensions = SubElement(invoice_element, 'ext:UBLExtensions')
    ubl_extension = SubElement(ubl_extensions, 'ext:UBLExtension')
    
    extension_uri = SubElement(ubl_extension, 'ext:ExtensionURI')
    extension_uri.text = 'urn:oasis:names:specification:ubl:dsig:enveloped:xades'
    
    extension_content = SubElement(ubl_extension, 'ext:ExtensionContent')
    
    # Signature placeholder (will be filled during signing process)
    sig_doc_signatures = SubElement(extension_content, 'sig:UBLDocumentSignatures')
    sig_doc_signatures.set('xmlns:sig', 'urn:oasis:names:specification:ubl:schema:xsd:CommonSignatureComponents-2')
    sig_doc_signatures.set('xmlns:sac', 'urn:oasis:names:specification:ubl:schema:xsd:SignatureAggregateComponents-2')
    sig_doc_signatures.set('xmlns:sbc', 'urn:oasis:names:specification:ubl:schema:xsd:SignatureBasicComponents-2')


def add_basic_invoice_info(invoice_element, invoice):
    """
    Adds basic invoice information like ID, UUID, dates, and type.
    
    Args:
        invoice_element: Root invoice XML element
        invoice: Invoice data dictionary
    """
    # Profile ID - indicates the business process context
    profile_id = SubElement(invoice_element, 'cbc:ProfileID')
    profile_id.text = invoice.get('profile_id', 'reporting:1.0')
    
    # Invoice ID - unique identifier for the invoice
    invoice_id = SubElement(invoice_element, 'cbc:ID')
    invoice_id.text = invoice.get('name', 'INV-0001')
    
    # UUID - universally unique identifier
    invoice_uuid = SubElement(invoice_element, 'cbc:UUID')
    invoice_uuid.text = invoice.get('uuid', str(uuid.uuid4()))
    
    # Issue Date - when the invoice was issued
    issue_date = SubElement(invoice_element, 'cbc:IssueDate')
    if 'posting_date' in invoice:
        issue_date.text = invoice['posting_date']
    else:
        issue_date.text = datetime.now().strftime('%Y-%m-%d')
    
    # Issue Time - time when the invoice was issued
    issue_time = SubElement(invoice_element, 'cbc:IssueTime')
    if 'posting_time' in invoice:
        issue_time.text = invoice['posting_time']
    else:
        issue_time.text = datetime.now().strftime('%H:%M:%S')
    
    # Invoice Type Code - determines if it's standard or simplified invoice
    invoice_type_code = SubElement(invoice_element, 'cbc:InvoiceTypeCode')
    if invoice.get('is_simplified_invoice', False):
        invoice_type_code.set('name', '0200000')  # Simplified Tax Invoice
    else:
        invoice_type_code.set('name', '0100000')  # Standard Tax Invoice
    invoice_type_code.text = '388'  # Tax Invoice
    
    # Currency codes
    doc_currency = SubElement(invoice_element, 'cbc:DocumentCurrencyCode')
    doc_currency.text = invoice.get('currency', 'SAR')
    
    tax_currency = SubElement(invoice_element, 'cbc:TaxCurrencyCode')
    tax_currency.text = invoice.get('currency', 'SAR')


def add_additional_document_references(invoice_element, invoice):
    """
    Adds additional document references required by ZATCA:
    - ICV (Invoice Counter Value)
    - PIH (Previous Invoice Hash)
    - QR (QR Code placeholder)
    
    Args:
        invoice_element: Root invoice XML element
        invoice: Invoice data dictionary
    """
    # ICV (Invoice Counter Value) - sequential counter for invoices
    icv_ref = SubElement(invoice_element, 'cac:AdditionalDocumentReference')
    icv_id = SubElement(icv_ref, 'cbc:ID')
    icv_id.text = 'ICV'
    icv_uuid = SubElement(icv_ref, 'cbc:UUID')
    icv_uuid.text = str(invoice.get('icv_counter', 1))
    
    # PIH (Previous Invoice Hash) - cryptographic hash of previous invoice
    pih_ref = SubElement(invoice_element, 'cac:AdditionalDocumentReference')
    pih_id = SubElement(pih_ref, 'cbc:ID')
    pih_id.text = 'PIH'
    pih_attachment = SubElement(pih_ref, 'cac:Attachment')
    pih_binary = SubElement(pih_attachment, 'cbc:EmbeddedDocumentBinaryObject')
    pih_binary.set('mimeCode', 'text/plain')
    pih_value = invoice.get('previous_invoice_hash', 'NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRkNGU5MWI0NjcyOWQ3M2EyN2ZiNTdlOQ==')
    pih_binary.text = pih_value
    
    # QR Code placeholder - will be generated after signing
    qr_ref = SubElement(invoice_element, 'cac:AdditionalDocumentReference')
    qr_id = SubElement(qr_ref, 'cbc:ID')
    qr_id.text = 'QR'
    qr_attachment = SubElement(qr_ref, 'cac:Attachment')
    qr_binary = SubElement(qr_attachment, 'cbc:EmbeddedDocumentBinaryObject')
    qr_binary.set('mimeCode', 'text/plain')
    qr_binary.text = ''  # Will be populated after signing


def add_signature_placeholder(invoice_element):
    """
    Adds signature placeholder that will be populated during the signing process.
    
    Args:
        invoice_element: Root invoice XML element
    """
    from xml.etree.ElementTree import SubElement
    
    signature = SubElement(invoice_element, 'cac:Signature')
    sig_id = SubElement(signature, 'cbc:ID')
    sig_id.text = 'urn:oasis:names:specification:ubl:signature:Invoice'
    sig_method = SubElement(signature, 'cbc:SignatureMethod')
    sig_method.text = 'urn:oasis:names:specification:ubl:dsig:enveloped:xades'



def add_supplier_party(invoice_element, invoice):
    """
    Adds supplier (seller) party information including:
    - Company identification and registration
    - Address details
    - Tax information
    - Legal entity details
    
    Args:
        invoice_element: Root invoice XML element
        invoice: Invoice data dictionary
    """
    supplier_party = SubElement(invoice_element, 'cac:AccountingSupplierParty')
    supplier = SubElement(supplier_party, 'cac:Party')
    
    # Supplier Party Identification (Company Registration Number)
    supplier_id_elem = SubElement(supplier, 'cac:PartyIdentification')
    supplier_id = SubElement(supplier_id_elem, 'cbc:ID')
    supplier_id.set('schemeID', 'CRN')
    supplier_id.text = invoice.get('company_registration', '1010010000')
    
    # Supplier Address
    supplier_address = SubElement(supplier, 'cac:PostalAddress')
    
    supplier_street = SubElement(supplier_address, 'cbc:StreetName')
    supplier_street.text = invoice.get('company_address_line1', 'Company Street')
    
    supplier_building = SubElement(supplier_address, 'cbc:BuildingNumber')
    supplier_building.text = invoice.get('company_building_number', '1234')
    
    supplier_subdivision = SubElement(supplier_address, 'cbc:CitySubdivisionName')
    supplier_subdivision.text = invoice.get('company_city_subdivision', 'District')
    
    supplier_city = SubElement(supplier_address, 'cbc:CityName')
    supplier_city.text = invoice.get('company_city', 'Riyadh')
    
    supplier_postal = SubElement(supplier_address, 'cbc:PostalZone')
    supplier_postal.text = invoice.get('company_postal_code', '12345')
    
    supplier_country = SubElement(supplier_address, 'cac:Country')
    supplier_country_code = SubElement(supplier_country, 'cbc:IdentificationCode')
    supplier_country_code.text = invoice.get('company_country', 'SA')
    
    # Supplier Tax Scheme (VAT Registration)
    supplier_tax_scheme = SubElement(supplier, 'cac:PartyTaxScheme')
    supplier_vat = SubElement(supplier_tax_scheme, 'cbc:CompanyID')
    supplier_vat.text = invoice.get('company_tax_id', '399999999900003')
    
    supplier_tax_scheme_elem = SubElement(supplier_tax_scheme, 'cac:TaxScheme')
    supplier_tax_id = SubElement(supplier_tax_scheme_elem, 'cbc:ID')
    supplier_tax_id.text = 'VAT'
    
    # Supplier Legal Entity (Company Name)
    supplier_legal = SubElement(supplier, 'cac:PartyLegalEntity')
    supplier_name = SubElement(supplier_legal, 'cbc:RegistrationName')
    supplier_name.text = invoice.get('company', 'Company Name')


def add_customer_party(invoice_element, invoice):
    """
    Adds customer (buyer) party information.
    For simplified invoices, adds minimal required fields.
    """
    customer_party = SubElement(invoice_element, 'cac:AccountingCustomerParty')
    customer = SubElement(customer_party, 'cac:Party')

    if invoice.get('is_simplified_invoice', False):
        party_name = SubElement(customer, 'cac:PartyName')
        name = SubElement(party_name, 'cbc:Name')
        name.text = invoice.get('customer_name', 'Consumer')
        return

    # Customer Address
    customer_address = SubElement(customer, 'cac:PostalAddress')
    customer_street = SubElement(customer_address, 'cbc:StreetName')
    customer_street.text = invoice.get('customer_address_line1', 'Customer Street')
    customer_building = SubElement(customer_address, 'cbc:BuildingNumber')
    customer_building.text = invoice.get('customer_building_number', '5678')
    customer_subdivision = SubElement(customer_address, 'cbc:CitySubdivisionName')
    customer_subdivision.text = invoice.get('customer_city_subdivision', 'District')
    customer_city = SubElement(customer_address, 'cbc:CityName')
    customer_city.text = invoice.get('customer_city', 'Riyadh')
    customer_postal = SubElement(customer_address, 'cbc:PostalZone')
    customer_postal.text = invoice.get('customer_postal_code', '54321')
    customer_country = SubElement(customer_address, 'cac:Country')
    customer_country_code = SubElement(customer_country, 'cbc:IdentificationCode')
    customer_country_code.text = invoice.get('customer_country', 'SA')

    # Tax details
    if invoice.get('customer_tax_id'):
        customer_tax_scheme = SubElement(customer, 'cac:PartyTaxScheme')
        customer_vat = SubElement(customer_tax_scheme, 'cbc:CompanyID')
        customer_vat.text = invoice['customer_tax_id']
        customer_tax_scheme_elem = SubElement(customer_tax_scheme, 'cac:TaxScheme')
        customer_tax_id = SubElement(customer_tax_scheme_elem, 'cbc:ID')
        customer_tax_id.text = 'VAT'

    # Legal entity name
    customer_legal = SubElement(customer, 'cac:PartyLegalEntity')
    customer_name = SubElement(customer_legal, 'cbc:RegistrationName')
    customer_name.text = invoice.get('customer_name', 'Customer Name')


def add_delivery_info(invoice_element, invoice):
    """
    Adds delivery information if applicable.
    
    Args:
        invoice_element: Root invoice XML element
        invoice: Invoice data dictionary
    """
    if invoice.get('delivery_date'):
        delivery = SubElement(invoice_element, 'cac:Delivery')
        delivery_date = SubElement(delivery, 'cbc:ActualDeliveryDate')
        delivery_date.text = invoice['delivery_date']


def add_payment_means(invoice_element, invoice):
    """
    Adds payment method information using ZATCA standard codes.
    
    Args:
        invoice_element: Root invoice XML element
        invoice: Invoice data dictionary
    """
    payment_means = SubElement(invoice_element, 'cac:PaymentMeans')
    payment_code = SubElement(payment_means, 'cbc:PaymentMeansCode')
    
    # Map payment methods to ZATCA standard codes
    payment_mapping = {
        'Cash': '10',
        'Credit Card': '48',
        'Bank Transfer': '30',
        'Check': '20'
    }
    payment_method = invoice.get('payment_method', 'Cash')
    payment_code.text = payment_mapping.get(payment_method, '10')


def add_allowance_charge(invoice_element, invoice):
    """
    Adds allowance/charge information for invoice-level discounts or charges.
    
    Args:
        invoice_element: Root invoice XML element
        invoice: Invoice data dictionary
    """
    total_discount = invoice.get('discount_amount', 0)
    
    allowance_charge = SubElement(invoice_element, 'cac:AllowanceCharge')
    charge_indicator = SubElement(allowance_charge, 'cbc:ChargeIndicator')
    charge_indicator.text = 'false'  # false = allowance (discount), true = charge
    
    allowance_reason = SubElement(allowance_charge, 'cbc:AllowanceChargeReason')
    allowance_reason.text = 'discount'
    
    allowance_amount = SubElement(allowance_charge, 'cbc:Amount')
    allowance_amount.set('currencyID', invoice.get('currency', 'SAR'))
    allowance_amount.text = f"{total_discount:.2f}"
    
    # Tax Category for Allowance
    allowance_tax_cat = SubElement(allowance_charge, 'cac:TaxCategory')
    allowance_tax_id = SubElement(allowance_tax_cat, 'cbc:ID')
    allowance_tax_id.set('schemeID', 'UN/ECE 5305')
    allowance_tax_id.set('schemeAgencyID', '6')
    allowance_tax_id.text = 'S'  # Standard rate
    
    allowance_tax_percent = SubElement(allowance_tax_cat, 'cbc:Percent')
    allowance_tax_percent.text = '15'
    
    allowance_tax_scheme = SubElement(allowance_tax_cat, 'cac:TaxScheme')
    allowance_tax_scheme_id = SubElement(allowance_tax_scheme, 'cbc:ID')
    allowance_tax_scheme_id.set('schemeID', 'UN/ECE 5153')
    allowance_tax_scheme_id.set('schemeAgencyID', '6')
    allowance_tax_scheme_id.text = 'VAT'


def add_tax_totals(invoice_element, invoice):
    """
    Adds tax total information including summary and detailed breakdown.
    ZATCA requires both summary and detailed tax totals.
    
    Args:
        invoice_element: Root invoice XML element
        invoice: Invoice data dictionary
    """
    total_tax_amount = invoice.get('total_taxes_and_charges', 0)
    net_total = invoice.get('net_total', 0)
    tax_rate = invoice.get('tax_rate', 15)
    
    # Tax Total (Summary) - Required by ZATCA
    tax_total = SubElement(invoice_element, 'cac:TaxTotal')
    tax_amount = SubElement(tax_total, 'cbc:TaxAmount')
    tax_amount.set('currencyID', invoice.get('currency', 'SAR'))
    tax_amount.text = f"{total_tax_amount:.2f}"
    
    # Tax Total (Detailed) - Required by ZATCA with subtotal breakdown
    tax_total_detailed = SubElement(invoice_element, 'cac:TaxTotal')
    tax_amount_detailed = SubElement(tax_total_detailed, 'cbc:TaxAmount')
    tax_amount_detailed.set('currencyID', invoice.get('currency', 'SAR'))
    tax_amount_detailed.text = f"{total_tax_amount:.2f}"
    
    # Tax Subtotal - breakdown by tax category
    tax_subtotal = SubElement(tax_total_detailed, 'cac:TaxSubtotal')
    
    taxable_amount = SubElement(tax_subtotal, 'cbc:TaxableAmount')
    taxable_amount.set('currencyID', invoice.get('currency', 'SAR'))
    taxable_amount.text = f"{net_total:.2f}"
    
    subtotal_tax_amount = SubElement(tax_subtotal, 'cbc:TaxAmount')
    subtotal_tax_amount.set('currencyID', invoice.get('currency', 'SAR'))
    subtotal_tax_amount.text = f"{total_tax_amount:.2f}"
    
    # Tax Category information
    tax_category = SubElement(tax_subtotal, 'cac:TaxCategory')
    tax_cat_id = SubElement(tax_category, 'cbc:ID')
    tax_cat_id.set('schemeID', 'UN/ECE 5305')
    tax_cat_id.set('schemeAgencyID', '6')
    tax_cat_id.text = 'S'  # Standard rate
    
    tax_percent = SubElement(tax_category, 'cbc:Percent')
    tax_percent.text = f"{tax_rate:.2f}"
    
    tax_scheme = SubElement(tax_category, 'cac:TaxScheme')
    tax_scheme_id = SubElement(tax_scheme, 'cbc:ID')
    tax_scheme_id.set('schemeID', 'UN/ECE 5153')
    tax_scheme_id.set('schemeAgencyID', '6')
    tax_scheme_id.text = 'VAT'


def add_legal_monetary_total(invoice_element, invoice):
    """
    Adds legal monetary total section containing all financial summaries.
    This section provides a complete financial breakdown of the invoice.
    
    Args:
        invoice_element: Root invoice XML element
        invoice: Invoice data dictionary
    """
    net_total = invoice.get('net_total', 0)
    grand_total = invoice.get('grand_total', 0)
    total_discount = invoice.get('discount_amount', 0)
    outstanding_amount = invoice.get('outstanding_amount', grand_total)
    
    legal_monetary_total = SubElement(invoice_element, 'cac:LegalMonetaryTotal')
    
    # Line Extension Amount - sum of all line amounts before tax
    line_extension_amount = SubElement(legal_monetary_total, 'cbc:LineExtensionAmount')
    line_extension_amount.set('currencyID', invoice.get('currency', 'SAR'))
    line_extension_amount.text = f"{net_total:.2f}"
    
    # Tax Exclusive Amount - total before tax
    tax_exclusive_amount = SubElement(legal_monetary_total, 'cbc:TaxExclusiveAmount')
    tax_exclusive_amount.set('currencyID', invoice.get('currency', 'SAR'))
    tax_exclusive_amount.text = f"{net_total:.2f}"
    
    # Tax Inclusive Amount - total including tax
    tax_inclusive_amount = SubElement(legal_monetary_total, 'cbc:TaxInclusiveAmount')
    tax_inclusive_amount.set('currencyID', invoice.get('currency', 'SAR'))
    tax_inclusive_amount.text = f"{grand_total:.2f}"
    
    # Allowance Total Amount - total discounts
    allowance_total_amount = SubElement(legal_monetary_total, 'cbc:AllowanceTotalAmount')
    allowance_total_amount.set('currencyID', invoice.get('currency', 'SAR'))
    allowance_total_amount.text = f"{total_discount:.2f}"
    
    # Prepaid Amount - amount already paid
    prepaid_amount = SubElement(legal_monetary_total, 'cbc:PrepaidAmount')
    prepaid_amount.set('currencyID', invoice.get('currency', 'SAR'))
    prepaid_amount.text = "0.00"
    
    # Payable Amount - amount still due
    payable_amount = SubElement(legal_monetary_total, 'cbc:PayableAmount')
    payable_amount.set('currencyID', invoice.get('currency', 'SAR'))
    payable_amount.text = f"{outstanding_amount:.2f}"


def add_invoice_lines(invoice_element, invoice):
    """
    Adds all invoice line items with their details including:
    - Item information
    - Quantities and prices
    - Tax calculations
    - Line-level discounts
    
    Args:
        invoice_element: Root invoice XML element
        invoice: Invoice data dictionary
    """
    tax_rate = invoice.get('tax_rate', 15)
    
    for idx, item in enumerate(invoice.get('items', []), 1):
        invoice_line = SubElement(invoice_element, 'cac:InvoiceLine')
        
        # Line ID - sequential line number
        line_id = SubElement(invoice_line, 'cbc:ID')
        line_id.text = str(idx)
        
        # Invoiced Quantity - quantity of items
        invoiced_quantity = SubElement(invoice_line, 'cbc:InvoicedQuantity')
        invoiced_quantity.set('unitCode', item.get('uom', 'PCE'))  # PCE = Piece
        invoiced_quantity.text = f"{item.get('qty', 1):.6f}"
        
        # Line Extension Amount - total for this line before tax
        line_extension_amount = SubElement(invoice_line, 'cbc:LineExtensionAmount')
        line_extension_amount.set('currencyID', invoice.get('currency', 'SAR'))
        line_amount = item.get('amount', 0)
        line_extension_amount.text = f"{line_amount:.2f}"
        
        # Line Tax Total - tax calculation for this line
        line_tax_total = SubElement(invoice_line, 'cac:TaxTotal')
        line_tax_amount = SubElement(line_tax_total, 'cbc:TaxAmount')
        line_tax_amount.set('currencyID', invoice.get('currency', 'SAR'))
        item_tax_amount = line_amount * (tax_rate / 100)
        line_tax_amount.text = f"{item_tax_amount:.2f}"
        
        # Rounding Amount - total including tax for this line
        line_rounding_amount = SubElement(line_tax_total, 'cbc:RoundingAmount')
        line_rounding_amount.set('currencyID', invoice.get('currency', 'SAR'))
        line_total_with_tax = line_amount + item_tax_amount
        line_rounding_amount.text = f"{line_total_with_tax:.2f}"
        
        # Item Information
        item_elem = SubElement(invoice_line, 'cac:Item')
        item_name = SubElement(item_elem, 'cbc:Name')
        item_name.text = item.get('item_name', item.get('item_code', 'Item'))
        
        # Item Tax Category
        item_tax_category = SubElement(item_elem, 'cac:ClassifiedTaxCategory')
        item_tax_id = SubElement(item_tax_category, 'cbc:ID')
        item_tax_id.text = 'S'  # Standard rate
        
        item_tax_percent = SubElement(item_tax_category, 'cbc:Percent')
        item_tax_percent.text = f"{tax_rate:.2f}"
        
        item_tax_scheme = SubElement(item_tax_category, 'cac:TaxScheme')
        item_tax_scheme_id = SubElement(item_tax_scheme, 'cbc:ID')
        item_tax_scheme_id.text = 'VAT'
        
        # Price Information
        price = SubElement(invoice_line, 'cac:Price')
        price_amount = SubElement(price, 'cbc:PriceAmount')
        price_amount.set('currencyID', invoice.get('currency', 'SAR'))
        unit_rate = item.get('rate', 0)
        price_amount.text = f"{unit_rate:.2f}"
        
        # Price Allowance/Charge (item level discount)
        item_discount = item.get('discount_amount', 0)
        if item_discount != 0:
            price_allowance = SubElement(price, 'cac:AllowanceCharge')
            price_charge_indicator = SubElement(price_allowance, 'cbc:ChargeIndicator')
            price_charge_indicator.text = 'true' if item_discount < 0 else 'false'
            
            price_allowance_reason = SubElement(price_allowance, 'cbc:AllowanceChargeReason')
            price_allowance_reason.text = 'discount'
            
            price_allowance_amount = SubElement(price_allowance, 'cbc:Amount')
            price_allowance_amount.set('currencyID', invoice.get('currency', 'SAR'))
            price_allowance_amount.text = f"{abs(item_discount):.2f}"


def create_zatca_base_xml(invoice):
    """
    Convert invoice data to ZATCA e-invoice base XML format.
    
    This is the main function that orchestrates the creation of a complete
    ZATCA-compliant XML invoice. The XML structure follows UBL 2.1 standard
    with ZATCA-specific extensions and requirements.
    
    Args:
        invoice (dict): Invoice data containing all invoice information
        
    Returns:
        str: Formatted XML string ready for ZATCA processing (before signing)
    """
    
    # Create root element with all required namespaces
    invoice_element = Element('Invoice')
    invoice_element.set('xmlns', 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2')
    invoice_element.set('xmlns:cac', 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2')
    invoice_element.set('xmlns:cbc', 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2')
    invoice_element.set('xmlns:ext', 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2')
    
    # Build XML structure using modular functions
    create_ubl_extensions(invoice_element)
    add_basic_invoice_info(invoice_element, invoice)
    add_additional_document_references(invoice_element, invoice)
    add_signature_placeholder(invoice_element)
    add_supplier_party(invoice_element, invoice)
    add_customer_party(invoice_element, invoice)
    # add_delivery_info(invoice_element, invoice)
    add_payment_means(invoice_element, invoice)
    add_allowance_charge(invoice_element, invoice)
    add_tax_totals(invoice_element, invoice)
    add_legal_monetary_total(invoice_element, invoice)
    add_invoice_lines(invoice_element, invoice)
    
    # Convert to formatted XML string
    rough_string = tostring(invoice_element, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="    ", encoding='utf-8').decode('utf-8')


def save_xml_to_erpnext_file(invoice, attached_to_doctype=None, attached_to_name=None):
    """
    Generate ZATCA base XML and save it as a File document in ERPNext.

    Args:
        invoice (dict): Invoice data for XML generation.
        attached_to_doctype (str, optional): DocType to attach the file to.
        attached_to_name (str, optional): Doc name to attach the file to.

    Returns:
        str: File URL of the saved XML document.
    """
    # Generate XML
    xml_string = create_zatca_base_xml(invoice)

    # Prepare file details
    invoice_number = invoice.get("name") or invoice.get("invoice_number") or "invoice"
    filename = f"ZATCA-Unsigned-{invoice_number}.xml"
    content = xml_string.encode("utf-8")

    # Save the file
    file_doc = save_file(
        filename,
        content,
        dt=attached_to_doctype,
        dn=attached_to_name,
        folder="Home/Attachments",
        is_private=1  # Note: must be int, not bool
    )

    return file_doc


def prepare_invoice_payload(invoice_doc):
    """Extract real data from a Sales Invoice doc for ZATCA XML generation"""
    # return {
    #     "name": invoice_doc.name,
    #     "uuid": str(uuid.uuid4()),
    #     "posting_date": str(invoice_doc.posting_date),
    #     "posting_time": str(invoice_doc.posting_time or "00:00:00"),
    #     "company": invoice_doc.company,
    #     "customer_name": invoice_doc.customer_name,
    #     "currency": invoice_doc.currency,
    #     "is_simplified_invoice": invoice_doc.get("is_simplified_invoice", False),
    #     "profile_id": "reporting:1.0",
    #     "icv_counter": cint(invoice_doc.get("icv_counter") or 1),

    #     # You can fetch this from your ZATCA metadata if needed
    #     "previous_invoice_hash": "",

    #     # Company info
    #     "company_registration": frappe.db.get_value("Company", invoice_doc.company, "tax_id"),
    #     "company_tax_id": frappe.db.get_value("Company", invoice_doc.company, "tax_id"),
    #     "company_address_line1": invoice_doc.company_address or "",
    #     "company_building_number": "123",  # Optionally fetch from Address Doctype
    #     "company_city_subdivision": "",
    #     "company_city": invoice_doc.get("company_city") or "Riyadh",
    #     "company_postal_code": "",
    #     "company_country": "SA",

    #     # Customer info
    #     "customer_tax_id": invoice_doc.get("customer_tax_id") or "",
    #     "customer_address_line1": invoice_doc.get("customer_address") or "",
    #     "customer_building_number": "",
    #     "customer_city_subdivision": "",
    #     "customer_city": "",
    #     "customer_postal_code": "",
    #     "customer_country": "SA",

    #     # Amounts
    #     "net_total": invoice_doc.net_total,
    #     "total_taxes_and_charges": invoice_doc.total_taxes_and_charges,
    #     "grand_total": invoice_doc.grand_total,
    #     "outstanding_amount": invoice_doc.outstanding_amount,
    #     "discount_amount": invoice_doc.discount_amount,
    #     "tax_rate": 15.0,  # or fetch from tax table

    #     # Payment
    #     "payment_method": invoice_doc.get("payment_method") or "Cash",
    #     "delivery_date": str(invoice_doc.get("delivery_date") or invoice_doc.posting_date),

    #     # Items
    #     "items": [
    #         {
    #             "item_code": item.item_code,
    #             "item_name": item.item_name,
    #             "qty": item.qty,
    #             "rate": item.rate,
    #             "amount": item.amount,
    #             "uom": item.uom,
    #             "discount_amount": item.discount_amount or 0.0
    #         }
    #         for item in invoice_doc.items
    #     ]
    # }

    return {
        "name": "SINV-2024-00002",
        "uuid": str(uuid.uuid4()),
        "posting_date": "2025-07-02",
        "posting_time": "09:00:00",
        "company": "Tech Solutions Company Ltd",
        "customer_name": "ABC Trading Company",
        "currency": "SAR",
        "is_simplified_invoice": True,
        "profile_id": "reporting:1.0",
        "icv_counter": 1,
        "previous_invoice_hash": "NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRkNGU5MWI0NjcyOWQ3M2EyN2ZiNTdlOQ==",

        # Company details
        "company_registration": "1010010000",
        "company_tax_id": "399999999900003",
        "company_address_line1": "King Fahd Road",
        "company_building_number": "1234",
        "company_city_subdivision": "Al-Olaya",
        "company_city": "Riyadh",
        "company_postal_code": "12345",
        "company_country": "SA",

        # Customer details (Simplified - No VAT ID)
        "customer_tax_id": "",  # Must be empty for simplified
        "customer_address_line1": "Prince Sultan Road",
        "customer_building_number": "5678",
        "customer_city_subdivision": "Al-Malaz",
        "customer_city": "Riyadh",
        "customer_postal_code": "54321",
        "customer_country": "SA",

        # Amounts
        "net_total": 1000.00,
        "total_taxes_and_charges": 150.00,
        "grand_total": 1150.00,
        "outstanding_amount": 1150.00,
        "discount_amount": 0.00,
        "tax_rate": 15.0,

        # Payment
        "payment_method": "Cash",
        "delivery_date": "2025-07-15",

        # Items
        "items": [
            {
                "item_code": "LAPTOP-001",
                "item_name": "Dell Laptop",
                "qty": 2,
                "rate": 400.00,
                "amount": 800.00,
                "uom": "Nos",
                "discount_amount": 0.00
            },
            {
                "item_code": "MOUSE-001",
                "item_name": "Wireless Mouse",
                "qty": 5,
                "rate": 40.00,
                "amount": 200.00,
                "uom": "Nos",
                "discount_amount": 0.00
            }
        ]
    }

@frappe.whitelist()
def test_the_invoice(invoice):
    invoice_doc = frappe.get_doc("Sales Invoice", invoice)
    sample_data = prepare_invoice_payload(invoice_doc)
    file = save_xml_to_erpnext_file(sample_data, attached_to_doctype="Sales Invoice", attached_to_name=sample_data["name"])
    return file.file_name
   

