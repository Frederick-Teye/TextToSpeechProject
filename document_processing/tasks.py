import io
import os
import tempfile
import logging
import requests
import boto3

from tts_project.settings.celery import app
from django.conf import settings
from django.db import transaction

import pymupdf4llm
import pypandoc
from markdownify import markdownify

from .models import Document, DocumentPage, TextStatus, SourceType

logger = logging.getLogger(__name__)
MIN_CONTENT_LENGTH = 100


def _process_pdf(buf: io.BytesIO):
    logger.info("→ PDF: extracting pages via PyMuPDF4LLM")
    pages = pymupdf4llm.to_markdown(buf, page_chunks=True)
    return [
        {"page_number": p["page_number"], "markdown": p["markdown"].strip()}
        for p in pages
        if p.get("markdown", "").strip()
    ]


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
def parse_document_task(self, document_id):
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
            raw = doc.source_content.strip()
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
