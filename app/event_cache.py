"""Short-lived caching for provider-independent calendar events."""

from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from time import monotonic

from app.models import Event
from app.providers import EventProvider

EVENT_CACHE_TTL_SECONDS = 60.0
EVENT_CACHE_MAX_ENTRIES = 256

type CacheKey = tuple[str, str]


@dataclass(frozen=True)
class _CacheEntry:
    event: Event
    expires_at: float


class EventCache:
    """Store successful event reads for a fixed time-to-live."""

    def __init__(
        self,
        ttl_seconds: float = EVENT_CACHE_TTL_SECONDS,
        *,
        max_entries: int = EVENT_CACHE_MAX_ENTRIES,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        """Configure the cache lifetime, capacity, and expiration clock."""
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._entries: dict[CacheKey, _CacheEntry] = {}
        self._lock = Lock()

    def get(self, namespace: str, event_id: str) -> Event | None:
        """Return an unexpired event for the namespace and identifier, if present."""
        key = (namespace, event_id)
        now = self._clock()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                del self._entries[key]
                return None
            return entry.event

    def put(self, namespace: str, event_id: str, event: Event) -> None:
        """Store an event, discarding expired entries and the oldest when full."""
        now = self._clock()
        with self._lock:
            self._entries = {
                key: entry
                for key, entry in self._entries.items()
                if entry.expires_at > now
            }
            key = (namespace, event_id)
            self._entries.pop(key, None)
            if len(self._entries) >= self._max_entries:
                oldest_key = next(iter(self._entries))
                del self._entries[oldest_key]
            self._entries[key] = _CacheEntry(
                event=event,
                expires_at=now + self._ttl_seconds,
            )


class CachedEventProvider:
    """Cache successful reads from another provider using domain Events only."""

    def __init__(
        self,
        provider: EventProvider,
        *,
        cache: EventCache,
        namespace: str,
    ) -> None:
        """Wrap a provider with a cache namespace selected by composition code."""
        self._provider = provider
        self._cache = cache
        self._namespace = namespace

    def get_event(self, event_id: str) -> Event:
        """Return a cached Event or retrieve and cache a successful result."""
        cached_event = self._cache.get(self._namespace, event_id)
        if cached_event is not None:
            return cached_event

        event = self._provider.get_event(event_id)
        self._cache.put(self._namespace, event_id, event)
        return event
