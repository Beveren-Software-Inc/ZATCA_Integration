

import datetime
import uuid
import frappe
from frappe.model.document import Document
import time


def generate_compliance_standard_invoice():
    
    # Get ZATCA Settings and ZATCA Environment
    zatca_settings = frappe.get_doc("Zatca Settings", 'Zatca Settings')

    # Get ZATCA Compliance CSID


    # Invoice Number
    invoiceNumber  = "INV-00001"
    # Global Unique Identifier
    uniqueInvoiceIdentifier = str(uuid.uuid4())
    # Counter Value, once used cannot be used even for same invoice
    invoiceCounterValue  = int(time.time() * 1000)

    invoice_date = datetime.date.today().strftime("%Y-%m-%d")
    invoice_time = datetime.datetime.now().strftime("%H:%M:%S")

    # Seller Information
    seller = get_seller_information(zatca_settings)

    # Buyer Information
    zatca_compliance_csid = frappe.get_doc("Zatca Compliance CSID", "Zatca Compliance CSID")
    test_buyer = frappe.get_doc("Customer", zatca_compliance_csid.buyer) 
    buyer = get_buyer_information(frappe.get_doc("Customer", test_buyer) )

    # Invoice Delivery Date
    invoiceDeliveryDate = (datetime.date.today() + datetime.timedelta(days=10)).strftime("%Y-%m-%d")

    standard_invoice_xml = frappe.render_template("zatca_integration/templates/zatca/clearence/Standard_Invoice.xml", {
        "invoiceNumber": invoiceNumber,
        "uniqueInvoiceIdentifier": uniqueInvoiceIdentifier,
        "invoiceCounterValue": invoiceCounterValue,
        "invoice_date": invoice_date,
        "invoice_time": invoice_time,
        "seller": seller,
        "buyer": buyer,
        "invoiceDeliveryDate": invoiceDeliveryDate,
    })
    return uniqueInvoiceIdentifier, standard_invoice_xml

def get_seller_information(zatca_settings):
    return {
        "registrationScheme": zatca_settings.registration_scheme,
        "registrationNumber": zatca_settings.registration_number,
        "streetName": zatca_settings.street_name,
        "buildingNumber": zatca_settings.building_number,
        "citySubdivisionName": zatca_settings.city_subdivision_name,
        "cityName": zatca_settings.city_name,
        "postalZone": zatca_settings.postal_zone,
        "countryCode": zatca_settings.csrcountryname,
        "vatNumber": zatca_settings.csrorganizationidentifier,
        "organizationName": zatca_settings.csrorganizationname
    }

def get_buyer_information(customer):
    return {
        "streetName": customer.custom_street_name,
        "buildingNumber":  customer.custom_building_number,
        "citySubdivisionName":  customer.custom_city_subdivision_name,
        "cityName":  customer.custom_city_name,
        "postalZone":  customer.custom_postal_zone,
        "countryCode":  customer.custom_country_code,
        "vatNumber":  customer.custom_vat_or_group_vat_registration_number,
        "organizationName":  customer.custom_organization_name
    }

