"""
Typed error taxonomy for Brain From Cero.

Rules:
- Code raises DomainError subclasses — never HTTPException, never str(e).
- Global handlers in app.py translate these to HTTP responses.
- internal_detail is logged server-side and NEVER sent to clients.
- Every response includes a correlation ID (set by middleware).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DomainError(Exception):
    message: str
    code: str = "internal_error"
    status: int = 500
    internal_detail: Optional[str] = None

    def __str__(self) -> str:
        return self.message


@dataclass
class InvalidRequest(DomainError):
    code: str = field(default="invalid_request", init=False)
    status: int = field(default=400, init=False)


@dataclass
class Unauthorized(DomainError):
    code: str = field(default="unauthorized", init=False)
    status: int = field(default=401, init=False)


@dataclass
class Forbidden(DomainError):
    code: str = field(default="forbidden", init=False)
    status: int = field(default=403, init=False)


@dataclass
class NotFound(DomainError):
    code: str = field(default="not_found", init=False)
    status: int = field(default=404, init=False)


@dataclass
class Conflict(DomainError):
    code: str = field(default="conflict", init=False)
    status: int = field(default=409, init=False)


@dataclass
class ModelNotFound(NotFound):
    code: str = field(default="model_not_found", init=False)


@dataclass
class ProjectNotFound(NotFound):
    code: str = field(default="project_not_found", init=False)


@dataclass
class TrainingFailed(DomainError):
    code: str = field(default="training_failed", init=False)
    status: int = field(default=500, init=False)


@dataclass
class InferenceFailed(DomainError):
    code: str = field(default="inference_failed", init=False)
    status: int = field(default=500, init=False)


@dataclass
class EmbeddingFailed(DomainError):
    code: str = field(default="embedding_failed", init=False)
    status: int = field(default=500, init=False)


@dataclass
class EvalGateFailed(DomainError):
    """Raised when a trained adapter doesn't clear the eval threshold."""
    code: str = field(default="eval_gate_failed", init=False)
    status: int = field(default=422, init=False)


@dataclass
class RateLimited(DomainError):
    code: str = field(default="rate_limited", init=False)
    status: int = field(default=429, init=False)


@dataclass
class Timeout(DomainError):
    code: str = field(default="timeout", init=False)
    status: int = field(default=504, init=False)


@dataclass
class InternalError(DomainError):
    code: str = field(default="internal_error", init=False)
    status: int = field(default=500, init=False)
