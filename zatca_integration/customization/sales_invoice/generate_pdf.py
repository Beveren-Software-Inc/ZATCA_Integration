
"""
Generate PDF/A-3A compliant PDF for Frappe Sales Invoice with embedded XML
This method integrates with ERPNext Sales Invoice to create compliant PDFs
"""
import os
import tempfile
from datetime import datetime, timezone
import frappe
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import black
from reportlab.lib import colors

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Image as RLImage

import pikepdf
from pikepdf import Name, Dictionary, Array, String
from pathlib import Path

# Configuration paths
font_dir = Path(frappe.get_app_path("zatca_integration", "public", "fonts"))
template_dir = Path(frappe.get_app_path("zatca_integration", "public", "template"))
icc_ = Path(frappe.get_app_path("zatca_integration", "public"))
icc_2014 = icc_ / "sRGB2014.icc"

regular = str(font_dir / "DejaVuSans.ttf")
helvetica = str(font_dir / "Helvetica.ttf")
helvetica_bold = str(font_dir / "Helvetica-Bold.ttf")
EMBEDDED_SRGB_ICC = icc_2014
EMBEDDED_FONT_TTF = regular
template_dir = str( template_dir / "invoice.html")


# Register the font files you already placed in zatca_integration/public/fonts
pdfmetrics.registerFont(TTFont("HelveticaVCA", helvetica))        
pdfmetrics.registerFont(TTFont("HelveticaVCA-Bold", helvetica_bold))  


def find_ttf_font() -> str:
    """Return a TTF path to embed. Prefer bundled DejaVuSans.ttf; otherwise try common system fonts."""
    if os.path.isfile(EMBEDDED_FONT_TTF):
        return EMBEDDED_FONT_TTF

    candidates = [
        "/Library/Fonts/Arial.ttf",
        "/Library/Fonts/Verdana.ttf",
        "/Library/Fonts/Tahoma.ttf",
        "/Library/Fonts/Times New Roman.ttf",
        "/Library/Fonts/Courier New.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Verdana.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p

    raise FileNotFoundError(
        "No embeddable TTF font found. Place DejaVuSans.ttf in assets/ or ensure a system TTF like Arial.ttf exists."
    )


def ensure_assets():
    """Ensure required assets exist; if not, attempt to locate system equivalents."""
    _ = find_ttf_font()

    if os.path.isfile(EMBEDDED_SRGB_ICC):
        return EMBEDDED_SRGB_ICC

    candidate_paths = [
        "/System/Library/ColorSync/Profiles/sRGB Profile.icc",
        "/System/Library/ColorSync/Profiles/sRGB Profile.icm",
        "/Library/ColorSync/Profiles/sRGB Profile.icc",
        "/Library/ColorSync/Profiles/sRGB Profile.icm",
        "/System/Library/ColorSync/Profiles/sRGB IEC61966-2.1.icc",
        "/Library/ColorSync/Profiles/sRGB IEC61966-2.1.icc",
    ]

    for p in candidate_paths:
        if os.path.isfile(p):
            return p

    raise FileNotFoundError(
        "sRGB ICC profile not found. Place 'sRGB_IEC61966-2-1.icc' under assets/ or install a system sRGB profile."
    )


def generate_invoice_content(invoice_doc):
    """Generate PDF content from Sales Invoice document."""
    content_lines = [
        f"SALES INVOICE: {invoice_doc.name}",
        f"Date: {invoice_doc.posting_date}",
        f"Customer: {invoice_doc.customer_name}",
        "",
        "This is a PDF/A-3A compliant invoice with embedded XML.",
        "Editing the PDF will cause it to no longer comply with PDF/A.",
        "",
        f"Grand Total: {invoice_doc.currency} {invoice_doc.grand_total}",
    ]
    
    # Add items
    if invoice_doc.items:
        content_lines.append("")
        content_lines.append("ITEMS:")
        for item in invoice_doc.items:
            content_lines.append(f"- {item.item_code}: {item.description[:50]}...")
            content_lines.append(f"  Qty: {item.qty}, Rate: {invoice_doc.currency} {item.rate}")
    
    return content_lines

def draw_pdf_with_reportlab(temp_pdf_path: str, invoice_doc):
    """Draw Sales Invoice on canvas with complete layout matching HTML template."""
    
    # Initialize canvas and fonts
    ttf_path = find_ttf_font()
    font_name = "EmbeddedTTF"
    pdfmetrics.registerFont(TTFont(font_name, ttf_path))

    c = canvas.Canvas(temp_pdf_path, pagesize=A4, pageCompression=0)
    width, height = A4
    margin_x = 30
    margin_y = 30
    y = height - 60
    
    # ---------- DRAW INVOICE SECTIONS ----------
    y = _draw_header_section(c, invoice_doc, width, height, margin_x, y, font_name)
    y = _draw_seller_buyer_section(c, invoice_doc, width, margin_x, y, font_name)
    y = _draw_items_section(c, invoice_doc, width, height, margin_x, y, font_name)
    y = _draw_totals_section(c, invoice_doc, width, margin_x, y, font_name)
    y = _draw_tax_summary(c, invoice_doc, width, margin_x, y, font_name)
    _draw_bank_details(c, invoice_doc, width, margin_x, y, font_name)
    _draw_footer(c, width, font_name)
    
    c.save()


# def _draw_table_cell(c, x, y, w, h, text, font_name, font_size=9, align='left', bg_color=None):
#     """Helper function to draw bordered table cell with optional background color."""
#     if bg_color:
#         c.setFillColor(bg_color)
#         c.rect(x, y-h, w, h, fill=1)
#         c.setFillColor(black)
    
#     c.rect(x, y-h, w, h, fill=0)
#     c.setFont(font_name, font_size)
    
#     # Handle multi-line text
#     text_str = str(text)
#     lines = text_str.split('\n')
#     line_height = font_size + 2
    
#     for i, line in enumerate(lines):
#         text_y = y - h/2 - font_size/3 + (len(lines)/2 - i - 0.5) * line_height
        
#         if align == 'center':
#             c.drawCentredString(x + w/2, text_y, line)
#         elif align == 'right':
#             c.drawRightString(x + w - 5, text_y, line)
#         else:
#             c.drawString(x + 5, text_y, line)

def _draw_table_cell(c, x, y, w, h, text, font_name, font_size=9, align='left', bg_color=None):
    """Helper function to draw bordered table cell with optional background color."""
    if bg_color:
        c.setFillColor(bg_color)
        c.rect(x, y-h, w, h, fill=1)
        c.setFillColor(black)
    
    # CHANGE THIS: Make lines thinner
    c.setLineWidth(0.5)  # Change from default (usually 1) to 0.5 or 0.3
    c.rect(x, y-h, w, h, fill=0)
    
    # Reset line width after drawing
    c.setLineWidth(1)
    
    c.setFont(font_name, font_size)
    
    # Handle multi-line text
    text_str = str(text)
    lines = text_str.split('\n')
    line_height = font_size + 2
    
    for i, line in enumerate(lines):
        text_y = y - h/2 - font_size/3 + (len(lines)/2 - i - 0.5) * line_height
        
        if align == 'center':
            c.drawCentredString(x + w/2, text_y, line)
        elif align == 'right':
            c.drawRightString(x + w - 5, text_y, line)
        else:
            c.drawString(x + 5, text_y, line)

def add_letterhead(c, doc, page_width, page_height, top_margin=20):
    """
    Adds letterhead (image or HTML) directly to the canvas.
    Returns new y position below the letterhead.
    """
    letterhead = None

    # Pick letterhead
    if getattr(doc, "letter_head", None):
        letterhead = frappe.get_doc("Letter Head", doc.letter_head)
    else:
        lh = frappe.get_all("Letter Head", filters={"is_default": 1}, fields=["name"], limit=1)
        if lh:
            letterhead = frappe.get_doc("Letter Head", lh[0].name)

    if not letterhead:
        return page_height - top_margin  # nothing drawn, return safe y

    y_after = page_height - top_margin

    # --- Image ---
    if letterhead.image:
        file_url = letterhead.image
        if file_url.startswith("/files/"):
            file_path = frappe.get_site_path("public", "files", file_url.split("/files/")[1])
        else:
            file_path = frappe.get_site_path("public", file_url.lstrip("/"))

        try:
            img_height = 60
            c.drawImage(
                file_path,
                (page_width - 200) / 2,
                page_height - img_height - top_margin,
                width=200, height=img_height,
                preserveAspectRatio=True, mask="auto"
            )
            y_after = page_height - img_height - top_margin - 10
        except Exception as e:
            frappe.log_error(f"Letterhead image rendering failed: {e}", "PDF Generator")

    # --- HTML ---
    elif letterhead.content:
        try:
            styles = getSampleStyleSheet()
            style = styles["Times New Roman"]
            style.fontSize = 9
            style.leading = 12

            para = Paragraph(letterhead.content, style)
            w, h = para.wrap(page_width - 80, 100)
            para.drawOn(c, 40, page_height - h - top_margin)
            y_after = page_height - h - top_margin - 10
        except Exception as e:
            frappe.log_error(f"Letterhead HTML rendering failed: {e}", "PDF Generator")

    return y_after


        
def _draw_header_section(c, invoice_doc, width, height, margin_x, y, font_name):
    """Draw the header section including invoice details and QR code."""
    cell_height = 15
    table_width = width - 2 * margin_x
    qr_width = 80
    detail_width = table_width - qr_width
    y = add_letterhead(c, invoice_doc, width, height)
    
    # Invoice title
    c.setFont(font_name, 14)
    c.setFillColor(black)
    c.drawCentredString(width/2, y, "Tax Invoice - فاتورة ضريبية")
    y -= 30
    
    # Invoice details table (left side)
    col_widths = [70, 90, 80, 80, 70, 80]
    
    # Row data for invoice details
    delivery_note = getattr(invoice_doc.items[0], 'delivery_note', '') if invoice_doc.items else ''
    delivery_note = delivery_note if delivery_note else '-'
    supply_date = getattr(invoice_doc, 'custom_date_of_supply', '') or '-'
    
    rows_data = [
        ["Invoice No:", invoice_doc.name, "رقم الفاتورة", "Issue Date:", str(invoice_doc.posting_date), "تاريخ إصدار الفاتورة"],
        ["ZATCA Status", getattr(invoice_doc, 'custom_zatca_submit_status', ''), "حالة التخليص", "Due Date:", str(invoice_doc.due_date or ''), "تاريخ الاستحقاق"],
        ["Delivery Note:", delivery_note, "مذكرة التسليم", "Date of Supply:", supply_date, "تاريخ التوريد"]
    ]
    
    current_y = y
    for row_data in rows_data:
        for i, text in enumerate(row_data):
            align = 'right' if i in [2, 5] else 'left'
            _draw_table_cell(c, margin_x + sum(col_widths[:i]), current_y, col_widths[i], 
                            cell_height, text, font_name, 9, align)
        current_y -= cell_height
    
    # QR Code (right side)
    qr_x = width - margin_x - qr_width
    c.rect(qr_x, y - cell_height * 3, qr_width, cell_height * 3)
    
    # Draw QR code image if available
    qr_code_path = getattr(invoice_doc, 'custom_invoice_qr_code', '')
    if qr_code_path:
        try:
            # Remove '/files/' prefix if present and get the actual file path
            if qr_code_path.startswith('/files/'):
                qr_code_path = qr_code_path.replace('/files/', '')
            
            full_qr_path = frappe.utils.get_site_path('public', 'files', qr_code_path)
            
            # Draw the QR code image
            c.drawImage(full_qr_path, qr_x + 5, y - cell_height * 3 + 5, 
                    width=qr_width - 10, height=cell_height * 3 - 10, 
                    preserveAspectRatio=True, mask='auto')
        except Exception as e:
            print(f"Error loading QR code: {e}")
            # Fallback to text if image can't be loaded
            c.drawCentredString(qr_x + qr_width/2, y - cell_height * 1.5, "QR CODE")
    else:
        c.drawCentredString(qr_x + qr_width/2, y - cell_height * 1.5, "QR CODE")
    
    y = current_y - cell_height - 10
    
    # Purchase order details table
    po_table_width = detail_width
    po_col_width = po_table_width / 6
    
    # Headers
    current_y = y
    po_headers = ["Vendor Number\nرقم البائع", "PO No\nرقم طلب الشراء", "Purchase Agreement\nرقم العقد", 
                  "ASN Number\nرقم أ س ن", "Truck Request No\nرقم طلب الشاحنة", "GR\nجي آر"]
    
    for i, header in enumerate(po_headers):
        _draw_table_cell(c, margin_x + i * po_col_width, current_y, po_col_width, 
                        cell_height * 2, header, font_name, 8, 'center', colors.lightgrey)
    
    current_y -= cell_height * 2
    
    # Data row
    po_data = [
        getattr(invoice_doc, 'custom_vendor_number', '') or '-',
        invoice_doc.po_no or '-',
        getattr(invoice_doc, 'custom_purchase_agreement', '') or '-',
        getattr(invoice_doc, 'custom_asn_number', '') or '-',
        getattr(invoice_doc, 'custom_truck_request_number', '') or '-',
        invoice_doc.reference_no or '-'
    ]
    
    for i, data in enumerate(po_data):
        _draw_table_cell(c, margin_x + i * po_col_width, current_y, po_col_width, 
                        cell_height, data, font_name, 9, 'center')
    
    return current_y - cell_height - 20

import textwrap
from reportlab.pdfbase.pdfmetrics import stringWidth


def _draw_table_cell_with_wrapping(c, x, y, w, h, text, font_name, font_size=9, align='left', bg_color=None, auto_height=False):
    """Helper function to draw bordered table cell with text wrapping for long content."""
    
    # Calculate available width for text (minus padding)
    text_width = w - 10  # 5px padding on each side
    
    # Handle empty or None text
    if not text:
        text = ""
    
    text_str = str(text)
    
    # Check if text fits in one line
    if stringWidth(text_str, font_name, font_size) <= text_width:
        lines = [text_str]
    else:
        # Calculate approximate characters per line
        avg_char_width = stringWidth('A', font_name, font_size)
        chars_per_line = int(text_width / avg_char_width)
        
        # Wrap text
        lines = textwrap.wrap(text_str, width=chars_per_line)
        
        # If still too wide, force break long words
        final_lines = []
        for line in lines:
            while stringWidth(line, font_name, font_size) > text_width:
                # Find how many characters fit
                for i in range(len(line), 0, -1):
                    if stringWidth(line[:i], font_name, font_size) <= text_width:
                        final_lines.append(line[:i])
                        line = line[i:]
                        break
            if line:
                final_lines.append(line)
        lines = final_lines
    
    # Calculate required height if auto_height is True
    line_height = font_size + 2
    required_height = max(h, len(lines) * line_height + 4)  # 4px total padding
    
    # Use required height if auto_height, otherwise use provided height
    cell_height = required_height if auto_height else h
    
    # Draw background if specified
    if bg_color:
        c.setFillColor(bg_color)
        c.rect(x, y-cell_height, w, cell_height, fill=1)
        c.setFillColor(black)
    
    # Draw border
    c.setLineWidth(0.5)  # Thin border
    c.rect(x, y-cell_height, w, cell_height, fill=0)
    c.setLineWidth(1)  # Reset
    
    # Set font
    c.setFont(font_name, font_size)
    
    # Draw text lines
    for i, line in enumerate(lines):
        text_y = y - cell_height/2 - font_size/2 + (len(lines)/2 - i - 0.5) * line_height
        
        if align == 'center':
            c.drawCentredString(x + w/2, text_y, line)
        elif align == 'right':
            c.drawRightString(x + w - 5, text_y, line)
        else:
            c.drawString(x + 5, text_y, line)
    
    return cell_height  # Return actual height used


def _draw_seller_buyer_section(c, invoice_doc, width, margin_x, y, font_name):
    """Draw seller and buyer information section with text wrapping."""
    base_cell_height = 15
    seller_buyer_width = (width - 2 * margin_x) / 2
    detail_col_width = seller_buyer_width / 4
    
    # Headers
    current_y = y
    _draw_table_cell_with_wrapping(c, margin_x, current_y, seller_buyer_width/2, base_cell_height, 
                    "Seller:", font_name, 10, bg_color=colors.lightgrey)
    _draw_table_cell_with_wrapping(c, margin_x + seller_buyer_width/2, current_y, seller_buyer_width/2, base_cell_height, 
                    ":المورد", font_name, 10, 'right', colors.lightgrey)
    _draw_table_cell_with_wrapping(c, margin_x + seller_buyer_width, current_y, seller_buyer_width/2, base_cell_height, 
                    "Buyer:", font_name, 10, bg_color=colors.lightgrey)
    _draw_table_cell_with_wrapping(c, margin_x + seller_buyer_width + seller_buyer_width/2, current_y, 
                    seller_buyer_width/2, base_cell_height, ":العميل", font_name, 10, 'right', colors.lightgrey)
    
    current_y -= base_cell_height
    
    # Seller and Buyer details
    details_data = [
        ("Name:", invoice_doc.company, invoice_doc.customer_name, "الاسم"),
        ("Building No", getattr(invoice_doc, 'company_building_no', ''), getattr(invoice_doc, 'customer_building_no', ''), "رقم المبنى"),
        ("Street Name", getattr(invoice_doc, 'company_street', ''), getattr(invoice_doc, 'customer_street', ''), "اسم الشارع"),
        ("District", getattr(invoice_doc, 'company_district', ''), getattr(invoice_doc, 'customer_district', ''), "الحي"),
        ("City", getattr(invoice_doc, 'company_city', ''), getattr(invoice_doc, 'customer_city', ''), "المدينه"),
        ("Country", getattr(invoice_doc, 'company_country', 'Saudi Arabia'), getattr(invoice_doc, 'customer_country', ''), "البلد"),
        ("Postal Code", getattr(invoice_doc, 'company_pincode', ''), getattr(invoice_doc, 'customer_pincode', ''), "الرمز البريدي"),
        ("Additional No.", getattr(invoice_doc, 'company_additional_no', ''), getattr(invoice_doc, 'customer_additional_no', ''), "رقم إضافي"),
        ("VAT Number", getattr(invoice_doc, 'company_tax_id', ''), invoice_doc.tax_id or '', "الرقم الضريبي"),
        ("Other ID", getattr(invoice_doc, 'company_cr_number', ''), getattr(invoice_doc, 'customer_cr', ''), "معرف آخر")
    ]
    
    for label, seller_val, buyer_val, arabic_label in details_data:
        # Calculate the maximum height needed for this row
        max_height = base_cell_height
        
        # Check each cell content and calculate required height
        for content in [label, str(seller_val), str(buyer_val), arabic_label]:
            content_width = detail_col_width - 10  # minus padding
            if stringWidth(str(content), font_name, 9) > content_width:
                # Calculate lines needed
                avg_char_width = stringWidth('A', font_name, 9)
                chars_per_line = int(content_width / avg_char_width)
                lines_needed = len(textwrap.wrap(str(content), width=chars_per_line))
                content_height = lines_needed * 11 + 4  # 9px font + 2px spacing + 4px padding
                max_height = max(max_height, content_height)
        
        # Draw seller side
        _draw_table_cell_with_wrapping(c, margin_x, current_y, detail_col_width, max_height, 
                        label, font_name, 9)
        _draw_table_cell_with_wrapping(c, margin_x + detail_col_width, current_y, detail_col_width, max_height, 
                        str(seller_val), font_name, 9)
        _draw_table_cell_with_wrapping(c, margin_x + detail_col_width * 2, current_y, detail_col_width, max_height, 
                        str(seller_val), font_name, 9, 'right')
        _draw_table_cell_with_wrapping(c, margin_x + detail_col_width * 3, current_y, detail_col_width, max_height, 
                        arabic_label, font_name, 9, 'right')
        
        # Draw buyer side
        _draw_table_cell_with_wrapping(c, margin_x + seller_buyer_width, current_y, detail_col_width, max_height, 
                        label, font_name, 9)
        _draw_table_cell_with_wrapping(c, margin_x + seller_buyer_width + detail_col_width, current_y, detail_col_width, max_height, 
                        str(buyer_val), font_name, 9)
        _draw_table_cell_with_wrapping(c, margin_x + seller_buyer_width + detail_col_width * 2, current_y, detail_col_width, max_height, 
                        str(buyer_val), font_name, 9, 'right')
        _draw_table_cell_with_wrapping(c, margin_x + seller_buyer_width + detail_col_width * 3, current_y, detail_col_width, max_height, 
                        arabic_label, font_name, 9, 'right')
        
        current_y -= max_height
    
    return current_y - 20


def _draw_items_section(c, invoice_doc, width, height, margin_x, y, font_name):
    """Draw items table section."""
    cell_height = 15
    items_table_width = width - 2 * margin_x
    item_col_widths = [60, 180, 70, 60, 90, 80, 120]  # Adjusted widths to fit properly
    
    # Headers
    current_y = y
    item_headers = [
        "PO Item\nبند طلب شراء",
        "Nature of goods or services\nتفاصيل السلع او الخدمات",
        "Unit Price\nسعر الوحدة",
        "Quantity\nالكمية",
        "Taxable Amount\nالمبلغ الخاضع للضريبة",
        "Tax Amount\nمبلغ الضريبة",
        "Subtotal (Incl. VAT)\nالمجموع شامل الضريبة"
    ]
    
    for i, header in enumerate(item_headers):
        _draw_table_cell(c, margin_x + sum(item_col_widths[:i]), current_y, item_col_widths[i], 
                        cell_height * 2, header, font_name, 8, 'center', colors.lightgrey)
    
    current_y -= cell_height * 2
    
    # Items data
    if invoice_doc.items:
        # Check if all items are the same
        first_item = invoice_doc.items[0]
        same_item = all(item.item_code == first_item.item_code for item in invoice_doc.items)
        
        if same_item:
            # Consolidate same items
            total_qty = sum(item.qty for item in invoice_doc.items)
            total_amount = sum(item.amount for item in invoice_doc.items)
            
            item_data = [
                getattr(first_item, 'line_item', ''),
                f"{first_item.item_code}\n{first_item.item_name}\n{first_item.description}",
                f"{first_item.rate:.2f} {invoice_doc.currency}",
                f"{total_qty:.0f}\n{first_item.uom}",
                f"{total_amount:.2f} {invoice_doc.currency}",
                f"{invoice_doc.total_taxes_and_charges:.2f} {invoice_doc.currency}\n15%",
                f"{invoice_doc.grand_total:.2f} {invoice_doc.currency}"
            ]
            
            for i, data in enumerate(item_data):
                align = 'right' if i > 1 else 'left'
                _draw_table_cell(c, margin_x + sum(item_col_widths[:i]), current_y, 
                                item_col_widths[i], cell_height * 2, data, font_name, 8, align)
            
            current_y -= cell_height * 2
        else:
            # Show individual items
            for item in invoice_doc.items:
                if current_y < 150:  # Check for page break
                    c.showPage()
                    current_y = height - 100
                
                item_data = [
                    getattr(item, 'line_item', ''),
                    f"{item.item_code}\n{item.item_name}\n{item.description}",
                    f"{item.rate:.2f} {invoice_doc.currency}",
                    f"{item.qty}\n{item.uom}",
                    f"{item.amount:.2f} {invoice_doc.currency}",
                    f"{invoice_doc.total_taxes_and_charges:.2f} {invoice_doc.currency}\n15%",
                    f"{invoice_doc.grand_total:.2f} {invoice_doc.currency}"
                ]
                
                for i, data in enumerate(item_data):
                    align = 'right' if i > 1 else 'left'
                    _draw_table_cell(c, margin_x + sum(item_col_widths[:i]), current_y, 
                                    item_col_widths[i], cell_height * 2, data, font_name, 8, align)
                
                current_y -= cell_height * 2
    
    return current_y - 20


def _draw_totals_section(c, invoice_doc, width, margin_x, y, font_name):
    """Draw totals section."""
    cell_height = 15
    totals_width = width - 2 * margin_x
    
    # Total amounts header
    current_y = y
    _draw_table_cell(c, margin_x, current_y, totals_width/2, cell_height, 
                    "Total Amounts:", font_name, 10, bg_color=colors.lightgrey)
    _draw_table_cell(c, margin_x + totals_width/2, current_y, totals_width/2, cell_height, 
                    ":اجمالي المبالغ", font_name, 10, 'right', colors.lightgrey)
    
    current_y -= cell_height
    
    # Totals data
    totals_data = [
        ("Total Taxable Amount (Excluding VAT)", "الاجمالي الخاضع للضريبة  (غير شامل ضريبة القيمة المضافة)", f"{invoice_doc.net_total:.2f} {invoice_doc.currency}"),
        ("Total VAT", "مجموع ضريبة القيمة المضافة", f"{invoice_doc.total_taxes_and_charges:.2f} {invoice_doc.currency}"),
        ("Total Amount Due", "اجمالي المبلغ المستحق", f"{invoice_doc.grand_total:.2f} {invoice_doc.currency}"),
        ("Total In Words", "", invoice_doc.in_words or "")
    ]
    
    for english, arabic, amount in totals_data:
        _draw_table_cell(c, margin_x, current_y, totals_width/4, cell_height, "", font_name, 9)
        _draw_table_cell(c, margin_x + totals_width/4, current_y, totals_width/4, cell_height, english, font_name, 9)
        _draw_table_cell(c, margin_x + totals_width/2, current_y, totals_width/4, cell_height, arabic, font_name, 9, 'right')
        _draw_table_cell(c, margin_x + 3*totals_width/4, current_y, totals_width/4, cell_height, amount, font_name, 9, 'right')
        current_y -= cell_height
    
    return current_y - 20


def _draw_tax_summary(c, invoice_doc, width, margin_x, y, font_name):
    """Draw tax summary section."""
    cell_height = 15
    totals_width = width - 2 * margin_x
    conversion_rate = getattr(invoice_doc, 'conversion_rate', 1)
    
    # Tax summary header
    current_y = y
    _draw_table_cell(c, margin_x, current_y, totals_width, cell_height, 
                    f"Tax Summary (1 {invoice_doc.currency} = {conversion_rate} SAR)", 
                    font_name, 10, bg_color=colors.lightgrey)
    current_y -= cell_height
    
    # Tax table headers
    tax_col_widths = [totals_width/2, totals_width/4, totals_width/4]
    tax_headers = ["Tax Details", "Taxable Amount(SAR)", "Tax Amount(SAR)"]
    
    for i, header in enumerate(tax_headers):
        align = 'left' if i == 0 else 'right'
        _draw_table_cell(c, margin_x + sum(tax_col_widths[:i]), current_y, tax_col_widths[i], 
                        cell_height, header, font_name, 9, align, colors.lightgrey)
    
    current_y -= cell_height
    
    # Tax data
    base_net_total = getattr(invoice_doc, 'base_net_total', invoice_doc.net_total * conversion_rate)
    base_tax_amount = getattr(invoice_doc, 'base_total_taxes_and_charges', invoice_doc.total_taxes_and_charges * conversion_rate)
    
    tax_data = [
        getattr(invoice_doc, 'taxes_and_charges', 'VAT 15%'),
        f"{base_net_total:.2f}",
        f"{base_tax_amount:.2f}"
    ]
    
    for i, data in enumerate(tax_data):
        align = 'left' if i == 0 else 'right'
        _draw_table_cell(c, margin_x + sum(tax_col_widths[:i]), current_y, tax_col_widths[i], 
                        cell_height, data, font_name, 9, align)
    
    return current_y - cell_height - 20


def _draw_bank_details(c, invoice_doc, width, margin_x, y, font_name):
    """Draw bank details section."""
    cell_height = 15
    totals_width = width - 2 * margin_x
    
    # Bank details header
    current_y = y
    _draw_table_cell(c, margin_x, current_y, totals_width/2, cell_height, 
                    "Bank Details (USD)", font_name, 10, bg_color=colors.lightgrey)
    _draw_table_cell(c, margin_x + totals_width/2, current_y, totals_width/2, cell_height, 
                    "التفاصيل المصرفية", font_name, 10, 'right', colors.lightgrey)
    
    current_y -= cell_height
    
    # Bank details data
    bank_details = [
        ("Account Name", "اسم الحساب المصرفي", "Renewable Energy Petrochemicals Factory Co Ltd", "شركة مصنع مواد الطاقة المتجددة للبتروكيماويات المحدودة"),
        ("Bank Name", "اسم البنك", "Banque Saudi Fransi", "البنك السعودي الفرنسي"),
        ("IBAN", "رقم الآيبان", "SA56 5500 0000 0995 4870 0220", "SA56 5500 0000 0995 4870 0220"),
        ("Swift Code", "رمز السويفت", "BSFRSARIXXX", "BSFRSARIXXX")
    ]
    
    bank_col_width = totals_width / 4
    
    for english_label, arabic_label, english_value, arabic_value in bank_details:
        _draw_table_cell(c, margin_x, current_y, bank_col_width, cell_height, 
                        english_label, font_name, 9, bg_color=colors.white)
        _draw_table_cell(c, margin_x + bank_col_width, current_y, bank_col_width, cell_height, 
                        english_value, font_name, 9, 'center')
        _draw_table_cell(c, margin_x + 2*bank_col_width, current_y, bank_col_width, cell_height, 
                        arabic_value, font_name, 9, 'center')
        _draw_table_cell(c, margin_x + 3*bank_col_width, current_y, bank_col_width, cell_height, 
                        arabic_label, font_name, 9, 'right', colors.white)
        current_y -= cell_height


def _draw_footer(c, width, font_name):
    """Draw footer section."""
    c.setFont(font_name, 8)
    c.drawCentredString(width/2, 30, "This is a PDF/A-3A compliant invoice with embedded XML")
    

def build_xmp_metadata(invoice_doc) -> bytes:
    """Create XMP packet for PDF/A-3A with invoice info."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    xmp = f'''<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/">
      <dc:format>application/pdf</dc:format>
      <dc:title>
        <rdf:Alt>
          <rdf:li xml:lang="x-default">Sales Invoice {invoice_doc.name}</rdf:li>
        </rdf:Alt>
      </dc:title>
      <dc:creator>
        <rdf:Seq>
          <rdf:li>ERPNext ZATCA Integration</rdf:li>
        </rdf:Seq>
      </dc:creator>
    </rdf:Description>

    <rdf:Description xmlns:xmp="http://ns.adobe.com/xap/1.0/">
      <xmp:CreateDate>{now}</xmp:CreateDate>
      <xmp:ModifyDate>{now}</xmp:ModifyDate>
      <xmp:MetadataDate>{now}</xmp:MetadataDate>
      <xmp:CreatorTool>ERPNext ZATCA Integration</xmp:CreatorTool>
    </rdf:Description>

    <rdf:Description xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/">
        <pdfaid:part>3</pdfaid:part>
        <pdfaid:conformance>A</pdfaid:conformance>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>'''
    return xmp.encode("utf-8")


def finalize_pdfa(temp_pdf_path: str, final_pdf_path: str, icc_path: str, xml_path: str, invoice_doc):
    """Inject OutputIntent and XMP per PDF/A-3A, ensure no encryption and proper Catalog flags."""
    with pikepdf.open(temp_pdf_path, allow_overwriting_input=True) as pdf:
        if pdf.is_encrypted:
            raise RuntimeError("PDF must not be encrypted for PDF/A")

        # Create and attach XMP metadata
        xmp_bytes = build_xmp_metadata(invoice_doc)
        metadata_stream = pdf.make_stream(xmp_bytes)
        metadata_stream['/Subtype'] = Name('/XML')
        metadata_stream['/Type'] = Name('/Metadata')
        pdf.Root['/Metadata'] = metadata_stream

        # OutputIntent with sRGB IEC61966-2.1
        with open(icc_path, "rb") as f:
            icc_bytes = f.read()
        icc_stream = pdf.make_stream(icc_bytes)
        icc_stream['/N'] = 3

        oi = Dictionary({
            '/Type': Name('/OutputIntent'),
            '/S': Name('/GTS_PDFA1'),
            '/OutputConditionIdentifier': "sRGB",
            '/OutputCondition': "sRGB IEC61966-2.1",
            '/Info': "sRGB IEC61966-2.1",
            '/DestOutputProfile': icc_stream,
        })

        pdf.Root['/OutputIntents'] = Array([oi])
        pdf.Root['/Trapped'] = Name('/False')

        # PDF/A-3A tagging requirements
        pdf.Root['/Lang'] = String('en-US')
        pdf.Root['/MarkInfo'] = Dictionary({'/Marked': True})

        # Ensure page has StructParents
        pages = pdf.Root['/Pages']
        first_page = pages['/Kids'][0]
        if not first_page.is_indirect:
            first_page = pdf.make_indirect(first_page)
        first_page['/StructParents'] = 0

        # Build minimal StructTreeRoot
        parent_tree = Dictionary({'/Nums': Array()})
        struct_tree_root = Dictionary({
            '/Type': Name('/StructTreeRoot'),
            '/ParentTree': parent_tree,
            '/ParentTreeNextKey': 1,
            '/RoleMap': Dictionary()
        })

        struct_tree_root_ind = pdf.make_indirect(struct_tree_root)
        pdf.Root['/StructTreeRoot'] = struct_tree_root_ind

        # ViewerPreferences
        vp = pdf.Root.get('/ViewerPreferences', Dictionary())
        vp['/DisplayDocTitle'] = True
        pdf.Root['/ViewerPreferences'] = vp

        # Embed XML file
        if xml_path and os.path.isfile(xml_path):
            with open(xml_path, "rb") as xf:
                xml_bytes = xf.read()

            ef_stream = pdf.make_stream(xml_bytes)
            ef_stream["/Type"] = Name("/EmbeddedFile")
            ef_stream["/Subtype"] = Name('/application/xml')
            
            mod_date = datetime.now(timezone.utc).strftime("D:%Y%m%d%H%M%SZ")
            ef_stream["/Params"] = Dictionary({
                "/Size": len(xml_bytes), 
                "/ModDate": String(mod_date)
            })

            ef_stream_ind = pdf.make_indirect(ef_stream)

            filename = 'invoice.xml'
            filespec = Dictionary({
                '/Type': Name('/Filespec'),
                '/F': String(filename),
                '/UF': String(filename),
                '/EF': Dictionary({'/F': ef_stream_ind, '/UF': ef_stream_ind}),
                '/Desc': String('ZATCA invoice XML'),
                '/AFRelationship': Name('/Data'),
            })

            filespec_ind = pdf.make_indirect(filespec)

            # Add to Names -> EmbeddedFiles
            names_dict = pdf.Root.get('/Names', Dictionary())
            names_dict['/EmbeddedFiles'] = Dictionary({
                '/Names': Array([String(filename), filespec_ind])
            })
            pdf.Root['/Names'] = names_dict

            # Add to AF array
            af_array = Array([filespec_ind])
            pdf.Root['/AF'] = af_array

        try:
            from pikepdf import PdfVersion
            pdf.save(final_pdf_path, linearize=False, min_version=PdfVersion.v1_7)
        except Exception:
            pdf.save(final_pdf_path, linearize=False)


@frappe.whitelist()
def zatca_embed_qr_in_pdf(invoice_name):
    """
    Generate PDF/A-3A compliant PDF for Sales Invoice with embedded XML.
    This method is whitelisted and can be called from the frontend.
    """
    try:
        # Validate invoice exists
        if not frappe.db.exists("Sales Invoice", invoice_name):
            frappe.throw(f"Sales Invoice {invoice_name} does not exist")

        # Get invoice document
        invoice_doc = frappe.get_doc("Sales Invoice", invoice_name)
        
        # Check if custom_invoice_xml field exists and has value
        if not hasattr(invoice_doc, 'custom_invoice_xml') or not invoice_doc.custom_invoice_xml:
            frappe.throw("No XML file path found in custom_invoice_xml field")

        xml_filename = os.path.basename(invoice_doc.custom_invoice_xml)

        # Find XML file in attachments
        attachments = frappe.get_all(
            "File", 
            filters={"attached_to_name": invoice_name}, 
            fields=["file_name", "file_url"]
        )
        
        xml_file = None
        for attachment in attachments:
            if attachment.file_name == xml_filename:
                xml_file = os.path.join(
                    frappe.local.site_path, "public", "files", attachment.file_name
                )
                break

        if not xml_file or not os.path.isfile(xml_file):
            frappe.throw(f"XML file {xml_filename} not found in attachments")

        # Ensure assets exist
        icc_path = ensure_assets()

        # Create temporary PDF
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_pdf:
            temp_pdf_path = temp_pdf.name

        try:
            # Generate base PDF
            draw_pdf_with_reportlab(temp_pdf_path, invoice_doc)

            # Create final PDF with embedded XML
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as final_pdf:
                final_pdf_path = final_pdf.name

            finalize_pdfa(temp_pdf_path, final_pdf_path, icc_path, xml_file, invoice_doc)

            # Read the generated PDF
            with open(final_pdf_path, 'rb') as f:
                pdf_content = f.read()

            # Create File document in ERPNext
            pdf_filename = f"{invoice_name}_PDFA3.pdf"
            
            # Check if file already exists
            existing_file = frappe.db.exists("File", {
                "attached_to_name": invoice_name,
                "file_name": pdf_filename
            })
            
            if existing_file:
                # Update existing file
                file_doc = frappe.get_doc("File", existing_file)
                file_doc.content = pdf_content
                file_doc.save()
            else:
                # Create new file
                file_doc = frappe.get_doc({
                    "doctype": "File",
                    "file_name": pdf_filename,
                    "attached_to_doctype": "Sales Invoice",
                    "attached_to_name": invoice_name,
                    "content": pdf_content,
                    "is_private": 0,
                })
                file_doc.insert()

            frappe.db.commit()
            
            return {
                "status": "success",
                "message":file_doc.file_url,
                "file_url": file_doc.file_url,
                "file_name": pdf_filename
            }

        finally:
            # Clean up temporary files
            if os.path.exists(temp_pdf_path):
                os.remove(temp_pdf_path)
            if os.path.exists(final_pdf_path):
                os.remove(final_pdf_path)

    except Exception as e:
        frappe.log_error(f"Error generating PDF/A-3: {str(e)}")
        frappe.throw(f"Failed to generate PDF/A-3: {str(e)}")


@frappe.whitelist()
def test_pdfa3_assets():
    """Test method to check if required assets are available."""
    try:
        icc_path = ensure_assets()
        font_path = find_ttf_font()
        
        return {
            "status": "success",
            "icc_profile": icc_path,
            "font_file": font_path,
            "message": "All required assets are available"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }