# Copyright (c) 2024, Shakir PM and contributors
# For license information, please see license.txt

import uuid

import frappe
from frappe import _
from frappe.model.document import Document

from zatca_integration.common_util import validate_ksa_vat_number
from zatca_integration.saudi_arabia_electronic_invoicing.saudi_national_address import (
    validate_zatca_city_name,
)


class ZatcaCSRSettings(Document):
    def before_save(self):
        if not self.csrserialnumber:
            self.csrserialnumber = self.generate_serial_number()

        if not isinstance(self.building_number, int) or not (1000 <= self.building_number <= 9999):
            frappe.throw(_("Building Number must be a 4-digit integer"))

        if not isinstance(self.postal_zone, int) or not (10000 <= self.postal_zone <= 99999):
            frappe.throw(_("Postal Zone must be a 5-digit integer"))

        # City Name is written as cbc:CityName on every invoice. A value outside
        # the Saudi National Address list is what ZATCA reports as "inaccurate
        # address data", so a known spelling is corrected and an unknown one is
        # refused here instead of on the invoice.
        if str(self.csrcountryname or "").strip().upper() in ("", "SA"):
            self.city_name = validate_zatca_city_name(
                self.city_name, _("Seller address (Zatca CSR Settings)"), notify=True
            )

        validate_ksa_vat_number(
            self.csrorganizationidentifier,
            field_label=_("VAT or Group VAT Registration Number"),
        )

    def generate_serial_number(self):
        serial_number = str(uuid.uuid4())
        return "1-ERPNext|2-V15|3-" + serial_number
