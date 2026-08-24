import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APIClient

from catalog.models import (
    AxisValue, Collection, Product, ProductAxis, Vocabulary, VocabularyValue,
)
from media_storage.backends.factory import _build

User = get_user_model()


@pytest.fixture(autouse=True)
def isolated_media_root(tmp_path):
    _build.cache_clear()
    with override_settings(MEDIA_ROOT=tmp_path, MEDIA_STORAGE_BACKEND='local'):
        yield
    _build.cache_clear()


@pytest.fixture
def admin_client():
    client = APIClient()
    client.force_authenticate(user=User(is_staff=True))
    return client


@pytest.fixture
def collection():
    return Collection.objects.create(title='Shirts')


@pytest.fixture
def product(collection):
    return Product.objects.create(
        title='Test Shirt', slug='test-shirt', collection=collection)


# --- vocabulary registry -----------------------------------------------
# These are seeded by migration 0005, and pytest-django builds the test
# database by running migrations — so every test gets the real vocabularies
# without a fixture having to invent them. Inventing them would also defeat
# the point: the registry is meant to be the one source of display copy, so
# tests that make up their own values are not testing the thing that ships.

@pytest.fixture
def size_letter_vocab():
    return Vocabulary.objects.get(key='size_letter')


@pytest.fixture
def colour_vocab():
    return Vocabulary.objects.get(key='colour')


@pytest.fixture
def size_waist_vocab():
    return Vocabulary.objects.get(key='size_waist_in')


@pytest.fixture
def make_axis_value():
    """Build an AxisValue the only sanctioned way: by copying a registry
    entry. name/code/label are never typed by hand, in tests or in
    production."""
    def _make(axis, value):
        vocabulary_value = VocabularyValue.objects.get(
            vocabulary=axis.vocabulary, value=value)
        return AxisValue.objects.create(
            axis=axis, vocabulary_value=vocabulary_value,
            name=vocabulary_value.value, code=vocabulary_value.code,
            label=vocabulary_value.label)
    return _make


@pytest.fixture
def size_axis(product, size_letter_vocab):
    return ProductAxis.objects.create(
        product=product, name='Size', sort_order=0,
        vocabulary=size_letter_vocab)


@pytest.fixture
def color_axis(product, colour_vocab):
    return ProductAxis.objects.create(
        product=product, name='Colour', sort_order=1,
        vocabulary=colour_vocab)


@pytest.fixture
def small(size_axis, make_axis_value):
    return make_axis_value(size_axis, 'S')


@pytest.fixture
def large(size_axis, make_axis_value):
    return make_axis_value(size_axis, 'L')


@pytest.fixture
def olive(color_axis, make_axis_value):
    return make_axis_value(color_axis, 'Olive')


@pytest.fixture
def rust(color_axis, make_axis_value):
    return make_axis_value(color_axis, 'Rust')
