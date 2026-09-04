import threading

from castero.episode import Episode
from castero.workers import WorkerManager


class DownloadQueue:
    """A FIFO ordered queue for handling episode downloads."""

    def __init__(self, display=None, workers=None) -> None:
        self._episodes = []
        self._display = display
        self._owns_workers = workers is None
        self._workers = workers or WorkerManager(max_workers=1)
        self._current = None
        self._current_cancelled = False
        self._worker = None
        self._stopping = False
        self._lock = threading.RLock()

    @staticmethod
    def _matches(first, second) -> bool:
        """Return whether two objects represent the same episode."""
        return first is second or (
            first.ep_id is not None
            and second.ep_id is not None
            and first.ep_id == second.ep_id
        )

    def next(self) -> None:
        """Proceed to the next episode in the queue."""
        with self._lock:
            if self._current is None:
                if len(self._episodes) > 0:
                    self._episodes.pop(0)
            else:
                self._episodes = [
                    episode
                    for episode in self._episodes
                    if not self._matches(episode, self._current)
                ]
            self._current = None
            self._current_cancelled = False
            self._worker = None

        self.start()

    def add(self, episode) -> None:
        """Adds an episode to the end of the queue."""
        assert isinstance(episode, Episode)

        with self._lock:
            if self._stopping or self._workers.cancelled:
                return
            if episode not in self._episodes:
                self._episodes.append(episode)

    def remove(self, episode) -> None:
        """Removes an episode from the queue."""
        assert isinstance(episode, Episode)

        with self._lock:
            if self._current is not None and self._matches(self._current, episode):
                self._current_cancelled = True
            self._episodes = [
                queued_episode
                for queued_episode in self._episodes
                if not self._matches(queued_episode, episode)
            ]

    def start(self) -> None:
        """Start downloading the first episode in the queue."""
        with self._lock:
            if (
                self._stopping
                or self._workers.cancelled
                or self._current is not None
                or len(self._episodes) == 0
            ):
                return
            self._current = self._episodes[0]
            episode = self._current
            worker = self._workers.submit(episode.download, self, self._display)
            if self._current is episode:
                self._worker = worker
            if worker is None:
                self._current = None

    def finalize(self, callback) -> bool:
        """Run a download's final promotion while cancellation is excluded."""
        with self._lock:
            if self._stopping or self._current_cancelled:
                return False
            callback()
            return True

    def stop(self) -> None:
        """Cancel queued work and wait for the active download worker to exit."""
        with self._lock:
            self._stopping = True
            self._episodes = []
            if self._current is not None:
                self._current_cancelled = True
            worker = self._worker

        if worker is not None:
            try:
                worker.result()
            except Exception:
                pass

        with self._lock:
            if self._worker is worker:
                self._worker = None
            self._current = None

        if self._owns_workers:
            self._workers.shutdown()

    def update(self) -> None:
        """Checks the status of the current download."""
        with self._lock:
            should_start = self._current is None and len(self._episodes) > 0
        if should_start:
            self.start()

    @property
    def first(self) -> Episode:
        """Episode: the first episode in the queue"""
        with self._lock:
            if len(self._episodes) > 0:
                return self._episodes[0]
        return None

    @property
    def length(self) -> int:
        """int: the length of the queue"""
        with self._lock:
            return len(self._episodes)

    @property
    def cancelled(self) -> bool:
        """bool: whether the current download has been cancelled"""
        with self._lock:
            return self._current_cancelled or self._workers.cancelled
