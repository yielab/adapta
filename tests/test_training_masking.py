"""
§E1.4 — response-only loss for text SFT.

Proves, without a GPU, that ``adapta.training.masking.response_labels`` — the
pure helper the trainer and the eval gate now BOTH build labels with — masks
exactly the shared prompt/full-text prefix, not a fixed prompt length. This is
the regression guard for the §A3.2 single-token masking bug: a bare-label
classification row (one response token) must leave exactly that token
unmasked, even when the prompt/full tokenizations merge at the boundary.
"""

from adapta.training.masking import response_labels


def test_response_only_tokens_are_unmasked_prompt_is_masked():
    # No merge at the boundary: prompt_ids is a clean prefix of full_ids.
    prompt_ids = [1, 2, 3]
    full_ids = [1, 2, 3, 4, 5]
    labels = response_labels(prompt_ids, full_ids)
    assert labels == [-100, -100, -100, 4, 5]


def test_bare_label_classification_row_leaves_exactly_the_label_token_unmasked():
    # The §A3.2 regression case: tokenizing the prompt alone yields a trailing
    # token (e.g. a lone " " after "Assistant: ") that, in the full text,
    # fuses with the single-token answer into one different id. The prompt-only
    # and full-text sequences diverge at that final position, so the longest
    # common prefix stops one token short of the prompt's own length — and
    # exactly the response token (here: id 99, standing in for a fused
    # " positive" token) is left scorable.
    prompt_ids = [10, 11, 12, 7]  # trailing token 7 is "Assistant: "'s lone space
    full_ids = [10, 11, 12, 99]  # in the full text that position fused → " positive"
    labels = response_labels(prompt_ids, full_ids)
    assert labels == [-100, -100, -100, 99]
    unmasked = [t for t in labels if t != -100]
    assert unmasked == [99]  # exactly one label token survives — the answer


def test_full_ids_identical_to_prompt_masks_everything():
    # Degenerate: truncation cut the whole response away, so prompt and full
    # tokenizations are identical. Nothing is left scorable — this row
    # contributes no loss (handled by the caller, not this function).
    prompt_ids = [1, 2, 3]
    full_ids = [1, 2, 3]
    labels = response_labels(prompt_ids, full_ids)
    assert labels == [-100, -100, -100]


def test_empty_prompt_leaves_everything_unmasked():
    labels = response_labels([], [4, 5, 6])
    assert labels == [4, 5, 6]


def test_response_labels_is_pure_and_does_not_mutate_inputs():
    prompt_ids = [1, 2]
    full_ids = [1, 2, 3]
    response_labels(prompt_ids, full_ids)
    assert prompt_ids == [1, 2]
    assert full_ids == [1, 2, 3]
