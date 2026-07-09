# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django_pim.domains.abstract.pim import DomainPim


class DomainPimProduct(DomainPim):
    def __init__(self):
        super().__init__()

    def _name_from_idx(self, idx: str) -> str:
        return idx.capitalize().replace("_", " ")
