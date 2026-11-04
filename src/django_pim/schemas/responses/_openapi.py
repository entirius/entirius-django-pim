# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""OpenAPI marker for response models that are the whole body of a list view."""

from drf_spectacular.utils import extend_schema_serializer

# drf-spectacular describes the 200 of every `list` action as an array of its response model. The admin list
# views answer one object (a page `{count, next, previous, results}`, `{results}`, or category products'
# `{positioned, unpositioned, ...}`), so their models opt out.
list_body = extend_schema_serializer(many=False)
