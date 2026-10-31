import copy
import time
from collections import OrderedDict
import threading


class CachedEmbeddingEncoder:
    def __init__(self, model, max_size):
        if max_size < 0:
            raise ValueError("Embedding cache size cannot be negative")
        self.model = model
        self.max_size = max_size
        self.entries = OrderedDict()
        self.lock = threading.Lock()

    def encode(self, question):
        return self.encode_with_status(question)[0]

    def encode_with_status(self, question):
        with self.lock:
            if question in self.entries:
                self.entries.move_to_end(question)
                return self.entries[question], True

        embedding = self.model.encode(question)
        if self.max_size:
            with self.lock:
                self.entries[question] = embedding
                self.entries.move_to_end(question)
                while len(self.entries) > self.max_size:
                    self.entries.popitem(last=False)
        return embedding, False

    def cache_clear(self):
        with self.lock:
            self.entries.clear()


class TTLCache:
    def __init__(self, max_entries, ttl_seconds):
        if max_entries < 0 or ttl_seconds < 0:
            raise ValueError("Cache size and TTL cannot be negative")
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self.entries = OrderedDict()
        self.lock = threading.Lock()

    def get(self, key, now=None):
        current_time = time.monotonic() if now is None else now
        with self.lock:
            entry = self.entries.get(key)
            if entry is None:
                return False, None
            expires_at, value = entry
            if expires_at <= current_time:
                del self.entries[key]
                return False, None
            self.entries.move_to_end(key)
            return True, copy.deepcopy(value)

    def set(self, key, value, now=None):
        if self.max_entries == 0 or self.ttl_seconds == 0:
            return
        current_time = time.monotonic() if now is None else now
        with self.lock:
            self.entries[key] = (
                current_time + self.ttl_seconds,
                copy.deepcopy(value),
            )
            self.entries.move_to_end(key)
            while len(self.entries) > self.max_entries:
                self.entries.popitem(last=False)

    def clear(self):
        with self.lock:
            self.entries.clear()
