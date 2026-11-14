"""Item 6.0a (ADR-029): the served generator prompt, the NO_ANSWER sentinel and its fallback.

The prompt has two parts, a system text and a user template, and the manifest's hash covers both.
The failure these tests guard is silent: a prompt edit that leaves the hash alone describes the
wrong prompt in every manifest, and a sentinel that reaches a customer (or the cache) looks like
an ordinary answer.
"""

import hashlib

import pytest

from rag import generate

# The served prompt, pinned. Changing either part changes this, and that needs an ADR.
SERVED_PROMPT_SHA256 = "7a6acf979a041a7683e67a8453de1316636410998d2c225ef12f7b2179fe3929"
OLD_PROMPT_SHA256 = "3e224f4500a18dc065ab6e24c46e25302ac275f8e145085bfb211bcf65ba67dd"

FALLBACK = (
    "Sorry, I don't have that detail for this product. "
    "Please check the product page or contact our support team."
)


def test_the_served_prompt_hash_is_pinned():
    assert generate.prompt_sha256() == SERVED_PROMPT_SHA256


def test_the_hash_covers_the_system_text_and_the_template(monkeypatch):
    base = generate.prompt_sha256()
    with monkeypatch.context() as m:
        m.setattr(generate, "_SYSTEM_PROMPT", generate._SYSTEM_PROMPT + " Be brief.")
        assert generate.prompt_sha256() != base
    with monkeypatch.context() as m:
        m.setattr(generate, "_PROMPT_TEMPLATE", generate._PROMPT_TEMPLATE + " ")
        assert generate.prompt_sha256() != base
    # the two parts are hashed with a NUL between them
    joined = generate._SYSTEM_PROMPT + "\x00" + generate._PROMPT_TEMPLATE
    assert base == hashlib.sha256(joined.encode()).hexdigest()


def test_the_old_prompt_is_no_longer_the_served_one():
    assert generate.prompt_sha256() != OLD_PROMPT_SHA256


def test_the_request_body_carries_the_system_text():
    body = generate._request_body("Q?", [])
    assert body["system"] == generate._SYSTEM_PROMPT
    assert body["think"] is False
    assert body["prompt"].endswith("Question: Q?\nAnswer:")


@pytest.mark.parametrize(
    "text",
    [
        "NO_ANSWER",
        "no_answer",
        "No answer.",
        "NO ANSWER",
        "  NO_ANSWER\n",
        "The reply is NO_ANSWER.",
    ],
)
def test_a_sentinel_becomes_the_fixed_sentence_and_is_flagged(text):
    assert generate.finalize(text) == (FALLBACK, True)
    assert generate.FALLBACK_ANSWER == FALLBACK


@pytest.mark.parametrize(
    "text",
    [
        "Yes. Unopened items can be returned within 30 days.",
        "The answer is 30 days.",
        "Please answer the survey after you call.",
        "There is no answering machine on the support line.",
        "",
    ],
)
def test_an_ordinary_answer_is_unchanged(text):
    assert generate.finalize(text) == (text, False)
