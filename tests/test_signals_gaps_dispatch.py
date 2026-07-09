# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Gap recompute debounce layer (etap-03).

Proves the gap tor uses its OWN Redis keys / flush task / queue — never the Matrix tor's — plus the
SETNX coalesce, the pending-set TTL, and graceful degradation when Redis is down. Mirrors
test_signals_dispatch.py.
"""

from unittest.mock import MagicMock, patch


def _make_redis_mock(setnx_returns=False):
    redis_mock = MagicMock()
    redis_mock.set.return_value = setnx_returns
    return redis_mock


def _patch_caches(redis_mock):
    cache_mock = MagicMock()
    cache_mock.__getitem__.return_value.client.get_client.return_value = redis_mock
    return patch("django_pim.signals.dispatch.caches", cache_mock)


def _call(product_pk=42):
    from django_pim.signals.dispatch import enqueue_gap_recompute

    enqueue_gap_recompute(product_pk)


# --- own keys, never matrix's ------------------------------------------------


def test_uses_own_pending_key():
    redis_mock = _make_redis_mock()
    with _patch_caches(redis_mock):
        _call(42)

    key = redis_mock.zadd.call_args[0][0]
    assert key == "pim:gaps:pending"
    assert key != "pim:matrix:pending"


def test_member_is_product_pk():
    redis_mock = _make_redis_mock()
    with _patch_caches(redis_mock):
        _call(42)

    member_dict = redis_mock.zadd.call_args[0][1]
    assert "42" in member_dict


def test_pending_key_ttl_uses_setting():
    redis_mock = _make_redis_mock()
    with _patch_caches(redis_mock):
        _call()

    redis_mock.expire.assert_called_once_with("pim:gaps:pending", 300)


# --- SETNX coalesce ----------------------------------------------------------


def test_setnx_success_schedules_own_flush_task():
    redis_mock = _make_redis_mock(setnx_returns=True)
    with _patch_caches(redis_mock), patch("django_pim.signals.dispatch.current_app") as mock_celery:
        _call()

    (name,) = mock_celery.send_task.call_args[0]
    kwargs = mock_celery.send_task.call_args[1]
    assert name == "pim.flush_gap_recompute"
    assert name != "django_matrix.tasks.flush_pending_matrix_sync"
    assert kwargs["queue"] == "celery"
    assert kwargs["countdown"] == 5


def test_setnx_failure_skips_flush():
    redis_mock = _make_redis_mock(setnx_returns=False)
    with _patch_caches(redis_mock), patch("django_pim.signals.dispatch.current_app") as mock_celery:
        _call()

    mock_celery.send_task.assert_not_called()


def test_lock_key_is_gaps_specific():
    redis_mock = _make_redis_mock(setnx_returns=True)
    with _patch_caches(redis_mock), patch("django_pim.signals.dispatch.current_app"):
        _call()

    lock_key = redis_mock.set.call_args[0][0]
    assert lock_key == "pim:gaps:flush_scheduled"


# --- graceful degradation ----------------------------------------------------


def test_redis_unavailable_does_not_raise():
    with patch("django_pim.signals.dispatch.caches") as mock_caches:
        mock_caches.__getitem__.side_effect = Exception("Connection refused")
        _call()  # must not raise


def test_redis_zadd_error_does_not_raise():
    redis_mock = _make_redis_mock()
    redis_mock.zadd.side_effect = Exception("Redis timeout")
    with _patch_caches(redis_mock):
        _call()  # must not raise
