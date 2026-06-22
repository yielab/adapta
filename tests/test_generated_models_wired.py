"""Guard: the API routers MUST consume the generated contract models.

Pillar 1 of the Extended SDD is only real if the spec actually drives the code.
For a long time the Pydantic models generated from ``specs/openapi.yaml`` were
committed and kept in sync by ``make check-models`` — but nothing imported them:
every router hand-wrote its own request/response models in parallel, so the
"contract" was decorative. These tests fail if that regression returns.

Two invariants:
  1. No v1 router defines its own ``pydantic.BaseModel`` subclass — every
     request/response DTO is imported from ``adapta.models.generated``.
  2. The generated package re-exports its models (so the routers' imports
     resolve) and the key response models the routers bind ARE the generated
     classes, by identity.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil

import pytest
from pydantic import BaseModel

import adapta.api.v1 as v1_pkg
from adapta.models import generated

V1_MODULES = sorted(m.name for m in pkgutil.iter_modules(v1_pkg.__path__))


@pytest.mark.parametrize("mod_name", V1_MODULES)
def test_router_defines_no_local_pydantic_models(mod_name: str) -> None:
    """Every API DTO must come from the generated contract, not be redefined."""
    module = importlib.import_module(f"adapta.api.v1.{mod_name}")
    local_models = [
        name
        for name, obj in inspect.getmembers(module, inspect.isclass)
        if issubclass(obj, BaseModel)
        and obj is not BaseModel
        and obj.__module__ == module.__name__  # defined HERE, not imported
    ]
    assert not local_models, (
        f"adapta.api.v1.{mod_name} defines hand-written Pydantic models {local_models}. "
        "API request/response models must be generated from specs/openapi.yaml and "
        "imported from adapta.models.generated (run `make generate`)."
    )


def test_generated_package_reexports_models() -> None:
    """`from adapta.models.generated import X` must resolve (package re-export)."""
    for name in ("ProjectResponse", "JobResponse", "ChatCompletionRequest", "BaseModelInfo"):
        assert hasattr(generated, name), f"adapta.models.generated does not export {name}"


def test_routers_bind_the_generated_models_by_identity() -> None:
    """Spot-check that routers reference the generated classes, not look-alikes."""
    from adapta.api.v1 import endpoints, jobs, projects, settings, usage

    assert projects.ProjectResponse is generated.ProjectResponse
    assert projects.ProjectCreate is generated.ProjectCreate
    assert jobs.JobResponse is generated.JobResponse
    assert jobs.JobCreateRequest is generated.JobCreateRequest
    assert endpoints.EndpointResponse is generated.EndpointResponse
    assert usage.UsageResponse is generated.UsageResponse
    assert settings.SettingResponse is generated.SettingResponse
