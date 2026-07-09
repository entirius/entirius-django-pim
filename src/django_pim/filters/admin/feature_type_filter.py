# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.contrib.admin import SimpleListFilter

from django_pim.models import Feature, FeatureTypeEnum


class FeatureTypeFilter(SimpleListFilter):
    title = "Feature"
    parameter_name = "feature"

    def lookups(self, request, model_admin):
        features = Feature.objects.filter(feature_type__in=[FeatureTypeEnum.SELECT, FeatureTypeEnum.MULTISELECT])
        return [(feature.id, f"[{feature.idx}] {feature.name}") for feature in features]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(attribute__feature__id=self.value())
        return queryset
