


import json
import frappe
import os
from datetime import datetime
import pikepdf
import frappe
from frappe.utils.pdf import get_pdf
from frappe import _
from frappe.utils import get_url


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

        # Use default language if not provided
        language = "en"

        letterhead = invoice_doc.letter_head or None
        # If no letterhead provided, get default
        if not letterhead:
            default_lh = frappe.db.get_value("Letter Head", {"is_default": 1}, "name")
            if default_lh:
                letterhead = default_lh
        
        # Find XML attachment
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

        # Output file path
        final_pdf_path = os.path.join(
            frappe.local.site_path,
            "public",
            "files",
            f"PDF-A3 {invoice_name} output.pdf"
        )

        # Embed XML into PDF
        with pikepdf.Pdf.open(input_pdf, allow_overwriting_input=True) as pdf:
            with open(xml_file, "rb") as xml_attachment:
                pdf.attachments["invoice.xml"] = xml_attachment.read()
            pdf.save(input_pdf)

            # Ensure PDF/A-3 compliance
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
        # -----------------------------
        # 1. Set PDF Metadata
        # -----------------------------
        with pdf.open_metadata() as metadata:
            metadata["pdf:Trapped"] = "False"
            metadata["dc:creator"] = ["ERPNext ZATCA"]  
            metadata["dc:title"] = "ZATCA Invoice PDF/A-3"
            metadata["dc:description"] = "Invoice with embedded ZATCA XML"
            metadata["dc:date"] = datetime.now().isoformat()

        # -----------------------------
        # 2. Build XMP Metadata
        # -----------------------------
        xmp_metadata = f"""<?xpacket begin='' id='W5M0MpCehiHzreSzNTczkc9d'?>
        <x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="XMP toolkit 2.9.1">
            <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
                <rdf:Description rdf:about=""
                    xmlns:dc="http://purl.org/dc/elements/1.1/"
                    xmlns:pdf="http://ns.adobe.com/pdf/1.3/"
                    xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/">
                    <pdf:Producer>pikepdf</pdf:Producer>
                    <pdf:Trapped>False</pdf:Trapped>
                    <dc:creator>
                        <rdf:Seq>
                            <rdf:li>ERPNext ZATCA</rdf:li>
                        </rdf:Seq>
                    </dc:creator>
                    <dc:title>
                        <rdf:Alt>
                            <rdf:li xml:lang="x-default">ZATCA Invoice PDF/A-3</rdf:li>
                        </rdf:Alt>
                    </dc:title>
                    <dc:description>
                        <rdf:Alt>
                            <rdf:li xml:lang="x-default">Invoice with embedded ZATCA XML</rdf:li>
                        </rdf:Alt>
                    </dc:description>
                    <pdfaid:part>3</pdfaid:part>
                    <pdfaid:conformance>A</pdfaid:conformance>
                </rdf:Description>
            </rdf:RDF>
        </x:xmpmeta>
        <?xpacket end="w"?>"""

        if "/StructTreeRoot" not in pdf.Root:
            pdf.Root["/StructTreeRoot"] = pikepdf.Dictionary()
        pdf.Root["/Metadata"] = pdf.make_stream(xmp_metadata.encode("utf-8"))
        pdf.Root["/MarkInfo"] = pikepdf.Dictionary({"/Marked": True})
        pdf.Root["/Lang"] = pikepdf.String("en-US")

        # -----------------------------
        # 3. Embed XML File
        # -----------------------------
        with open(xml_file, "rb") as xf:
            xml_data = xf.read()

        embedded_file_stream = pdf.make_stream(xml_data)
        embedded_file_stream.Type = "/EmbeddedFile"
        embedded_file_stream.Subtype = "/application/xml"

        embedded_file_dict = pikepdf.Dictionary({
            "/Type": "/Filespec",
            "/F": pikepdf.String(os.path.basename(xml_file)),
            "/EF": pikepdf.Dictionary({"/F": embedded_file_stream}),
            "/AFRelationship": pikepdf.Name("/Data"),
            "/Desc": "ZATCA Invoice XML"
        })

        if "/Names" not in pdf.Root:
            pdf.Root.Names = pikepdf.Dictionary()
        if "/EmbeddedFiles" not in pdf.Root.Names:
            pdf.Root.Names.EmbeddedFiles = pikepdf.Dictionary()
        if "/Names" not in pdf.Root.Names.EmbeddedFiles:
            pdf.Root.Names.EmbeddedFiles.Names = pikepdf.Array()

        pdf.Root.Names.EmbeddedFiles.Names.append(
            pikepdf.String(os.path.basename(xml_file))
        )
        pdf.Root.Names.EmbeddedFiles.Names.append(embedded_file_dict)
        
        #Added to enforce the embedded file to be recognized as an attachment
        pdf.Root["/AF"] = pikepdf.Array([embedded_file_dict])

        #OutputIntent
        with open(icc_path, "rb") as icc_file:
            icc_data = icc_file.read()
            output_intent_dict = pikepdf.Dictionary(
                {
                    "/Type": "/OutputIntent",
                    "/S": "/GTS_PDFA1",
                    "/OutputConditionIdentifier": "sRGB",
                    "/Info": "sRGB IEC61966-2.1",
                    "/DestOutputProfile": pdf.make_stream(icc_data),
                }
            )
            if "/OutputIntents" not in pdf.Root:
                pdf.Root["/OutputIntents"] = pikepdf.Array([output_intent_dict])
            else:
                pdf.Root.OutputIntents.append(output_intent_dict)
                
        # -----------------------------
        # 4. Final  Compliance Info
        # -----------------------------
        #added latest just to test if its missing piece for compliance
        pdf.Root["/GTS_PDFA1"] = pikepdf.Name("/PDF/A-3A")
        pdf.docinfo["/GTS_PDFA1"] = "PDF/A-3A"
        ########################################
        
        # Set PDF metadata
        
        pdf.docinfo["/Title"] = invoice_name
        pdf.docinfo["/Author"] = "ERPNext ZATCA Integration"
        pdf.docinfo["/Subject"] = "Invoice with Embedded XML"
        pdf.docinfo["/Creator"] = "ERPNext ZATCA"
        pdf.docinfo["/Producer"] = "pikepdf"
        pdf.docinfo["/CreationDate"] = datetime.now().isoformat()

        # -----------------------------
        # 5. Save File
        # -----------------------------
        pdf.save(output_pdf)

        print(f"✅ XML embedded successfully into {output_pdf}")


def generate_invoice_pdf(invoice, language, letterhead=None, print_format=None, public=False):
    """
    Generate a Sales Invoice PDF with the specified language, print format, and letterhead.

    Args:
        invoice (Document): Sales Invoice document object.
        language (str): Language code (e.g., "en", "ar").
        letterhead (str, optional): Letterhead name. Defaults to None.
        print_format (str, optional): Print format name. Defaults to None.
        public (bool, optional): Store file in public folder if True, else private. Defaults to False.

    Returns:
        str: Full file path of the generated PDF.
    """
    invoice_name = invoice.name

    # Store original language to restore later
    original_language = frappe.local.lang
    frappe.local.lang = language

    try:
        # Generate HTML content for the invoice
        html = frappe.get_print(
            doctype="Sales Invoice",
            name=invoice_name,
            print_format=print_format,
            no_letterhead=not bool(letterhead),
            letterhead=letterhead
        )
    finally:
        frappe.local.lang = original_language

    # Convert HTML to PDF
    pdf_content = get_pdf(html)

    folder_type = "public" if public else "private"
    site_path = frappe.local.site_path
    files_dir = os.path.join(site_path, folder_type, "files")

    os.makedirs(files_dir, exist_ok=True)

    # Save PDF
    file_name = f"{invoice_name}.pdf"
    file_path = os.path.join(files_dir, file_name)

    with open(file_path, "wb") as pdf_file:
        pdf_file.write(pdf_content)

    return file_path
# import json
# import frappe
# import os
# from datetime import datetime
# import pikepdf
# import frappe
# from frappe.utils.pdf import get_pdf
# from frappe import _
# from frappe.utils import get_url


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

#         # Use default language if not provided
#         language = "en"

#         letterhead = invoice_doc.letter_head or None
#         # If no letterhead provided, get default
#         if not letterhead:
#             default_lh = frappe.db.get_value("Letter Head", {"is_default": 1}, "name")
#             if default_lh:
#                 letterhead = default_lh
        
#         # Find XML attachment
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

#         # Output file path
#         final_pdf_path = os.path.join(
#             frappe.local.site_path,
#             "public",
#             "files",
#             f"PDF-A3 {invoice_name} output.pdf"
#         )

#         # Ensure PDF/A-3A compliance and embed XML
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
#     """Embed an XML file into a PDF and make it PDF/A-3A compliant to match ZATCA SDK standard."""
#     icc_path = os.path.join(frappe.get_app_path("zatca_integration"), "public", "sRGB2014.icc")
    
#     # Validate ICC profile exists
#     if not os.path.exists(icc_path):
#         frappe.throw(_("ICC Color Profile file not found: {0}").format(icc_path))

#     with pikepdf.open(input_pdf, allow_overwriting_input=True) as pdf:
#         # -----------------------------
#         # 1. Enhanced XMP Metadata for PDF/A-3A (ZATCA SDK Standard)
#         # -----------------------------
#         current_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+03:00")  # Saudi timezone
        
#         xmp_metadata = f"""<?xpacket begin="\uFEFF" id="W5M0MpCehiHzreSzNTczkc9d"?>
# <x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Adobe XMP Core 9.0-c001 152.deb9585, 2024/02/06-08:21:05">
#     <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
#         <rdf:Description rdf:about=""
#             xmlns:dc="http://purl.org/dc/elements/1.1/"
#             xmlns:pdf="http://ns.adobe.com/pdf/1.3/"
#             xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/"
#             xmlns:xmp="http://ns.adobe.com/xap/1.0/"
#             xmlns:pdfx="http://ns.adobe.com/pdfx/1.3/">
            
#             <!-- Document Metadata -->
#             <dc:format>application/pdf</dc:format>
#             <dc:creator>
#                 <rdf:Seq>
#                     <rdf:li>ERPNext ZATCA Integration</rdf:li>
#                 </rdf:Seq>
#             </dc:creator>
#             <dc:title>
#                 <rdf:Alt>
#                     <rdf:li xml:lang="en-US">ZATCA Invoice PDF/A-3A - {invoice_name}</rdf:li>
#                     <rdf:li xml:lang="ar-SA">فاتورة هيئة الزكاة والضريبة والجمارك - {invoice_name}</rdf:li>
#                 </rdf:Alt>
#             </dc:title>
#             <dc:description>
#                 <rdf:Alt>
#                     <rdf:li xml:lang="en-US">Saudi ZATCA Compliant Electronic Invoice with Embedded XML</rdf:li>
#                     <rdf:li xml:lang="ar-SA">فاتورة إلكترونية متوافقة مع هيئة الزكاة والضريبة والجمارك مع XML مدمج</rdf:li>
#                 </rdf:Alt>
#             </dc:description>
#             <dc:subject>
#                 <rdf:Bag>
#                     <rdf:li>ZATCA</rdf:li>
#                     <rdf:li>Invoice</rdf:li>
#                     <rdf:li>Saudi Arabia</rdf:li>
#                     <rdf:li>Electronic Billing</rdf:li>
#                     <rdf:li>UBL 2.1</rdf:li>
#                     <rdf:li>Aramco</rdf:li>
#                 </rdf:Bag>
#             </dc:subject>
            
#             <!-- PDF Metadata -->
#             <pdf:Producer>ERPNext ZATCA PDF/A-3A Generator with pikepdf</pdf:Producer>
#             <pdf:Trapped>False</pdf:Trapped>
#             <pdf:Keywords>ZATCA, Invoice, Saudi Arabia, PDF/A-3A, UBL, Electronic, Aramco</pdf:Keywords>
            
#             <!-- XMP Metadata -->
#             <xmp:CreateDate>{current_time}</xmp:CreateDate>
#             <xmp:ModifyDate>{current_time}</xmp:ModifyDate>
#             <xmp:MetadataDate>{current_time}</xmp:MetadataDate>
#             <xmp:CreatorTool>ERPNext ZATCA Integration v3.0</xmp:CreatorTool>
            
#             <!-- PDF/A-3A Identification (ZATCA SDK Standard) -->
#             <pdfaid:part>3</pdfaid:part>
#             <pdfaid:conformance>A</pdfaid:conformance>
            
#         </rdf:Description>
#     </rdf:RDF>
# </x:xmpmeta>
# <?xpacket end="w"?>"""

#         # Set XMP metadata stream with proper attributes
#         metadata_stream = pdf.make_stream(xmp_metadata.encode("utf-8"))
#         metadata_stream.Type = "/Metadata"
#         metadata_stream.Subtype = "/XML"
#         pdf.Root["/Metadata"] = metadata_stream

#         # -----------------------------
#         # 2. PDF/A-3A Compliance Settings (ZATCA SDK Standard)
#         # -----------------------------
#         # Set MarkInfo for accessibility - Required for PDF/A-3A
#         pdf.Root["/MarkInfo"] = pikepdf.Dictionary({
#             "/Marked": True,
#             "/UserProperties": False,
#             "/Suspects": False
#         })
        
#         # Set language and viewer preferences
#         pdf.Root["/Lang"] = pikepdf.String("en-US")
#         pdf.Root["/ViewerPreferences"] = pikepdf.Dictionary({
#             "/DisplayDocTitle": True
#         })

#         # PDF version is managed by pikepdf automatically (cannot be set directly)
#         # The PDF will use an appropriate version (1.7 or higher) for PDF/A-3A compliance

#         # -----------------------------
#         # 3. Enhanced Embedded File with Proper MIME Type
#         # -----------------------------
#         with open(xml_file, "rb") as xf:
#             xml_data = xf.read()
        
#         # Validate XML content
#         if not xml_data or len(xml_data) == 0:
#             frappe.throw(_("XML file is empty or invalid: {0}").format(xml_file))

#         # Create embedded file stream with proper parameters
#         embedded_file_stream = pdf.make_stream(xml_data)
#         embedded_file_stream.Type = "/EmbeddedFile"
#         embedded_file_stream.Subtype = "/text#2Fxml"  
#         embedded_file_stream.Params = pikepdf.Dictionary({
#             "/ModDate": pikepdf.String(f"D:{datetime.now().strftime('%Y%m%d%H%M%S')}+03'00'"),
#             "/Size": len(xml_data),
#             "/CreationDate": pikepdf.String(f"D:{datetime.now().strftime('%Y%m%d%H%M%S')}+03'00'")
#         })

#         # Create file specification with both F and UF for Unicode support
#         xml_basename = os.path.basename(xml_file)
#         embedded_file_dict = pikepdf.Dictionary({
#             "/Type": "/Filespec",
#             "/F": pikepdf.String(xml_basename),
#             "/UF": pikepdf.String(xml_basename),  
#             "/EF": pikepdf.Dictionary({
#                 "/F": embedded_file_stream,
#                 "/UF": embedded_file_stream 
#             }),
#             "/Desc": pikepdf.String("ZATCA Invoice XML - UBL 2.1 Format"),
#             "/AFRelationship": "/Data"
#         })

#         # Create proper Names dictionary structure
#         if "/Names" not in pdf.Root:
#             pdf.Root.Names = pikepdf.Dictionary()
#         if "/EmbeddedFiles" not in pdf.Root.Names:
#             pdf.Root.Names.EmbeddedFiles = pikepdf.Dictionary()
#         if "/Names" not in pdf.Root.Names.EmbeddedFiles:
#             pdf.Root.Names.EmbeddedFiles.Names = pikepdf.Array()

#         # Add to Names array (name-tree structure)
#         pdf.Root.Names.EmbeddedFiles.Names.extend([
#             pikepdf.String(xml_basename),
#             embedded_file_dict
#         ])
        
#         # Create AF (Associated Files) array - Critical for PDF/A-3A
#         if "/AF" not in pdf.Root:
#             pdf.Root.AF = pikepdf.Array()
#         pdf.Root.AF.append(embedded_file_dict)

#         # -----------------------------
#         # 4. OutputIntent for Color Management
#         # -----------------------------
#         try:
#             with open(icc_path, "rb") as icc_file:
#                 icc_data = icc_file.read()
#                 output_intent_dict = pikepdf.Dictionary({
#                     "/Type": "/OutputIntent",
#                     "/S": "/GTS_PDFA1",
#                     "/OutputConditionIdentifier": "sRGB IEC61966-2.1",
#                     "/Info": "sRGB IEC61966-2.1",
#                     "/OutputCondition": "sRGB",
#                     "/DestOutputProfile": pdf.make_stream(icc_data),
#                 })
#                 if "/OutputIntents" not in pdf.Root:
#                     pdf.Root["/OutputIntents"] = pikepdf.Array([output_intent_dict])
#                 else:
#                     pdf.Root.OutputIntents.append(output_intent_dict)
#         except Exception as e:
#             frappe.log_error(f"Error adding ICC profile: {e}")
                
#         # -----------------------------
#         # 5. Document Info Dictionary (Legacy metadata)
#         # -----------------------------
#         pdf.docinfo["/Title"] = f"ZATCA Invoice - {invoice_name}"
#         pdf.docinfo["/Author"] = "ERPNext ZATCA Integration"
#         pdf.docinfo["/Subject"] = "Saudi ZATCA Compliant Electronic Invoice"
#         pdf.docinfo["/Creator"] = "ERPNext ZATCA PDF/A-3A Generator"
#         pdf.docinfo["/Producer"] = "ERPNext ZATCA with pikepdf"
#         pdf.docinfo["/Keywords"] = "ZATCA, Invoice, Saudi Arabia, PDF/A-3A, UBL, Electronic, Aramco"
#         pdf.docinfo["/CreationDate"] = pikepdf.String(f"D:{datetime.now().strftime('%Y%m%d%H%M%S')}+03'00'")
#         pdf.docinfo["/ModDate"] = pikepdf.String(f"D:{datetime.now().strftime('%Y%m%d%H%M%S')}+03'00'")
#         pdf.docinfo["/Trapped"] = "/False"

#         # -----------------------------
#         # 6. Save with PDF/A-3A compliance options (ZATCA SDK Standard)
#         # -----------------------------
#         try:
#             pdf.save(
#                 output_pdf, 
#                 compress_streams=False,  
#                 object_stream_mode=pikepdf.ObjectStreamMode.disable, 
#                 normalize_content=True,  
#                 linearize=False, 
#                 min_version="1.7"
#             )
#             print(f"✅ PDF/A-3A compliant file created successfully: {output_pdf}")
#         except Exception as e:
#             frappe.throw(_("Error saving PDF/A-3A file: {0}").format(str(e)))


# def generate_invoice_pdf(invoice, language, letterhead=None, print_format=None, public=False):
#     """
#     Generate a Sales Invoice PDF with the specified language, print format, and letterhead.

#     Args:
#         invoice (Document): Sales Invoice document object.
#         language (str): Language code (e.g., "en", "ar").
#         letterhead (str, optional): Letterhead name. Defaults to None.
#         print_format (str, optional): Print format name. Defaults to None.
#         public (bool, optional): Store file in public folder if True, else private. Defaults to False.

#     Returns:
#         str: Full file path of the generated PDF.
#     """
#     invoice_name = invoice.name

#     # Store original language to restore later
#     original_language = frappe.local.lang
#     frappe.local.lang = language

#     try:
#         # Generate HTML content for the invoice
#         html = frappe.get_print(
#             doctype="Sales Invoice",
#             name=invoice_name,
#             print_format=print_format,
#             no_letterhead=not bool(letterhead),
#             letterhead=letterhead
#         )
#     finally:
#         frappe.local.lang = original_language

#     # Convert HTML to PDF
#     pdf_content = get_pdf(html)

#     folder_type = "public" if public else "private"
#     site_path = frappe.local.site_path
#     files_dir = os.path.join(site_path, folder_type, "files")

#     os.makedirs(files_dir, exist_ok=True)

#     # Save PDF
#     file_name = f"{invoice_name}.pdf"
#     file_path = os.path.join(files_dir, file_name)

#     with open(file_path, "wb") as pdf_file:
#         pdf_file.write(pdf_content)

#     return file_path