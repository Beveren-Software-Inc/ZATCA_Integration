# import json
# import frappe
# import os
# from datetime import datetime
# import pikepdf
# import frappe
# from frappe.utils.pdf import get_pdf
# from frappe import _
# from frappe.utils import get_url
# import io


# @frappe.whitelist(allow_guest=False)
# def zatca_embed_qr_in_pdf(invoice_name, print_format=None):
#     """
#     Generate a PDF for a Sales Invoice, embed its related XML, and save as PDF/A-3.
#     Use the system default.
#     """
#     try:
#         # Fetch invoice document
#         invoice_doc = frappe.get_doc("Sales Invoice", invoice_name)
#         xml_file_path = invoice_doc.custom_invoice_xml
#         xml_filename = os.path.basename(xml_file_path)

#         language = "en"

#         letterhead = invoice_doc.letter_head or None
#         if not letterhead:
#             default_lh = frappe.db.get_value("Letter Head", {"is_default": 1}, "name")
#             if default_lh:
#                 letterhead = default_lh
        
#         attachments = frappe.get_all(
#             "File", filters={"attached_to_name": invoice_name}, fields=["file_name"]
#         )
        
#         xml_file = None
#         for attachment in attachments:
#             if attachment.file_name == xml_filename:
#                 xml_file = os.path.join(
#                     frappe.local.site_path, "public", "files", attachment.file_name
#                 )
#                 break

#         if not xml_file or not os.path.exists(xml_file):
#             frappe.throw(f"No XML file found for the invoice {invoice_name}!")

#         # Generate invoice PDF
#         input_pdf = generate_invoice_pdf(
#             invoice_doc,
#             language=language,
#             letterhead=letterhead,
#             print_format=print_format
#         )

#         final_pdf_path = os.path.join(
#             frappe.local.site_path,
#             "public",
#             "files",
#             f"PDF-A3 {invoice_name} output.pdf"
#         )

#         # Embed XML into PDF with proper PDF/A-3 compliance
#         embed_xml_file_in_pdf(input_pdf, xml_file, final_pdf_path, invoice_name)

#         # Save file record
#         file_doc = frappe.get_doc({
#             "doctype": "File",
#             "file_url": f"/files/PDF-A3 {invoice_name} output.pdf",
#             "attached_to_doctype": "Sales Invoice",
#             "attached_to_name": invoice_name,
#             "is_private": 0
#         })
#         file_doc.insert(ignore_permissions=True)

#         return get_url(file_doc.file_url)

#     except pikepdf.PdfError as e:
#         frappe.throw(_(f"Error processing the PDF: {e}"))
#     except FileNotFoundError as e:
#         frappe.throw(_(f"File not found: {e}"))
#     except IOError as e:
#         frappe.throw(_(f"I/O error: {e}"))


# def embed_xml_file_in_pdf(input_pdf, xml_file, output_pdf, invoice_name):
#     """Embed an XML file into a PDF and make it PDF/A-3 compliant."""
#     icc_path = os.path.join(frappe.get_app_path("zatca_integration"), "public", "sRGB2014.icc")
   
#     with pikepdf.open(input_pdf, allow_overwriting_input=True) as pdf:
        
#         # Get XML file stats for proper metadata
#         xml_stats = os.stat(xml_file)
#         xml_size = xml_stats.st_size
#         xml_mod_time = datetime.fromtimestamp(xml_stats.st_mtime)
        
#         # -----------------------------
#         # 1. Fix Font Issues for PDF/A-3 Compliance - The major cause
#         # -----------------------------
        
#         #All functions I have written still gives error, will revisit this later on.
        
#         # -----------------------------
#         # 2. Set PDF/A-3 XMP Metadata (CRITICAL)
#         # -----------------------------
#         xmp_metadata = create_xmp_metadata(invoice_name)
#         # Set the XMP metadata
#         pdf.Root["/Metadata"] = pdf.make_stream(xmp_metadata.encode("utf-8"))
#         pdf.Root.Metadata["/Type"] = pikepdf.Name("/Metadata")
#         pdf.Root.Metadata["/Subtype"] = pikepdf.Name("/XML")
        
#         # -----------------------------
#         # 3. Set PDF document info with proper date format
#         # -----------------------------
#         current_time = datetime.now()
#         pdf_date = f"D:{current_time.strftime('%Y%m%d%H%M%S')}+00'00'"
        
#         pdf.docinfo["/Title"] = f"ZATCA Invoice {invoice_name}"
#         pdf.docinfo["/Author"] = "ERPNext ZATCA Integration"
#         pdf.docinfo["/Subject"] = "ZATCA compliant invoice with embedded XML"
#         pdf.docinfo["/Creator"] = "ERPNext ZATCA"
#         pdf.docinfo["/Producer"] = "pikepdf"
#         pdf.docinfo["/CreationDate"] = pikepdf.String(pdf_date)
#         pdf.docinfo["/ModDate"] = pikepdf.String(pdf_date)
#         pdf.docinfo["/Trapped"] = pikepdf.Name("/False")

#         # -----------------------------
#         # 4. Add Color Profile (ICC Profile) - FIXED
#         # -----------------------------
#         if os.path.exists(icc_path):
#             with open(icc_path, "rb") as icc_file:
#                 icc_data = icc_file.read()
                
#             # Create ICC profile stream
#             icc_stream = pdf.make_stream(icc_data)
#             icc_stream["/N"] = 3  # RGB color space
            
#             output_intent_dict = pikepdf.Dictionary({
#                 "/Type": pikepdf.Name("/OutputIntent"),
#                 "/S": pikepdf.Name("/GTS_PDFA1"),
#                 "/OutputConditionIdentifier": pikepdf.String("sRGB"),
#                 "/Info": pikepdf.String("sRGB IEC61966-2.1"),
#                 "/DestOutputProfile": icc_stream,
#                 "/OutputCondition": pikepdf.String("sRGB")
#             })
            
#             pdf.Root["/OutputIntents"] = pikepdf.Array([output_intent_dict])
#         else:
#             # Fallback: Create a simple output intent without ICC profile
#             frappe.log_error(f"ICC profile not found at {icc_path}", "ZATCA PDF Generation")
#             output_intent_dict = pikepdf.Dictionary({
#                 "/Type": pikepdf.Name("/OutputIntent"),
#                 "/S": pikepdf.Name("/GTS_PDFA1"),
#                 "/OutputConditionIdentifier": pikepdf.String("sRGB"),
#                 "/Info": pikepdf.String("sRGB IEC61966-2.1"),
#                 "/OutputCondition": pikepdf.String("sRGB")
#             })
#             pdf.Root["/OutputIntents"] = pikepdf.Array([output_intent_dict])

#         # -----------------------------
#         # 5. Embed XML File with Complete Metadata - FIXED MIME TYPE
#         # -----------------------------
#         with open(xml_file, "rb") as xf:
#             xml_data = xf.read()

#         # Create the embedded file stream with proper parameters
#         embedded_file_stream = pdf.make_stream(xml_data)
#         embedded_file_stream["/Type"] = pikepdf.Name("/EmbeddedFile")
#         embedded_file_stream["/Subtype"] = pikepdf.Name("/application/xml")  
        
#         # Add file parameters with proper metadata
#         xml_pdf_date = f"D:{xml_mod_time.strftime('%Y%m%d%H%M%S')}+00'00'"
#         embedded_file_stream["/Params"] = pikepdf.Dictionary({
#             "/Size": xml_size,
#             "/CreationDate": pikepdf.String(xml_pdf_date),
#             "/ModDate": pikepdf.String(xml_pdf_date),
#             "/CheckSum": pikepdf.String(""),
#         })

#         # Create file specification dictionary with complete metadata
#         xml_filename_base = os.path.basename(xml_file)
#         embedded_file_dict = pikepdf.Dictionary({
#             "/Type": pikepdf.Name("/Filespec"),
#             "/F": pikepdf.String(xml_filename_base),
#             "/UF": pikepdf.String(xml_filename_base), 
#             "/EF": pikepdf.Dictionary({"/F": embedded_file_stream}),
#             "/AFRelationship": pikepdf.Name("/Data"),  
#             "/Desc": pikepdf.String(f"ZATCA XML for invoice {invoice_name}")
#         })

#         # -----------------------------
#         # 6. Add to PDF Names Dictionary
#         # -----------------------------
#         if "/Names" not in pdf.Root:
#             pdf.Root["/Names"] = pikepdf.Dictionary()
#         if "/EmbeddedFiles" not in pdf.Root.Names:
#             pdf.Root.Names["/EmbeddedFiles"] = pikepdf.Dictionary()
#         if "/Names" not in pdf.Root.Names.EmbeddedFiles:
#             pdf.Root.Names.EmbeddedFiles["/Names"] = pikepdf.Array()

#         # Add to embedded files array
#         pdf.Root.Names.EmbeddedFiles.Names.extend([
#             pikepdf.String(xml_filename_base),
#             embedded_file_dict
#         ])
        

#         pdf.Root["/AF"] = pikepdf.Array([embedded_file_dict])

#         if "/StructTreeRoot" not in pdf.Root:
#             pdf.Root["/StructTreeRoot"] = pikepdf.Dictionary({
#                 "/Type": pikepdf.Name("/StructTreeRoot")
#             })
        
#         pdf.Root["/MarkInfo"] = pikepdf.Dictionary({
#             "/Marked": True,
#             "/UserProperties": False,
#             "/Suspects": False
#         })
        
#         pdf.Root["/Lang"] = pikepdf.String("en-US")
 
#         pdf.Root["/Version"] = pikepdf.Name("/1.7")

#         pdf.save(output_pdf, min_version=("1", 7))
#         return output_pdf

# def  create_xmp_metadata(invoice_name):
#     xmp_metadata = f"""<?xpacket begin='' id='W5M0MpCehiHzreSzNTczkc9d'?>
# <x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="pikepdf">
#     <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
#         <rdf:Description rdf:about=""
#             xmlns:dc="http://purl.org/dc/elements/1.1/"
#             xmlns:pdf="http://ns.adobe.com/pdf/1.3/"
#             xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/"
#             xmlns:xmp="http://ns.adobe.com/xap/1.0/">
#             <dc:format>application/pdf</dc:format>
#             <dc:creator>
#                 <rdf:Seq>
#                     <rdf:li>ERPNext ZATCA</rdf:li>
#                 </rdf:Seq>
#             </dc:creator>
#             <dc:title>
#                 <rdf:Alt>
#                     <rdf:li xml:lang="en">ZATCA Invoice {invoice_name}</rdf:li>
#                 </rdf:Alt>
#             </dc:title>
#             <dc:description>
#                 <rdf:Alt>
#                     <rdf:li xml:lang="en">ZATCA compliant invoice with embedded XML</rdf:li>
#                 </rdf:Alt>
#             </dc:description>
#             <xmp:CreateDate>{datetime.now().strftime('%Y-%m-%dT%H:%M:%S+00:00')}</xmp:CreateDate>
#             <xmp:ModifyDate>{datetime.now().strftime('%Y-%m-%dT%H:%M:%S+00:00')}</xmp:ModifyDate>
#             <xmp:CreatorTool>ERPNext ZATCA Integration</xmp:CreatorTool>
#             <pdf:Producer>pikepdf</pdf:Producer>
#             <pdf:Trapped>False</pdf:Trapped>
#             <pdfaid:part>3</pdfaid:part>
#             <pdfaid:conformance>A</pdfaid:conformance>
#         </rdf:Description>
#     </rdf:RDF>
# </x:xmpmeta>
# <?xpacket end="w"?>"""

#     return xmp_metadata

                
# def create_basic_tounicode_cmap():
#     """
#     Create a basic ToUnicode CMap for common characters.
#     This ensures compliance with ISO 19005-3:2012 6.2.11.7
#     """
#     return """/CIDInit /ProcSet findresource begin
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
# 100 beginbfchar
# <0020> <0020>
# <0021> <0021>
# <0022> <0022>
# <0023> <0023>
# <0024> <0024>
# <0025> <0025>
# <0026> <0026>
# <0027> <0027>
# <0028> <0028>
# <0029> <0029>
# <002A> <002A>
# <002B> <002B>
# <002C> <002C>
# <002D> <002D>
# <002E> <002E>
# <002F> <002F>
# <0030> <0030>
# <0031> <0031>
# <0032> <0032>
# <0033> <0033>
# <0034> <0034>
# <0035> <0035>
# <0036> <0036>
# <0037> <0037>
# <0038> <0038>
# <0039> <0039>
# <003A> <003A>
# <003B> <003B>
# <003C> <003C>
# <003D> <003D>
# <003E> <003E>
# <003F> <003F>
# <0040> <0040>
# <0041> <0041>
# <0042> <0042>
# <0043> <0043>
# <0044> <0044>
# <0045> <0045>
# <0046> <0046>
# <0047> <0047>
# <0048> <0048>
# <0049> <0049>
# <004A> <004A>
# <004B> <004B>
# <004C> <004C>
# <004D> <004D>
# <004E> <004E>
# <004F> <004F>
# <0050> <0050>
# <0051> <0051>
# <0052> <0052>
# <0053> <0053>
# <0054> <0054>
# <0055> <0055>
# <0056> <0056>
# <0057> <0057>
# <0058> <0058>
# <0059> <0059>
# <005A> <005A>
# <005B> <005B>
# <005C> <005C>
# <005D> <005D>
# <005E> <005E>
# <005F> <005F>
# <0060> <0060>
# <0061> <0061>
# <0062> <0062>
# <0063> <0063>
# <0064> <0064>
# <0065> <0065>
# <0066> <0066>
# <0067> <0067>
# <0068> <0068>
# <0069> <0069>
# <006A> <006A>
# <006B> <006B>
# <006C> <006C>
# <006D> <006D>
# <006E> <006E>
# <006F> <006F>
# <0070> <0070>
# <0071> <0071>
# <0072> <0072>
# <0073> <0073>
# <0074> <0074>
# <0075> <0075>
# <0076> <0076>
# <0077> <0077>
# <0078> <0078>
# <0079> <0079>
# <007A> <007A>
# <007B> <007B>
# <007C> <007C>
# <007D> <007D>
# <007E> <007E>
# <00A0> <00A0>
# <00A1> <00A1>
# <00A2> <00A2>
# <00A3> <00A3>
# <00A4> <00A4>
# <00A5> <00A5>
# <00A6> <00A6>
# <00A7> <00A7>
# <00A8> <00A8>
# <00A9> <00A9>
# <00AA> <00AA>
# <00AB> <00AB>
# <00AC> <00AC>
# <00AD> <00AD>
# <00AE> <00AE>
# <00AF> <00AF>
# <00B0> <00B0>
# <00B1> <00B1>
# <00B2> <00B2>
# <00B3> <00B3>
# endbfchar
# endcmap
# CMapName currentdict /CMap defineresource pop
# end
# end"""


# def generate_invoice_pdf(invoice, language="en", letterhead=None, print_format=None, public=False):
#     """
#     Generate a Sales Invoice PDF with local fonts suitable for PDF/A-3.

#     Args:
#         invoice (Document): Sales Invoice document.
#         language (str): Language code ("en" or "ar").
#         letterhead (str, optional): Letterhead name.
#         print_format (str, optional): Print format.
#         public (bool, optional): Save in public folder if True, else private.

#     Returns:
#         str: Full file path of generated PDF.
#     """
#     invoice_name = invoice.name
#     original_lang = frappe.local.lang
#     frappe.local.lang = language

#     try:
#         # Generate HTML from print format
#         html = frappe.get_print(
#             doctype="Sales Invoice",
#             name=invoice_name,
#             print_format=print_format,
#             no_letterhead=not bool(letterhead),
#             letterhead=letterhead
#         )

#         # Add PDF/A-3 friendly CSS with local fonts
#         pdf_a3_css = """
#         <style>
#         @font-face {
#             font-family: 'Cairo';
#             src: url('/fonts//Cairo.otf') format('truetype');
#         }
#         @font-face {
#             font-family: 'Amiri';
#             src: url('/fonts/Amiri.ttf') format('truetype');
#         }
#         body, * {
#             font-family: 'Cairo', 'Amiri', Arial, sans-serif !important;
#         }
#         .arabic-text {
#             font-family: 'Amiri', 'Cairo', Arial, sans-serif;
#             direction: rtl;
#             unicode-bidi: bidi-override;
#         }
#         </style>
#         """

#         # Inject CSS before </head>
#         if '</head>' in html:
#             html = html.replace('</head>', pdf_a3_css + '</head>')
#         else:
#             html = pdf_a3_css + html

#     finally:
#         frappe.local.lang = original_lang

#     # PDF options for wkhtmltopdf
#     pdf_options = {
#         'page-size': 'A4',
#         'margin-top': '1in',
#         'margin-right': '0.75in',
#         'margin-bottom': '0.75in',
#         'margin-left': '0.75in',
#         'encoding': 'UTF-8',
#         'enable-local-file-access': True,
#         'no-outline': None
#     }

#     # Convert HTML to PDF
#     pdf_content = get_pdf(html, options=pdf_options)
    
#     # Determine file path
#     folder_type = "public" if public else "private"
#     files_dir = os.path.join(frappe.local.site_path, folder_type, "files")
#     os.makedirs(files_dir, exist_ok=True)
#     file_name = f"{invoice_name}.pdf"
#     file_path = os.path.join(files_dir, file_name)

#     # Save PDF
#     with open(file_path, "wb") as f:
#         f.write(pdf_content)

#     return file_path

#!/usr/bin/env python3
"""
Generate PDF/A-3A compliant PDF for Frappe Sales Invoice with embedded XML
This method integrates with ERPNext Sales Invoice to create compliant PDFs
"""
import io
import os
import sys
import tempfile
from datetime import datetime, timezone
import frappe
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import black

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


import pikepdf
from pikepdf import Name, Dictionary, Array, String, Stream
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
pdfmetrics.registerFont(TTFont("HelveticaVCA", helvetica))        # regular
pdfmetrics.registerFont(TTFont("HelveticaVCA-Bold", helvetica_bold))  # bold


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
    from reportlab.lib import colors
    
    ttf_path = find_ttf_font()
    font_name = "EmbeddedTTF"
    pdfmetrics.registerFont(TTFont(font_name, ttf_path))

    c = canvas.Canvas(temp_pdf_path, pagesize=A4, pageCompression=0)
    width, height = A4

    # Helper function to draw bordered table cell
    def draw_table_cell(x, y, w, h, text, font_size=9, align='left', bg_color=None):
        if bg_color:
            c.setFillColor(bg_color)
            c.rect(x, y-h, w, h, fill=1)
            c.setFillColor(black)
        
        c.rect(x, y-h, w, h, fill=0)
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

    margin_x = 30
    margin_y = 30
    y = height - 60
    
    # ---------- HEADER SECTION ----------
    c.setFont(font_name, 14)
    c.setFillColor(black)
    c.drawCentredString(width/2, y, "Tax Invoice - فاتورة ضريبية")
    y -= 30

    # Top table with invoice details and QR code
    table_width = width - 2 * margin_x
    qr_width = 80
    detail_width = table_width - qr_width
    
    # Invoice details table (left side)
    cell_height = 15
    col_widths = [80, 80, 100, 60, 80, 80]
    
    # Row 1
    current_y = y
    draw_table_cell(margin_x, current_y, col_widths[0], cell_height, "Invoice No:", 9)
    draw_table_cell(margin_x + col_widths[0], current_y, col_widths[1], cell_height, invoice_doc.name, 9)
    draw_table_cell(margin_x + col_widths[0] + col_widths[1], current_y, col_widths[2], cell_height, "رقم الفاتورة", 9, 'right')
    draw_table_cell(margin_x + col_widths[0] + col_widths[1] + col_widths[2], current_y, col_widths[3], cell_height, "Issue Date:", 9)
    draw_table_cell(margin_x + col_widths[0] + col_widths[1] + col_widths[2] + col_widths[3], current_y, col_widths[4], cell_height, str(invoice_doc.posting_date), 9)
    draw_table_cell(margin_x + col_widths[0] + col_widths[1] + col_widths[2] + col_widths[3] + col_widths[4], current_y, col_widths[5], cell_height, "تاريخ إصدار الفاتورة", 9, 'right')
    
    # QR Code placeholder (right side)
    # QR Code placeholder (right side)
    qr_x = width - margin_x - qr_width
    c.rect(qr_x, current_y - cell_height * 3, qr_width, cell_height * 3)

    # Draw QR code image if available
    qr_code_path = getattr(invoice_doc, 'custom_invoice_qr_code', '')
    if qr_code_path:
        try:
            # Remove '/files/' prefix if present and get the actual file path
            if qr_code_path.startswith('/files/'):
                qr_code_path = qr_code_path.replace('/files/', '')
            
            full_qr_path = frappe.utils.get_site_path('public', 'files', qr_code_path)
            
            # Draw the QR code image
            c.drawImage(full_qr_path, qr_x + 5, current_y - cell_height * 3 + 5, 
                    width=qr_width - 10, height=cell_height * 3 - 10, 
                    preserveAspectRatio=True, mask='auto')
        except:
            # Fallback to text if image can't be loaded
            c.drawCentredString(qr_x + qr_width/2, current_y - cell_height * 1.5, "QR CODE")
    else:
        c.drawCentredString(qr_x + qr_width/2, current_y - cell_height * 1.5, "QR CODE")
    current_y -= cell_height
    
    # Row 2
    draw_table_cell(margin_x, current_y, col_widths[0], cell_height, "ZATCA Status", 9)
    draw_table_cell(margin_x + col_widths[0], current_y, col_widths[1], cell_height, getattr(invoice_doc, 'custom_zatca_submit_status', ''), 9)
    draw_table_cell(margin_x + col_widths[0] + col_widths[1], current_y, col_widths[2], cell_height, "حالة التخليص", 9, 'right')
    draw_table_cell(margin_x + col_widths[0] + col_widths[1] + col_widths[2], current_y, col_widths[3], cell_height, "Due Date:", 9)
    draw_table_cell(margin_x + col_widths[0] + col_widths[1] + col_widths[2] + col_widths[3], current_y, col_widths[4], cell_height, str(invoice_doc.due_date or ''), 9)
    draw_table_cell(margin_x + col_widths[0] + col_widths[1] + col_widths[2] + col_widths[3] + col_widths[4], current_y, col_widths[5], cell_height, "تاريخ الاستحقاق", 9, 'right')
    
    current_y -= cell_height
    
    # Row 3
    delivery_note = getattr(invoice_doc.items[0], 'delivery_note', '') if invoice_doc.items else ''
    delivery_note = delivery_note if delivery_note else '-'
    supply_date = getattr(invoice_doc, 'custom_date_of_supply', '') or '-'
    
    draw_table_cell(margin_x, current_y, col_widths[0], cell_height, "Delivery Note:", 9)
    draw_table_cell(margin_x + col_widths[0], current_y, col_widths[1], cell_height, delivery_note, 9)
    draw_table_cell(margin_x + col_widths[0] + col_widths[1], current_y, col_widths[2], cell_height, "مذكرة التسليم", 9, 'right')
    draw_table_cell(margin_x + col_widths[0] + col_widths[1] + col_widths[2], current_y, col_widths[3], cell_height, "Date of Supply:", 9)
    draw_table_cell(margin_x + col_widths[0] + col_widths[1] + col_widths[2] + col_widths[3], current_y, col_widths[4], cell_height, supply_date, 9)
    draw_table_cell(margin_x + col_widths[0] + col_widths[1] + col_widths[2] + col_widths[3] + col_widths[4], current_y, col_widths[5], cell_height, "تاريخ التوريد", 9, 'right')
    
    y = current_y - cell_height - 10
    
    # Purchase order details table
    po_table_width = detail_width
    po_col_width = po_table_width / 6
    
    # Headers
    current_y = y
    po_headers = ["Vendor Number\nرقم البائع", "PO No\nرقم طلب الشراء", "Purchase Agreement\nرقم العقد", 
                  "ASN Number\nرقم أ س ن", "Truck Request No\nرقم طلب الشاحنة", "GR\nجي آر"]
    
    for i, header in enumerate(po_headers):
        draw_table_cell(margin_x + i * po_col_width, current_y, po_col_width, cell_height * 2, header, 8, 'center', colors.lightgrey)
    
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
        draw_table_cell(margin_x + i * po_col_width, current_y, po_col_width, cell_height, data, 9, 'center')
    
    y = current_y - cell_height - 20
    
    # ---------- SELLER AND BUYER INFO ----------
    seller_buyer_width = (width - 2 * margin_x) / 2
    
    # Headers
    current_y = y
    draw_table_cell(margin_x, current_y, seller_buyer_width/2, cell_height, "Seller:", 10, bg_color=colors.lightgrey)
    draw_table_cell(margin_x + seller_buyer_width/2, current_y, seller_buyer_width/2, cell_height, ":المورد", 10, 'right', colors.lightgrey)
    draw_table_cell(margin_x + seller_buyer_width, current_y, seller_buyer_width/2, cell_height, "Buyer:", 10, bg_color=colors.lightgrey)
    draw_table_cell(margin_x + seller_buyer_width + seller_buyer_width/2, current_y, seller_buyer_width/2, cell_height, ":العميل", 10, 'right', colors.lightgrey)
    
    current_y -= cell_height
    
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
    
    detail_col_width = seller_buyer_width / 4
    
    for label, seller_val, buyer_val, arabic_label in details_data:
        # Seller side
        draw_table_cell(margin_x, current_y, detail_col_width, cell_height, label, 9)
        draw_table_cell(margin_x + detail_col_width, current_y, detail_col_width, cell_height, str(seller_val), 9)
        draw_table_cell(margin_x + detail_col_width * 2, current_y, detail_col_width, cell_height, str(seller_val), 9, 'right')
        draw_table_cell(margin_x + detail_col_width * 3, current_y, detail_col_width, cell_height, arabic_label, 9, 'right')
        
        # Buyer side
        draw_table_cell(margin_x + seller_buyer_width, current_y, detail_col_width, cell_height, label, 9)
        draw_table_cell(margin_x + seller_buyer_width + detail_col_width, current_y, detail_col_width, cell_height, str(buyer_val), 9)
        draw_table_cell(margin_x + seller_buyer_width + detail_col_width * 2, current_y, detail_col_width, cell_height, str(buyer_val), 9, 'right')
        draw_table_cell(margin_x + seller_buyer_width + detail_col_width * 3, current_y, detail_col_width, cell_height, arabic_label, 9, 'right')
        
        current_y -= cell_height
    
    y = current_y - 20
    
    # ---------- ITEMS TABLE ----------
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
        draw_table_cell(margin_x + sum(item_col_widths[:i]), current_y, item_col_widths[i], cell_height * 2, header, 8, 'center', colors.lightgrey)
    
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
                draw_table_cell(margin_x + sum(item_col_widths[:i]), current_y, item_col_widths[i], cell_height * 2, data, 8, 'right' if i > 1 else 'left')
            
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
                    draw_table_cell(margin_x + sum(item_col_widths[:i]), current_y, item_col_widths[i], cell_height * 2, data, 8, 'right' if i > 1 else 'left')
                
                current_y -= cell_height * 2
    
    y = current_y - 20
    
    # ---------- TOTALS SECTION ----------
    totals_width = width - 2 * margin_x
    
    # Total amounts header
    current_y = y
    draw_table_cell(margin_x, current_y, totals_width/2, cell_height, "Total Amounts:", 10, bg_color=colors.lightgrey)
    draw_table_cell(margin_x + totals_width/2, current_y, totals_width/2, cell_height, ":اجمالي المبالغ", 10, 'right', colors.lightgrey)
    
    current_y -= cell_height
    
    # Totals data
    totals_data = [
        ("Total Taxable Amount (Excluding VAT)", "الاجمالي الخاضع للضريبة  (غير شامل ضريبة القيمة المضافة)", f"{invoice_doc.net_total:.2f} {invoice_doc.currency}"),
        ("Total VAT", "مجموع ضريبة القيمة المضافة", f"{invoice_doc.total_taxes_and_charges:.2f} {invoice_doc.currency}"),
        ("Total Amount Due", "اجمالي المبلغ المستحق", f"{invoice_doc.grand_total:.2f} {invoice_doc.currency}"),
        ("Total In Words", "", invoice_doc.in_words or "")
    ]
    
    for english, arabic, amount in totals_data:
        draw_table_cell(margin_x, current_y, totals_width/4, cell_height, "", 9)
        draw_table_cell(margin_x + totals_width/4, current_y, totals_width/4, cell_height, english, 9)
        draw_table_cell(margin_x + totals_width/2, current_y, totals_width/4, cell_height, arabic, 9, 'right')
        draw_table_cell(margin_x + 3*totals_width/4, current_y, totals_width/4, cell_height, amount, 9, 'right')
        current_y -= cell_height
    
    y = current_y - 20
    
    # ---------- TAX SUMMARY ----------
    current_y = y
    conversion_rate = getattr(invoice_doc, 'conversion_rate', 1)
    
    # Tax summary header
    draw_table_cell(margin_x, current_y, totals_width, cell_height, f"Tax Summary (1 {invoice_doc.currency} = {conversion_rate} SAR)", 10, bg_color=colors.lightgrey)
    current_y -= cell_height
    
    # Tax table headers
    tax_col_widths = [totals_width/2, totals_width/4, totals_width/4]
    tax_headers = ["Tax Details", "Taxable Amount(SAR)", "Tax Amount(SAR)"]
    
    for i, header in enumerate(tax_headers):
        draw_table_cell(margin_x + sum(tax_col_widths[:i]), current_y, tax_col_widths[i], cell_height, header, 9, 'left' if i == 0 else 'right', colors.lightgrey)
    
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
        draw_table_cell(margin_x + sum(tax_col_widths[:i]), current_y, tax_col_widths[i], cell_height, data, 9, 'left' if i == 0 else 'right')
    
    current_y -= cell_height - 20
    
    # ---------- BANK DETAILS ----------
    current_y -= 20
    
    # Bank details header
    draw_table_cell(margin_x, current_y, totals_width/2, cell_height, "Bank Details (USD)", 10, bg_color=colors.lightgrey)
    draw_table_cell(margin_x + totals_width/2, current_y, totals_width/2, cell_height, "التفاصيل المصرفية", 10, 'right', colors.lightgrey)
    
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
        draw_table_cell(margin_x, current_y, bank_col_width, cell_height, english_label, 9, bg_color=colors.white)
        draw_table_cell(margin_x + bank_col_width, current_y, bank_col_width, cell_height, english_value, 9, 'center')
        draw_table_cell(margin_x + 2*bank_col_width, current_y, bank_col_width, cell_height, arabic_value, 9, 'center')
        draw_table_cell(margin_x + 3*bank_col_width, current_y, bank_col_width, cell_height, arabic_label, 9, 'right', colors.white)
        current_y -= cell_height
    
    # ---------- FOOTER ----------
    c.setFont(font_name, 8)
    c.drawCentredString(width/2, 30, "This is a PDF/A-3A compliant invoice with embedded XML")
    
    c.save()
    # c.setFont(font_name, 10)
    # c.drawString(margin_x, y, f"Invoice No: {invoice_doc.name}")
    # c.drawRightString(width - margin_x, y, f"Issue Date: {invoice_doc.posting_date}")
    # y -= 20

    # c.drawString(margin_x, y, f"Due Date: {invoice_doc.due_date or ''}")
    # c.drawRightString(width - margin_x, y, f"Date of Supply: {getattr(invoice_doc, 'custom_date_of_supply', '')}")
    # y -= 40

    # ---------- Seller / Buyer ----------
    # c.setFont(font_name, 12)
    # c.drawString(margin_x, y, "Seller:")
    # c.drawRightString(width - margin_x, y, "Buyer:")
    # y -= 20

    # c.setFont(font_name, 10)
    # c.drawString(margin_x, y, f"{invoice_doc.company}")
    # c.drawRightString(width - margin_x, y, f"{invoice_doc.customer_name}")
    # y -= 15

    # c.drawString(margin_x, y, f"VAT: {invoice_doc.company_tax_id or ''}")
    # c.drawRightString(width - margin_x, y, f"VAT: {invoice_doc.tax_id or ''}")
    # y -= 40

    # # ---------- Items Table ----------
    # table_top = y
    # col_x = [margin_x, 200, 300, 370, 440, 520]
    # headers = ["Item", "Description", "Qty", "Rate", "Amount"]

    # c.setFont(font_name, 10)
    # for i, h in enumerate(headers):
    #     c.drawString(col_x[i], y, h)
    # y -= 15
    # c.line(margin_x, y, width - margin_x, y)
    # y -= 10

    # # Items
    # for item in invoice_doc.items:
    #     if y < 100:  # new page
    #         c.showPage()
    #         c.setFont(font_name, 10)
    #         y = height - 100

    #     c.drawString(col_x[0], y, item.item_code)
    #     c.drawString(col_x[1], y, item.item_name[:25])
    #     c.drawRightString(col_x[2]+30, y, str(item.qty))
    #     c.drawRightString(col_x[3]+50, y, f"{item.rate:.2f}")
    #     c.drawRightString(col_x[4]+60, y, f"{item.amount:.2f}")
    #     y -= 15

    # y -= 20
    # c.line(margin_x, y, width - margin_x, y)
    # y -= 20

    # # ---------- Totals ----------
    # c.setFont(font_name, 10)
    # c.drawRightString(width - margin_x, y, f"Net Total: {invoice_doc.currency} {invoice_doc.net_total:.2f}")
    # y -= 15
    # c.drawRightString(width - margin_x, y, f"Total VAT: {invoice_doc.currency} {invoice_doc.total_taxes_and_charges:.2f}")
    # y -= 15
    # c.setFont(font_name, 12)
    # c.drawRightString(width - margin_x, y, f"Grand Total: {invoice_doc.currency} {invoice_doc.grand_total:.2f}")
    # y -= 30

    # # ---------- Footer ----------
    # c.setFont(font_name, 8)
    # c.drawCentredString(width/2, 40, "This is a PDF/A-3A compliant invoice with embedded XML")

    # c.save()

# from reportlab.lib.pagesizes import A4
# from reportlab.lib import colors
# from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
# from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer


# def draw_pdf_with_reportlab(file_path, invoice_doc):
#     doc = SimpleDocTemplate(file_path, pagesize=A4,
#                             rightMargin=20, leftMargin=20,
#                             topMargin=20, bottomMargin=20)

#     styles = getSampleStyleSheet()
#     normal = ParagraphStyle(name="Normal", fontName="HelveticaVCA", fontSize=9)
#     bold = ParagraphStyle(name="Bold", parent=normal, fontName="HelveticaVCA-Bold", fontSize=9)

#     # normal = styles["Normal"]
#     # bold = ParagraphStyle(name='Bold', parent=normal, fontName='Helvetica-Bold')

#     elements = []

#     # Title
#     elements.append(Paragraph("<b>Tax Invoice</b>", styles['Title']))
#     elements.append(Spacer(1, 10))

#     # Invoice Info Table (No, Date, Status)
#     invoice_info = [
#         ["Invoice No:", invoice_doc.name, "",
#          "Issue Date:", str(invoice_doc.posting_date), ""],
#         ["ZATCA Status", invoice_doc.get("custom_zatca_submit_status", ""), "",
#          "Due Date:", str(invoice_doc.due_date), ""]
#     ]

#     t = Table(invoice_info, colWidths=[80, 80, 80, 80, 80, 80])
#     t.setStyle(TableStyle([
#         ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
#         ('FONTNAME', (0, 0), (-1, -1), 'HelveticaVCA'),
#         ('FONTSIZE', (0, 0), (-1, -1), 8),
#     ]))
#     elements.append(t)
#     elements.append(Spacer(1, 10))

#     # Seller & Buyer Info
#     seller_buyer = [
#         [Paragraph("<b>Seller:</b>", bold), invoice_doc.company, "", "",
#          Paragraph("<b>Buyer:</b>", bold), invoice_doc.customer_name, "", ""]
#     ]
#     sb_table = Table(seller_buyer, colWidths=[60, 100, 60, 40, 60, 100, 60, 40])
#     sb_table.setStyle(TableStyle([
#         ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
#         ('FONTSIZE', (0, 0), (-1, -1), 8),
#         ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey)
#     ]))
#     elements.append(sb_table)
#     elements.append(Spacer(1, 10))

#     # Items Table
#     item_data = [["PO Item", "Nature of goods", "Unit Price", "Quantity",
#                   "Taxable Amount", "Tax Amount", "Subtotal"]]
#     for row in invoice_doc.items:
#         item_data.append([
#             row.get("line_item", ""),
#             f"{row.item_code}",
#             f"{row.rate:.2f} {invoice_doc.currency}",
#             f"{row.qty} {row.uom}",
#             f"{row.amount:.2f} {invoice_doc.currency}",
#             f"{invoice_doc.total_taxes_and_charges:.2f} {invoice_doc.currency}",
#             f"{invoice_doc.grand_total:.2f} {invoice_doc.currency}"
#         ])

#     items_table = Table(item_data, repeatRows=1)
#     items_table.setStyle(TableStyle([
#         ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
#         ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
#         ('FONTSIZE', (0, 0), (-1, -1), 8)
#     ]))
#     elements.append(items_table)
#     elements.append(Spacer(1, 10))

#     # Totals
#     totals = [
#         ["Total Taxable Amount (Excl. VAT)", f"{invoice_doc.total:.2f} {invoice_doc.currency}"],
#         ["Total VAT", f"{invoice_doc.total_taxes_and_charges:.2f} {invoice_doc.currency}"],
#         ["Grand Total", f"{invoice_doc.grand_total:.2f} {invoice_doc.currency}"],
#         ["In Words", invoice_doc.in_words]
#     ]
#     totals_table = Table(totals, colWidths=[250, 250])
#     totals_table.setStyle(TableStyle([
#         ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
#         ('FONTSIZE', (0, 0), (-1, -1), 8),
#         ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey)
#     ]))
#     elements.append(totals_table)

#     # Bank details (static example, you can fetch dynamically)
#     bank_details = [
#         ["Bank Details (USD)", ""],
#         ["Account Name", "Renewable Energy Petrochemicals Factory Co Ltd"],
#         ["Bank Name", "Banque Saudi Fransi"],
#         ["IBAN", "SA56 5500 0000 0995 4870 0220"],
#         ["Swift Code", "BSFRSARIXXX"]
#     ]
#     bank_table = Table(bank_details, colWidths=[200, 300])
#     bank_table.setStyle(TableStyle([
#         ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
#         ('FONTSIZE', (0, 0), (-1, -1), 8),
#         ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey)
#     ]))
#     elements.append(Spacer(1, 20))
#     elements.append(bank_table)

#     doc.build(elements)




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