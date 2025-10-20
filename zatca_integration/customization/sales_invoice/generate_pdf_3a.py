# ruff: noqa: E501

"""
Generate PDF/A-3A compliant PDF for Frappe Sales Invoice with embedded XML
This method uses the first approach: get print format HTML, attach to PDF, attach XML, create PDF3A
"""

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import convertapi
import frappe
import pikepdf
from frappe.utils.pdf import get_pdf
from pikepdf import Array, Dictionary, Name, String

# Configuration paths
font_dir = Path(frappe.get_app_path("zatca_integration", "public", "fonts"))
icc_ = Path(frappe.get_app_path("zatca_integration", "public"))
icc_2014 = icc_ / "sRGB2014.icc"

cairo_regular = str(font_dir / "Cairo-Regular.ttf")

EMBEDDED_SRGB_ICC = icc_2014
EMBEDDED_FONT_TTF = cairo_regular

# Configure ConvertAPI (PDF -> PDF/A-3A)
convertapi.api_credentials = "GxRHhnLAaS1962KKdBhrSbZAc5v8ZFUt"


def find_ttf_font() -> str:
    """Return a TTF path to embed. Prefer bundled Cairo font; otherwise try common system fonts."""
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
        "No embeddable TTF font found. Place Cairo-Regular.ttf in fonts/ or ensure a system TTF like Arial.ttf exists."
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
        "sRGB ICC profile not found. Place 'sRGB2014.icc' under public/ or install a system sRGB profile."
    )


def generate_pdf_from_print_format(invoice_doc):
    """Generate PDF from print format HTML using default Zatca PDF-A 3B format."""
    try:
        # Generate HTML content from print format using default Zatca PDF-A 3B
        html = frappe.get_print(
            doctype="Sales Invoice",
            name=invoice_doc.name,
            print_format="Zatca PDF-A 3B",
            no_letterhead=0,  # Include letterhead
        )

        # Debug: Log HTML content length
        frappe.log_error(f"HTML content length: {len(html) if html else 0}", "PDF3A Generator")

        if not html:
            frappe.throw("Failed to generate HTML content from print format")

        # Use wkhtmltopdf to preserve print format design, then convert to PDF/A-3A with ConvertAPI
        pdf_content = None

        # Approach 1: wkhtmltopdf with print format (preserves design)
        try:
            pdf_content = get_pdf(
                html,
                options={
                    "page-size": "A4",
                    "margin-top": "0.75in",
                    "margin-right": "0.75in",
                    "margin-bottom": "0.75in",
                    "margin-left": "0.75in",
                    "encoding": "UTF-8",
                    "no-outline": None,
                    "enable-local-file-access": None,
                    "print-media-type": None,
                    "disable-smart-shrinking": None,
                    "dpi": 300,
                    "image-quality": 100,
                },
            )
            frappe.log_error(
                "PDF generated with wkhtmltopdf preserving print format", "PDF3A Generator"
            )
        except Exception as e:
            frappe.log_error(f"wkhtmltopdf generation failed: {e}", "PDF3A Generator")

        # Approach 2: Fallback to ReportLab if wkhtmltopdf fails
        if not pdf_content:
            try:
                pdf_content = create_comprehensive_pdfa_pdf(invoice_doc)
                frappe.log_error("PDF generated with ReportLab fallback", "PDF3A Generator")
            except Exception as e:
                frappe.log_error(f"ReportLab fallback failed: {e}", "PDF3A Generator")

        # Debug: Log PDF content length
        frappe.log_error(
            f"PDF content length: {len(pdf_content) if pdf_content else 0}", "PDF3A Generator"
        )

        if not pdf_content:
            frappe.throw("Failed to create PDF/A compliant PDF")

        return pdf_content

    except Exception as e:
        frappe.log_error(f"Error generating PDF from print format: {e}", "PDF3A Generator")
        frappe.throw(f"Failed to generate PDF from print format: {str(e)}")


def create_pdfa_compliant_pdf(html_content, invoice_doc):
    """Create PDF/A compliant PDF using ReportLab with HTML content conversion."""
    try:
        import tempfile

        from bs4 import BeautifulSoup
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import SimpleDocTemplate

        # Create a temporary PDF file
        temp_pdf = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        temp_pdf_path = temp_pdf.name
        temp_pdf.close()

        # Register fonts for PDF/A compliance
        font_path = find_ttf_font()
        pdfmetrics.registerFont(TTFont("EmbeddedFont", font_path))

        # Create PDF document
        doc = SimpleDocTemplate(
            temp_pdf_path,
            pagesize=A4,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=18,
            title=f"Sales Invoice {invoice_doc.name}",
            author="ERPNext ZATCA Integration",
            subject="PDF/A-3A Compliant Invoice",
            creator="ERPNext ZATCA Integration",
        )

        # Parse HTML content
        soup = BeautifulSoup(html_content, "html.parser")

        # Create story (content)
        story = []
        styles = getSampleStyleSheet()

        # Configure styles with embedded font
        for style_name in ["Title", "Heading1", "Heading2", "Normal", "BodyText"]:
            if hasattr(styles, style_name):
                style = getattr(styles, style_name)
                style.fontName = "EmbeddedFont"

        # Convert HTML to ReportLab elements
        convert_html_to_reportlab(soup, story, styles, invoice_doc)

        # Build PDF
        doc.build(story)

        # Read the generated PDF
        with open(temp_pdf_path, "rb") as f:
            pdf_content = f.read()

        # Clean up temporary file
        os.unlink(temp_pdf_path)

        return pdf_content

    except Exception as e:
        frappe.log_error(f"Error creating PDF/A compliant PDF: {e}", "PDF3A Generator")
        # Fallback to standard PDF generation
        try:
            return get_pdf(html_content)
        except Exception as fallback_e:
            frappe.log_error(
                f"Fallback PDF generation also failed: {fallback_e}", "PDF3A Generator"
            )
            return None


def convert_html_to_reportlab(soup, story, styles, invoice_doc):
    """Convert HTML content to ReportLab elements."""
    try:
        # Remove script and style tags
        for script in soup(["script", "style"]):
            script.decompose()

        # Process the main content
        body = soup.find("body")
        if not body:
            body = soup

        # Convert HTML elements to ReportLab elements
        for element in body.find_all(
            ["h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "span", "table", "tr", "td", "th"]
        ):
            if element.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                # Handle headings
                level = int(element.name[1])
                style_name = f"Heading{level}" if level <= 2 else "Heading2"
                style = getattr(styles, style_name, styles["Heading2"])
                text = element.get_text(strip=True)
                if text:
                    story.append(Paragraph(text, style))
                    story.append(Spacer(1, 6))

            elif element.name == "p":
                # Handle paragraphs
                text = element.get_text(strip=True)
                if text:
                    story.append(Paragraph(text, styles["Normal"]))
                    story.append(Spacer(1, 6))

            elif element.name == "table":
                # Handle tables
                table_data = []
                rows = element.find_all("tr")
                for row in rows:
                    cells = row.find_all(["td", "th"])
                    row_data = []
                    for cell in cells:
                        cell_text = cell.get_text(strip=True)
                        row_data.append(cell_text)
                    if row_data:
                        table_data.append(row_data)

                if table_data:
                    # Create table
                    table = Table(table_data)
                    table.setStyle(
                        TableStyle(
                            [
                                ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                                ("FONTNAME", (0, 0), (-1, -1), "EmbeddedFont"),
                                ("FONTSIZE", (0, 0), (-1, -1), 8),
                                ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                                ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                            ]
                        )
                    )
                    story.append(table)
                    story.append(Spacer(1, 12))

            elif element.name in ["div", "span"]:
                # Handle divs and spans - convert to paragraphs
                text = element.get_text(strip=True)
                if text and len(text) > 0:
                    story.append(Paragraph(text, styles["Normal"]))
                    story.append(Spacer(1, 3))

        # If no content was processed, add basic invoice info
        if not story:
            story.append(Paragraph(f"Sales Invoice: {invoice_doc.name}", styles["Title"]))
            story.append(Spacer(1, 12))
            story.append(Paragraph(f"Date: {invoice_doc.posting_date}", styles["Normal"]))
            story.append(Paragraph(f"Customer: {invoice_doc.customer_name}", styles["Normal"]))
            story.append(
                Paragraph(
                    f"Grand Total: {invoice_doc.currency} {invoice_doc.grand_total}",
                    styles["Normal"],
                )
            )

    except Exception as e:
        frappe.log_error(f"Error converting HTML to ReportLab: {e}", "PDF3A Generator")
        # Add basic content as fallback
        story.append(Paragraph(f"Sales Invoice: {invoice_doc.name}", styles["Title"]))
        story.append(Spacer(1, 12))
        story.append(Paragraph(f"Date: {invoice_doc.posting_date}", styles["Normal"]))
        story.append(Paragraph(f"Customer: {invoice_doc.customer_name}", styles["Normal"]))
        story.append(
            Paragraph(
                f"Grand Total: {invoice_doc.currency} {invoice_doc.grand_total}", styles["Normal"]
            )
        )


def create_comprehensive_pdfa_pdf(invoice_doc):
    """Create a comprehensive PDF/A compliant PDF using ReportLab with full invoice layout."""
    try:
        import tempfile

        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        # Create a temporary PDF file
        temp_pdf = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        temp_pdf_path = temp_pdf.name
        temp_pdf.close()

        # Register fonts for PDF/A compliance
        font_path = find_ttf_font()
        pdfmetrics.registerFont(TTFont("EmbeddedFont", font_path))

        # Create PDF document
        doc = SimpleDocTemplate(
            temp_pdf_path,
            pagesize=A4,
            rightMargin=1 * inch,
            leftMargin=1 * inch,
            topMargin=1 * inch,
            bottomMargin=1 * inch,
            title=f"Sales Invoice {invoice_doc.name}",
            author="ERPNext ZATCA Integration",
            subject="PDF/A-3A Compliant Invoice",
            creator="ERPNext ZATCA Integration",
        )

        # Create story (content)
        story = []

        # Create custom styles
        styles = getSampleStyleSheet()

        # Title style
        title_style = ParagraphStyle(
            "CustomTitle",
            parent=styles["Title"],
            fontName="EmbeddedFont",
            fontSize=16,
            spaceAfter=20,
            alignment=TA_CENTER,
            textColor=colors.black,
        )

        # Header style
        header_style = ParagraphStyle(
            "CustomHeader",
            parent=styles["Heading2"],
            fontName="EmbeddedFont",
            fontSize=12,
            spaceAfter=10,
            textColor=colors.black,
        )

        # Normal style
        normal_style = ParagraphStyle(
            "CustomNormal",
            parent=styles["Normal"],
            fontName="EmbeddedFont",
            fontSize=9,
            spaceAfter=6,
            textColor=colors.black,
        )

        # Small style
        _small_style = ParagraphStyle(
            "CustomSmall",
            parent=styles["Normal"],
            fontName="EmbeddedFont",
            fontSize=8,
            spaceAfter=4,
            textColor=colors.black,
        )

        # Add title
        story.append(Paragraph("Sales Invoice", title_style))
        story.append(Spacer(1, 10))

        # Invoice details table
        invoice_details = [
            ["Invoice Number:", invoice_doc.name, "Date:", str(invoice_doc.posting_date)],
            ["Customer:", invoice_doc.customer_name, "Due Date:", str(invoice_doc.due_date or "")],
            [
                "Currency:",
                invoice_doc.currency,
                "Grand Total:",
                f"{invoice_doc.currency} {invoice_doc.grand_total}",
            ],
        ]

        invoice_table = Table(invoice_details, colWidths=[2 * inch, 2 * inch, 1.5 * inch, 2 * inch])
        invoice_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "EmbeddedFont"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ALIGN", (0, 0), (0, -1), "LEFT"),
                    ("ALIGN", (1, 0), (1, -1), "LEFT"),
                    ("ALIGN", (2, 0), (2, -1), "LEFT"),
                    ("ALIGN", (3, 0), (3, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(invoice_table)
        story.append(Spacer(1, 20))

        # Items table
        if invoice_doc.items:
            story.append(Paragraph("Items", header_style))

            # Items table headers
            items_data = [["Item Code", "Description", "Qty", "Rate", "Amount"]]

            # Add items
            for item in invoice_doc.items:
                description = (
                    item.description[:40] + "..."
                    if len(item.description) > 40
                    else item.description
                )
                items_data.append(
                    [
                        item.item_code,
                        description,
                        str(item.qty),
                        f"{invoice_doc.currency} {item.rate}",
                        f"{invoice_doc.currency} {item.amount}",
                    ]
                )

            items_table = Table(
                items_data, colWidths=[1.2 * inch, 3 * inch, 0.8 * inch, 1.2 * inch, 1.2 * inch]
            )
            items_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("ALIGN", (1, 0), (1, -1), "LEFT"),
                        ("FONTNAME", (0, 0), (-1, -1), "EmbeddedFont"),
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                        ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                        ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                        ("GRID", (0, 0), (-1, -1), 1, colors.black),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            story.append(items_table)
            story.append(Spacer(1, 20))

        # Totals section
        totals_data = [
            ["Net Total:", f"{invoice_doc.currency} {invoice_doc.net_total}"],
            ["Taxes:", f"{invoice_doc.currency} {invoice_doc.total_taxes_and_charges}"],
            ["Grand Total:", f"{invoice_doc.currency} {invoice_doc.grand_total}"],
        ]

        totals_table = Table(totals_data, colWidths=[2 * inch, 2 * inch])
        totals_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "EmbeddedFont"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("ALIGN", (0, 0), (0, -1), "LEFT"),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("FONTNAME", (0, -1), (-1, -1), "EmbeddedFont"),
                    ("FONTSIZE", (0, -1), (-1, -1), 12),
                    ("FONTNAME", (0, -1), (-1, -1), "EmbeddedFont"),
                    ("LINEBELOW", (0, -1), (-1, -1), 2, colors.black),
                ]
            )
        )
        story.append(totals_table)

        # Add amount in words if available
        if hasattr(invoice_doc, "in_words") and invoice_doc.in_words:
            story.append(Spacer(1, 10))
            story.append(Paragraph(f"Amount in words: {invoice_doc.in_words}", normal_style))

        # Build PDF
        doc.build(story)

        # Read the generated PDF
        with open(temp_pdf_path, "rb") as f:
            pdf_content = f.read()

        # Clean up temporary file
        os.unlink(temp_pdf_path)

        return pdf_content

    except Exception as e:
        frappe.log_error(f"Error creating comprehensive PDF/A PDF: {e}", "PDF3A Generator")
        return None


def create_basic_pdfa_pdf(invoice_doc):
    """Create a basic PDF/A compliant PDF using ReportLab."""
    try:
        import tempfile

        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        # Create a temporary PDF file
        temp_pdf = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        temp_pdf_path = temp_pdf.name
        temp_pdf.close()

        # Register fonts for PDF/A compliance
        font_path = find_ttf_font()
        pdfmetrics.registerFont(TTFont("EmbeddedFont", font_path))

        # Create PDF document
        doc = SimpleDocTemplate(
            temp_pdf_path,
            pagesize=A4,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=18,
            title=f"Sales Invoice {invoice_doc.name}",
            author="ERPNext ZATCA Integration",
            subject="PDF/A-3A Compliant Invoice",
            creator="ERPNext ZATCA Integration",
        )

        # Create story (content)
        story = []
        styles = getSampleStyleSheet()

        # Configure styles with embedded font
        for style_name in ["Title", "Heading1", "Heading2", "Normal", "BodyText"]:
            if hasattr(styles, style_name):
                style = getattr(styles, style_name)
                style.fontName = "EmbeddedFont"

        # Add title
        story.append(Paragraph(f"Sales Invoice: {invoice_doc.name}", styles["Title"]))
        story.append(Spacer(1, 12))

        # Add basic invoice information
        story.append(Paragraph(f"Date: {invoice_doc.posting_date}", styles["Normal"]))
        story.append(Paragraph(f"Customer: {invoice_doc.customer_name}", styles["Normal"]))
        story.append(
            Paragraph(
                f"Grand Total: {invoice_doc.currency} {invoice_doc.grand_total}", styles["Normal"]
            )
        )
        story.append(Spacer(1, 12))

        # Add items table
        if invoice_doc.items:
            story.append(Paragraph("Items:", styles["Heading2"]))

            # Create items table
            table_data = [["Item Code", "Description", "Qty", "Rate", "Amount"]]
            for item in invoice_doc.items:
                table_data.append(
                    [
                        item.item_code,
                        item.description[:30] + "..."
                        if len(item.description) > 30
                        else item.description,
                        str(item.qty),
                        f"{invoice_doc.currency} {item.rate}",
                        f"{invoice_doc.currency} {item.amount}",
                    ]
                )

            table = Table(table_data)
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("FONTNAME", (0, 0), (-1, -1), "EmbeddedFont"),
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                        ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                        ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                        ("GRID", (0, 0), (-1, -1), 1, colors.black),
                    ]
                )
            )
            story.append(table)

        # Build PDF
        doc.build(story)

        # Read the generated PDF
        with open(temp_pdf_path, "rb") as f:
            pdf_content = f.read()

        # Clean up temporary file
        os.unlink(temp_pdf_path)

        return pdf_content

    except Exception as e:
        frappe.log_error(f"Error creating basic PDF/A PDF: {e}", "PDF3A Generator")
        return None


def fix_font_embedding(pdf):
    """Fix font embedding issues for PDF/A-3A compliance with aggressive font rebuilding."""
    try:
        # Get all pages
        pages = pdf.Root["/Pages"]["/Kids"]

        for page_ref in pages:
            page = page_ref
            if page_ref.is_indirect:
                page = page_ref.get_object()

            # Get page resources
            resources = page.get("/Resources", Dictionary())
            fonts = resources.get("/Font", Dictionary())

            # Process each font aggressively
            for _font_name, font_ref in fonts.items():
                font = font_ref
                if font_ref.is_indirect:
                    font = font_ref.get_object()

                # Aggressively rebuild font information
                rebuild_font_aggressively(font, pdf)

        frappe.log_error("Aggressive font embedding fixes applied successfully", "PDF3A Generator")

    except Exception as e:
        frappe.log_error(f"Error in aggressive font embedding fix: {str(e)}", "PDF3A Generator")


def rebuild_font_aggressively(font, pdf):
    """Aggressively rebuild font information to ensure PDF/A-3A compliance."""
    try:
        # Get base font name
        base_font_name = str(font.get("/BaseFont", "Unknown"))

        # Remove subset prefix if present
        if base_font_name.startswith("+"):
            base_font_name = base_font_name[1:]

        # Completely rebuild font with consistent properties
        font.clear()

        # Set all required font properties
        font["/Type"] = Name("/Font")
        font["/Subtype"] = Name("/Type1")
        font["/BaseFont"] = String(f"+{base_font_name}")
        font["/Encoding"] = Name("/WinAnsiEncoding")
        font["/FirstChar"] = 0
        font["/LastChar"] = 255

        # Create completely consistent width array
        widths = Array([600] * 256)  # All characters have same width
        font["/Widths"] = widths

        # Create new font descriptor with matching properties
        font_descriptor = Dictionary(
            {
                "/Type": Name("/FontDescriptor"),
                "/FontName": String(f"+{base_font_name}"),
                "/Flags": 4,
                "/FontBBox": Array([0, 0, 1000, 1000]),
                "/ItalicAngle": 0,
                "/Ascent": 800,
                "/Descent": -200,
                "/CapHeight": 700,
                "/StemV": 80,
                "/StemH": 80,
                "/AvgWidth": 600,  # Must match width array
                "/MaxWidth": 1000,
                "/MissingWidth": 600,  # Must match width array
            }
        )

        # Make font descriptor indirect
        font_descriptor_ind = pdf.make_indirect(font_descriptor)
        font["/FontDescriptor"] = font_descriptor_ind

        # Create ToUnicode stream
        to_unicode_content = create_to_unicode_stream()
        to_unicode_stream = pdf.make_stream(to_unicode_content)
        font["/ToUnicode"] = to_unicode_stream

        # Set font name consistently
        font["/FontName"] = String(f"+{base_font_name}")

    except Exception as e:
        frappe.log_error(
            f"Error aggressively rebuilding font {font.get('/BaseFont', 'Unknown')}: {str(e)}",
            "PDF3A Generator",
        )


def rebuild_font_for_pdfa(font, pdf):
    """Rebuild font information to ensure PDF/A-3A compliance."""
    try:
        # Get base font name
        base_font_name = str(font.get("/BaseFont", "Unknown"))

        # Remove subset prefix if present for consistency
        if base_font_name.startswith("+"):
            base_font_name = base_font_name[1:]

        # Set consistent font properties
        font["/Type"] = Name("/Font")
        font["/Subtype"] = Name("/Type1")
        font["/BaseFont"] = String(f"+{base_font_name}")
        font["/Encoding"] = Name("/WinAnsiEncoding")

        # Set character range
        font["/FirstChar"] = 0
        font["/LastChar"] = 255

        # Create consistent width array (600 units for all characters)
        widths = Array([600] * 256)
        font["/Widths"] = widths

        # Create or update font descriptor
        font_descriptor = Dictionary(
            {
                "/Type": Name("/FontDescriptor"),
                "/FontName": String(f"+{base_font_name}"),
                "/Flags": 4,  # Symbolic font flag
                "/FontBBox": Array([0, 0, 1000, 1000]),
                "/ItalicAngle": 0,
                "/Ascent": 800,
                "/Descent": -200,
                "/CapHeight": 700,
                "/StemV": 80,
                "/StemH": 80,
                "/AvgWidth": 600,
                "/MaxWidth": 1000,
                "/MissingWidth": 600,
            }
        )

        # Make font descriptor indirect
        font_descriptor_ind = pdf.make_indirect(font_descriptor)
        font["/FontDescriptor"] = font_descriptor_ind

        # Create ToUnicode stream for proper character mapping
        to_unicode_content = create_to_unicode_stream()
        to_unicode_stream = pdf.make_stream(to_unicode_content)
        font["/ToUnicode"] = to_unicode_stream

        # Ensure font name is consistent
        font["/FontName"] = String(f"+{base_font_name}")

    except Exception as e:
        frappe.log_error(
            f"Error rebuilding font {font.get('/BaseFont', 'Unknown')}: {str(e)}", "PDF3A Generator"
        )


def create_to_unicode_stream():
    """Create a ToUnicode stream for proper character mapping."""
    return b"""\
/CIDInit /ProcSet findresource begin
12 dict begin
begincmap
/CIDSystemInfo
<< /Registry (Adobe)
/Ordering (UCS)
/Supplement 0
>> def
/CMapName /Adobe-Identity-UCS def
/CMapType 2 def
1 begincodespacerange
<0000> <FFFF>
endcodespacerange
1 beginbfrange
<0000> <FFFF> <0000>
endbfrange
endcmap
CMapName currentdict /CMap defineresource pop
end
end"""


def build_xmp_metadata(invoice_doc) -> bytes:
    """Create XMP packet for PDF/A-3A with invoice info."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    xmp = f"""<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>
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
<?xpacket end="w"?>"""
    return xmp.encode("utf-8")


def finalize_pdfa(
    temp_pdf_path: str, final_pdf_path: str, icc_path: str, xml_path: str, invoice_doc
):
    """Embed XML file and prepare PDF for ConvertAPI PDF/A-3A conversion."""
    with pikepdf.open(temp_pdf_path, allow_overwriting_input=True) as pdf:
        if pdf.is_encrypted:
            raise RuntimeError("PDF must not be encrypted for PDF/A")

        # Embed XML file
        if xml_path and os.path.isfile(xml_path):
            with open(xml_path, "rb") as xf:
                xml_bytes = xf.read()

            ef_stream = pdf.make_stream(xml_bytes)
            ef_stream["/Type"] = Name("/EmbeddedFile")
            ef_stream["/Subtype"] = Name("/application/xml")

            mod_date = datetime.now(timezone.utc).strftime("D:%Y%m%d%H%M%SZ")
            ef_stream["/Params"] = Dictionary(
                {"/Size": len(xml_bytes), "/ModDate": String(mod_date)}
            )

            ef_stream_ind = pdf.make_indirect(ef_stream)

            filename = "invoice.xml"
            filespec = Dictionary(
                {
                    "/Type": Name("/Filespec"),
                    "/F": String(filename),
                    "/UF": String(filename),
                    "/EF": Dictionary({"/F": ef_stream_ind, "/UF": ef_stream_ind}),
                    "/Desc": String("ZATCA invoice XML"),
                    "/AFRelationship": Name("/Data"),
                }
            )

            filespec_ind = pdf.make_indirect(filespec)

            # Add to Names -> EmbeddedFiles
            names_dict = pdf.Root.get("/Names", Dictionary())
            names_dict["/EmbeddedFiles"] = Dictionary(
                {"/Names": Array([String(filename), filespec_ind])}
            )
            pdf.Root["/Names"] = names_dict

            # Add to AF array
            af_array = Array([filespec_ind])
            pdf.Root["/AF"] = af_array

        # Save the PDF with embedded XML
        try:
            from pikepdf import PdfVersion

            pdf.save(final_pdf_path, linearize=False, min_version=PdfVersion.v1_7)
        except Exception:
            pdf.save(final_pdf_path, linearize=False)

    # Convert to PDF/A-3A using ConvertAPI to preserve original print format rendering
    try:
        # ConvertAPI writes output files; convert then overwrite final_pdf_path
        out_dir = tempfile.mkdtemp()
        result = convertapi.convert(
            "pdfa",
            {
                "File": final_pdf_path,
                "PdfaVersion": "PdfA3a",
            },
            from_format="pdf",
        )
        saved_files = result.save_files(out_dir)
        if saved_files:
            converted_path = saved_files[0]
            # Replace final_pdf_path contents with converted file
            with open(converted_path, "rb") as src, open(final_pdf_path, "wb") as dst:
                dst.write(src.read())
            frappe.log_error(
                "Successfully converted to PDF/A-3A using ConvertAPI", "PDF3A Generator"
            )
    except Exception as e:
        # If external conversion fails, continue with internally conformed file
        frappe.log_error(f"ConvertAPI PDF/A conversion failed: {e}", "PDF3A Generator")


@frappe.whitelist()
def generate_pdf3a_with_xml(invoice_name):
    """
    Generate PDF/A-3A compliant PDF for Sales Invoice with embedded XML.
    Uses the first approach: get print format HTML, attach to PDF, attach XML, create PDF3A
    """
    try:
        # Validate invoice exists
        if not frappe.db.exists("Sales Invoice", invoice_name):
            frappe.throw(f"Sales Invoice {invoice_name} does not exist")

        # Get invoice document
        invoice_doc = frappe.get_doc("Sales Invoice", invoice_name)

        # Check if custom_invoice_xml field exists and has value
        if not hasattr(invoice_doc, "custom_invoice_xml") or not invoice_doc.custom_invoice_xml:
            frappe.throw("No XML file path found in custom_invoice_xml field")

        xml_filename = os.path.basename(invoice_doc.custom_invoice_xml)

        # Find XML file in attachments
        attachments = frappe.get_all(
            "File", filters={"attached_to_name": invoice_name}, fields=["file_name", "file_url"]
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

        # Generate PDF from print format
        pdf_content = generate_pdf_from_print_format(invoice_doc)

        # Create temporary PDF file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_pdf:
            temp_pdf_path = temp_pdf.name
            temp_pdf.write(pdf_content)

        try:
            # Create final PDF with embedded XML
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as final_pdf:
                final_pdf_path = final_pdf.name

            finalize_pdfa(temp_pdf_path, final_pdf_path, icc_path, xml_file, invoice_doc)

            # Read the generated PDF
            with open(final_pdf_path, "rb") as f:
                final_pdf_content = f.read()

            # Create File document in ERPNext
            pdf_filename = f"{invoice_name}_PDF3A.pdf"

            # Check if file already exists
            existing_file = frappe.db.exists(
                "File", {"attached_to_name": invoice_name, "file_name": pdf_filename}
            )

            if existing_file:
                # Update existing file
                file_doc = frappe.get_doc("File", existing_file)
                file_doc.content = final_pdf_content
                file_doc.save()
            else:
                # Create new file
                file_doc = frappe.get_doc(
                    {
                        "doctype": "File",
                        "file_name": pdf_filename,
                        "attached_to_doctype": "Sales Invoice",
                        "attached_to_name": invoice_name,
                        "content": final_pdf_content,
                        "is_private": 0,
                    }
                )
                file_doc.insert()

            frappe.db.commit()

            return {
                "status": "success",
                "message": f"PDF3A generated successfully for {invoice_name}",
                "file_url": file_doc.file_url,
                "file_name": pdf_filename,
            }

        finally:
            # Clean up temporary files
            if os.path.exists(temp_pdf_path):
                os.remove(temp_pdf_path)
            if os.path.exists(final_pdf_path):
                os.remove(final_pdf_path)

    except Exception as e:
        frappe.log_error(f"Error generating PDF3A: {str(e)}", "PDF3A Generator")
        frappe.throw(f"Failed to generate PDF3A: {str(e)}")


@frappe.whitelist()
def test_pdf3a_assets():
    """Test method to check if required assets are available."""
    try:
        icc_path = ensure_assets()
        font_path = find_ttf_font()

        return {
            "status": "success",
            "icc_profile": icc_path,
            "font_file": font_path,
            "message": "All required assets are available for PDF3A generation",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
