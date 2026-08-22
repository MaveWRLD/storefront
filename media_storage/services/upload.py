import uuid
import magic
from media_storage.backends.factory import get_storage_backend

ALLOWED_MIME = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp'}
MAX_BYTES = 10 * 1024 * 1024


class InvalidImageError(Exception):
    pass


def upload_image(file_obj, *, product_id, variant_id=None) -> str:
    data = file_obj.read()
    if len(data) > MAX_BYTES:
        raise InvalidImageError('File exceeds 10MB limit')

    mime = magic.from_buffer(data, mime=True)
    ext = ALLOWED_MIME.get(mime)
    if not ext:
        raise InvalidImageError(f'Unsupported MIME type: {mime}')

    key_parts = ['products', str(product_id)]
    if variant_id:
        key_parts += ['variants', str(variant_id)]
    key = '/'.join(key_parts) + f'/{uuid.uuid4()}.{ext}'

    get_storage_backend().put(key, data, mime)
    return key


def delete_image(key: str) -> None:
    get_storage_backend().delete(key)
