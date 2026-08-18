import os
from unittest import mock

from castero.downloadqueue import DownloadQueue
from castero.episode import Episode
from castero.feed import Feed

my_dir = os.path.dirname(os.path.realpath(__file__))

feed = Feed(file=my_dir + "/feeds/valid_basic.xml")
episode1 = Episode(feed=feed, title="episode1 title")
episode2 = Episode(feed=feed, title="episode2 title")


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
    second.download.assert_called_once_with(mydownloadqueue, None)


def test_downloadqueue_advances_past_episode_without_enclosure():
    mydownloadqueue = DownloadQueue()
    missing_enclosure = Episode(feed=feed, ep_id=1, title="missing enclosure")
    next_episode = Episode(feed=feed, ep_id=2, title="next episode")
    next_episode.download = mock.MagicMock()
    mydownloadqueue.add(missing_enclosure)
    mydownloadqueue.add(next_episode)

    mydownloadqueue.start()

    assert mydownloadqueue.length == 1
    next_episode.download.assert_called_once_with(mydownloadqueue, None)


def test_downloadqueue_start():
    mydownloadqueue = DownloadQueue()
    mydownloadqueue._display = mock.MagicMock()
    mydownloadqueue.add(episode1)
    episode1.download = mock.MagicMock(name="download")
    mydownloadqueue.start()
    episode1.download.assert_called_with(
        mydownloadqueue,
        mydownloadqueue._display,
    )


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
