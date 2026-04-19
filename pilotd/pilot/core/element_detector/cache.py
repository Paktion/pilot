"""LRU detection cache and perceptual image hashing.

Two pieces split out of the detector module for size / reusability:

* :func:`hash_image` computes an 8x8 average hash (aHash) over the input
  image. Visually similar frames collapse onto identical or Hamming-close
  hash values, which is exactly what we want for a cache key -- minor
  rendering differences (antialiasing, sub-pixel font shifts, JPEG
  artefacts) should not invalidate a previous detection.

* :class:`LRUCache` is a tiny wrapper around ``OrderedDict`` that
  supports exact and similarity lookups, TTL-based expiry, and LRU
  eviction when capacity is exceeded.

The default capacity is 8 entries, which is plenty for a single phone
screen: the agent typically bounces between a handful of frames per
task, and stale entries are invalidated by TTL anyway.
"""

from __future__ import annotations

import collections
import time
from dataclasses import dataclass

from PIL import Image as PILImage

from pilot.core.element_detector.screen_graph import ScreenGraph


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

EHASH_SIZE: int = 8
DEFAULT_CACHE_SIZE: int = 8


# ---------------------------------------------------------------------------
# Perceptual hashing
# ---------------------------------------------------------------------------

def hash_image(image: PILImage.Image) -> str:
    """Compute a perceptual average-hash (aHash) of *image*.

    Algorithm:

    1. Resize to ``(EHASH_SIZE x EHASH_SIZE)`` with LANCZOS resampling.
    2. Convert to grayscale.
    3. Compute the mean pixel value.
    4. Each bit of the hash is 1 if the pixel exceeds the mean, else 0.
    5. Pack the bits into bytes and encode as hex.

    The resulting hex string can be compared via Hamming distance to
    measure visual similarity between frames.
    """
    size = EHASH_SIZE
    resized = image.resize((size, size), PILImage.LANCZOS).convert("L")
    pixels = list(resized.getdata())
    mean_val = sum(pixels) / len(pixels)
    bits = [1 if px > mean_val else 0 for px in pixels]
    hash_bytes = bytearray()
    for i in range(0, len(bits), 8):
        byte_val = 0
        for bit in bits[i:i + 8]:
            byte_val = (byte_val << 1) | bit
        hash_bytes.append(byte_val)
    return bytes(hash_bytes).hex()


def hamming_distance(hex1: str, hex2: str) -> int:
    """Return the Hamming distance (differing bits) between two hex hashes."""
    try:
        b1 = bytes.fromhex(hex1)
        b2 = bytes.fromhex(hex2)
    except ValueError:
        return 999
    max_len = max(len(b1), len(b2))
    b1 = b1.ljust(max_len, b"\x00")
    b2 = b2.ljust(max_len, b"\x00")
    return sum(bin(a ^ b).count("1") for a, b in zip(b1, b2))


# ---------------------------------------------------------------------------
# Cache implementation
# ---------------------------------------------------------------------------

@dataclass
class _CacheEntry:
    """Internal cache entry for a detection result."""
    graph: ScreenGraph
    image_hash: str
    created_at: float


class LRUCache:
    """LRU cache keyed by perceptual hash.

    Uses an ``OrderedDict`` to maintain insertion / access order. On a
    cache hit the entry moves to the end (most-recently used). When the
    cache exceeds *max_size*, the least-recently-used entry is evicted.
    Entries older than *ttl* seconds are treated as misses.
    """

    def __init__(self, max_size: int = DEFAULT_CACHE_SIZE) -> None:
        self._max_size = max(1, max_size)
        self._store: "collections.OrderedDict[str, _CacheEntry]" = (
            collections.OrderedDict()
        )

    # -- lookup --------------------------------------------------------

    def get(self, image_hash: str, ttl: float) -> ScreenGraph | None:
        """Return the cached graph for *image_hash* if fresh, else ``None``."""
        entry = self._store.get(image_hash)
        if entry is None:
            return None

        age = time.time() - entry.created_at
        if ttl > 0 and age >= ttl:
            del self._store[image_hash]
            return None

        self._store.move_to_end(image_hash)
        return entry.graph

    def get_by_similarity(
        self,
        image_hash: str,
        ttl: float,
        threshold: int = 5,
    ) -> ScreenGraph | None:
        """Return the nearest cached entry within *threshold* Hamming bits.

        Checks for an exact match first (fast path). On miss, scans from
        the most-recently-used entry backward for a perceptual neighbour
        within *threshold* Hamming distance.
        """
        exact = self.get(image_hash, ttl)
        if exact is not None:
            return exact

        for key in reversed(list(self._store)):
            entry = self._store[key]
            age = time.time() - entry.created_at
            if ttl > 0 and age >= ttl:
                continue
            if hamming_distance(image_hash, key) <= threshold:
                self._store.move_to_end(key)
                return entry.graph
        return None

    # -- mutation ------------------------------------------------------

    def put(self, image_hash: str, graph: ScreenGraph) -> None:
        """Insert or update an entry, evicting LRU when full."""
        entry = _CacheEntry(
            graph=graph, image_hash=image_hash, created_at=time.time()
        )
        if image_hash in self._store:
            self._store.move_to_end(image_hash)
            self._store[image_hash] = entry
        else:
            if len(self._store) >= self._max_size:
                self._store.popitem(last=False)
            self._store[image_hash] = entry

    def clear(self) -> None:
        """Drop every cached entry."""
        self._store.clear()

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self._store)


__all__ = [
    "DEFAULT_CACHE_SIZE",
    "EHASH_SIZE",
    "LRUCache",
    "hamming_distance",
    "hash_image",
]
