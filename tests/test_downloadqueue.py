import os
import threading
import time
from unittest import mock

from castero.downloadqueue import DownloadQueue
from castero.episode import Episode
from castero.feed import Feed
from castero.workers import WorkerManager

my_dir = os.path.dirname(os.path.realpath(__file__))

feed = Feed(file=my_dir + "/feeds/valid_basic.xml")
episode1 = Episode(feed=feed, title="episode1 title")
episode2 = Episode(feed=feed, title="episode2 title")


def wait_for(predicate, timeout=1):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.001)
    return predicate()


def test_downloadqueue_init():
    mydownloadqueue = DownloadQueue()
    assert isinstance(mydownloadqueue, DownloadQueue)


def test_downloadqueue_add():
    mydownloadqueue = DownloadQueue()
    assert mydownloadqueue.length == 0
    mydownloadqueue.add(episode1)
    assert mydownloadqueue.length == 1
    mydownloadqueue.add(episode1)
    assert mydownloadqueue.length == 1
    mydownloadqueue.add(episode2)
    assert mydownloadqueue.length == 2


def test_downloadqueue_remove_by_episode_id():
    mydownloadqueue = DownloadQueue()
    queued_episode = Episode(feed=feed, ep_id=1, title="queued episode")
    matching_episode = Episode(feed=feed, ep_id=1, title="matching episode")
    mydownloadqueue.add(queued_episode)

    mydownloadqueue.remove(matching_episode)

    assert mydownloadqueue.length == 0


def test_downloadqueue_remove_current_does_not_skip_next():
    mydownloadqueue = DownloadQueue()
    first = Episode(feed=feed, ep_id=1, title="first episode")
    second = Episode(feed=feed, ep_id=2, title="second episode")
    first.download = mock.MagicMock()
    second.download = mock.MagicMock()
    mydownloadqueue.add(first)
    mydownloadqueue.add(second)
    mydownloadqueue.start()

    mydownloadqueue.remove(first)
    assert mydownloadqueue.cancelled
    mydownloadqueue.next()

    assert mydownloadqueue.length == 1
    assert wait_for(lambda: second.download.call_count == 1)
    second.download.assert_called_once_with(mydownloadqueue, None)
    mydownloadqueue.stop()


def test_downloadqueue_advances_past_episode_without_enclosure():
    mydownloadqueue = DownloadQueue()
    missing_enclosure = Episode(feed=feed, ep_id=1, title="missing enclosure")
    next_episode = Episode(feed=feed, ep_id=2, title="next episode")
    next_episode.download = mock.MagicMock()
    mydownloadqueue.add(missing_enclosure)
    mydownloadqueue.add(next_episode)

    mydownloadqueue.start()

    assert wait_for(lambda: mydownloadqueue.length == 1)
    assert wait_for(lambda: next_episode.download.call_count == 1)
    next_episode.download.assert_called_once_with(mydownloadqueue, None)
    mydownloadqueue.stop()


def test_downloadqueue_start():
    mydownloadqueue = DownloadQueue()
    mydownloadqueue._display = mock.MagicMock()
    mydownloadqueue.add(episode1)
    episode1.download = mock.MagicMock(name="download")
    mydownloadqueue.start()
    assert wait_for(lambda: episode1.download.call_count == 1)
    episode1.download.assert_called_with(
        mydownloadqueue,
        mydownloadqueue._display,
    )
    mydownloadqueue.stop()


def test_downloadqueue_first():
    mydownloadqueue = DownloadQueue()
    mydownloadqueue.add(episode1)
    assert mydownloadqueue.first == episode1


def test_downloadqueue_next():
    mydownloadqueue = DownloadQueue()
    mydownloadqueue.add(episode1)
    mydownloadqueue.add(episode2)
    mydownloadqueue.start = mock.MagicMock(name="start")
    mydownloadqueue.next()
    assert mydownloadqueue.length == 1
    assert mydownloadqueue.start.call_count == 1


def test_downloadqueue_update():
    mydownloadqueue = DownloadQueue()
    mydownloadqueue.add(episode1)
    mydownloadqueue.start = mock.MagicMock(name="start")
    mydownloadqueue.update()
    assert mydownloadqueue.start.call_count == 1


def test_downloadqueue_stop_cancels_and_joins_active_worker():
    workers = WorkerManager(max_workers=1)
    download_queue = DownloadQueue(workers=workers)
    episode = Episode(feed=feed, ep_id=1, title="active episode")
    started = threading.Event()
    finished = threading.Event()

    def download(queue, _display):
        started.set()
        while not queue.cancelled:
            finished.wait(0.001)
        finished.set()
        queue.next()

    episode.download = download
    download_queue.add(episode)
    download_queue.start()
    assert started.wait(1)

    download_queue.stop()

    assert finished.is_set()
    assert download_queue.length == 0
    assert download_queue._worker is None
    workers.shutdown()


def test_downloadqueue_runs_download_on_managed_worker():
    workers = WorkerManager(max_workers=1)
    download_queue = DownloadQueue(workers=workers)
    episode = Episode(feed=feed, ep_id=1, title="active episode")
    owner_thread = threading.get_ident()
    worker_threads = []
    started = threading.Event()

    def download(queue, _display):
        worker_threads.append(threading.get_ident())
        started.set()
        queue.next()

    episode.download = download
    download_queue.add(episode)
    download_queue.start()
    assert started.wait(1)
    download_queue.stop()

    assert worker_threads
    assert worker_threads != [owner_thread]
    workers.shutdown()


def test_downloadqueue_rejects_work_after_stop():
    download_queue = DownloadQueue()
    episode = Episode(feed=feed, ep_id=1, title="episode")

    download_queue.stop()
    download_queue.add(episode)
    download_queue.start()

    assert download_queue.length == 0
