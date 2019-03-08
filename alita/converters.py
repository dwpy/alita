import math
from alita.base import BaseConverter


class StringConverter(BaseConverter):
    regex = "[^/]+"

    def convert(self, value):
        return value

    def to_string(self, value):
        value = str(value)
        assert "/" not in value, "May not contain path seperators"
        assert value, "Must not be empty"
        return value


class PathConverter(BaseConverter):
    regex = ".*"

    def convert(self, value):
        return str(value)

    def to_string(self, value):
        return str(value)


class IntegerConverter(BaseConverter):
    regex = "[0-9]+"

    def convert(self, value):
        return int(value)

    def to_string(self, value):
        value = int(value)
        assert value >= 0, "Negative integers are not supported"
        return str(value)


class FloatConverter(BaseConverter):
    regex = "[0-9]+(.[0-9]+)?"

    def convert(self, value):
        return float(value)

    def to_string(self, value):
        value = float(value)
        assert value >= 0.0, "Negative floats are not supported"
        assert not math.isnan(value), "NaN values are not supported"
        assert not math.isinf(value), "Infinite values are not supported"
        return ("%0.20f" % value).rstrip("0").rstrip(".")


CONVERTER_TYPES = {
    "str": StringConverter(),
    "path": PathConverter(),
    "int": IntegerConverter(),
    "float": FloatConverter(),
}
