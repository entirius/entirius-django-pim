# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.


def update_field(field_name, value):
    def action(modeladmin, request, queryset):
        queryset.update(**{field_name: value})

    action.short_description = f"Mark selected features {field_name}={value}"
    action.__name__ = f"{field_name}_{value}"
    return action


make_visible = update_field("is_visible", True)
make_invisible = update_field("is_visible", False)
make_required = update_field("is_required", True)
make_not_required = update_field("is_required", False)
make_filterable = update_field("is_filterable", True)
make_not_filterable = update_field("is_filterable", False)
make_searchable = update_field("is_searchable", True)
make_not_searchable = update_field("is_searchable", False)
make_comparable = update_field("is_comparable", True)
make_not_comparable = update_field("is_comparable", False)
make_for_customization = update_field("is_for_customization", True)
make_not_for_customization = update_field("is_for_customization", False)
