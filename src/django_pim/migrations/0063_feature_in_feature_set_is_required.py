# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Nullable per-set override of Feature.is_required. Existing memberships get NULL (inherit the
# feature's flag), so behaviour is unchanged until someone sets an override.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("django_pim", "0062_option_titles_system_scope"),
    ]

    operations = [
        migrations.AddField(
            model_name="featureinfeatureset",
            name="is_required",
            field=models.BooleanField(
                blank=True,
                default=None,
                help_text="Per-set override of Feature.is_required. None inherits the feature's flag; True/False wins for this set only. Not allowed on SYSTEM-scope features.",
                null=True,
            ),
        ),
    ]
