"""
Audio Converter Pro
Queue state (single source of truth for files awaiting conversion).

A lock guards the list because conversion runs on a background thread
(so the UI doesn't freeze) while the main thread reads/iterates the
same list to update the table — without it, the two can race and
occasionally corrupt iteration or read a half-written status.
"""

import threading


class QueueManager:

    def __init__(self):
        self._items = []
        self._lock = threading.Lock()

    def add(self, path):
        item = {"path": path, "status": "Waiting", "error": None}
        with self._lock:
            self._items.append(item)
        return item

    def contains(self, path) -> bool:
        with self._lock:
            return any(item["path"] == path for item in self._items)

    def set_status(self, path, status, error=None):
        with self._lock:
            for item in self._items:
                if item["path"] == path:
                    item["status"] = status
                    item["error"] = error
                    return

    def remove(self, path):
        with self._lock:
            self._items = [item for item in self._items if item["path"] != path]

    def clear(self):
        with self._lock:
            self._items.clear()

    def reset_statuses(self):
        with self._lock:
            for item in self._items:
                item["status"] = "Waiting"
                item["error"] = None

    def snapshot(self):
        """A shallow copy safe to iterate outside the lock."""
        with self._lock:
            return [dict(item) for item in self._items]

    def __len__(self):
        with self._lock:
            return len(self._items)

    def __iter__(self):
        return iter(self.snapshot())
