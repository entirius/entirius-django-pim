# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.core.management.base import BaseCommand

from ...managers import FeatureToSetManager


class Command(BaseCommand):
    help = "Feature Filters Discovery"

    def handle(self, *args, **options):
        FeatureToSetManager.discover_filters()
        self.stdout.write(self.style.SUCCESS("done"))
