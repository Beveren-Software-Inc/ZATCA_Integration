
"""
Generate PDF/A-3A compliant PDF for Frappe Sales Invoice with embedded XML
This method integrates with ERPNext Sales Invoice to create compliant PDFs
"""
import os
import re
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
import textwrap
from reportlab.pdfbase.pdfmetrics import stringWidth

import pikepdf
from pikepdf import Name, Dictionary, Array, String
from pathlib import Path

# Configuration paths
font_dir = Path(frappe.get_app_path("zatca_integration", "public", "fonts"))
template_dir = Path(frappe.get_app_path("zatca_integration", "public", "template"))
icc_ = Path(frappe.get_app_path("zatca_integration", "public"))
icc_2014 = icc_ / "sRGB2014.icc"
height = A4

regular = str(font_dir / "DejaVuSans.ttf")
helvetica = str(font_dir / "Helvetica.ttf")
helvetica_bold = str(font_dir / "Helvetica-Bold.ttf")
amiri_regular = str(font_dir / "Amiri-Regular.ttf")
amiri_bold = str(font_dir / "Amiri-Bold.ttf")
cairo_regular = str(font_dir / "Cairo-Regular.ttf")
cairo_bold = str(font_dir / "Cairo-Bold.ttf")

EMBEDDED_SRGB_ICC = icc_2014
# EMBEDDED_FONT_TTF = regular
EMBEDDED_FONT_TTF = cairo_regular
template_dir = str( template_dir / "invoice.html")



# Register the font files you already placed in zatca_integration/public/fonts
pdfmetrics.registerFont(TTFont("HelveticaVCA", helvetica))        
pdfmetrics.registerFont(TTFont("HelveticaVCA-Bold", helvetica_bold))  

pdfmetrics.registerFont(TTFont("Amiri", amiri_regular))
pdfmetrics.registerFont(TTFont("Amiri-Bold", amiri_bold))

pdfmetrics.registerFont(TTFont("Cairo", cairo_regular))
pdfmetrics.registerFont(TTFont("Cairo-Bold", cairo_bold))

# Arabic text detection and processing functions
def is_arabic_text(text):
    """
    Detect if text contains Arabic characters.
    Returns True if text contains Arabic characters.
    """
    if not text:
        return False
    
    text_str = str(text)
    # Arabic Unicode ranges: 0x0600-0x06FF (Arabic), 0x0750-0x077F (Arabic Supplement)
    arabic_pattern = re.compile(r'[\u0600-\u06FF\u0750-\u077F]')
    return bool(arabic_pattern.search(text_str))


def has_mixed_content(text):
    """
    Check if text contains both Arabic and Latin characters.
    """
    if not text:
        return False
    
    text_str = str(text)
    has_arabic = is_arabic_text(text_str)
    has_latin = bool(re.search(r'[a-zA-Z]', text_str))
    
    return has_arabic and has_latin

def get_appropriate_font(text, base_font_name="EmbeddedTTF", arabic_font_name="Amiri"):
    """
    Return appropriate font name based on text content.
    """
    if is_arabic_text(text):
        # Check if Amiri font is available
        try:
            pdfmetrics.getFont(arabic_font_name)
            return arabic_font_name
        except:
            # Fallback to base font if Amiri not available
            return base_font_name
    return base_font_name

def process_bidi_text(text):
    """
    Process bidirectional text (Arabic + English).
    This is a simplified version - for production, consider using python-bidi library.
    """
    if not text or not has_mixed_content(text):
        return str(text)
    
    # Simple approach: reverse Arabic words while keeping English words in order
    text_str = str(text)
    words = text_str.split()
    processed_words = []
    
    for word in words:
        if is_arabic_text(word):
            # For Arabic words, we might need to reverse character order
            # This is very basic - proper implementation would use bidi algorithm
            processed_words.append(word)  # Keep as-is for now
        else:
            processed_words.append(word)
    
    return ' '.join(processed_words)

def get_text_alignment(text, default_align):
    """
    Determine text alignment based on content and default alignment.
    Arabic text should generally be right-aligned.
    """
    if is_arabic_text(text):
        return 'right'
    return default_align

def wrap_text_with_font(text, max_width, font_name, font_size):
    """
    Wrap text considering the specific font metrics.
    """
    if not text:
        return [""]
    
    # Check if text fits in one line
    if stringWidth(text, font_name, font_size) <= max_width:
        return [text]
    
    # Calculate approximate characters per line based on font
    avg_char_width = stringWidth('A', font_name, font_size)  # Use 'A' as average
    
    # For Arabic text, use different character for average width calculation
    if is_arabic_text(text):
        # Use Arabic letter 'alef' as average character width
        avg_char_width = stringWidth('ا', font_name, font_size)
    
    chars_per_line = max(1, int(max_width / avg_char_width))
    
    # Split text respecting word boundaries
    words = text.split()
    lines = []
    current_line = ""
    
    for word in words:
        test_line = current_line + (" " if current_line else "") + word
        
        if stringWidth(test_line, font_name, font_size) <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
                current_line = word
            else:
                # Word is too long, force break
                while stringWidth(word, font_name, font_size) > max_width:
                    # Find how many characters fit
                    for i in range(len(word), 0, -1):
                        if stringWidth(word[:i], font_name, font_size) <= max_width:
                            lines.append(word[:i])
                            word = word[i:]
                            break
                current_line = word
    
    if current_line:
        lines.append(current_line)
    
    return lines if lines else [""]

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
    width, height = A4  # This returns a tuple (width, height)
    margin_x = 30
    y = height - 60  # height is now just the numeric value
    
    # ---------- DRAW INVOICE SECTIONS ----------
    y = add_letterhead(c, invoice_doc, width, height)
    y = _draw_header_section(c, invoice_doc, width, height, margin_x, y, font_name)
    y = _draw_seller_buyer_section(c, invoice_doc, width, margin_x, y, font_name)
    y = _draw_items_section(c, invoice_doc, width, height, margin_x, y, font_name)
    y = _draw_totals_section(c, invoice_doc, width, margin_x, y, font_name)
    y = _draw_tax_summary(c, invoice_doc, width, margin_x, y, font_name)
    y = _draw_bank_details(c, invoice_doc, width, margin_x, y, font_name)
    _draw_footer(c, width, font_name)
    
    c.save()

def check_page_break(c, y, height, margin_y=100, font_name="Cairo", font_size=9, debug=False, invoice_doc=None):
    """
    Check if we need to start a new page. Return reset y if page breaks.
    Added debug parameter to print information about page break decisions.
    """
    # Handle case where height might be a tuple (width, height)
    if isinstance(height, tuple):
        page_height = height[1] 
    else:
        page_height = height
    
    if debug:
        print(f"DEBUG: Current y={y}, margin_y={margin_y}, page_height={page_height}, page_break_needed={y < margin_y}")
    
    if y < margin_y:  
        width = c._pagesize[0]
        c.showPage()
        c.setFont(font_name, font_size)
        add_letterhead(c, invoice_doc, width, page_height)

        # Draw footer on new page
        try:
            _draw_footer(c, c._pagesize[0], font_name)
        except Exception as e:
            if debug:
                print(f"DEBUG: Error drawing footer on new page: {e}")
        
        new_y = page_height - 100  # reset y for new page top
        if debug:
            print(f"DEBUG: Returning new y position: {new_y}")
        
        return new_y
    
    if debug:
        print(f"DEBUG: No page break needed. Current y ({y}) is above margin ({margin_y})")
    
    return y


# def _draw_table_cell(c, x, y, w, h, text, font_name, font_size=7, align='left', bg_color=None):
#     """Helper function to draw bordered table cell with optional background color."""
#     if bg_color:
#         c.setFillColor(bg_color)
#         c.rect(x, y-h, w, h, fill=1)
#         c.setFillColor(black)
    
#     # CHANGE THIS: Make lines thinner
#     c.setLineWidth(0.5)  # Change from default (usually 1) to 0.5 or 0.3
#     c.rect(x, y-h, w, h, fill=0)
    
#     # Reset line width after drawing
#     c.setLineWidth(1)
    
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
def _draw_table_cell(c, x, y, w, h, text, base_font_name, font_size=7, align='left', bg_color=None):
    """
    Enhanced table cell drawing with bilingual (English/Arabic) font support.
    Supports multi-line (split by \n).
    """
    if not text:
        text = ""
    
    text_str = str(text)
    lines = text_str.split('\n')   # -> ["Vendor Number", "رقم البائع"]
    
    # Draw background if specified
    if bg_color:
        c.setFillColor(bg_color)
        c.rect(x, y-h, w, h, fill=1)
        c.setFillColor(black)
    
    # Draw border
    c.setLineWidth(0.5)
    c.rect(x, y-h, w, h, fill=0)
    c.setLineWidth(1)
    
    line_height = font_size + 2
    total_text_height = len(lines) * line_height
    
    # Start drawing from vertical center
    start_y = y - (h/2) + (total_text_height/2) - font_size
    
    for i, line in enumerate(lines):
        # Pick correct font for this line
        font_name = get_appropriate_font(line, base_font_name)
        c.setFont(font_name, font_size)
        
        text_y = start_y - i * line_height
        
        # Alignment
        effective_align = get_text_alignment(line, align)
        
        if effective_align == 'center':
            c.drawCentredString(x + w/2, text_y, line)
        elif effective_align == 'right' or is_arabic_text(line):
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
        if file_url.startswith("/files/"):  # public file
            file_path = frappe.get_site_path("public", "files", file_url.split("/files/")[1])
        elif file_url.startswith("/private/files/"):  # private file
            file_path = frappe.get_site_path("private", "files", file_url.split("/private/files/")[1])
        else:
            # fallback: try relative to /public
            file_path = frappe.get_site_path("public", file_url.lstrip("/"))

        try:
            img_height = 60
            img_width = 400
            x = (page_width - img_width) / 2  # center horizontally
            y = page_height - img_height - top_margin

            c.drawImage(
                file_path,
                x,
                y,
                width=img_width,
                height=img_height,
                preserveAspectRatio=True,
                mask="auto"
            )
            y_after = y - 10
        except Exception as e:
            frappe.log_error(f"Letterhead image rendering failed: {e}", "PDF Generator")

    # --- HTML ---
    elif letterhead.content:
        try:
            styles = getSampleStyleSheet()
            style = styles["Normal"]
            style.fontName = "Times-Roman"
            style.fontSize = 20
            style.leading = 22
            style.alignment = 1  # center text

            para = Paragraph(letterhead.content, style)
            w, h = para.wrap(page_width - 80, 100)
            x = (page_width - w) / 2  # center horizontally
            y = page_height - h - top_margin

            para.drawOn(c, x, y)
            y_after = y - 10
        except Exception as e:
            frappe.log_error(f"Letterhead HTML rendering failed: {e}", "PDF Generator")

    return y_after


    
def _draw_header_section(c, invoice_doc, width, height, margin_x, y, font_name):
    """Draw the header section including invoice details and QR code."""
    cell_height = 15
    table_width = width - 2 * margin_x  # Full width between margins
    qr_width = 60
    y = add_letterhead(c, invoice_doc, width, height)
    
    # Invoice title
    c.setFont(font_name, 8)
    c.setFillColor(black)
    c.drawCentredString(width/2, y, "Tax Invoice - فاتورة ضريبية")
    y -= 30
    
    # Invoice details table (left side) - 6 columns with dynamic height
    col_widths = [70, 90, 80, 80, 70, 80]
    
    # Row data for invoice details
    delivery_note = getattr(invoice_doc.items[0], 'delivery_note', '') if invoice_doc.items else ''
    delivery_note = delivery_note if delivery_note else '-'
    supply_date = frappe.utils.get_datetime(frappe.db.get_value('Delivery Note', invoice_doc.items[0].delivery_note, 'posting_date')).strftime("%d-%m-%Y") or '-'
    
    rows_data = [
        ["Invoice No:", invoice_doc.name, "رقم الفاتورة", "Issue Date:", str(invoice_doc.posting_date), "تاريخ إصدار الفاتورة"],
        ["ZATCA Status", getattr(invoice_doc, 'custom_zatca_submit_status', ''), "حالة التخليص", "Due Date:", str(invoice_doc.due_date or ''), "تاريخ الاستحقاق"],
        ["Delivery Note:", delivery_note, "مذكرة التسليم", "Date of Supply:", supply_date, "تاريخ التوريد"]
    ]
    
    current_y = y
    total_table_height = 0 
    
    for row_data in rows_data:
        # Calculate max height needed for this row
        max_height = cell_height
        for i, text in enumerate(row_data):
            text_width = col_widths[i] - 10
            avg_char_width = stringWidth('A', font_name, 7)
            chars_per_line = max(1, int(text_width / avg_char_width))
            lines_needed = len(textwrap.wrap(str(text), width=chars_per_line))
            content_height = lines_needed * (9 + 2) + 4 
            max_height = max(max_height, content_height)
        
        # Draw the row with consistent height
        for i, text in enumerate(row_data):
            align = 'right' if i in [2, 5] else 'left'
            _draw_table_cell_with_wrapping(
                c, margin_x + sum(col_widths[:i]), current_y, col_widths[i], 
                max_height, text, font_name, 7, align, auto_height=True
            )
        
        total_table_height += max_height
        current_y -= max_height
    
    # QR Code (right side) - NO BORDER
    qr_x = width - margin_x - qr_width
    
    # Draw QR code image if available (without border) - height matches table height
    qr_code_path = getattr(invoice_doc, 'custom_invoice_qr_code', '')
    if qr_code_path:
        try:
            if qr_code_path.startswith('/files/'):
                qr_code_path = qr_code_path.replace('/files/', '')
            
            full_qr_path = frappe.utils.get_site_path('public', 'files', qr_code_path)
            
            # Draw the QR code image without border - height matches table height
            # Position it to the right of the table, not overlapping
            c.drawImage(full_qr_path, qr_x, y - total_table_height, 
                    width=qr_width, height=total_table_height, 
                    preserveAspectRatio=True, mask='auto')
        except Exception as e:
            print(f"Error loading QR code: {e}")
            # Fallback to text if image can't be loaded
            c.drawCentredString(qr_x + qr_width/2, y - total_table_height/2, "QR CODE")
    else:
        c.drawCentredString(qr_x + qr_width/2, y - total_table_height/2, "QR CODE")
    
    y = current_y - 20  
    
    # Purchase order details table - 6 columns (FULL WIDTH like other tables)
    po_table_width = table_width  
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
        getattr(invoice_doc, 'reference_no', '') or '-',
       
    ]
    
    for i, data in enumerate(po_data):
        _draw_table_cell(c, margin_x + i * po_col_width, current_y, po_col_width, 
                        cell_height, data, font_name, 7, 'center')
    
    return current_y - cell_height - 20


# def _draw_table_cell_with_wrapping(c, x, y, w, h, text, font_name, font_size=7, align='left', bg_color=None, auto_height=False):
#     """Helper function to draw bordered table cell with text wrapping for long content."""
    
#     # Calculate available width for text (minus padding)
#     text_width = w - 10  # 5px padding on each side
    
#     # Handle empty or None text
#     if not text:
#         text = ""
    
#     text_str = str(text)
    
#     # Check if text fits in one line
#     if stringWidth(text_str, font_name, font_size) <= text_width:
#         lines = [text_str]
#     else:
#         # Calculate approximate characters per line
#         avg_char_width = stringWidth('A', font_name, font_size)
#         chars_per_line = int(text_width / avg_char_width)
        
#         # Wrap text
#         lines = textwrap.wrap(text_str, width=chars_per_line)
        
#         # If still too wide, force break long words
#         final_lines = []
#         for line in lines:
#             while stringWidth(line, font_name, font_size) > text_width:
#                 # Find how many characters fit
#                 for i in range(len(line), 0, -1):
#                     if stringWidth(line[:i], font_name, font_size) <= text_width:
#                         final_lines.append(line[:i])
#                         line = line[i:]
#                         break
#             if line:
#                 final_lines.append(line)
#         lines = final_lines
    
#     # Calculate required height if auto_height is True
#     line_height = font_size + 2
#     required_height = max(h, len(lines) * line_height + 4)  # 4px total padding
    
#     # Use required height if auto_height, otherwise use provided height
#     cell_height = required_height if auto_height else h
    
#     # Draw background if specified
#     if bg_color:
#         c.setFillColor(bg_color)
#         c.rect(x, y-cell_height, w, cell_height, fill=1)
#         c.setFillColor(black)
    
#     # Draw border
#     c.setLineWidth(0.5) 
#     c.rect(x, y-cell_height, w, cell_height, fill=0)
#     c.setLineWidth(1)
    
#     # Set font
#     c.setFont(font_name, font_size)
    
#     # Draw text lines
#     for i, line in enumerate(lines):
#         text_y = y - cell_height/2 - font_size/2 + (len(lines)/2 - i - 0.5) * line_height
        
#         if align == 'center':
#             c.drawCentredString(x + w/2, text_y, line)
#         elif align == 'right':
#             c.drawRightString(x + w - 5, text_y, line)
#         else:
#             c.drawString(x + 5, text_y, line)
    
#     return cell_height

def _draw_table_cell_with_wrapping(c, x, y, w, h, text, base_font_name, font_size=7, align='left', bg_color=None, auto_height=False):
    """
    Enhanced table cell drawing with Arabic font support and RTL positioning.
    """
    # Handle empty or None text
    if not text:
        text = ""
    
    text_str = str(text)
    
    # Calculate available width for text (minus padding)
    text_width = w - 10  # 5px padding on each side
    
    # Split by newlines first to handle explicit line breaks
    explicit_lines = text_str.split('\n')
    final_lines = []
    
    # Process each explicit line for wrapping if needed
    for line in explicit_lines:
        processed_line = process_bidi_text(line)
        
        # Check if this line fits
        line_font = get_appropriate_font(processed_line, base_font_name)
        if stringWidth(processed_line, line_font, font_size) <= text_width:
            final_lines.append((processed_line, line_font))
        else:
            # Line needs wrapping
            wrapped_lines = wrap_text_with_font(processed_line, text_width, line_font, font_size)
            for wrapped_line in wrapped_lines:
                wrapped_font = get_appropriate_font(wrapped_line, base_font_name)
                final_lines.append((wrapped_line, wrapped_font))
    
    # Calculate required height if auto_height is True
    line_height = font_size + 2
    required_height = max(h, len(final_lines) * line_height + 4)  # 4px total padding
    
    # Use required height if auto_height, otherwise use provided height
    cell_height = required_height if auto_height else h
    
    # Draw background if specified
    if bg_color:
        c.setFillColor(bg_color)
        c.rect(x, y-cell_height, w, cell_height, fill=1)
        c.setFillColor(black)
    
    # Draw border
    c.setLineWidth(0.5)
    c.rect(x, y-cell_height, w, cell_height, fill=0)
    c.setLineWidth(1)
    
    # Draw text lines with proper alignment for Arabic/RTL content
    for i, (line, line_font) in enumerate(final_lines):
        # Set font for each line individually
        c.setFont(line_font, font_size)
        
        text_y = y - cell_height/2 - font_size/2 + (len(final_lines)/2 - i - 0.5) * line_height
        
        # Determine alignment based on text content
        effective_align = get_text_alignment(line, align)
        
        if effective_align == 'center':
            c.drawCentredString(x + w/2, text_y, line)
        elif effective_align == 'right' or is_arabic_text(line):
            # Arabic text should be right-aligned
            c.drawRightString(x + w - 5, text_y, line)
        else:
            c.drawString(x + 5, text_y, line)
    
    return cell_height

def safe_get_value(doctype, name, fieldname):
    try:
        meta = frappe.get_meta(doctype)
        fieldnames = [df.fieldname for df in meta.fields]

        if fieldname in fieldnames:
            return frappe.db.get_value(doctype, name, fieldname) or "-"
        else:
            return "-"
    except Exception:
        return "-"


def _draw_seller_buyer_section(c, invoice_doc, width, margin_x, y, font_name):
    """Draw seller and buyer information section with text wrapping."""
    base_cell_height = 15
    seller_buyer_width = (width - 2 * margin_x) / 2
    detail_col_width = seller_buyer_width / 4
    
    # Headers
    current_y = y
    _draw_table_cell_with_wrapping(c, margin_x, current_y, seller_buyer_width/2, base_cell_height, 
                    "Seller:", font_name, 8, bg_color=colors.lightgrey)
    _draw_table_cell_with_wrapping(c, margin_x + seller_buyer_width/2, current_y, seller_buyer_width/2, base_cell_height, 
                    ":المورد", font_name, 8, 'right', colors.lightgrey)
    _draw_table_cell_with_wrapping(c, margin_x + seller_buyer_width, current_y, seller_buyer_width/2, base_cell_height, 
                    "Buyer:", font_name, 8, bg_color=colors.lightgrey)
    _draw_table_cell_with_wrapping(c, margin_x + seller_buyer_width + seller_buyer_width/2, current_y, 
                    seller_buyer_width/2, base_cell_height, ":العميل", font_name, 8, 'right', colors.lightgrey)
    
    current_y -= base_cell_height
    
    # Fetch address details from linked Address records
    company_name_arabic = safe_get_value("Company", invoice_doc.company, "company_name_in_arabic")
    company_tax_id = safe_get_value("Company", invoice_doc.company, "tax_id")
    company_cr_number = safe_get_value("Company", invoice_doc.company, "cr_number")
    
    # Get company address details
    company_address_title = safe_get_value('Address', invoice_doc.company_address, 'address_title')
    company_address_line1 = safe_get_value('Address', invoice_doc.company_address, 'address_line1')
    company_address_line1_arabic = safe_get_value('Address', invoice_doc.company_address, 'address_line_1_in_arabic')
    company_address_line2 = safe_get_value('Address', invoice_doc.company_address, 'address_line2')
    company_address_line2_arabic = safe_get_value('Address', invoice_doc.company_address, 'address_line_2_in_arabic')
    company_city = safe_get_value('Address', invoice_doc.company_address, 'city')
    company_city_arabic = safe_get_value('Address', invoice_doc.company_address, 'city_in_arabic')
    company_country = safe_get_value('Address', invoice_doc.company_address, 'country')
    company_country_arabic = safe_get_value('Address', invoice_doc.company_address, 'county_in_arabic')
    company_pincode = safe_get_value('Address', invoice_doc.company_address, 'pincode')
    company_additional_number = safe_get_value('Address', invoice_doc.company_address, 'additional_number')

    # Get customer address details
    # customer_name_arabic = getattr(invoice_doc, 'customer_name_in_arabic', invoice_doc.customer_name)
    # customer_cr = frappe.db.get_value('Customer', invoice_doc.customer, 'cr') if invoice_doc.customer else '-'
    customer_name_arabic = safe_get_value("Sales Invoice", invoice_doc.name, "customer_name_in_arabic") or invoice_doc.customer_name
    customer_cr = safe_get_value("Customer", invoice_doc.customer, "cr") if invoice_doc.customer else "-"

    
    customer_address_title = safe_get_value("Address", invoice_doc.customer_address, "address_title")
    customer_address_line1 = safe_get_value("Address", invoice_doc.customer_address, "address_line1")
    customer_address_line1_arabic = safe_get_value("Address", invoice_doc.customer_address, "address_line_1_in_arabic")
    customer_address_line2 = safe_get_value("Address", invoice_doc.customer_address, "address_line2")
    customer_address_line2_arabic = safe_get_value("Address", invoice_doc.customer_address, "address_line_2_in_arabic")
    customer_city = safe_get_value("Address", invoice_doc.customer_address, "city")
    customer_city_arabic = safe_get_value("Address", invoice_doc.customer_address, "city_in_arabic")
    customer_country = safe_get_value("Address", invoice_doc.customer_address, "country")
    customer_country_arabic = safe_get_value("Address", invoice_doc.customer_address, "county_in_arabic")
    customer_pincode = safe_get_value("Address", invoice_doc.customer_address, "pincode")
    customer_additional_number = safe_get_value("Address", invoice_doc.customer_address, "additional_number")


    # Seller and Buyer details - Format: Label, Value, Arabic Value, Arabic Label
    details_data = [
        ("Name:", invoice_doc.company, company_name_arabic or '-', "الاسم"),
        ("Building No", company_address_title, company_address_title, "رقم المبنى"),
        ("Street Name", company_address_line1, company_address_line1_arabic, "اسم الشارع"),
        ("District", company_address_line2, company_address_line2_arabic, "الحي"),
        ("City", company_city, company_city_arabic, "المدينه"),
        ("Country", company_country, company_country_arabic, "البلد"),
        ("Postal Code", company_pincode, company_pincode, "الرمز البريدي"),
        ("Additional No.", company_additional_number, company_additional_number, "رقم إضافي"),
        ("VAT Number", company_tax_id or '-', company_tax_id or '-', "الرقم الضريبي"),
        ("Other ID", company_cr_number or '-', company_cr_number or '-', "معرف آخر")
    ]
    
    buyer_details_data = [
        ("Name:", invoice_doc.customer_name, customer_name_arabic or '-', "الاسم"),
        ("Building No", customer_address_title, customer_address_title, "رقم المبنى"),
        ("Street Name", customer_address_line1, customer_address_line1_arabic, "اسم الشارع"),
        ("District", customer_address_line2, customer_address_line2_arabic, "الحي"),
        ("City", customer_city, customer_city_arabic, "المدينه"),
        ("Country", customer_country, customer_country_arabic, "البلد"),
        ("Postal Code", customer_pincode, customer_pincode, "الرمز البريدي"),
        ("Additional No.", customer_additional_number, customer_additional_number, "رقم إضافي"),
        ("VAT Number", invoice_doc.tax_id or '-', invoice_doc.tax_id or '-', "الرقم الضريبي"),
        ("Other ID", customer_cr or '-', customer_cr or '-', "معرف آخر")
    ]
    
    for i, (label, seller_val, seller_val_arabic, arabic_label) in enumerate(details_data):
        max_height = base_cell_height
        
        # Check each cell content and calculate required height
        for content in [label, str(seller_val), str(seller_val_arabic), arabic_label]:
            content_width = detail_col_width - 10  # minus padding
            if stringWidth(str(content), font_name, 7) > content_width:
                avg_char_width = stringWidth('A', font_name, 7)
                chars_per_line = int(content_width / avg_char_width)
                lines_needed = len(textwrap.wrap(str(content), width=chars_per_line))
                content_height = lines_needed * 11 + 4  # 9px font + 2px spacing + 4px padding
                max_height = max(max_height, content_height)
        
        # Draw seller side - Format: Label, Value, Arabic Value, Arabic Label
        _draw_table_cell_with_wrapping(c, margin_x, current_y, detail_col_width, max_height, 
                        label, font_name, 7)
        _draw_table_cell_with_wrapping(c, margin_x + detail_col_width, current_y, detail_col_width, max_height, 
                        str(seller_val), font_name, 7)
        _draw_table_cell_with_wrapping(c, margin_x + detail_col_width * 2, current_y, detail_col_width, max_height, 
                        str(seller_val_arabic), font_name, 7, 'right') 
        _draw_table_cell_with_wrapping(c, margin_x + detail_col_width * 3, current_y, detail_col_width, max_height, 
                        arabic_label, font_name, 7, 'right')  # Arabic label
        
        # Draw buyer side - Format: Label, Value, Arabic Value, Arabic Label
        if i < len(buyer_details_data):
            buyer_label, buyer_val, buyer_val_arabic, buyer_arabic_label = buyer_details_data[i]
            _draw_table_cell_with_wrapping(c, margin_x + seller_buyer_width, current_y, detail_col_width, max_height, 
                            buyer_label, font_name, 7)
            _draw_table_cell_with_wrapping(c, margin_x + seller_buyer_width + detail_col_width, current_y, detail_col_width, max_height, 
                            str(buyer_val), font_name, 7)
            _draw_table_cell_with_wrapping(c, margin_x + seller_buyer_width + detail_col_width * 2, current_y, detail_col_width, max_height, 
                            str(buyer_val_arabic), font_name, 7, 'right')
            _draw_table_cell_with_wrapping(c, margin_x + seller_buyer_width + detail_col_width * 3, current_y, detail_col_width, max_height, 
                            buyer_arabic_label, font_name, 7, 'right')
        
        current_y -= max_height
    
    return current_y - 20


def strip_html_tags(text):
    """Remove HTML tags from text and return plain text."""
    if not text:
        return ""
    
    # Remove HTML tags using regex
    clean_text = re.sub('<[^<]+?>', '', str(text))
    
    # Replace HTML entities if needed
    clean_text = clean_text.replace('&amp;', '&')
    clean_text = clean_text.replace('&lt;', '<')
    clean_text = clean_text.replace('&gt;', '>')
    clean_text = clean_text.replace('&quot;', '"')
    clean_text = clean_text.replace('&#39;', "'")
    
    return clean_text.strip()

def get_first_tax_rate(doc):
    """
    Get the tax rate from the first row of Sales Taxes and Charges
    """
    if getattr(doc, "taxes", None) and len(doc.taxes) > 0:
        return doc.taxes[0].rate or 0
    return 0

def _draw_items_section(c, invoice_doc, width, height, margin_x, y, font_name):
    """Draw items table section with flexible row heights based on content."""
    base_cell_height = 15
    table_width = width - 2 * margin_x  # Full width between margins
    
    # Column widths that add up to table_width
    item_col_widths = [60, 180, 70, 60, 90, 80, 120]
    # Adjust if they don't add up to table_width
    total_col_width = sum(item_col_widths)
    if total_col_width != table_width:
        scale_factor = table_width / total_col_width
        item_col_widths = [int(w * scale_factor) for w in item_col_widths]
    
    current_y = y
    
    # English and Arabic headers combined
    combined_headers = [
        "PO Item\nبند طلب",
        "Nature of goods or services\nفاصيل السلع او الخدمات",
        "Unit Price\nعر الوحدة",
        "Qty\nالكمية",
        "Taxable Amt\nلمبلغ الخاضع للضريبة",
        "Tax Amt\nبلغ الضريبة",
        "Subtotal(Inc. VAT)\nلمجموع شامل الضريبة"
    ]

    for i, header in enumerate(combined_headers):
        _draw_table_cell(
            c,
            margin_x + sum(item_col_widths[:i]),
            current_y,
            item_col_widths[i],
            base_cell_height * 2,  # Double height for two lines
            header,
            font_name,
            7,  # Consistent font size
            'center',
            colors.lightgrey
        )

    current_y -= base_cell_height * 2

    # Items data with flexible row heights
    
    if invoice_doc.items:
        for item in invoice_doc.items:
            # Calculate maximum height needed for this row
            max_height = base_cell_height
            
            # Prepare item data
            clean_description = strip_html_tags(item.description or '')
            item_description = f"{item.item_code}\n{item.item_name}\n{clean_description}"
            item_tax_amount = get_first_tax_rate(invoice_doc) * item.amount / 100 if get_first_tax_rate(invoice_doc) else 0
            item_data = [
                getattr(item, 'line_item', '') or '',
                item_description,
                format_currency(item.rate, invoice_doc.currency),
                f"{item.qty}",
                format_currency(item.amount, invoice_doc.currency),
                format_currency(item_tax_amount, invoice_doc.currency),
                format_currency(item.amount + item_tax_amount, invoice_doc.currency)
            ]
            
            # Calculate required height for each cell
            for i, data in enumerate(item_data):
                if i == 1:  # Description column needs special handling
                    # Calculate lines needed for description
                    desc_width = item_col_widths[1] - 10  # minus padding
                    avg_char_width = stringWidth('A', font_name, 7)
                    chars_per_line = max(1, int(desc_width / avg_char_width))
                    lines_needed = len(textwrap.wrap(str(data), width=chars_per_line))
                    content_height = lines_needed * (8 + 2) + 4  # font + spacing + padding
                    max_height = max(max_height, content_height)
                else:
                    # For other columns, check if text fits or needs wrapping
                    text_width = item_col_widths[i] - 10
                    if stringWidth(str(data), font_name, 7) > text_width:
                        avg_char_width = stringWidth('A', font_name, 7)
                        chars_per_line = max(1, int(text_width / avg_char_width))
                        lines_needed = len(textwrap.wrap(str(data), width=chars_per_line))
                        content_height = lines_needed * (8 + 2) + 4
                        max_height = max(max_height, content_height)
            
            # Check page break before drawing the row
            current_y = check_page_break(c, current_y, height, 100, font_name, 8, False, invoice_doc)
            
            # Draw each cell with consistent row height
            for i, data in enumerate(item_data):
                align = 'right' if i in [2, 3, 4, 5, 6] else 'left'
                
                if i == 1:  # Use wrapping for description column
                    _draw_table_cell_with_wrapping(
                        c,
                        margin_x + sum(item_col_widths[:i]),
                        current_y,
                        item_col_widths[i],
                        max_height,
                        str(data),
                        font_name,
                        7,
                        align,
                        auto_height=False
                    )
                else:
                    _draw_table_cell(
                        c,
                        margin_x + sum(item_col_widths[:i]),
                        current_y,
                        item_col_widths[i],
                        max_height,
                        str(data),
                        font_name,
                        7,
                        align
                    )

            current_y -= max_height

    return current_y - 20


def _draw_totals_section(c, invoice_doc, width, margin_x, y, font_name):
    """Draw totals section with dynamic height expansion."""
    base_cell_height = 15
    table_width = width - 2 * margin_x  

    # Total amounts header
    current_y = check_page_break(c, y, height, 150, font_name, 9, False, invoice_doc)
    _draw_table_cell_with_wrapping(
        c, margin_x, current_y, table_width/2, base_cell_height,
        "Total Amounts:", font_name, 7, bg_color=colors.lightgrey, auto_height=True
    )
    _draw_table_cell_with_wrapping(
        c, margin_x + table_width/2, current_y, table_width/2, base_cell_height,
        ":اجمالي المبالغ", font_name, 7, 'right', colors.lightgrey, auto_height=True
    )
    current_y -= base_cell_height

    # Totals data
    totals_data = [
        ("Total Taxable Amount (Excluding VAT)", "الاجمالي الخاضع للضريبة  (غير شامل ضريبة القيمة المضافة)", format_currency(invoice_doc.net_total, invoice_doc.currency)),
        ("Total VAT", "مجموع ضريبة القيمة المضافة", format_currency(invoice_doc.total_taxes_and_charges, invoice_doc.currency)),
        ("Total Amount Due", "اجمالي المبلغ المستحق", format_currency(invoice_doc.grand_total, invoice_doc.currency)),
        ("Total In Words", "", invoice_doc.in_words or "")
    ]

    col_widths = [table_width/4, table_width/4, table_width/4, table_width/4]

    for english, arabic, amount in totals_data:
        # First pass: calculate required height
        max_height = base_cell_height
        for content, w in zip(["", english, arabic, amount], col_widths):
            content_width = w - 10
            avg_char_width = stringWidth('A', font_name, 7)
            chars_per_line = max(1, int(content_width / avg_char_width))
            lines_needed = len(textwrap.wrap(str(content), width=chars_per_line))
            content_height = lines_needed * (9 + 2) + 4 
            max_height = max(max_height, content_height)

        # Second pass: draw row with dynamic height
        _draw_table_cell_with_wrapping(c, margin_x, current_y, col_widths[0], max_height, "", font_name, 7, auto_height=True)
        _draw_table_cell_with_wrapping(c, margin_x + col_widths[0], current_y, col_widths[1], max_height, english, font_name, 7, auto_height=True)
        _draw_table_cell_with_wrapping(c, margin_x + col_widths[0] + col_widths[1], current_y, col_widths[2], max_height, arabic, font_name, 7, 'right', auto_height=True)
        _draw_table_cell_with_wrapping(c, margin_x + col_widths[0] + col_widths[1] + col_widths[2], current_y, col_widths[3], max_height, amount, font_name, 7, 'right', auto_height=True)

        current_y -= max_height

    return current_y - 20


def format_currency(value, currency):
    """Format currency using ERPNext Currency Doc symbol"""
    if not currency:
        return value
    # fetch symbol from Currency doctype
    symbol = frappe.db.get_value("Currency", currency, "symbol") or currency
    # format number with 2 decimals and add symbol
    return f"{symbol} {frappe.utils.fmt_money(value, 2)}"


def _draw_tax_summary(c, invoice_doc, width, margin_x, y, font_name):
    """Draw tax summary section."""
    cell_height = 15
    table_width = width - 2 * margin_x  # Full width between margins
    conversion_rate = getattr(invoice_doc, 'conversion_rate', 1)
    current_y = check_page_break(c, y, height, 150, font_name, 7,False, invoice_doc)
    
    # Tax summary header
    _draw_table_cell(c, margin_x, current_y, table_width, cell_height, 
                    f"Tax Summary (1 {invoice_doc.currency} = {conversion_rate} SAR)", 
                    font_name, 8, bg_color=colors.lightgrey)
    current_y -= cell_height
    
    # Tax table headers
    tax_col_widths = [table_width/2, table_width/4, table_width/4]
    tax_headers = ["Tax Details", "Taxable Amount(SAR)", "Tax Amount(SAR)"]
    
    for i, header in enumerate(tax_headers):
        align = 'left' if i == 0 else 'right'
        _draw_table_cell(c, margin_x + sum(tax_col_widths[:i]), current_y, tax_col_widths[i], 
                        cell_height, header, font_name, 9, align, colors.lightgrey)
    
    current_y -= cell_height
    
    # Tax data
    base_net_total = format_currency(getattr(invoice_doc, 'base_net_total', invoice_doc.net_total * conversion_rate), "SAR")
    base_tax_amount = format_currency(getattr(invoice_doc, 'base_total_taxes_and_charges', invoice_doc.total_taxes_and_charges * conversion_rate), "SAR")
    
    tax_data = [
        getattr(invoice_doc, 'taxes_and_charges', 'VAT 15%'),
        f"{base_net_total}",
        f"{base_tax_amount}"
    ]
    
    for i, data in enumerate(tax_data):
        align = 'left' if i == 0 else 'right'
        _draw_table_cell(c, margin_x + sum(tax_col_widths[:i]), current_y, tax_col_widths[i], 
                        cell_height, data, font_name, 7, align)
    
    return current_y - cell_height - 20


def _draw_bank_details(c, invoice_doc, width, margin_x, y, font_name):
    """Draw bank details section dynamically from Bank Account doctype, only if custom_display_in_pdf is ticked."""
    base_cell_height = 15
    table_width = width - 2 * margin_x  
    current_y = check_page_break(c, y, height, 150, font_name, 9, False, invoice_doc)

    # Fetch bank accounts with display flag
    bank_accounts = frappe.get_all(
        "Bank Account",
        filters={"custom_display_in_pdf": 1},
        fields=["account_name", "custom_account_name_in_arabic", "bank", "iban"]
    )

    if not bank_accounts:
        # No accounts with ticked flag -> skip table
        return y  

    # Add swift_number from Bank master
    for ba in bank_accounts:
        ba["swift_number"] = safe_get_value("Bank", ba.bank, "swift_number")
        ba["custom_bank_name_in_arabic"] = safe_get_value("Bank", ba.bank,"custom_bank_name_in_arabic")

    # Table header
    _draw_table_cell_with_wrapping(
        c, margin_x, current_y, table_width/2, base_cell_height,
        "Bank Details", font_name, 8, bg_color=colors.lightgrey, auto_height=True
    )
    _draw_table_cell_with_wrapping(
        c, margin_x + table_width/2, current_y, table_width/2, base_cell_height,
        "التفاصيل المصرفية", font_name, 8, 'right', colors.lightgrey, auto_height=True
    )
    current_y -= base_cell_height

    bank_col_width = table_width / 4

    for ba in bank_accounts:
        bank_details = [
            ("Account Name", "اسم الحساب المصرفي", ba.account_name, ba.custom_account_name_in_arabic or "-"),
            ("Bank Name", "اسم البنك", ba.bank or "-", ba.custom_bank_name_in_arabic or "-"),
            ("IBAN", "رقم الآيبان", ba.iban or "-", ba.iban or "-"),
            ("Swift Code", "رمز السويفت", ba.swift_number or "-", ba.swift_number or "-")
        ]

        for english_label, arabic_label, english_value, arabic_value in bank_details:
            # Calculate dynamic row height
            max_height = base_cell_height
            row_data = [english_label, english_value, arabic_value, arabic_label]
            for content, w in zip(row_data, [bank_col_width] * 4):
                content_width = w - 10
                avg_char_width = stringWidth('A', font_name, 7)
                chars_per_line = max(1, int(content_width / avg_char_width))
                lines_needed = len(textwrap.wrap(str(content), width=chars_per_line))
                content_height = lines_needed * (9 + 2) + 4  
                max_height = max(max_height, content_height)

            # Draw the row
            _draw_table_cell_with_wrapping(c, margin_x, current_y, bank_col_width, max_height,
                                           english_label, font_name, 7, bg_color=colors.white, auto_height=True)
            _draw_table_cell_with_wrapping(c, margin_x + bank_col_width, current_y, bank_col_width, max_height,
                                           english_value, font_name, 7, 'center', auto_height=True)
            _draw_table_cell_with_wrapping(c, margin_x + 2*bank_col_width, current_y, bank_col_width, max_height,
                                           arabic_value, font_name, 7, 'center', auto_height=True)
            _draw_table_cell_with_wrapping(c, margin_x + 3*bank_col_width, current_y, bank_col_width, max_height,
                                           arabic_label, font_name, 7, 'right', colors.white, auto_height=True)

            current_y -= max_height

    return current_y - 20



def _draw_footer(c, width, font_name):
    """Draw footer section."""
    c.setFont(font_name, 8)
    c.drawCentredString(width/2, 30, "This is a PDF/A-3A compliant invoice with embedded XML")
    print("here man")
    

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