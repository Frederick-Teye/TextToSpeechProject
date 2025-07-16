import io, os, tempfile, logging, requests
from celery import shared_task
from django.conf import settings
import boto3
import pymupdf4llm
import pypandoc  # pip install pypandoc
from markdownify import markdownify  # pip install markdownify
from .models import Document, DocumentPage, TextStatus

logger = logging.getLogger(__name__)
MIN_CONTENT_LENGTH = 100

# -------------------------------------------------------------------
# PER-FORMAT PROCESSORS → return List[{"page_number": int, "markdown": str}]
# -------------------------------------------------------------------


def _process_pdf_bytes(buf: io.BytesIO):
    logger.info("Processing PDF via PyMuPDF4LLM.page_chunks")
    pages = pymupdf4llm.to_markdown(buf, page_chunks=True)
    return [
        {"page_number": p["page_number"], "markdown": p["markdown"].strip()}
        for p in pages
        if p.get("markdown", "").strip()
    ]


def _process_docx_bytes(buf: io.BytesIO):
    logger.info("Processing DOCX via Pandoc")
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp.write(buf.getvalue())
        tmp.flush()
        md = pypandoc.convert_file(tmp.name, "markdown", format="docx")
    os.unlink(tmp.name)
    return [{"page_number": 1, "markdown": md.strip()}]


def _process_md_bytes(buf: io.BytesIO):
    logger.info("Processing Markdown file directly")
    text = buf.read().decode("utf-8", errors="ignore")
    return [{"page_number": 1, "markdown": text.strip()}]


def _process_url(url: str):
    logger.info(f"Fetching URL → HTML → Markdown: {url}")
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    md_text = markdownify(resp.text, heading_style="ATX")
    return [{"page_number": 1, "markdown": md_text.strip()}]


# -------------------------------------------------------------------
# MAIN TASK: download → route → validate → save pages
# -------------------------------------------------------------------


@shared_task(bind=True)
def parse_document_task(self, document_id):
    logger.info(f"Start parsing Document #{document_id}")

    try:
        doc = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        logger.error("Document not found, aborting.")
        return

    doc.status = TextStatus.PROCESSING
    doc.save()

    try:
        src = doc.source_content

        # 1. URL content?
        if src.startswith(("http://", "https://")):
            pages = _process_url(src)

        # 2. S3 file content
        else:
            # Download raw bytes
            buf = io.BytesIO()
            s3 = boto3.client("s3", region_name=settings.AWS_S3_REGION_NAME)
            s3.download_fileobj(settings.AWS_STORAGE_BUCKET_NAME, src, buf)
            buf.seek(0)

            # Route by extension
            _, ext = os.path.splitext(src.lower())
            processors = {
                ".pdf": _process_pdf_bytes,
                ".docx": _process_docx_bytes,
                ".md": _process_md_bytes,
                ".markdown": _process_md_bytes,
            }
            processor = processors.get(ext)
            if not processor:
                raise NotImplementedError(f"No processor for '{ext}' files.")
            pages = processor(buf)

        # 3. Smart Check: total content length
        total_len = sum(len(p["markdown"]) for p in pages)
        if total_len < MIN_CONTENT_LENGTH:
            raise ValueError("No extractable text or empty document.")

        # 4. Persist each page
        objs = [
            DocumentPage(
                document=doc,
                page_number=p["page_number"],
                markdown_content=p["markdown"],
            )
            for p in pages
        ]
        DocumentPage.objects.bulk_create(objs)

        # 5. Mark success
        doc.status = TextStatus.COMPLETED
        doc.error_message = None
        logger.info(f"Saved {len(objs)} pages for Document #{document_id}")

    except NotImplementedError as e:
        logger.error(e, exc_info=True)
        doc.status = TextStatus.FAILED
        doc.error_message = str(e)

    except requests.RequestException as e:
        logger.error("URL fetch error", exc_info=True)
        doc.status = TextStatus.FAILED
        doc.error_message = "Failed to fetch URL."

    except ValueError as e:
        logger.error(e, exc_info=True)
        doc.status = TextStatus.FAILED
        doc.error_message = str(e)

    except Exception as e:
        logger.error("Processing error", exc_info=True)
        doc.status = TextStatus.FAILED
        doc.error_message = "Unsupported or corrupted content."

    finally:
        doc.save()
        logger.info(f"Finished Document #{document_id} with status {doc.status}")
