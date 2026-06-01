import pytest

from voice_wheel.core.modes import (
    BUFFER_LABEL,
    VOICE_LABEL,
    Ring,
    build_system_prompt,
    build_user_message,
    get_sector,
    normalize_ring,
    normalize_sector,
    sector_keys,
    sectors,
)


def test_sectors_loaded_from_prompts():
    assert len(sectors()) >= 1
    assert all(s.prompt for s in sectors())
    assert all(s.key for s in sectors())


def test_system_prompt_is_the_sector_body_verbatim():
    first = sectors()[0]
    # the prompt body owns output rules + ГОЛОС/БУФЕР handling; the code adds nothing
    assert build_system_prompt(Ring.TRANSFORM, first.key) == first.prompt


def test_system_prompt_same_for_transform_and_context():
    # what differs between the rings is the user message (БУФЕР present or not),
    # not the system prompt — this also lets prompt caching reuse it
    key = sectors()[0].key
    assert build_system_prompt(Ring.TRANSFORM, key) == build_system_prompt(Ring.CONTEXT, key)


def test_dictate_has_no_llm_prompt():
    with pytest.raises(ValueError):
        build_system_prompt(Ring.DICTATE, sectors()[0].key)


def test_unknown_sector_yields_empty_system_prompt():
    assert get_sector("definitely-not-a-sector") is None
    assert build_system_prompt(Ring.TRANSFORM, "definitely-not-a-sector") == ""


def test_user_message_labels_speech_only():
    assert build_user_message("привет") == f"{VOICE_LABEL}\nпривет"
    assert BUFFER_LABEL not in build_user_message("привет")


def test_user_message_labels_and_separates_both():
    msg = build_user_message("ответь живо", context="чужой пост")
    assert f"{VOICE_LABEL}\nответь живо" in msg
    assert f"{BUFFER_LABEL}\nчужой пост" in msg
    # ГОЛОС (my intent) leads; БУФЕР (external) follows
    assert msg.index(VOICE_LABEL) < msg.index(BUFFER_LABEL)


def test_user_message_buffer_only_and_empty():
    assert build_user_message("", context="только буфер") == f"{BUFFER_LABEL}\nтолько буфер"
    assert build_user_message("   ") == ""
    assert build_user_message("", context="") == ""


def test_normalizers_fall_back_to_defaults():
    assert normalize_ring("bogus") is Ring.TRANSFORM
    assert normalize_ring("context") is Ring.CONTEXT
    keys = sector_keys()
    assert normalize_sector("bogus") == keys[0]
    assert normalize_sector(keys[0]) == keys[0]
