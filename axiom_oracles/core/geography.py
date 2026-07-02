from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


_GEOID_LENGTHS = {
    "census_state": 2,
    "census_county": 5,
    "census_place": 7,
    "census_tract": 11,
    "census_block": 15,
    "puma": 7,
    "zcta": 5,
}

_SUPPORTED_COUNTRIES = frozenset({"BE", "UK", "US"})


@dataclass(frozen=True)
class GeographyScope:
    """A typed geography identifier for comparison scoping.

    `geoid` is intentionally overloaded. Its meaning comes from `type`.
    """

    type: str
    geoid: str
    vintage: int | None = None

    def __post_init__(self) -> None:
        scope_type = self.type.lower().replace("-", "_")
        geoid = str(self.geoid).upper() if scope_type == "country" else str(self.geoid)
        object.__setattr__(self, "type", scope_type)
        object.__setattr__(self, "geoid", geoid)

        if scope_type == "country":
            if geoid not in _SUPPORTED_COUNTRIES:
                raise ValueError(f"Unsupported country scope: {geoid}")
            return

        if scope_type not in _GEOID_LENGTHS:
            raise ValueError(f"Unsupported geography scope type: {scope_type}")

        expected_length = _GEOID_LENGTHS[scope_type]
        if len(geoid) != expected_length or not geoid.isdigit():
            raise ValueError(
                f"{scope_type} geoid must be a {expected_length}-digit string"
            )

        if scope_type == "puma" and self.vintage is None:
            raise ValueError("PUMA scope requires a vintage")

    def as_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {"type": self.type, "geoid": self.geoid}
        if self.vintage is not None:
            value["vintage"] = self.vintage
        return value


def normalize_scope(
    value: GeographyScope | Mapping[str, Any] | None,
) -> GeographyScope | None:
    if value is None:
        return None
    if isinstance(value, GeographyScope):
        return value
    if not isinstance(value, Mapping):
        raise TypeError(
            f"Geography scope must be a mapping, got {type(value).__name__}"
        )
    return GeographyScope(
        type=str(value["type"]),
        geoid=str(value["geoid"]),
        vintage=value.get("vintage"),
    )


def scope_contains(
    container: GeographyScope | Mapping[str, Any],
    item: GeographyScope | Mapping[str, Any],
) -> bool:
    container_scope = normalize_scope(container)
    item_scope = normalize_scope(item)
    if container_scope is None or item_scope is None:
        return False
    if container_scope == item_scope:
        return True

    if container_scope.type == "country":
        return container_scope.geoid == "US" and item_scope.type != "country"

    if container_scope.type == "census_state":
        if item_scope.type in {
            "census_county",
            "census_place",
            "census_tract",
            "census_block",
            "puma",
        }:
            return item_scope.geoid.startswith(container_scope.geoid)
        return False

    if container_scope.type == "census_county":
        if item_scope.type in {"census_tract", "census_block"}:
            return item_scope.geoid.startswith(container_scope.geoid)
        return False

    if container_scope.type == "census_tract":
        return (
            item_scope.type == "census_block"
            and item_scope.geoid.startswith(container_scope.geoid)
        )

    return False


def scope_intersection(
    left: GeographyScope | Mapping[str, Any] | None,
    right: GeographyScope | Mapping[str, Any] | None,
) -> GeographyScope | None:
    left_scope = normalize_scope(left)
    right_scope = normalize_scope(right)
    if left_scope is None:
        return right_scope
    if right_scope is None:
        return left_scope
    if scope_contains(left_scope, right_scope):
        return right_scope
    if scope_contains(right_scope, left_scope):
        return left_scope
    return None


def pe_inputs_for_scope(
    value: GeographyScope | Mapping[str, Any] | None,
) -> dict[str, int | str]:
    scope = normalize_scope(value)
    if scope is None or scope.type == "country":
        return {}
    if scope.type == "census_state":
        return {"state_fips": int(scope.geoid)}
    if scope.type == "census_county":
        return {"state_fips": int(scope.geoid[:2]), "county_fips": scope.geoid}
    if scope.type == "census_place":
        return {"state_fips": int(scope.geoid[:2]), "place_fips": scope.geoid[2:]}
    if scope.type == "census_tract":
        return {
            "state_fips": int(scope.geoid[:2]),
            "county_fips": scope.geoid[:5],
            "tract_geoid": scope.geoid,
        }
    if scope.type == "census_block":
        return {
            "state_fips": int(scope.geoid[:2]),
            "county_fips": scope.geoid[:5],
            "tract_geoid": scope.geoid[:11],
            "block_geoid": scope.geoid,
        }
    if scope.type == "puma":
        return {"state_fips": int(scope.geoid[:2]), "puma": scope.geoid[2:]}
    if scope.type == "zcta":
        return {"zcta": scope.geoid}
    raise ValueError(f"Unsupported geography scope type: {scope.type}")
