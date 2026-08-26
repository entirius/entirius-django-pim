# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Shared test fixtures for django-pim tests."""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


@pytest.fixture(autouse=True)
def _clear_killswitch_cache():
    """Reset the killswitch toggle cache between tests.

    ``is_matrix_signals_enabled``/``is_gaps_enabled`` cache the PimSettings
    toggles for 60s in the process-wide LocMemCache. Any test that fires
    model signals primes those keys with the then-current DB value, which
    leaks into later tests (DB rolls back per test, the cache does not) —
    the ~35-test flake in test_signals_* under ``--create-db``.
    """
    from django.core.cache import cache

    from django_pim.signals.killswitch import GAPS_CACHE_KEY, MATRIX_SIGNALS_CACHE_KEY

    cache.delete(MATRIX_SIGNALS_CACHE_KEY)
    cache.delete(GAPS_CACHE_KEY)
    yield
    cache.delete(MATRIX_SIGNALS_CACHE_KEY)
    cache.delete(GAPS_CACHE_KEY)


@pytest.fixture(autouse=True)
def _clear_lookup_provider_cache():
    """Same leak, same fix, for `lookup_provider._fingerprinted_feature_ids`'s 60s cache.

    `Feature.id` is DB-assigned; a stale cached id set from an earlier (rolled-back) test would
    make `_ref_for_attribute` short-circuit incorrectly for the current test's features.
    """
    from django.core.cache import cache

    from django_pim.services.lookup_provider import FINGERPRINTED_FEATURE_IDS_CACHE_KEY

    cache.delete(FINGERPRINTED_FEATURE_IDS_CACHE_KEY)
    yield
    cache.delete(FINGERPRINTED_FEATURE_IDS_CACHE_KEY)


_user_counter = 0


def _next_username(prefix: str) -> str:
    global _user_counter
    _user_counter += 1
    return f"{prefix}_{_user_counter}"


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        username=_next_username("admin"),
        email=f"admin_{_user_counter}@test.com",
        password="adminpass123",
        is_staff=True,
        is_superuser=False,
    )


@pytest.fixture
def regular_user(db):
    return User.objects.create_user(
        username=_next_username("regular"),
        email=f"regular_{_user_counter}@test.com",
        password="regularpass123",
        is_staff=False,
        is_superuser=False,
    )


@pytest.fixture
def admin_token(admin_user):
    return str(RefreshToken.for_user(admin_user).access_token)


@pytest.fixture
def regular_token(regular_user):
    return str(RefreshToken.for_user(regular_user).access_token)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def authenticated_client(api_client, admin_token):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_token}")
    return api_client
