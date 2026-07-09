# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.core.management.base import BaseCommand

from django_pim.utils.pim_configurator import PimConfigurator


class Command(BaseCommand):
    help = "Export PIM configuration from YML file."

    def handle(self, *args, **options):
        worker = PimConfigurator()
        rv = worker.config_export_as_yml()
        if rv:
            self.stdout.write(self.style.SUCCESS("done"))
        else:
            self.stdout.write(self.style.ERROR("error"))
