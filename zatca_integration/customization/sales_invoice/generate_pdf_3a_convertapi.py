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


# # ruff: noqa: E501

# """
# Generate PDF/A-3A compliant PDF for Frappe Sales Invoice with embedded XML
# This method uses the first approach: get print format HTML, attach to PDF, attach XML, create PDF3A
# """

# import os
# import base64
# import subprocess
# import tempfile
# from datetime import datetime, timezone
# from pathlib import Path

# import frappe
# import pikepdf
# from frappe.utils.pdf import get_pdf
# from pikepdf import Array, Dictionary, Name, String
# import fitz  # PyMuPDF
# from urllib.parse import urljoin
# import mimetypes
# import re

# # Configuration paths
# font_dir = Path(frappe.get_app_path("zatca_integration", "public", "fonts"))
# icc_ = Path(frappe.get_app_path("zatca_integration", "public"))
# icc_2014 = icc_ / "sRGB2014.icc"

# cairo_regular = str(font_dir / "Cairo-Regular.ttf")

# EMBEDDED_SRGB_ICC = icc_2014
# EMBEDDED_FONT_TTF = cairo_regular

# # Note: ConvertAPI removed due to cost - using Ghostscript for PDF/A-3A conversion


# def find_ttf_font() -> str:
#     """Return a TTF path to embed. Prefer bundled Cairo font; otherwise try common system fonts."""
#     if os.path.isfile(EMBEDDED_FONT_TTF):
#         return EMBEDDED_FONT_TTF

#     candidates = [
#         "/Library/Fonts/Arial.ttf",
#         "/Library/Fonts/Verdana.ttf",
#         "/Library/Fonts/Tahoma.ttf",
#         "/Library/Fonts/Times New Roman.ttf",
#         "/Library/Fonts/Courier New.ttf",
#         "/System/Library/Fonts/Supplemental/Arial.ttf",
#         "/System/Library/Fonts/Supplemental/Verdana.ttf",
#         "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
#         "/System/Library/Fonts/Supplemental/Courier New.ttf",
#     ]
#     for p in candidates:
#         if os.path.isfile(p):
#             return p

#     raise FileNotFoundError(
#         "No embeddable TTF font found. Place Cairo-Regular.ttf in fonts/ or ensure a system TTF like Arial.ttf exists."
#     )


# def inject_font_css(html: str) -> str:
#     """Inject @font-face with embedded TTF (base64) and force usage across the document.
#     This ensures Chromium uses a single embedded TrueType font for all text.
#     """
#     try:
#         font_path = find_ttf_font()
#         with open(font_path, "rb") as f:
#             font_b64 = base64.b64encode(f.read()).decode("ascii")
#         style = (
#             "<style>@font-face{font-family:'EmbeddedFont';src:url(data:font/ttf;base64," + font_b64 +
#             ") format('truetype');font-weight:normal;font-style:normal;}"
#             "html,body,*{font-family:'EmbeddedFont' !important;}</style>"
#         )
#         # Prepend style inside head or at top
#         if "</head>" in html:
#             return html.replace("</head>", style + "</head>")
#         return style + html
#     except Exception as e:
#         frappe.log_error(f"Failed to inject font CSS: {e}", "PDF3A Generator")
#         return html


# def normalize_asset_urls(html: str) -> str:
#     """Ensure all src/href URLs in HTML are absolute and inject a <base> href.
#     Fixes broken images/styles when rendering outside Frappe.
#     """
#     try:
#         from bs4 import BeautifulSoup  # already used elsewhere in this module
#     except Exception as e:
#         frappe.log_error(f"BeautifulSoup import failed: {e}", "PDF3A Generator")
#         return html

#     try:
#         site_url = frappe.utils.get_url()
#         if not site_url.endswith("/"):
#             site_url = site_url + "/"

#         soup = BeautifulSoup(html or "", "html.parser")

#         # Inject <base href> for resolving relative URLs in CSS, images, links
#         head = soup.find("head")
#         base_tag_needed = True
#         if head:
#             existing_base = head.find("base")
#             if existing_base and existing_base.get("href"):
#                 base_tag_needed = False
#         if base_tag_needed:
#             base_tag = soup.new_tag("base", href=site_url)
#             if not head:
#                 head = soup.new_tag("head")
#                 soup.insert(0, head)
#             head.insert(0, base_tag)

#         # Rewrite src and href attributes to absolute when they are relative
#         def absolutize(value: str) -> str:
#             if not value:
#                 return value
#             # Skip data URIs and javascript/mailto
#             if value.startswith("data:") or value.startswith("javascript:") or value.startswith("mailto:"):
#                 return value
#             # If already absolute (http/https), keep
#             if value.startswith("http://") or value.startswith("https://"):
#                 return value
#             # Otherwise, join with site_url
#             return urljoin(site_url, value)

#         for tag in soup.find_all(True):
#             if tag.has_attr("src"):
#                 tag["src"] = absolutize(tag.get("src"))
#             if tag.has_attr("href"):
#                 tag["href"] = absolutize(tag.get("href"))
#             # Inline styles: url(...) references
#             style_val = tag.get("style")
#             if style_val and "url(" in style_val:
#                 try:
#                     # Replace url(/path) with absolute URL
#                     tag["style"] = re.sub(r"url\((['\"]?)(/[^)\"']+)\1\)", lambda m: f"url({urljoin(site_url, m.group(2))})", style_val)
#                 except Exception:
#                     pass

#         return str(soup)
#     except Exception as e:
#         frappe.log_error(f"Failed to normalize asset URLs: {e}", "PDF3A Generator")
#         return html


# def embed_local_images_as_data_uri(html: str) -> str:
#     """Embed local images and CSS background urls as data URIs to avoid broken links.
#     Converts src/href pointing to /files, /assets, or relative paths to inline base64.
#     """
#     try:
#         from bs4 import BeautifulSoup
#     except Exception as e:
#         frappe.log_error(f"BeautifulSoup import failed: {e}", "PDF3A Generator")
#         return html

#     try:
#         site_path = frappe.local.site_path if getattr(frappe, "local", None) else frappe.get_site_path()
#         if not site_path:
#             return html

#         def to_fs_path(url_path: str) -> str | None:
#             if not url_path or url_path.startswith("http://") or url_path.startswith("https://") or url_path.startswith("data:"):
#                 return None
#             # Strip query/hash
#             clean_path = url_path.split("?")[0].split("#")[0]
#             # Ensure leading slash handling
#             if clean_path.startswith("/files/"):
#                 return os.path.join(site_path, "public", clean_path.lstrip("/"))
#             if clean_path.startswith("/assets/"):
#                 return os.path.join(site_path, clean_path.lstrip("/"))
#             if clean_path.startswith("/"):
#                 # Try under public first
#                 cand = os.path.join(site_path, "public", clean_path.lstrip("/"))
#                 if os.path.isfile(cand):
#                     return cand
#                 cand2 = os.path.join(site_path, clean_path.lstrip("/"))
#                 return cand2 if os.path.isfile(cand2) else None
#             # relative path: try under public
#             cand = os.path.join(site_path, "public", clean_path)
#             if os.path.isfile(cand):
#                 return cand
#             cand2 = os.path.join(site_path, clean_path)
#             return cand2 if os.path.isfile(cand2) else None

#         def file_to_data_uri(fp: str) -> str | None:
#             try:
#                 mime, _ = mimetypes.guess_type(fp)
#                 if not mime:
#                     mime = "application/octet-stream"
#                 with open(fp, "rb") as f:
#                     b64 = base64.b64encode(f.read()).decode("ascii")
#                 return f"data:{mime};base64,{b64}"
#             except Exception as e:
#                 frappe.log_error(f"Failed to inline file {fp}: {e}", "PDF3A Generator")
#                 return None

#         soup = BeautifulSoup(html or "", "html.parser")

#         # Inline <img src>
#         for img in soup.find_all("img"):
#             src = img.get("src")
#             fs = to_fs_path(src)
#             if fs and os.path.isfile(fs):
#                 data_uri = file_to_data_uri(fs)
#                 if data_uri:
#                     img["src"] = data_uri

#         # Inline CSS background-image urls in style attributes
#         for tag in soup.find_all(True):
#             style_val = tag.get("style")
#             if not style_val:
#                 continue
#             # Find all url(...) occurrences
#             urls = re.findall(r"url\((['\"]?)([^)\"']+)\1\)", style_val)
#             new_style = style_val
#             for _, url_path in urls:
#                 fs = to_fs_path(url_path)
#                 if fs and os.path.isfile(fs):
#                     data_uri = file_to_data_uri(fs)
#                     if data_uri:
#                         new_style = new_style.replace(url_path, data_uri)
#             if new_style != style_val:
#                 tag["style"] = new_style

#         return str(soup)
#     except Exception as e:
#         frappe.log_error(f"Failed to embed local images: {e}", "PDF3A Generator")
#         return html


# def generate_pdf_from_print_format_template(invoice_doc):
#     """Generate PDF directly from print format Jinja template using ReportLab for perfect font consistency."""
#     try:
#         import tempfile
#         from reportlab.lib.pagesizes import A4
#         from reportlab.lib import colors
#         from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
#         from reportlab.lib.units import inch
#         from reportlab.pdfbase import pdfmetrics
#         from reportlab.pdfbase.ttfonts import TTFont
#         from reportlab.platypus import (
#             Paragraph,
#             SimpleDocTemplate,
#             Spacer,
#             Table,
#             TableStyle,
#         )
        
#         # Get print format template
#         pf = frappe.get_doc("Print Format", "Zatca PDF-A 3B")
#         doc = frappe.get_doc("Sales Invoice", invoice_doc.name)
        
#         # Render Jinja template to get structured data
#         template_data = frappe.render_template(pf.html, {"doc": doc.as_dict(), "no_letterhead": 0})
        
#         # Create temporary PDF file
#         temp_pdf = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
#         temp_pdf_path = temp_pdf.name
#         temp_pdf.close()
        
#         # Register embedded font for perfect consistency
#         font_path = find_ttf_font()
#         pdfmetrics.registerFont(TTFont("EmbeddedFont", font_path))
        
#         # Create PDF document with proper metadata
#         doc_pdf = SimpleDocTemplate(
#             temp_pdf_path,
#             pagesize=A4,
#             rightMargin=1*inch,
#             leftMargin=1*inch,
#             topMargin=1*inch,
#             bottomMargin=1*inch,
#             title=f"Sales Invoice {invoice_doc.name}",
#             author="ERPNext ZATCA Integration",
#             subject="PDF/A-3A Compliant Invoice",
#             creator="ERPNext ZATCA Integration",
#         )
        
#         # Create story (content)
#         story = []
#         styles = getSampleStyleSheet()
        
#         # Configure all styles with embedded font
#         for style_name in ['Title', 'Heading1', 'Heading2', 'Normal', 'BodyText']:
#             if hasattr(styles, style_name):
#                 style = getattr(styles, style_name)
#                 style.fontName = "EmbeddedFont"
        
#         # Add title
#         story.append(Paragraph(f"Sales Invoice: {invoice_doc.name}", styles['Title']))
#         story.append(Spacer(1, 12))
        
#         # Add invoice details
#         details_data = [
#             ["Invoice Number:", invoice_doc.name],
#             ["Date:", str(invoice_doc.posting_date)],
#             ["Customer:", invoice_doc.customer_name],
#             ["Due Date:", str(invoice_doc.due_date or "")],
#             ["Currency:", invoice_doc.currency],
#             ["Grand Total:", f"{invoice_doc.currency} {invoice_doc.grand_total}"],
#         ]
        
#         details_table = Table(details_data, colWidths=[2*inch, 3*inch])
#         details_table.setStyle(TableStyle([
#             ('FONTNAME', (0, 0), (-1, -1), 'EmbeddedFont'),
#             ('FONTSIZE', (0, 0), (-1, -1), 10),
#             ('ALIGN', (0, 0), (0, -1), 'LEFT'),
#             ('ALIGN', (1, 0), (1, -1), 'LEFT'),
#             ('VALIGN', (0, 0), (-1, -1), 'TOP'),
#             ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
#         ]))
#         story.append(details_table)
#         story.append(Spacer(1, 20))
        
#         # Add items table
#         if invoice_doc.items:
#             story.append(Paragraph("Items", styles['Heading2']))
            
#             items_data = [["Item Code", "Description", "Qty", "Rate", "Amount"]]
#             for item in invoice_doc.items:
#                 description = item.description[:40] + "..." if len(item.description) > 40 else item.description
#                 items_data.append([
#                     item.item_code,
#                     description,
#                     str(item.qty),
#                     f"{invoice_doc.currency} {item.rate}",
#                     f"{invoice_doc.currency} {item.amount}"
#                 ])
            
#             items_table = Table(items_data, colWidths=[1.2*inch, 3*inch, 0.8*inch, 1.2*inch, 1.2*inch])
#             items_table.setStyle(TableStyle([
#                 ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
#                 ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
#                 ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
#                 ('ALIGN', (1, 0), (1, -1), 'LEFT'),
#                 ('FONTNAME', (0, 0), (-1, -1), 'EmbeddedFont'),
#                 ('FONTSIZE', (0, 0), (-1, -1), 8),
#                 ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
#                 ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
#                 ('GRID', (0, 0), (-1, -1), 1, colors.black),
#                 ('VALIGN', (0, 0), (-1, -1), 'TOP'),
#             ]))
#             story.append(items_table)
#             story.append(Spacer(1, 20))
        
#         # Add totals
#         totals_data = [
#             ["Net Total:", f"{invoice_doc.currency} {invoice_doc.net_total}"],
#             ["Taxes:", f"{invoice_doc.currency} {invoice_doc.total_taxes_and_charges}"],
#             ["Grand Total:", f"{invoice_doc.currency} {invoice_doc.grand_total}"],
#         ]
        
#         totals_table = Table(totals_data, colWidths=[2*inch, 2*inch])
#         totals_table.setStyle(TableStyle([
#             ('FONTNAME', (0, 0), (-1, -1), 'EmbeddedFont'),
#             ('FONTSIZE', (0, 0), (-1, -1), 10),
#             ('ALIGN', (0, 0), (0, -1), 'LEFT'),
#             ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
#             ('FONTNAME', (0, -1), (-1, -1), 'EmbeddedFont'),
#             ('FONTSIZE', (0, -1), (-1, -1), 12),
#             ('LINEBELOW', (0, -1), (-1, -1), 2, colors.black),
#         ]))
#         story.append(totals_table)
        
#         # Build PDF
#         doc_pdf.build(story)
        
#         # Read the generated PDF
#         with open(temp_pdf_path, "rb") as f:
#             pdf_content = f.read()
        
#         # Clean up temporary file
#         os.unlink(temp_pdf_path)
        
#         return pdf_content
        
#     except Exception as e:
#         frappe.log_error(f"Error generating PDF from print format template: {e}", "PDF3A Generator")
#         return None


# def generate_pdf_with_chromium(html: str) -> bytes | None:
#     """Render HTML to PDF using headless Chromium (Playwright). Returns PDF bytes or None."""
#     try:
#         from playwright.sync_api import sync_playwright
#     except ImportError as e:
#         frappe.log_error(f"Playwright not installed: {e}. Install with: pip install playwright && python -m playwright install chromium", "PDF3A Generator")
#         return None
#     except Exception as e:
#         frappe.log_error(f"Playwright import error: {e}", "PDF3A Generator")
#         return None

#     try:
#         pdf_bytes: bytes | None = None
#         with sync_playwright() as p:
#             browser = p.chromium.launch(headless=True, args=["--no-sandbox"])  # server-safe
#             context = browser.new_context()
#             page = context.new_page()
#             # Ensure print CSS is applied
#             page.set_content(html, wait_until="networkidle")
#             pdf_bytes = page.pdf(
#                 format="A4",
#                 print_background=True,
#                 prefer_css_page_size=True,
#                 margin={
#                     "top": "0.75in",
#                     "right": "0.75in",
#                     "bottom": "0.75in",
#                     "left": "0.75in",
#                 },
#                 scale=1,
#             )
#             context.close()
#             browser.close()
#         return pdf_bytes
#     except Exception as e:
#         frappe.log_error(f"Chromium PDF render failed: {e}", "PDF3A Generator")
#         return None


# def ensure_assets():
#     """Ensure required assets exist; if not, attempt to locate system equivalents."""
#     _ = find_ttf_font()

#     if os.path.isfile(EMBEDDED_SRGB_ICC):
#         return EMBEDDED_SRGB_ICC

#     candidate_paths = [
#         "/System/Library/ColorSync/Profiles/sRGB Profile.icc",
#         "/System/Library/ColorSync/Profiles/sRGB Profile.icm",
#         "/Library/ColorSync/Profiles/sRGB Profile.icc",
#         "/Library/ColorSync/Profiles/sRGB Profile.icm",
#         "/System/Library/ColorSync/Profiles/sRGB IEC61966-2.1.icc",
#         "/Library/ColorSync/Profiles/sRGB IEC61966-2.1.icc",
#     ]

#     for p in candidate_paths:
#         if os.path.isfile(p):
#             return p

#     raise FileNotFoundError(
#         "sRGB ICC profile not found. Place 'sRGB2014.icc' under public/ or install a system sRGB profile."
#     )


# def check_ghostscript():
#     """Check if Ghostscript is installed and available."""
#     try:
#         result = subprocess.run(['gs', '--version'], capture_output=True, text=True, check=True)
#         version = result.stdout.strip()
#         frappe.log_error(f"Ghostscript version: {version}", "PDF3A Generator")
#         return True
#     except (subprocess.CalledProcessError, FileNotFoundError) as e:
#         frappe.log_error(f"Ghostscript not found: {e}. Please install Ghostscript for PDF/A-3A conversion.", "PDF3A Generator")
#         return False


# def convert_to_pdfa_with_ghostscript(input_pdf_path, output_pdf_path):
#     """Convert PDF to PDF/A-3A using Ghostscript with proper color space and font handling."""
#     try:
#         # Get ICC profile path for proper color space
#         icc_path = ensure_assets()
        
#         # Ghostscript command for PDF/A-3A conversion with proper color space and font handling
#         cmd = [
#             'gs',
#             '-dPDFA=3',                    # PDF/A-3A compliance
#             '-dBATCH',                     # Batch mode (no interactive prompts)
#             '-dNOPAUSE',                   # Don't pause between pages
#             '-sDEVICE=pdfwrite',           # Output device
#             '-dPDFACompatibilityPolicy=1', # PDF/A compatibility policy
#             '-dAutoRotatePages=/None',     # Don't auto-rotate pages
#             '-dColorImageDownsampleType=/Bicubic',
#             '-dColorImageResolution=300',
#             '-dGrayImageDownsampleType=/Bicubic',
#             '-dGrayImageResolution=300',
#             '-dMonoImageDownsampleType=/Bicubic',
#             '-dMonoImageResolution=300',
#             '-dEmbedAllFonts=true',        # Embed all fonts
#             '-dSubsetFonts=false',        # Don't subset fonts - this is crucial for font consistency
#             '-dCompressFonts=false',       # Don't compress fonts to avoid width issues
#             '-dNOPLATFONTS',              # Don't use platform fonts
#             '-dPDFSETTINGS=/prepress',     # High quality settings
#             '-sColorConversionStrategy=RGB', # Use RGB color conversion
#             f'-sOutputICCProfile={icc_path}', # Use our sRGB ICC profile
#             f'-sDefaultRGBProfile={icc_path}', # Set default RGB profile
#             '-dUseCIEColor',              # Use CIE color space
#             '-dOverrideICC=true',          # Override ICC profiles
#             f'-sOutputFile={output_pdf_path}',
#             input_pdf_path
#         ]
        
#         frappe.log_error("Running Ghostscript PDF/A-3A conversion", "PDF3A Generator")
#         result = subprocess.run(cmd, capture_output=True, text=True, check=True)
#         if result.stdout:
#             frappe.log_error(f"GS stdout: {result.stdout[:200]}", "PDF3A Generator")
#         if result.stderr:
#             frappe.log_error(f"GS stderr: {result.stderr[:200]}", "PDF3A Generator")
#         frappe.log_error("Successfully converted to PDF/A-3A using Ghostscript", "PDF3A Generator")
#         return True
        
#     except subprocess.CalledProcessError as e:
#         frappe.log_error(f"Ghostscript conversion failed: {e.stderr}", "PDF3A Generator")
#         return False
#     except Exception as e:
#         frappe.log_error(f"Error during Ghostscript conversion: {str(e)}", "PDF3A Generator")
#         return False


# def generate_pdf_from_print_format(invoice_doc):
#     """Generate PDF from print format HTML using default Zatca PDF-A 3B format."""
#     try:
#         # Generate HTML content from print format using default Zatca PDF-A 3B
#         html = frappe.get_print(
#             doctype="Sales Invoice",
#             name=invoice_doc.name,
#             print_format="Zatca PDF-A 3B",
#             no_letterhead=0,  # Include letterhead
#         )

#         # Debug: Log HTML content length
#         frappe.log_error(f"HTML content length: {len(html) if html else 0}", "PDF3A Generator")

#         if not html:
#             frappe.throw("Failed to generate HTML content from print format")

#         # Normalize asset URLs and embed local images to avoid broken links
#         html = normalize_asset_urls(html)
#         html = embed_local_images_as_data_uri(html)

#         # Use ONLY the print format HTML - inject font and render with Chromium/wkhtmltopdf
#         pdf_content = None

#         # Inject a single embedded TTF via @font-face to force consistent font
#         html_with_font = inject_font_css(html)

#         # Approach 1: Chromium (Playwright) - best for font consistency
#         pdf_content = generate_pdf_with_chromium(html_with_font)
#         if pdf_content:
#             frappe.log_error("PDF generated with Chromium from print format", "PDF3A Generator")
#         else:
#             # Approach 2: wkhtmltopdf fallback - still uses print format HTML
#             try:
#                 pdf_content = get_pdf(
#                     html_with_font,
#                     options={
#                         "page-size": "A4",
#                         "margin-top": "0.75in",
#                         "margin-right": "0.75in",
#                         "margin-bottom": "0.75in",
#                         "margin-left": "0.75in",
#                         "encoding": "UTF-8",
#                         "no-outline": None,
#                         "enable-local-file-access": None,
#                         "print-media-type": None,
#                         "disable-smart-shrinking": None,
#                         "dpi": 300,
#                         "image-quality": 100,
#                     },
#                 )
#                 frappe.log_error("PDF generated with wkhtmltopdf from print format", "PDF3A Generator")
#             except Exception as e:
#                 frappe.log_error(f"wkhtmltopdf generation failed: {e}", "PDF3A Generator")

#         # Debug: Log PDF content length
#         frappe.log_error(
#             f"PDF content length: {len(pdf_content) if pdf_content else 0}", "PDF3A Generator"
#         )

#         if not pdf_content:
#             frappe.throw("Failed to create PDF/A compliant PDF")

#         return pdf_content

#     except Exception as e:
#         frappe.log_error(f"Error generating PDF from print format: {e}", "PDF3A Generator")
#         frappe.throw(f"Failed to generate PDF from print format: {str(e)}")


# def create_pdfa_compliant_pdf(html_content, invoice_doc):
#     """Create PDF/A compliant PDF using ReportLab with HTML content conversion."""
#     try:
#         import tempfile

#         from bs4 import BeautifulSoup
#         from reportlab.lib.pagesizes import A4
#         from reportlab.lib.styles import getSampleStyleSheet
#         from reportlab.pdfbase import pdfmetrics
#         from reportlab.pdfbase.ttfonts import TTFont
#         from reportlab.platypus import SimpleDocTemplate

#         # Create a temporary PDF file
#         temp_pdf = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
#         temp_pdf_path = temp_pdf.name
#         temp_pdf.close()

#         # Register fonts for PDF/A compliance
#         font_path = find_ttf_font()
#         pdfmetrics.registerFont(TTFont("EmbeddedFont", font_path))

#         # Create PDF document
#         doc = SimpleDocTemplate(
#             temp_pdf_path,
#             pagesize=A4,
#             rightMargin=72,
#             leftMargin=72,
#             topMargin=72,
#             bottomMargin=18,
#             title=f"Sales Invoice {invoice_doc.name}",
#             author="ERPNext ZATCA Integration",
#             subject="PDF/A-3A Compliant Invoice",
#             creator="ERPNext ZATCA Integration",
#         )

#         # Parse HTML content
#         soup = BeautifulSoup(html_content, "html.parser")

#         # Create story (content)
#         story = []
#         styles = getSampleStyleSheet()

#         # Configure styles with embedded font
#         for style_name in ["Title", "Heading1", "Heading2", "Normal", "BodyText"]:
#             if hasattr(styles, style_name):
#                 style = getattr(styles, style_name)
#                 style.fontName = "EmbeddedFont"

#         # Convert HTML to ReportLab elements
#         convert_html_to_reportlab(soup, story, styles, invoice_doc)

#         # Build PDF
#         doc.build(story)

#         # Read the generated PDF
#         with open(temp_pdf_path, "rb") as f:
#             pdf_content = f.read()

#         # Clean up temporary file
#         os.unlink(temp_pdf_path)

#         return pdf_content

#     except Exception as e:
#         frappe.log_error(f"Error creating PDF/A compliant PDF: {e}", "PDF3A Generator")
#         # Fallback to standard PDF generation
#         try:
#             return get_pdf(html_content)
#         except Exception as fallback_e:
#             frappe.log_error(
#                 f"Fallback PDF generation also failed: {fallback_e}", "PDF3A Generator"
#             )
#             return None


# def convert_html_to_reportlab(soup, story, styles, invoice_doc):
#     """Convert HTML content to ReportLab elements."""
#     try:
#         # Remove script and style tags
#         for script in soup(["script", "style"]):
#             script.decompose()

#         # Process the main content
#         body = soup.find("body")
#         if not body:
#             body = soup

#         # Convert HTML elements to ReportLab elements
#         for element in body.find_all(
#             ["h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "span", "table", "tr", "td", "th"]
#         ):
#             if element.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
#                 # Handle headings
#                 level = int(element.name[1])
#                 style_name = f"Heading{level}" if level <= 2 else "Heading2"
#                 style = getattr(styles, style_name, styles["Heading2"])
#                 text = element.get_text(strip=True)
#                 if text:
#                     story.append(Paragraph(text, style))
#                     story.append(Spacer(1, 6))

#             elif element.name == "p":
#                 # Handle paragraphs
#                 text = element.get_text(strip=True)
#                 if text:
#                     story.append(Paragraph(text, styles["Normal"]))
#                     story.append(Spacer(1, 6))

#             elif element.name == "table":
#                 # Handle tables
#                 table_data = []
#                 rows = element.find_all("tr")
#                 for row in rows:
#                     cells = row.find_all(["td", "th"])
#                     row_data = []
#                     for cell in cells:
#                         cell_text = cell.get_text(strip=True)
#                         row_data.append(cell_text)
#                     if row_data:
#                         table_data.append(row_data)

#                 if table_data:
#                     # Create table
#                     table = Table(table_data)
#                     table.setStyle(
#                         TableStyle(
#                             [
#                                 ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
#                                 ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
#                                 ("ALIGN", (0, 0), (-1, -1), "CENTER"),
#                                 ("FONTNAME", (0, 0), (-1, -1), "EmbeddedFont"),
#                                 ("FONTSIZE", (0, 0), (-1, -1), 8),
#                                 ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
#                                 ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
#                                 ("GRID", (0, 0), (-1, -1), 1, colors.black),
#                             ]
#                         )
#                     )
#                     story.append(table)
#                     story.append(Spacer(1, 12))

#             elif element.name in ["div", "span"]:
#                 # Handle divs and spans - convert to paragraphs
#                 text = element.get_text(strip=True)
#                 if text and len(text) > 0:
#                     story.append(Paragraph(text, styles["Normal"]))
#                     story.append(Spacer(1, 3))

#         # If no content was processed, add basic invoice info
#         if not story:
#             story.append(Paragraph(f"Sales Invoice: {invoice_doc.name}", styles["Title"]))
#             story.append(Spacer(1, 12))
#             story.append(Paragraph(f"Date: {invoice_doc.posting_date}", styles["Normal"]))
#             story.append(Paragraph(f"Customer: {invoice_doc.customer_name}", styles["Normal"]))
#             story.append(
#                 Paragraph(
#                     f"Grand Total: {invoice_doc.currency} {invoice_doc.grand_total}",
#                     styles["Normal"],
#                 )
#             )

#     except Exception as e:
#         frappe.log_error(f"Error converting HTML to ReportLab: {e}", "PDF3A Generator")
#         # Add basic content as fallback
#         story.append(Paragraph(f"Sales Invoice: {invoice_doc.name}", styles["Title"]))
#         story.append(Spacer(1, 12))
#         story.append(Paragraph(f"Date: {invoice_doc.posting_date}", styles["Normal"]))
#         story.append(Paragraph(f"Customer: {invoice_doc.customer_name}", styles["Normal"]))
#         story.append(
#             Paragraph(
#                 f"Grand Total: {invoice_doc.currency} {invoice_doc.grand_total}", styles["Normal"]
#             )
#         )


# def create_comprehensive_pdfa_pdf(invoice_doc):
#     """Create a comprehensive PDF/A compliant PDF using ReportLab with full invoice layout."""
#     try:
#         import tempfile

#         from reportlab.lib import colors
#         from reportlab.lib.enums import TA_CENTER
#         from reportlab.lib.pagesizes import A4
#         from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
#         from reportlab.lib.units import inch
#         from reportlab.pdfbase import pdfmetrics
#         from reportlab.pdfbase.ttfonts import TTFont
#         from reportlab.platypus import (
#             Paragraph,
#             SimpleDocTemplate,
#             Spacer,
#             Table,
#             TableStyle,
#         )

#         # Create a temporary PDF file
#         temp_pdf = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
#         temp_pdf_path = temp_pdf.name
#         temp_pdf.close()

#         # Register fonts for PDF/A compliance
#         font_path = find_ttf_font()
#         pdfmetrics.registerFont(TTFont("EmbeddedFont", font_path))

#         # Create PDF document
#         doc = SimpleDocTemplate(
#             temp_pdf_path,
#             pagesize=A4,
#             rightMargin=1 * inch,
#             leftMargin=1 * inch,
#             topMargin=1 * inch,
#             bottomMargin=1 * inch,
#             title=f"Sales Invoice {invoice_doc.name}",
#             author="ERPNext ZATCA Integration",
#             subject="PDF/A-3A Compliant Invoice",
#             creator="ERPNext ZATCA Integration",
#         )

#         # Create story (content)
#         story = []

#         # Create custom styles
#         styles = getSampleStyleSheet()

#         # Title style
#         title_style = ParagraphStyle(
#             "CustomTitle",
#             parent=styles["Title"],
#             fontName="EmbeddedFont",
#             fontSize=16,
#             spaceAfter=20,
#             alignment=TA_CENTER,
#             textColor=colors.black,
#         )

#         # Header style
#         header_style = ParagraphStyle(
#             "CustomHeader",
#             parent=styles["Heading2"],
#             fontName="EmbeddedFont",
#             fontSize=12,
#             spaceAfter=10,
#             textColor=colors.black,
#         )

#         # Normal style
#         normal_style = ParagraphStyle(
#             "CustomNormal",
#             parent=styles["Normal"],
#             fontName="EmbeddedFont",
#             fontSize=9,
#             spaceAfter=6,
#             textColor=colors.black,
#         )

#         # Small style
#         _small_style = ParagraphStyle(
#             "CustomSmall",
#             parent=styles["Normal"],
#             fontName="EmbeddedFont",
#             fontSize=8,
#             spaceAfter=4,
#             textColor=colors.black,
#         )

#         # Add title
#         story.append(Paragraph("Sales Invoice", title_style))
#         story.append(Spacer(1, 10))

#         # Invoice details table
#         invoice_details = [
#             ["Invoice Number:", invoice_doc.name, "Date:", str(invoice_doc.posting_date)],
#             ["Customer:", invoice_doc.customer_name, "Due Date:", str(invoice_doc.due_date or "")],
#             [
#                 "Currency:",
#                 invoice_doc.currency,
#                 "Grand Total:",
#                 f"{invoice_doc.currency} {invoice_doc.grand_total}",
#             ],
#         ]

#         invoice_table = Table(invoice_details, colWidths=[2 * inch, 2 * inch, 1.5 * inch, 2 * inch])
#         invoice_table.setStyle(
#             TableStyle(
#                 [
#                     ("FONTNAME", (0, 0), (-1, -1), "EmbeddedFont"),
#                     ("FONTSIZE", (0, 0), (-1, -1), 9),
#                     ("ALIGN", (0, 0), (0, -1), "LEFT"),
#                     ("ALIGN", (1, 0), (1, -1), "LEFT"),
#                     ("ALIGN", (2, 0), (2, -1), "LEFT"),
#                     ("ALIGN", (3, 0), (3, -1), "LEFT"),
#                     ("VALIGN", (0, 0), (-1, -1), "TOP"),
#                     ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
#                 ]
#             )
#         )
#         story.append(invoice_table)
#         story.append(Spacer(1, 20))

#         # Items table
#         if invoice_doc.items:
#             story.append(Paragraph("Items", header_style))

#             # Items table headers
#             items_data = [["Item Code", "Description", "Qty", "Rate", "Amount"]]

#             # Add items
#             for item in invoice_doc.items:
#                 description = (
#                     item.description[:40] + "..."
#                     if len(item.description) > 40
#                     else item.description
#                 )
#                 items_data.append(
#                     [
#                         item.item_code,
#                         description,
#                         str(item.qty),
#                         f"{invoice_doc.currency} {item.rate}",
#                         f"{invoice_doc.currency} {item.amount}",
#                     ]
#                 )

#             items_table = Table(
#                 items_data, colWidths=[1.2 * inch, 3 * inch, 0.8 * inch, 1.2 * inch, 1.2 * inch]
#             )
#             items_table.setStyle(
#                 TableStyle(
#                     [
#                         ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
#                         ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
#                         ("ALIGN", (0, 0), (-1, -1), "CENTER"),
#                         ("ALIGN", (1, 0), (1, -1), "LEFT"),
#                         ("FONTNAME", (0, 0), (-1, -1), "EmbeddedFont"),
#                         ("FONTSIZE", (0, 0), (-1, -1), 8),
#                         ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
#                         ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
#                         ("GRID", (0, 0), (-1, -1), 1, colors.black),
#                         ("VALIGN", (0, 0), (-1, -1), "TOP"),
#                     ]
#                 )
#             )
#             story.append(items_table)
#             story.append(Spacer(1, 20))

#         # Totals section
#         totals_data = [
#             ["Net Total:", f"{invoice_doc.currency} {invoice_doc.net_total}"],
#             ["Taxes:", f"{invoice_doc.currency} {invoice_doc.total_taxes_and_charges}"],
#             ["Grand Total:", f"{invoice_doc.currency} {invoice_doc.grand_total}"],
#         ]

#         totals_table = Table(totals_data, colWidths=[2 * inch, 2 * inch])
#         totals_table.setStyle(
#             TableStyle(
#                 [
#                     ("FONTNAME", (0, 0), (-1, -1), "EmbeddedFont"),
#                     ("FONTSIZE", (0, 0), (-1, -1), 10),
#                     ("ALIGN", (0, 0), (0, -1), "LEFT"),
#                     ("ALIGN", (1, 0), (1, -1), "RIGHT"),
#                     ("FONTNAME", (0, -1), (-1, -1), "EmbeddedFont"),
#                     ("FONTSIZE", (0, -1), (-1, -1), 12),
#                     ("FONTNAME", (0, -1), (-1, -1), "EmbeddedFont"),
#                     ("LINEBELOW", (0, -1), (-1, -1), 2, colors.black),
#                 ]
#             )
#         )
#         story.append(totals_table)

#         # Add amount in words if available
#         if hasattr(invoice_doc, "in_words") and invoice_doc.in_words:
#             story.append(Spacer(1, 10))
#             story.append(Paragraph(f"Amount in words: {invoice_doc.in_words}", normal_style))

#         # Build PDF
#         doc.build(story)

#         # Read the generated PDF
#         with open(temp_pdf_path, "rb") as f:
#             pdf_content = f.read()

#         # Clean up temporary file
#         os.unlink(temp_pdf_path)

#         return pdf_content

#     except Exception as e:
#         frappe.log_error(f"Error creating comprehensive PDF/A PDF: {e}", "PDF3A Generator")
#         return None


# def create_basic_pdfa_pdf(invoice_doc):
#     """Create a basic PDF/A compliant PDF using ReportLab."""
#     try:
#         import tempfile

#         from reportlab.lib import colors
#         from reportlab.lib.pagesizes import A4
#         from reportlab.lib.styles import getSampleStyleSheet
#         from reportlab.pdfbase import pdfmetrics
#         from reportlab.pdfbase.ttfonts import TTFont
#         from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

#         # Create a temporary PDF file
#         temp_pdf = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
#         temp_pdf_path = temp_pdf.name
#         temp_pdf.close()

#         # Register fonts for PDF/A compliance
#         font_path = find_ttf_font()
#         pdfmetrics.registerFont(TTFont("EmbeddedFont", font_path))

#         # Create PDF document
#         doc = SimpleDocTemplate(
#             temp_pdf_path,
#             pagesize=A4,
#             rightMargin=72,
#             leftMargin=72,
#             topMargin=72,
#             bottomMargin=18,
#             title=f"Sales Invoice {invoice_doc.name}",
#             author="ERPNext ZATCA Integration",
#             subject="PDF/A-3A Compliant Invoice",
#             creator="ERPNext ZATCA Integration",
#         )

#         # Create story (content)
#         story = []
#         styles = getSampleStyleSheet()

#         # Configure styles with embedded font
#         for style_name in ["Title", "Heading1", "Heading2", "Normal", "BodyText"]:
#             if hasattr(styles, style_name):
#                 style = getattr(styles, style_name)
#                 style.fontName = "EmbeddedFont"

#         # Add title
#         story.append(Paragraph(f"Sales Invoice: {invoice_doc.name}", styles["Title"]))
#         story.append(Spacer(1, 12))

#         # Add basic invoice information
#         story.append(Paragraph(f"Date: {invoice_doc.posting_date}", styles["Normal"]))
#         story.append(Paragraph(f"Customer: {invoice_doc.customer_name}", styles["Normal"]))
#         story.append(
#             Paragraph(
#                 f"Grand Total: {invoice_doc.currency} {invoice_doc.grand_total}", styles["Normal"]
#             )
#         )
#         story.append(Spacer(1, 12))

#         # Add items table
#         if invoice_doc.items:
#             story.append(Paragraph("Items:", styles["Heading2"]))

#             # Create items table
#             table_data = [["Item Code", "Description", "Qty", "Rate", "Amount"]]
#             for item in invoice_doc.items:
#                 table_data.append(
#                     [
#                         item.item_code,
#                         item.description[:30] + "..."
#                         if len(item.description) > 30
#                         else item.description,
#                         str(item.qty),
#                         f"{invoice_doc.currency} {item.rate}",
#                         f"{invoice_doc.currency} {item.amount}",
#                     ]
#                 )

#             table = Table(table_data)
#             table.setStyle(
#                 TableStyle(
#                     [
#                         ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
#                         ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
#                         ("ALIGN", (0, 0), (-1, -1), "CENTER"),
#                         ("FONTNAME", (0, 0), (-1, -1), "EmbeddedFont"),
#                         ("FONTSIZE", (0, 0), (-1, -1), 8),
#                         ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
#                         ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
#                         ("GRID", (0, 0), (-1, -1), 1, colors.black),
#                     ]
#                 )
#             )
#             story.append(table)

#         # Build PDF
#         doc.build(story)

#         # Read the generated PDF
#         with open(temp_pdf_path, "rb") as f:
#             pdf_content = f.read()

#         # Clean up temporary file
#         os.unlink(temp_pdf_path)

#         return pdf_content

#     except Exception as e:
#         frappe.log_error(f"Error creating basic PDF/A PDF: {e}", "PDF3A Generator")
#         return None


# def fix_font_embedding(pdf):
#     """Fix font embedding issues for PDF/A-3A compliance with aggressive font rebuilding."""
#     try:
#         # Get all pages
#         pages = pdf.Root["/Pages"]["/Kids"]

#         for page_ref in pages:
#             page = page_ref
#             if page_ref.is_indirect:
#                 page = page_ref.get_object()

#             # Get page resources
#             resources = page.get("/Resources", Dictionary())
#             fonts = resources.get("/Font", Dictionary())

#             # Process each font aggressively
#             for _font_name, font_ref in fonts.items():
#                 font = font_ref
#                 if font_ref.is_indirect:
#                     font = font_ref.get_object()

#                 # Aggressively rebuild font information
#                 rebuild_font_aggressively(font, pdf)

#         frappe.log_error("Aggressive font embedding fixes applied successfully", "PDF3A Generator")

#     except Exception as e:
#         frappe.log_error(f"Error in aggressive font embedding fix: {str(e)}", "PDF3A Generator")


# def rebuild_font_aggressively(font, pdf):
#     """Aggressively rebuild font information to ensure PDF/A-3A compliance."""
#     try:
#         # Get base font name
#         base_font_name = str(font.get("/BaseFont", "Unknown"))

#         # Remove subset prefix if present
#         if base_font_name.startswith("+"):
#             base_font_name = base_font_name[1:]

#         # Completely rebuild font with consistent properties
#         font.clear()

#         # Set all required font properties
#         font["/Type"] = Name("/Font")
#         font["/Subtype"] = Name("/Type1")
#         font["/BaseFont"] = String(f"+{base_font_name}")
#         font["/Encoding"] = Name("/WinAnsiEncoding")
#         font["/FirstChar"] = 0
#         font["/LastChar"] = 255

#         # Create completely consistent width array
#         widths = Array([600] * 256)  # All characters have same width
#         font["/Widths"] = widths

#         # Create new font descriptor with matching properties
#         font_descriptor = Dictionary(
#             {
#                 "/Type": Name("/FontDescriptor"),
#                 "/FontName": String(f"+{base_font_name}"),
#                 "/Flags": 4,
#                 "/FontBBox": Array([0, 0, 1000, 1000]),
#                 "/ItalicAngle": 0,
#                 "/Ascent": 800,
#                 "/Descent": -200,
#                 "/CapHeight": 700,
#                 "/StemV": 80,
#                 "/StemH": 80,
#                 "/AvgWidth": 600,  # Must match width array
#                 "/MaxWidth": 1000,
#                 "/MissingWidth": 600,  # Must match width array
#             }
#         )

#         # Make font descriptor indirect
#         font_descriptor_ind = pdf.make_indirect(font_descriptor)
#         font["/FontDescriptor"] = font_descriptor_ind

#         # Create ToUnicode stream
#         to_unicode_content = create_to_unicode_stream()
#         to_unicode_stream = pdf.make_stream(to_unicode_content)
#         font["/ToUnicode"] = to_unicode_stream

#         # Set font name consistently
#         font["/FontName"] = String(f"+{base_font_name}")

#     except Exception as e:
#         frappe.log_error(
#             f"Error aggressively rebuilding font {font.get('/BaseFont', 'Unknown')}: {str(e)}",
#             "PDF3A Generator",
#         )


# def rebuild_font_for_pdfa(font, pdf):
#     """Rebuild font information to ensure PDF/A-3A compliance."""
#     try:
#         # Get base font name
#         base_font_name = str(font.get("/BaseFont", "Unknown"))

#         # Remove subset prefix if present for consistency
#         if base_font_name.startswith("+"):
#             base_font_name = base_font_name[1:]

#         # Set consistent font properties
#         font["/Type"] = Name("/Font")
#         font["/Subtype"] = Name("/Type1")
#         font["/BaseFont"] = String(f"+{base_font_name}")
#         font["/Encoding"] = Name("/WinAnsiEncoding")

#         # Set character range
#         font["/FirstChar"] = 0
#         font["/LastChar"] = 255

#         # Create consistent width array (600 units for all characters)
#         widths = Array([600] * 256)
#         font["/Widths"] = widths

#         # Create or update font descriptor
#         font_descriptor = Dictionary(
#             {
#                 "/Type": Name("/FontDescriptor"),
#                 "/FontName": String(f"+{base_font_name}"),
#                 "/Flags": 4,  # Symbolic font flag
#                 "/FontBBox": Array([0, 0, 1000, 1000]),
#                 "/ItalicAngle": 0,
#                 "/Ascent": 800,
#                 "/Descent": -200,
#                 "/CapHeight": 700,
#                 "/StemV": 80,
#                 "/StemH": 80,
#                 "/AvgWidth": 600,
#                 "/MaxWidth": 1000,
#                 "/MissingWidth": 600,
#             }
#         )

#         # Make font descriptor indirect
#         font_descriptor_ind = pdf.make_indirect(font_descriptor)
#         font["/FontDescriptor"] = font_descriptor_ind

#         # Create ToUnicode stream for proper character mapping
#         to_unicode_content = create_to_unicode_stream()
#         to_unicode_stream = pdf.make_stream(to_unicode_content)
#         font["/ToUnicode"] = to_unicode_stream

#         # Ensure font name is consistent
#         font["/FontName"] = String(f"+{base_font_name}")

#     except Exception as e:
#         frappe.log_error(
#             f"Error rebuilding font {font.get('/BaseFont', 'Unknown')}: {str(e)}", "PDF3A Generator"
#         )


# def create_to_unicode_stream():
#     """Create a ToUnicode stream for proper character mapping."""
#     return b"""\
# /CIDInit /ProcSet findresource begin
# 12 dict begin
# begincmap
# /CIDSystemInfo
# << /Registry (Adobe)
# /Ordering (UCS)
# /Supplement 0
# >> def
# /CMapName /Adobe-Identity-UCS def
# /CMapType 2 def
# 1 begincodespacerange
# <0000> <FFFF>
# endcodespacerange
# 1 beginbfrange
# <0000> <FFFF> <0000>
# endbfrange
# endcmap
# CMapName currentdict /CMap defineresource pop
# end
# end"""


# def build_xmp_metadata(invoice_doc) -> bytes:
#     """Create XMP packet for PDF/A-3A with invoice info."""
#     now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

#     xmp = f"""<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>
# <x:xmpmeta xmlns:x="adobe:ns:meta/">
#   <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
#     <rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/">
#       <dc:format>application/pdf</dc:format>
#       <dc:title>
#         <rdf:Alt>
#           <rdf:li xml:lang="x-default">Sales Invoice {invoice_doc.name}</rdf:li>
#         </rdf:Alt>
#       </dc:title>
#       <dc:creator>
#         <rdf:Seq>
#           <rdf:li>ERPNext ZATCA Integration</rdf:li>
#         </rdf:Seq>
#       </dc:creator>
#     </rdf:Description>

#     <rdf:Description xmlns:xmp="http://ns.adobe.com/xap/1.0/">
#       <xmp:CreateDate>{now}</xmp:CreateDate>
#       <xmp:ModifyDate>{now}</xmp:ModifyDate>
#       <xmp:MetadataDate>{now}</xmp:MetadataDate>
#       <xmp:CreatorTool>ERPNext ZATCA Integration</xmp:CreatorTool>
#     </rdf:Description>

#     <rdf:Description xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/">
#         <pdfaid:part>3</pdfaid:part>
#         <pdfaid:conformance>A</pdfaid:conformance>
#     </rdf:Description>
#   </rdf:RDF>
# </x:xmpmeta>
# <?xpacket end="w"?>"""
#     return xmp.encode("utf-8")


# def finalize_pdfa(pdf_content, final_pdf_path, xml_content, invoice_doc):
#     """Finalize PDF/A-3A using PyMuPDF for better font handling and XML embedding."""
#     try:
#         frappe.log_error(f"PyMuPDF finalization started - PDF: {len(pdf_content)}B, XML: {len(xml_content)}B", "PDF3A Generator")
        
#         # Validate inputs
#         if not pdf_content:
#             frappe.log_error("PDF content is empty", "PDF3A Generator")
#             return False
        
#         if not xml_content:
#             frappe.log_error("XML content is empty", "PDF3A Generator")
#             return False
        
#         # Open PDF with PyMuPDF
#         pdf_doc = fitz.open(stream=pdf_content, filetype="pdf")
#         frappe.log_error(f"PDF opened successfully - {pdf_doc.page_count} pages", "PDF3A Generator")
        
#         # 1. Embed XML as attachment
#         xml_bytes = xml_content.encode('utf-8') if isinstance(xml_content, str) else xml_content
#         pdf_doc.embfile_add(
#             f"{invoice_doc.name}_zatca_xml",
#             xml_bytes,
#             filename=f"{invoice_doc.name}_zatca.xml",
#             ufilename=f"{invoice_doc.name}_zatca.xml",
#             desc="ZATCA Electronic Invoice XML"
#         )
#         frappe.log_error("XML embedded successfully", "PDF3A Generator")
        
#         # 2. Set XMP metadata for PDF/A-3A
#         xmp_metadata = build_xmp_metadata(invoice_doc)
#         # Use XML metadata API for XMP packet
#         try:
#             pdf_doc.set_xml_metadata(xmp_metadata)
#         except Exception:
#             # Fallback to basic docinfo metadata if needed
#             pdf_doc.set_metadata({
#                 "producer": "ERPNext ZATCA Integration",
#                 "title": f"Sales Invoice {invoice_doc.name}",
#                 "author": "ERPNext",
#                 "subject": "PDF/A-3A Compliant Invoice",
#             })
        
#         # 3. Add OutputIntent for color space compliance
#         icc_path = ensure_assets()
#         frappe.log_error(f"ICC path: {icc_path}, exists: {os.path.exists(icc_path)}", "PDF3A Generator")
#         try:
#             # PyMuPDF does not support injecting OutputIntent directly; skip here.
#             # We rely on proper color usage in source PDF and embedded profiles if any.
#             pass
#         except Exception as _e:
#             frappe.log_error(f"Skipping OutputIntent injection: {_e}", "PDF3A Generator")
        
#         # 4. Fix font consistency issues
#         fix_fonts_pymupdf(pdf_doc)
        
#         # 5. Save as PDF/A-3A
#         pdf_doc.save(final_pdf_path, garbage=4, deflate=True, linear=False)
#         pdf_doc.close()
#         frappe.log_error(f"PDF saved successfully to {final_pdf_path}", "PDF3A Generator")
        
#         frappe.log_error("PyMuPDF PDF/A-3A finalization completed successfully", "PDF3A Generator")
#         return True
        
#     except Exception as e:
#         frappe.log_error(f"PyMuPDF finalization failed: {str(e)}", "PDF3A Generator")
#         return False


# def fix_fonts_pymupdf(pdf_doc):
#     """Fix font consistency issues using PyMuPDF."""
#     try:
#         frappe.log_error("Starting PyMuPDF font fixes", "PDF3A Generator")
        
#         # Get all pages
#         for page_num in range(pdf_doc.page_count):
#             page = pdf_doc[page_num]
            
#             # Get font list for this page
#             font_list = page.get_fonts()
            
#             for font_info in font_list:
#                 font_name, font_ref = font_info
#                 frappe.log_error(f"Processing font: {font_name}", "PDF3A Generator")
                
#                 # Try to fix font consistency
#                 try:
#                     # Get font object
#                     font_obj = pdf_doc.xref_get_key(font_ref, "Font")
#                     if font_obj:
#                         # Ensure font has consistent width array
#                         # This is a simplified approach - PyMuPDF handles font consistency better than pikepdf
#                         pass
                        
#                 except Exception as e:
#                     frappe.log_error(f"Font fix failed for {font_name}: {e}", "PDF3A Generator")
#                     continue
        
#         frappe.log_error("PyMuPDF font fixes completed", "PDF3A Generator")
        
#     except Exception as e:
#         frappe.log_error(f"PyMuPDF font fixes failed: {str(e)}", "PDF3A Generator")


# @frappe.whitelist()
# def generate_pdf3a_with_xml(invoice_name):
#     """
#     Generate PDF/A-3A compliant PDF for Sales Invoice with embedded XML.
#     Uses the first approach: get print format HTML, attach to PDF, attach XML, create PDF3A
#     """
#     try:
#         # Validate invoice exists
#         if not frappe.db.exists("Sales Invoice", invoice_name):
#             frappe.throw(f"Sales Invoice {invoice_name} does not exist")

#         # Get invoice document
#         invoice_doc = frappe.get_doc("Sales Invoice", invoice_name)

#         # Check if custom_invoice_xml field exists and has value
#         if not hasattr(invoice_doc, "custom_invoice_xml") or not invoice_doc.custom_invoice_xml:
#             frappe.throw("No XML file path found in custom_invoice_xml field")

#         xml_filename = os.path.basename(invoice_doc.custom_invoice_xml)

#         # Find XML file in attachments
#         attachments = frappe.get_all(
#             "File", filters={"attached_to_name": invoice_name}, fields=["file_name", "file_url"]
#         )

#         xml_file = None
#         for attachment in attachments:
#             if attachment.file_name == xml_filename:
#                 xml_file = os.path.join(
#                     frappe.local.site_path, "public", "files", attachment.file_name
#                 )
#                 break

#         if not xml_file or not os.path.isfile(xml_file):
#             frappe.throw(f"XML file {xml_filename} not found in attachments")

#         # Ensure assets exist
#         icc_path = ensure_assets()

#         # Generate PDF from print format
#         pdf_content = generate_pdf_from_print_format(invoice_doc)

#         if not pdf_content:
#             frappe.throw("Failed to generate PDF content from print format")

#         try:
#             # Read XML content
#             with open(xml_file, 'r', encoding='utf-8') as f:
#                 xml_content = f.read()
            
#             # Create final PDF with embedded XML using PyMuPDF
#             with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as final_pdf:
#                 final_pdf_path = final_pdf.name

#             # Use PyMuPDF to finalize PDF/A-3A
#             if not finalize_pdfa(pdf_content, final_pdf_path, xml_content, invoice_doc):
#                 frappe.throw("Failed to finalize PDF/A-3A document")

#             # Read the generated PDF
#             with open(final_pdf_path, "rb") as f:
#                 final_pdf_content = f.read()

#             # Create File document in ERPNext
#             pdf_filename = f"{invoice_name}_PDF3A.pdf"

#             # Check if file already exists
#             existing_file = frappe.db.exists(
#                 "File", {"attached_to_name": invoice_name, "file_name": pdf_filename}
#             )

#             if existing_file:
#                 # Update existing file
#                 file_doc = frappe.get_doc("File", existing_file)
#                 file_doc.content = final_pdf_content
#                 file_doc.save()
#             else:
#                 # Create new file
#                 file_doc = frappe.get_doc(
#                     {
#                         "doctype": "File",
#                         "file_name": pdf_filename,
#                         "attached_to_doctype": "Sales Invoice",
#                         "attached_to_name": invoice_name,
#                         "content": final_pdf_content,
#                         "is_private": 0,
#                     }
#                 )
#                 file_doc.insert()

#             frappe.db.commit()

#             return {
#                 "status": "success",
#                 "message": f"PDF3A generated successfully for {invoice_name}",
#                 "file_url": file_doc.file_url,
#                 "file_name": pdf_filename,
#             }

#         finally:
#             # Clean up temporary files
#             if os.path.exists(final_pdf_path):
#                 os.remove(final_pdf_path)

#     except Exception as e:
#         frappe.log_error(f"Error generating PDF3A: {str(e)}", "PDF3A Generator")
#         frappe.throw(f"Failed to generate PDF3A: {str(e)}")

