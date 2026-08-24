import json

from io import BytesIO

import pytest
from PIL import Image as PILImage
from rest_framework import status

from catalog.models import AxisValue, Product, VocabularyValue


def make_image(name='test.png'):
    buf = BytesIO()
    PILImage.new('RGB', (10, 10)).save(buf, format='PNG')
    buf.seek(0)
    buf.name = name
    return buf


def payload(**overrides):
    data = {
        'name': 'New Shirt',
        'price': {'amount': 25.00, 'currency': 'GHS'},
        'axes': [
            {'name': 'Size', 'sortOrder': 0, 'vocabulary': 'size_letter',
             'allowedValues': [{'name': 'S'}]},
        ],
    }
    data.update(overrides)
    return data


def post(client, images=None, **overrides):
    return client.post(
        '/store-admin/products/',
        {'data': json.dumps(payload(**overrides)),
         'images': [make_image()] if images is None else images},
        format='multipart')


@pytest.mark.django_db
class TestAxisVocabularyIsRequired:
    def test_missing_vocabulary_is_rejected(self, admin_client):
        response = post(admin_client, axes=[
            {'name': 'Size', 'sortOrder': 0, 'allowedValues': [{'name': 'S'}]}])

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'axes[0].vocabulary' in response.data['data']

    def test_unknown_vocabulary_is_rejected(self, admin_client):
        response = post(admin_client, axes=[
            {'name': 'Size', 'sortOrder': 0, 'vocabulary': 'size_martian',
             'allowedValues': [{'name': 'S'}]}])

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'size_martian' in str(response.data)

    def test_two_axes_may_not_share_a_vocabulary(self, admin_client):
        response = post(admin_client, axes=[
            {'name': 'Size', 'sortOrder': 0, 'vocabulary': 'size_letter',
             'allowedValues': [{'name': 'S'}]},
            {'name': 'Waist', 'sortOrder': 1, 'vocabulary': 'size_letter',
             'allowedValues': [{'name': 'M'}]},
        ])

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'axes[1].vocabulary' in response.data['data']


@pytest.mark.django_db
class TestValuesResolveFromTheRegistry:
    def test_unregistered_value_is_rejected(self, admin_client):
        response = post(admin_client, axes=[
            {'name': 'Size', 'sortOrder': 0, 'vocabulary': 'size_letter',
             'allowedValues': [{'name': 'XXL'}]}])

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'axes[0].allowedValues[0].name' in response.data['data']

    def test_label_is_taken_from_the_registry_not_the_request(self, admin_client):
        response = post(admin_client, axes=[
            {'name': 'Size', 'sortOrder': 0, 'vocabulary': 'size_waist_in',
             'allowedValues': [{'name': '30'}]}])

        assert response.status_code == status.HTTP_201_CREATED
        assert AxisValue.objects.get(name='30').label == 'W30'

    def test_contradicting_the_registry_label_is_rejected(self, admin_client):
        """Relabelling is global and goes through PATCH — a product payload
        may echo a label but never override it."""
        response = post(admin_client, axes=[
            {'name': 'Size', 'sortOrder': 0, 'vocabulary': 'size_waist_in',
             'allowedValues': [{'name': '30', 'label': '30 inches'}]}])

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'axes[0].allowedValues[0].label' in response.data['data']

    def test_contradicting_the_registry_code_is_rejected(self, admin_client):
        response = post(admin_client, axes=[
            {'name': 'Size', 'sortOrder': 0, 'vocabulary': 'size_waist_in',
             'allowedValues': [{'name': '30', 'code': 'WAIST30'}]}])

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'axes[0].allowedValues[0].code' in response.data['data']


@pytest.mark.django_db
class TestInlineAddNewValue:
    def test_adds_the_value_to_the_vocabulary_and_uses_it(self, admin_client):
        response = post(admin_client, axes=[
            {'name': 'Size', 'sortOrder': 0, 'vocabulary': 'size_letter',
             'allowedValues': [
                 {'name': 'XXL', 'newValue': True, 'code': 'XXL',
                  'label': 'XXL'}]}])

        assert response.status_code == status.HTTP_201_CREATED
        assert VocabularyValue.objects.filter(
            vocabulary__key='size_letter', value='XXL').exists()
        assert AxisValue.objects.get(name='XXL').label == 'XXL'

    def test_new_value_requires_a_label(self, admin_client):
        response = post(admin_client, axes=[
            {'name': 'Size', 'sortOrder': 0, 'vocabulary': 'size_letter',
             'allowedValues': [{'name': 'XXL', 'newValue': True, 'code': 'XXL'}]}])

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'axes[0].allowedValues[0].label' in response.data['data']

    def test_new_value_rejects_a_code_already_in_the_vocabulary(self, admin_client):
        response = post(admin_client, axes=[
            {'name': 'Size', 'sortOrder': 0, 'vocabulary': 'size_letter',
             'allowedValues': [
                 {'name': 'XXL', 'newValue': True, 'code': 'S',
                  'label': 'XXL'}]}])

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'axes[0].allowedValues[0].code' in response.data['data']

    def test_a_later_failure_rolls_the_registry_write_back(self, admin_client):
        """The registry write shares product creation's transaction, so a
        failed product cannot leave an orphan vocabulary entry behind."""
        response = post(admin_client, images=[], axes=[
            {'name': 'Size', 'sortOrder': 0, 'vocabulary': 'size_letter',
             'allowedValues': [
                 {'name': 'XXL', 'newValue': True, 'code': 'XXL',
                  'label': 'XXL'}]}])

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not VocabularyValue.objects.filter(value='XXL').exists()
        assert not Product.objects.filter(title='New Shirt').exists()
