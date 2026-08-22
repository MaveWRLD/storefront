from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
import pytest

User = get_user_model()


@pytest.mark.django_db
class TestAuthRateLimiting:
    """Gap-analysis doc: 'No rate limiting anywhere' — Spring runs 5/min,
    IP-keyed, on both login and register to blunt brute-force/enumeration.
    Matched here via the 'auth' ScopedRateThrottle scope."""

    def test_registration_is_rate_limited_after_5_per_minute(self):
        client = APIClient()
        for i in range(5):
            response = client.post('/auth/users/', {
                'email': f'user{i}@example.com', 'password': 'sUpers3cret!',
            })
            assert response.status_code == status.HTTP_201_CREATED

        response = client.post('/auth/users/', {
            'email': 'oneTooMany@example.com', 'password': 'sUpers3cret!',
        })
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_login_is_rate_limited_after_5_per_minute(self):
        User.objects.create_user(email='shopper@example.com', password='sUpers3cret!')
        client = APIClient()
        for _ in range(5):
            response = client.post('/auth/jwt/create/', {
                'email': 'shopper@example.com', 'password': 'wrong-password',
            })
            assert response.status_code == status.HTTP_401_UNAUTHORIZED

        response = client.post('/auth/jwt/create/', {
            'email': 'shopper@example.com', 'password': 'wrong-password',
        })
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_other_djoser_user_actions_are_not_throttled_by_the_auth_scope(self):
        # 'me' shares the same viewset as 'create' but isn't a brute-force
        # surface the same way — only registration itself gets the scope.
        user = User.objects.create_user(email='shopper2@example.com', password='sUpers3cret!')
        client = APIClient()
        client.force_authenticate(user=user)

        for _ in range(6):
            response = client.get('/auth/users/me/')
            assert response.status_code == status.HTTP_200_OK
