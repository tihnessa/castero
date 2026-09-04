import threading
import time

import pytest

from castero.workers import WorkerManager


def drain_until(workers, predicate, timeout=1):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        workers.drain()
        time.sleep(0.001)
    workers.drain()


def test_worker_results_are_applied_on_owner_thread():
    workers = WorkerManager(max_workers=1)
    owner_thread = threading.get_ident()
    worker_threads = []
    callback_threads = []
    results = []

    def work():
        worker_threads.append(threading.get_ident())
        return "finished"

    future = workers.submit(
        work,
        on_result=lambda result: (
            callback_threads.append(threading.get_ident()),
            results.append(result),
        ),
    )
    future.result(timeout=1)

    assert results == []
    drain_until(workers, lambda: bool(results))

    assert results == ["finished"]
    assert callback_threads == [owner_thread]
    assert worker_threads != callback_threads
    workers.shutdown()


def test_worker_manager_requires_a_positive_pool_size():
    with pytest.raises(ValueError):
        WorkerManager(max_workers=0)


def test_worker_manager_bounds_concurrent_work():
    workers = WorkerManager(max_workers=2)
    started = []
    two_started = threading.Event()
    release = threading.Event()
    lock = threading.Lock()

    def work(index):
        with lock:
            started.append(index)
            if len(started) == 2:
                two_started.set()
        release.wait(1)

    futures = [workers.submit(work, index) for index in range(3)]
    assert two_started.wait(1)
    time.sleep(0.01)
    assert len(started) == 2

    release.set()
    for future in futures:
        future.result(timeout=1)
    assert sorted(started) == [0, 1, 2]
    workers.shutdown()


def test_worker_manager_rejects_duplicate_keyed_work():
    workers = WorkerManager(max_workers=2)
    started = threading.Event()
    release = threading.Event()

    def work():
        started.set()
        release.wait(1)

    first = workers.submit(work, key="reload")
    assert started.wait(1)

    assert workers.submit(work, key="reload") is None

    release.set()
    first.result(timeout=1)
    workers.shutdown()


def test_shutdown_cancels_running_work_and_rejects_new_work():
    workers = WorkerManager(max_workers=1)
    started = threading.Event()
    finished = threading.Event()

    def work():
        started.set()
        while not workers.cancelled:
            finished.wait(0.001)
        finished.set()

    workers.submit(work)
    assert started.wait(1)

    workers.shutdown()

    assert finished.is_set()
    assert workers.submit(lambda: None) is None


def test_shutdown_discards_pending_ui_callbacks():
    workers = WorkerManager(max_workers=1)
    callback = []
    workers.call_soon(callback.append, "stale")

    workers.shutdown()
    workers.drain()

    assert callback == []
