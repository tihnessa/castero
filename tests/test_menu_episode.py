import threading
import time
from unittest import mock

from castero.episode import Episode
from castero.feed import Feed
from castero.menus.episodemenu import EpisodeMenu
from castero.workers import WorkerManager

feed = mock.MagicMock(spec=Feed)
episode1 = mock.MagicMock(spec=Episode)
episode2 = mock.MagicMock(spec=Episode)
window = mock.MagicMock()
window.getmaxyx = mock.MagicMock(return_value=(40, 80))
source = mock.MagicMock()
source.episodes = mock.MagicMock(return_value=[episode1, episode2])

episode1.progress = 0
episode2.progress = 0

episode1.title = "episode1"
episode2.title = "episode1"


def test_menu_episode_init():
    mymenu = EpisodeMenu(window, source)
    assert isinstance(mymenu, EpisodeMenu)


@mock.patch("curses.color_pair")
@mock.patch("curses.A_NORMAL")
def test_menu_episode_update_items(mock_color_pair, mock_A_NORMAL):
    mymenu = EpisodeMenu(window, source)
    mymenu.update_items(feed)
    source.episodes.assert_called_with(feed)
    assert len(mymenu._items) == 2
    assert len(mymenu) == 2


@mock.patch("curses.color_pair")
@mock.patch("curses.A_NORMAL")
def test_menu_episode_items(mock_A_NORMAL, mock_color_pair):
    mymenu = EpisodeMenu(window, source)
    mymenu.update_items(feed)
    items = mymenu._items
    assert {"attr": mock_color_pair(5), "tags": ["D"], "text": str(episode1)} in items


def test_menu_episode_item_none():
    mymenu = EpisodeMenu(window, source)
    assert mymenu.item is None


@mock.patch("curses.color_pair")
def test_menu_episode_item(_color_pair):
    mymenu = EpisodeMenu(window, source)
    mymenu.update_items(feed)
    assert mymenu.item == episode1
    mymenu._selected += 1
    assert mymenu.item == episode2


def test_menu_episode_metadata_none():
    mymenu = EpisodeMenu(window, source)
    assert mymenu.metadata == ""
    mymenu.update_items(None)
    assert mymenu.metadata == ""


@mock.patch("curses.color_pair")
def test_menu_episode_metadata(_color_pair):
    mymenu = EpisodeMenu(window, source)
    mymenu.update_items(feed)
    assert mymenu.metadata == episode1.metadata


@mock.patch("curses.color_pair")
@mock.patch("curses.A_NORMAL")
def test_menu_episode_update_child(mock_A_NORMAL, mock_color_pair):
    mymenu = EpisodeMenu(window, source)
    mymenu.update_items(feed)
    items = mymenu._items
    mymenu.update_child()
    assert mymenu._items == items


@mock.patch("curses.color_pair")
def test_menu_episode_invert(_color_pair):
    mymenu = EpisodeMenu(window, source)
    mymenu.invert()
    assert mymenu._inverted
    mymenu.update_items(feed)


def test_menu_episode_sorts_mixed_pubdates():
    unknown = mock.MagicMock(spec=Episode, pubdate=None)
    offset = mock.MagicMock(spec=Episode, pubdate="Tue, 18 Aug 2026 10:00:00 +1000")
    utc = mock.MagicMock(spec=Episode, pubdate="Tue, 18 Aug 2026 01:00:00 +0000")
    local_source = mock.MagicMock()
    local_source.episodes.return_value = [unknown, offset, utc]
    mymenu = EpisodeMenu(window, local_source)
    mymenu._feed = feed
    mymenu.display = mock.MagicMock()

    mymenu._request_source_episodes(feed)

    assert mymenu._episodes == [utc, offset, unknown]


def test_menu_episode_inverts_mixed_pubdate_order():
    unknown = mock.MagicMock(spec=Episode, pubdate="not a date")
    offset = mock.MagicMock(spec=Episode, pubdate="Tue, 18 Aug 2026 10:00:00 +1000")
    utc = mock.MagicMock(spec=Episode, pubdate="Tue, 18 Aug 2026 01:00:00 +0000")
    local_source = mock.MagicMock()
    local_source.episodes.return_value = [unknown, offset, utc]
    mymenu = EpisodeMenu(window, local_source)
    mymenu._feed = feed
    mymenu._inverted = True
    mymenu.display = mock.MagicMock()

    mymenu._request_source_episodes(feed)

    assert mymenu._episodes == [unknown, offset, utc]


def test_menu_episode_applies_worker_result_on_owner_thread():
    workers = WorkerManager(max_workers=1)
    owner_thread = threading.get_ident()
    loaded = threading.Event()
    callback_threads = []
    local_source = mock.MagicMock()
    local_source.episodes.return_value = [episode1]
    mymenu = EpisodeMenu(window, local_source, workers=workers)
    mymenu.display = lambda: (callback_threads.append(threading.get_ident()), loaded.set())

    mymenu.update_items(feed)
    deadline = time.monotonic() + 1
    while not loaded.is_set() and time.monotonic() < deadline:
        workers.drain()
        time.sleep(0.001)

    assert loaded.is_set()
    assert callback_threads == [owner_thread]
    workers.shutdown()


def test_menu_episode_discards_stale_worker_result():
    workers = WorkerManager(max_workers=2)
    first_feed = mock.MagicMock(spec=Feed)
    second_feed = mock.MagicMock(spec=Feed)
    first_episode = mock.MagicMock(spec=Episode, pubdate=None)
    second_episode = mock.MagicMock(spec=Episode, pubdate=None)
    release_first = threading.Event()

    def episodes(selected_feed):
        if selected_feed is first_feed:
            release_first.wait(1)
            return [first_episode]
        return [second_episode]

    local_source = mock.MagicMock()
    local_source.episodes.side_effect = episodes
    mymenu = EpisodeMenu(window, local_source, workers=workers)
    mymenu.display = mock.MagicMock()

    mymenu.update_items(first_feed)
    mymenu.update_items(second_feed)
    release_first.set()

    deadline = time.monotonic() + 1
    while mymenu._episodes != [second_episode] and time.monotonic() < deadline:
        workers.drain()
        time.sleep(0.001)

    assert mymenu._episodes == [second_episode]
    workers.shutdown()
