# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import re


def t9n_cleanup(name_t9n):
    for key in name_t9n:
        name = name_t9n[key]
        name = name.replace("\n", " ").replace("\r", "")
        name = re.sub(" +", " ", name)  # remove multiple spaces
        name = name.strip()
        name_t9n[key] = name
    return name_t9n


def t9n_update(t9n_to_update, t9n_data):
    """Aktualizuje "t9n_to_update" o dane z "t9n_data"
    Zwracam informacje, czy cos zostalo zmienione w t9n_to_update
    """
    is_t9n_updated = False
    changed = {}
    for key in t9n_data:
        if t9n_data[key] is None or t9n_data[key] == "":
            continue
        if key in t9n_to_update and t9n_to_update[key] is not None:
            if t9n_to_update[key] == t9n_data[key]:
                continue
            changed[key] = {"from": t9n_to_update[key], "to": t9n_data[key]}
            t9n_to_update[key] = t9n_data[key]
        else:
            changed[key] = {"from": "", "to": t9n_data[key]}
            t9n_to_update[key] = t9n_data[key]
        is_t9n_updated = True
    return is_t9n_updated, changed
