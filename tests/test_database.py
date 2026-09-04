import os
import sqlite3
import threading
from shutil import copyfile
from unittest import mock

import pytest

from castero.episode import Episode
from castero.feed import Feed
from castero.database import Database
from castero.config import Config
from castero.queue import Queue
from castero.player import Player

my_dir = os.path.dirname(os.path.realpath(__file__))


def feed_response(url, content, status_code=200, history=None):
    response = mock.MagicMock()
    response.request.url = url
    response.content = content
    response.status_code = status_code
    response.history = [] if history is None else history
    return response


def valid_feed_content():
    with open(my_dir + "/feeds/valid_basic.xml", "rb") as feed_file:
        return feed_file.read()


def test_database_migrates_episode_guid_column(tmp_path):
    database_path = tmp_path / "castero.db"
    connection = sqlite3.connect(str(database_path))
    for migration in sorted(os.listdir(Database.MIGRATIONS_DIR)):
        if int(migration.split("-")[0]) > 5:
            continue
        with open(os.path.join(Database.MIGRATIONS_DIR, migration), "rt") as migration_file:
            connection.executescript(migration_file.read())
    connection.execute(
        "insert into feed (key, title) values (?, ?)",
        ("https://example.com/feed.xml", "Feed"),
    )
    connection.execute(
        "insert into episode (id, feed_key, title, enclosure, played) "
        "values (?, ?, ?, ?, ?)",
        (1, "https://example.com/feed.xml", "Episode", "episode.mp3", 0),
    )

    Database.migrate_connection(connection)

    assert connection.execute("pragma user_version").fetchone()[0] == 6
    assert "guid" in {
        row[1] for row in connection.execute("pragma table_info(episode)").fetchall()
    }
    assert connection.execute("select id, guid from episode").fetchone() == (1, None)
    connection.close()


def test_database_default(prevent_modification):
    mydatabase = Database()
    assert isinstance(mydatabase, Database)


def test_database_serializes_connection_access(display):
    started = threading.Event()
    completed = threading.Event()

    def read_feeds():
        started.set()
        display.database.feeds()
        completed.set()

    with display.database._lock:
        thread = threading.Thread(target=read_feeds)
        thread.start()
        assert started.wait(1)
        assert not completed.wait(0.05)

    assert completed.wait(1)
    thread.join()


def test_database_close_replaces_existing_backup_on_windows(tmp_path, monkeypatch):
    database_path = tmp_path / "castero.db"
    monkeypatch.setattr(Database, "PATH", str(database_path))
    monkeypatch.setattr(Database, "OLD_PATH", str(tmp_path / "feeds"))
    Config.data["restrict_memory_usage"] = "False"

    first_database = Database()
    feed = Feed(file=my_dir + "/feeds/valid_basic.xml")
    first_database.replace_feed(feed)
    first_database.close()

    second_database = Database()
    feed._title = "updated feed title"
    second_database.replace_feed(feed)

    original_rename = os.rename

    def windows_rename(source, destination):
        if os.path.exists(destination):
            raise FileExistsError(destination)
        original_rename(source, destination)

    monkeypatch.setattr(os, "rename", windows_rename)
    second_database.close()

    current_connection = sqlite3.connect(database_path)
    current_title = current_connection.execute("select title from feed").fetchone()[0]
    current_connection.close()

    backup_connection = sqlite3.connect(str(database_path) + ".old")
    backup_title = backup_connection.execute("select title from feed").fetchone()[0]
    backup_connection.close()

    assert current_title == "updated feed title"
    assert backup_title == "myfeed title"


def test_database_feeds_length(prevent_modification):
    copyfile(my_dir + "/datafiles/database_example1.db", Database.PATH)
    mydatabase = Database()

    assert len(mydatabase.feeds()) == 2


def test_database_feed(prevent_modification):
    copyfile(my_dir + "/datafiles/database_example1.db", Database.PATH)
    mydatabase = Database()

    feed = mydatabase.feeds()[0]
    assert isinstance(feed, Feed)
    assert feed.key == "feed key"
    assert feed.title == "feed title"


def test_database_delete_feed(prevent_modification):
    copyfile(my_dir + "/datafiles/database_example1.db", Database.PATH)
    mydatabase = Database()
    assert len(mydatabase.feeds()) == 2

    feed = mydatabase.feeds()[0]
    mydatabase.delete_feed(feed)
    assert len(mydatabase.feeds()) == 1


def test_database_delete_feed_and_episode(prevent_modification):
    copyfile(my_dir + "/datafiles/database_example1.db", Database.PATH)
    mydatabase = Database()

    feed = mydatabase.feeds()[0]
    feed_episode = mydatabase.episodes(feed)[0]

    mydatabase.delete_feed(feed)
    feed_episode = mydatabase.episodes(feed)
    assert len(feed_episode) == 0


def test_database_feed_episodes(prevent_modification):
    copyfile(my_dir + "/datafiles/database_example1.db", Database.PATH)
    mydatabase = Database()

    feed = mydatabase.feeds()[0]
    episodes = mydatabase.episodes(feed)
    for episode in episodes:
        assert isinstance(episode, Episode)


def test_database_episode_id(prevent_modification):
    copyfile(my_dir + "/datafiles/database_example1.db", Database.PATH)
    mydatabase = Database()

    episode = mydatabase.episode(1)
    assert episode.ep_id == 1
    assert episode.title == "episode title"


def test_database_episodes_length(prevent_modification):
    copyfile(my_dir + "/datafiles/database_example1.db", Database.PATH)
    mydatabase = Database()

    feed1 = mydatabase.feeds()[0]
    feed2 = mydatabase.feeds()[1]
    assert len(mydatabase.episodes(feed1)) == 1
    assert len(mydatabase.episodes(feed2)) == 1


def test_database_feed_unplayed_episode_length(prevent_modification):
    copyfile(my_dir + "/datafiles/database_example1.db", Database.PATH)
    mydatabase = Database()
    myfeed_path = my_dir + "/feeds/valid_basic.xml"
    myfeed = Feed(file=myfeed_path)
    episodes = myfeed.parse_episodes()

    mydatabase.replace_feed(myfeed)
    mydatabase.replace_episode(myfeed, episodes[0])
    mydatabase.replace_episode(myfeed, episodes[1])
    assert len(mydatabase.unplayed_episodes(myfeed)) == 2
    feed_episodes = mydatabase.episodes(myfeed)
    feed_episodes[0].played = 1
    mydatabase.replace_episode(myfeed, feed_episodes[0])
    assert len(mydatabase.unplayed_episodes(myfeed)) == 1


def test_database_add_feed(prevent_modification):
    copyfile(my_dir + "/datafiles/database_example1.db", Database.PATH)
    mydatabase = Database()

    myfeed_path = my_dir + "/feeds/valid_basic.xml"
    myfeed = Feed(file=myfeed_path)

    assert len(mydatabase.feeds()) == 2
    mydatabase.replace_feed(myfeed)
    assert len(mydatabase.feeds()) == 3


def test_database_replace_feed(prevent_modification):
    copyfile(my_dir + "/datafiles/database_example1.db", Database.PATH)
    mydatabase = Database()

    myfeed_path = my_dir + "/feeds/valid_basic.xml"
    myfeed1 = Feed(file=myfeed_path)
    myfeed2 = Feed(file=myfeed_path)

    mydatabase.replace_feed(myfeed1)
    assert len(mydatabase.feeds()) == 3
    mydatabase.replace_feed(myfeed2)
    assert len(mydatabase.feeds()) == 3


def test_database_add_episode(prevent_modification):
    copyfile(my_dir + "/datafiles/database_example1.db", Database.PATH)
    mydatabase = Database()

    myfeed_path = my_dir + "/feeds/valid_basic.xml"
    myfeed = Feed(file=myfeed_path)
    episodes = myfeed.parse_episodes()

    mydatabase.replace_feed(myfeed)
    assert len(mydatabase.episodes(myfeed)) == 0
    mydatabase.replace_episode(myfeed, episodes[0])
    assert len(mydatabase.episodes(myfeed)) == 1


def test_database_replace_episode(prevent_modification):
    copyfile(my_dir + "/datafiles/database_example1.db", Database.PATH)
    mydatabase = Database()

    myfeed_path = my_dir + "/feeds/valid_basic.xml"
    myfeed = Feed(file=myfeed_path)
    episodes = myfeed.parse_episodes()

    mydatabase.replace_feed(myfeed)
    mydatabase.replace_episode(myfeed, episodes[0])
    assert len(mydatabase.episodes(myfeed)) == 1
    episode = mydatabase.episodes(myfeed)[0]
    mydatabase.replace_episode(myfeed, episode)
    assert len(mydatabase.episodes(myfeed)) == 1


def test_database_round_trips_episode_guid(display):
    mydatabase = display.database
    myfeed = Feed(file=my_dir + "/feeds/valid_basic.xml")
    episode = Episode(
        myfeed,
        title="Episode with GUID",
        enclosure="https://example.com/episode.mp3",
        guid="episode-guid",
    )
    mydatabase.replace_feed(myfeed)
    mydatabase.replace_episode(myfeed, episode)

    assert mydatabase.episode(episode.ep_id).guid == "episode-guid"
    assert mydatabase.episodes(myfeed)[0].guid == "episode-guid"
    assert mydatabase.episodes()[0].guid == "episode-guid"
    assert mydatabase.unplayed_episodes(myfeed)[0].guid == "episode-guid"

    player = mock.MagicMock(spec=Player)
    player.episode = mydatabase.episode(episode.ep_id)
    queue = Queue(display)
    queue.add(player)
    mydatabase.replace_queue(queue)
    assert mydatabase.queue()[0].guid == "episode-guid"

    updated = Episode(
        myfeed,
        ep_id=episode.ep_id,
        title="Updated episode",
        enclosure="https://example.com/episode.mp3",
        guid="updated-guid",
    )
    mydatabase.replace_episode(myfeed, updated)
    assert mydatabase.episode(episode.ep_id).guid == "updated-guid"


def test_database_download_metadata(prevent_modification):
    copyfile(my_dir + "/datafiles/database_example1.db", Database.PATH)
    mydatabase = Database()
    episode = mydatabase.episode(1)

    mydatabase.replace_download(
        episode, "feed_title/1-episode_title.mp3", "a" * 64
    )

    stored = mydatabase.episode(1)
    assert stored.download_path == "feed_title/1-episode_title.mp3"
    assert stored.download_checksum == "a" * 64

    mydatabase.delete_download(stored)
    stored = mydatabase.episode(1)
    assert stored.download_path is None
    assert stored.download_checksum is None


def test_database_add_episodes(prevent_modification):
    copyfile(my_dir + "/datafiles/database_example1.db", Database.PATH)
    mydatabase = Database()

    myfeed_path = my_dir + "/feeds/valid_basic.xml"
    myfeed = Feed(file=myfeed_path)
    episodes = myfeed.parse_episodes()

    mydatabase.replace_feed(myfeed)
    assert len(mydatabase.episodes(myfeed)) == 0
    mydatabase.replace_episodes(myfeed, episodes)
    assert len(mydatabase.episodes(myfeed)) == len(episodes)


def test_database_delete_feed_episode_and_progress(prevent_modification):
    copyfile(my_dir + "/datafiles/database_example1.db", Database.PATH)
    mydatabase = Database()

    feed = mydatabase.feeds()[0]
    feed_episode = mydatabase.episodes(feed)[0]
    mydatabase.replace_progress(feed_episode, 1000)

    feed_episode = mydatabase.episodes(feed)[0]
    assert feed_episode.progress == 1000
    mydatabase.replace_progress(feed_episode, 1000)
    mydatabase.delete_feed(feed)
    # returns None since nothing was deleted
    assert mydatabase.delete_progress(feed_episode) is None


def test_database_add_episode_progress(prevent_modification):
    copyfile(my_dir + "/datafiles/database_example1.db", Database.PATH)
    mydatabase = Database()
    ep = mydatabase.episode(1)
    mydatabase.replace_progress(ep, 1000)
    ep_db = mydatabase.episode(1)
    assert ep_db.progress == 1000
    assert ep.progress == 1000


def test_database_delete_episode_progress(prevent_modification):
    copyfile(my_dir + "/datafiles/database_example1.db", Database.PATH)
    mydatabase = Database()
    ep = mydatabase.episode(1)
    mydatabase.replace_progress(ep, 1000)
    p = mydatabase.episode(1)
    assert ep.progress == 1000
    assert p.progress == 1000
    mydatabase.delete_progress(ep)
    p = mydatabase.episode(1)
    assert ep.progress == 0
    assert p.progress == 0


def test_database_reload(prevent_modification, display):
    mydatabase = Database()

    myfeed_path = my_dir + "/feeds/valid_basic.xml"
    myfeed = Feed(file=myfeed_path)
    real_title = myfeed.title
    myfeed._title = "fake title"

    mydatabase.replace_feed(myfeed)

    display.change_status = mock.MagicMock(name="change_status")
    mydatabase.reload(display)
    assert display.change_status.call_count == 2
    assert mydatabase.feeds()[0].title == real_title


def test_database_reload_uses_async_response_without_downloading_again(
    prevent_modification, monkeypatch
):
    mydatabase = Database()
    old_feed = Feed(url="https://example.com/feed.xml", title="old title")
    mydatabase.replace_feed(old_feed)
    response = feed_response(old_feed.key, valid_feed_content())
    display = mock.MagicMock()

    monkeypatch.setattr(
        "castero.database.grequests.imap",
        lambda requests, size: iter([response]),
    )
    get = mock.MagicMock(side_effect=AssertionError("unexpected synchronous GET"))
    monkeypatch.setattr("castero.feed.Net.Get", get)

    mydatabase.reload(display, [old_feed])

    get.assert_not_called()
    assert mydatabase.feed(old_feed.key).title == "myfeed title"
    display.change_status.assert_called_with("Successfully reloaded 1 feeds")
    display.invalidate_menus.assert_called_once_with()


@pytest.mark.parametrize("content", [b"not xml", b""])
def test_database_reload_rejects_invalid_async_content_without_retrying(
    prevent_modification, monkeypatch, content
):
    mydatabase = Database()
    old_feed = Feed(url="https://example.com/feed.xml", title="old title")
    response = feed_response(old_feed.key, content)
    display = mock.MagicMock()
    mydatabase._reload_feed_data = mock.MagicMock()

    monkeypatch.setattr(
        "castero.database.grequests.imap",
        lambda requests, size: iter([response]),
    )
    get = mock.MagicMock(side_effect=AssertionError("unexpected synchronous GET"))
    monkeypatch.setattr("castero.feed.Net.Get", get)

    mydatabase.reload(display, [old_feed])

    get.assert_not_called()
    mydatabase._reload_feed_data.assert_not_called()
    display.change_status.assert_called_with(
        "Successfully reloaded 0 feeds (1 errors)"
    )
    display.invalidate_menus.assert_called_once_with()


def test_database_reload_rejects_non_200_async_response(
    prevent_modification, monkeypatch
):
    mydatabase = Database()
    old_feed = Feed(url="https://example.com/feed.xml", title="old title")
    response = feed_response(old_feed.key, valid_feed_content(), status_code=500)
    display = mock.MagicMock()
    mydatabase._reload_feed_data = mock.MagicMock()

    monkeypatch.setattr(
        "castero.database.grequests.imap",
        lambda requests, size: iter([response]),
    )
    get = mock.MagicMock(side_effect=AssertionError("unexpected synchronous GET"))
    monkeypatch.setattr("castero.feed.Net.Get", get)

    mydatabase.reload(display, [old_feed])

    get.assert_not_called()
    mydatabase._reload_feed_data.assert_not_called()
    display.change_status.assert_called_with(
        "Successfully reloaded 0 feeds (1 errors)"
    )
    display.invalidate_menus.assert_called_once_with()


def test_database_reload_counts_async_responses_that_are_not_yielded_as_errors(
    prevent_modification, monkeypatch
):
    mydatabase = Database()
    old_feed = Feed(url="https://example.com/feed.xml", title="old title")
    display = mock.MagicMock()
    mydatabase._reload_feed_data = mock.MagicMock()

    monkeypatch.setattr(
        "castero.database.grequests.imap",
        lambda requests, size: iter([]),
    )

    mydatabase.reload(display, [old_feed])

    mydatabase._reload_feed_data.assert_not_called()
    display.change_status.assert_called_once_with(
        "Successfully reloaded 0 feeds (1 errors)"
    )
    display.invalidate_menus.assert_called_once_with()


def test_database_reload_reports_mixed_url_and_file_results(
    prevent_modification, monkeypatch, tmp_path
):
    mydatabase = Database()
    url_feed = Feed(url="https://example.com/feed.xml", title="url feed")
    file_feed = Feed(file=my_dir + "/feeds/valid_basic.xml")
    missing_feed = Feed(file=str(tmp_path / "missing.xml"), title="missing feed")
    response = feed_response(url_feed.key, valid_feed_content())
    display = mock.MagicMock()
    mydatabase._reload_feed_data = mock.MagicMock()

    monkeypatch.setattr(
        "castero.database.grequests.imap",
        lambda requests, size: iter([response]),
    )
    get = mock.MagicMock(side_effect=AssertionError("unexpected synchronous GET"))
    monkeypatch.setattr("castero.feed.Net.Get", get)

    mydatabase.reload(display, [url_feed, file_feed, missing_feed])

    get.assert_not_called()
    assert mydatabase._reload_feed_data.call_count == 2
    display.change_status.assert_called_with(
        "Successfully reloaded 2 feeds (1 errors)"
    )
    display.invalidate_menus.assert_called_once_with()


def test_database_reload_matches_redirected_response_to_original_feed(
    prevent_modification, monkeypatch
):
    mydatabase = Database()
    old_feed = Feed(url="https://example.com/feed.xml", title="old title")
    redirect = mock.MagicMock()
    redirect.url = old_feed.key
    response = feed_response(
        "https://cdn.example.com/feed.xml",
        valid_feed_content(),
        history=[redirect],
    )
    display = mock.MagicMock()
    mydatabase._reload_feed_data = mock.MagicMock()

    monkeypatch.setattr(
        "castero.database.grequests.imap",
        lambda requests, size: iter([response]),
    )
    get = mock.MagicMock(side_effect=AssertionError("unexpected synchronous GET"))
    monkeypatch.setattr("castero.feed.Net.Get", get)

    mydatabase.reload(display, [old_feed])

    get.assert_not_called()
    reloaded_old_feed, new_feed = mydatabase._reload_feed_data.call_args.args
    assert reloaded_old_feed is old_feed
    assert new_feed.key == old_feed.key
    display.change_status.assert_called_with("Successfully reloaded 1 feeds")
    display.invalidate_menus.assert_called_once_with()


def test_database_reload_skips_results_after_cancellation(
    prevent_modification, monkeypatch
):
    mydatabase = Database()
    feed = Feed(url="https://example.com/feed.xml", title="feed")
    response = mock.MagicMock()
    response.request.url = feed.key
    cancel_event = threading.Event()
    display = mock.MagicMock()
    mydatabase._reload_feed_data = mock.MagicMock()

    def responses(_requests, size):
        assert size == 3
        cancel_event.set()
        yield response

    monkeypatch.setattr("castero.database.grequests.imap", responses)

    mydatabase.reload(display, [feed], cancel_event)

    mydatabase._reload_feed_data.assert_not_called()
    display.change_status.assert_not_called()
    display.invalidate_menus.assert_not_called()


def test_database_reload_preserves_episode_progress(prevent_modification):
    mydatabase = Database()

    myfeed_path = my_dir + "/feeds/valid_basic.xml"
    myfeed = Feed(file=myfeed_path)
    mydatabase.replace_feed(myfeed)
    mydatabase.replace_episodes(myfeed, myfeed.parse_episodes())

    episodes = mydatabase.episodes(myfeed)
    mydatabase.replace_progress(episodes[0], 42000)

    reloaded_feed = Feed(file=myfeed_path)
    mydatabase._reload_feed_data(myfeed, reloaded_feed)

    reloaded_episodes = {episode.title: episode for episode in mydatabase.episodes(reloaded_feed)}
    assert reloaded_episodes[episodes[0].title].progress == 42000
    assert reloaded_episodes[episodes[1].title].progress == 0


def test_database_reload_preserves_queued_retained_episode(display):
    mydatabase = display.database

    myfeed_path = my_dir + "/feeds/valid_basic.xml"
    myfeed = Feed(file=myfeed_path)
    mydatabase.replace_feed(myfeed)
    mydatabase.replace_episodes(myfeed, myfeed.parse_episodes())

    episodes = mydatabase.episodes(myfeed)
    retained_episode_id = episodes[0].ep_id

    myqueue = Queue(display)
    for episode in episodes:
        player = mock.MagicMock(spec=Player)
        player.episode = episode
        myqueue.add(player)
    mydatabase.replace_queue(myqueue)

    reloaded_feed = Feed(file=myfeed_path)
    reloaded_feed._description = "updated feed description"
    reloaded_episodes = reloaded_feed.parse_episodes()
    reloaded_episodes[0]._description = "updated episode description"
    reloaded_feed.parse_episodes = mock.MagicMock(return_value=reloaded_episodes)
    Config.data["max_episodes"] = "1"

    mydatabase._reload_feed_data(myfeed, reloaded_feed)

    queued_episodes = mydatabase.queue()
    assert len(queued_episodes) == 1
    assert queued_episodes[0].ep_id == retained_episode_id
    assert queued_episodes[0].description == "updated episode description"
    assert mydatabase.feed(reloaded_feed.key).description == "updated feed description"
    assert len(mydatabase.episodes(reloaded_feed)) == 1


def test_database_reload_retains_absent_episodes_and_metadata(display):
    mydatabase = display.database

    myfeed_path = my_dir + "/feeds/valid_basic.xml"
    myfeed = Feed(file=myfeed_path)
    mydatabase.replace_feed(myfeed)
    mydatabase.replace_episodes(myfeed, myfeed.parse_episodes())

    original_episodes = mydatabase.episodes(myfeed)
    original_episode_ids = {
        episode.title: episode.ep_id for episode in original_episodes
    }
    absent_episode = original_episodes[1]
    mydatabase.replace_progress(absent_episode, 42000)

    myqueue = Queue(display)
    player = mock.MagicMock(spec=Player)
    player.episode = absent_episode
    myqueue.add(player)
    mydatabase.replace_queue(myqueue)

    reloaded_feed = Feed(file=myfeed_path)
    current_episode = reloaded_feed.parse_episodes()[0]
    reloaded_feed.parse_episodes = mock.MagicMock(return_value=[current_episode])
    Config.data["retain_absent_episodes"] = "True"
    Config.data["max_episodes"] = "-1"

    mydatabase._reload_feed_data(myfeed, reloaded_feed)

    retained_episodes = {
        episode.title: episode for episode in mydatabase.episodes(reloaded_feed)
    }
    assert {
        title: episode.ep_id for title, episode in retained_episodes.items()
    } == original_episode_ids
    assert retained_episodes[absent_episode.title].progress == 42000
    assert [episode.ep_id for episode in mydatabase.queue()] == [
        absent_episode.ep_id
    ]


def test_database_reload_removes_absent_episodes_when_retention_disabled(display):
    mydatabase = display.database

    myfeed_path = my_dir + "/feeds/valid_basic.xml"
    myfeed = Feed(file=myfeed_path)
    mydatabase.replace_feed(myfeed)
    mydatabase.replace_episodes(myfeed, myfeed.parse_episodes())

    original_episodes = mydatabase.episodes(myfeed)
    absent_episode = original_episodes[1]
    mydatabase.replace_progress(absent_episode, 42000)

    myqueue = Queue(display)
    player = mock.MagicMock(spec=Player)
    player.episode = absent_episode
    myqueue.add(player)
    mydatabase.replace_queue(myqueue)

    reloaded_feed = Feed(file=myfeed_path)
    current_episode = reloaded_feed.parse_episodes()[0]
    reloaded_feed.parse_episodes = mock.MagicMock(return_value=[current_episode])
    Config.data["retain_absent_episodes"] = "False"
    Config.data["max_episodes"] = "-1"

    mydatabase._reload_feed_data(myfeed, reloaded_feed)

    reloaded_episodes = mydatabase.episodes(reloaded_feed)
    assert [episode.title for episode in reloaded_episodes] == [
        current_episode.title
    ]
    assert mydatabase.episode(absent_episode.ep_id) is None
    assert mydatabase.queue() == []


def test_database_reload_caps_retained_absent_episodes(display):
    mydatabase = display.database

    myfeed_path = my_dir + "/feeds/valid_basic.xml"
    myfeed = Feed(file=myfeed_path)
    mydatabase.replace_feed(myfeed)
    mydatabase.replace_episodes(myfeed, myfeed.parse_episodes())

    original_episodes = mydatabase.episodes(myfeed)
    reloaded_feed = Feed(file=myfeed_path)
    current_episode = reloaded_feed.parse_episodes()[0]
    reloaded_feed.parse_episodes = mock.MagicMock(return_value=[current_episode])
    Config.data["retain_absent_episodes"] = "True"
    Config.data["max_episodes"] = "2"

    mydatabase._reload_feed_data(myfeed, reloaded_feed)

    retained_episodes = mydatabase.episodes(reloaded_feed)
    assert [episode.title for episode in retained_episodes] == [
        original_episodes[0].title,
        original_episodes[1].title,
    ]
    assert retained_episodes[0].ep_id == original_episodes[0].ep_id
    assert retained_episodes[1].ep_id == original_episodes[1].ep_id
    assert mydatabase.episode(original_episodes[2].ep_id) is None


def test_database_reload_matches_duplicate_titles_by_enclosure(display):
    mydatabase = display.database

    myfeed_path = my_dir + "/feeds/valid_basic.xml"
    myfeed = Feed(file=myfeed_path)
    original_episodes = [
        Episode(
            myfeed,
            title="Repeated title",
            description="First original description",
            enclosure="https://example.com/first.mp3",
            guid="shared-guid",
        ),
        Episode(
            myfeed,
            title="Repeated title",
            description="Second original description",
            enclosure="https://example.com/second.mp3",
            guid="shared-guid",
        ),
    ]
    mydatabase.replace_feed(myfeed)
    mydatabase.replace_episodes(myfeed, original_episodes)

    stored_episodes = mydatabase.episodes(myfeed)
    original_episode_ids = {
        episode.enclosure: episode.ep_id for episode in stored_episodes
    }
    mydatabase.replace_progress(stored_episodes[0], 42000)
    mydatabase.replace_progress(stored_episodes[1], 84000)

    myqueue = Queue(display)
    player = mock.MagicMock(spec=Player)
    player.episode = stored_episodes[1]
    myqueue.add(player)
    mydatabase.replace_queue(myqueue)

    Config.data["retain_absent_episodes"] = "True"
    Config.data["max_episodes"] = "-1"

    for _ in range(2):
        reloaded_feed = Feed(file=myfeed_path)
        reloaded_feed.parse_episodes = mock.MagicMock(
            return_value=[
                Episode(
                    reloaded_feed,
                    title="Repeated title",
                    description="First updated description",
                    enclosure="https://example.com/first.mp3",
                    guid="shared-guid",
                ),
                Episode(
                    reloaded_feed,
                    title="Repeated title",
                    description="Second updated description",
                    enclosure="https://example.com/second.mp3",
                    guid="shared-guid",
                ),
            ]
        )
        mydatabase._reload_feed_data(myfeed, reloaded_feed)

    stored_episodes = mydatabase.episodes(myfeed)
    assert len(stored_episodes) == 2
    reloaded_episodes = {
        episode.enclosure: episode for episode in stored_episodes
    }
    assert len(reloaded_episodes) == 2
    assert {
        enclosure: episode.ep_id
        for enclosure, episode in reloaded_episodes.items()
    } == original_episode_ids
    assert reloaded_episodes["https://example.com/first.mp3"].progress == 42000
    assert (
        reloaded_episodes["https://example.com/second.mp3"].progress == 84000
    )
    assert [episode.ep_id for episode in mydatabase.queue()] == [
        original_episode_ids["https://example.com/second.mp3"]
    ]


def test_database_reload_matches_duplicate_titles_by_guid(display):
    mydatabase = display.database
    myfeed_path = my_dir + "/feeds/valid_basic.xml"
    myfeed = Feed(file=myfeed_path)
    original_episodes = [
        Episode(
            myfeed,
            title="Repeated title",
            enclosure="https://example.com/old-a.mp3",
            guid="guid-a",
        ),
        Episode(
            myfeed,
            title="Repeated title",
            enclosure="https://example.com/old-b.mp3",
            guid="guid-b",
        ),
    ]
    mydatabase.replace_feed(myfeed)
    mydatabase.replace_episodes(myfeed, original_episodes)
    stored_episodes = mydatabase.episodes(myfeed)
    original_episode_ids = {
        episode.guid: episode.ep_id for episode in stored_episodes
    }
    mydatabase.replace_progress(stored_episodes[0], 111)
    mydatabase.replace_progress(stored_episodes[1], 222)
    mydatabase.replace_download(stored_episodes[1], "example/old-b.mp3", "a" * 64)

    player = mock.MagicMock(spec=Player)
    player.episode = stored_episodes[1]
    queue = Queue(display)
    queue.add(player)
    mydatabase.replace_queue(queue)

    reloaded_feed = Feed(file=myfeed_path)
    reloaded_feed.parse_episodes = mock.MagicMock(
        return_value=[
            Episode(
                reloaded_feed,
                title="Repeated title",
                enclosure="https://example.com/new-b.mp3",
                guid="guid-b",
            ),
            Episode(
                reloaded_feed,
                title="Repeated title",
                enclosure="https://example.com/new-a.mp3",
                guid="guid-a",
            ),
        ]
    )

    mydatabase._reload_feed_data(myfeed, reloaded_feed)

    reloaded_episodes = {
        episode.guid: episode for episode in mydatabase.episodes(reloaded_feed)
    }
    assert {guid: episode.ep_id for guid, episode in reloaded_episodes.items()} == (
        original_episode_ids
    )
    assert reloaded_episodes["guid-a"].progress == 111
    assert reloaded_episodes["guid-b"].progress == 222
    assert reloaded_episodes["guid-a"].enclosure == "https://example.com/new-a.mp3"
    assert reloaded_episodes["guid-b"].enclosure == "https://example.com/new-b.mp3"
    assert reloaded_episodes["guid-b"].download_path == "example/old-b.mp3"
    assert [episode.ep_id for episode in mydatabase.queue()] == [
        original_episode_ids["guid-b"]
    ]


def test_database_reload_backfills_guid_through_enclosure_match(display):
    mydatabase = display.database
    myfeed_path = my_dir + "/feeds/valid_basic.xml"
    myfeed = Feed(file=myfeed_path)
    episode = Episode(
        myfeed,
        title="Legacy episode",
        enclosure="https://example.com/episode.mp3",
    )
    mydatabase.replace_feed(myfeed)
    mydatabase.replace_episode(myfeed, episode)
    original_id = episode.ep_id
    mydatabase.replace_progress(episode, 123)

    reloaded_feed = Feed(file=myfeed_path)
    reloaded_feed.parse_episodes = mock.MagicMock(
        return_value=[
            Episode(
                reloaded_feed,
                title="Renamed episode",
                enclosure="https://example.com/episode.mp3",
                guid="new-guid",
            )
        ]
    )

    mydatabase._reload_feed_data(myfeed, reloaded_feed)

    reloaded_episode = mydatabase.episodes(reloaded_feed)[0]
    assert reloaded_episode.ep_id == original_id
    assert reloaded_episode.guid == "new-guid"
    assert reloaded_episode.progress == 123


def test_database_reload_does_not_match_conflicting_guids(display):
    mydatabase = display.database
    myfeed_path = my_dir + "/feeds/valid_basic.xml"
    myfeed = Feed(file=myfeed_path)
    original_episode = Episode(
        myfeed,
        title="Episode",
        enclosure="https://example.com/episode.mp3",
        guid="old-guid",
    )
    mydatabase.replace_feed(myfeed)
    mydatabase.replace_episode(myfeed, original_episode)
    original_id = original_episode.ep_id
    mydatabase.replace_progress(original_episode, 123)
    mydatabase.replace_download(original_episode, "example/episode.mp3", "a" * 64)

    player = mock.MagicMock(spec=Player)
    player.episode = original_episode
    queue = Queue(display)
    queue.add(player)
    mydatabase.replace_queue(queue)

    reloaded_feed = Feed(file=myfeed_path)
    reloaded_feed.parse_episodes = mock.MagicMock(
        return_value=[
            Episode(
                reloaded_feed,
                title="Episode",
                enclosure="https://example.com/episode.mp3",
                guid="new-guid",
            )
        ]
    )
    Config.data["retain_absent_episodes"] = "False"

    mydatabase._reload_feed_data(myfeed, reloaded_feed)

    reloaded_episode = mydatabase.episodes(reloaded_feed)[0]
    assert reloaded_episode.ep_id != original_id
    assert reloaded_episode.guid == "new-guid"
    assert reloaded_episode.progress == 0
    assert reloaded_episode.download_path is None
    assert mydatabase.queue() == []


def test_database_reload_disambiguates_duplicate_enclosures_by_title(display):
    mydatabase = display.database

    myfeed_path = my_dir + "/feeds/valid_basic.xml"
    myfeed = Feed(file=myfeed_path)
    shared_enclosure = "https://example.com/shared.mp3"
    original_episodes = [
        Episode(
            myfeed,
            title="Episode A",
            description="Episode A description",
            enclosure=shared_enclosure,
        ),
        Episode(
            myfeed,
            title="Episode B",
            description="Original Episode B description",
            enclosure=shared_enclosure,
        ),
    ]
    mydatabase.replace_feed(myfeed)
    mydatabase.replace_episodes(myfeed, original_episodes)

    stored_episodes = mydatabase.episodes(myfeed)
    original_episode_ids = {
        episode.title: episode.ep_id for episode in stored_episodes
    }
    mydatabase.replace_progress(stored_episodes[0], 111)
    mydatabase.replace_progress(stored_episodes[1], 222)

    myqueue = Queue(display)
    player = mock.MagicMock(spec=Player)
    player.episode = stored_episodes[1]
    myqueue.add(player)
    mydatabase.replace_queue(myqueue)

    reloaded_feed = Feed(file=myfeed_path)
    reloaded_feed.parse_episodes = mock.MagicMock(
        return_value=[
            Episode(
                reloaded_feed,
                title="Episode B",
                description="Updated Episode B description",
                enclosure=shared_enclosure,
            )
        ]
    )
    Config.data["retain_absent_episodes"] = "True"
    Config.data["max_episodes"] = "-1"

    mydatabase._reload_feed_data(myfeed, reloaded_feed)

    retained_episodes = {
        episode.title: episode for episode in mydatabase.episodes(reloaded_feed)
    }
    assert set(retained_episodes) == {"Episode A", "Episode B"}
    assert retained_episodes["Episode A"].ep_id == original_episode_ids["Episode A"]
    assert retained_episodes["Episode A"].progress == 111
    assert retained_episodes["Episode B"].ep_id == original_episode_ids["Episode B"]
    assert retained_episodes["Episode B"].progress == 222
    assert retained_episodes["Episode B"].description == "Updated Episode B description"
    assert [episode.ep_id for episode in mydatabase.queue()] == [
        original_episode_ids["Episode B"]
    ]


def test_database_reload_does_not_reuse_remaining_duplicate_enclosure(display):
    mydatabase = display.database

    myfeed_path = my_dir + "/feeds/valid_basic.xml"
    myfeed = Feed(file=myfeed_path)
    shared_enclosure = "https://example.com/shared.mp3"
    original_episodes = [
        Episode(myfeed, title="Episode A", enclosure=shared_enclosure),
        Episode(myfeed, title="Episode B", enclosure=shared_enclosure),
    ]
    mydatabase.replace_feed(myfeed)
    mydatabase.replace_episodes(myfeed, original_episodes)

    stored_episodes = mydatabase.episodes(myfeed)
    original_episode_ids = {
        episode.title: episode.ep_id for episode in stored_episodes
    }
    mydatabase.replace_progress(stored_episodes[1], 222)

    myqueue = Queue(display)
    player = mock.MagicMock(spec=Player)
    player.episode = stored_episodes[1]
    myqueue.add(player)
    mydatabase.replace_queue(myqueue)

    reloaded_feed = Feed(file=myfeed_path)
    reloaded_feed.parse_episodes = mock.MagicMock(
        return_value=[
            Episode(
                reloaded_feed,
                title="Episode A",
                enclosure=shared_enclosure,
            ),
            Episode(
                reloaded_feed,
                title="Episode C",
                enclosure=shared_enclosure,
            ),
        ]
    )
    Config.data["retain_absent_episodes"] = "True"
    Config.data["max_episodes"] = "-1"

    mydatabase._reload_feed_data(myfeed, reloaded_feed)

    retained_episodes = {
        episode.title: episode
        for episode in mydatabase.episodes(reloaded_feed)
    }
    assert set(retained_episodes) == {"Episode A", "Episode B", "Episode C"}
    assert (
        retained_episodes["Episode A"].ep_id
        == original_episode_ids["Episode A"]
    )
    assert (
        retained_episodes["Episode B"].ep_id
        == original_episode_ids["Episode B"]
    )
    assert retained_episodes["Episode B"].progress == 222
    assert (
        retained_episodes["Episode C"].ep_id
        not in original_episode_ids.values()
    )
    assert retained_episodes["Episode C"].progress == 0
    assert [episode.ep_id for episode in mydatabase.queue()] == [
        original_episode_ids["Episode B"]
    ]


def test_database_reload_does_not_reuse_remaining_duplicate_title(display):
    mydatabase = display.database

    myfeed_path = my_dir + "/feeds/valid_basic.xml"
    myfeed = Feed(file=myfeed_path)
    original_episodes = [
        Episode(
            myfeed,
            title="Repeated title",
            enclosure="https://example.com/a.mp3",
        ),
        Episode(
            myfeed,
            title="Repeated title",
            enclosure="https://example.com/b.mp3",
        ),
    ]
    mydatabase.replace_feed(myfeed)
    mydatabase.replace_episodes(myfeed, original_episodes)

    stored_episodes = mydatabase.episodes(myfeed)
    original_episode_ids = {
        episode.enclosure: episode.ep_id for episode in stored_episodes
    }
    mydatabase.replace_progress(stored_episodes[1], 222)
    mydatabase.replace_download(
        stored_episodes[1], "example/b.mp3", "a" * 64
    )

    myqueue = Queue(display)
    player = mock.MagicMock(spec=Player)
    player.episode = stored_episodes[1]
    myqueue.add(player)
    mydatabase.replace_queue(myqueue)

    reloaded_feed = Feed(file=myfeed_path)
    reloaded_feed.parse_episodes = mock.MagicMock(
        return_value=[
            Episode(
                reloaded_feed,
                title="Repeated title",
                enclosure="https://example.com/a.mp3",
            ),
            Episode(
                reloaded_feed,
                title="Repeated title",
                enclosure="https://example.com/c.mp3",
            ),
        ]
    )
    Config.data["retain_absent_episodes"] = "True"
    Config.data["max_episodes"] = "-1"

    mydatabase._reload_feed_data(myfeed, reloaded_feed)

    retained_episodes = {
        episode.enclosure: episode
        for episode in mydatabase.episodes(reloaded_feed)
    }
    assert set(retained_episodes) == {
        "https://example.com/a.mp3",
        "https://example.com/b.mp3",
        "https://example.com/c.mp3",
    }
    assert (
        retained_episodes["https://example.com/a.mp3"].ep_id
        == original_episode_ids["https://example.com/a.mp3"]
    )
    assert (
        retained_episodes["https://example.com/b.mp3"].ep_id
        == original_episode_ids["https://example.com/b.mp3"]
    )
    assert retained_episodes["https://example.com/b.mp3"].progress == 222
    assert (
        retained_episodes["https://example.com/b.mp3"].download_path
        == "example/b.mp3"
    )
    assert (
        retained_episodes["https://example.com/c.mp3"].ep_id
        not in original_episode_ids.values()
    )
    assert retained_episodes["https://example.com/c.mp3"].progress == 0
    assert retained_episodes["https://example.com/c.mp3"].download_path is None
    assert [episode.ep_id for episode in mydatabase.queue()] == [
        original_episode_ids["https://example.com/b.mp3"]
    ]


def test_database_reload_preserves_exact_duplicates(display):
    mydatabase = display.database

    myfeed_path = my_dir + "/feeds/valid_basic.xml"
    myfeed = Feed(file=myfeed_path)
    original_episodes = [
        Episode(
            myfeed,
            title="Repeated episode",
            description="Repeated description",
            enclosure="https://example.com/shared.mp3",
        )
        for _ in range(2)
    ]
    mydatabase.replace_feed(myfeed)
    mydatabase.replace_episodes(myfeed, original_episodes)

    stored_episodes = mydatabase.episodes(myfeed)
    original_episode_ids = [episode.ep_id for episode in stored_episodes]
    mydatabase.replace_progress(stored_episodes[0], 111)
    mydatabase.replace_progress(stored_episodes[1], 222)

    reloaded_feed = Feed(file=myfeed_path)
    reloaded_feed.parse_episodes = mock.MagicMock(
        return_value=[
            Episode(
                reloaded_feed,
                title="Repeated episode",
                description="Repeated description",
                enclosure="https://example.com/shared.mp3",
            )
            for _ in range(2)
        ]
    )
    Config.data["retain_absent_episodes"] = "True"
    Config.data["max_episodes"] = "-1"

    mydatabase._reload_feed_data(myfeed, reloaded_feed)

    retained_episodes = mydatabase.episodes(reloaded_feed)
    retained_episode_ids = [episode.ep_id for episode in retained_episodes]
    assert retained_episode_ids == original_episode_ids
    assert [episode.progress for episode in retained_episodes] == [111, 222]


def test_database_replace_queue(display):
    copyfile(my_dir + "/datafiles/database_example1.db", Database.PATH)
    mydatabase = Database()

    assert len(mydatabase.queue()) == 0

    myqueue = Queue(display)
    player1 = mock.MagicMock(spec=Player)
    feed = mydatabase.feeds()[0]
    episode = mydatabase.episodes(feed)[0]
    player1.episode = episode
    myqueue.add(player1)

    mydatabase.replace_queue(myqueue)
    assert len(mydatabase.queue()) == 1


def test_database_delete_queue(display):
    copyfile(my_dir + "/datafiles/database_example1.db", Database.PATH)
    mydatabase = Database()

    myqueue = Queue(display)
    player1 = mock.MagicMock(spec=Player)
    feed = mydatabase.feeds()[0]
    episode = mydatabase.episodes(feed)[0]
    player1.episode = episode
    myqueue.add(player1)

    mydatabase.replace_queue(myqueue)
    assert len(mydatabase.queue()) == 1
    mydatabase.delete_queue()
    assert len(mydatabase.queue()) == 0


def test_database_replace_queue_with_deleted_episode(display):
    copyfile(my_dir + "/datafiles/database_example1.db", Database.PATH)
    mydatabase = Database()

    myqueue = Queue(display)
    player1 = mock.MagicMock(spec=Player)
    feed = mydatabase.feeds()[0]
    episode = mydatabase.episodes(feed)[0]
    player1.episode = episode
    myqueue.add(player1)

    mydatabase.delete_feed(feed)
    mydatabase.replace_queue(myqueue)
    assert len(mydatabase.queue()) == 0


def test_database_from_json(prevent_modification):
    copyfile(my_dir + "/datafiles/feeds_working", Database.OLD_PATH)
    mydatabase = Database()

    feeds = mydatabase.feeds()
    assert len(feeds) == 2

    # we don't technically make any assumptions about the order of the feeds
    if feeds[0].key != "feed key":
        feeds.reverse()

    assert feeds[0].key == "feed key"
    assert feeds[0].title == "feed title"
    assert feeds[0].description == "feed description"
    assert feeds[0].link == "feed link"
    assert feeds[0].last_build_date == "feed last_build_date"
    assert feeds[0].copyright == "feed copyright"
    episodes0 = mydatabase.episodes(feeds[0])
    assert episodes0[0].title == "episode title"
    assert episodes0[0].description == "episode description"
    assert episodes0[0].link == "episode link"
    assert episodes0[0].pubdate == "episode pubdate"
    assert episodes0[0].copyright == "episode copyright"
    assert episodes0[0].enclosure == "episode enclosure"
    assert not episodes0[0].played

    assert feeds[1].key == "http://feed2_url"
    assert feeds[1].title == "feed2 title"
    assert feeds[1].description == "feed2 description"
    assert feeds[1].link == "feed2 link"
    assert feeds[1].last_build_date == "feed2 last_build_date"
    assert feeds[1].copyright == "feed2 copyright"
    episodes1 = mydatabase.episodes(feeds[1])
    assert episodes1[0].title == "episode title"
    assert episodes1[0].description == "episode description"
    assert episodes1[0].link == "episode link"
    assert episodes1[0].pubdate == "episode pubdate"
    assert episodes1[0].copyright == "episode copyright"
    assert episodes1[0].enclosure == "episode enclosure"
    assert not episodes1[0].played
