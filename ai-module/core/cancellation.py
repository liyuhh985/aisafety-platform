import threading


class StreamCancelled(Exception):
    """Raised when a client closes a streaming response."""


class CancellationToken:
    def __init__(self):
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._closers = set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        with self._lock:
            if self._event.is_set():
                return
            self._event.set()
            closers = list(self._closers)
            self._closers.clear()
        for closer in closers:
            try:
                closer()
            except Exception:
                pass

    def register(self, closer) -> None:
        with self._lock:
            if not self._event.is_set():
                self._closers.add(closer)
                return
        try:
            closer()
        except Exception:
            pass

    def unregister(self, closer) -> None:
        with self._lock:
            self._closers.discard(closer)

    def throw_if_cancelled(self) -> None:
        if self.is_cancelled():
            raise StreamCancelled()
