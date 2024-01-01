

import datetime
import uuid
import frappe
from frappe.model.document import Document
import time

def generate_compliance_standard_debit_note(invoiceNumber, seller, buyer, originalinvoiceNumber, originalinvoiceDeliveryDate, previousInvoiceHash):
    
    # Global Unique Identifier
    uniqueInvoiceIdentifier = str(uuid.uuid4())
    # Counter Value, once used cannot be used even for same invoice
    invoiceCounterValue  = int(time.time())

    # Invoice Date and Time
    invoice_date = datetime.date.today().strftime("%Y-%m-%d")
    invoice_time = datetime.datetime.now().strftime("%H:%M:%S")

    standard_debit_note_xml = frappe.render_template("zatca_integration/templates/zatca/clearence/Standard_Debit_Note.xml", {
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

def generate_compliance_standard_credit_note(invoiceNumber, seller, buyer, originalinvoiceNumber, originalinvoiceDeliveryDate, previousInvoiceHash):
    
    # Global Unique Identifier
    uniqueInvoiceIdentifier = str(uuid.uuid4())
    # Counter Value, once used cannot be used even for same invoice
    invoiceCounterValue  = int(time.time())

    # Invoice Date and Time
    invoice_date = datetime.date.today().strftime("%Y-%m-%d")
    invoice_time = datetime.datetime.now().strftime("%H:%M:%S")

    standard_credit_note_xml = frappe.render_template("zatca_integration/templates/zatca/clearence/Standard_Credit_Note.xml", {
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

def generate_compliance_standard_invoice(invoiceNumber, seller, buyer, previousInvoiceHash):
    
    # Global Unique Identifier
    uniqueInvoiceIdentifier = str(uuid.uuid4())
    # Counter Value, once used cannot be used even for same invoice
    invoiceCounterValue  = int(time.time())

    # Invoice Date and Time
    invoice_date = datetime.date.today().strftime("%Y-%m-%d")
    invoice_time = datetime.datetime.now().strftime("%H:%M:%S")

    # Invoice Delivery Date
    invoiceDeliveryDate = (datetime.date.today() + datetime.timedelta(days=10)).strftime("%Y-%m-%d")

    standard_invoice_xml = frappe.render_template("zatca_integration/templates/zatca/clearence/Standard_Invoice.xml", {
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
