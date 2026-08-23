from unittest import mock

from castero.feed import Feed
from castero.menus.episodemenu import EpisodeMenu
from castero.menus.feedmenu import FeedMenu


window = mock.MagicMock()
window.getmaxyx.return_value = (40, 80)


def create_feed(title, metadata):
    feed = mock.MagicMock(spec=Feed)
    feed.__str__.return_value = title
    feed.metadata = metadata
    return feed


def create_menu(feeds, filter_text):
    source = mock.MagicMock()
    source.feeds.return_value = feeds
    child = mock.MagicMock(spec=EpisodeMenu)
    menu = FeedMenu(window, source, child=child)
    menu.display = mock.MagicMock()
    menu.filter_text = filter_text
    menu.update_items(None)
    return menu, child


def test_menu_feed_filter_aligns_rendering_selection_metadata_and_child():
    alpha = create_feed("Alpha", "Alpha metadata")
    beta = create_feed("Beta", "Beta metadata")

    menu, child = create_menu([alpha, beta], "beta")

    assert len(menu) == 1
    assert [item["text"] for item in menu._items] == ["Beta"]
    assert menu.item is beta
    assert menu.metadata == "Beta metadata"

    menu.update_child()
    child.update_items.assert_called_once_with(beta)


def test_menu_feed_filter_is_case_insensitive():
    alpha = create_feed("Alpha", "Alpha metadata")
    beta = create_feed("Beta", "Beta metadata")

    menu, _child = create_menu([alpha, beta], "BETA")

    assert len(menu) == 1
    assert [item["text"] for item in menu._items] == ["Beta"]
    assert menu.item is beta
