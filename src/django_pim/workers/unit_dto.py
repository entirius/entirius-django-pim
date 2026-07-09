# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models
from django.utils.translation import gettext_lazy as _


class TemperatureUnit(models.TextChoices):
    C = "C", _("Celsius")
    K = "K", _("Kelvin")
    R = "R", _("Rankine")
    F = "F", _("Fahrenheit")


class LengthUnit(models.TextChoices):
    MM = "mm", _("Millimeter")
    CM = "cm", _("Centimeter")
    M = "m", _("Meter")
    KM = "km", _("Kilometer")
    INCH = "inch", _("Inch")
    FT = "ft", _("Foot")
    YD = "yd", _("Yard")
    MI = "mi", _("Mile")


class MassUnit(models.TextChoices):
    KG = "kg", _("Kilogram")
    G = "g", _("Gram")
    MG = "mg", _("Milligram")
    TON = "ton", _("Ton")
    LB = "lb", _("Pound")
    OZ = "oz", _("Ounce")
