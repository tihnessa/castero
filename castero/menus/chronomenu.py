import curses

from castero.episode import Episode
from castero.feed import Feed
from castero.menu import Menu
from castero import helpers


class ChronoMenu(Menu):
    """The menu for all episodes in chronological order."""

    def __init__(self, window, source, child=None, active=False, workers=None) -> None:
        super().__init__(window, source, child=child, active=active)

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
                    "text": "[%s] %s" % (episode.feed_str, str(episode)),
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

    def update_items(self, obj):
        """Called by the parent menu(the feeds menu) to update our items."""
        super().update_items(obj)
        self._request_generation += 1
        generation = self._request_generation

        if self._workers is None:
            self._request_source_episodes()
        else:
            self._workers.submit(
                self._load_source_episodes,
                self._inverted,
                self._workers.cancel_event,
                on_result=lambda episodes: self._apply_source_episodes(
                    generation, episodes
                ),
            )

        self._sanitize()

    def _request_source_episodes(self):
        episodes = self._load_source_episodes(self._inverted)
        self._apply_source_episodes(self._request_generation, episodes)

    def _load_source_episodes(self, inverted, cancel_event=None):
        episodes = self._source.episodes()
        if cancel_event is not None and cancel_event.is_set():
            return None
        return sorted(
            episodes,
            reverse=not inverted,
            key=lambda ep: helpers.datetime_from_rfc822(ep.pubdate),
        )

    def _apply_source_episodes(self, generation, episodes):
        if episodes is not None and generation == self._request_generation:
            self._episodes = episodes
            self._sanitize()
            self.display()

    def update_child(self):
        """Not necessary for this menu - - does nothing."""
        pass

    def invert(self):
        """Invert the menu order."""
        super().invert()

        self.update_items(None)

    @property
    def _filtered_episodes(self):
        """A list of episodes which match the menu filter."""
        return list(filter(lambda ep: self._filter_text in str(ep).lower(), self._episodes))
