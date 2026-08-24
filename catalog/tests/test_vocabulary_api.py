import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from catalog.models import (
    AxisValue, Product, ProductAxis, Variant, VariantAxisValue,
    VocabularyValue,
)

User = get_user_model()

VALUES_URL = '/store-admin/vocabularies/colour/values/'


@pytest.fixture
def customer_client():
    client = APIClient()
    client.force_authenticate(user=User(is_staff=False))
    return client


@pytest.mark.django_db
class TestPermissions:
    @pytest.mark.parametrize('url', [
        '/store-admin/vocabularies/',
        '/store-admin/vocabularies/colour/',
        VALUES_URL,
        VALUES_URL + 'Olive/',
    ])
    def test_anonymous_is_rejected(self, url):
        assert APIClient().get(url).status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.parametrize('url', [
        '/store-admin/vocabularies/',
        VALUES_URL,
    ])
    def test_non_staff_is_rejected(self, customer_client, url):
        assert customer_client.get(url).status_code == status.HTTP_403_FORBIDDEN

    def test_staff_is_allowed(self, admin_client):
        assert admin_client.get(VALUES_URL).status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestListValues:
    def test_lists_every_value_unpaginated(self, admin_client):
        """Deliberately unpaginated — this feeds a selector, and the house
        page_size of 10 would silently truncate the 10-entry colour
        vocabulary."""
        response = admin_client.get(VALUES_URL)

        assert isinstance(response.data, list)
        assert len(response.data) == 10
        assert all(row['label'] for row in response.data)

    def test_inactive_values_are_hidden_by_default(self, admin_client, colour_vocab):
        colour_vocab.values.filter(value='Clay').update(is_active=False)

        assert 'Clay' not in {r['value'] for r in admin_client.get(VALUES_URL).data}

    def test_inactive_values_can_be_requested(self, admin_client, colour_vocab):
        colour_vocab.values.filter(value='Clay').update(is_active=False)

        response = admin_client.get(VALUES_URL + '?include_inactive=1')

        assert 'Clay' in {row['value'] for row in response.data}


@pytest.mark.django_db
class TestAddValue:
    def test_adds_a_value(self, admin_client, colour_vocab):
        response = admin_client.post(
            VALUES_URL, {'value': 'Ochre', 'code': 'OCH', 'label': 'Ochre'},
            format='json')

        assert response.status_code == status.HTTP_201_CREATED
        assert colour_vocab.values.filter(value='Ochre').exists()

    def test_rejects_a_blank_label(self, admin_client):
        response = admin_client.post(
            VALUES_URL, {'value': 'Ochre', 'code': 'OCH', 'label': ''},
            format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'label' in response.data

    def test_rejects_a_duplicate_value(self, admin_client):
        response = admin_client.post(
            VALUES_URL, {'value': 'Olive', 'code': 'OL2', 'label': 'Olive II'},
            format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'value' in response.data

    def test_rejects_a_duplicate_code(self, admin_client):
        response = admin_client.post(
            VALUES_URL, {'value': 'Olivine', 'code': 'OLV', 'label': 'Olivine'},
            format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'code' in response.data

    def test_rejects_a_value_containing_a_path_separator(self, admin_client):
        """`value` is the row's URL identity, so a '/' would make it
        unreachable by its own detail route."""
        response = admin_client.post(
            VALUES_URL,
            {'value': 'Black/White', 'code': 'BKW', 'label': 'Black & White'},
            format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'value' in response.data


@pytest.mark.django_db
class TestAddValueToExistingAxes:
    """The only route by which a new registry value reaches an
    already-created product: ProductSerializer discards axes, and
    VariantSerializer only accepts ids of rows that already exist."""

    def test_attaches_the_new_value_to_the_listed_axis(
            self, admin_client, color_axis):
        response = admin_client.post(
            VALUES_URL,
            {'value': 'Ochre', 'code': 'OCH', 'label': 'Ochre',
             'axis_ids': [color_axis.id]},
            format='json')

        assert response.status_code == status.HTTP_201_CREATED
        axis_value = AxisValue.objects.get(axis=color_axis, name='Ochre')
        assert (axis_value.code, axis_value.label) == ('OCH', 'Ochre')

    def test_rejects_an_axis_from_another_vocabulary(
            self, admin_client, size_axis):
        response = admin_client.post(
            VALUES_URL,
            {'value': 'Ochre', 'code': 'OCH', 'label': 'Ochre',
             'axis_ids': [size_axis.id]},
            format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'axis_ids' in response.data

    def test_a_rejected_axis_creates_no_registry_value(
            self, admin_client, size_axis, color_axis):
        admin_client.post(
            VALUES_URL,
            {'value': 'Ochre', 'code': 'OCH', 'label': 'Ochre',
             'axis_ids': [color_axis.id, size_axis.id]},
            format='json')

        assert not VocabularyValue.objects.filter(value='Ochre').exists()


@pytest.mark.django_db
class TestCreateVocabulary:
    def test_creates_a_vocabulary_with_initial_values(self, admin_client):
        response = admin_client.post(
            '/store-admin/vocabularies/',
            {'key': 'size_eu_shoe', 'label': 'EU shoe size',
             'values': [
                 {'value': '42', 'code': 'EU42', 'label': 'EU 42'},
                 {'value': '43', 'code': 'EU43', 'label': 'EU 43'}]},
            format='json')

        assert response.status_code == status.HTTP_201_CREATED
        assert VocabularyValue.objects.filter(
            vocabulary__key='size_eu_shoe').count() == 2

    def test_rejects_a_duplicate_key(self, admin_client):
        response = admin_client.post(
            '/store-admin/vocabularies/', {'key': 'colour', 'label': 'Colour'},
            format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_repeated_values_in_one_payload(self, admin_client):
        response = admin_client.post(
            '/store-admin/vocabularies/',
            {'key': 'size_eu_shoe', 'label': 'EU shoe size',
             'values': [
                 {'value': '42', 'code': 'EU42', 'label': 'EU 42'},
                 {'value': '42', 'code': 'EU43', 'label': 'EU 42 again'}]},
            format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestRelabel:
    def test_relabelling_fans_out_to_every_product_using_the_value(
            self, admin_client, product, collection, olive, colour_vocab,
            make_axis_value):
        other = Product.objects.create(
            title='Other', slug='other', collection=collection)
        other_axis = ProductAxis.objects.create(
            product=other, name='Colour', vocabulary=colour_vocab)
        other_value = make_axis_value(other_axis, 'Olive')

        response = admin_client.patch(
            VALUES_URL + 'Olive/', {'label': 'Olive Drab'}, format='json')

        assert response.status_code == status.HTTP_200_OK
        olive.refresh_from_db()
        other_value.refresh_from_db()
        assert olive.label == other_value.label == 'Olive Drab'

    def test_value_is_immutable(self, admin_client):
        response = admin_client.patch(
            VALUES_URL + 'Olive/', {'value': 'Renamed'}, format='json')

        assert response.status_code == status.HTTP_200_OK
        assert response.data['value'] == 'Olive'
        assert VocabularyValue.objects.filter(
            vocabulary__key='colour', value='Olive').exists()

    def test_resolves_a_value_containing_a_space(self, admin_client):
        response = admin_client.patch(
            VALUES_URL + 'Sea%20Green/', {'label': 'Seafoam'}, format='json')

        assert response.status_code == status.HTTP_200_OK
        assert VocabularyValue.objects.get(
            vocabulary__key='colour', value='Sea Green').label == 'Seafoam'

    def test_changing_a_code_does_not_rewrite_existing_skus(
            self, admin_client, product, olive):
        """SKUs are stored strings, never recomputed — the registry does not
        reach into them."""
        variant = Variant.objects.create(
            product=product, sku='OLV-S-TEST-SHIRT', unit_price=1000)
        VariantAxisValue.objects.create(variant=variant, axis_value=olive)

        admin_client.patch(VALUES_URL + 'Olive/', {'code': 'OLI'}, format='json')

        variant.refresh_from_db()
        olive.refresh_from_db()
        assert variant.sku == 'OLV-S-TEST-SHIRT'
        assert olive.code == 'OLI'

    def test_no_delete_action(self, admin_client):
        response = admin_client.delete(VALUES_URL + 'Olive/')

        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
