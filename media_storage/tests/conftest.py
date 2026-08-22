import pytest
from django.test import override_settings

from media_storage.backends.factory import _build


@pytest.fixture(autouse=True)
def isolated_media_root(tmp_path):
    _build.cache_clear()
    with override_settings(MEDIA_ROOT=tmp_path, MEDIA_STORAGE_BACKEND='local'):
        yield
    _build.cache_clear()
