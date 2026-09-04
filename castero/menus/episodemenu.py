import curses

from castero.episode import Episode
from castero.feed import Feed
from castero.menu import Menu
from castero import helpers


class EpisodeMenu(Menu):
    """The menu for episodes in a feed."""

    def __init__(self, window, source, child=None, active=False, workers=None) -> None:
        super().__init__(window, source, child=child, active=active)

        self._feed = None
        self._episodes = []
        self._workers = workers
        self._request_generation = 0

    def __len__(self) -> int:
        return len(self._filtered_episodes)

    @property
    def _items(self):
        """A list of items in the menu represented as dictionaries."""
        result = []
        for episode in self._filtered_episodes:
            tags = []
            if episode.downloaded:
                tags.append("D")
            if episode.progress > 0:
                tags.append(Episode.PROGRESS_INDICATOR)

            result.append(
                {
                    "attr": curses.color_pair(5) if episode.played else curses.A_NORMAL,
                    "tags": tags,
                    "text": str(episode),
                }
            )
        return result

    @property
    def title(self) -> str:
        """The title of the menu to display in the window header."""
        base = "Episodes"
        if len(self._filtered_episodes) > 0:
            unplayed_episodes = 0
            for episode in self._filtered_episodes:
                if not episode.played:
                    unplayed_episodes += 1

            return "%s (%d/%d)" % (base, unplayed_episodes, len(self._filtered_episodes))
        return base

    @property
    def item(self) -> Episode:
        """The selected episode."""
        if len(self._filtered_episodes) == 0:
            return None

        return self._filtered_episodes[self._selected]

    @property
    def metadata(self) -> str:
        """Metadata for the selected episode."""
        if len(self._filtered_episodes) == 0:
            return ""

        return self._filtered_episodes[self._selected].metadata

    def update_items(self, feed):
        """Called by the parent menu (the feeds menu) to update our items."""
        assert isinstance(feed, Feed) or feed is None

        super().update_items(feed)

        self._feed = feed
        self._request_generation += 1
        generation = self._request_generation

        if feed is None:
            self._episodes = []
        elif self._workers is None:
            self._request_source_episodes(feed)
        else:
            self._workers.submit(
                self._load_source_episodes,
                feed,
                self._inverted,
                self._workers.cancel_event,
                on_result=lambda episodes: self._apply_source_episodes(
                    feed, generation, episodes
                ),
            )

        self._sanitize()

    def _request_source_episodes(self, feed):
        episodes = self._load_source_episodes(feed, self._inverted)
        self._apply_source_episodes(feed, self._request_generation, episodes)

    def _load_source_episodes(self, feed, inverted, cancel_event=None):
        episodes = self._source.episodes(feed)
        if cancel_event is not None and cancel_event.is_set():
            return None
        return sorted(
            episodes,
            reverse=not inverted,
            key=lambda ep: helpers.datetime_from_rfc822(ep.pubdate),
        )

    def _apply_source_episodes(self, feed, generation, episodes):
        # The load may have taken some time; ignore results for an old request.
        if episodes is not None and self._feed == feed and generation == self._request_generation:
            self._episodes = episodes

            self._sanitize()
            self.display()

    def update_child(self):
        """Not necessary for this menu -- does nothing."""
        pass

    def invert(self):
        """Invert the menu order."""
        super().invert()

        self.update_items(self._feed)

    @property
    def _filtered_episodes(self):
        """A list of episodes which match the menu filter."""
        return list(filter(lambda ep: self._filter_text in str(ep).lower(), self._episodes))
