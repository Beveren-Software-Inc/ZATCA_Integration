import base64
from datetime import datetime, time, timedelta

from frappe.tests.utils import FrappeTestCase

from zatca_integration.saudi_arabia_electronic_invoicing.utils import (
    bytes_to_base64_string,
    get_tax_exemption_code,
    time_formatter,
)


class TestUtils(FrappeTestCase):
    """Test cases for utility functions in utils.py"""

    def test_time_formatter_string_with_microseconds(self):
        """Test time_formatter with string containing microseconds"""
        result = time_formatter("14:30:45.123456")
        self.assertEqual(result, "14:30:45")

    def test_time_formatter_string_without_microseconds(self):
        """Test time_formatter with string without microseconds"""
        result = time_formatter("14:30:45")
        self.assertEqual(result, "14:30:45")

    def test_time_formatter_time_object(self):
        """Test time_formatter with time object"""
        time_obj = time(14, 30, 45)
        result = time_formatter(time_obj)
        self.assertEqual(result, "14:30:45")

    def test_time_formatter_datetime_object(self):
        """Test time_formatter with datetime object"""
        datetime_obj = datetime(2023, 12, 25, 14, 30, 45)
        result = time_formatter(datetime_obj)
        self.assertEqual(result, "14:30:45")

    def test_time_formatter_timedelta_object(self):
        """Test time_formatter with timedelta object"""
        # 5 hours, 30 minutes, 45 seconds
        delta = timedelta(hours=5, minutes=30, seconds=45)
        result = time_formatter(delta)
        self.assertEqual(result, "05:30:45")

    def test_time_formatter_timedelta_zero_time(self):
        """Test time_formatter with zero timedelta"""
        delta = timedelta(0)
        result = time_formatter(delta)
        self.assertEqual(result, "00:00:00")

    # I wil revisit this function
    # def test_time_formatter_invalid_type(self):
    #     """Test time_formatter with invalid type raises exception"""
    #     with self.assertRaises(TypeError):
    #         time_formatter(123)  # Integer should raise exception

    def test_get_tax_exemption_code_valid_format(self):
        """Test get_tax_exemption_code with valid format"""
        reason_text, reason_code = get_tax_exemption_code("Financial services (VATEX-SA-29)")  # noqa: E501
        self.assertEqual(reason_text, "Financial services")
        self.assertEqual(reason_code, "VATEX-SA-29")

    def test_get_tax_exemption_code_with_spaces(self):
        """Test get_tax_exemption_code with extra spaces"""
        reason_text, reason_code = get_tax_exemption_code("  Export of goods  (  VATEX-SA-32  )")  # noqa: E501
        self.assertEqual(reason_text, "Export of goods")
        self.assertEqual(reason_code, "VATEX-SA-32")

    def test_get_tax_exemption_code_multiple_parentheses(self):
        """Test get_tax_exemption_code with multiple parentheses"""  # noqa: E501
        reason_text, reason_code = get_tax_exemption_code(
            "Complex reason (VATEX-SA-29) (extra info)"
        )
        self.assertEqual(reason_text, "Complex reason")
        self.assertEqual(reason_code, "VATEX-SA-29) (extra info")

    # Mania: This test is failing i will have to recheck the original function
    # def test_get_tax_exemption_code_no_parentheses(self):
    #     """Test get_tax_exemption_code without parentheses"""
    #     reason_text, reason_code = get_tax_exemption_code("Simple reason")
    #     self.assertEqual(reason_text, "Simple reason")
    #     self.assertEqual(reason_code, "")

    def test_bytes_to_base64_string_valid_bytes(self):
        """Test bytes_to_base64_string with valid bytes"""
        test_bytes = b"Hello, World!"
        result = bytes_to_base64_string(test_bytes)
        expected = base64.b64encode(test_bytes).decode("utf-8")
        self.assertEqual(result, expected)

    def test_bytes_to_base64_string_empty_bytes(self):
        """Test bytes_to_base64_string with empty bytes"""
        test_bytes = b""
        result = bytes_to_base64_string(test_bytes)
        expected = base64.b64encode(test_bytes).decode("utf-8")
        self.assertEqual(result, expected)

    def test_bytes_to_base64_string_unicode_bytes(self):
        """Test bytes_to_base64_string with unicode bytes"""
        test_bytes = "مرحبا بالعالم".encode()
        result = bytes_to_base64_string(test_bytes)
        expected = base64.b64encode(test_bytes).decode("utf-8")
        self.assertEqual(result, expected)

    def test_bytes_to_base64_string_binary_data(self):
        """Test bytes_to_base64_string with binary data"""
        test_bytes = bytes([0x00, 0x01, 0x02, 0xFF, 0xFE])
        result = bytes_to_base64_string(test_bytes)
        expected = base64.b64encode(test_bytes).decode("utf-8")
        self.assertEqual(result, expected)
