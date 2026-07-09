# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from datetime import datetime

from django_pim.domains.abstract.pim import DomainPim


class DomainPimProductMedia(DomainPim):
    updated_at: datetime

    def set_updated_at(self, updated_at: datetime) -> None:
        self.updated_at = updated_at
