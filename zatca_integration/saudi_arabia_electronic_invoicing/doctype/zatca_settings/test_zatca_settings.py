# Copyright (c) 2026, Beveren Software and Contributors
# See license.txt

# import frappe
# `frappe.tests.utils` rather than `frappe.tests`, because the app is tested on
# Frappe version-15 in CI, where the test base class is only exported there.
from frappe.tests.utils import FrappeTestCase

# On FrappeTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]


class TestZatcaSettings(FrappeTestCase):
    """
    Integration tests for ZatcaSettings.
    Use this class for testing interactions between multiple components.
    """

    pass
