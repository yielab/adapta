"""JSON mode (E4.9): the request model accepts response_format and the llama-cpp
backend compiles it into a grammar. Live decoding is in test_inference_slow.py."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from adapta.core.backends.llamacpp import grammar_for
from adapta.models.generated import ChatCompletionRequest

_MSG = [{"role": "user", "content": "hi"}]


@pytest.mark.parametrize(
    "rf",
    [
        {"type": "text"},
        {"type": "json_object"},
        {"type": "json_schema", "json_schema": {"name": "x", "schema": {"type": "object"}}},
    ],
)
def test_request_accepts_response_format(rf):
    body = ChatCompletionRequest(model="m", messages=_MSG, response_format=rf)
    assert body.response_format.type == rf["type"]


def test_request_rejects_unknown_response_format():
    with pytest.raises(ValidationError):
        ChatCompletionRequest(model="m", messages=_MSG, response_format={"type": "xml"})


def test_response_format_is_optional():
    assert ChatCompletionRequest(model="m", messages=_MSG).response_format is None


def test_grammar_for_unconstrained_is_none():
    assert grammar_for(None) is None
    assert grammar_for({"type": "text"}) is None
