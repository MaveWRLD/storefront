from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status
import pytest

from catalog.models import Collection

@pytest.mark.django_db
class TestCreateCollection:
    def test_if_user_is_annonymous_returns_401(self):
        client = APIClient()
        response = client.post('/store-admin/collections/', {'title': 'a'})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_if_user_is_not_admin_returns_403(self):
        client = APIClient()
        client.force_authenticate(user={})
        response = client.post('/store-admin/collections/', {'title': 'a'})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_if_data_is_invalid_returns_400(self):
        client = APIClient()
        client.force_authenticate(user=User(is_staff=True))
        response = client.post('/store-admin/collections/', {'title': ''})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data['title'] is not None

    def test_if_data_is_valid_returns_201(self):
        client = APIClient()
        client.force_authenticate(user=User(is_staff=True))
        response = client.post('/store-admin/collections/', {'title': 'a'})

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['id'] > 0


@pytest.mark.django_db
class TestListCollections:
    def test_id__in_filter_returns_only_matching_collections(self):
        c1 = Collection.objects.create(title='a')
        c2 = Collection.objects.create(title='b')
        Collection.objects.create(title='c')  # excluded

        client = APIClient()
        client.force_authenticate(user=User(is_staff=True))
        response = client.get(
            '/store-admin/collections/', {'id__in': f'{c1.id},{c2.id}'})

        assert response.status_code == status.HTTP_200_OK
        returned_ids = {c['id'] for c in response.data}
        assert returned_ids == {c1.id, c2.id}

    def test_id__in_filter_with_no_match_returns_empty(self):
        Collection.objects.create(title='a')

        client = APIClient()
        client.force_authenticate(user=User(is_staff=True))
        response = client.get('/store-admin/collections/', {'id__in': '0'})

        assert response.status_code == status.HTTP_200_OK
        assert response.data == []