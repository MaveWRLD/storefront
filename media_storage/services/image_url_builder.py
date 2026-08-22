from media_storage.backends.factory import get_storage_backend


def build_url(key: str) -> str:
    """Passthrough for now — no Cloudflare resize/srcset transform syntax
    yet. Kept as its own module (not a StorageBackend method) since URL
    transformation is a separate concern from storage I/O; local dev may
    never need transforms at all."""
    return get_storage_backend().public_url(key)
