

import datetime
import uuid
import frappe
from frappe.model.document import Document
import time
import frappe

def generate_debit_note_xml(invoiceType, invoiceNumber, seller, buyer, originalinvoiceNumber, originalinvoiceDeliveryDate, previousInvoiceHash):
    
    # Global Unique Identifier
    uniqueInvoiceIdentifier = str(uuid.uuid4())
    # Counter Value, once used cannot be used even for same invoice
    invoiceCounterValue  = int(time.time())

    # Invoice Date and Time
    invoice_date = datetime.date.today().strftime("%Y-%m-%d")
    invoice_time = datetime.datetime.now().strftime("%H:%M:%S")

    if invoiceType == "standard":
        template_file = "zatca_integration/templates/zatca/compliance/Standard_Debit_Note.xml"
    elif invoiceType == "simplified":
        template_file = "zatca_integration/templates/zatca/compliance/Simplified_Debit_Note.xml"
    else:
        frappe.throw("Invalid Invoice Type")


    standard_debit_note_xml = frappe.render_template(template_file, {
        "originalinvoiceNumber": originalinvoiceNumber,
        "previousInvoiceHash": previousInvoiceHash,
        "invoiceNumber": invoiceNumber,
        "uniqueInvoiceIdentifier": uniqueInvoiceIdentifier,
        "invoiceCounterValue": invoiceCounterValue,
        "invoice_date": invoice_date,
        "invoice_time": invoice_time,
        "seller": seller,
        "buyer": buyer,
        "invoiceDeliveryDate": originalinvoiceDeliveryDate,
    })
    standard_debit_note = {
        "invoiceNumber": invoiceNumber,
        "uniqueInvoiceIdentifier": uniqueInvoiceIdentifier,
        "invoiceCounterValue": invoiceCounterValue,
        "invoiceDeliveryDate": originalinvoiceDeliveryDate,
        "xml": standard_debit_note_xml,
    }
    return standard_debit_note

def generate_credit_note_xml(invoiceType, invoiceNumber, seller, buyer, originalinvoiceNumber, originalinvoiceDeliveryDate, previousInvoiceHash):
    
    # Global Unique Identifier
    uniqueInvoiceIdentifier = str(uuid.uuid4())
    # Counter Value, once used cannot be used even for same invoice
    invoiceCounterValue  = int(time.time())

    # Invoice Date and Time
    invoice_date = datetime.date.today().strftime("%Y-%m-%d")
    invoice_time = datetime.datetime.now().strftime("%H:%M:%S")

    if invoiceType == "standard":
        template_file = "zatca_integration/templates/zatca/compliance/Standard_Credit_Note.xml"
    elif invoiceType == "simplified":
        template_file = "zatca_integration/templates/zatca/compliance/Simplified_Credit_Note.xml"
    else:
        frappe.throw("Invalid Invoice Type")

    standard_credit_note_xml = frappe.render_template(template_file, {
        "originalinvoiceNumber": originalinvoiceNumber,
        "previousInvoiceHash": previousInvoiceHash,
        "invoiceNumber": invoiceNumber,
        "uniqueInvoiceIdentifier": uniqueInvoiceIdentifier,
        "invoiceCounterValue": invoiceCounterValue,
        "invoice_date": invoice_date,
        "invoice_time": invoice_time,
        "seller": seller,
        "buyer": buyer,
        "invoiceDeliveryDate": originalinvoiceDeliveryDate,
    })
    standard_credit_note = {
        "invoiceNumber": invoiceNumber,
        "uniqueInvoiceIdentifier": uniqueInvoiceIdentifier,
        "invoiceCounterValue": invoiceCounterValue,
        "invoiceDeliveryDate": originalinvoiceDeliveryDate,
        "xml": standard_credit_note_xml,
    }
    return standard_credit_note

def generate_tax_invoice_xml(invoiceType, invoiceNumber, seller, buyer, previousInvoiceHash):
    
    # Global Unique Identifier
    uniqueInvoiceIdentifier = str(uuid.uuid4())
    # Counter Value, once used cannot be used even for same invoice
    invoiceCounterValue  = int(time.time())

    # Invoice Date and Time
    invoice_date = datetime.date.today().strftime("%Y-%m-%d")
    invoice_time = datetime.datetime.now().strftime("%H:%M:%S")

    # Invoice Delivery Date
    invoiceDeliveryDate = (datetime.date.today() + datetime.timedelta(days=10)).strftime("%Y-%m-%d")

    if invoiceType == "standard":
        template_file = "zatca_integration/templates/zatca/compliance/Standard_Invoice.xml"
    elif invoiceType == "simplified":
        template_file = "zatca_integration/templates/zatca/compliance/Simplified_Invoice.xml"
    else:
        frappe.throw("Invalid Invoice Type")

    standard_invoice_xml = frappe.render_template(template_file, {
        "previousInvoiceHash": previousInvoiceHash,
        "invoiceNumber": invoiceNumber,
        "uniqueInvoiceIdentifier": uniqueInvoiceIdentifier,
        "invoiceCounterValue": invoiceCounterValue,
        "invoice_date": invoice_date,
        "invoice_time": invoice_time,
        "seller": seller,
        "buyer": buyer,
        "invoiceDeliveryDate": invoiceDeliveryDate,
    })
    standard_invoice = {
        "invoiceNumber": invoiceNumber,
        "uniqueInvoiceIdentifier": uniqueInvoiceIdentifier,
        "invoiceCounterValue": invoiceCounterValue,
        "invoiceDeliveryDate": invoiceDeliveryDate,
        "xml": standard_invoice_xml,
    }
    return standard_invoice
