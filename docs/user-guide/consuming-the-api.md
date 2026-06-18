# Consuming the API

Once a project has an endpoint and a key, your applications talk to it through
the **OpenAI-compatible** chat completions API. This is the **only** protocol
customer applications use — if your code already talks to OpenAI, it already
talks to Adapta.

## The three things you need

| Thing | Where it comes from | Used as |
|---|---|---|
| **Base URL** | Your server, e.g. `http://your-server:8000/v1` | OpenAI client `base_url` |
| **Endpoint slug** | The Endpoint tab in the console | the `model` field |
| **Scoped key** (`adp_…`) | The Keys tab (shown once) | the `api_key` |

## Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://your-server:8000/v1",
    api_key="adp_xxxx…",            # scoped to one project endpoint
)

resp = client.chat.completions.create(
    model="support-kb-a1b2c3d4",    # your endpoint slug (from the console)
    messages=[{"role": "user", "content": "What is our refund window?"}],
)
print(resp.choices[0].message.content)
```

## curl

```bash
curl http://your-server:8000/v1/chat/completions \
  -H "Authorization: Bearer adp_xxxx…" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "support-kb-a1b2c3d4",
    "messages": [{"role": "user", "content": "What is our refund window?"}]
  }'
```

## What's different from vanilla OpenAI

- **The key picks the endpoint, not the `model` field.** Each `adp_` key is
  bound to exactly one endpoint. The `model` slug you pass must match the key's
  endpoint — a mismatched slug is rejected (`403`). This means a key can never
  reach an endpoint it wasn't issued for.
- **Answers carry citations when the project has documents.** If the project
  has indexed documents (a Knowledge project, or a fine-tune project that also
  uploaded documents), the response is grounded in them and includes the source
  chunks it used.
- **Usage is metered.** Every response includes `prompt_tokens`,
  `completion_tokens`, and `total_tokens`, and is rolled up per day (visible in
  the console's Usage tab).
- **Fine-tune endpoints serve base + adapter.** A fine-tune project's endpoint
  applies your trained LoRA adapter on top of the base model transparently — the
  request shape is identical. If that project also indexed documents, retrieval
  and the adapter compose in the same call (see
  [Knowledge + behavior together](knowledge-and-behavior.md)).

## Images (vision endpoints)

An endpoint whose project was created on a **vision base model** accepts the
standard OpenAI image content-parts — the image inline as a base64 `data:` URL:

```python
import base64

with open("invoice.png", "rb") as f:
    data_url = "data:image/png;base64," + base64.b64encode(f.read()).decode()

resp = client.chat.completions.create(
    model="invoice-reader-a1b2c3d4",
    messages=[{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": data_url}},
        {"type": "text", "text": "Extract vendor, date and total as JSON."},
    ]}],
)
```

Rules (v1, all violations come back as typed 4xx errors, never a crash):

- **Inline `data:` URLs only** — the server never fetches remote image URLs.
- png, jpeg or webp; **≤ 10 MB** and **≤ 8192 px** per image; **≤ 4 images** per request.
- Requests with images are **non-streaming** (`stream` must be false) and skip
  document retrieval — text-only requests on the same endpoint still answer
  from indexed documents with citations.
- Sending an image to a *text* endpoint returns a clear `400` — create the
  project on a vision base instead.

## Streaming

Set `"stream": true` (or `stream=True` in the SDK) to receive tokens as
server-sent events, the same as the OpenAI streaming protocol. The final chunk
carries the usage totals. (Not available for requests carrying images — see above.)

## Errors

Errors come back in a consistent envelope with a `correlation_id`:

```json
{ "error": { "code": "rate_limited", "message": "…", "correlation_id": "…" } }
```

If you need to report a problem, the `correlation_id` lets an operator find the
exact request in the server logs. No internal details (stack traces, library
errors) are ever exposed in the response.

---

The full request/response schema for every endpoint is in the
[API reference](../reference/api.md), generated from the live OpenAPI spec.
