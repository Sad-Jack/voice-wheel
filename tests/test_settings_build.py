"""Structural regression net for the settings window build (B2 refactor).

Unlike the other settings tests (which check specific behaviours), this asserts
the *shape* of the built view tree: every widget attribute exists, the 9 tabs are
present in order, controls live inside the right connection groups, tooltips wire
up, the dirty round-trip holds, and the safe UI handlers don't throw. These are
exactly the regressions that extracting `_build` into per-tab builders could
introduce silently (a forgotten container restore, a dropped attr) — they don't
raise on their own, so we pin them here.

Builds the real NSWindow under a shared NSApplication; never writes config.
"""

from __future__ import annotations

import pytest

pytest.importorskip("AppKit")

from AppKit import NSApplication  # noqa: E402

NSApplication.sharedApplication()

from voice_wheel.hostos.macos.settings import (  # noqa: E402
    SettingsWindow,
    _FlippedView,
)

# Widget attrs assigned in _build that must be a live (non-None) ObjC object.
# Excludes _ollama_state (a status string, None until checked) and _logs_timer
# (None until the Logs tab is shown).
WIDGET_ATTRS = [
    "_tabs", "_grp_api", "_grp_ollama", "_grp_cc",
    "_provider", "_provider_row", "_api_model", "_api_model_row", "_api_no_key_btn",
    "_ollama", "_ollama_none_btn", "_ollama_url", "_cc_model", "_cc_status", "_cc_action",
    "_ollama_status", "_ollama_action",
    "_models_installed", "_models_pull", "_models_dl_btn",
    "_prompts_label", "_rules_stack",
    "_stt_backend", "_stt_model", "_lang",
    "_tts_enabled", "_tts_voice", "_prem",
    "_tts_kb", "_cap_tts_kb", "_tts_kb_on", "_tts_ms", "_cap_tts_ms", "_tts_ms_on",
    "_wheel_kb", "_cap_wheel_kb", "_wheel_kb_on",
    "_wheel_ms", "_cap_wheel_ms", "_wheel_ms_on",
    "_concurrent", "_uilang_popup", "_logs_view",
    "_restart_warn", "_note", "_save_btn", "_window",
]

LIST_ATTRS = ["_conn_radios", "_key_rows", "_installed_rows", "_sectors",
              "_tts_ms_map", "_wheel_ms_map"]

TAB_IDS = ["tab_llm", "tab_models", "tab_prompts", "tab_keys", "tab_stt",
           "tab_voice", "tab_triggers", "tab_lang", "tab_logs"]


def _window():
    w = SettingsWindow.alloc().init()
    w._build()
    return w


def _is_descendant(ancestor, view) -> bool:
    """True if `view` is anywhere in `ancestor`'s subview tree."""
    stack = [ancestor]
    while stack:
        v = stack.pop()
        for kid in v.subviews():
            if kid == view:
                return True
            stack.append(kid)
    return False


# ---- (a) every widget attribute exists and is non-None --------------------

def test_all_widget_attrs_present_and_live():
    w = _window()
    missing = [a for a in WIDGET_ATTRS if getattr(w, a, None) is None]
    assert not missing, f"missing/None widget attrs after build: {missing}"


def test_collection_attrs_are_lists():
    w = _window()
    for a in LIST_ATTRS:
        assert isinstance(getattr(w, a), list), a
    assert len(w._conn_radios) == 3   # ollama / api / cc
    assert len(w._key_rows) == 3      # anthropic / openai / ollama


# ---- (b) tab identity, count and order ------------------------------------

def test_nine_tabs_in_expected_order():
    w = _window()
    tabs = w._tabs
    assert tabs.numberOfTabViewItems() == 9
    ids = [tabs.tabViewItemAtIndex_(i).identifier() for i in range(9)]
    assert ids == TAB_IDS, ids


# ---- (c) connection-group containment (forgotten group() restore guard) ---

def test_controls_live_inside_their_connection_group():
    w = _window()
    assert _is_descendant(w._grp_api, w._provider)
    assert _is_descendant(w._grp_api, w._api_model)
    assert _is_descendant(w._grp_api, w._api_no_key_btn)
    assert _is_descendant(w._grp_ollama, w._ollama)
    assert _is_descendant(w._grp_cc, w._cc_model)
    # the Ollama URL field now lives on the «Модели» tab, not the LLM Ollama group
    assert not _is_descendant(w._grp_ollama, w._ollama_url)
    # and NOT mis-nested across groups
    assert not _is_descendant(w._grp_ollama, w._provider)
    assert not _is_descendant(w._grp_api, w._cc_model)


# ---- (d) each tab's document view is the flipped (top-left origin) view ----

def test_each_tab_doc_view_is_flipped():
    w = _window()
    tabs = w._tabs
    for i in range(tabs.numberOfTabViewItems()):
        view = tabs.tabViewItemAtIndex_(i).view()
        if view.respondsToSelector_("documentView") and view.documentView() is not None:
            view = view.documentView()  # scroll tabs wrap the _FlippedView
        ident = tabs.tabViewItemAtIndex_(i).identifier()
        assert isinstance(view, _FlippedView), f"{ident}: doc view is {type(view)}"


# ---- (e) tooltips wire up (dereferences ~30 widgets) ----------------------

def test_set_tooltips_runs():
    w = _window()
    w._set_tooltips()  # must not raise


# ---- (f) dirty round-trip + snapshot arity --------------------------------

def test_build_leaves_form_clean_and_snapshot_arity():
    w = _window()
    assert w._dirty is False
    assert w._full_snapshot() == w._baseline
    assert len(w._full_snapshot()) == 6  # llm, keys, stt, voice, triggers, lang


def test_mutate_then_revert_toggles_dirty():
    w = _window()
    n = w._lang.numberOfItems()
    orig = w._lang.indexOfSelectedItem()
    w._lang.selectItemAtIndex_((orig + 1) % n)
    w.markDirty_(None)
    assert w._dirty is True
    w._lang.selectItemAtIndex_(orig)
    w._recompute_dirty()
    assert w._dirty is False


# ---- (g) scoped safe-handler smoke (no thread/subprocess/modal handlers) ---

def test_safe_ui_handlers_do_not_throw():
    w = _window()
    w.markDirty_(None)
    w.providerChanged_(None)
    w.triggerToggled_(None)
    w.ttsEnabledChanged_(None)
    w.clearLogs_(None)
    for sel in ("resetLlm_", "resetStt_", "resetVoice_", "resetTriggers_", "resetLang_"):
        getattr(w, sel)(None)
    # exercise a prompt row: expand, switch connection to API, switch provider
    if w._rules:
        r = w._rules[0]
        w.ruleToggle_(r["disclosure"])
        api_radio = next(rb for rb, t in r["radios"] if t == "api")
        w.ruleConnChanged_(api_radio)
        w.ruleProviderChanged_(r["provider"])
    # reveal then the eye toggle path
    w.toggleKeyRow_(w._key_rows[0]["eye"])


# ---- per-prompt connection rows (the new Prompts-tab design) --------------

def test_one_collapsible_row_per_prompt():
    w = _window()
    assert len(w._rules) == len(w._sectors)
    assert {r["sector_key"] for r in w._rules} == {s.key for s in w._sectors}


def test_prompt_rows_default_to_base_and_show_inherit():
    w = _window()
    for r in w._rules:
        assert w._prompt_row_backend(r) == w._current_backend()  # defaults to base
        s = str(r["summary"].stringValue())
        assert "как базовая" in s or "as base" in s  # inherit summary, not an override


def test_changing_a_row_model_makes_it_an_override():
    w = _window()
    r = w._rules[0]
    r["model"].setStringValue_("some-other-model")  # differs from base
    w._update_rule_summary(r)
    assert "→" in str(r["summary"].stringValue())  # override arrow, not "inherit"
    # the tab_llm snapshot (which drives Save) ends with the per-prompt rules tuple
    snap = w._tab_snapshot("tab_llm")
    assert any("some-other-model" in str(x) for x in snap[-1])


# ---- (h) build is idempotent (the _window guard) --------------------------

def test_build_is_idempotent():
    w = _window()
    w._build()  # second call must no-op
    assert w._tabs.numberOfTabViewItems() == 9
