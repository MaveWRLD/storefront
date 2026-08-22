from media_storage.backends.url_builders.factory import get_url_builder

DEFAULT_SRC_WIDTH = 800
DEFAULT_SRCSET_WIDTHS = (400, 800, 1200, 1600)


def build_url(key: str, *, width: int | None = None,
               quality: int | None = None, format: str | None = None) -> str:
    """Builds a public URL for a stored image key, via the configured
    UrlBuilder (local passthrough or R2 cdn-cgi transform). Transform
    kwargs are optional — omitted ones fall back to each builder's own
    defaults (ignored entirely by the local builder). Callers that want
    the shared 'src' size should pass width=DEFAULT_SRC_WIDTH explicitly."""
    if not key:
        return ''
    return get_url_builder().build(key, width=width, quality=quality, format=format)


def build_srcset(key: str, widths=DEFAULT_SRCSET_WIDTHS) -> str:
    """Builds a full `srcset` attribute value — one URL per width tier,
    space-descriptor-joined, so a browser can pick the tier that matches
    its viewport/DPR instead of always downloading the 'src' size."""
    if not key:
        return ''
    builder = get_url_builder()
    return ', '.join(
        f'{builder.build(key, width=w, quality=None, format=None)} {w}w'
        for w in widths)
