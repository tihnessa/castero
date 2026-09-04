import concurrent.futures
from collections import deque
import threading


class WorkerManager:
    """Own background work and marshal its results to the creating thread."""

    def __init__(self, max_workers=4, error_handler=None) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be greater than zero")
        self._owner_thread = threading.get_ident()
        self._max_workers = max_workers
        self._error_handler = error_handler
        self._callbacks = deque()
        self._tasks = deque()
        self._cancel_event = threading.Event()
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._threads = []
        self._futures = set()
        self._keyed_futures = {}
        self._stopping = False

    @property
    def cancelled(self) -> bool:
        """Whether shutdown has requested cancellation of active work."""
        return self._cancel_event.is_set()

    @property
    def cancel_event(self):
        """The event background jobs should check for cooperative cancellation."""
        return self._cancel_event

    @property
    def on_owner_thread(self) -> bool:
        """Whether the caller is the thread which created this manager."""
        return threading.get_ident() == self._owner_thread

    def submit(self, target, *args, key=None, on_result=None, on_error=None, **kwargs):
        """Submit work unless shutdown or work with the same key is active."""
        with self._lock:
            if self._stopping or (key is not None and key in self._keyed_futures):
                return None

            future = concurrent.futures.Future()
            self._futures.add(future)
            if key is not None:
                self._keyed_futures[key] = future
            future.add_done_callback(
                lambda completed: self._complete(
                    completed,
                    key=key,
                    on_result=on_result,
                    on_error=on_error,
                )
            )
            self._tasks.append((future, target, args, kwargs))
            self._ensure_threads()
            self._condition.notify()
            return future

    def _ensure_threads(self) -> None:
        if self._threads:
            return
        for index in range(self._max_workers):
            thread = threading.Thread(
                target=self._work,
                name="castero-worker-%d" % index,
                daemon=True,
            )
            self._threads.append(thread)
            thread.start()

    def _work(self) -> None:
        while True:
            with self._condition:
                while not self._tasks and not self._stopping:
                    self._condition.wait()
                if self._stopping:
                    return
                future, target, args, kwargs = self._tasks.popleft()

            if not future.set_running_or_notify_cancel():
                continue
            try:
                result = target(*args, **kwargs)
            except BaseException as error:
                future.set_exception(error)
            else:
                future.set_result(result)

    def _complete(self, future, key=None, on_result=None, on_error=None) -> None:
        with self._lock:
            self._futures.discard(future)
            if key is not None and self._keyed_futures.get(key) is future:
                del self._keyed_futures[key]

        if future.cancelled():
            return
        try:
            result = future.result()
        except Exception as error:
            handler = on_error or self._error_handler
            if handler is not None:
                self.call_soon(handler, error)
        else:
            if on_result is not None:
                self.call_soon(on_result, result)

    def call_soon(self, callback, *args, **kwargs) -> bool:
        """Queue a callback for the owner thread, unless shutdown has begun."""
        with self._lock:
            if self._stopping:
                return False
            self._callbacks.append((callback, args, kwargs))
            return True

    def drain(self) -> int:
        """Run all queued callbacks on the owner thread."""
        if not self.on_owner_thread:
            raise RuntimeError("Worker callbacks must be drained on the owner thread")

        completed = 0
        while True:
            with self._lock:
                if not self._callbacks:
                    break
                callback, args, kwargs = self._callbacks.popleft()
            callback(*args, **kwargs)
            completed += 1
        return completed

    def cancel(self) -> None:
        """Reject new work and request cancellation of active work."""
        with self._condition:
            if self._stopping:
                return
            self._stopping = True
            self._cancel_event.set()
            pending = [task[0] for task in self._tasks]
            self._tasks.clear()
            self._condition.notify_all()

        for future in pending:
            future.cancel()

    def shutdown(self) -> None:
        """Cancel pending work, join running work, and discard UI callbacks."""
        self.cancel()
        for thread in self._threads:
            if thread is not threading.current_thread():
                thread.join()
        with self._lock:
            self._callbacks.clear()
