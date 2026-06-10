# API reference

This is the complete HTTP API, rendered live from `specs/openapi.yaml` — the
same contract the server is validated against in CI (`make test-contracts`,
schemathesis). It cannot drift from the implementation: change the spec and this
page changes with it.

!!! info "OpenAI-compatible serving"
    `POST /v1/chat/completions` is the only protocol a customer's *applications*
    call. Everything else is the control plane an operator uses to set up
    projects, training, endpoints, and keys. For how to call the serving API
    from your code, see [Consuming the API](../user-guide/consuming-the-api.md).

A running instance also serves interactive docs at `/docs` (Swagger UI) and
`/redoc`.

!!swagger openapi.yaml!!
