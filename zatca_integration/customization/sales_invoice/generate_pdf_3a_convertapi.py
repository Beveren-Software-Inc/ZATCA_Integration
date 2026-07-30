# ruff: noqa: E501

"""
Generate PDF/A-3A compliant PDF for Frappe Sales Invoice with embedded XML
This method uses the first approach: get print format HTML, attach to PDF, attach XML, create PDF3A
"""

import base64
import mimetypes
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import convertapi
import frappe
import pikepdf
from bs4 import BeautifulSoup
from frappe.core.doctype.file.utils import find_file_by_url
from frappe.utils import get_bench_path, get_url
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


def _set_convertapi_credentials(token: str) -> None:
    if not token:
        frappe.throw("ConvertAPI token is missing. Set it on Company → ConvertAPI Token.")
    convertapi.api_credentials = token


def _normalize_data_uri(src: str) -> str:
    """Fix common data-URI quirks (e.g. space after ';base64,')."""
    if src.startswith("data:") and ";base64, " in src:
        return src.replace(";base64, ", ";base64,", 1)
    return src


def _local_paths_for_src(path: str) -> list[str]:
    """Map a site-relative image path to possible on-disk locations."""
    path = unquote(path or "")
    if not path:
        return []

    if not path.startswith("/"):
        path = "/" + path

    candidates = []
    site_path = frappe.local.site_path

    if path.startswith("/files/"):
        candidates.append(os.path.join(site_path, "public", path.lstrip("/")))
    elif path.startswith("/private/files/"):
        candidates.append(os.path.join(site_path, path.lstrip("/")))
    elif path.startswith("/assets/"):
        candidates.append(os.path.join(get_bench_path(), "sites", path.lstrip("/")))
        # Fallback: app public assets under sites/assets already covered above
    else:
        # Generic public path under the site
        candidates.append(os.path.join(site_path, "public", path.lstrip("/")))

    return candidates


def _src_to_base64(src: str) -> str | None:
    """Load any printable image src as a data URI so ConvertAPI does not need network access."""
    if not src:
        return None

    src = src.strip()
    if src.startswith("data:"):
        return _normalize_data_uri(src)

    site_url = get_url().rstrip("/")
    path = src
    if src.startswith(site_url):
        path = src[len(site_url) :]
    elif "://" in src:
        # External absolute URL — leave for ConvertAPI to fetch
        return None

    parsed = urlparse(path if "://" in path else f"file://{path}")
    path_only = unquote(parsed.path or path)
    query = parse_qs(parsed.query)
    fid = (query.get("fid") or [None])[0]

    # Prefer File doctype content (covers renamed / private files)
    try:
        file_doc = find_file_by_url(path_only, name=fid)
        if not file_doc and path_only.startswith("/"):
            # Sometimes file_url is stored without leading host but with /files/...
            file_doc = find_file_by_url(path_only)
        if file_doc:
            content = file_doc.get_content()
            if content:
                mime = (
                    mimetypes.guess_type(file_doc.file_name or path_only)[0]
                    or mimetypes.guess_type(path_only)[0]
                    or "image/png"
                )
                return f"data:{mime};base64,{base64.b64encode(content).decode()}"
    except Exception:
        frappe.logger("pdf3a").error("Failed File lookup for image inline", exc_info=True)

    # Fallback: read from disk under the site/bench
    for local_path in _local_paths_for_src(path_only):
        try:
            if os.path.isfile(local_path):
                mime = mimetypes.guess_type(local_path)[0] or "image/png"
                with open(local_path, "rb") as fh:
                    return f"data:{mime};base64,{base64.b64encode(fh.read()).decode()}"
        except Exception:
            continue

    return None


def _replace_css_urls(css_text: str) -> str:
    def repl(match):
        raw = match.group(1).strip().strip("'\"")
        b64 = _src_to_base64(raw)
        if not b64:
            return match.group(0)
        return f"url('{b64}')"

    return re.sub(r"url\(([^)]+)\)", repl, css_text)


def prepare_html_for_convertapi(html: str) -> str:
    """
    Clean printview chrome and inline local images for ConvertAPI.

    Frappe printview includes a Print / Get PDF action banner (class print-hide)
    that is normally hidden by @media print CSS. ConvertAPI often cannot load
    that CSS from the site, so the banner text would otherwise appear in the PDF.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Remove print preview action UI ("Print", "Get PDF")
    for banner in soup.select(".action-banner"):
        banner.decompose()

    for tag in soup.select(".print-hide"):
        tag.decompose()

    # Match frappe.utils.pdf.toggle_visible_pdf behaviour
    for tag in soup.select(".visible-pdf"):
        classes = [c for c in (tag.get("class") or []) if c != "visible-pdf"]
        tag["class"] = classes

    for tag in soup.select(".hidden-pdf"):
        tag.decompose()

    for img in soup.find_all("img"):
        src = img.get("src")
        if not src:
            continue
        b64 = _src_to_base64(src)
        if b64:
            img["src"] = b64

    for tag in soup.find_all(style=True):
        tag["style"] = _replace_css_urls(tag["style"])

    for style_tag in soup.find_all("style"):
        if style_tag.string:
            style_tag.string.replace_with(_replace_css_urls(str(style_tag.string)))

    return str(soup)


def generate_pdf_from_print_format(invoice_doc, print_format: str, token: str) -> bytes:
    """Generate PDF from print format via ConvertAPI after inlining images."""
    try:
        html = frappe.get_print(
            doctype="Sales Invoice",
            name=invoice_doc.name,
            print_format=print_format,
            no_letterhead=0,
        )

        if not html:
            frappe.throw("Failed to generate HTML content from print format")

        html = prepare_html_for_convertapi(html)
        _set_convertapi_credentials(token)

        html_path = None
        out_dir = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".html", delete=False, encoding="utf-8"
            ) as html_file:
                html_file.write(html)
                html_path = html_file.name

            out_dir = tempfile.mkdtemp()
            result = convertapi.convert(
                "pdf",
                {
                    "File": html_path,
                    "PageSize": "a4",
                    "MarginTop": 10,
                    "MarginRight": 10,
                    "MarginBottom": 10,
                    "MarginLeft": 10,
                    "CssMediaType": "print",
                    "LoadLazy": True,
                },
                from_format="html",
            )
            saved_files = result.save_files(out_dir)
            if not saved_files:
                frappe.throw("ConvertAPI HTML→PDF returned no file")

            with open(saved_files[0], "rb") as pdf_file:
                return pdf_file.read()
        finally:
            if html_path and os.path.exists(html_path):
                os.remove(html_path)
            if out_dir and os.path.isdir(out_dir):
                for name in os.listdir(out_dir):
                    try:
                        os.remove(os.path.join(out_dir, name))
                    except OSError:
                        pass
                try:
                    os.rmdir(out_dir)
                except OSError:
                    pass

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


def convert_to_pdfa3a(pdf_path: str, token: str) -> None:
    """Convert PDF to PDF/A-3A using ConvertAPI."""
    out_dir = None
    try:
        _set_convertapi_credentials(token)
        out_dir = tempfile.mkdtemp()
        result = convertapi.convert(
            "pdfa",
            {
                "File": pdf_path,
                "PdfaVersion": "PdfA3a",
            },
            from_format="pdf",
        )
        saved_files = result.save_files(out_dir)
        if not saved_files:
            frappe.throw("ConvertAPI PDF/A conversion returned no file")

        with open(saved_files[0], "rb") as src, open(pdf_path, "wb") as dst:
            dst.write(src.read())

    except Exception as e:
        frappe.log_error(f"ConvertAPI PDF/A conversion failed: {e}", "PDF3A Generator")
        frappe.throw(f"ConvertAPI PDF/A conversion failed: {e}")
    finally:
        if out_dir and os.path.isdir(out_dir):
            for name in os.listdir(out_dir):
                try:
                    os.remove(os.path.join(out_dir, name))
                except OSError:
                    pass
            try:
                os.rmdir(out_dir)
            except OSError:
                pass


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

    convert_to_pdfa3a(final_pdf_path, token)


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
        if not token:
            frappe.throw("ConvertAPI token is missing. Set it on Company → ConvertAPI Token.")

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

        pdf_content = generate_pdf_from_print_format(invoice_doc, print_format, token)

        # Create temporary PDF file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_pdf:
            temp_pdf_path = temp_pdf.name
            temp_pdf.write(pdf_content)

        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as final_pdf:
                final_pdf_path = final_pdf.name

            finalize_pdfa(temp_pdf_path, final_pdf_path, icc_path, xml_file, invoice_doc, token)

            with open(final_pdf_path, "rb") as f:
                final_pdf_content = f.read()

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
