# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.conf import settings

from django_pim.workers.unit_dto import LengthUnit, MassUnit, TemperatureUnit

DEBUG = getattr(settings, "DEBUG", False)

# API
# PUBLIC_BASE_URL = getattr(settings, "API_PUBLIC_BASE_URL", "api").strip("/")
VIEWER_BASE_URL = getattr(settings, "API_VIEWER_BASE_URL", "api-viewer").strip("/")
ADMIN_BASE_URL = getattr(settings, "API_ADMIN_BASE_URL", "api-admin").strip("/")

MEDIA_URL = settings.MEDIA_URL
STATIC_URL = settings.STATIC_URL
TMP_DIR = settings.TMP_DIR

SYSTEM_FEATURE_NAME_IDX = "name"
SYSTEM_FEATURE_DESCRIPTION_IDX = "description"
SYSTEM_FEATURE_SHORT_DESCRIPTION_IDX = "short_description"
SYSTEM_FEATURE_URL_KEY_IDX = "url_key"
SYSTEM_FEATURE_BADGE_IDX = "badge"
SYSTEM_FEATURE_BRAND_IDX = "brand"
SYSTEM_FEATURE_SUBNAME_IDX = "subname"
SYSTEM_FEATURE_SUBNAME2_IDX = "subname2"
SYSTEM_FEATURE_SIZE_TABLE_IDX = "size_table"
SYSTEM_FEATURE_EXTENSION_IDX = "extension"
SYSTEM_FEATURE_META_TITLE_IDX = "meta_title"
SYSTEM_FEATURE_META_DESCRIPTION_IDX = "meta_description"
SYSTEM_FEATURE_RICH_CONTENT_IDX = "rich_content"
SYSTEM_FEATURE_MAX_LIMIT_BUNDLE_IDX = "max_limit_bundle"
SYSTEM_FEATURE_MIN_LIMIT_BUNDLE_IDX = "min_limit_bundle"
SYSTEM_FEATURE_VOLUME_IDX = "volume"
SYSTEM_FEATURE_CANONICAL_URL_IDX = "canonical_url"
SYSTEM_FEATURE_OG_IMAGE_IDX = "og_image"
SYSTEM_FEATURE_MAX_LIMIT_BUNDLE_IDX = "max_limit_bundle"
SYSTEM_FEATURE_MIN_LIMIT_BUNDLE_IDX = "min_limit_bundle"
SYSTEM_FEATURE_VOLUME_IDX = "volume"

DESCRIPTION_FEATURE_IDXS = {
    SYSTEM_FEATURE_NAME_IDX,
    SYSTEM_FEATURE_DESCRIPTION_IDX,
    SYSTEM_FEATURE_SHORT_DESCRIPTION_IDX,
}

SYSTEM_FEATURES_IDXS = [
    SYSTEM_FEATURE_NAME_IDX,
    SYSTEM_FEATURE_DESCRIPTION_IDX,
    SYSTEM_FEATURE_SHORT_DESCRIPTION_IDX,
    SYSTEM_FEATURE_URL_KEY_IDX,
    SYSTEM_FEATURE_BADGE_IDX,
    SYSTEM_FEATURE_BRAND_IDX,
    SYSTEM_FEATURE_SUBNAME_IDX,
    SYSTEM_FEATURE_SUBNAME2_IDX,
    SYSTEM_FEATURE_SIZE_TABLE_IDX,
    SYSTEM_FEATURE_EXTENSION_IDX,
    SYSTEM_FEATURE_META_TITLE_IDX,
    SYSTEM_FEATURE_META_DESCRIPTION_IDX,
    SYSTEM_FEATURE_RICH_CONTENT_IDX,
    SYSTEM_FEATURE_CANONICAL_URL_IDX,
    SYSTEM_FEATURE_OG_IMAGE_IDX,
    SYSTEM_FEATURE_MAX_LIMIT_BUNDLE_IDX,
    SYSTEM_FEATURE_MIN_LIMIT_BUNDLE_IDX,
    SYSTEM_FEATURE_VOLUME_IDX,
]

SEO_FEATURE_IDXS = {
    SYSTEM_FEATURE_META_TITLE_IDX,
    SYSTEM_FEATURE_META_DESCRIPTION_IDX,
    SYSTEM_FEATURE_CANONICAL_URL_IDX,
    SYSTEM_FEATURE_OG_IMAGE_IDX,
}

T9N_DEFAULT_LANG = getattr(settings, "T9N_DEFAULT_LANG", "en")
DEFAULT_CURRENCY = getattr(settings, "DEFAULT_CURRENCY", "PLN")

# Lista rozmiarów w formacie [(width, height, transform_method, format, quality), ...] dla resizera
#   transform_method - one of PictureThumb.TransformMethod values as str
#   format - one of PictureThumb.ImageFormat values as str
#   quality - from 1 … 100
#
# Available transform_methods:
#  - "resize ratio, white"
#  - "resize ratio, black"
#  - "resize ratio, pink"
#  - "resize ratio, transparent"
#  - "fill and crop, white"
#  - "fill and crop, black"
#  - "fill and crop, pink"
#  - "fill and crop, transparent"
#  - "remove background experimental"
#  - "remove background experimental v2"

THUMBS_CONFIG = getattr(settings, "THUMBS_CONFIG", None)
CATEGORY_THUMBS_CONFIG = getattr(settings, "CATEGORY_THUMBS_CONFIG", THUMBS_CONFIG)
TIMEOUT_PICTURE_SECONDS = getattr(settings, "TIMEOUT_PICTURE_SECONDS", 15)

# for available units see django_pim.managers.unit_conversion. Temperature, Length, Weight etc.
DEFAULT_TEMPERATURE_UNIT = getattr(settings, "DEFAULT_TEMPERATURE_UNIT", TemperatureUnit.C)
DEFAULT_LENGTH_UNIT = getattr(settings, "DEFAULT_LENGTH_UNIT", LengthUnit.MM)
DEFAULT_MASS_UNIT = getattr(settings, "DEFAULT_MASS_UNIT", MassUnit.G)


UNIT_SIGN_MAPPING = {
    TemperatureUnit.C: ("°C", 0),
    TemperatureUnit.F: ("°F", 0),
    TemperatureUnit.K: ("K", 0),
    LengthUnit.MM: ("mm", 0),
    LengthUnit.CM: ("cm", 0),
    LengthUnit.M: ("m", 0),
    LengthUnit.KM: ("km", 0),
    LengthUnit.INCH: ("inch", 0),
    LengthUnit.FT: ("ft", 0),
    LengthUnit.YD: ("yd", 0),
    LengthUnit.MI: ("mi", 0),
    MassUnit.KG: ("kg", 0),
    MassUnit.G: ("g", 0),
    MassUnit.MG: ("mg", 0),
    MassUnit.LB: ("lb", 2),
    MassUnit.OZ: ("oz", 0),
}
UNIT_SIGN_MAPPING.update(getattr(settings, "UNIT_SIGN_MAPPING", {}))

# True: Default lang brany jest z PIM.Shop.default_language i moze byc rozny dla roznych kanalow
# False: Default lang brany jest z T9N_DEFAULT_LANG
IS_DEFAULT_LANG_FOR_CHANNELS_FROM_PIM = getattr(settings, "IS_DEFAULT_LANG_FOR_CHANNELS_FROM_PIM", True)

LIMITED_CUSTOM_FEATURES_IDXS_TO_VIEW = getattr(settings, "LIMITED_CUSTOM_FEATURES_IDXS_TO_VIEW", None)
# check conversions in django_pim.workers.unit_conversion to declare default/available units lang mapping
# Provide languages that are supposed to have different behavior from the default
LANG_TEMPERATURE_MAPPING = getattr(settings, "LANG_TEMPERATURE_MAPPING", {"us": TemperatureUnit.F})
LANG_LENGTH_MAPPING = getattr(settings, "LANG_LENGTH_MAPPING", {"us": LengthUnit.INCH})
LANG_MASS_MAPPING = getattr(settings, "LANG_MASS_MAPPING", {"us": MassUnit.OZ})
UNIT_CONVERSION_DECIMAL_PLACES = getattr(settings, "UNIT_CONVERSION_DECIMAL_PLACES", 2)

CUSTOM_FEATURES_ADDITIONAL_DATA = getattr(settings, "CUSTOM_FEATURES_ADDITIONAL_DATA", [])

# Matrix signal-driven sync
PIM_MATRIX_SIGNALS_DEBOUNCE_SECONDS = getattr(settings, "PIM_MATRIX_SIGNALS_DEBOUNCE_SECONDS", 5)
PIM_MATRIX_SIGNALS_BATCH_THRESHOLD = getattr(settings, "PIM_MATRIX_SIGNALS_BATCH_THRESHOLD", 500)
PIM_MATRIX_SIGNALS_CHANNEL_DENYLIST = getattr(settings, "PIM_MATRIX_SIGNALS_CHANNEL_DENYLIST", [])

# Quality-gaps recompute (etap-03) — own tor, separate from Matrix sync above.
PIM_GAPS_DEBOUNCE_SECONDS = getattr(settings, "PIM_GAPS_DEBOUNCE_SECONDS", 5)
PIM_GAPS_BATCH_SIZE = getattr(settings, "PIM_GAPS_BATCH_SIZE", 10000)
PIM_GAPS_QUEUE = getattr(settings, "PIM_GAPS_QUEUE", "celery")
PIM_GAPS_PENDING_TTL = getattr(settings, "PIM_GAPS_PENDING_TTL", 300)
