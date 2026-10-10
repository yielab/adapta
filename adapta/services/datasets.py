"""SFT dataset-row validation.

A dataset is a ``.jsonl`` file with one SFT row per line (``prompt`` + ``response``,
optional ``system`` / ``metadata``), checked against
``specs/schemas/eval_dataset.schema.json``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

DATASET_SCHEMA_PATH = Path("specs/schemas/eval_dataset.schema.json")

# How many row problems to list before truncating the report. A large file with a
# systemic mistake could otherwise produce a multi-megabyte error string; the
# operator only needs a representative batch to fix the pattern.
MAX_REPORTED_ERRORS = 25


def _load_schema() -> Optional[dict]:
    if DATASET_SCHEMA_PATH.exists():
        return json.loads(DATASET_SCHEMA_PATH.read_text())  # type: ignore[no-any-return]
    return None


def _validate_row(i: int, obj: object, schema: Optional[dict]) -> list[str]:
    """Validate one parsed row; return every problem found on it (not just the first)."""
    if not isinstance(obj, dict):
        return [f"Line {i}: row must be a JSON object"]

    errors: list[str] = []
    if not isinstance(obj.get("prompt"), str) or not obj["prompt"].strip():
        errors.append(f"Line {i}: missing or empty 'prompt' field")
    if not isinstance(obj.get("response"), str) or not obj["response"].strip():
        errors.append(f"Line {i}: missing or empty 'response' field")

    if schema:
        import jsonschema

        try:
            jsonschema.validate(obj, schema)
        except jsonschema.ValidationError as e:
            errors.append(f"Line {i}: schema violation — {e.message}")
    return errors


def _format_error_report(errors: list[str]) -> str:
    """Build one operator-facing message from collected per-row problems."""
    shown = errors[:MAX_REPORTED_ERRORS]
    body = "\n".join(f"  • {e}" for e in shown)
    header = f"Found {len(errors)} problem(s) in the dataset:"
    if len(errors) > MAX_REPORTED_ERRORS:
        body += f"\n  … and {len(errors) - MAX_REPORTED_ERRORS} more"
    return f"{header}\n{body}\nFix these and re-upload."


def validate_dataset(path: Path) -> tuple[bool, Optional[str], int]:
    """Validate a JSONL file of SFT rows.

    Returns (is_valid, error_message, num_samples).

    Validation does **not** stop at the first bad row: it scans the file and reports
    up to :data:`MAX_REPORTED_ERRORS` problems at once, so an operator sees every
    issue in one pass instead of discovering them one re-upload at a time.
    """
    try:
        schema = _load_schema()
        num_samples = 0
        errors: list[str] = []
        with path.open(encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as exc:
                    errors.append(f"Line {i}: invalid JSON — {exc}")
                    if len(errors) >= MAX_REPORTED_ERRORS:
                        break
                    continue

                row_errors = _validate_row(i, obj, schema)
                if row_errors:
                    errors.extend(row_errors)
                    if len(errors) >= MAX_REPORTED_ERRORS:
                        break
                    continue
                num_samples += 1

        if errors:
            return False, _format_error_report(errors), 0
        if num_samples == 0:
            return False, "Dataset is empty — must have at least one row", 0
        return True, None, num_samples

    except Exception as exc:
        return False, str(exc), 0
