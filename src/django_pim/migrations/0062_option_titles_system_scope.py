# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# `option_titles` became a reserved system feature idx in 3.1.0 (added to
# SYSTEM_FEATURES_IDXS). Feature.save() asserts that a reserved idx is only ever used at
# SYSTEM scope, so any catalogue that already created `option_titles` at BUSINESS_UNIT
# scope — the CSV importer's default — would raise AssertionError on every save of that
# row after upgrade, breaking CSV import and the admin edit path. Align the data with the
# new declaration.
#
# The idx is spelled out rather than imported from django_pim.settings: migrations must
# stay frozen against the code moving underneath them.

from django.db import migrations

OPTION_TITLES_IDX = "option_titles"
SCOPE_SYSTEM = 1


def promote_option_titles_to_system(apps, schema_editor):
    Feature = apps.get_model("django_pim", "Feature")
    count = Feature.objects.filter(idx=OPTION_TITLES_IDX).exclude(scope=SCOPE_SYSTEM).update(scope=SCOPE_SYSTEM)
    if count:
        print(f"\n  Promoted {count} '{OPTION_TITLES_IDX}' feature(s) to SYSTEM scope")


class Migration(migrations.Migration):
    dependencies = [
        ("django_pim", "0061_productvariantgroup_productvariantgroupproduct_and_more"),
    ]

    operations = [
        # Irreversible by design: the original scope is not recoverable, and demoting a
        # genuinely-system feature would re-break Feature.save().
        migrations.RunPython(promote_option_titles_to_system, migrations.RunPython.noop),
    ]
