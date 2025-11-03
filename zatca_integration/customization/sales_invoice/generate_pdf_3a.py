# ruff: noqa: E501

"""
Generate PDF/A-3A compliant PDF for Frappe Sales Invoice with embedded XML
Simple approach: use frappe.get_print() then add XML attachment
"""

import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import frappe
import pikepdf
from pikepdf import Array, Dictionary, Name, String

# Configuration paths
font_dir = Path(frappe.get_app_path("zatca_integration", "public", "fonts"))
icc_ = Path(frappe.get_app_path("zatca_integration", "public"))
icc_2014 = icc_ / "sRGB2014.icc"

cairo_regular = str(font_dir / "Cairo-Regular.ttf")

EMBEDDED_SRGB_ICC = icc_2014
EMBEDDED_FONT_TTF = cairo_regular

# Note: Using Ghostscript for PDF/A-3A conversion


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


def generate_pdf_from_print_format(invoice_doc):
    """Generate PDF from print format using frappe.get_print() - simple approach."""
    try:
        # Use frappe.get_print for simple PDF generation
        pdf_content = frappe.get_print(
            doctype="Sales Invoice",
            name=invoice_doc.name,
            print_format="Zatca PDF-A 3B",
            no_letterhead=0,
            as_pdf=True,
        )

        if pdf_content:
            frappe.log_error("PDF generated with frappe.get_print", "PDF3A Generator")
            return pdf_content
        else:
            frappe.throw("Failed to generate PDF content from print format")

    except Exception as e:
        frappe.log_error(f"Error generating PDF from print format: {e}", "PDF3A Generator")
        frappe.throw(f"Failed to generate PDF from print format: {str(e)}")


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


def check_ghostscript():
    """Check if Ghostscript is installed and available."""
    try:
        result = subprocess.run(["gs", "--version"], capture_output=True, text=True, check=True)
        version = result.stdout.strip()
        frappe.log_error(f"Ghostscript version: {version}", "PDF3A Generator")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        frappe.log_error(
            f"Ghostscript not found: {e}. Please install Ghostscript for PDF/A-3A conversion.",
            "PDF3A Generator",
        )
        return False


def convert_to_pdfa_with_ghostscript(input_pdf_path, output_pdf_path):
    """Convert PDF to PDF/A-3A using Ghostscript with proper color space and font handling."""
    try:
        # Get ICC profile path for proper color space
        icc_path = ensure_assets()

        # Ghostscript command for PDF/A-3A conversion with proper color space and font handling
        cmd = [
            "gs",
            "-dPDFA=3",  # PDF/A-3A compliance
            "-dBATCH",  # Batch mode (no interactive prompts)
            "-dNOPAUSE",  # Don't pause between pages
            "-sDEVICE=pdfwrite",  # Output device
            "-dPDFACompatibilityPolicy=1",  # PDF/A compatibility policy
            "-dAutoRotatePages=/None",  # Don't auto-rotate pages
            "-dColorImageDownsampleType=/Bicubic",
            "-dColorImageResolution=300",
            "-dGrayImageDownsampleType=/Bicubic",
            "-dGrayImageResolution=300",
            "-dMonoImageDownsampleType=/Bicubic",
            "-dMonoImageResolution=300",
            "-dEmbedAllFonts=true",  # Embed all fonts
            "-dSubsetFonts=false",  # Don't subset fonts - this is crucial for font consistency
            "-dCompressFonts=false",  # Don't compress fonts to avoid width issues
            "-dNOPLATFONTS",  # Don't use platform fonts
            "-dPDFSETTINGS=/prepress",  # High quality settings
            "-sColorConversionStrategy=RGB",  # Use RGB color conversion
            f"-sOutputICCProfile={icc_path}",  # Use our sRGB ICC profile
            f"-sDefaultRGBProfile={icc_path}",  # Set default RGB profile
            "-dUseCIEColor",  # Use CIE color space
            "-dOverrideICC=true",  # Override ICC profiles
            f"-sOutputFile={output_pdf_path}",
            input_pdf_path,
        ]

        frappe.log_error("Running Ghostscript PDF/A-3A conversion", "PDF3A Generator")
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        if result.stdout:
            frappe.log_error(f"GS stdout: {result.stdout[:200]}", "PDF3A Generator")
        if result.stderr:
            frappe.log_error(f"GS stderr: {result.stderr[:200]}", "PDF3A Generator")
        frappe.log_error("Successfully converted to PDF/A-3A using Ghostscript", "PDF3A Generator")
        return True

    except subprocess.CalledProcessError as e:
        frappe.log_error(f"Ghostscript conversion failed: {e.stderr}", "PDF3A Generator")
        return False
    except Exception as e:
        frappe.log_error(f"Error during Ghostscript conversion: {str(e)}", "PDF3A Generator")
        return False


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


def fix_font_width_consistency(pdf: pikepdf.Pdf) -> None:
    """
    Fixes font width consistency issues for PDF/A-3A compliance.
    Ensures glyph width information in font dictionary matches embedded font program.
    """
    try:
        frappe.log_error("Starting font width consistency fixes", "PDF3A Generator")

        # Track all fonts across all pages to avoid duplicates
        processed_fonts = set()

        for page in pdf.pages:
            try:
                resources = page.obj.get("/Resources", Dictionary())
                fonts = resources.get("/Font", Dictionary())

                if isinstance(fonts, pikepdf.Dictionary):
                    for font_name, font_ref in list(fonts.items()):
                        # Skip if already processed
                        font_id = str(font_ref)
                        if font_id in processed_fonts:
                            continue
                        processed_fonts.add(font_id)

                        try:
                            if hasattr(font_ref, "get_object"):
                                font_obj = font_ref.get_object()
                            else:
                                font_obj = font_ref

                            if isinstance(font_obj, pikepdf.Dictionary):
                                # Check if this is a Type1 or TrueType font
                                subtype = font_obj.get("/Subtype", None)
                                if subtype in [Name("/Type1"), Name("/TrueType")]:
                                    # Remove Widths array to force PDF reader to use embedded font widths
                                    if "/Widths" in font_obj:
                                        del font_obj["/Widths"]
                                        frappe.log_error(
                                            f"Removed Widths array from font {font_name}",
                                            "PDF3A Generator",
                                        )

                                    # Remove FirstChar and LastChar if Widths was removed
                                    if "/FirstChar" in font_obj:
                                        del font_obj["/FirstChar"]
                                    if "/LastChar" in font_obj:
                                        del font_obj["/LastChar"]

                                    # Ensure BaseFont is properly set
                                    base_font = font_obj.get("/BaseFont", None)
                                    if base_font:
                                        frappe.log_error(
                                            f"Font {font_name} has BaseFont: {base_font}",
                                            "PDF3A Generator",
                                        )

                                # Handle CIDFontType2 fonts (common in PDF/A issues)
                                elif subtype == Name("/CIDFontType2"):
                                    # Remove W array (widths) to use embedded font program widths
                                    if "/W" in font_obj:
                                        del font_obj["/W"]
                                        frappe.log_error(
                                            f"Removed W array from CIDFont {font_name}",
                                            "PDF3A Generator",
                                        )

                                    # Remove DW (default width) if present
                                    if "/DW" in font_obj:
                                        del font_obj["/DW"]
                                        frappe.log_error(
                                            f"Removed DW from CIDFont {font_name}",
                                            "PDF3A Generator",
                                        )

                                    # Ensure CIDSystemInfo is present
                                    if "/CIDSystemInfo" not in font_obj:
                                        font_obj["/CIDSystemInfo"] = Dictionary(
                                            {
                                                Name("/Registry"): pikepdf.String("Adobe"),
                                                Name("/Ordering"): pikepdf.String("Identity"),
                                                Name("/Supplement"): pikepdf.Number(0),
                                            }
                                        )
                                        frappe.log_error(
                                            f"Added CIDSystemInfo to font {font_name}",
                                            "PDF3A Generator",
                                        )

                                # Handle Type0 fonts (composite fonts)
                                elif subtype == Name("/Type0"):
                                    # Get the descendant font
                                    descendant = font_obj.get("/DescendantFonts", None)
                                    if (
                                        descendant
                                        and isinstance(descendant, pikepdf.Array)
                                        and len(descendant) > 0
                                    ):
                                        try:
                                            desc_ref = descendant[0]
                                            if hasattr(desc_ref, "get_object"):
                                                desc_obj = desc_ref.get_object()
                                            else:
                                                desc_obj = desc_ref

                                            if isinstance(desc_obj, pikepdf.Dictionary):
                                                desc_subtype = desc_obj.get("/Subtype", None)
                                                if desc_subtype == Name("/CIDFontType2"):
                                                    # Apply same fixes to descendant CIDFont
                                                    if "/W" in desc_obj:
                                                        del desc_obj["/W"]
                                                        frappe.log_error(
                                                            f"Removed W array from descendant CIDFont in {font_name}",
                                                            "PDF3A Generator",
                                                        )
                                                    if "/DW" in desc_obj:
                                                        del desc_obj["/DW"]
                                                        frappe.log_error(
                                                            f"Removed DW from descendant CIDFont in {font_name}",
                                                            "PDF3A Generator",
                                                        )
                                        except Exception as desc_error:
                                            frappe.log_error(
                                                f"Failed to fix descendant font in {font_name}: {desc_error}",
                                                "PDF3A Generator",
                                            )

                        except Exception as font_error:
                            frappe.log_error(
                                f"Failed to fix font {font_name}: {font_error}", "PDF3A Generator"
                            )
                            continue

            except Exception as page_error:
                frappe.log_error(f"Failed to process page fonts: {page_error}", "PDF3A Generator")
                continue

        # Also check for fonts in the document catalog
        try:
            if "/AcroForm" in pdf.Root:
                acroform = pdf.Root["/AcroForm"]
                if isinstance(acroform, pikepdf.Dictionary) and "/DR" in acroform:
                    dr = acroform["/DR"]
                    if isinstance(dr, pikepdf.Dictionary) and "/Font" in dr:
                        fonts = dr["/Font"]
                        if isinstance(fonts, pikepdf.Dictionary):
                            for font_name, font_ref in list(fonts.items()):
                                try:
                                    if hasattr(font_ref, "get_object"):
                                        font_obj = font_ref.get_object()
                                    else:
                                        font_obj = font_ref

                                    if isinstance(font_obj, pikepdf.Dictionary):
                                        subtype = font_obj.get("/Subtype", None)
                                        if (
                                            subtype in [Name("/Type1"), Name("/TrueType")]
                                            and "/Widths" in font_obj
                                        ):
                                            del font_obj["/Widths"]
                                            frappe.log_error(
                                                f"Removed Widths array from AcroForm font {font_name}",
                                                "PDF3A Generator",
                                            )
                                except Exception as acro_error:
                                    frappe.log_error(
                                        f"Failed to fix AcroForm font {font_name}: {acro_error}",
                                        "PDF3A Generator",
                                    )
                                    continue
        except Exception as catalog_error:
            frappe.log_error(
                f"Failed to process document catalog fonts: {catalog_error}", "PDF3A Generator"
            )

        frappe.log_error("Completed font width consistency fixes", "PDF3A Generator")
    except Exception as e:
        frappe.log_error(f"fix_font_width_consistency failed: {e}", "PDF3A Generator")


def fix_image_interpolation(pdf: pikepdf.Pdf) -> None:
    """Ensure all images have Interpolate=false to satisfy PDF/A 6.2.8.
    Updates XObject images and patches inline image flags in content streams.
    """
    try:
        frappe.log_error("Starting image interpolation fixes", "PDF3A Generator")

        # Fix all XObject images globally
        try:
            for page in pdf.pages:
                try:
                    resources = page.obj.get("/Resources", Dictionary())
                    xobjects = resources.get("/XObject", Dictionary())
                    if isinstance(xobjects, pikepdf.Dictionary):
                        for name, xo in list(xobjects.items()):
                            try:
                                # Check if xo is a reference or direct object
                                if hasattr(xo, "get_object"):
                                    xo_obj = xo.get_object()
                                else:
                                    xo_obj = xo

                                if isinstance(xo_obj, pikepdf.Stream):
                                    sub = xo_obj.stream_dict.get("/Subtype", None)
                                    if sub == Name("/Image"):
                                        # Force Interpolate to false
                                        xo_obj.stream_dict[Name("/Interpolate")] = pikepdf.Boolean(
                                            False
                                        )
                                        frappe.log_error(
                                            f"Fixed XObject image {name} interpolation",
                                            "PDF3A Generator",
                                        )
                            except Exception as e:
                                frappe.log_error(
                                    f"Failed to fix XObject {name}: {e}", "PDF3A Generator"
                                )
                                continue
                except Exception as page_error:
                    frappe.log_error(
                        f"Failed to process page resources: {page_error}", "PDF3A Generator"
                    )
                    continue
        except Exception as e:
            frappe.log_error(f"XObject image fix failed: {e}", "PDF3A Generator")

        # Fix inline images in content streams more aggressively
        try:
            for page in pdf.pages:
                try:
                    contents = page.obj.get("/Contents", None)
                    if contents is None:
                        continue

                    def patch_stream(s: pikepdf.Stream) -> None:
                        try:
                            data = bytes(s.read_bytes())
                            original_len = len(data)

                            # More comprehensive replacements
                            replacements = [
                                (b"/Interpolate true", b"/Interpolate false"),
                                (b"/I true", b"/I false"),
                                (b"/Interpolate true\n", b"/Interpolate false\n"),
                                (b"/I true\n", b"/I false\n"),
                                (b"/Interpolate true\r\n", b"/Interpolate false\r\n"),
                                (b"/I true\r\n", b"/I false\r\n"),
                                (b"/Interpolate true ", b"/Interpolate false "),
                                (b"/I true ", b"/I false "),
                            ]

                            for old, new in replacements:
                                data = data.replace(old, new)

                            if len(data) != original_len:
                                frappe.log_error(
                                    "Patched inline image flags in content stream",
                                    "PDF3A Generator",
                                )
                                s.set_data(data)
                        except Exception as e:
                            frappe.log_error(
                                f"Failed to patch content stream: {e}", "PDF3A Generator"
                            )

                    if isinstance(contents, pikepdf.Array):
                        for cs in contents:
                            try:
                                if hasattr(cs, "get_object"):
                                    cs_obj = cs.get_object()
                                else:
                                    cs_obj = cs
                                if isinstance(cs_obj, pikepdf.Stream):
                                    patch_stream(cs_obj)
                            except Exception as cs_error:
                                frappe.log_error(
                                    f"Failed to process content stream: {cs_error}",
                                    "PDF3A Generator",
                                )
                                continue
                    elif isinstance(contents, pikepdf.Stream):
                        patch_stream(contents)
                except Exception as page_error:
                    frappe.log_error(
                        f"Failed to process page contents: {page_error}", "PDF3A Generator"
                    )
                    continue
        except Exception as e:
            frappe.log_error(f"Inline image fix failed: {e}", "PDF3A Generator")

        frappe.log_error("Completed image interpolation fixes", "PDF3A Generator")
    except Exception as e:
        frappe.log_error(f"fix_image_interpolation failed: {e}", "PDF3A Generator")


def finalize_pdfa(
    temp_pdf_path: str, final_pdf_path: str, icc_path: str, xml_path: str, invoice_doc
):
    """Embed XML, set XMP + OutputIntent via pikepdf, then convert to PDF/A-3A with Ghostscript."""
    try:
        with pikepdf.open(temp_pdf_path, allow_overwriting_input=True) as pdf:
            if pdf.is_encrypted:
                raise RuntimeError("PDF must not be encrypted for PDF/A")

            # Fix fonts before metadata
            fix_font_embedding(pdf)
            # Fix font width consistency for PDF/A-3A compliance
            fix_font_width_consistency(pdf)
            # Ensure image interpolation disabled
            fix_image_interpolation(pdf)

            # XMP metadata
            xmp_bytes = build_xmp_metadata(invoice_doc)
            metadata_stream = pdf.make_stream(xmp_bytes)
            metadata_stream["/Subtype"] = Name("/XML")
            metadata_stream["/Type"] = Name("/Metadata")
            pdf.Root["/Metadata"] = metadata_stream

            # OutputIntent (sRGB)
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

            # Basic tagging flags
            pdf.Root["/Lang"] = String("en-US")
            pdf.Root["/MarkInfo"] = Dictionary({"/Marked": True})

            # Minimal logical structure tree (StructTreeRoot) and page StructParents
            try:
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

                # Ensure each page has StructParents
                try:
                    for idx, page in enumerate(pdf.pages):
                        page_obj = page.obj
                        page_obj["/StructParents"] = idx
                except Exception:
                    # Fallback: set on first page if iteration fails
                    pages_dict = pdf.Root.get("/Pages")
                    if pages_dict and "/Kids" in pages_dict:
                        first_page = pages_dict["/Kids"][0]
                        if not first_page.is_indirect:
                            first_page = pdf.make_indirect(first_page)
                        first_page["/StructParents"] = 0
            except Exception as tag_e:
                frappe.log_error(
                    f"Failed to add StructTreeRoot/StructParents: {tag_e}", "PDF3A Generator"
                )

            # Embed XML attachment
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
                filename = f"{invoice_doc.name}_zatca.xml"
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
                names_dict = pdf.Root.get("/Names", Dictionary())
                names_dict["/EmbeddedFiles"] = Dictionary(
                    {"/Names": Array([String(filename), filespec_ind])}
                )
                pdf.Root["/Names"] = names_dict
                pdf.Root["/AF"] = Array([filespec_ind])

            # Save interim
            try:
                from pikepdf import PdfVersion

                pdf.save(temp_pdf_path, linearize=False, min_version=PdfVersion.v1_7)
            except Exception:
                pdf.save(temp_pdf_path, linearize=False)

        # Ghostscript conversion
        if check_ghostscript():
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_converted:
                temp_converted_path = temp_converted.name
            if convert_to_pdfa_with_ghostscript(temp_pdf_path, temp_converted_path):
                try:
                    with pikepdf.open(
                        temp_converted_path, allow_overwriting_input=True
                    ) as converted_pdf:
                        fix_font_embedding(converted_pdf)
                        fix_image_interpolation(converted_pdf)
                        converted_pdf.save(temp_converted_path, linearize=False)
                except Exception:
                    pass
                with open(temp_converted_path, "rb") as src, open(final_pdf_path, "wb") as dst:
                    dst.write(src.read())
                os.unlink(temp_converted_path)
            else:
                # fallback to original
                with open(temp_pdf_path, "rb") as src, open(final_pdf_path, "wb") as dst:
                    dst.write(src.read())
        else:
            # no GS, just copy
            with open(temp_pdf_path, "rb") as src, open(final_pdf_path, "wb") as dst:
                dst.write(src.read())
        return True
    except Exception as e:
        frappe.log_error(f"PDF/A finalize (pikepdf) failed: {e}", "PDF3A Generator")
        return False


@frappe.whitelist()
def generate_pdf3a_with_xml(invoice_name):
    """
    Generate PDF/A-3A compliant PDF for Sales Invoice with embedded XML.
    Simple approach: use frappe.get_print() then add XML attachment
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

        # Generate PDF from print format using simple approach
        pdf_content = generate_pdf_from_print_format(invoice_doc)

        if not pdf_content:
            frappe.throw("Failed to generate PDF content from print format")

        try:
            # Create final PDF path
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as final_pdf:
                final_pdf_path = final_pdf.name

            # Write input PDF to temp path for pikepdf processing
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_pdf_in:
                temp_input_path = temp_pdf_in.name
                temp_pdf_in.write(pdf_content)

            # Finalize using pikepdf + Ghostscript
            if not finalize_pdfa(temp_input_path, final_pdf_path, icc_path, xml_file, invoice_doc):
                frappe.throw("Failed to finalize PDF/A-3A document")

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
            if os.path.exists(final_pdf_path):
                os.remove(final_pdf_path)
            if "temp_input_path" in locals() and os.path.exists(temp_input_path):
                os.remove(temp_input_path)

    except Exception as e:
        frappe.log_error(f"Error generating PDF3A: {str(e)}", "PDF3A Generator")
        frappe.throw(f"Failed to generate PDF3A: {str(e)}")
