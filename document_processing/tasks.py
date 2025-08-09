import io
import os
import json
import subprocess
import tempfile
import logging
import requests
import boto3
import fitz  # PyMuPDF

from tts_project.settings.celery import app
from django.conf import settings
from django.db import transaction
from pymupdf4llm import to_markdown

# import pdfplumber
import pypandoc
from markdownify import markdownify

from .models import Document, DocumentPage, TextStatus, SourceType

logger = logging.getLogger(__name__)
MIN_CONTENT_LENGTH = 100


def _process_pdf(buf: io.BytesIO) -> list[dict]:
    """
    Uses PyMuPDF and pymupdf4llm to convert each PDF page into Markdown.
    Returns a list of dicts: [{"page_number": n, "markdown": "..."}].
    """
    # Dump incoming BytesIO to a temp file
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(buf.getvalue())
        tmp.flush()
        pdf_path = tmp.name

    try:
        # Open the PDF file using PyMuPDF
        logger.info("→ PDF→MD: Processing with PyMuPDF4LLM")
        doc = fitz.open(pdf_path)

        pages = []
        for page_index in range(len(doc)):
            # Convert single page to markdown
            markdown_text = to_markdown(doc, pages=[page_index])
            clean_md = markdown_text.strip()

            if clean_md:
                pages.append(
                    {
                        "page_number": page_index + 1,  # 1-indexed page numbers
                        "markdown": clean_md,
                    }
                )

        logger.info(f"Converted {len(pages)}/{len(doc)} pages with content")
        return pages

    except Exception as e:
        logger.exception("PyMuPDF4LLM processing error")
        raise RuntimeError(f"PDF processing failed: {str(e)}")

    finally:
        # Clean up temp file
        try:
            os.unlink(pdf_path)
        except OSError:
            logger.warning("Could not delete temp file: %s", pdf_path)


def _process_docx(buf: io.BytesIO):
    logger.info("→ DOCX: converting via Pandoc")
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp.write(buf.getvalue())
        tmp.flush()
        md = pypandoc.convert_file(tmp.name, "markdown", format="docx")
    os.unlink(tmp.name)
    return [{"page_number": 1, "markdown": md.strip()}]


def _process_md(buf: io.BytesIO):
    logger.info("→ MD: reading raw Markdown")
    text = buf.read().decode("utf-8", errors="ignore")
    return [{"page_number": 1, "markdown": text.strip()}]


def _process_url(url: str):
    logger.info(f"→ URL: fetching and markdownifying {url}")
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    md = markdownify(resp.text, heading_style="ATX")
    return [{"page_number": 1, "markdown": md.strip()}]


# @ shared_task(bind=True)
@app.task(bind=True)
def parse_document_task(self, document_id, raw_text=""):
    logger.info(f"[{self.request.id}] Start processing Document {document_id}")
    try:
        doc = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        logger.error("Document not found, aborting.")
        return

    doc.status = TextStatus.PROCESSING
    doc.save()

    try:
        # 1) Branch on source_type
        stype = doc.source_type

        if stype == SourceType.URL:
            pages = _process_url(doc.source_content)

        elif stype == SourceType.TEXT:
            # Raw text is already Markdown-ish
            raw = raw_text.strip()
            pages = [{"page_number": 1, "markdown": raw}]

        else:  # FILE
            # Download from S3
            buf = io.BytesIO()
            s3 = boto3.client("s3", region_name=settings.AWS_S3_REGION_NAME)
            s3.download_fileobj(
                settings.AWS_STORAGE_BUCKET_NAME, doc.source_content, buf
            )
            buf.seek(0)

            # Dispatch by extension
            _, ext = os.path.splitext(doc.source_content.lower())
            processors = {
                ".pdf": _process_pdf,
                ".docx": _process_docx,
                ".md": _process_md,
                ".markdown": _process_md,
            }
            proc = processors.get(ext)
            if not proc:
                raise NotImplementedError(f"No processor for '{ext}' files")
            pages = proc(buf)

        # 2) Smart check
        total_len = sum(len(p["markdown"]) for p in pages)
        if total_len < MIN_CONTENT_LENGTH:
            raise ValueError("No readable text found")

        # 3) Bulk save each page
        objs = [
            DocumentPage(
                document=doc,
                page_number=p["page_number"],
                markdown_content=p["markdown"],
            )
            for p in pages
        ]
        DocumentPage.objects.bulk_create(objs)

        # 4) Mark success
        doc.status = TextStatus.COMPLETED
        doc.error_message = None

    except NotImplementedError as e:
        logger.error(e, exc_info=True)
        doc.status = TextStatus.FAILED
        doc.error_message = str(e)

    except requests.RequestException as e:
        logger.error("URL fetch error", exc_info=True)
        doc.status = TextStatus.FAILED
        doc.error_message = "Failed to fetch URL content"

    except ValueError as e:
        logger.error(e, exc_info=True)
        doc.status = TextStatus.FAILED
        doc.error_message = "Processing failed: no readable text"

    except Exception as e:
        logger.exception("Unexpected processing error")
        doc.status = TextStatus.FAILED
        doc.error_message = "Processing failed: unsupported or corrupted content"

    finally:
        doc.save()
        logger.info(f"Finished Document {document_id} with status {doc.status}")
