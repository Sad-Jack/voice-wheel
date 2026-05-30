from voice_wheel.history import History


def test_add_and_recent_newest_first(tmp_path):
    hist = History(tmp_path / "h.sqlite", limit=10)
    hist.add("dictate", "clean", "t1", "r1")
    hist.add("transform", "tech", "t2", "r2")
    recent = hist.recent()
    assert [e.result for e in recent] == ["r2", "r1"]
    hist.close()


def test_prune_keeps_only_limit(tmp_path):
    hist = History(tmp_path / "h.sqlite", limit=3)
    for i in range(7):
        hist.add("dictate", "clean", f"t{i}", f"r{i}")
    recent = hist.recent(100)
    assert len(recent) == 3
    assert [e.result for e in recent] == ["r6", "r5", "r4"]
    hist.close()
