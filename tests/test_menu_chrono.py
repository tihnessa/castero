from unittest import mock

from castero.episode import Episode
from castero.menus.chronomenu import ChronoMenu


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
