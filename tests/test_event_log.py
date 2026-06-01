"""Tests for the structured event log behind the «Логи» settings tab."""

from voice_wheel.core.event_log import EventLog, classify_error


def test_classify_error_buckets():
    assert classify_error("STT: model failed to transcribe") == "stt"
    assert classify_error("401 Unauthorized: invalid x-api-key") == "auth"
    assert classify_error("Error code: 429 rate limit exceeded") == "rate_limit"
    assert classify_error("Connection refused (max retries)") == "unreachable"
    assert classify_error("model 'llama3' not found, pull it first") == "model"
    assert classify_error("something weird happened") == "other"
    assert classify_error("") == "other"


def test_add_and_recent_is_newest_first():
    log = EventLog()
    log.add("dictate", transcript="привет", result="привет")
    log.add("tts", text="готово")
    recent = log.recent()
    assert [e["kind"] for e in recent] == ["tts", "dictate"]
    assert recent[0]["text"] == "готово"
    assert all("t" in e and "level" in e for e in recent)


def test_recent_limit_and_maxlen():
    log = EventLog(maxlen=3)
    for i in range(5):
        log.add("dictate", result=str(i))
    # only the last 3 survive; newest first
    assert [e["result"] for e in log.recent()] == ["4", "3", "2"]
    assert [e["result"] for e in log.recent(2)] == ["4", "3"]


def test_clear_empties_memory_and_file(tmp_path):
    path = tmp_path / "events.jsonl"
    log = EventLog(path=path)
    log.add("error", level="error", message="boom", cat="other")
    assert path.read_text(encoding="utf-8").strip()
    log.clear()
    assert log.recent() == []
    assert path.read_text(encoding="utf-8") == ""


def test_jsonl_persists_and_reloads_tail(tmp_path):
    path = tmp_path / "events.jsonl"
    first = EventLog(path=path)
    first.add("dictate", result="один")
    first.add("transform", sector="clean", result="два")
    # a fresh log over the same file restores the tail (newest first)
    reopened = EventLog(path=path)
    restored = reopened.recent()
    assert [e["result"] for e in restored] == ["два", "один"]
    assert restored[0]["sector"] == "clean"


def test_file_compacts_when_over_byte_cap(tmp_path):
    import json

    path = tmp_path / "events.jsonl"
    # a tiny cap forces compaction on every append; the file must never keep more
    # than the in-memory tail (maxlen), so it can't grow without bound
    log = EventLog(path=path, maxlen=10, max_bytes=50)
    for i in range(50):
        log.add("dictate", result=f"event-{i}")
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) <= 10                       # bounded to maxlen, not 50
    assert json.loads(lines[-1])["result"] == "event-49"   # newest survives
    # and the in-memory view is consistent (newest first)
    assert log.recent(1)[0]["result"] == "event-49"


def test_load_tail_skips_corrupt_lines(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text('{"kind": "tts", "text": "ok"}\nnot json\n', encoding="utf-8")
    log = EventLog(path=path)
    recent = log.recent()
    assert len(recent) == 1
    assert recent[0]["text"] == "ok"
