import frappe
import base64
import requests

def validate_purchase_invoice(doc, method):
    if not doc.taxes_and_charges:
        frappe.throw("Purchase Taxes and Charges Template must be provided.")

def validate_sales_invoice(doc, method):
    if not doc.taxes_and_charges:
        frappe.throw("Sales Taxes and Charges Template must be provided.")


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
        frappe.throw("Error in generating invoice request from backend")

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
    
    full_address = f"{customer.custom_building_number}, {customer.custom_street_name},\n"
    full_address += f"{customer.custom_city_subdivision_name},\n"
    full_address += f"{customer.custom_city_name},\n"
    full_address += f"{customer.custom_postal_zone}, {customer.custom_country_code}"
    
    return {
        "organizationName": customer.custom_organization_name,
        "vatNumber": customer.custom_vat_number,
        "streetName": customer.custom_street_name,
        "buildingNumber": customer.custom_building_number,
        "citySubdivisionName": customer.custom_city_subdivision_name,
        "cityName": customer.custom_city_name,
        "postalZone": customer.custom_postal_zone,
        "countryCode": customer.custom_country_code,
        "full_address": full_address
    }

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

def get_registration_scheme_code(registration_scheme):
    # Find the start and end indices of the parentheses
    start = registration_scheme.find('(')
    end = registration_scheme.find(')')

    # Extract and return the text inside the parentheses
    if start != -1 and end != -1:
        return registration_scheme[start + 1:end]
    else:
        frappe.throw("Invalid Registration Scheme")