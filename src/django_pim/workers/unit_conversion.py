# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from decimal import Decimal

from django.utils.translation import gettext_lazy as _

from django_pim import settings
from django_pim.settings import UNIT_CONVERSION_DECIMAL_PLACES, UNIT_SIGN_MAPPING

from .unit_dto import LengthUnit, MassUnit, TemperatureUnit


class Unit:
    default_unit = None
    conversions = dict()
    lang_mapping = dict()

    def __init__(self, value, unit: str = None):
        super().__init__()
        self.value = float(value)
        self.unit = unit if unit else self.default_unit

        if self.unit not in self.conversions:
            raise ValueError(f"Invalid unit, not in conversions: {self.unit}")

        if not self.unit:
            raise ValueError(f"Invalid unit: {self.unit}")

    def convert(self, to_unit):
        """Converts the object from one unit to another."""
        from_unit = self.unit
        to_unit = to_unit
        return float(self.value) / float(self.conversions[from_unit]) * float(self.conversions[to_unit])

    def convert_to_lang_and_prettify(self, lang):
        new_unit = self.lang_mapping.get(lang, self.default_unit)
        if new_unit == self.unit:
            return self.prettify_to_str()
        else:
            sign, decimal_places = UNIT_SIGN_MAPPING.get(new_unit, (self.unit, UNIT_CONVERSION_DECIMAL_PLACES))
            rounded_value = round(self.convert(new_unit), decimal_places)
            if rounded_value.is_integer():
                rounded_value = int(rounded_value)
            return str(rounded_value) + " " + _(sign)

    def prettify_to_str(self):
        sign, decimal_places = UNIT_SIGN_MAPPING.get(self.unit, (self.unit, UNIT_CONVERSION_DECIMAL_PLACES))
        rounded_value = round(self.value, decimal_places)
        if rounded_value.is_integer():
            rounded_value = int(rounded_value)

        return str(rounded_value) + " " + _(sign)

    def changeUnit(self, unit):
        """Converts the current value of the object to a new unit.  Returns a float of the new value."""
        self.value = self.convert(unit)
        self.unit = unit
        return float(self.value)

    def setValue(self, value, unit):
        """Sets the value and unit of the object"""
        self.value = value
        self.unit = unit

    def getValue(self):
        """Returns a list of the float value and unit of the object."""
        return [float(self.value), self.unit]

    def __str__(self):
        return str(self.value) + " " + self.unit

    def __add__(self, other):
        if isinstance(other, self.__class__):
            new_value = self.value + other.changeUnit(self.unit)
            return self.__class__(new_value, self.unit)
        elif isinstance(other, (int, float, Decimal)):
            new_value = self + self.__class__(other, self.unit)
            return self.__class__(new_value.value, self.unit)
        else:
            return NotImplemented(f"Cannot add {self.__class__} to {type(other)}")

    def __sub__(self, other):
        new_value = self.value - other.changeUnit(self.unit)
        return self.__class__(new_value, self.unit)

    def __mul__(self, other):
        new_value = self.value * other
        return self.__class__(new_value, self.unit)

    def __rmul__(self, other):
        new_value = self.value * other
        return self.__class__(new_value, self.unit)

    def __truediv__(self, other):
        new_value = self.value / other
        return self.__class__(new_value, self.unit)

    def __floordiv__(self, other):
        new_value = self.value // other
        return self.__class__(new_value, self.unit)

    def __pow__(self, other):
        new_value = self.value**other
        return self.__class__(new_value, self.unit)


class Temperature(Unit):
    """Creates a temperature object that can store a temperature value and
    convert between units of temperature."""

    lang_mapping = (
        {
            # Nie ustawione tutaj języki przyjmują wartość default_unit
            "us": TemperatureUnit.F
        }
        if not settings.LANG_TEMPERATURE_MAPPING
        else settings.LANG_TEMPERATURE_MAPPING
    )

    # conversions { } is not used to convert the Temperature() class because
    # temperature is not converted with a scalar.  See the convert() function below.
    default_unit = settings.DEFAULT_TEMPERATURE_UNIT
    conversions = {TemperatureUnit.C: 1.0}

    def convert(self, to_unit):

        if self.unit == TemperatureUnit.C:
            temperature_celsius = self.value
        elif self.unit == TemperatureUnit.K:
            temperature_celsius = self.value - 273.15
        elif self.unit == TemperatureUnit.R:
            temperature_celsius = (self.value - 491.67) * 5.0 / 9.0
        elif self.unit == TemperatureUnit.F:
            temperature_celsius = (self.value - 32) * 5.0 / 9.0
        else:
            return None

        if to_unit == TemperatureUnit.C:
            return float(temperature_celsius)
        elif to_unit == TemperatureUnit.K:
            return temperature_celsius + 273.15
        elif to_unit == TemperatureUnit.R:
            return (temperature_celsius + 273.15) * 9.0 / 5.0
        elif to_unit == TemperatureUnit.F:
            return temperature_celsius * 9.0 / 5.0 + 32
        else:
            return None

    def __add__(self, other):
        if isinstance(other, self.__class__):
            self_original_unit = self.unit
            self.changeUnit(TemperatureUnit.C)
            if other.unit in (TemperatureUnit.K, TemperatureUnit.C):
                new_value = self.value + other.value
            else:
                new_value = self.value + (other.value - 32) * 5.0 / 9.0
            new_unit = self.__class__(new_value, TemperatureUnit.C)
            new_unit.changeUnit(self_original_unit)
            return new_unit
        elif isinstance(other, (int, float, Decimal)):
            new_value = self + self.__class__(other, self.unit)
            return self.__class__(new_value.value, self.unit)
        else:
            return NotImplemented(f"Cannot add {self.__class__} to {type(other)}")

    def __sub__(self, other):
        self_original_unit = self.unit

        self.changeUnit(TemperatureUnit.K)

        if other.unit in (TemperatureUnit.K, TemperatureUnit.C):
            new_value = self.value - other.value
        else:
            new_value = self.value - (other.value * 5.0 / 9.0)

        new_unit = self.__class__(new_value, TemperatureUnit.C)
        new_unit.changeUnit(self_original_unit)
        return new_unit


class Length(Unit):
    default_unit = settings.DEFAULT_LENGTH_UNIT
    lang_mapping = settings.LANG_LENGTH_MAPPING
    conversions = {
        LengthUnit.MM: 1000,
        LengthUnit.CM: 100,
        LengthUnit.M: 1.0,
        LengthUnit.KM: 0.001,
        LengthUnit.INCH: 39.3701,
        LengthUnit.FT: 3.28084,
        LengthUnit.YD: 1.09361,
        LengthUnit.MI: 0.000621371,
    }


class Mass(Unit):
    default_unit = settings.DEFAULT_MASS_UNIT
    lang_mapping = settings.LANG_MASS_MAPPING
    conversions = {
        MassUnit.KG: 1.0,
        MassUnit.G: 1000.0,
        MassUnit.MG: 1000000.0,
        MassUnit.TON: 1.0 / 1000.0,
        MassUnit.LB: 2.2046226218,
        MassUnit.OZ: 35.274,
    }
