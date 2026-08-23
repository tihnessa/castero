import curses
import os
from unittest import mock

import pytest

import castero
from castero.display import Display, DisplaySizeError
from castero.feed import Feed
from castero.episode import Episode

my_dir = os.path.dirname(os.path.realpath(__file__))


def test_display_init(display):
    assert isinstance(display, Display)
    display._stdscr.reset_mock()


def test_display_display_header(display):
    disp = display
    disp.display()
    args, kwargs = display._header_window.addstr.call_args
    assert castero.__title__ in args[2]
    disp._stdscr.reset_mock()


def test_display_display_footer_empty(display):
    display.display()
    args, kwargs = display._footer_window.addstr.call_args
    assert "Press h for help" in args[2]


def test_display_display_borders(display):
    display.display()
    assert display._header_window.hline.call_count == 1
    assert display._footer_window.hline.call_count == 1
    display._stdscr.reset_mock()


def test_display_help(display):
    display._stdscr.reset_mock()
    display.show_help()
    assert display._stdscr.refresh.call_count >= 2


def test_display_refresh(display):
    display._stdscr.reset_mock()
    display.refresh()
    assert display._stdscr.refresh.call_count == 1


def test_display_get_input_str(display):
    display._footer_window.getch = mock.Mock()
    display._footer_window.getch.side_effect = [ord("a"), ord("b"), 10]
    display._get_input_str("prompt")
    assert display._footer_window.getch.call_count == 3
    assert display._footer_window.clear.call_count == 1
    assert display._footer_window.addstr.call_count == 2
    display._footer_window.addstr.assert_any_call(1, 0, "prompt")
    display._footer_window.getch.assert_has_calls([mock.call(), mock.call(), mock.call()])


def test_display_get_y_n(display):
    display._get_y_n("prompt")
    assert display._footer_window.clear.call_count == 1
    assert display._footer_window.addstr.call_count == 2
    display._footer_window.addstr.assert_any_call(1, 0, "prompt")
    display._footer_window.getch.assert_called_once_with()


def test_display_input_keys(display):
    for perspective_id in display.perspectives:
        perspective = display.perspectives[perspective_id]
        perspective.handle_input = mock.MagicMock()
        display.handle_input(display.KEY_MAPPING[str(perspective_id)])
        assert perspective.handle_input.call_count == 1


def test_display_getch(display):
    display._stdscr.reset_mock()
    display.getch()
    assert display._stdscr.getch.call_count == 1


def test_display_update_status(display):
    display._status = ""
    display._status_timer = 0
    display.change_status("test status")
    assert display._status == "test status"
    assert display._status_timer == display.STATUS_TIMEOUT


def test_display_update(display):
    display._status = "test status"
    display._status_timer = 1
    display.update()
    assert display._status_timer == 0
    assert display._status == ""


def test_display_nonempty(display):
    myfeed = Feed(file=my_dir + "/feeds/valid_basic.xml")
    display.database.feeds = mock.MagicMock(return_value=[myfeed])
    display.menus_valid = False
    display.display()


def test_display_min_dimensions(display):
    display.display()
    display._stdscr.setmaxyx(100, Display.MIN_WIDTH - 1)
    with pytest.raises(DisplaySizeError):
        display.display()
    display._stdscr.setmaxyx(Display.MIN_HEIGHT - 1, 100)
    with pytest.raises(DisplaySizeError):
        display.display()


def test_display_add_feed(display):
    feed_dir = my_dir + "/feeds/valid_basic.xml"
    display._get_input_str = mock.MagicMock(return_value=feed_dir)
    display.add_feed()
    assert len(display.database.feeds()) == 1


def test_display_add_feed_errors(display):
    test_inputs = [
        "fake",
        "http://fake",
        my_dir + "/feeds/broken_is_rss.xml",
        my_dir + "/datafiles/parse_error.conf",
    ]
    for test_input in test_inputs:
        display._get_input_str = mock.MagicMock(return_value=test_input)
        display.add_feed()
        assert "Error" in display._status
        display._status = ""
        assert len(display.database.feeds()) == 0


def test_display_delete_feed(display):
    feed = Feed(
        url="feed url",
        title="feed title",
        description="feed description",
        link="feed link",
        last_build_date="feed last_build_date",
        copyright="feed copyright",
        episodes=[],
    )
    display.database.replace_feed(feed)
    assert len(display.database.feeds()) == 1
    display.delete_feed(feed)
    assert len(display.database.feeds()) == 0


def test_display_delete_feed_deletes_downloaded_episodes(display, tmp_path):
    feed = Feed(
        url="feed url",
        title="feed title",
        description="feed description",
        link="feed link",
        last_build_date="feed last_build_date",
        copyright="feed copyright",
        episodes=[],
    )
    episodes = [
        Episode(feed, title="episode one"),
        Episode(feed, title="episode two"),
    ]
    display.database.replace_feed(feed)
    for episode in episodes:
        display.database.replace_episode(feed, episode)

    castero.config.Config.data["custom_download_dir"] = str(tmp_path)
    feed_directory = tmp_path / "feed_title"
    feed_directory.mkdir()
    episode_files = [
        feed_directory / ("%s-episode.mp3" % episode.ep_id)
        for episode in episodes
    ]
    for episode_file in episode_files:
        episode_file.write_text("downloaded episode")

    display.delete_feed(feed)

    assert all(not episode_file.exists() for episode_file in episode_files)
    assert not feed_directory.exists()
    assert display.database.episodes(feed) == []
    assert display.database.feeds() == []


def test_display_delete_feed_removes_pending_download(display):
    feed = Feed(
        url="feed url",
        title="feed title",
        description="feed description",
        link="feed link",
        last_build_date="feed last_build_date",
        copyright="feed copyright",
        episodes=[],
    )
    episode = Episode(feed, title="queued episode", enclosure="episode.mp3")
    display.database.replace_feed(feed)
    display.database.replace_episode(feed, episode)
    episode.download = mock.MagicMock()
    display._download_queue.add(episode)

    display.delete_feed(feed)
    display._download_queue.update()

    assert display._download_queue.length == 0
    episode.download.assert_not_called()


def test_display_delete_feed_cancels_active_download(display):
    feed = Feed(url="feed url", title="feed title")
    episode = Episode(feed, title="active episode", enclosure="episode.mp3")
    display.database.replace_feed(feed)
    display.database.replace_episode(feed, episode)
    episode.download = mock.MagicMock()
    display._download_queue.add(episode)
    display._download_queue.start()

    display.delete_feed(feed)

    assert display._download_queue.length == 0
    assert display._download_queue.cancelled


def test_display_terminate_stops_downloads_before_closing_database(display):
    calls = mock.Mock()
    display._download_queue.stop = calls.stop_downloads
    display._queue.stop = calls.stop_players
    display.database.replace_queue = calls.replace_queue
    display.database.close = calls.close_database

    display.terminate()

    assert calls.method_calls == [
        mock.call.stop_downloads(),
        mock.call.stop_players(),
        mock.call.replace_queue(display._queue),
        mock.call.close_database(),
    ]


def test_display_execute_command(display):
    myfeed = Feed(file=my_dir + "/feeds/valid_basic.xml")
    myepisode = Episode(
        myfeed,
        title="episode title",
        description="episode description",
        link="episode link",
        pubdate="episode pubdate",
        copyright="episode copyright",
        enclosure="episode file",
    )
    castero.config.Config.data = {"execute_command": "player {file}"}

    with mock.patch("castero.display.subprocess.Popen") as popen:
        display.execute_command(myepisode)

    popen.assert_called_once_with("player episode file", shell=True)


def test_display_color_numbers(display):
    assert display.color_number("2") == 2
    assert display.color_number("3") == 3
    assert display.color_number(str(curses.COLORS)) == -1
