import uuid
import magic
from media_storage.backends.factory import get_storage_backend

ALLOWED_MIME = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp'}
MAX_BYTES = 10 * 1024 * 1024


class InvalidImageError(Exception):
    pass


def validate_image_bytes(data: bytes) -> str:
    """Validate raw image bytes against size/MIME rules. Returns the
    file extension for the detected MIME type, or raises InvalidImageError."""
    if len(data) > MAX_BYTES:
        raise InvalidImageError('File exceeds 10MB limit')
    mime = magic.from_buffer(data, mime=True)
    ext = ALLOWED_MIME.get(mime)
    if not ext:
        raise InvalidImageError(f'Unsupported MIME type: {mime}')
    return ext


def upload_image(file_obj, *, product_id, variant_id=None) -> str:
    size = getattr(file_obj, 'size', None)
    if size is not None and size > MAX_BYTES:
        raise InvalidImageError('File exceeds 10MB limit')

    data = file_obj.read()
    ext = validate_image_bytes(data)

    key_parts = ['products', str(product_id)]
    if variant_id is not None:
        key_parts += ['variants', str(variant_id)]
    key = '/'.join(key_parts) + f'/{uuid.uuid4()}.{ext}'

    get_storage_backend().put(key, data, magic.from_buffer(data, mime=True))
    return key


def delete_image(key: str) -> None:
    get_storage_backend().delete(key)
