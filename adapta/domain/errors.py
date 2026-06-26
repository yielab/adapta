"""
Typed error taxonomy for Adapta.

Rules enforced at the boundary (adapta/api/app.py):
- Code raises DomainError subclasses — never HTTPException, never str(e).
- ``internal_detail`` is logged server-side and never serialized to clients.
- Every error response carries a correlation ID stamped by middleware.
- ``make check-leaks`` CI gate prevents reintroducing raw str(e) to clients.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DomainError(Exception):
    """Base class for all application errors.

    Fields:
        message: Safe, human-readable text sent to the client.
        code: Stable machine-readable error code (snake_case).
        status: HTTP status code for the boundary handler.
        internal_detail: Diagnostic text logged server-side only — never sent to clients.

    The boundary handler in ``adapta/api/app.py`` is the only place that
    translates these into HTTP responses.  All service code raises subclasses;
    nothing outside ``app.py`` should catch and re-raise as HTTPException.
    """

    message: str
    code: str = "internal_error"
    status: int = 500
    internal_detail: Optional[str] = None

    def __str__(self) -> str:
        return self.message


@dataclass
class InvalidRequest(DomainError):
    """The client sent a semantically invalid value (HTTP 400).

    Use this for domain-level validation failures — e.g. a password that is
    too short, an unsupported file type, or a conflicting state transition.
    Structural schema failures (missing fields, wrong types) are handled by
    FastAPI's RequestValidationError and produce 422 automatically.
    """

    code: str = field(default="invalid_request", init=False)
    status: int = field(default=400, init=False)


@dataclass
class Unauthorized(DomainError):
    """The request is missing valid credentials (HTTP 401).

    Tells clients to authenticate; do not use when the caller is authenticated
    but lacks rights — use Forbidden instead.
    """

    code: str = field(default="unauthorized", init=False)
    status: int = field(default=401, init=False)


@dataclass
class Forbidden(DomainError):
    """Authenticated caller lacks permission for this resource (HTTP 403).

    Distinct from Unauthorized: the token is valid, but the role or team
    membership check failed.  Returning 401 here would wrongly prompt clients
    to re-authenticate.
    """

    code: str = field(default="forbidden", init=False)
    status: int = field(default=403, init=False)


@dataclass
class NotFound(DomainError):
    """A requested resource does not exist or is not accessible (HTTP 404)."""

    code: str = field(default="not_found", init=False)
    status: int = field(default=404, init=False)


@dataclass
class Conflict(DomainError):
    """The request conflicts with existing state (HTTP 409).

    Examples: registering a duplicate email, creating a second endpoint for a
    project that already has one.
    """

    code: str = field(default="conflict", init=False)
    status: int = field(default=409, init=False)


@dataclass
class ModelNotFound(NotFound):
    """A referenced base model is not in the catalog or its GGUF is absent (HTTP 404).

    Distinct from plain NotFound so callers can differentiate a missing model
    from a missing project or file.
    """

    code: str = field(default="model_not_found", init=False)


@dataclass
class ProjectNotFound(NotFound):
    """The referenced project does not exist or the caller's team does not own it."""

    code: str = field(default="project_not_found", init=False)


@dataclass
class TrainingFailed(DomainError):
    """A training job failed for a non-eval reason (HTTP 500).

    Examples: OOM during QLoRA, broken dataset file on disk, adapter
    conversion subprocess crash.  Distinct from EvalGateFailed (the job ran
    to completion but the adapter did not clear the threshold).
    """

    code: str = field(default="training_failed", init=False)
    status: int = field(default=500, init=False)


@dataclass
class InferenceFailed(DomainError):
    """The llama-cpp or vLLM inference call raised an unexpected exception (HTTP 500)."""

    code: str = field(default="inference_failed", init=False)
    status: int = field(default=500, init=False)


@dataclass
class AdapterConversionFailed(DomainError):
    """PEFT→GGUF LoRA conversion failed; the adapter cannot be served (HTTP 500)."""

    code: str = field(default="adapter_conversion_failed", init=False)
    status: int = field(default=500, init=False)


@dataclass
class EmbeddingFailed(DomainError):
    """sentence-transformers embedding or cross-encoder reranking call failed (HTTP 500).

    Raised from both EmbeddingService and RerankerService so they share the
    same HTTP surface.
    """

    code: str = field(default="embedding_failed", init=False)
    status: int = field(default=500, init=False)


@dataclass
class EvalGateFailed(DomainError):
    """A trained adapter did not clear the eval threshold (HTTP 422).

    HTTP 422 signals a business-rule rejection, not a server error: the job
    ran successfully, but the resulting adapter is not good enough to serve.
    The caller may inspect eval_score / eval_metrics on the job, improve the
    dataset, and re-train.
    """

    code: str = field(default="eval_gate_failed", init=False)
    status: int = field(default=422, init=False)


@dataclass
class RateLimited(DomainError):
    """Too many requests from this client (HTTP 429)."""

    code: str = field(default="rate_limited", init=False)
    status: int = field(default=429, init=False)


@dataclass
class Timeout(DomainError):
    """An upstream operation (Chroma retrieval, inference) exceeded its deadline (HTTP 504).

    504 Gateway Timeout is used rather than 408 Request Timeout because the
    deadline belongs to the server's call to a downstream component, not to
    the client's request delivery.
    """

    code: str = field(default="timeout", init=False)
    status: int = field(default=504, init=False)


@dataclass
class InternalError(DomainError):
    """A named raising point for unexpected server-side conditions (HTTP 500).

    Prefer a more specific subclass when the failure mode is known.  This
    class exists so services can write ``raise InternalError(...)`` to make
    intent explicit, rather than instantiating the base ``DomainError`` directly.
    """

    code: str = field(default="internal_error", init=False)
    status: int = field(default=500, init=False)
