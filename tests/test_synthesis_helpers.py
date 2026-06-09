"""
Unit tests for the pure synthesis helpers (brain/services/synthesis.py):
parsing LLM output into Q/A pairs and converting them to the training-dataset
schema. The async synthesize_from_project flow (needs Chroma + inference) is left
to integration tests.
"""

from brain.services.synthesis import _extract_pairs, _to_instruction_pair


def test_extract_pairs_plain_json_array():
    raw = '[{"question": "What is RAG?", "answer": "Retrieval-augmented generation."}]'
    pairs = _extract_pairs(raw)
    assert pairs == [{"question": "What is RAG?", "answer": "Retrieval-augmented generation."}]


def test_extract_pairs_strips_markdown_fences():
    raw = '```json\n[{"question": "Q1", "answer": "A1"}]\n```'
    assert _extract_pairs(raw) == [{"question": "Q1", "answer": "A1"}]


def test_extract_pairs_finds_array_amid_prose():
    raw = 'Sure! Here are the pairs:\n[{"question": "Q", "answer": "A"}]\nHope that helps.'
    assert _extract_pairs(raw) == [{"question": "Q", "answer": "A"}]


def test_extract_pairs_skips_incomplete_and_nondict_items():
    raw = '[{"question": "Q", "answer": ""}, "junk", {"question": "", "answer": "A"}, {"question": "Good", "answer": "Yes"}]'
    assert _extract_pairs(raw) == [{"question": "Good", "answer": "Yes"}]


def test_extract_pairs_returns_empty_on_no_array():
    assert _extract_pairs("no json here at all") == []


def test_extract_pairs_returns_empty_on_invalid_json():
    assert _extract_pairs("[{not: valid json}]") == []


def test_to_instruction_pair_maps_to_schema():
    rec = _to_instruction_pair({"question": "Q", "answer": "A"})
    assert rec == {"prompt": "Q", "response": "A"}


def test_to_instruction_pair_includes_system_when_given():
    rec = _to_instruction_pair({"question": "Q", "answer": "A"}, system="You are terse.")
    assert rec == {"prompt": "Q", "response": "A", "system": "You are terse."}
