# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from idx_normalizator import normalize_idx as normalize_idx_utils
from idx_normalizator import validate_idx as validate_idx_utils


def normalize_idx(text: str, max_len: int = 128) -> str:
    """Deprecated"""
    return normalize_idx_utils(text, max_len)


def validate_idx(idx: str, min_len=1, max_len=128):
    """Deprecated"""
    return validate_idx_utils(idx, min_len, max_len)
