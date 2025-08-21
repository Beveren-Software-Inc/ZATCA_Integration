import json
import frappe
import os
from datetime import datetime
import pikepdf
import frappe
from frappe.utils.pdf import get_pdf
from frappe import _
from frappe.utils import get_url
import io


@frappe.whitelist(allow_guest=False)
def zatca_embed_qr_in_pdf(invoice_name, print_format=None):
    """
    Generate a PDF for a Sales Invoice, embed its related XML, and save as PDF/A-3.
    Use the system default.
    """
    try:
        # Fetch invoice document
        invoice_doc = frappe.get_doc("Sales Invoice", invoice_name)
        xml_file_path = invoice_doc.custom_invoice_xml
        xml_filename = os.path.basename(xml_file_path)

        language = "en"

        letterhead = invoice_doc.letter_head or None
        if not letterhead:
            default_lh = frappe.db.get_value("Letter Head", {"is_default": 1}, "name")
            if default_lh:
                letterhead = default_lh
        
        attachments = frappe.get_all(
            "File", filters={"attached_to_name": invoice_name}, fields=["file_name"]
        )
        
        xml_file = None
        for attachment in attachments:
            if attachment.file_name == xml_filename:
                xml_file = os.path.join(
                    frappe.local.site_path, "public", "files", attachment.file_name
                )
                break

        if not xml_file or not os.path.exists(xml_file):
            frappe.throw(f"No XML file found for the invoice {invoice_name}!")

        # Generate invoice PDF
        input_pdf = generate_invoice_pdf(
            invoice_doc,
            language=language,
            letterhead=letterhead,
            print_format=print_format
        )

        final_pdf_path = os.path.join(
            frappe.local.site_path,
            "public",
            "files",
            f"PDF-A3 {invoice_name} output.pdf"
        )

        # Embed XML into PDF with proper PDF/A-3 compliance
        embed_xml_file_in_pdf(input_pdf, xml_file, final_pdf_path, invoice_name)

        # Save file record
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_url": f"/files/PDF-A3 {invoice_name} output.pdf",
            "attached_to_doctype": "Sales Invoice",
            "attached_to_name": invoice_name,
            "is_private": 0
        })
        file_doc.insert(ignore_permissions=True)

        return get_url(file_doc.file_url)

    except pikepdf.PdfError as e:
        frappe.throw(_(f"Error processing the PDF: {e}"))
    except FileNotFoundError as e:
        frappe.throw(_(f"File not found: {e}"))
    except IOError as e:
        frappe.throw(_(f"I/O error: {e}"))


def embed_xml_file_in_pdf(input_pdf, xml_file, output_pdf, invoice_name):
    """Embed an XML file into a PDF and make it PDF/A-3 compliant."""
    icc_path = os.path.join(frappe.get_app_path("zatca_integration"), "public", "sRGB2014.icc")
   
    with pikepdf.open(input_pdf, allow_overwriting_input=True) as pdf:
        
        # Get XML file stats for proper metadata
        xml_stats = os.stat(xml_file)
        xml_size = xml_stats.st_size
        xml_mod_time = datetime.fromtimestamp(xml_stats.st_mtime)
        
        # -----------------------------
        # 1. Fix Font Issues for PDF/A-3 Compliance - The major cause
        # -----------------------------
        
        #All functions I have written still gives error, will revisit this later on.
        
        # -----------------------------
        # 2. Set PDF/A-3 XMP Metadata (CRITICAL)
        # -----------------------------
        xmp_metadata = create_xmp_metadata(invoice_name)
        # Set the XMP metadata
        pdf.Root["/Metadata"] = pdf.make_stream(xmp_metadata.encode("utf-8"))
        pdf.Root.Metadata["/Type"] = pikepdf.Name("/Metadata")
        pdf.Root.Metadata["/Subtype"] = pikepdf.Name("/XML")
        
        # -----------------------------
        # 3. Set PDF document info with proper date format
        # -----------------------------
        current_time = datetime.now()
        pdf_date = f"D:{current_time.strftime('%Y%m%d%H%M%S')}+00'00'"
        
        pdf.docinfo["/Title"] = f"ZATCA Invoice {invoice_name}"
        pdf.docinfo["/Author"] = "ERPNext ZATCA Integration"
        pdf.docinfo["/Subject"] = "ZATCA compliant invoice with embedded XML"
        pdf.docinfo["/Creator"] = "ERPNext ZATCA"
        pdf.docinfo["/Producer"] = "pikepdf"
        pdf.docinfo["/CreationDate"] = pikepdf.String(pdf_date)
        pdf.docinfo["/ModDate"] = pikepdf.String(pdf_date)
        pdf.docinfo["/Trapped"] = pikepdf.Name("/False")

        # -----------------------------
        # 4. Add Color Profile (ICC Profile) - FIXED
        # -----------------------------
        if os.path.exists(icc_path):
            with open(icc_path, "rb") as icc_file:
                icc_data = icc_file.read()
                
            # Create ICC profile stream
            icc_stream = pdf.make_stream(icc_data)
            icc_stream["/N"] = 3  # RGB color space
            
            output_intent_dict = pikepdf.Dictionary({
                "/Type": pikepdf.Name("/OutputIntent"),
                "/S": pikepdf.Name("/GTS_PDFA1"),
                "/OutputConditionIdentifier": pikepdf.String("sRGB"),
                "/Info": pikepdf.String("sRGB IEC61966-2.1"),
                "/DestOutputProfile": icc_stream,
                "/OutputCondition": pikepdf.String("sRGB")
            })
            
            pdf.Root["/OutputIntents"] = pikepdf.Array([output_intent_dict])
        else:
            # Fallback: Create a simple output intent without ICC profile
            frappe.log_error(f"ICC profile not found at {icc_path}", "ZATCA PDF Generation")
            output_intent_dict = pikepdf.Dictionary({
                "/Type": pikepdf.Name("/OutputIntent"),
                "/S": pikepdf.Name("/GTS_PDFA1"),
                "/OutputConditionIdentifier": pikepdf.String("sRGB"),
                "/Info": pikepdf.String("sRGB IEC61966-2.1"),
                "/OutputCondition": pikepdf.String("sRGB")
            })
            pdf.Root["/OutputIntents"] = pikepdf.Array([output_intent_dict])

        # -----------------------------
        # 5. Embed XML File with Complete Metadata - FIXED MIME TYPE
        # -----------------------------
        with open(xml_file, "rb") as xf:
            xml_data = xf.read()

        # Create the embedded file stream with proper parameters
        embedded_file_stream = pdf.make_stream(xml_data)
        embedded_file_stream["/Type"] = pikepdf.Name("/EmbeddedFile")
        embedded_file_stream["/Subtype"] = pikepdf.Name("/application/xml")  
        
        # Add file parameters with proper metadata
        xml_pdf_date = f"D:{xml_mod_time.strftime('%Y%m%d%H%M%S')}+00'00'"
        embedded_file_stream["/Params"] = pikepdf.Dictionary({
            "/Size": xml_size,
            "/CreationDate": pikepdf.String(xml_pdf_date),
            "/ModDate": pikepdf.String(xml_pdf_date),
            "/CheckSum": pikepdf.String(""),
        })

        # Create file specification dictionary with complete metadata
        xml_filename_base = os.path.basename(xml_file)
        embedded_file_dict = pikepdf.Dictionary({
            "/Type": pikepdf.Name("/Filespec"),
            "/F": pikepdf.String(xml_filename_base),
            "/UF": pikepdf.String(xml_filename_base), 
            "/EF": pikepdf.Dictionary({"/F": embedded_file_stream}),
            "/AFRelationship": pikepdf.Name("/Data"),  
            "/Desc": pikepdf.String(f"ZATCA XML for invoice {invoice_name}")
        })

        # -----------------------------
        # 6. Add to PDF Names Dictionary
        # -----------------------------
        if "/Names" not in pdf.Root:
            pdf.Root["/Names"] = pikepdf.Dictionary()
        if "/EmbeddedFiles" not in pdf.Root.Names:
            pdf.Root.Names["/EmbeddedFiles"] = pikepdf.Dictionary()
        if "/Names" not in pdf.Root.Names.EmbeddedFiles:
            pdf.Root.Names.EmbeddedFiles["/Names"] = pikepdf.Array()

        # Add to embedded files array
        pdf.Root.Names.EmbeddedFiles.Names.extend([
            pikepdf.String(xml_filename_base),
            embedded_file_dict
        ])
        

        pdf.Root["/AF"] = pikepdf.Array([embedded_file_dict])

        if "/StructTreeRoot" not in pdf.Root:
            pdf.Root["/StructTreeRoot"] = pikepdf.Dictionary({
                "/Type": pikepdf.Name("/StructTreeRoot")
            })
        
        pdf.Root["/MarkInfo"] = pikepdf.Dictionary({
            "/Marked": True,
            "/UserProperties": False,
            "/Suspects": False
        })
        
        pdf.Root["/Lang"] = pikepdf.String("en-US")
 
        pdf.Root["/Version"] = pikepdf.Name("/1.7")

        pdf.save(output_pdf, min_version=("1", 7))
        return output_pdf

def  create_xmp_metadata(invoice_name):
    xmp_metadata = f"""<?xpacket begin='' id='W5M0MpCehiHzreSzNTczkc9d'?>
<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="pikepdf">
    <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
        <rdf:Description rdf:about=""
            xmlns:dc="http://purl.org/dc/elements/1.1/"
            xmlns:pdf="http://ns.adobe.com/pdf/1.3/"
            xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/"
            xmlns:xmp="http://ns.adobe.com/xap/1.0/">
            <dc:format>application/pdf</dc:format>
            <dc:creator>
                <rdf:Seq>
                    <rdf:li>ERPNext ZATCA</rdf:li>
                </rdf:Seq>
            </dc:creator>
            <dc:title>
                <rdf:Alt>
                    <rdf:li xml:lang="en">ZATCA Invoice {invoice_name}</rdf:li>
                </rdf:Alt>
            </dc:title>
            <dc:description>
                <rdf:Alt>
                    <rdf:li xml:lang="en">ZATCA compliant invoice with embedded XML</rdf:li>
                </rdf:Alt>
            </dc:description>
            <xmp:CreateDate>{datetime.now().strftime('%Y-%m-%dT%H:%M:%S+00:00')}</xmp:CreateDate>
            <xmp:ModifyDate>{datetime.now().strftime('%Y-%m-%dT%H:%M:%S+00:00')}</xmp:ModifyDate>
            <xmp:CreatorTool>ERPNext ZATCA Integration</xmp:CreatorTool>
            <pdf:Producer>pikepdf</pdf:Producer>
            <pdf:Trapped>False</pdf:Trapped>
            <pdfaid:part>3</pdfaid:part>
            <pdfaid:conformance>A</pdfaid:conformance>
        </rdf:Description>
    </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""

    return xmp_metadata

                
def create_basic_tounicode_cmap():
    """
    Create a basic ToUnicode CMap for common characters.
    This ensures compliance with ISO 19005-3:2012 6.2.11.7
    """
    return """/CIDInit /ProcSet findresource begin
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
100 beginbfchar
<0020> <0020>
<0021> <0021>
<0022> <0022>
<0023> <0023>
<0024> <0024>
<0025> <0025>
<0026> <0026>
<0027> <0027>
<0028> <0028>
<0029> <0029>
<002A> <002A>
<002B> <002B>
<002C> <002C>
<002D> <002D>
<002E> <002E>
<002F> <002F>
<0030> <0030>
<0031> <0031>
<0032> <0032>
<0033> <0033>
<0034> <0034>
<0035> <0035>
<0036> <0036>
<0037> <0037>
<0038> <0038>
<0039> <0039>
<003A> <003A>
<003B> <003B>
<003C> <003C>
<003D> <003D>
<003E> <003E>
<003F> <003F>
<0040> <0040>
<0041> <0041>
<0042> <0042>
<0043> <0043>
<0044> <0044>
<0045> <0045>
<0046> <0046>
<0047> <0047>
<0048> <0048>
<0049> <0049>
<004A> <004A>
<004B> <004B>
<004C> <004C>
<004D> <004D>
<004E> <004E>
<004F> <004F>
<0050> <0050>
<0051> <0051>
<0052> <0052>
<0053> <0053>
<0054> <0054>
<0055> <0055>
<0056> <0056>
<0057> <0057>
<0058> <0058>
<0059> <0059>
<005A> <005A>
<005B> <005B>
<005C> <005C>
<005D> <005D>
<005E> <005E>
<005F> <005F>
<0060> <0060>
<0061> <0061>
<0062> <0062>
<0063> <0063>
<0064> <0064>
<0065> <0065>
<0066> <0066>
<0067> <0067>
<0068> <0068>
<0069> <0069>
<006A> <006A>
<006B> <006B>
<006C> <006C>
<006D> <006D>
<006E> <006E>
<006F> <006F>
<0070> <0070>
<0071> <0071>
<0072> <0072>
<0073> <0073>
<0074> <0074>
<0075> <0075>
<0076> <0076>
<0077> <0077>
<0078> <0078>
<0079> <0079>
<007A> <007A>
<007B> <007B>
<007C> <007C>
<007D> <007D>
<007E> <007E>
<00A0> <00A0>
<00A1> <00A1>
<00A2> <00A2>
<00A3> <00A3>
<00A4> <00A4>
<00A5> <00A5>
<00A6> <00A6>
<00A7> <00A7>
<00A8> <00A8>
<00A9> <00A9>
<00AA> <00AA>
<00AB> <00AB>
<00AC> <00AC>
<00AD> <00AD>
<00AE> <00AE>
<00AF> <00AF>
<00B0> <00B0>
<00B1> <00B1>
<00B2> <00B2>
<00B3> <00B3>
endbfchar
endcmap
CMapName currentdict /CMap defineresource pop
end
end"""


def generate_invoice_pdf(invoice, language="en", letterhead=None, print_format=None, public=False):
    """
    Generate a Sales Invoice PDF with local fonts suitable for PDF/A-3.

    Args:
        invoice (Document): Sales Invoice document.
        language (str): Language code ("en" or "ar").
        letterhead (str, optional): Letterhead name.
        print_format (str, optional): Print format.
        public (bool, optional): Save in public folder if True, else private.

    Returns:
        str: Full file path of generated PDF.
    """
    invoice_name = invoice.name
    original_lang = frappe.local.lang
    frappe.local.lang = language

    try:
        # Generate HTML from print format
        html = frappe.get_print(
            doctype="Sales Invoice",
            name=invoice_name,
            print_format=print_format,
            no_letterhead=not bool(letterhead),
            letterhead=letterhead
        )

        # Add PDF/A-3 friendly CSS with local fonts
        pdf_a3_css = """
        <style>
        @font-face {
            font-family: 'Cairo';
            src: url('/fonts//Cairo.otf') format('truetype');
        }
        @font-face {
            font-family: 'Amiri';
            src: url('/fonts/Amiri.ttf') format('truetype');
        }
        body, * {
            font-family: 'Cairo', 'Amiri', Arial, sans-serif !important;
        }
        .arabic-text {
            font-family: 'Amiri', 'Cairo', Arial, sans-serif;
            direction: rtl;
            unicode-bidi: bidi-override;
        }
        </style>
        """

        # Inject CSS before </head>
        if '</head>' in html:
            html = html.replace('</head>', pdf_a3_css + '</head>')
        else:
            html = pdf_a3_css + html

    finally:
        frappe.local.lang = original_lang

    # PDF options for wkhtmltopdf
    pdf_options = {
        'page-size': 'A4',
        'margin-top': '1in',
        'margin-right': '0.75in',
        'margin-bottom': '0.75in',
        'margin-left': '0.75in',
        'encoding': 'UTF-8',
        'enable-local-file-access': True,
        'no-outline': None
    }

    # Convert HTML to PDF
    pdf_content = get_pdf(html, options=pdf_options)
    
    # Determine file path
    folder_type = "public" if public else "private"
    files_dir = os.path.join(frappe.local.site_path, folder_type, "files")
    os.makedirs(files_dir, exist_ok=True)
    file_name = f"{invoice_name}.pdf"
    file_path = os.path.join(files_dir, file_name)

    # Save PDF
    with open(file_path, "wb") as f:
        f.write(pdf_content)

    return file_path
