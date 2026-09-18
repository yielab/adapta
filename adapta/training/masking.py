"""Pure prompt/response label masking for causal-LM SFT (§E1.4).

Lifted out of ``ModelEvaluator._tokenize_with_response_mask`` (§A3.2) so the
trainer and the eval gate share exactly ONE masking boundary instead of two
implementations that could drift.

The boundary is the **longest common prefix** of the prompt-only and
full-text (prompt + target) token id sequences — not ``len(prompt_ids)``.
Tokenizing the prompt alone and the full text can retokenize differently
right at the join: a prompt ending in ``"Assistant: "`` tokenizes its
trailing space as a lone token, but in the full text that space fuses into
the response's first token (e.g. ``" account"``). Masking a fixed prefix
length would then bury that response token too, leaving single-token
responses (a bare classification label, a yes/no) entirely un-scorable —
loss skipped, gate wrongly failing an adapter that did learn the behavior.
The longest common prefix is the true boundary: it masks exactly the shared
context and leaves the first divergent (response) token, and everything
after it, gradable.
"""


def response_labels(prompt_ids: list[int], full_ids: list[int]) -> list[int]:
    """Causal-LM labels for ``full_ids``, masking (``-100``) the run shared
    with ``prompt_ids`` at the start of ``full_ids``.

    Positions from the first point of divergence onward (the response, plus
    anything after it) keep their token id as the label, so cross-entropy is
    computed response-only. Returns a plain ``list[int]`` the same length as
    ``full_ids`` — callers convert to whatever tensor type they need.
    """
    mask_len = 0
    # strict=False on purpose: the two tokenizations diverge at the boundary,
    # so the shorter one (the prompt) bounds the scan — we only want the
    # shared leading run, not a length match.
    for p, f in zip(prompt_ids, full_ids, strict=False):
        if p != f:
            break
        mask_len += 1
    return [-100] * mask_len + list(full_ids[mask_len:])
