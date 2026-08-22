from django.conf import settings
from .base import UrlBuilder

DEFAULT_WIDTH = 1200
DEFAULT_QUALITY = 80
DEFAULT_FORMAT = 'auto'


class R2UrlBuilder(UrlBuilder):
    """Builds Cloudflare cdn-cgi image-resizing URLs against the R2 public
    domain. Reads CLOUDFLARE_R2['PUBLIC_DOMAIN'] directly from settings —
    same source R2StorageBackend uses — rather than reaching into the
    backend's private attributes."""

    def __init__(self):
        self._public_domain = settings.CLOUDFLARE_R2['PUBLIC_DOMAIN']

    def build(self, key: str, *, width: int | None = None,
              quality: int | None = None, format: str | None = None) -> str:
        width = width if width is not None else DEFAULT_WIDTH
        quality = quality if quality is not None else DEFAULT_QUALITY
        format = format if format is not None else DEFAULT_FORMAT
        domain = self._public_domain.rstrip('/')
        params = f'width={width},quality={quality},format={format}'
        return f'{domain}/cdn-cgi/image/{params}/{key}'
