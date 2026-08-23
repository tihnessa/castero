import os
import sqlite3
from shutil import copyfile
from unittest import mock

from castero.episode import Episode
from castero.feed import Feed
from castero.database import Database
from castero.config import Config
from castero.queue import Queue
from castero.player import Player

my_dir = os.path.dirname(os.path.realpath(__file__))


def test_database_default(prevent_modification):
    mydatabase = Database()
    assert isinstance(mydatabase, Database)


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
        ),
        Episode(
            myfeed,
            title="Repeated title",
            description="Second original description",
            enclosure="https://example.com/second.mp3",
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
                ),
                Episode(
                    reloaded_feed,
                    title="Repeated title",
                    description="Second updated description",
                    enclosure="https://example.com/second.mp3",
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
