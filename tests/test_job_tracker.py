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


def test_begin_returns_token_and_finish_counts_down():
    jt = JobTracker()
    assert jt.inflight == 0
    t1 = jt.begin()
    t2 = jt.begin()
    assert t1 != t2
    assert jt.inflight == 2
    assert jt.finish(t1) == 1
    assert jt.finish(t2) == 0
    assert jt.finish(t2) == 0            # finishing twice is harmless, never negative
    assert jt.inflight == 0


def test_superseded_job_does_not_stop_the_new_one():
    """The bug fix: a superseded job finishing late must NOT zero the count of a
    newer in-flight job (which would stop the spinner early)."""
    jt = JobTracker()
    old = jt.begin()        # cycle A starts processing
    jt.reset()              # non-concurrent press supersedes A (forgets its token)
    new = jt.begin()        # cycle B starts processing
    assert jt.inflight == 1
    assert jt.finish(old) == 1   # A finishes late -> no-op, B still active
    assert jt.finish(new) == 0   # B finishes -> now zero -> spinner stops here


def test_results_fifo_and_empty_pop():
    jt = JobTracker()
    assert jt.pop_result() is None       # empty -> None, not an exception
    jt.push_result(("green", "first", 1))
    jt.push_result(("red", "second", 2))
    assert jt.pop_result() == ("green", "first", 1)
    assert jt.pop_result() == ("red", "second", 2)
    assert jt.pop_result() is None


def test_reset_clears_active_and_results():
    jt = JobTracker()
    jt.begin()
    jt.begin()
    jt.push_result(("green", "x", 1))
    jt.reset()
    assert jt.inflight == 0
    assert jt.pop_result() is None


def test_concurrent_begin_finish_is_consistent():
    """Many threads begin+finish; the active set must return to exactly empty."""
    jt = JobTracker()

    def work():
        for _ in range(1000):
            t = jt.begin()
            jt.finish(t)

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
            jt.push_result((tag, str(i), i))

    producers = [threading.Thread(target=produce, args=(f"t{n}",)) for n in range(8)]
    for t in producers:
        t.start()
    for t in producers:
        t.join()

    popped = 0
    while jt.pop_result() is not None:
        popped += 1
    assert popped == total
