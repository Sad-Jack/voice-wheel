import pytest

from voice_wheel.modes import (
    Ring,
    build_system_prompt,
    build_user_message,
    normalize_ring,
    normalize_sector,
)


def test_transform_prompt_includes_style_and_guardrails():
    prompt = build_system_prompt(Ring.TRANSFORM, "tech")
    assert "технически" in prompt  # the 'tech' style line
    assert "Не добавляй новые факты" in prompt  # don't-invent guardrail


def test_context_prompt_references_clipboard():
    prompt = build_system_prompt(Ring.CONTEXT, "friendly")
    assert "буфера обмена" in prompt
    assert "дружелюбно" in prompt


def test_dictate_has_no_llm_prompt():
    with pytest.raises(ValueError):
        build_system_prompt(Ring.DICTATE, "clean")


def test_user_message_with_and_without_context():
    assert build_user_message("hello") == "hello"
    msg = build_user_message("reply nicely", context="original post")
    assert "original post" in msg
    assert "reply nicely" in msg


def test_normalizers_fall_back_to_defaults():
    assert normalize_ring("bogus") is Ring.TRANSFORM
    assert normalize_ring("context") is Ring.CONTEXT
    assert normalize_sector("bogus") == "normalize"
    assert normalize_sector("short") == "short"
