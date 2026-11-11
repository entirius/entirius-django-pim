# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Raw Redis writer for PIM's distributed locks and pending sets."""

from django.core.cache.backends.redis import RedisCache


def get_redis_client(cache):
    """Support Django's built-in backend and django-redis without changing key encoding.

    Locks and pending-set reads must use the writer too, rather than a possibly lagging
    read replica. These operations already own their raw Redis keys, outside Django's
    cache prefixing/serialization API.
    """
    if isinstance(cache, RedisCache):
        return cache._cache.get_client(write=True)
    return cache.client.get_client(write=True)
