"""E4.2 adapter import: static validation, storage, and the endpoint binding rule.

Offline: the service is exercised on the checked-in fixtures
(``tests/fixtures/adapters/classify-pass``: PEFT safetensors + the converted ``adapter.gguf``),
the endpoint handler against a scripted fake session.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from adapta.config import settings
from adapta.db.models import AdapterFormat, AdapterStatus
from adapta.domain.errors import InvalidAdapter, InvalidRequest, PayloadTooLarge
from adapta.services import adapters as svc

FIXTURE = Path(__file__).parent / "fixtures" / "adapters" / "classify-pass"
BASE = "qwen2.5-0.5b-instruct"


@pytest.fixture(autouse=True)
def _adapters_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "adapters_dir", tmp_path / "adapters")


def _zip(tmp_path: Path, members: dict[str, bytes], name: str = "a.zip") -> Path:
    p = tmp_path / name
    with zipfile.ZipFile(p, "w") as zf:
        for member, data in members.items():
            zf.writestr(member, data)
    return p


def _peft_members(**config_overrides) -> dict[str, bytes]:
    cfg = json.loads((FIXTURE / "adapter_config.json").read_text())
    cfg.update(config_overrides)
    return {
        "adapter_model.safetensors": (FIXTURE / "adapter_model.safetensors").read_bytes(),
        "adapter_config.json": json.dumps(cfg).encode(),
    }


def _store(upload: Path, filename: str | None = None, base: str = BASE):
    return svc.validate_and_store(upload, filename or upload.name, base, "ad-1")


def _rejects(upload: Path, needle: str, filename: str | None = None, base: str = BASE):
    with pytest.raises(InvalidAdapter) as exc:
        _store(upload, filename, base)
    assert needle in exc.value.message
    assert exc.value.status == 400 and exc.value.code == "invalid_adapter"
    assert not svc.adapter_dir("ad-1").exists()  # nothing left behind


# ── accepted ────────────────────────────────────────────────────────────────


def test_peft_zip_is_extracted_and_hashed(tmp_path):
    z = _zip(tmp_path, _peft_members())
    stored = _store(z)
    assert stored.format == AdapterFormat.peft
    assert stored.gguf_path is None
    assert sorted(p.name for p in stored.peft_dir.iterdir()) == [
        "adapter_config.json",
        "adapter_model.safetensors",
    ]
    assert not z.exists()  # the upload itself is not kept


def test_peft_sha256_is_of_the_uploaded_zip(tmp_path):
    z = _zip(tmp_path, _peft_members())
    digest, size = hashlib.sha256(z.read_bytes()).hexdigest(), z.stat().st_size
    stored = _store(z)
    assert (stored.sha256, stored.size_bytes) == (digest, size)


def test_peft_accepts_unsloth_mirror_base(tmp_path):
    z = _zip(tmp_path, _peft_members(base_model_name_or_path="unsloth/Qwen2.5-0.5B-Instruct"))
    assert _store(z).format == AdapterFormat.peft


def test_gguf_fixture_is_accepted(tmp_path):
    up = tmp_path / "lora.gguf"
    up.write_bytes((FIXTURE / "adapter.gguf").read_bytes())
    digest = hashlib.sha256(up.read_bytes()).hexdigest()
    stored = _store(up)
    assert stored.format == AdapterFormat.gguf
    assert stored.sha256 == digest
    assert stored.gguf_path == svc.adapter_dir("ad-1") / "adapter.gguf"
    assert stored.gguf_path.read_bytes()[:4] == b"GGUF"
    assert stored.peft_dir is None


# ── rejected: file type ─────────────────────────────────────────────────────


def test_unknown_extension_is_rejected(tmp_path):
    up = tmp_path / "adapter.bin"
    up.write_bytes(b"whatever")
    _rejects(up, ".gguf")


def test_gguf_extension_with_wrong_magic(tmp_path):
    up = tmp_path / "a.gguf"
    up.write_bytes(b"NOPE" + b"\0" * 100)
    _rejects(up, "GGUF")


def test_zip_extension_that_is_not_a_zip(tmp_path):
    up = tmp_path / "a.zip"
    up.write_bytes(b"GGUF" + b"\0" * 100)
    _rejects(up, "zip")


# ── rejected: GGUF content ──────────────────────────────────────────────────


def _write_gguf(path: Path, arch: str, general_type: str | None, adapter_type: str | None):
    from gguf import GGUFWriter

    w = GGUFWriter(str(path), arch)
    if general_type:
        w.add_string("general.type", general_type)
    if adapter_type:
        w.add_string("adapter.type", adapter_type)
    w.write_header_to_file()
    w.write_kv_data_to_file()
    w.write_ti_data_to_file()
    w.close()


def test_gguf_that_is_a_model_not_an_adapter(tmp_path):
    up = tmp_path / "model.gguf"
    _write_gguf(up, "qwen2", "model", None)
    _rejects(up, "general.type must be 'adapter'")


def test_gguf_adapter_that_is_not_lora(tmp_path):
    up = tmp_path / "a.gguf"
    _write_gguf(up, "qwen2", "adapter", "control_vector")
    _rejects(up, "adapter.type must be 'lora'")


def test_gguf_architecture_must_match_the_base(tmp_path):
    up = tmp_path / "a.gguf"
    up.write_bytes((FIXTURE / "adapter.gguf").read_bytes())  # qwen2 adapter
    _rejects(up, "'qwen2vl'", base="qwen2.5-vl-3b-instruct")


def test_truncated_gguf_is_rejected(tmp_path):
    up = tmp_path / "a.gguf"
    up.write_bytes((FIXTURE / "adapter.gguf").read_bytes()[:40])
    _rejects(up, "GGUF")


# ── rejected: PEFT zip content ──────────────────────────────────────────────


def test_zip_with_extra_member(tmp_path):
    members = _peft_members() | {"README.md": b"hi"}
    _rejects(_zip(tmp_path, members), "exactly adapter_model.safetensors")


def test_zip_missing_member(tmp_path):
    members = _peft_members()
    del members["adapter_config.json"]
    _rejects(_zip(tmp_path, members), "exactly adapter_model.safetensors")


def test_zip_with_directory_entries(tmp_path):
    members = {f"sub/{k}": v for k, v in _peft_members().items()}
    _rejects(_zip(tmp_path, members), "no directories")


def test_zip_path_traversal(tmp_path):
    members = {"../adapter_model.safetensors": b"x", "adapter_config.json": b"{}"}
    _rejects(_zip(tmp_path, members), "no directories")
    assert not (tmp_path / "adapter_model.safetensors").exists()


def test_zip_absolute_path(tmp_path):
    members = {"/etc/adapter_model.safetensors": b"x", "adapter_config.json": b"{}"}
    _rejects(_zip(tmp_path, members), "no directories")


def test_zip_duplicate_member(tmp_path):
    p = tmp_path / "dup.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("adapter_config.json", b"{}")
        with pytest.warns(UserWarning):
            zf.writestr("adapter_config.json", b"{}")
        zf.writestr("adapter_model.safetensors", b"x")
    _rejects(p, "exactly adapter_model.safetensors")


def test_zip_mismatched_base_model(tmp_path):
    z = _zip(tmp_path, _peft_members(base_model_name_or_path="meta-llama/Llama-3.2-1B"))
    with pytest.raises(InvalidAdapter) as exc:
        _store(z)
    assert "Qwen/Qwen2.5-0.5B-Instruct" in exc.value.message
    assert "meta-llama/Llama-3.2-1B" in exc.value.message


def test_zip_base_of_another_catalog_model(tmp_path):
    z = _zip(tmp_path, _peft_members())  # a 0.5B adapter...
    _rejects(z, "Qwen/Qwen2.5-1.5B-Instruct", base="qwen2.5-1.5b-instruct")  # ...on a 1.5B project


def test_zip_not_lora(tmp_path):
    z = _zip(tmp_path, _peft_members(peft_type="IA3"))
    _rejects(z, "peft_type must be 'LORA'")


def test_zip_config_not_json(tmp_path):
    members = _peft_members() | {"adapter_config.json": b"not json"}
    _rejects(_zip(tmp_path, members), "JSON object")


def test_zip_weights_not_safetensors(tmp_path):
    members = _peft_members() | {"adapter_model.safetensors": b"\xff" * 64}
    _rejects(_zip(tmp_path, members), "safetensors")


def test_corrupt_zip(tmp_path):
    z = _zip(tmp_path, _peft_members())
    z.write_bytes(z.read_bytes()[:-30])  # lop off the central directory
    with pytest.raises(InvalidAdapter):
        _store(z)
    assert not svc.adapter_dir("ad-1").exists()


# ── size ─────────────────────────────────────────────────────────────────────


def test_zip_that_expands_past_the_cap(tmp_path, monkeypatch):
    z = _zip(tmp_path, _peft_members())
    monkeypatch.setattr(settings, "adapter_max_upload_mb", 1)  # fixture weights are ~8 MB
    with pytest.raises(PayloadTooLarge) as exc:
        _store(z)
    assert exc.value.status == 413 and "1 MB" in exc.value.message
    assert not svc.adapter_dir("ad-1").exists()


def test_default_cap_is_512_mb():
    assert settings.adapter_max_upload_mb == 512


# ── base model not in the catalog ───────────────────────────────────────────


def test_project_base_not_in_catalog(tmp_path):
    z = _zip(tmp_path, _peft_members())
    _rejects(z, "not in the catalog", base="mystery-model")


# ── endpoint binding ─────────────────────────────────────────────────────────


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _Stop(Exception):
    """Raised by the fake commit: the Endpoint was built; nothing more to run."""


class _FakeDB:
    """Answers the handler's selects in order: project, existing endpoint, passed adapter."""

    def __init__(self, project, adapter):
        self._answers = [project, None, adapter]
        self.added = []

    async def execute(self, _stmt):
        return _Result(self._answers.pop(0))

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        raise _Stop


def _project():
    from adapta.db.models import ProjectType

    return SimpleNamespace(
        id="p-1234567890",
        team_id="t",
        name="Tickets",
        type=ProjectType.finetune,
        base_model=BASE,
        status=None,
    )


async def _create(db, monkeypatch):
    from adapta.api.v1 import endpoints

    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(endpoints, "require_team_writer", _noop)
    return await endpoints.create_endpoint("p-1234567890", SimpleNamespace(id="u"), db)


async def test_finetune_endpoint_refused_without_a_passed_adapter(monkeypatch):
    with pytest.raises(InvalidRequest) as exc:
        await _create(_FakeDB(_project(), None), monkeypatch)
    assert "passed" in exc.value.message


async def test_finetune_endpoint_binds_the_passed_adapter(monkeypatch):
    adapter = SimpleNamespace(id="ad-9", status=AdapterStatus.passed)
    db = _FakeDB(_project(), adapter)
    with pytest.raises(_Stop):
        await _create(db, monkeypatch)
    assert db.added[0].adapter_id == "ad-9"
