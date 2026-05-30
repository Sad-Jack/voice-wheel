import threading

from voice_wheel.core.job_tracker import JobTracker


def test_generation_bumps_and_is_captured():
    jt = JobTracker()
    assert jt.generation == 0
    assert jt.bump_generation() == 1
    gen = jt.generation
    assert gen == 1
    assert not jt.is_stale(gen)
    jt.bump_generation()                 # a newer cycle starts
    assert jt.is_stale(gen)              # the captured gen is now stale


def test_inflight_begin_finish_never_negative():
    jt = JobTracker()
    assert jt.inflight == 0
    assert jt.begin() == 1
    assert jt.begin() == 2
    assert jt.finish() == 1
    assert jt.finish() == 0
    assert jt.finish() == 0              # clamps at 0, never negative
    assert jt.inflight == 0


def test_results_fifo_and_empty_pop():
    jt = JobTracker()
    assert jt.pop_result() is None       # empty -> None, not an exception
    jt.push_result(("green", "first"))
    jt.push_result(("red", "second"))
    assert jt.pop_result() == ("green", "first")
    assert jt.pop_result() == ("red", "second")
    assert jt.pop_result() is None


def test_reset_clears_inflight_and_results():
    jt = JobTracker()
    jt.begin()
    jt.begin()
    jt.push_result(("green", "x"))
    jt.reset()
    assert jt.inflight == 0
    assert jt.pop_result() is None


def test_concurrent_begin_finish_is_consistent():
    """Many threads begin+finish; the count must return to exactly zero."""
    jt = JobTracker()

    def work():
        for _ in range(1000):
            jt.begin()
            jt.finish()

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert jt.inflight == 0


def test_concurrent_push_pop_loses_nothing():
    """Producers push N items; a drain pops exactly N back."""
    jt = JobTracker()
    total = 8 * 500

    def produce(tag):
        for i in range(500):
            jt.push_result((tag, str(i)))

    producers = [threading.Thread(target=produce, args=(f"t{n}",)) for n in range(8)]
    for t in producers:
        t.start()
    for t in producers:
        t.join()

    popped = 0
    while jt.pop_result() is not None:
        popped += 1
    assert popped == total
