


import hashlib
import uuid
import base64
import frappe
import json
from lxml import etree
from frappe.model.document import Document


def generate_invoice_xml(customer, supplier, line_items):
    
    # Get ZATCA Settings and ZATCA Environment
    zatca_settings = frappe.get_doc("Zatca Settings", 'Zatca Settings')
    zatca_environment = frappe.get_doc("Zatca Environment", zatca_settings.zatca_environment)

    # Generate a UUID 
    generated_uuid = str(uuid.uuid4())

    standard_invoice_xml = frappe.render_template("zatca_integration/templates/invoice/Standard_Invoice.xml", {
        "uuid": generated_uuid,
        "zatca_settings": zatca_settings,
        "zatca_environment": zatca_environment,
    })
    return generated_uuid, standard_invoice_xml

def generate_compliance_invoice_xml():
    # TODO To create a proper XML Customer and Supplier
    customer = {
        "name": "CUST-00001",
        "customer_name": "Test Customer",
        "customer_address": "Test Address",
        "customer_vat_number": "123456789",
        "customer_phone_number": "123456789",
        "customer_email": "test@gmail.com"
    }
    supplier = {
        "name": "COMP-00001",
        "supplier_name": "Test Supplier",
        "supplier_address": "Test Address",
        "supplier_vat_number": "123456789",
        "supplier_phone_number": "123456789",
        "supplier_email": "test@gmail.com"
    }
    line_items = [
        {
            "name": "ITEM-00001",
            "item_name": "Test Item",
            "item_description": "Test Item Description",
            "item_quantity": "1",
            "item_unit_price": "100",
            "item_total_price": "100",
            "item_vat_rate": "5",
            "item_vat_amount": "5",
            "item_total_amount": "105"
        }
    ]
    return generate_invoice_xml(customer, supplier, line_items)

