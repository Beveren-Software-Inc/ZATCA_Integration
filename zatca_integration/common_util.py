import frappe
import base64
import requests

def validate_sales_invoice(doc, method):
    if not doc.taxes_and_charges:
        frappe.throw("Sales Taxes and Charges Template must be provided.")

def validate_pos_invoice(doc, method):
    if doc.is_pos == 1:
        doc.custom_delivery_date = doc.posting_date

def generate_clearance_request(url, clientId, clientSecret, invoice):
    url = url + 'generateClearanceRequest'
    # Set the headers
    headers = {
        'clientId': clientId,
        'clientSecret': clientSecret,
        'Content-Type': 'application/json'
    }

    # Encode the string into bytes, then encode it using base64
    data = {
        'invoice': encode_invoice(invoice)
    }

    try:
        # Make the POST request
        response = requests.post(url, headers=headers, json=data)
        response_json = response.json()
    except requests.exceptions.JSONDecodeError:
        frappe.throw("Error in generating clearance request from backend")

    return response_json

def generate_reporting_request(url, clientId, clientSecret, privateKey, pemCertificate, invoice):
    url = url + 'generateReportingRequest'
    # Set the headers
    headers = {
        'clientId': clientId,
        'clientSecret': clientSecret,
        'privateKey': privateKey,
        'pemCertificate': pemCertificate,
        'Content-Type': 'application/json'
    }

    # Encode the string into bytes, then encode it using base64
    data = {
        'invoice': encode_invoice(invoice)
    }

    try:
        # Make the POST request
        response = requests.post(url, headers=headers, json=data)
        response_json = response.json()
    except requests.exceptions.JSONDecodeError:
        frappe.throw("Error in generating reporting request from backend")

    return response_json

def encode_invoice(invoice):
    input_bytes = invoice.encode('utf-8')
    encoded_bytes = base64.b64encode(input_bytes)
    encoded_string = encoded_bytes.decode('utf-8')
    return encoded_string

def decode_invoice(encoded_invoice):
    encoded_bytes = encoded_invoice.encode('utf-8')
    decoded_bytes = base64.b64decode(encoded_bytes)
    decoded_string = decoded_bytes.decode('utf-8')
    return decoded_string

def get_buyer_information(customer_name): 
    customer = frappe.get_doc("Customer", customer_name)
    country_code = get_country_code(customer.custom_country)

    if customer.customer_type == "Company":
        address = frappe.get_doc("Address", customer.customer_primary_address)
        if not address:
            frappe.throw("Customer must have a primary address")

        # Either VAT or Registration Scheme and Registration Number are required
        if not customer.custom_vat_number and not customer.custom_registration_scheme:
            frappe.throw("Either VAT Number or Registration Scheme and Registration Number are required for Company")
        if not customer.custom_vat_number and not customer.custom_registration_number:
            frappe.throw("Either VAT Number or Registration Scheme and Registration Number are required for Company ")
        
        # ZATCA Address Validation
        # Address Line 1 is required
        if not address.address_line1:
            frappe.throw("Street Name is required for Company type customer")

        # Building Number is required
        # Building Number must be 4 digits if country_code is SA
        if not address.address_line2:
            frappe.throw("Building Number is required for Company type customer")
        if country_code == "SA" and len(address.address_line2) != 4:
            frappe.throw("Building Number must be 4 digits for Company type customer in Saudi Arabia")

        # City Subdivision Name is required
        if not address.city:
            frappe.throw("City Subdivision Name is required for Company type customer")

        # City Name is required
        if not address.county:
            frappe.throw("City Name is required for Company type customer")

        # Postal Zone is required
        # Postal Zone must be 5 digits if country_code is SA
        if not address.pincode:
            frappe.throw("Postal Zone is required for Company type customer")
        if country_code == "SA" and len(address.pincode) != 5:
            frappe.throw("Postal Zone must be 5 digits for Company type customer in Saudi Arabia")
    
        full_address = f"{address.address_line2}, {address.address_line1},\n"
        full_address += f"{address.city},\n"
        full_address += f"{address.county},\n"
        full_address += f"{address.pincode}, {country_code}"
    
        return {
            "organizationName": customer.customer_name,
            "vatNumber": customer.custom_vat_number,
            "registrationScheme": get_registration_scheme_code(customer.custom_registration_scheme),
            "registrationNumber": customer.custom_registration_number,
            "streetName": address.address_line1,
            "buildingNumber": address.address_line2,
            "citySubdivisionName": address.city,
            "cityName": address.county,
            "postalZone": address.pincode,
            "countryCode": country_code,
            "full_address": full_address
        }
    elif customer.customer_type == "Individual":
        return {
            "organizationName": customer.customer_name
        }
    else:
        frappe.throw("Invalid Customer Type")

def get_seller_information(csr_settings):

    full_address = f"{csr_settings.building_number}, {csr_settings.street_name},\n"
    full_address += f"{csr_settings.city_subdivision_name},\n"
    full_address += f"{csr_settings.city_name},\n"
    full_address += f"{csr_settings.postal_zone}, {csr_settings.csrcountryname}"

    return {
        "organizationName": csr_settings.csrorganizationname,
        "vatNumber": csr_settings.csrorganizationidentifier,
        "streetName": csr_settings.street_name,
        "buildingNumber": csr_settings.building_number,
        "citySubdivisionName": csr_settings.city_subdivision_name,
        "cityName": csr_settings.city_name,
        "postalZone": csr_settings.postal_zone,
        "countryCode": csr_settings.csrcountryname,
        "full_address": full_address,
        "registrationScheme": get_registration_scheme_code(csr_settings.registration_scheme),
        "registrationNumber": csr_settings.registration_number
    }

def get_country_code(country_name):
    country_code = frappe.get_value("Country", filters={"name": country_name}, fieldname="code")
    if country_code:
        return country_code.upper()
    else:
        frappe.throw("Invalid Country Name")

def get_registration_scheme_code(registration_scheme):
    # If the registration_scheme is empty, return an empty string
    if registration_scheme is None or registration_scheme == "":
        return ""
    # Find the start and end indices of the parentheses
    start = registration_scheme.find('(')
    end = registration_scheme.find(')')

    # Extract and return the text inside the parentheses
    if start != -1 and end != -1:
        return registration_scheme[start + 1:end]
    else:
        frappe.throw("Invalid Registration Scheme")