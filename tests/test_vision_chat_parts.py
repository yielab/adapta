"""Image content-part handling in the chat service (§V4.2/§V4.3).

Pure-unit coverage of the validation seam: every malformed or out-of-cap image
input must become a typed 422 (InvalidRequest), never a 500 — schemathesis
fuzzes this surface hard. The actual multimodal generation is covered by the
opt-in GPU e2e (test_vlm_lora_e2e.py).
"""

from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from adapta.config import settings
from adapta.domain.errors import InvalidRequest
from adapta.services.chat import (
    _decode_data_url,
    _estimate_image_tokens,
    chat,
    flatten_text,
    has_image_parts,
    validate_image_parts,
)


def _png_data_url(width=64, height=64) -> str:
    img = Image.new("RGB", (width, height), (10, 20, 30))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _image_msg(url: str, text: str = "what is this?") -> dict:
    return {
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": url}},
            {"type": "text", "text": text},
        ],
    }


# ── flatten / detect ────────────────────────────────────────────────────────


def test_flatten_text_string_passthrough():
    assert flatten_text("hello") == "hello"


def test_flatten_text_parts_keeps_text_drops_images():
    content = [
        {"type": "text", "text": "extract the total"},
        {"type": "image_url", "image_url": {"url": "data:..."}},
        {"type": "text", "text": "as JSON"},
    ]
    assert flatten_text(content) == "extract the total as JSON"


def test_has_image_parts():
    assert has_image_parts([_image_msg(_png_data_url())]) is True
    assert has_image_parts([{"role": "user", "content": "plain"}]) is False
    assert has_image_parts([{"role": "user", "content": [{"type": "text", "text": "t"}]}]) is False


# ── data-URL decoding: every rejection is typed ─────────────────────────────


def test_remote_url_rejected():
    with pytest.raises(InvalidRequest, match="not fetched"):
        _decode_data_url("https://example.com/cat.png")


def test_non_base64_data_url_rejected():
    with pytest.raises(InvalidRequest):
        _decode_data_url("data:image/png,rawpayload")


def test_unsupported_media_type_rejected():
    with pytest.raises(InvalidRequest, match="Unsupported"):
        _decode_data_url("data:image/tiff;base64,AAAA")


def test_invalid_base64_rejected():
    with pytest.raises(InvalidRequest, match="base64"):
        _decode_data_url("data:image/png;base64,@@not-base64@@")


def test_oversize_image_rejected(monkeypatch):
    monkeypatch.setattr(settings, "max_image_mb", 0)
    with pytest.raises(InvalidRequest, match="limit"):
        _decode_data_url(_png_data_url())


# ── part validation: caps + decodability + token estimate ───────────────────


def test_validate_image_parts_returns_token_estimate():
    est = validate_image_parts([_image_msg(_png_data_url(224, 224))])
    # ceil(224/56)^2 + 8 = 16 + 8
    assert est == 24


def test_garbage_image_bytes_rejected():
    url = "data:image/png;base64," + base64.b64encode(b"not an image").decode()
    with pytest.raises(InvalidRequest, match="decoded"):
        validate_image_parts([_image_msg(url)])


def test_too_many_images_rejected(monkeypatch):
    monkeypatch.setattr(settings, "max_images_per_request", 2)
    url = _png_data_url()
    msgs = [_image_msg(url), _image_msg(url), _image_msg(url)]
    with pytest.raises(InvalidRequest, match="Too many images"):
        validate_image_parts(msgs)


def test_huge_dimensions_rejected(monkeypatch):
    monkeypatch.setattr(settings, "max_image_side_px", 32)
    with pytest.raises(InvalidRequest, match="px"):
        validate_image_parts([_image_msg(_png_data_url(64, 64))])


def test_estimate_scales_with_area():
    small = _estimate_image_tokens(224, 224)
    large = _estimate_image_tokens(1024, 1024)
    assert small < large
    assert large == (-(-1024 // 56)) ** 2 + 8


# ── modality gate: image on a text base is a typed 422, pre-model-load ──────


async def test_image_on_text_base_rejected():
    with pytest.raises(InvalidRequest, match="text-only"):
        await chat(
            model_name="qwen2.5-3b-instruct",  # catalog modality: text
            messages=[_image_msg(_png_data_url())],
        )
