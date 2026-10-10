"""
Eval-set synthesis: turn a project's indexed chunks into questions.

Two modes (E4.8):

* ``rag_eval`` — retrieval questions in the E3.8 golden-set format
  (``{q, expected_file, lang, expected_page?}`` plus ``answer`` and ``source_chunk_id``),
  so the ``make golden`` harness and E5.2 can consume them unchanged.
* ``behavior`` — ``{prompt, response, system?}`` rows shaped by an eval ``task``
  (``classify`` yes/no verification, ``extract`` JSON field objects, ``freeform``), usable as an
  adapter eval set (E4.3) or downloaded as JSONL. Classify/extract are preferred because
  token-F1 ``freeform`` sets are weak (E4.4). Extract field values are kept only when quoted
  verbatim from the chunk.

The generator is the project's local base model via ``services.chat`` by default; an optional
*teacher* is any OpenAI-compatible endpoint (``teacher_base_url``). No external key is needed.
Near-duplicate questions (embedding cosine above ``DEDUP_COSINE``) are dropped. The caller (API
layer) owns the DB record; chunk loading takes a session so it stays out of the generator.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import uuid
from pathlib import Path
from typing import Any, List, Optional, Tuple

from adapta.config import settings
from adapta.domain.errors import InternalError, InvalidRequest

logger = logging.getLogger(__name__)

DEDUP_COSINE = 0.92
MIN_CHUNK_CHARS = 80  # skip headings and fragments
_MAX_CHUNK_CHARS = 1500

_JSON_RULE = "Return ONLY a JSON array, no commentary and no markdown fences."

_RAG_SYSTEM = (
    "You write evaluation questions for a document search system. Given a passage, write "
    "questions a real user could ask whose answer is found in that passage. Each question "
    "must be self-contained: never say 'the passage' or 'the text', and name the subject. "
    "Write in the same language as the passage. "
    f'{_JSON_RULE} Each element is an object with keys "question" and "answer" (a short answer).'
)

_BEHAVIOR_SYSTEMS = {
    "extract": (
        "You write field-extraction exercises. Given a passage, write an instruction asking to "
        "extract 1-3 named fields, and the expected fields. Every field value must be a short span "
        "copied EXACTLY, character for character, from the passage (a number, name, date or short "
        "phrase). Use short snake_case field names. Write the instruction in the language of the "
        f'passage. {_JSON_RULE} Each element has keys "instruction" and "fields" (an object of '
        "field name to exact span)."
    ),
    "classify": (
        "You write true/false verification exercises. Given a passage, write statements about it: "
        'some that the passage supports (label "yes") and some that it contradicts or does not '
        'support (label "no"), mixing both. Write in the language of the passage. '
        f'{_JSON_RULE} Each element has keys "statement" and "label" (exactly "yes" or "no").'
    ),
    "freeform": (
        "You write question-answer exercises. Given a passage, write questions answerable from it, "
        "with answers that quote the passage's facts. Write in the language of the passage. "
        f'{_JSON_RULE} Each element has keys "question" and "answer".'
    ),
}

_USER_TEMPLATE = "Passage:\n---\n{chunk_text}\n---\n\nWrite {n} items.{style}"

_ES_WORDS = {"el", "la", "los", "las", "de", "del", "que", "y", "en", "un", "una", "por", "con", "para", "es", "se"}
_EN_WORDS = {"the", "of", "and", "to", "in", "is", "that", "for", "with", "are", "on", "as", "by"}


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def detect_lang(text: str) -> str:
    """Cheap en/es guess by stopword count (golden-set ``lang`` field)."""
    words = re.findall(r"[a-záéíóúñü]+", text.lower())
    es = sum(w in _ES_WORDS for w in words)
    en = sum(w in _EN_WORDS for w in words)
    return "es" if es > en else "en"


def _extract_items(raw: str) -> List[dict]:
    """Parse generator output into a list of dict items (tolerates fences and prose)."""
    clean = re.sub(r"```(?:json)?", "", raw).strip()
    match = re.search(r"\[.*\]", clean, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def _extract_pairs(raw: str) -> List[dict]:
    """Parse output into ``{question, answer}`` dicts, dropping incomplete items."""
    pairs = []
    for item in _extract_items(raw):
        q, a = item.get("question"), item.get("answer")
        if isinstance(q, str) and isinstance(a, str) and q.strip() and a.strip():
            pairs.append({"question": q.strip(), "answer": a.strip()})
    return pairs


def _norm_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def rag_eval_rows(raw: str, chunk: dict) -> List[Tuple[str, dict]]:
    """``(dedup_key, row)`` golden-format rows from one chunk's generator output."""
    lang = detect_lang(chunk["text"])
    out = []
    for pair in _extract_pairs(raw):
        row: dict = {
            "q": pair["question"],
            "expected_file": chunk["filename"],
            "lang": lang,
            "answer": pair["answer"],
            "source_chunk_id": chunk["id"],
        }
        if chunk.get("page") is not None:
            row["expected_page"] = chunk["page"]
        out.append((pair["question"], row))
    return out


def behavior_rows(
    raw: str, chunk: dict, task: str, system: Optional[str] = None
) -> List[Tuple[str, dict]]:
    """``(dedup_key, row)`` prompt/response rows for ``task``; rows that don't fit the
    task's shape (non-yes/no label, extract span not quoted from the chunk) are dropped."""
    text = chunk["text"][:_MAX_CHUNK_CHARS]
    out: List[Tuple[str, dict]] = []
    if task == "classify":
        for item in _extract_items(raw):
            st, label = item.get("statement"), item.get("label")
            if not (isinstance(st, str) and st.strip() and isinstance(label, str)):
                continue
            label = label.strip().lower()
            if label not in ("yes", "no"):
                continue
            prompt = (
                f"{text}\n\nBased on the text above, is this statement true? "
                f"{st.strip()}\nAnswer yes or no."
            )
            out.append((st.strip(), {"prompt": prompt, "response": label}))
    elif task == "extract":
        haystack = _norm_ws(text)
        for item in _extract_items(raw):
            ins, fields = item.get("instruction"), item.get("fields")
            if not (isinstance(ins, str) and ins.strip() and isinstance(fields, dict) and fields):
                continue
            values = list(fields.values())
            if not all(isinstance(v, (str, int, float)) and _norm_ws(str(v)) in haystack for v in values):
                continue  # a value not quoted from the chunk is an invented fact
            prompt = f"{text}\n\n{ins.strip()}\nRespond with a JSON object only."
            out.append((ins.strip(), {"prompt": prompt, "response": json.dumps(fields, ensure_ascii=False)}))
    else:
        for pair in _extract_pairs(raw):
            out.append(
                (pair["question"], {"prompt": f"{text}\n\n{pair['question']}", "response": pair["answer"]})
            )
    if system:
        for _, row in out:
            row["system"] = system
    return out


def dedup_exact(items: List[Tuple[str, dict]]) -> List[Tuple[str, dict]]:
    seen: set = set()
    kept = []
    for key, row in items:
        k = _norm_ws(key)
        if k not in seen:
            seen.add(k)
            kept.append((key, row))
    return kept


def near_duplicate_mask(vectors: List[List[float]], threshold: float = DEDUP_COSINE) -> List[bool]:
    """Greedy keep-mask: a vector is dropped when its cosine with an already-kept one
    exceeds ``threshold``. Earlier items win."""
    unit = []
    for v in vectors:
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        unit.append([x / n for x in v])
    keep: List[bool] = []
    kept_idx: List[int] = []
    for i, v in enumerate(unit):
        dup = any(sum(a * b for a, b in zip(v, unit[j], strict=True)) > threshold for j in kept_idx)
        keep.append(not dup)
        if not dup:
            kept_idx.append(i)
    return keep


def check_teacher_url(url: Optional[str]) -> Optional[str]:
    """A teacher endpoint must be an http(s) URL."""
    if url is None or url == "":
        return None
    if not re.match(r"^https?://\S+$", url):
        raise InvalidRequest(message="teacher_base_url must be an http(s) URL.")
    return url


# ---------------------------------------------------------------------------
# I/O: chunks, generator, writer
# ---------------------------------------------------------------------------


async def load_chunks(db: Any, project_id: str, max_chunks: int) -> List[dict]:
    """Up to ``max_chunks`` chunks (``id, text, page, filename``) sampled evenly across the
    project so one big file does not dominate. Raises InvalidRequest when none qualify."""
    from sqlalchemy import select

    from adapta.db.models import ProjectChunk, ProjectFile

    result = await db.execute(
        select(ProjectChunk.id, ProjectChunk.text, ProjectChunk.page, ProjectFile.filename)
        .join(ProjectFile, ProjectFile.id == ProjectChunk.file_id)
        .where(ProjectChunk.project_id == project_id)
        .order_by(ProjectFile.filename, ProjectChunk.chunk_index)
    )
    rows = [
        {"id": r[0], "text": r[1], "page": r[2], "filename": r[3]}
        for r in result.all()
        if r[1] and len(r[1].strip()) >= MIN_CHUNK_CHARS
    ]
    if not rows:
        raise InvalidRequest(message="No indexed chunks found for this project. Upload files first.")
    if len(rows) > max_chunks:
        stride = len(rows) / max_chunks
        rows = [rows[int(i * stride)] for i in range(max_chunks)]
    return rows


async def _generate(
    system: str,
    user: str,
    *,
    model: str,
    teacher_base_url: Optional[str],
    teacher_model: Optional[str],
) -> str:
    if teacher_base_url:
        import httpx

        url = teacher_base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": teacher_model or model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.7,
            "max_tokens": 768,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return str(resp.json()["choices"][0]["message"]["content"] or "")

    from adapta.services.chat import chat

    result = await chat(
        model_name=model,
        messages=[{"role": "user", "content": user}],
        system_prompt=system,
        temperature=0.7,
        max_tokens=768,
    )
    return str(result.get("choices", [{}])[0].get("message", {}).get("content", ""))


async def synthesize_from_chunks(
    project_id: str,
    chunks: List[dict],
    *,
    mode: str = "rag_eval",
    task: str = "extract",
    n_pairs_per_chunk: int = 3,
    system_prompt: Optional[str] = None,
    style_instructions: Optional[str] = None,
    base_model: Optional[str] = None,
    teacher_base_url: Optional[str] = None,
    teacher_model: Optional[str] = None,
) -> Tuple[Path, int]:
    """Generate, filter, dedup and write the JSONL. Returns ``(path, num_rows)``."""
    check_synthesis_args(mode, task, n_pairs_per_chunk, teacher_base_url)
    teacher_base_url = check_teacher_url(teacher_base_url)

    system = _RAG_SYSTEM if mode == "rag_eval" else _BEHAVIOR_SYSTEMS[task]
    style = ""
    if mode == "behavior" and style_instructions and style_instructions.strip():
        style = f"\nStyle for the answers: {style_instructions.strip()}"
    model = base_model or settings.default_model

    items: List[Tuple[str, dict]] = []
    errors = 0
    for i, chunk in enumerate(chunks):
        user = _USER_TEMPLATE.format(
            chunk_text=chunk["text"][:_MAX_CHUNK_CHARS], n=n_pairs_per_chunk, style=style
        )
        try:
            raw = await _generate(
                system, user, model=model, teacher_base_url=teacher_base_url, teacher_model=teacher_model
            )
        except Exception as exc:
            logger.warning("Synthesis failed for chunk %d: %s", i, exc)
            errors += 1
            continue
        if mode == "rag_eval":
            items.extend(rag_eval_rows(raw, chunk))
        else:
            items.extend(behavior_rows(raw, chunk, task, system_prompt))

    if not items:
        raise InternalError(
            message="Synthesis produced no valid rows. Check model availability.",
            internal_detail=f"Processed {len(chunks)} chunks, {errors} errors",
        )
    error_rate = errors / len(chunks) if chunks else 0.0
    if error_rate > settings.synthesis_max_error_rate:
        raise InternalError(
            message=(
                f"Synthesis failed on {error_rate*100:.0f}% of chunks "
                f"(max {settings.synthesis_max_error_rate*100:.0f}%) — the resulting dataset would "
                "be too sparse to trust. Check model availability and retry."
            ),
            internal_detail=f"{errors}/{len(chunks)} chunks failed, {len(items)} rows kept",
        )

    items = dedup_exact(items)
    from adapta.services.embeddings import get_embedding_service

    vectors = await asyncio.to_thread(
        get_embedding_service().embed, [key for key, _ in items], kind="query"
    )
    items = [it for it, keep in zip(items, near_duplicate_mask(vectors), strict=True) if keep]
    rows = [row for _, row in items]
    if mode == "behavior":
        rows = rows[: settings.eval_max_rows]

    out_dir = Path(settings.datasets_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"synthesis_{mode}_{project_id}_{uuid.uuid4().hex[:8]}.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    logger.info(
        "Synthesis complete: project=%s mode=%s chunks=%d rows=%d errors=%d",
        project_id, mode, len(chunks), len(rows), errors,
    )
    return path, len(rows)


def check_synthesis_args(
    mode: str, task: str, n_pairs_per_chunk: int, teacher_base_url: Optional[str]
) -> None:
    """Typed 400 on a bad mode/task/count/teacher URL — called by the endpoint before any work."""
    if mode not in ("rag_eval", "behavior"):
        raise InvalidRequest(message="mode must be 'rag_eval' or 'behavior'.")
    if mode == "behavior" and task not in _BEHAVIOR_SYSTEMS:
        raise InvalidRequest(message="task must be one of: classify, extract, freeform.")
    if not 1 <= n_pairs_per_chunk <= 10:
        raise InvalidRequest(message="n_pairs_per_chunk must be between 1 and 10")
    check_teacher_url(teacher_base_url)
