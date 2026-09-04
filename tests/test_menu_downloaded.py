import threading
import time
from unittest import mock

from castero.menus.downloadedmenu import DownloadedMenu
from castero.workers import WorkerManager


def test_menu_downloaded_applies_worker_result_on_owner_thread(tmp_path):
    workers = WorkerManager(max_workers=1)
    owner_thread = threading.get_ident()
    callback_threads = []
    source = mock.MagicMock()
    window = mock.MagicMock()
    window.getmaxyx.return_value = (40, 80)
    menu = DownloadedMenu(window, source, workers=workers)
    menu.display = lambda: callback_threads.append(threading.get_ident())

    with mock.patch("castero.menus.downloadedmenu.download_path", return_value=str(tmp_path)):
        menu.update_items(None)
        deadline = time.monotonic() + 1
        while not callback_threads and time.monotonic() < deadline:
            workers.drain()
            time.sleep(0.001)

    assert callback_threads == [owner_thread]
    workers.shutdown()
