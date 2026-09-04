import threading
import time
from unittest import mock

from castero.episode import Episode
from castero.menus.chronomenu import ChronoMenu
from castero.workers import WorkerManager


window = mock.MagicMock()
window.getmaxyx = mock.MagicMock(return_value=(40, 80))


def test_menu_chrono_sorts_mixed_pubdates():
    unknown = mock.MagicMock(spec=Episode, pubdate=None)
    offset = mock.MagicMock(spec=Episode, pubdate="Tue, 18 Aug 2026 10:00:00 +1000")
    utc = mock.MagicMock(spec=Episode, pubdate="Tue, 18 Aug 2026 01:00:00 +0000")
    source = mock.MagicMock()
    source.episodes.return_value = [unknown, offset, utc]
    menu = ChronoMenu(window, source)
    menu.display = mock.MagicMock()

    menu._request_source_episodes()

    assert menu._episodes == [utc, offset, unknown]


def test_menu_chrono_inverts_mixed_pubdate_order():
    unknown = mock.MagicMock(spec=Episode, pubdate="not a date")
    offset = mock.MagicMock(spec=Episode, pubdate="Tue, 18 Aug 2026 10:00:00 +1000")
    utc = mock.MagicMock(spec=Episode, pubdate="Tue, 18 Aug 2026 01:00:00 +0000")
    source = mock.MagicMock()
    source.episodes.return_value = [unknown, offset, utc]
    menu = ChronoMenu(window, source)
    menu._inverted = True
    menu.display = mock.MagicMock()

    menu._request_source_episodes()

    assert menu._episodes == [unknown, offset, utc]


def test_menu_chrono_applies_worker_result_on_owner_thread():
    workers = WorkerManager(max_workers=1)
    owner_thread = threading.get_ident()
    callback_threads = []
    source = mock.MagicMock()
    source.episodes.return_value = []
    menu = ChronoMenu(window, source, workers=workers)
    menu.display = lambda: callback_threads.append(threading.get_ident())

    menu.update_items(None)
    deadline = time.monotonic() + 1
    while not callback_threads and time.monotonic() < deadline:
        workers.drain()
        time.sleep(0.001)

    assert callback_threads == [owner_thread]
    workers.shutdown()
