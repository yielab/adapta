"""
§E1.3 — train = serve: one prompt renderer for SFT/DPO training, eval and serving.

Proves, without a GPU, that the trainer builds its training text from the exact
same renderer the serving path (``adapta.core.inference.InferenceEngine``) uses,
so an adapter is never trained/gated on a conditioning the endpoint doesn't
actually send. Serving's own prompt construction (``_format_chat_prompt``) is a
thin call to ``chat_templates.render`` — calling that function directly here
*is* simulating what the serving path would send for the same messages.
"""

from adapta.core import chat_templates, model_catalog
from adapta.training.trainer import render_training_example, resolve_chat_template


def test_resolve_chat_template_matches_catalog_entry():
    # The same base model resolves to the same template name training/eval/serving
    # all key off (adapta.core.model_catalog.CatalogEntry.chat_template).
    entry = model_catalog.resolve("qwen2.5-1.5b-instruct")
    assert entry is not None
    assert resolve_chat_template("qwen2.5-1.5b-instruct") == entry.chat_template


def test_training_text_starts_with_the_serving_prompt_for_the_same_messages():
    messages = [
        {"role": "system", "content": "You are terse."},
        {"role": "user", "content": "What is the capital of France?"},
        {"role": "assistant", "content": "Paris."},
    ]
    template_name = resolve_chat_template("qwen2.5-1.5b-instruct")

    # What serving would send for the SAME system + user turn (no answer yet) —
    # this is exactly what adapta.core.inference.InferenceEngine._format_chat_prompt
    # does: it calls chat_templates.render with the request's chat_template, system
    # prompt and messages. No engine import is needed to reproduce it — that is the
    # point of chat_templates.render being pure.
    from types import SimpleNamespace

    serving_prompt = chat_templates.render(
        template_name,
        "You are terse.",
        [SimpleNamespace(role="user", content="What is the capital of France?")],
    )

    train_prompt, train_target = render_training_example(template_name, messages)

    # The trainer's prompt is byte-for-byte what serving would render for a live
    # completion request on the same turns.
    assert train_prompt == serving_prompt

    # The full training text is prompt + target + stop token; it must start with
    # exactly the serving prompt.
    stop_token = chat_templates.default_stops(template_name)[0]
    training_text = train_prompt + train_target + stop_token
    assert training_text.startswith(serving_prompt)

    # The target begins right after the assistant cue, and the cue is the last
    # thing in the prompt — so the boundary the trainer/evaluator mask on is the
    # same point serving stops generating from.
    assert train_prompt.endswith("<|im_start|>assistant\n")
    assert train_target == "Paris."
    assert training_text == train_prompt + "Paris." + stop_token


def test_dpo_prompt_uses_the_same_renderer():
    # DPO rows carry no system turn (the worker drops it before it reaches the
    # trainer) — only the bare user prompt is rendered.
    template_name = resolve_chat_template("qwen2.5-1.5b-instruct")
    dpo_prompt, _ = render_training_example(
        template_name, [{"role": "user", "content": "Summarize this."}]
    )
    from types import SimpleNamespace

    expected = chat_templates.render(
        template_name, None, [SimpleNamespace(role="user", content="Summarize this.")]
    )
    assert dpo_prompt == expected
    assert dpo_prompt.endswith("<|im_start|>assistant\n")
