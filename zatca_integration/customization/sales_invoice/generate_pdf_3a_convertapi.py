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

from zatca_integration.saudi_arabia_electronic_invoicing.utils import get_pdf_3a_token

# Configuration paths
font_dir = Path(frappe.get_app_path("zatca_integration", "public", "fonts"))
icc_ = Path(frappe.get_app_path("zatca_integration", "public"))
icc_2014 = icc_ / "sRGB2014.icc"

cairo_regular = str(font_dir / "Cairo-Regular.ttf")

EMBEDDED_SRGB_ICC = icc_2014
EMBEDDED_FONT_TTF = cairo_regular


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


def generate_pdf_from_print_format(invoice_doc, print_format: str) -> bytes:
    """Generate PDF from print format HTML using default Zatca PDF-A 3B format."""
    try:
        print("Generating PDF from print format...", print_format)
        html = frappe.get_print(
            doctype="Sales Invoice",
            name=invoice_doc.name,
            print_format=print_format,
            no_letterhead=0,
        )

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

        except Exception as e:
            frappe.log_error(f"wkhtmltopdf generation failed: {e}", "PDF3A Generator")

        if not pdf_content:
            frappe.throw("Failed to create PDF/A compliant PDF")

        return pdf_content

    except Exception as e:
        frappe.log_error(f"Error generating PDF from print format: {e}", "PDF3A Generator")
        frappe.throw(f"Failed to generate PDF from print format: {str(e)}")


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
    temp_pdf_path: str, final_pdf_path: str, icc_path: str, xml_path: str, invoice_doc, token: str
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
        out_dir = tempfile.mkdtemp()

        convertapi.api_credentials = token
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

    except Exception as e:
        frappe.log_error(f"ConvertAPI PDF/A conversion failed: {e}", "PDF3A Generator")


@frappe.whitelist()
def generate_pdf3a_with_xml(invoice_name, print_format):
    """
    Generate PDF/A-3A compliant PDF for Sales Invoice with embedded XML.
    Uses the first approach: get print format HTML, attach to PDF, attach XML, create PDF3A
    """
    try:
        if not frappe.db.exists("Sales Invoice", invoice_name):
            frappe.throw(f"Sales Invoice {invoice_name} does not exist")

        # Get invoice document
        invoice_doc = frappe.get_doc("Sales Invoice", invoice_name)
        token = get_pdf_3a_token(invoice_doc.company)
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
        pdf_content = generate_pdf_from_print_format(invoice_doc, print_format)

        # Create temporary PDF file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_pdf:
            temp_pdf_path = temp_pdf.name
            temp_pdf.write(pdf_content)

        try:
            # Create final PDF with embedded XML
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as final_pdf:
                final_pdf_path = final_pdf.name

            finalize_pdfa(temp_pdf_path, final_pdf_path, icc_path, xml_file, invoice_doc, token)

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
