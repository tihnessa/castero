import os
import sys
from unittest import mock

import pytest

from castero.episode import Episode
from castero.feed import Feed
from castero.players.vlcplayer import VLCPlayer
from castero.player import PlayerDependencyError

my_dir = os.path.dirname(os.path.realpath(__file__))

feed = Feed(file=my_dir + "/feeds/valid_basic.xml")
episode = Episode(
    feed,
    title="episode title",
    description="episode description",
    link="episode link",
    pubdate="episode pubdate",
    copyright="episode copyright",
    enclosure="episode enclosure",
)


@pytest.fixture(autouse=True)
def mock_vlc_binding(monkeypatch):
    """Keep unit tests independent of the native libVLC installation."""
    monkeypatch.setitem(sys.modules, "vlc", mock.MagicMock())


def test_player_vlc_check_dependencies():
    vlc = mock.MagicMock()
    with mock.patch.dict(sys.modules, {"vlc": vlc}):
        VLCPlayer.check_dependencies()
    vlc.libvlc_release.assert_called_once_with(vlc.Instance.return_value)


def test_player_vlc_check_dependencies_reports_missing_binding():
    with mock.patch.dict(sys.modules, {"vlc": None}):
        with pytest.raises(PlayerDependencyError, match="python-vlc"):
            VLCPlayer.check_dependencies()


def test_player_vlc_check_dependencies_reports_native_library_error():
    vlc = mock.MagicMock()
    vlc.Instance.side_effect = OSError("libvlc could not be loaded")

    with mock.patch.dict(sys.modules, {"vlc": vlc}):
        with pytest.raises(PlayerDependencyError, match="libvlc could not be loaded"):
            VLCPlayer.check_dependencies()


def test_player_vlc_init():
    myplayer = VLCPlayer("player1 title", "player1 path", episode)
    assert isinstance(myplayer, VLCPlayer)


def test_player_vlc_play():
    myplayer = VLCPlayer("player1 title", "player1 path", episode)
    myplayer._player = mock.MagicMock()

    myplayer.play()
    assert myplayer._player.play.call_count == 1
    assert myplayer.state == 1


def test_player_vlc_pause():
    myplayer = VLCPlayer("player1 title", "player1 path", episode)
    myplayer._player = mock.MagicMock()

    myplayer.pause()
    assert myplayer._player.pause.call_count == 1
    assert myplayer.state == 2


def test_player_vlc_stop():
    myplayer = VLCPlayer("player1 title", "player1 path", episode)
    myplayer._player = mock.MagicMock()

    myplayer.stop()
    assert myplayer._player.stop.call_count == 1
    assert myplayer.state == 0


def test_player_vlc_del():
    myplayer = VLCPlayer("player1 title", "player1 path", episode)
    assert "myplayer" in locals()
    del myplayer
    assert "myplayer" not in locals()


def test_player_vlc_seek():
    myplayer = VLCPlayer("player1 title", "player1 path", episode)
    myplayer._player = mock.MagicMock()

    myplayer.seek(1, 10)
    myplayer._player.set_time.assert_called_with(myplayer._player.get_time() + 10 * 1000)


def test_player_vlc_play_from():
    myplayer = VLCPlayer("player1 title", "player1 path", episode)
    myplayer._player = mock.MagicMock()
    myplayer.play_from(10)

    assert myplayer._player.play.call_count == 1
    assert myplayer.state == 1
    myplayer._player.set_time.assert_called_with(10 * 1000)


def test_player_vlc_change_rate_increase():
    myplayer = VLCPlayer("player1 title", "player1 path", episode)
    myplayer._player = mock.MagicMock()

    myplayer.set_rate(1.6)
    assert myplayer._player.set_rate.call_count == 1


def test_player_vlc_str():
    myplayer = VLCPlayer("player1 title", "player1 path", episode)
    assert str(myplayer) == "[%s] %s" % (episode.feed_str, myplayer.title)


def test_player_vlc_title():
    myplayer = VLCPlayer("player1 title", "player1 path", episode)
    assert myplayer.title == "player1 title"


def test_player_vlc_episode():
    myplayer = VLCPlayer("player1 title", "player1 path", episode)
    assert myplayer.episode == episode


def test_player_vlc_time():
    myplayer = VLCPlayer("player1 title", "player1 path", episode)
    myplayer._player = mock.MagicMock()

    myplayer._player.get_time = mock.MagicMock(return_value=5000)
    assert myplayer.time == 5000


def test_player_vlc_time_str():
    myplayer = VLCPlayer("player1 title", "player1 path", episode)
    myplayer._player = mock.MagicMock()
    myplayer._media = mock.MagicMock()

    myplayer._player.get_time = mock.MagicMock(return_value=3000)
    myplayer._media.get_duration = mock.MagicMock(return_value=6000)
    assert myplayer.time_str == "00:00:03/00:00:06"
