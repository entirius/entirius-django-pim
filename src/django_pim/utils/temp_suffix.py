# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os
import re

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9.]")
_MAX_LENGTH = 16


def safe_temp_suffix(filename: str | None) -> str:
    """Temp-file suffix from an uploaded file's name: its extension only, never a path."""
    base_name = os.path.basename(str(filename or "").replace("\\", "/"))
    extension = _UNSAFE_CHARS.sub("", os.path.splitext(base_name)[1])[:_MAX_LENGTH]
    return extension if extension.strip(".") else ""
