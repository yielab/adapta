"""
Dataset synthesis: turn document chunks already indexed in ChromaDB
into instruction/response pairs that can be used for fine-tuning.

Flow:
  1. Retrieve all chunks for a project from Chroma (paginated).
  2. For each chunk batch, call the local inference engine with a
     generation prompt that asks it to produce N question/answer pairs.
  3. Parse, validate, and deduplicate the pairs.
  4. Write to a JSONL file in datasets_dir.
  5. Return the path + count so the caller can create a Dataset record.

The generation prompt is intentionally simple — no LangChain, no special
framework.  The caller (API layer) owns the DB record creation.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path
from typing import List, Optional, Tuple

from brain.domain.errors import InternalError, InvalidRequest

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are an expert at creating training data for language models. "
    "Given a passage of text, generate question-answer pairs that test "
    "comprehension of the passage. "
    "Return ONLY a JSON array where each element is an object with keys "
    '"question" and "answer". No extra commentary, no markdown fences, just the JSON array.'
)

_USER_TEMPLATE = (
    "Passage:\n"
    "---\n"
    "{chunk_text}\n"
    "---\n\n"
    "Generate {n_pairs} question-answer pairs based solely on the passage above."
)

# ---------------------------------------------------------------------------
# Pair extraction helpers
# ---------------------------------------------------------------------------


def _extract_pairs(raw: str) -> List[dict]:
    """Parse LLM output into a list of {question, answer} dicts."""
    # Strip markdown fences if the model ignored the instruction
    clean = re.sub(r"```(?:json)?", "", raw).strip()
    # Find the first [...] block
    match = re.search(r"\[.*\]", clean, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    pairs = []
    for item in data:
        if not isinstance(item, dict):
            continue
        q = item.get("question", "").strip()
        a = item.get("answer", "").strip()
        if q and a:
            pairs.append({"question": q, "answer": a})
    return pairs


def _to_instruction_pair(pair: dict, system: Optional[str] = None) -> dict:
    """Convert a {question, answer} pair to the training dataset schema."""
    record: dict = {"prompt": pair["question"], "response": pair["answer"]}
    if system:
        record["system"] = system
    return record


# ---------------------------------------------------------------------------
# Core synthesis function
# ---------------------------------------------------------------------------


async def synthesize_from_project(
    project_id: str,
    n_pairs_per_chunk: int = 3,
    max_chunks: int = 50,
    system_prompt: Optional[str] = None,
    base_model: Optional[str] = None,
) -> Tuple[Path, int]:
    """
    Synthesize a JSONL instruction dataset from a project's indexed chunks.

    Returns (output_path, num_samples).
    Raises InvalidRequest if the project has no indexed chunks.
    Raises InternalError on generation failures after exhausting chunks.
    """
    if n_pairs_per_chunk < 1 or n_pairs_per_chunk > 10:
        raise InvalidRequest(message="n_pairs_per_chunk must be between 1 and 10")
    if max_chunks < 1 or max_chunks > 500:
        raise InvalidRequest(message="max_chunks must be between 1 and 500")

    # Pull chunks from ChromaDB
    from brain.config import settings
    from brain.services.rag import _get_chroma_client, collection_name_for

    coll_name = collection_name_for(project_id)
    try:
        chroma = _get_chroma_client()
        chroma_collection = chroma.get_collection(coll_name)
        result = chroma_collection.get(limit=max_chunks, include=["documents"])
    except Exception as exc:
        raise InvalidRequest(
            message="Project has no indexed collection. Upload and index files first.",
            internal_detail=str(exc),
        ) from exc

    documents: List[str] = result.get("documents") or []
    if not documents:
        raise InvalidRequest(
            message="No indexed chunks found for this project. Upload files first."
        )

    # Generate pairs per chunk using the chat service (avoids direct inference engine coupling)
    from brain.services.chat import chat

    model = base_model or settings.default_model
    all_pairs: List[dict] = []
    seen_questions: set = set()
    errors = 0

    for i, chunk_text in enumerate(documents):
        if not chunk_text or not chunk_text.strip():
            continue
        user_msg = _USER_TEMPLATE.format(chunk_text=chunk_text[:1500], n_pairs=n_pairs_per_chunk)
        try:
            chat_result = await chat(
                model_name=model,
                messages=[{"role": "user", "content": user_msg}],
                system_prompt=_SYSTEM_PROMPT,
                temperature=0.7,
                max_tokens=512,
            )
            raw = chat_result.get("choices", [{}])[0].get("message", {}).get("content", "")
            pairs = _extract_pairs(raw)
            for pair in pairs:
                q_norm = pair["question"].lower().strip()
                if q_norm not in seen_questions:
                    seen_questions.add(q_norm)
                    all_pairs.append(_to_instruction_pair(pair, system=system_prompt))
        except Exception as exc:
            logger.warning("Synthesis failed for chunk %d: %s", i, exc)
            errors += 1
            continue

    if not all_pairs:
        raise InternalError(
            message="Synthesis produced no valid pairs. Check model availability.",
            internal_detail=f"Processed {len(documents)} chunks, {errors} errors",
        )

    # Guard against silently shipping a degraded dataset: if too large a fraction of
    # chunks failed (e.g. the LLM was flaky/down), fail loudly rather than returning
    # a partial dataset that looks complete (A4.12).
    from brain.config import settings as _settings

    error_rate = errors / len(documents) if documents else 0.0
    if error_rate > _settings.synthesis_max_error_rate:
        raise InternalError(
            message=(
                f"Synthesis failed on {error_rate*100:.0f}% of chunks "
                f"(max {_settings.synthesis_max_error_rate*100:.0f}%) — the resulting dataset would "
                "be too sparse to trust. Check model availability and retry."
            ),
            internal_detail=f"{errors}/{len(documents)} chunks failed, {len(all_pairs)} pairs kept",
        )

    # Write JSONL
    from brain.config import settings

    datasets_dir = Path(settings.datasets_dir)
    datasets_dir.mkdir(parents=True, exist_ok=True)
    output_path = datasets_dir / f"synthesis_{project_id}_{uuid.uuid4().hex[:8]}.jsonl"
    with output_path.open("w", encoding="utf-8") as fh:
        for record in all_pairs:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    logger.info(
        "Synthesis complete: project=%s chunks=%d pairs=%d errors=%d path=%s",
        project_id,
        len(documents),
        len(all_pairs),
        errors,
        output_path,
    )
    return output_path, len(all_pairs)
