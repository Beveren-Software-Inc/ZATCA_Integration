# ruff: noqa: E501

"""
Generate PDF/A-3A compliant PDF for Frappe Sales Invoice with embedded XML
This method integrates with ERPNext Sales Invoice to create compliant PDFs
"""

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# import arabic_reshaper
import fitz  # PyMuPDF for PDF to image conversion
import frappe
import pikepdf
from frappe.utils.pdf import get_pdf
from pikepdf import Array, Dictionary, Name, String
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

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
pdf = str(font_dir / "REPC-SRET-000001.pdf")

san_serif = str(font_dir / "san_seriff.ttf")
noto_sans = str(font_dir / "NotoSans.ttf")
plex_regular = str(font_dir / "Plex-Regular.ttf")

invoice_image = str(font_dir / "invoice.jpg")

EMBEDDED_SRGB_ICC = icc_2014
# EMBEDDED_FONT_TTF = regular
EMBEDDED_FONT_TTF = cairo_regular


# Register the font files you already placed in zatca_integration/public/fonts
pdfmetrics.registerFont(TTFont("HelveticaVCA", helvetica))
pdfmetrics.registerFont(TTFont("HelveticaVCA-Bold", helvetica_bold))

pdfmetrics.registerFont(TTFont("Amiri", amiri_regular))
pdfmetrics.registerFont(TTFont("Amiri-Bold", amiri_bold))

pdfmetrics.registerFont(TTFont("Cairo", cairo_regular))
pdfmetrics.registerFont(TTFont("Cairo-Bold", cairo_bold))

pdfmetrics.registerFont(TTFont("San-Serif", san_serif))
pdfmetrics.registerFont(TTFont("NotoSan", noto_sans))


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


def draw_pdf_with_reportlab(temp_pdf_path: str, invoice_doc):
    """Draw Sales Invoice using PDF to image conversion approach."""

    # Initialize canvas and fonts
    ttf_path = find_ttf_font()
    font_name = "EmbeddedTTF"
    pdfmetrics.registerFont(TTFont(font_name, ttf_path))

    c = canvas.Canvas(temp_pdf_path, pagesize=A4, pageCompression=0)
    width, height = A4
    _margin_x = 30
    y = height - 50  # height is now just the numeric value

    # ---------- GENERATE PDF FROM PRINT FORMAT AND CONVERT TO IMAGE ----------
    try:
        # Generate HTML content from print format - without letterhead since we handle it separately
        html = frappe.get_print(
            doctype="Sales Invoice",
            name=invoice_doc.name,
            print_format="Zatca PDF-A 3B",
            no_letterhead=1,
            letterhead=None,
        )

        # Debug: Log HTML content length
        frappe.log_error(f"HTML content length: {len(html) if html else 0}", "PDF Generator")

        # Convert HTML to PDF
        pdf_content = get_pdf(html)

        # Debug: Log PDF content length
        frappe.log_error(
            f"PDF content length: {len(pdf_content) if pdf_content else 0}", "PDF Generator"
        )

        # Save PDF to temporary file
        temp_html_pdf_path = tempfile.mktemp(suffix=".pdf")
        with open(temp_html_pdf_path, "wb") as f:
            f.write(pdf_content)

        try:
            # Open PDF with PyMuPDF and convert to image
            doc = fitz.open(temp_html_pdf_path)
            page = doc[0]  # First page

            # Convert page to pixmap (image)
            mat = fitz.Matrix(2.0, 2.0)  # Scale factor for better quality
            pix = page.get_pixmap(matrix=mat)

            # Save pixmap to temporary image file
            temp_image_path = tempfile.mktemp(suffix=".png")
            pix.save(temp_image_path)

            # Debug: Check if image file exists and has content
            if os.path.exists(temp_image_path):
                file_size = os.path.getsize(temp_image_path)
                frappe.log_error(
                    f"Image file created - path: {temp_image_path}, size: {file_size} bytes",
                    "PDF Generator",
                )

                # Try to get image dimensions
                try:
                    from PIL import Image

                    with Image.open(temp_image_path) as img:
                        img_width, img_height = img.size
                        frappe.log_error(
                            f"Image dimensions - width: {img_width}, height: {img_height}",
                            "PDF Generator",
                        )
                except Exception as e:
                    frappe.log_error(f"Error getting image dimensions: {e}", "PDF Generator")
            else:
                frappe.log_error(
                    f"Image file not created - path: {temp_image_path}", "PDF Generator"
                )

            # Draw the image on the canvas - full page coverage
            img_width = width  # Full page width
            img_height = height  # Full page height

            # Debug: Log the positioning values
            frappe.log_error(
                f"Image positioning - width: {img_width}, height: {img_height}", "PDF Generator"
            )

            c.drawImage(
                temp_image_path,
                0,  # Start from left edge
                0,  # Start from bottom edge
                width=width,  # Full page width
                height=height,  # Full page height
                preserveAspectRatio=False,  # Don't preserve aspect ratio to fill space
                mask="auto",
            )

            doc.close()

            # ---------- DRAW LETTERHEAD ON TOP OF IMAGE ----------
            y = add_letterhead(c, invoice_doc, width, height)

            # ---------- DRAW QR CODE ON TOP OF IMAGE (RIGHT SIDE) ----------
            qr_code_path = getattr(invoice_doc, "custom_invoice_qr_code", "")
            if qr_code_path:
                try:
                    if qr_code_path.startswith("/files/"):
                        qr_code_path = qr_code_path.replace("/files/", "")

                    full_qr_path = frappe.utils.get_site_path("public", "files", qr_code_path)

                    # QR code dimensions and position
                    qr_size = 80  # Size of QR code
                    qr_x = width - qr_size - 50  # Right side with 50px margin (moved 50px left)
                    qr_y = height - qr_size - 110  # Top with 200px margin (moved 200px down)

                    # Draw the QR code image
                    c.drawImage(
                        full_qr_path,
                        qr_x,
                        qr_y,
                        width=qr_size,
                        height=qr_size,
                        preserveAspectRatio=True,
                        mask="auto",
                    )

                    frappe.log_error(
                        f"QR code drawn at position: ({qr_x}, {qr_y}) with size: {qr_size}",
                        "PDF Generator",
                    )

                except Exception as e:
                    frappe.log_error(f"Error loading QR code: {e}", "PDF Generator")
                    # Fallback to text if image can't be loaded
                    c.drawCentredString(qr_x + qr_size / 2, qr_y + qr_size / 2, "QR CODE")
            else:
                frappe.log_error("No QR code found in invoice document", "PDF Generator")

        except Exception as e:
            frappe.log_error(f"Error processing PDF to image: {e}", "PDF Generator")
            # Fallback: draw simple text if image conversion fails
            c.setFont(font_name, 12)
            c.drawString(50, y - 50, f"Invoice: {invoice_doc.name}")
            c.drawString(50, y - 80, "Error converting PDF to image")
            c.drawString(50, y - 110, f"Error details: {str(e)}")

        finally:
            # Clean up temporary files
            if os.path.exists(temp_html_pdf_path):
                os.remove(temp_html_pdf_path)
            if os.path.exists(temp_image_path):
                os.remove(temp_image_path)

    except Exception as e:
        frappe.log_error(f"Error generating HTML content: {e}", "PDF Generator")
        # Fallback: draw simple text if HTML generation fails
        c.setFont(font_name, 12)
        c.drawString(50, y - 50, f"Invoice: {invoice_doc.name}")
        c.drawString(50, y - 80, "Error generating HTML content")

    # ---------- DRAW FOOTER ----------
    _draw_footer(c, width, font_name)

    c.save()


def check_page_break(
    c, y, height, margin_y=100, font_name="Cairo", font_size=9, debug=False, invoice_doc=None
):
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
        print(
            f"DEBUG: Current y={y}, margin_y={margin_y}, page_height={page_height}, page_break_needed={y < margin_y}"
        )

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
            file_path = frappe.get_site_path(
                "private", "files", file_url.split("/private/files/")[1]
            )
        else:
            # fallback: try relative to /public
            file_path = frappe.get_site_path("public", file_url.lstrip("/"))

        try:
            img_height = 45
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
                mask="auto",
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


def _draw_footer(c, width, font_name):
    """Draw footer section."""
    c.setFont(font_name, 8)
    c.drawCentredString(width / 2, 30, "This is a PDF/A-3A compliant invoice with embedded XML")
    print("here man")


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
    """Inject OutputIntent and XMP per PDF/A-3A, ensure no encryption and proper Catalog flags."""
    with pikepdf.open(temp_pdf_path, allow_overwriting_input=True) as pdf:
        if pdf.is_encrypted:
            raise RuntimeError("PDF must not be encrypted for PDF/A")

        # Create and attach XMP metadata
        xmp_bytes = build_xmp_metadata(invoice_doc)
        metadata_stream = pdf.make_stream(xmp_bytes)
        metadata_stream["/Subtype"] = Name("/XML")
        metadata_stream["/Type"] = Name("/Metadata")
        pdf.Root["/Metadata"] = metadata_stream

        # OutputIntent with sRGB IEC61966-2.1
        with open(icc_path, "rb") as f:
            icc_bytes = f.read()
        icc_stream = pdf.make_stream(icc_bytes)
        icc_stream["/N"] = 3

        oi = Dictionary(
            {
                "/Type": Name("/OutputIntent"),
                "/S": Name("/GTS_PDFA1"),
                "/OutputConditionIdentifier": "sRGB",
                "/OutputCondition": "sRGB IEC61966-2.1",
                "/Info": "sRGB IEC61966-2.1",
                "/DestOutputProfile": icc_stream,
            }
        )

        pdf.Root["/OutputIntents"] = Array([oi])
        pdf.Root["/Trapped"] = Name("/False")

        # PDF/A-3A tagging requirements
        pdf.Root["/Lang"] = String("en-US")
        pdf.Root["/MarkInfo"] = Dictionary({"/Marked": True})

        # Ensure page has StructParents
        pages = pdf.Root["/Pages"]
        first_page = pages["/Kids"][0]
        if not first_page.is_indirect:
            first_page = pdf.make_indirect(first_page)
        first_page["/StructParents"] = 0

        # Build minimal StructTreeRoot
        parent_tree = Dictionary({"/Nums": Array()})
        struct_tree_root = Dictionary(
            {
                "/Type": Name("/StructTreeRoot"),
                "/ParentTree": parent_tree,
                "/ParentTreeNextKey": 1,
                "/RoleMap": Dictionary(),
            }
        )

        struct_tree_root_ind = pdf.make_indirect(struct_tree_root)
        pdf.Root["/StructTreeRoot"] = struct_tree_root_ind

        # ViewerPreferences
        vp = pdf.Root.get("/ViewerPreferences", Dictionary())
        vp["/DisplayDocTitle"] = True
        pdf.Root["/ViewerPreferences"] = vp

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

        # Create temporary PDF
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_pdf:
            temp_pdf_path = temp_pdf.name

        try:
            # Generate base PDF
            draw_pdf_with_reportlab(temp_pdf_path, invoice_doc)

            # Create final PDF with embedded XML
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as final_pdf:
                final_pdf_path = final_pdf.name

            finalize_pdfa(temp_pdf_path, final_pdf_path, icc_path, xml_file, invoice_doc)

            # Read the generated PDF
            with open(final_pdf_path, "rb") as f:
                pdf_content = f.read()

            # Create File document in ERPNext
            pdf_filename = f"{invoice_name}_PDFA3.pdf"

            # Check if file already exists
            existing_file = frappe.db.exists(
                "File", {"attached_to_name": invoice_name, "file_name": pdf_filename}
            )

            if existing_file:
                # Update existing file
                file_doc = frappe.get_doc("File", existing_file)
                file_doc.content = pdf_content
                file_doc.save()
            else:
                # Create new file
                file_doc = frappe.get_doc(
                    {
                        "doctype": "File",
                        "file_name": pdf_filename,
                        "attached_to_doctype": "Sales Invoice",
                        "attached_to_name": invoice_name,
                        "content": pdf_content,
                        "is_private": 0,
                    }
                )
                file_doc.insert()

            frappe.db.commit()

            return {
                "status": "success",
                "message": file_doc.file_url,
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
            "message": "All required assets are available",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
