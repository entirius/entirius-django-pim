# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from django.core.cache.backends.redis import RedisCache

from django_pim.services import gap_recompute_service as gaps
from django_pim.signals import dispatch


@pytest.fixture(params=["django", "django_redis"])
def redis_backend(request, monkeypatch):
    client = MagicMock()
    factory = MagicMock(return_value=client)
    if request.param == "django":
        # Actual configured backend, with only its network-facing client factory isolated.
        cache = RedisCache("redis://127.0.0.1:6379/3", {})
        cache._cache = SimpleNamespace(get_client=factory)
    else:
        cache = SimpleNamespace(client=SimpleNamespace(get_client=factory))
    monkeypatch.setattr(gaps, "caches", {"default": cache})
    monkeypatch.setattr(dispatch, "caches", {"default": cache})
    return client, factory


def test_full_lock_acquires_then_coalesces_on_configured_backend(redis_backend):
    client, factory = redis_backend
    client.set.side_effect = [True, False]
    assert gaps.acquire_full_lock() is True
    assert gaps.acquire_full_lock() is False
    assert client.set.call_args_list[0].args == (gaps.RECOMPUTE_LOCK_KEY, "1")
    assert client.set.call_args_list[0].kwargs == {"nx": True, "ex": 1800}
    assert factory.call_count == 2
    factory.assert_called_with(write=True)


def test_full_lock_refresh_status_and_release_use_same_writer(redis_backend):
    client, factory = redis_backend
    client.get.return_value = b"1"
    gaps.refresh_full_lock()
    client.set.assert_called_once_with(gaps.RECOMPUTE_LOCK_KEY, "1", ex=1800)
    assert gaps.is_full_recompute_running() is True
    client.get.assert_called_once_with(gaps.RECOMPUTE_LOCK_KEY)
    gaps.release_full_lock()
    client.delete.assert_called_once_with(gaps.RECOMPUTE_LOCK_KEY)
    assert factory.call_count == 3
    factory.assert_called_with(write=True)


def test_unavailable_backend_keeps_existing_degradation_policy(redis_backend, caplog):
    client, factory = redis_backend
    factory.side_effect = ConnectionError("isolated unavailable backend")
    assert gaps.acquire_full_lock() is True
    gaps.refresh_full_lock()
    gaps.release_full_lock()
    assert gaps.is_full_recompute_running() is False
    assert "Redis unavailable" in caplog.text
    client.set.assert_not_called()
    client.delete.assert_not_called()


def test_gap_enqueue_and_drain_use_configured_backend(redis_backend, monkeypatch):
    client, factory = redis_backend
    send = MagicMock()
    monkeypatch.setattr(dispatch.current_app, "send_task", send)
    client.set.return_value = True
    dispatch.enqueue_gap_recompute(41)
    client.zadd.assert_called_once()
    assert client.zadd.call_args.args[0] == dispatch.GAPS_PENDING_KEY
    assert set(client.zadd.call_args.args[1]) == {"41"}
    send.assert_called_once_with(
        "pim.flush_gap_recompute",
        countdown=dispatch.pim_settings.PIM_GAPS_DEBOUNCE_SECONDS,
        queue=dispatch.pim_settings.PIM_GAPS_QUEUE,
    )
    client.zrange.return_value = [b"41", b"42"]
    assert dispatch.drain_pending_gap_pks() == [41, 42]
    client.zrem.assert_called_once_with(dispatch.GAPS_PENDING_KEY, b"41", b"42")
    factory.assert_called_with(write=True)


def test_matrix_enqueue_uses_configured_backend(redis_backend, monkeypatch):
    client, factory = redis_backend
    send = MagicMock()
    monkeypatch.setattr(dispatch.current_app, "send_task", send)
    client.set.return_value = True
    dispatch.enqueue_product_sync("SKU-1", "default")
    assert client.zadd.call_args.args[0] == "pim:matrix:pending"
    assert set(client.zadd.call_args.args[1]) == {"SKU-1:default"}
    send.assert_called_once_with(
        "django_matrix.tasks.flush_pending_matrix_sync",
        countdown=dispatch.pim_settings.PIM_MATRIX_SIGNALS_DEBOUNCE_SECONDS,
        queue="matrix_pull",
    )
    factory.assert_called_with(write=True)
