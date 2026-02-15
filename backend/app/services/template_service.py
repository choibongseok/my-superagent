"""Service for template marketplace management."""

import csv
import json
import logging
import math
import re
import textwrap
import unicodedata
from collections.abc import Mapping
from string import Formatter
from typing import List, Optional
from urllib.parse import quote_plus
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.template import Template, TemplateRating
from app.schemas.template import (
    TemplateCreate,
    TemplateSearchRequest,
    TemplateUpdate,
    TemplateRatingCreate,
    TemplateRatingUpdate,
)

logger = logging.getLogger(__name__)


class _TemplateContextDict(dict):
    """Dictionary wrapper supporting attribute-style access in format strings."""

    def __getattr__(self, key: str):
        try:
            return self[key]
        except KeyError as exc:  # pragma: no cover - exercised via Formatter errors
            raise AttributeError(key) from exc


def _to_template_context(value):
    """Recursively wrap mappings for dot-notation template rendering."""
    if isinstance(value, dict):
        return _TemplateContextDict(
            {key: _to_template_context(item) for key, item in value.items()}
        )

    if isinstance(value, list):
        return [_to_template_context(item) for item in value]

    return value


def _tokenize_case_transform(value: object) -> list[str]:
    """Split values into normalized lowercase word tokens for case transforms."""
    text = str(value)
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    text = re.sub(r"[^0-9A-Za-z]+", " ", text)
    return [token.lower() for token in text.strip().split() if token]


def _to_pascal_case(value: object) -> str:
    """Convert values to PascalCase using normalized word tokens."""
    return "".join(token.capitalize() for token in _tokenize_case_transform(value))


def _to_camel_case(value: object) -> str:
    """Convert values to camelCase using normalized word tokens."""
    pascal_case = _to_pascal_case(value)
    if not pascal_case:
        return ""

    return pascal_case[0].lower() + pascal_case[1:]


def _to_json(value: object, *, pretty: bool = False) -> str:
    """Serialize values to JSON for prompt rendering transforms."""
    if pretty:
        return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _to_slug(value: object) -> str:
    """Convert values into a lowercase, hyphen-delimited slug."""
    normalized = unicodedata.normalize("NFKD", str(value))
    without_diacritics = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )

    slug = re.sub(r"[^0-9A-Za-z]+", "-", without_diacritics.lower())
    return slug.strip("-")


def _truncate_text(value: object, max_length_spec: str) -> str:
    """Truncate text to a max length using an ellipsis when needed."""
    try:
        max_length = int(max_length_spec.strip())
    except ValueError as exc:
        raise ValueError("truncate expects an integer max length") from exc

    if max_length < 0:
        raise ValueError("truncate max length must be non-negative")

    text = str(value)
    if len(text) <= max_length:
        return text

    if max_length == 0:
        return ""

    if max_length == 1:
        return "…"

    return text[: max_length - 1].rstrip() + "…"


def _truncate_words(value: object, max_words_spec: str) -> str:
    """Truncate text by word count using an ellipsis when truncation occurs."""
    try:
        max_words = int(max_words_spec.strip())
    except ValueError as exc:
        raise ValueError("truncate_words expects an integer max word count") from exc

    if max_words < 0:
        raise ValueError("truncate_words max word count must be non-negative")

    if max_words == 0:
        return ""

    text = str(value)
    words = re.findall(r"\S+", text)
    if len(words) <= max_words:
        return text

    return " ".join(words[:max_words]) + "…"


def _compact_whitespace(value: object) -> str:
    """Collapse repeated whitespace into single spaces and trim edges."""
    return " ".join(str(value).split())


def _trim_lines(value: object) -> str:
    """Trim each line, normalize newlines, and strip outer blank lines."""
    normalized_text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    normalized_lines = [line.strip() for line in normalized_text.split("\n")]

    while normalized_lines and normalized_lines[0] == "":
        normalized_lines.pop(0)

    while normalized_lines and normalized_lines[-1] == "":
        normalized_lines.pop()

    return "\n".join(normalized_lines)


def _indent_text(value: object, argument_spec: str) -> str:
    """Indent multiline text values with an optional custom prefix."""
    args: list[str] = []
    if argument_spec.strip():
        args = _parse_transform_args(argument_spec)

    if len(args) > 1:
        raise ValueError("indent expects zero or one argument: prefix")

    prefix = args[0] if args else "    "
    if prefix == "":
        raise ValueError("indent prefix must not be empty")

    return textwrap.indent(str(value), prefix)


def _parse_transform_args(argument_spec: str) -> list[str]:
    """Parse comma-separated transform arguments, supporting CSV quoting."""
    try:
        parsed = next(csv.reader([argument_spec], skipinitialspace=True))
    except csv.Error as exc:  # pragma: no cover - handled by validation tests
        raise ValueError("Invalid transform arguments") from exc

    return parsed


def _replace_text(value: object, argument_spec: str) -> str:
    """Replace text using ``replace(search,replacement)`` transform arguments."""
    args = _parse_transform_args(argument_spec)
    if len(args) != 2:
        raise ValueError("replace expects exactly two arguments: search,replacement")

    search, replacement = args
    if search == "":
        raise ValueError("replace search argument must not be empty")

    return str(value).replace(search, replacement)


def _strip_affix_text(value: object, argument_spec: str, *, mode: str) -> str:
    """Strip a single prefix/suffix from text using CSV-quoted arguments."""
    args = _parse_transform_args(argument_spec)
    if len(args) != 1:
        raise ValueError(f"{mode} expects exactly one argument")

    affix = args[0]
    if affix == "":
        raise ValueError(f"{mode} argument must not be empty")

    text = str(value)
    if mode == "strip_prefix":
        return text[len(affix) :] if text.startswith(affix) else text

    if mode == "strip_suffix":
        return text[: -len(affix)] if text.endswith(affix) else text

    raise ValueError(f"Unsupported strip mode: {mode}")


def _apply_text_affix(value: object, argument_spec: str, *, mode: str) -> str:
    """Add a single prefix or suffix using CSV-quoted arguments."""
    args = _parse_transform_args(argument_spec)
    if len(args) != 1:
        raise ValueError(f"{mode} expects exactly one argument")

    affix = args[0]
    if affix == "":
        raise ValueError(f"{mode} argument must not be empty")

    text = str(value)
    if mode == "prepend":
        return f"{affix}{text}"

    if mode == "append":
        return f"{text}{affix}"

    raise ValueError(f"Unsupported affix mode: {mode}")


def _replace_regex_text(value: object, argument_spec: str) -> str:
    """Regex replacement helper for ``replace_regex(pattern,replacement[,flags])``."""
    args = _parse_transform_args(argument_spec)
    if len(args) not in {2, 3}:
        raise ValueError(
            "replace_regex expects two or three arguments: pattern,replacement[,flags]"
        )

    pattern, replacement = args[0], args[1]
    if pattern == "":
        raise ValueError("replace_regex pattern argument must not be empty")

    re_flags = 0
    if len(args) == 3:
        raw_flags = args[2].strip().lower()
        supported_flags = {
            "i": re.IGNORECASE,
            "m": re.MULTILINE,
            "s": re.DOTALL,
            "x": re.VERBOSE,
        }

        for flag in raw_flags:
            mapped_flag = supported_flags.get(flag)
            if mapped_flag is None:
                raise ValueError("replace_regex flags must use only i, m, s, or x")
            re_flags |= mapped_flag

    try:
        compiled_pattern = re.compile(pattern, flags=re_flags)
    except re.error as exc:
        raise ValueError(f"replace_regex pattern is invalid: {exc}") from exc

    return compiled_pattern.sub(replacement, str(value))


def _join_values(value: object, argument_spec: str) -> str:
    """Join iterable values into a single string.

    ``join()`` defaults to `", "` as separator.
    ``join(" | ")`` uses a custom separator.
    """
    args: list[str] = []
    if argument_spec.strip():
        args = _parse_transform_args(argument_spec)

    if len(args) > 1:
        raise ValueError("join expects zero or one argument: separator")

    separator = args[0] if args else ", "

    if isinstance(value, (str, bytes, bytearray)):
        raise ValueError("join expects an iterable value, not a string")

    try:
        iterator = iter(value)
    except TypeError as exc:
        raise ValueError("join expects an iterable value") from exc

    return separator.join(str(item) for item in iterator)


def _split_text(value: object, argument_spec: str) -> list[str]:
    """Split string values into token lists for downstream transforms.

    ``split()`` uses whitespace splitting.
    ``split(",")`` uses a custom separator.
    ``split(",",2)`` supports optional maxsplit control.
    """
    if not isinstance(value, str):
        raise ValueError("split expects a string value")

    args: list[str] = []
    if argument_spec.strip():
        args = _parse_transform_args(argument_spec)

    if len(args) > 2:
        raise ValueError("split expects zero to two arguments: [separator[,maxsplit]]")

    separator: str | None = None
    maxsplit = -1

    if args:
        separator = args[0]
        if separator == "":
            raise ValueError("split separator must not be empty")

    if len(args) == 2:
        try:
            maxsplit = int(args[1].strip())
        except ValueError as exc:
            raise ValueError("split maxsplit must be an integer") from exc

        if maxsplit < -1:
            raise ValueError("split maxsplit must be greater than or equal to -1")

    return value.split(separator, maxsplit)


def _flatten_values(value: object) -> list[object]:
    """Flatten one level of nested iterables while preserving item order."""
    if isinstance(value, (str, bytes, bytearray)):
        raise ValueError("flatten expects an iterable value, not a string")

    try:
        iterator = iter(value)
    except TypeError as exc:
        raise ValueError("flatten expects an iterable value") from exc

    flattened: list[object] = []

    for item in iterator:
        if isinstance(item, (str, bytes, bytearray, Mapping)):
            flattened.append(item)
            continue

        try:
            nested_iterator = iter(item)
        except TypeError:
            flattened.append(item)
            continue

        flattened.extend(nested_iterator)

    return flattened


def _flatten_values_with_args(
    value: object,
    argument_spec: str,
    *,
    transform_name: str = "flatten",
) -> list[object]:
    """Apply flatten transform while rejecting unsupported arguments."""
    if argument_spec.strip():
        raise ValueError(f"{transform_name} expects no arguments")

    return _flatten_values(value)


def _unique_values(value: object) -> list[object]:
    """Return iterable values with duplicates removed in first-seen order."""
    if isinstance(value, (str, bytes, bytearray)):
        raise ValueError("unique expects an iterable value, not a string")

    try:
        iterator = iter(value)
    except TypeError as exc:
        raise ValueError("unique expects an iterable value") from exc

    seen_hashable: set[object] = set()
    seen_unhashable: list[object] = []
    unique_items: list[object] = []

    for item in iterator:
        try:
            if item in seen_hashable:
                continue
            seen_hashable.add(item)
        except TypeError:
            if any(existing == item for existing in seen_unhashable):
                continue
            seen_unhashable.append(item)

        unique_items.append(item)

    return unique_items


def _sort_values(value: object, argument_spec: str) -> list[object]:
    """Sort iterable values with optional ``asc``/``desc`` order selection."""
    if isinstance(value, (str, bytes, bytearray)):
        raise ValueError("sort expects an iterable value, not a string")

    args: list[str] = []
    if argument_spec.strip():
        args = _parse_transform_args(argument_spec)

    if len(args) > 1:
        raise ValueError("sort expects zero or one argument: asc|desc")

    order = args[0].strip().lower() if args else "asc"
    if order == "":
        order = "asc"
    if order not in {"asc", "desc"}:
        raise ValueError("sort argument must be 'asc' or 'desc'")

    try:
        items = list(iter(value))
    except TypeError as exc:
        raise ValueError("sort expects an iterable value") from exc

    reverse = order == "desc"

    if all(isinstance(item, str) for item in items):
        return sorted(items, key=str.casefold, reverse=reverse)

    try:
        return sorted(items, reverse=reverse)
    except TypeError:
        return sorted(items, key=lambda item: str(item), reverse=reverse)


def _reverse_value(value: object) -> object:
    """Reverse strings directly and non-string iterables as lists."""
    if isinstance(value, str):
        return value[::-1]

    if isinstance(value, bytes):
        return value[::-1]

    if isinstance(value, bytearray):
        return value[::-1]

    try:
        items = list(iter(value))
    except TypeError as exc:
        raise ValueError("reverse expects a string or iterable value") from exc

    return list(reversed(items))


def _slice_value(value: object, argument_spec: str) -> object:
    """Slice strings/iterables using ``slice(start[,end[,step]])`` arguments."""
    if not argument_spec.strip():
        raise ValueError("slice expects one to three integer arguments")

    args = _parse_transform_args(argument_spec)
    if len(args) == 0 or len(args) > 3:
        raise ValueError("slice expects one to three arguments: start[,end[,step]]")

    def _parse_index(raw_value: str, *, field_name: str) -> int | None:
        normalized = raw_value.strip()
        if normalized == "":
            return None

        try:
            return int(normalized)
        except ValueError as exc:
            raise ValueError(f"slice {field_name} must be an integer") from exc

    start = _parse_index(args[0], field_name="start")
    end = _parse_index(args[1], field_name="end") if len(args) >= 2 else None
    step = _parse_index(args[2], field_name="step") if len(args) == 3 else None

    if start is None and end is None and step is None:
        raise ValueError("slice requires at least one numeric boundary")

    if step == 0:
        raise ValueError("slice step must not be 0")

    if isinstance(value, (str, bytes, bytearray)):
        return value[start:end:step]

    try:
        items = list(iter(value))
    except TypeError as exc:
        raise ValueError("slice expects a string or iterable value") from exc

    return items[start:end:step]


def _length_of(value: object) -> int:
    """Return collection length for strings, mappings, and iterables."""
    if isinstance(value, (str, bytes, bytearray, list, tuple, dict, set, frozenset)):
        return len(value)

    try:
        return len(value)  # type: ignore[arg-type]
    except TypeError:
        pass

    try:
        return sum(1 for _ in iter(value))
    except TypeError as exc:
        raise ValueError("length expects a sized or iterable value") from exc


def _distinct_count(value: object) -> int:
    """Count unique iterable values while preserving unique() validation semantics."""
    return len(_unique_values(value))


def _round_numeric(value: object, argument_spec: str) -> int | float:
    """Round numeric values with optional decimal precision."""
    args: list[str] = []
    if argument_spec.strip():
        args = _parse_transform_args(argument_spec)

    if len(args) > 1:
        raise ValueError("round expects zero or one argument: ndigits")

    if isinstance(value, bool):
        raise ValueError("round expects a numeric value")

    try:
        numeric_value = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("round expects a numeric value") from exc

    if not args:
        return round(numeric_value)

    try:
        ndigits = int(args[0].strip())
    except ValueError as exc:
        raise ValueError("round ndigits must be an integer") from exc

    return round(numeric_value, ndigits)


def _normalize_numeric_transform_value(value: object, *, transform_name: str) -> float:
    """Normalize numeric inputs for scalar math transforms."""
    if isinstance(value, bool):
        raise ValueError(f"{transform_name} expects a numeric value")

    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{transform_name} expects a numeric value") from exc


def _absolute_numeric(value: object) -> int | float:
    """Return absolute numeric magnitude while preserving integer outputs."""
    numeric_value = _normalize_numeric_transform_value(value, transform_name="abs")
    absolute_value = abs(numeric_value)
    return int(absolute_value) if absolute_value.is_integer() else absolute_value


def _floor_numeric(value: object) -> int:
    """Floor numeric values to the nearest lower integer."""
    numeric_value = _normalize_numeric_transform_value(value, transform_name="floor")
    return math.floor(numeric_value)


def _ceil_numeric(value: object) -> int:
    """Ceil numeric values to the nearest higher integer."""
    numeric_value = _normalize_numeric_transform_value(value, transform_name="ceil")
    return math.ceil(numeric_value)


def _clamp_numeric(value: object, argument_spec: str) -> int | float:
    """Clamp numeric values into an inclusive ``[min,max]`` range."""
    args = _parse_transform_args(argument_spec)
    if len(args) != 2:
        raise ValueError("clamp expects exactly two arguments: min,max")

    if isinstance(value, bool):
        raise ValueError("clamp expects a numeric value")

    try:
        numeric_value = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("clamp expects a numeric value") from exc

    try:
        minimum = float(args[0].strip())
        maximum = float(args[1].strip())
    except ValueError as exc:
        raise ValueError("clamp bounds must be numeric") from exc

    if minimum > maximum:
        raise ValueError("clamp min cannot be greater than max")

    clamped = min(max(numeric_value, minimum), maximum)

    if minimum.is_integer() and maximum.is_integer() and clamped.is_integer():
        return int(clamped)

    return clamped


def _iter_numeric_values(value: object, *, transform_name: str) -> list[float]:
    """Normalize iterable numeric values used by aggregate transforms."""
    if isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{transform_name} expects an iterable value, not a string")

    try:
        iterator = iter(value)
    except TypeError as exc:
        raise ValueError(f"{transform_name} expects an iterable value") from exc

    numeric_values: list[float] = []
    for item in iterator:
        numeric_values.append(
            _normalize_numeric_transform_value(item, transform_name=transform_name)
        )

    return numeric_values


def _sum_numeric_values(value: object, argument_spec: str) -> int | float:
    """Sum iterable numeric values with an optional ``start`` argument."""
    args: list[str] = []
    if argument_spec.strip():
        args = _parse_transform_args(argument_spec)

    if len(args) > 1:
        raise ValueError("sum expects zero or one argument: start")

    start = 0.0
    if args:
        start = _normalize_numeric_transform_value(
            args[0].strip(), transform_name="sum"
        )

    total = start + sum(_iter_numeric_values(value, transform_name="sum"))
    return int(total) if float(total).is_integer() else total


def _product_numeric_values(
    value: object,
    argument_spec: str,
    *,
    transform_name: str = "product",
) -> int | float:
    """Multiply iterable numeric values with an optional ``start`` argument."""
    args: list[str] = []
    if argument_spec.strip():
        args = _parse_transform_args(argument_spec)

    if len(args) > 1:
        raise ValueError(f"{transform_name} expects zero or one argument: start")

    start = 1.0
    if args:
        start = _normalize_numeric_transform_value(
            args[0].strip(), transform_name=transform_name
        )

    product = math.prod(
        _iter_numeric_values(value, transform_name=transform_name), start=start
    )
    return int(product) if float(product).is_integer() else product


def _average_numeric_values(value: object, argument_spec: str) -> int | float:
    """Return mean value for non-empty iterable numeric inputs."""
    if argument_spec.strip():
        raise ValueError("avg expects no arguments")

    numeric_values = _iter_numeric_values(value, transform_name="avg")
    if not numeric_values:
        raise ValueError("avg expects a non-empty iterable value")

    average = sum(numeric_values) / len(numeric_values)
    return int(average) if float(average).is_integer() else average


def _weighted_average_numeric_values(
    value: object,
    argument_spec: str,
    *,
    transform_name: str = "weighted_avg",
) -> int | float:
    """Return weighted average for numeric iterables.

    Arguments are interpreted as numeric weights in the same order as the input
    values: ``weighted_avg(0.2,0.3,0.5)``.
    """
    args = _parse_transform_args(argument_spec)
    if not args:
        raise ValueError(
            f"{transform_name} expects one or more numeric weight arguments"
        )

    numeric_values = _iter_numeric_values(value, transform_name=transform_name)
    if not numeric_values:
        raise ValueError(f"{transform_name} expects a non-empty iterable value")

    try:
        weights = [float(raw_weight.strip()) for raw_weight in args]
    except ValueError as exc:
        raise ValueError(f"{transform_name} weights must be numeric") from exc

    if len(weights) != len(numeric_values):
        raise ValueError(
            f"{transform_name} expects {len(numeric_values)} weights, "
            f"received {len(weights)}"
        )

    total_weight = sum(weights)
    if math.isclose(total_weight, 0.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError(f"{transform_name} total weight must not be zero")

    weighted_average = (
        sum(item * weight for item, weight in zip(numeric_values, weights))
        / total_weight
    )

    rounded_integer = round(weighted_average)
    if math.isclose(weighted_average, rounded_integer, rel_tol=0.0, abs_tol=1e-12):
        return int(rounded_integer)

    return weighted_average


def _geometric_mean_numeric_values(
    value: object,
    argument_spec: str,
    *,
    transform_name: str = "geomean",
) -> int | float:
    """Return geometric mean for non-empty numeric iterables."""
    if argument_spec.strip():
        raise ValueError(f"{transform_name} expects no arguments")

    numeric_values = _iter_numeric_values(value, transform_name=transform_name)
    if not numeric_values:
        raise ValueError(f"{transform_name} expects a non-empty iterable value")

    if any(item < 0 for item in numeric_values):
        raise ValueError(f"{transform_name} expects non-negative numeric values")

    if any(item == 0 for item in numeric_values):
        return 0

    log_sum = sum(math.log(item) for item in numeric_values)
    geometric_mean = math.exp(log_sum / len(numeric_values))

    rounded_integer = round(geometric_mean)
    if math.isclose(geometric_mean, rounded_integer, rel_tol=0.0, abs_tol=1e-12):
        return int(rounded_integer)

    return geometric_mean


def _harmonic_mean_numeric_values(
    value: object,
    argument_spec: str,
    *,
    transform_name: str = "harmmean",
) -> int | float:
    """Return harmonic mean for non-empty positive numeric iterables."""
    if argument_spec.strip():
        raise ValueError(f"{transform_name} expects no arguments")

    numeric_values = _iter_numeric_values(value, transform_name=transform_name)
    if not numeric_values:
        raise ValueError(f"{transform_name} expects a non-empty iterable value")

    if any(item <= 0 for item in numeric_values):
        raise ValueError(f"{transform_name} expects positive numeric values")

    reciprocal_sum = sum(1 / item for item in numeric_values)
    harmonic_mean = len(numeric_values) / reciprocal_sum

    rounded_integer = round(harmonic_mean)
    if math.isclose(harmonic_mean, rounded_integer, rel_tol=0.0, abs_tol=1e-12):
        return int(rounded_integer)

    return harmonic_mean


def _min_numeric_value(value: object, argument_spec: str) -> int | float:
    """Return the minimum numeric value from a non-empty iterable."""
    if argument_spec.strip():
        raise ValueError("min expects no arguments")

    numeric_values = _iter_numeric_values(value, transform_name="min")
    if not numeric_values:
        raise ValueError("min expects a non-empty iterable value")

    minimum = min(numeric_values)
    return int(minimum) if float(minimum).is_integer() else minimum


def _max_numeric_value(value: object, argument_spec: str) -> int | float:
    """Return the maximum numeric value from a non-empty iterable."""
    if argument_spec.strip():
        raise ValueError("max expects no arguments")

    numeric_values = _iter_numeric_values(value, transform_name="max")
    if not numeric_values:
        raise ValueError("max expects a non-empty iterable value")

    maximum = max(numeric_values)
    return int(maximum) if float(maximum).is_integer() else maximum


def _median_numeric_value(value: object, argument_spec: str) -> int | float:
    """Return the median numeric value from a non-empty iterable."""
    if argument_spec.strip():
        raise ValueError("median expects no arguments")

    numeric_values = sorted(_iter_numeric_values(value, transform_name="median"))
    if not numeric_values:
        raise ValueError("median expects a non-empty iterable value")

    midpoint = len(numeric_values) // 2
    if len(numeric_values) % 2 == 1:
        median = numeric_values[midpoint]
    else:
        median = (numeric_values[midpoint - 1] + numeric_values[midpoint]) / 2

    return int(median) if float(median).is_integer() else median


def _percentile_numeric_value(
    value: object,
    argument_spec: str,
    *,
    transform_name: str = "percentile",
) -> int | float:
    """Return an interpolated percentile for non-empty numeric iterables."""
    args = _parse_transform_args(argument_spec)
    if len(args) != 1:
        raise ValueError(f"{transform_name} expects exactly one argument: percentile")

    try:
        percentile = float(args[0].strip())
    except ValueError as exc:
        raise ValueError(f"{transform_name} percentile must be numeric") from exc

    if not 0 <= percentile <= 100:
        raise ValueError(f"{transform_name} percentile must be between 0 and 100")

    numeric_values = sorted(_iter_numeric_values(value, transform_name=transform_name))
    if not numeric_values:
        raise ValueError(f"{transform_name} expects a non-empty iterable value")

    if len(numeric_values) == 1:
        result = numeric_values[0]
    else:
        rank = (percentile / 100) * (len(numeric_values) - 1)
        lower_index = math.floor(rank)
        upper_index = math.ceil(rank)

        lower_value = numeric_values[lower_index]
        upper_value = numeric_values[upper_index]
        interpolation_ratio = rank - lower_index
        result = lower_value + (upper_value - lower_value) * interpolation_ratio

    return int(result) if float(result).is_integer() else result


def _variance_numeric_value(
    value: object,
    argument_spec: str,
    *,
    transform_name: str = "variance",
) -> int | float:
    """Return population variance for non-empty numeric iterables."""
    if argument_spec.strip():
        raise ValueError(f"{transform_name} expects no arguments")

    numeric_values = _iter_numeric_values(value, transform_name=transform_name)
    if not numeric_values:
        raise ValueError(f"{transform_name} expects a non-empty iterable value")

    average = sum(numeric_values) / len(numeric_values)
    variance = sum((item - average) ** 2 for item in numeric_values) / len(
        numeric_values
    )

    return int(variance) if float(variance).is_integer() else variance


def _standard_deviation_numeric_value(value: object, argument_spec: str) -> int | float:
    """Return population standard deviation for non-empty numeric iterables."""
    if argument_spec.strip():
        raise ValueError("stddev expects no arguments")

    variance = _variance_numeric_value(value, "", transform_name="stddev")
    standard_deviation = math.sqrt(float(variance))

    return (
        int(standard_deviation)
        if float(standard_deviation).is_integer()
        else standard_deviation
    )


def _sample_variance_numeric_value(
    value: object,
    argument_spec: str,
    *,
    transform_name: str = "sample_variance",
) -> int | float:
    """Return sample variance (Bessel-corrected) for numeric iterables."""
    if argument_spec.strip():
        raise ValueError(f"{transform_name} expects no arguments")

    numeric_values = _iter_numeric_values(value, transform_name=transform_name)
    if len(numeric_values) < 2:
        raise ValueError(f"{transform_name} expects at least two numeric values")

    average = sum(numeric_values) / len(numeric_values)
    variance = sum((item - average) ** 2 for item in numeric_values) / (
        len(numeric_values) - 1
    )

    return int(variance) if float(variance).is_integer() else variance


def _sample_standard_deviation_numeric_value(
    value: object,
    argument_spec: str,
    *,
    transform_name: str = "sample_stddev",
) -> int | float:
    """Return sample standard deviation for numeric iterables."""
    if argument_spec.strip():
        raise ValueError(f"{transform_name} expects no arguments")

    variance = _sample_variance_numeric_value(
        value,
        "",
        transform_name=transform_name,
    )
    standard_deviation = math.sqrt(float(variance))

    return (
        int(standard_deviation)
        if float(standard_deviation).is_integer()
        else standard_deviation
    )


def _mode_value(value: object, argument_spec: str) -> object:
    """Return the most frequent item from a non-empty iterable.

    Tie-breaking is deterministic and preserves the first value that reached
    the highest frequency.
    """
    if argument_spec.strip():
        raise ValueError("mode expects no arguments")

    if isinstance(value, (str, bytes, bytearray)):
        raise ValueError("mode expects an iterable value, not a string")

    try:
        iterator = iter(value)
    except TypeError as exc:
        raise ValueError("mode expects an iterable value") from exc

    hashable_counts: dict[object, int] = {}
    unhashable_items: list[object] = []
    unhashable_counts: list[int] = []

    best_item: object | None = None
    best_count = 0
    found_any = False

    for item in iterator:
        found_any = True
        try:
            count = hashable_counts.get(item, 0) + 1
            hashable_counts[item] = count
        except TypeError:
            count = 1
            for index, existing in enumerate(unhashable_items):
                if existing == item:
                    unhashable_counts[index] += 1
                    count = unhashable_counts[index]
                    break
            else:
                unhashable_items.append(item)
                unhashable_counts.append(1)

        if count > best_count:
            best_item = item
            best_count = count

    if not found_any:
        raise ValueError("mode expects a non-empty iterable value")

    return best_item


def _range_numeric_value(value: object, argument_spec: str) -> int | float:
    """Return numeric spread (max-min) for non-empty numeric iterables."""
    if argument_spec.strip():
        raise ValueError("range expects no arguments")

    numeric_values = _iter_numeric_values(value, transform_name="range")
    if not numeric_values:
        raise ValueError("range expects a non-empty iterable value")

    spread = max(numeric_values) - min(numeric_values)
    return int(spread) if float(spread).is_integer() else spread


def _interquartile_range_numeric_value(
    value: object,
    argument_spec: str,
    *,
    transform_name: str = "iqr",
) -> int | float:
    """Return interquartile range (Q3-Q1) for non-empty numeric iterables."""
    if argument_spec.strip():
        raise ValueError(f"{transform_name} expects no arguments")

    numeric_values = _iter_numeric_values(value, transform_name=transform_name)
    if not numeric_values:
        raise ValueError(f"{transform_name} expects a non-empty iterable value")

    first_quartile = float(
        _percentile_numeric_value(numeric_values, "25", transform_name=transform_name)
    )
    third_quartile = float(
        _percentile_numeric_value(numeric_values, "75", transform_name=transform_name)
    )
    interquartile_range = third_quartile - first_quartile

    return (
        int(interquartile_range)
        if float(interquartile_range).is_integer()
        else interquartile_range
    )


def _fallback_value(value: object, argument_spec: str) -> object:
    """Return fallback when values are missing, blank, or empty collections."""
    args = _parse_transform_args(argument_spec)
    if len(args) != 1:
        raise ValueError("fallback expects exactly one argument: value")

    fallback = args[0]

    if value is None:
        return fallback

    if isinstance(value, str) and value.strip() == "":
        return fallback

    if isinstance(value, (bytes, bytearray)) and len(value) == 0:
        return fallback

    try:
        if len(value) == 0:  # type: ignore[arg-type]
            return fallback
    except TypeError:
        pass

    return value


def _select_boundary_item(value: object, boundary: str) -> object:
    """Select the first/last item from a non-string iterable."""
    if boundary not in {"first", "last"}:
        raise ValueError("boundary must be either 'first' or 'last'")

    if isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{boundary} expects an iterable value, not a string")

    try:
        iterator = iter(value)
    except TypeError as exc:
        raise ValueError(f"{boundary} expects an iterable value") from exc

    try:
        first_item = next(iterator)
    except StopIteration as exc:
        raise ValueError(f"{boundary} expects a non-empty iterable value") from exc

    if boundary == "first":
        return first_item

    last_item = first_item
    for item in iterator:
        last_item = item

    return last_item


class TemplateService:
    """Service for template management."""

    def __init__(self, db: AsyncSession):
        """
        Initialize template service.

        Args:
            db: Database session
        """
        self.db = db

    async def create_template(
        self, template_data: TemplateCreate, author_id: UUID
    ) -> Template:
        """
        Create a new template.

        Args:
            template_data: Template creation data
            author_id: Author user ID

        Returns:
            Created template
        """
        template = Template(
            name=template_data.name,
            description=template_data.description,
            category=template_data.category,
            tags={"tags": template_data.tags} if template_data.tags else None,
            author_id=author_id,
            team_id=template_data.team_id,
            prompt_template=template_data.prompt_template,
            parameters=template_data.parameters,
            example_inputs=template_data.example_inputs,
            example_outputs=template_data.example_outputs,
            is_public=template_data.is_public,
        )

        self.db.add(template)
        await self.db.commit()
        await self.db.refresh(template)

        logger.info(f"Template created: {template.id} by user {author_id}")

        return template

    async def get_template(self, template_id: UUID) -> Optional[Template]:
        """
        Get template by ID.

        Args:
            template_id: Template ID

        Returns:
            Template or None if not found
        """
        result = await self.db.execute(
            select(Template).where(Template.id == template_id)
        )
        return result.scalar_one_or_none()

    async def update_template(
        self,
        template_id: UUID,
        template_data: TemplateUpdate,
        user_id: UUID,
    ) -> Optional[Template]:
        """
        Update template.

        Args:
            template_id: Template ID
            template_data: Update data
            user_id: Requesting user ID

        Returns:
            Updated template or None if not found/unauthorized
        """
        template = await self.get_template(template_id)

        if not template or template.author_id != user_id:
            return None

        # Update fields
        update_data = template_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if field == "tags" and value is not None:
                setattr(template, field, {"tags": value})
            else:
                setattr(template, field, value)

        await self.db.commit()
        await self.db.refresh(template)

        logger.info(f"Template updated: {template_id}")

        return template

    async def delete_template(self, template_id: UUID, user_id: UUID) -> bool:
        """
        Delete template.

        Args:
            template_id: Template ID
            user_id: Requesting user ID

        Returns:
            True if deleted, False if not found/unauthorized
        """
        template = await self.get_template(template_id)

        if not template or template.author_id != user_id:
            return False

        await self.db.delete(template)
        await self.db.commit()

        logger.info(f"Template deleted: {template_id}")

        return True

    async def search_templates(
        self, search_request: TemplateSearchRequest, user_id: Optional[UUID] = None
    ) -> tuple[List[Template], int]:
        """
        Search templates with filters.

        Args:
            search_request: Search parameters
            user_id: Optional user ID for personalized results

        Returns:
            Tuple of (templates, total_count)
        """
        # Base query: public templates or user's own templates
        query = select(Template).where(
            or_(Template.is_public == True, Template.author_id == user_id)
            if user_id
            else Template.is_public == True
        )

        # Apply filters
        if search_request.query:
            query = query.where(
                or_(
                    Template.name.ilike(f"%{search_request.query}%"),
                    Template.description.ilike(f"%{search_request.query}%"),
                )
            )

        if search_request.category:
            query = query.where(Template.category == search_request.category)

        if search_request.tags:
            # Filter by tags (JSON array contains)
            for tag in search_request.tags:
                query = query.where(func.jsonb_exists(Template.tags, f"tags.{tag}"))

        if search_request.author_id:
            query = query.where(Template.author_id == search_request.author_id)

        if search_request.is_official is not None:
            query = query.where(Template.is_official == search_request.is_official)

        if search_request.is_featured is not None:
            query = query.where(Template.is_featured == search_request.is_featured)

        if search_request.min_rating is not None:
            query = query.where(Template.rating >= search_request.min_rating)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply sorting
        sort_column = getattr(Template, search_request.sort_by, Template.usage_count)
        if search_request.sort_order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        # Apply pagination
        query = query.limit(search_request.limit).offset(search_request.offset)

        # Execute query
        result = await self.db.execute(query)
        templates = list(result.scalars().all())

        logger.info(f"Template search: {len(templates)} results (total: {total})")

        return templates, total

    @staticmethod
    def _parse_field_expression(field_name: str) -> tuple[str, str | None, list[str]]:
        """Parse template field expressions.

        Supported syntax:
        - ``{field}``
        - ``{field|default value}``
        - ``{field->upper}``
        - ``{field|default value->strip->title}``
        - ``{summary->truncate(120)}``
        - ``{name->replace("Agent", "Assistant")}``
        - ``{title->replace_regex("agent","assistant","i")}``
        - ``{path->strip_prefix("/tmp/")->strip_suffix(".txt")}``
        - ``{tags_csv->split(",")->unique->sort(desc)->join(" | ")}``
        - ``{owner_groups->flatten->unique->sort->join(", ")}``
        - ``{items->length}``
        - ``{owners->distinct_count}``
        - ``{backlog->first}``, ``{backlog->last}``
        - ``{steps->reverse->join(" | ")}``
        - ``{milestones->slice(0,2)->join(", ")}``
        - ``{items->slice(0,10,2)->join(", ")}``
        - ``{notes->dedent->indent("  ")->strip}``
        - ``{search_query->urlencode}``
        - ``{title->slug}``
        - ``{summary->compact}``
        - ``{notes->trim_lines}``
        - ``{ticket->prepend("#")}``, ``{title->append(" ✅")}``
        - ``{score->round(2)}``
        - ``{delta->abs}``
        - ``{estimate->floor}``, ``{estimate->ceil}``
        - ``{score->clamp(0,1)->round(2)}``
        - ``{durations->sum}``, ``{durations->sum(10)}``
        - ``{durations->product}``, ``{durations->product(0.5)}``
        - ``{durations->avg}``
        - ``{durations->weighted_avg(0.2,0.3,0.5)}``, ``{durations->wavg(0.2,0.3,0.5)}``
        - ``{durations->geomean}``, ``{durations->gmean}``
        - ``{durations->harmmean}``, ``{durations->hmean}``, ``{durations->harmonic_mean}``
        - ``{latencies->min}``, ``{latencies->max}``, ``{latencies->median}``
        - ``{latencies->percentile(95)}``, ``{latencies->pctl(90)}``
        - ``{latencies->variance}``, ``{latencies->var}``
        - ``{latencies->stddev}``, ``{latencies->stdev}``
        - ``{latencies->sample_variance}``, ``{latencies->svar}``
        - ``{latencies->sample_stddev}``, ``{latencies->sstddev}``
        - ``{latencies->range}``
        - ``{latencies->iqr}``, ``{latencies->interquartile_range}``
        - ``{labels->mode}``
        - ``{nickname->strip->fallback("friend")}``

        Returns:
            Tuple of ``(field_path, default_value, transforms)``.
        """
        base_expression, *transform_parts = field_name.split("->")

        transforms = [part.strip() for part in transform_parts if part.strip()]

        if "|" not in base_expression:
            return base_expression.strip(), None, transforms

        field_path, default_value = base_expression.split("|", 1)
        return field_path.strip(), default_value.strip(), transforms

    @staticmethod
    def _apply_template_transforms(value: object, transforms: list[str]) -> object:
        """Apply text transforms declared in a template field expression."""
        if not transforms:
            return value

        available_transforms = {
            "strip": lambda raw: str(raw).strip(),
            "upper": lambda raw: str(raw).upper(),
            "lower": lambda raw: str(raw).lower(),
            "title": lambda raw: str(raw).title(),
            "capitalize": lambda raw: str(raw).capitalize(),
            "dedent": lambda raw: textwrap.dedent(str(raw)),
            "compact": _compact_whitespace,
            "trim_lines": _trim_lines,
            "indent": lambda raw: _indent_text(raw, ""),
            "snake_case": lambda raw: "_".join(_tokenize_case_transform(raw)),
            "kebab_case": lambda raw: "-".join(_tokenize_case_transform(raw)),
            "dot_case": lambda raw: ".".join(_tokenize_case_transform(raw)),
            "constant_case": lambda raw: "_".join(
                _tokenize_case_transform(raw)
            ).upper(),
            "camel_case": _to_camel_case,
            "pascal_case": _to_pascal_case,
            "json": lambda raw: _to_json(raw, pretty=False),
            "json_pretty": lambda raw: _to_json(raw, pretty=True),
            "urlencode": lambda raw: quote_plus(str(raw), safe=""),
            "slug": _to_slug,
            "split": lambda raw: _split_text(raw, ""),
            "flatten": _flatten_values,
            "flat": _flatten_values,
            "unique": _unique_values,
            "sort": lambda raw: _sort_values(raw, ""),
            "length": _length_of,
            "distinct_count": _distinct_count,
            "first": lambda raw: _select_boundary_item(raw, "first"),
            "last": lambda raw: _select_boundary_item(raw, "last"),
            "reverse": _reverse_value,
            "round": lambda raw: _round_numeric(raw, ""),
            "abs": _absolute_numeric,
            "floor": _floor_numeric,
            "ceil": _ceil_numeric,
            "clamp": lambda raw: _clamp_numeric(raw, ""),
            "sum": lambda raw: _sum_numeric_values(raw, ""),
            "product": lambda raw: _product_numeric_values(raw, ""),
            "prod": lambda raw: _product_numeric_values(
                raw,
                "",
                transform_name="prod",
            ),
            "avg": lambda raw: _average_numeric_values(raw, ""),
            "mean": lambda raw: _average_numeric_values(raw, ""),
            "geomean": lambda raw: _geometric_mean_numeric_values(raw, ""),
            "gmean": lambda raw: _geometric_mean_numeric_values(
                raw,
                "",
                transform_name="gmean",
            ),
            "harmmean": lambda raw: _harmonic_mean_numeric_values(raw, ""),
            "hmean": lambda raw: _harmonic_mean_numeric_values(
                raw,
                "",
                transform_name="hmean",
            ),
            "harmonic_mean": lambda raw: _harmonic_mean_numeric_values(
                raw,
                "",
                transform_name="harmonic_mean",
            ),
            "min": lambda raw: _min_numeric_value(raw, ""),
            "max": lambda raw: _max_numeric_value(raw, ""),
            "median": lambda raw: _median_numeric_value(raw, ""),
            "variance": lambda raw: _variance_numeric_value(raw, ""),
            "var": lambda raw: _variance_numeric_value(raw, "", transform_name="var"),
            "stddev": lambda raw: _standard_deviation_numeric_value(raw, ""),
            "stdev": lambda raw: _standard_deviation_numeric_value(raw, ""),
            "sample_variance": lambda raw: _sample_variance_numeric_value(raw, ""),
            "svar": lambda raw: _sample_variance_numeric_value(
                raw,
                "",
                transform_name="svar",
            ),
            "sample_stddev": lambda raw: _sample_standard_deviation_numeric_value(
                raw,
                "",
            ),
            "sstddev": lambda raw: _sample_standard_deviation_numeric_value(
                raw,
                "",
                transform_name="sstddev",
            ),
            "range": lambda raw: _range_numeric_value(raw, ""),
            "iqr": lambda raw: _interquartile_range_numeric_value(raw, ""),
            "interquartile_range": lambda raw: _interquartile_range_numeric_value(
                raw,
                "",
                transform_name="interquartile_range",
            ),
            "mode": lambda raw: _mode_value(raw, ""),
        }
        supported_transforms = sorted(
            [
                *available_transforms.keys(),
                "truncate(<max_length>)",
                "truncate_words(<max_words>)",
                "replace(<search>,<replacement>)",
                "replace_regex(<pattern>,<replacement>[,<flags>])",
                "strip_prefix(<prefix>)",
                "strip_suffix(<suffix>)",
                "prepend(<prefix>)",
                "append(<suffix>)",
                "join([separator])",
                "split([separator[,maxsplit]])",
                "flatten",
                "flat",
                "sort([asc|desc])",
                "distinct_count",
                "slice(<start>[,<end>[,<step>]])",
                "fallback(<value>)",
                "indent([prefix])",
                "round([ndigits])",
                "clamp(<min>,<max>)",
                "sum([start])",
                "product([start])",
                "prod([start])",
                "avg",
                "mean",
                "weighted_avg(<w1>[,<w2>...])",
                "wavg(<w1>[,<w2>...])",
                "geomean",
                "gmean",
                "harmmean",
                "hmean",
                "harmonic_mean",
                "min",
                "max",
                "median",
                "percentile(<p>)",
                "pctl(<p>)",
                "variance",
                "var",
                "stddev",
                "stdev",
                "sample_variance",
                "svar",
                "sample_stddev",
                "sstddev",
                "range",
                "iqr",
                "interquartile_range",
                "mode",
            ]
        )

        transformed = value
        for transform in transforms:
            normalized_transform = transform.lower()
            operation = available_transforms.get(normalized_transform)

            function_match = re.fullmatch(
                r"([a-z_]+)\((.*)\)", transform, flags=re.IGNORECASE
            )
            if operation is None and function_match is not None:
                transform_name = function_match.group(1).lower()
                argument_spec = function_match.group(2)

                if transform_name == "truncate":
                    operation = lambda raw, spec=argument_spec: _truncate_text(
                        raw, spec
                    )
                elif transform_name == "truncate_words":
                    operation = lambda raw, spec=argument_spec: _truncate_words(
                        raw,
                        spec,
                    )
                elif transform_name == "replace":
                    operation = lambda raw, spec=argument_spec: _replace_text(raw, spec)
                elif transform_name == "replace_regex":
                    operation = lambda raw, spec=argument_spec: _replace_regex_text(
                        raw,
                        spec,
                    )
                elif transform_name == "strip_prefix":
                    operation = lambda raw, spec=argument_spec: _strip_affix_text(
                        raw,
                        spec,
                        mode="strip_prefix",
                    )
                elif transform_name == "strip_suffix":
                    operation = lambda raw, spec=argument_spec: _strip_affix_text(
                        raw,
                        spec,
                        mode="strip_suffix",
                    )
                elif transform_name == "prepend":
                    operation = lambda raw, spec=argument_spec: _apply_text_affix(
                        raw,
                        spec,
                        mode="prepend",
                    )
                elif transform_name == "append":
                    operation = lambda raw, spec=argument_spec: _apply_text_affix(
                        raw,
                        spec,
                        mode="append",
                    )
                elif transform_name == "join":
                    operation = lambda raw, spec=argument_spec: _join_values(raw, spec)
                elif transform_name == "split":
                    operation = lambda raw, spec=argument_spec: _split_text(raw, spec)
                elif transform_name in {"flatten", "flat"}:
                    operation = lambda raw, spec=argument_spec, name=transform_name: _flatten_values_with_args(
                        raw,
                        spec,
                        transform_name=name,
                    )
                elif transform_name == "sort":
                    operation = lambda raw, spec=argument_spec: _sort_values(raw, spec)
                elif transform_name == "slice":
                    operation = lambda raw, spec=argument_spec: _slice_value(raw, spec)
                elif transform_name == "fallback":
                    operation = lambda raw, spec=argument_spec: _fallback_value(
                        raw,
                        spec,
                    )
                elif transform_name == "indent":
                    operation = lambda raw, spec=argument_spec: _indent_text(raw, spec)
                elif transform_name == "round":
                    operation = lambda raw, spec=argument_spec: _round_numeric(
                        raw, spec
                    )
                elif transform_name == "clamp":
                    operation = lambda raw, spec=argument_spec: _clamp_numeric(
                        raw, spec
                    )
                elif transform_name == "sum":
                    operation = lambda raw, spec=argument_spec: _sum_numeric_values(
                        raw, spec
                    )
                elif transform_name in {"product", "prod"}:
                    operation = lambda raw, spec=argument_spec, name=transform_name: _product_numeric_values(
                        raw,
                        spec,
                        transform_name=name,
                    )
                elif transform_name in {"avg", "mean"}:
                    operation = lambda raw, spec=argument_spec: _average_numeric_values(
                        raw,
                        spec,
                    )
                elif transform_name in {"weighted_avg", "wavg"}:
                    operation = lambda raw, spec=argument_spec, name=transform_name: _weighted_average_numeric_values(
                        raw,
                        spec,
                        transform_name=name,
                    )
                elif transform_name in {"geomean", "gmean"}:
                    operation = lambda raw, spec=argument_spec, name=transform_name: _geometric_mean_numeric_values(
                        raw,
                        spec,
                        transform_name=name,
                    )
                elif transform_name in {"harmmean", "hmean", "harmonic_mean"}:
                    operation = lambda raw, spec=argument_spec, name=transform_name: _harmonic_mean_numeric_values(
                        raw,
                        spec,
                        transform_name=name,
                    )
                elif transform_name == "min":
                    operation = lambda raw, spec=argument_spec: _min_numeric_value(
                        raw,
                        spec,
                    )
                elif transform_name == "max":
                    operation = lambda raw, spec=argument_spec: _max_numeric_value(
                        raw,
                        spec,
                    )
                elif transform_name == "median":
                    operation = lambda raw, spec=argument_spec: _median_numeric_value(
                        raw,
                        spec,
                    )
                elif transform_name in {"percentile", "pctl"}:
                    operation = lambda raw, spec=argument_spec, name=transform_name: _percentile_numeric_value(
                        raw,
                        spec,
                        transform_name=name,
                    )
                elif transform_name in {"variance", "var"}:
                    operation = lambda raw, spec=argument_spec, name=transform_name: _variance_numeric_value(
                        raw,
                        spec,
                        transform_name=name,
                    )
                elif transform_name in {"stddev", "stdev"}:
                    operation = lambda raw, spec=argument_spec: _standard_deviation_numeric_value(
                        raw,
                        spec,
                    )
                elif transform_name in {"sample_variance", "svar"}:
                    operation = lambda raw, spec=argument_spec, name=transform_name: _sample_variance_numeric_value(
                        raw,
                        spec,
                        transform_name=name,
                    )
                elif transform_name in {"sample_stddev", "sstddev"}:
                    operation = lambda raw, spec=argument_spec, name=transform_name: _sample_standard_deviation_numeric_value(
                        raw,
                        spec,
                        transform_name=name,
                    )
                elif transform_name == "range":
                    operation = lambda raw, spec=argument_spec: _range_numeric_value(
                        raw,
                        spec,
                    )
                elif transform_name in {"iqr", "interquartile_range"}:
                    operation = lambda raw, spec=argument_spec, name=transform_name: _interquartile_range_numeric_value(
                        raw,
                        spec,
                        transform_name=name,
                    )
                elif transform_name == "mode":
                    operation = lambda raw, spec=argument_spec: _mode_value(raw, spec)

            if operation is None:
                supported = ", ".join(supported_transforms)
                raise ValueError(
                    f"Unsupported template transform: {transform}. "
                    f"Supported transforms: {supported}"
                )

            try:
                transformed = operation(transformed)
            except Exception as exc:
                raise ValueError(
                    f"Failed to apply template transform '{transform}': {exc}"
                ) from exc

        return transformed

    @classmethod
    def _extract_template_variables(cls, prompt_template: str) -> set[str]:
        """Extract required top-level variables from a format-style template.

        Fields declared with ``|`` default syntax (e.g. ``{audience|general}``)
        are treated as optional and excluded from the required input set.
        Optional ``->transform`` directives do not affect required field
        detection.
        """
        variables: set[str] = set()
        for _, field_name, _, _ in Formatter().parse(prompt_template):
            if not field_name:
                continue

            resolved_field, default_value, _ = cls._parse_field_expression(field_name)
            if default_value is not None:
                continue

            # Handle nested field access like {user.name} or {user[name]}
            base_field = resolved_field.split(".", 1)[0].split("[", 1)[0]
            if base_field:
                variables.add(base_field)

        return variables

    @staticmethod
    def _should_apply_default(value: object) -> bool:
        """Return whether a resolved value should fall back to a template default."""
        if value is None:
            return True

        if isinstance(value, str) and value.strip() == "":
            return True

        return False

    @classmethod
    def _render_prompt_template(cls, prompt_template: str, inputs: dict) -> str:
        """Render prompt template and validate required inputs.

        Supports nested input interpolation via dot notation (``{user.name}``) and
        bracket access (``{items[0][title]}``) when ``inputs`` contains nested
        dictionaries/lists.

        Also supports optional defaults via ``field|default`` syntax (for example
        ``{audience|general audience}``) and text transforms via ``->`` (for
        example ``{audience->upper}``, ``{name|friend->title}``,
        ``{project_name->snake_case}``, ``{release_title->kebab_case}``,
        ``{service->dot_case}``, ``{build_target->constant_case}``,
        ``{variable->camel_case}``, ``{variable->pascal_case}``,
        ``{summary->truncate(120)}``, ``{summary->truncate_words(40)}``,
        ``{title->replace("Agent", "Assistant")}``,
        ``{title->replace_regex("agent","assistant","i")}``,
        ``{path->strip_prefix("/tmp/")->strip_suffix(".txt")}``,
        ``{tags_csv->split(",")->unique->sort(desc)->join(" | ")}``,
        ``{owner_groups->flatten->unique->sort->join(", ")}``, ``{items->length}``,
        ``{owners->distinct_count}``, ``{queue->first}``, ``{queue->last}``,
        ``{tasks->reverse}``,
        ``{milestones->slice(0,2)}``, ``{items->slice(0,10,2)}``,
        ``{notes->dedent->indent("> ")->strip}``,
        ``{payload->json}``, ``{payload->json_pretty}``,
        ``{search_query->urlencode}``, ``{title->slug}``,
        ``{summary->compact}``, ``{notes->trim_lines}``,
        ``{ticket->prepend("#")}``,
        ``{title->append(" ✅")}``, ``{score->round(2)}``,
        ``{delta->abs}``, ``{estimate->floor}``, ``{estimate->ceil}``,
        ``{score->clamp(0,1)->round(2)}``,
        ``{durations->sum}``, ``{durations->sum(10)}``,
        ``{durations->product}``, ``{durations->product(0.5)}``,
        ``{durations->avg}``,
        ``{durations->weighted_avg(0.2,0.3,0.5)}``, ``{durations->wavg(0.2,0.3,0.5)}``,
        ``{durations->geomean}``, ``{durations->gmean}``,
        ``{latencies->min}``, ``{latencies->max}``,
        ``{latencies->median}``, ``{latencies->percentile(95)}``,
        ``{latencies->pctl(90)}``,
        ``{latencies->variance}``, ``{latencies->var}``,
        ``{latencies->stddev}``, ``{latencies->stdev}``,
        ``{latencies->sample_variance}``, ``{latencies->svar}``,
        ``{latencies->sample_stddev}``, ``{latencies->sstddev}``,
        ``{latencies->iqr}``, ``{latencies->interquartile_range}``,
        ``{labels->mode}``, or ``{nickname->strip->fallback("friend")}``).
        """
        required_inputs = cls._extract_template_variables(prompt_template)
        missing_inputs = sorted(key for key in required_inputs if key not in inputs)
        if missing_inputs:
            missing = ", ".join(missing_inputs)
            raise ValueError(f"Missing template inputs: {missing}")

        formatter = Formatter()
        context = _to_template_context(inputs)
        rewritten_parts: list[str] = []
        resolved_values: dict[str, object] = {}

        for index, (literal, field_name, format_spec, conversion) in enumerate(
            formatter.parse(prompt_template)
        ):
            rewritten_parts.append(literal.replace("{", "{{").replace("}", "}}"))
            if field_name is None:
                continue

            resolved_field, default_value, transforms = cls._parse_field_expression(
                field_name
            )
            placeholder = f"__field_{index}__"

            rebuilt_field = "{" + placeholder
            if conversion:
                rebuilt_field += f"!{conversion}"
            if format_spec:
                rebuilt_field += f":{format_spec}"
            rebuilt_field += "}"
            rewritten_parts.append(rebuilt_field)

            try:
                value, _ = formatter.get_field(resolved_field, (), context)
            except (KeyError, ValueError, AttributeError, IndexError, TypeError) as exc:
                if default_value is None:
                    raise ValueError(f"Failed to render template: {exc}") from exc
                value = default_value
            else:
                if default_value is not None and cls._should_apply_default(value):
                    value = default_value

            value = cls._apply_template_transforms(value, transforms)
            resolved_values[placeholder] = value

        try:
            rewritten_template = "".join(rewritten_parts)
            return rewritten_template.format_map(_to_template_context(resolved_values))
        except (KeyError, ValueError, AttributeError, IndexError, TypeError) as exc:
            raise ValueError(f"Failed to render template: {exc}") from exc

    async def use_template(
        self,
        template_id: UUID,
        inputs: dict,
        user_id: UUID,
        output_type: str | None = None,
    ) -> dict:
        """
        Use a template with inputs to generate prompt.

        Args:
            template_id: Template ID
            inputs: Input values for template variables
            user_id: User ID
            output_type: Optional output type override

        Returns:
            Dict with template_id, prompt, and suggested output_type
        """
        template = await self.get_template(template_id)

        if not template:
            raise ValueError(f"Template not found: {template_id}")

        prompt = self._render_prompt_template(template.prompt_template, inputs)

        # Increment usage count only after successful prompt rendering
        template.usage_count += 1
        await self.db.commit()

        selected_output_type = (output_type or template.category).strip()

        logger.info(f"Template {template_id} used by user {user_id}")

        return {
            "template_id": str(template_id),
            "prompt": prompt,
            "output_type": selected_output_type,
        }

    # Rating methods

    async def create_rating(
        self,
        template_id: UUID,
        user_id: UUID,
        rating_data: TemplateRatingCreate,
    ) -> TemplateRating:
        """
        Create or update template rating.

        Args:
            template_id: Template ID
            user_id: User ID
            rating_data: Rating data

        Returns:
            Created/updated rating
        """
        # Check if rating exists
        result = await self.db.execute(
            select(TemplateRating).where(
                TemplateRating.template_id == template_id,
                TemplateRating.user_id == user_id,
            )
        )
        existing_rating = result.scalar_one_or_none()

        if existing_rating:
            # Update existing rating
            old_rating = existing_rating.rating
            existing_rating.rating = rating_data.rating
            existing_rating.review = rating_data.review
            rating = existing_rating
        else:
            # Create new rating
            rating = TemplateRating(
                template_id=template_id,
                user_id=user_id,
                rating=rating_data.rating,
                review=rating_data.review,
            )
            self.db.add(rating)
            old_rating = None

        await self.db.commit()
        await self.db.refresh(rating)

        # Update template rating average
        await self._update_template_rating(template_id)

        logger.info(f"Rating created/updated for template {template_id}")

        return rating

    async def _update_template_rating(self, template_id: UUID):
        """Update template's average rating and count."""
        result = await self.db.execute(
            select(
                func.avg(TemplateRating.rating),
                func.count(TemplateRating.id),
            ).where(TemplateRating.template_id == template_id)
        )
        avg_rating, count = result.one()

        template = await self.get_template(template_id)
        if template:
            template.rating = float(avg_rating or 0.0)
            template.rating_count = count or 0
            await self.db.commit()

    async def get_template_ratings(
        self, template_id: UUID, limit: int = 20, offset: int = 0
    ) -> tuple[List[TemplateRating], int]:
        """
        Get ratings for template.

        Args:
            template_id: Template ID
            limit: Page limit
            offset: Page offset

        Returns:
            Tuple of (ratings, total_count)
        """
        # Count total
        count_result = await self.db.execute(
            select(func.count()).where(TemplateRating.template_id == template_id)
        )
        total = count_result.scalar() or 0

        # Get ratings
        result = await self.db.execute(
            select(TemplateRating)
            .where(TemplateRating.template_id == template_id)
            .order_by(TemplateRating.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        ratings = list(result.scalars().all())

        return ratings, total

    async def get_user_templates(
        self, user_id: UUID, limit: int = 20, offset: int = 0
    ) -> tuple[List[Template], int]:
        """
        Get templates created by user.

        Args:
            user_id: User ID
            limit: Page limit
            offset: Page offset

        Returns:
            Tuple of (templates, total_count)
        """
        # Count total
        count_result = await self.db.execute(
            select(func.count()).where(Template.author_id == user_id)
        )
        total = count_result.scalar() or 0

        # Get templates
        result = await self.db.execute(
            select(Template)
            .where(Template.author_id == user_id)
            .order_by(Template.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        templates = list(result.scalars().all())

        return templates, total


__all__ = ["TemplateService"]
