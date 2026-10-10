"""Visual extraction (E5.4): the vision base fills structured metadata and re-reads weak pages.

Opt-in per project: ``projects.extraction_schema`` (a small JSON-Schema object) turns it on, a
queued ``extract`` job runs it on a file's pages that ``needs_review`` (all pages on request).
Per page the vision model is called once for the schema fields and, only when the page's OCR
confidence was below the threshold, once more to transcribe it. The pure helpers here (schema
check, prompt, parser, header, page rendering) are unit-tested; :func:`extract_file` is the job.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from adapta.config import settings
from adapta.domain.errors import Conflict, InvalidRequest

logger = logging.getLogger(__name__)

EXTRACT_JOB_KIND = "extract"
MAX_SCHEMA_PROPERTIES = 20
_RENDERABLE = frozenset({".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"})
_SCALARS = (str, int, float, bool)


def validate_schema(schema: Any) -> Dict[str, Any]:
    """Check a project's extraction schema; return it. Shape::

        {"title": "Invoice", "properties": {"vendor": {"type": "string", "description": "..."}, ...}}

    ``title`` is optional (first word of the chunk header); property order is the header order.
    """
    props = schema.get("properties") if isinstance(schema, dict) else None
    if not isinstance(props, dict) or not props:
        raise InvalidRequest(message="extraction_schema needs a non-empty 'properties' object.")
    if len(props) > MAX_SCHEMA_PROPERTIES:
        raise InvalidRequest(
            message=f"extraction_schema allows at most {MAX_SCHEMA_PROPERTIES} properties."
        )
    for key, spec in props.items():
        if not isinstance(key, str) or not key.strip() or not isinstance(spec, dict):
            raise InvalidRequest(message="Each extraction_schema property must be an object.")
    title = schema.get("title")
    if title is not None and not isinstance(title, str):
        raise InvalidRequest(message="extraction_schema 'title' must be a string.")
    return dict(schema)


def fields_prompt(schema: Dict[str, Any]) -> str:
    """The user text sent with the page image for the structured read."""
    return (
        "Read this document page and extract the fields below. "
        "Return JSON only: one object with exactly these keys; use null for a field that is "
        "not on the page. Copy values exactly as printed.\n"
        f"{json.dumps({'properties': schema['properties']}, ensure_ascii=False)}"
    )


TRANSCRIBE_PROMPT = (
    "Transcribe all text on this document page exactly as printed, in reading order. "
    "Return the plain text only, with no commentary."
)


# A model that is told "use null" sometimes writes the word instead of the JSON literal (F1.1).
_ABSENT = frozenset({"null", "none"})


def parse_fields(raw: str, schema: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Parse the model's reply to ``{key: scalar}`` over the schema's keys.

    Tolerates code fences and prose around the object. Unknown keys, nulls (including the strings
    "null"/"none"), empty strings and nested values are dropped. Returns None when no JSON object is found or no field survives.
    """
    clean = re.sub(r"```(?:json)?", "", raw or "").strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    out: Dict[str, Any] = {}
    for key in schema["properties"]:
        value = data.get(key)
        if isinstance(value, str):
            value = " ".join(value.split())
        if isinstance(value, str) and value.lower() in _ABSENT:
            continue
        if isinstance(value, _SCALARS) and value != "":
            out[key] = value
    return out or None


def fields_header(fields: Optional[Dict[str, Any]], schema: Optional[Dict[str, Any]]) -> str:
    """One-line chunk header, e.g. ``Invoice · Acme SA · 2026-03-01 · 1,250.00`` ("" if none).

    Values follow the schema's property order; ``title`` leads when set.
    """
    if not fields:
        return ""
    keys = list(schema["properties"]) if schema else list(fields)
    parts = [str(fields[k]) for k in keys if k in fields]
    if not parts:
        return ""
    title = schema.get("title") if schema else None
    return " · ".join(([title] if title else []) + parts)


def render_page(path: Path, page: int) -> bytes:
    """PNG bytes of page ``page`` (1-based) of a PDF or image file, longest side capped."""
    from PIL import Image

    ext = path.suffix.lower()
    if ext not in _RENDERABLE:
        raise InvalidRequest(message="Visual extraction supports PDF and image files only.")
    side = settings.extract_image_side_px
    if ext == ".pdf":
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(path))
        try:
            if not 1 <= page <= len(pdf):
                raise InvalidRequest(message=f"Page {page} is outside the document.")
            pdf_page = pdf[page - 1]
            width, height = pdf_page.get_size()
            scale = min(3.0, side / max(width, height))
            img = pdf_page.render(scale=scale).to_pil().convert("RGB")
        finally:
            pdf.close()
    else:
        img = Image.open(path)
        if getattr(img, "n_frames", 1) >= page:
            img.seek(page - 1)
        img = img.convert("RGB")
    if max(img.size) > side:
        img.thumbnail((side, side))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def _ask(png: bytes, text: str, *, model: str) -> str:
    """One vision completion through the serving path (``_chat_vision``), greedy."""
    from adapta.services.chat import _chat_vision, validate_image_parts

    url = "data:image/png;base64," + base64.b64encode(png).decode()
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": url}},
                {"type": "text", "text": text},
            ],
        }
    ]
    result = await _chat_vision(
        model_name=model,
        messages=messages,
        image_tokens=validate_image_parts(messages),
        temperature=0.0,
        max_tokens=settings.extract_max_tokens,
        top_p=1.0,
        adapter_path=None,
    )
    return result["choices"][0]["message"]["content"] or ""


def select_pages(rows: Sequence[Any], *, all_pages: bool) -> List[int]:
    """Distinct pages to process, ascending: flagged ones, or every page with ``all_pages``."""
    return sorted(
        {r.page for r in rows if r.page is not None and (all_pages or r.needs_review)}
    )


def check_extractable(filename: str, status: str, schema: Optional[dict]) -> None:
    """Request-time guards for ``POST .../extract`` (typed 409/422)."""
    if schema is None:
        raise InvalidRequest(
            message="Set the project's extraction_schema first (PATCH /v1/projects/{id})."
        )
    if Path(filename).suffix.lower() not in _RENDERABLE:
        raise InvalidRequest(message="Visual extraction supports PDF and image files only.")
    if status != "indexed":
        raise Conflict(message="The file must be indexed before fields can be extracted.")


async def extract_file(file_id: str, *, all_pages: bool = False) -> dict:
    """The ``extract`` job body. Returns ``{"pages": n, "reread": n, "seconds": {...}}``.

    Per selected page: structured read → ``chunks.fields`` on every chunk of the page; if the
    page was flagged and the transcription is non-empty, its chunks are replaced by the
    re-chunked transcription (re-embedded, ``needs_review`` cleared). A page whose model call
    fails is skipped; one that exceeds ``extract_page_timeout_seconds`` raises a typed ``Timeout`` (F1.1) and logged; if every page fails the job raises so it ends ``failed``.
    """
    import asyncio

    from sqlalchemy import delete, select, update

    from adapta.db.models import Collection, Project, ProjectChunk, ProjectFile
    from adapta.db.session import AsyncSessionLocal
    from adapta.domain.errors import InferenceFailed, NotFound, Timeout
    from adapta.services.documents import Chunk, chunk_text
    from adapta.services.rag import build_chunk_rows, get_rag_service

    async with AsyncSessionLocal() as db:
        pfile = (
            await db.execute(select(ProjectFile).where(ProjectFile.id == file_id))
        ).scalar_one_or_none()
        if pfile is None:
            raise NotFound(message="File not found")
        project = (
            await db.execute(select(Project).where(Project.id == pfile.project_id))
        ).scalar_one()
        schema = validate_schema(project.extraction_schema)
        rows = (
            await db.execute(
                select(ProjectChunk.page, ProjectChunk.needs_review).where(
                    ProjectChunk.file_id == file_id
                )
            )
        ).all()
        path, project_id, filename = Path(pfile.storage_path), pfile.project_id, pfile.filename
    pages = select_pages(rows, all_pages=all_pages)
    if len(pages) > settings.extract_max_pages:
        raise InvalidRequest(
            message=f"{len(pages)} pages exceed the {settings.extract_max_pages}-page limit per job."
        )
    flagged = {r.page for r in rows if r.needs_review}
    model = settings.extract_model

    done = reread = 0
    seconds: Dict[int, float] = {}
    for page in pages:
        t0 = time.perf_counter()
        try:
            png = await asyncio.to_thread(render_page, path, page)

            async def read_page(png: bytes, page: int) -> tuple:
                got = parse_fields(await _ask(png, fields_prompt(schema), model=model), schema)
                said = ""
                if page in flagged:
                    said = " ".join((await _ask(png, TRANSCRIBE_PROMPT, model=model)).split())
                return got, said

            fields, text = await asyncio.wait_for(read_page(png, page), timeout=settings.extract_page_timeout_seconds)
        except asyncio.TimeoutError as exc:  # a hung model call: end the job so the serial worker moves on (F1.1)
            budget = settings.extract_page_timeout_seconds
            raise Timeout(
                message=(
                    f"Visual extraction timed out after {budget} s on page {page} - the vision model "
                    "stopped answering. Check the stack with GET /health/deep, then extract again."
                ),
                internal_detail=f"extract deadline {budget}s, file {file_id}, page {page}",
            ) from exc
        except Exception as exc:  # noqa: BLE001 — per page; counted below
            logger.warning("extract: page %d of %s failed: %r", page, file_id, exc)
            continue
        seconds[page] = round(time.perf_counter() - t0, 1)
        async with AsyncSessionLocal() as db:
            old = (
                await db.execute(
                    select(ProjectChunk)
                    .where(ProjectChunk.file_id == file_id, ProjectChunk.page == page)
                    .order_by(ProjectChunk.chunk_index)
                )
            ).scalars().all()
            if not old:
                continue
            if text:
                pieces = chunk_text(text, filename)
                ids_old = [c.id for c in old]
                max_idx = (
                    await db.scalar(
                        select(ProjectChunk.chunk_index)
                        .where(ProjectChunk.file_id == file_id)
                        .order_by(ProjectChunk.chunk_index.desc())
                        .limit(1)
                    )
                ) or 0
                indexes = [
                    old[k].chunk_index if k < len(old) else max_idx + 1 + (k - len(old))
                    for k in range(len(pieces))
                ]
                new_chunks = [
                    Chunk(
                        text=p.text, source=filename, index=idx, page=page,
                        section=old[0].section, ocr=True, ocr_confidence=None,
                    )
                    for p, idx in zip(pieces, indexes, strict=True)
                ]
                await db.execute(delete(ProjectChunk).where(ProjectChunk.id.in_(ids_old)))
                await db.flush()
                new_rows = build_chunk_rows(project_id, file_id, new_chunks)
                for r in new_rows:
                    r.fields = fields
                db.add_all(new_rows)
                delta = len(new_rows) - len(old)
                rag = get_rag_service()
                await asyncio.to_thread(rag.index_chunks, project_id, file_id, new_chunks)
                surplus = [i for i in ids_old if i not in {r.id for r in new_rows}]
                if surplus:
                    await asyncio.to_thread(rag.delete_chunk_ids, project_id, surplus)
                if delta:
                    await db.execute(
                        update(ProjectFile).where(ProjectFile.id == file_id)
                        .values(num_chunks=ProjectFile.num_chunks + delta)
                    )
                    await db.execute(
                        update(Collection).where(Collection.project_id == project_id)
                        .values(num_chunks=Collection.num_chunks + delta)
                    )
                reread += 1
            elif fields:
                await db.execute(
                    update(ProjectChunk)
                    .where(ProjectChunk.file_id == file_id, ProjectChunk.page == page)
                    .values(fields=fields)
                )
            await db.commit()
        done += 1
    if pages and done == 0:
        raise InferenceFailed(
            message="Visual extraction failed on every page. Check that the vision model is available.",
            internal_detail=f"extract {file_id}: 0/{len(pages)} pages (model={model!r})",
        )
    logger.info("extract %s: %d/%d pages, %d re-read, seconds=%s", file_id, done, len(pages), reread, seconds)
    return {"pages": done, "reread": reread, "seconds": seconds}


def fields_csv(rows: Sequence[Any], schema: Dict[str, Any]) -> str:
    """CSV of extracted fields: ``file, page`` then one column per schema property.

    ``rows`` carry ``filename``, ``page`` and ``fields``. Cells starting with ``= + - @`` are
    prefixed with ``'`` so a spreadsheet never evaluates document text as a formula.
    """
    import csv

    def cell(v: Any) -> Any:
        return "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@") else v

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    keys = list(schema["properties"])
    writer.writerow(["file", "page", *keys])
    for r in rows:
        writer.writerow([cell(r.filename), r.page, *(cell((r.fields or {}).get(k, "")) for k in keys)])
    return buf.getvalue()
