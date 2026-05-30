import pytest

from voice_wheel.core.modes import (
    Ring,
    build_system_prompt,
    build_user_message,
    normalize_ring,
    normalize_sector,
    sector_keys,
    sectors,
)


def test_sectors_loaded_from_prompts():
    assert len(sectors()) >= 1
    assert all(s.prompt for s in sectors())
    assert all(s.key for s in sectors())


def test_transform_prompt_includes_sector_prompt_and_tail():
    first = sectors()[0]
    prompt = build_system_prompt(Ring.TRANSFORM, first.key)
    assert first.prompt[:24] in prompt               # the file's own instruction
    assert "не выбрасывай части" in prompt.lower()   # universal output guardrail


def test_context_prompt_references_clipboard():
    prompt = build_system_prompt(Ring.CONTEXT, sectors()[0].key)
    assert "буфера обмена" in prompt


def test_dictate_has_no_llm_prompt():
    with pytest.raises(ValueError):
        build_system_prompt(Ring.DICTATE, sectors()[0].key)


def test_user_message_with_and_without_context():
    assert build_user_message("hello") == "hello"
    msg = build_user_message("reply nicely", context="original post")
    assert "original post" in msg
    assert "reply nicely" in msg


def test_normalizers_fall_back_to_defaults():
    assert normalize_ring("bogus") is Ring.TRANSFORM
    assert normalize_ring("context") is Ring.CONTEXT
    keys = sector_keys()
    assert normalize_sector("bogus") == keys[0]
    assert normalize_sector(keys[0]) == keys[0]
