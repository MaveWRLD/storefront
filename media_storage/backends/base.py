from abc import ABC, abstractmethod


class StorageBackend(ABC):
    """Interface every storage backend must implement. catalog (and any
    future media-uploading app) depends only on this — never on a
    concrete backend or a third-party SDK directly."""

    @abstractmethod
    def put(self, key: str, data: bytes, content_type: str) -> None:
        """Upload raw bytes under the given key."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete the object at the given key. Must not raise if the key
        doesn't exist (idempotent — safe to call on cleanup paths)."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check whether an object exists at the given key."""

    @abstractmethod
    def public_url(self, key: str) -> str:
        """Return a direct (non-CDN-transformed) URL for the raw object."""
