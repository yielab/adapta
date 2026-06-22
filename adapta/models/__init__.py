"""
Pydantic models for the Adapta API.

``adapta.models.generated`` — auto-generated from ``specs/openapi.yaml`` (the API
contract) via ``make generate``. These are the request/response models the API
routers consume directly: the spec is the single source of truth, the code is
generated from it, and ``make check-models`` (in ``make ci``) fails if the two
drift. There are no hand-written API models — change the spec, not the code.
"""
