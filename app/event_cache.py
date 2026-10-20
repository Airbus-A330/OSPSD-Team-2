"""Short-lived caching for provider-independent calendar events."""

from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from time import monotonic

from app.models import Event
from app.providers import EventProvider

EVENT_CACHE_TTL_SECONDS = 60.0

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
        clock: Callable[[], float] = monotonic,
    ) -> None:
        """Configure the cache lifetime and clock used for expiration checks."""
        self._ttl_seconds = ttl_seconds
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
        """Store a successful domain event and discard other expired entries."""
        now = self._clock()
        with self._lock:
            self._entries = {
                key: entry
                for key, entry in self._entries.items()
                if entry.expires_at > now
            }
            self._entries[(namespace, event_id)] = _CacheEntry(
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
