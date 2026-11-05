"""Short-lived caching for provider-independent calendar events."""

from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from time import monotonic

from app.models import CreateEventRequest, Event, EventPatch, EventReplacement
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
        self._mutation_epoch = 0
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

    def current_epoch(self) -> int:
        """Return the current cache mutation epoch for an in-flight read."""
        with self._lock:
            return self._mutation_epoch

    def put(
        self,
        namespace: str,
        event_id: str,
        event: Event,
        *,
        expected_epoch: int | None = None,
    ) -> bool:
        """Store an event unless a write occurred during its provider read."""
        now = self._clock()
        with self._lock:
            if expected_epoch is not None and expected_epoch != self._mutation_epoch:
                return False
            if expected_epoch is None:
                self._mutation_epoch += 1
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
            return True

    def remove(self, namespace: str, event_id: str) -> int:
        """Invalidate an event and return the new mutation epoch."""
        with self._lock:
            self._mutation_epoch += 1
            self._entries.pop((namespace, event_id), None)
            return self._mutation_epoch


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

        cache_epoch = self._cache.current_epoch()
        event = self._provider.get_event(event_id)
        self._cache.put(
            self._namespace,
            event_id,
            event,
            expected_epoch=cache_epoch,
        )
        return event

    def list_events(self, limit: int) -> list[Event]:
        """List events directly because the cache stores single-event reads."""
        return self._provider.list_events(limit)

    def create_event(self, event: CreateEventRequest) -> Event:
        """Create an event and reject older reads when its identifier is known."""
        write_epoch = self._cache.current_epoch()
        created = self._provider.create_event(event)
        self._finish_write(created.id, write_epoch, created)
        return created

    def _finish_write(
        self, event_id: str, write_epoch: int, result: Event | None = None
    ) -> None:
        # Clear reads cached during the write and reject late in-flight reads.
        completed_epoch = self._cache.remove(self._namespace, event_id)
        # Overlapping mutations make response order unreliable; let GET refresh.
        if result is not None and completed_epoch == write_epoch + 1:
            self._cache.put(
                self._namespace, event_id, result, expected_epoch=completed_epoch
            )

    def replace_event(self, event_id: str, replacement: EventReplacement) -> Event:
        """Invalidate across a complete replacement, including uncertain failures."""
        write_epoch = self._cache.remove(self._namespace, event_id)
        replaced = None
        try:
            replaced = self._provider.replace_event(event_id, replacement)
            return replaced
        finally:
            self._finish_write(event_id, write_epoch, replaced)

    def patch_event(self, event_id: str, changes: EventPatch) -> Event:
        """Invalidate across a partial update, including uncertain failures."""
        write_epoch = self._cache.remove(self._namespace, event_id)
        patched = None
        try:
            patched = self._provider.patch_event(event_id, changes)
            return patched
        finally:
            self._finish_write(event_id, write_epoch, patched)

    def delete_event(self, event_id: str) -> None:
        """Invalidate before and after deletion, even if its outcome is uncertain."""
        write_epoch = self._cache.remove(self._namespace, event_id)
        try:
            self._provider.delete_event(event_id)
        finally:
            self._finish_write(event_id, write_epoch)
