from abc import ABC, abstractmethod


class UrlBuilder(ABC):
    """Interface for building public image URLs. Kept separate from
    StorageBackend — a backend can serve bytes without knowing anything
    about CDN resize/transform syntax, and URL-building can be swapped
    (e.g. local passthrough vs. CDN-transformed) independently of storage
    I/O."""

    @abstractmethod
    def build(self, key: str, *, width: int | None = None,
              quality: int | None = None, format: str | None = None) -> str:
        """Return a public URL for the given key, optionally requesting a
        resize/quality/format transform. Backends that don't support
        transforms (e.g. local) ignore the transform kwargs."""
