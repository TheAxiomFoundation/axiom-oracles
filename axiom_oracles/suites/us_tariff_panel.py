"""US tariff panel suite: rulespec-us spine vs the Yale Budget Lab panel.

Companion to TheAxiomFoundation/axiom-oracles#444 (P5, parity campaign).
The reference is the Yale Budget Lab tariff-rate-tracker statutory panel
(``rate_timeseries.rds``, legal-date mode), extracted to a committed
covered-slice CSV by ``scripts/extract_yale_panel.R`` — a reviewer-independent
reference: expected values never come from artifacts shared with the
rulespec-us implementation.

Comparison grain: one (HTS-10 line, census country, validity interval) cell
from THEIR panel spine, probed at both interval endpoints clipped to our
encoded temporal domain (a single probe date can mask timing mismatches
inside an interval). Per-authority mapping and the statutory-total
reconciliation are defined here; tolerance is exact (both sides are closed
statutory ad-valorem rates).

Design memo: _tariff-parity/laneB-design.md (lane workspace).
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from axiom_oracles.core.case import Case, Entity

# Earliest date the composed spine parameterizes (every effective_from in
# rulespec-us us/policies/cbp/us-tariff-duty/composition.yaml is
# 2026-02-15; probing earlier dates hard-fails the engine batch). Yale
# intervals wholly before this date are in-scope-not-covered temporal debt.
DOMAIN_START = date(2026, 2, 15)

COMPOSITION_MODULE = "us:policies/cbp/us-tariff-duty/composition"
DUTY_MODULE = "us:policies/cbp/us-tariff-duty"

MFN = f"{COMPOSITION_MODULE}#mfn_ad_valorem_rate"
IEEPA = f"{COMPOSITION_MODULE}#ieepa_component_rate"
S122 = f"{COMPOSITION_MODULE}#section_122_component_rate"
S232_ALUMINUM = f"{COMPOSITION_MODULE}#section_232_aluminum_component_rate"
CHINA_301 = f"{COMPOSITION_MODULE}#china_section_301_component_rate"
BRAZIL_301 = f"{COMPOSITION_MODULE}#brazil_section_301_component_rate"
FORCED_LABOR_301 = f"{COMPOSITION_MODULE}#forced_labor_section_301_component_rate"
TOTAL = f"{COMPOSITION_MODULE}#us_tariff_total_ad_valorem_rate"

OUTPUTS: tuple[str, ...] = (
    MFN,
    IEEPA,
    S122,
    S232_ALUMINUM,
    CHINA_301,
    BRAZIL_301,
    FORCED_LABOR_301,
    TOTAL,
)

#: All statutory reference columns in the extract. The statutory total is
#: their SUM — never the panel's stored ``total_rate``/``total_additional``,
#: which are effective (utilization-share-scaled) rates.
YALE_STATUTORY_COLUMNS: tuple[str, ...] = (
    "statutory_base_rate",
    "statutory_rate_232",
    "statutory_rate_ieepa_recip",
    "statutory_rate_ieepa_fent",
    "statutory_rate_301",
    "statutory_rate_301_cs",
    "statutory_rate_s301fl",
    "statutory_rate_s301br",
    "statutory_rate_s338",
    "statutory_rate_s122",
    "statutory_rate_section_201",
    "statutory_rate_other",
)

#: Per-authority slots: our concept (None = no counterpart encoded, compared
#: against an implicit 0 — an honest mismatch when their side is nonzero,
#: never a silent drop) mapped to the Yale columns whose sum is the expected
#: value for the slot. Yale splits IEEPA into reciprocal + fentanyl; the
#: composition encodes one combined component, so the slot compares the sum
#: (splitting ours is a P4 candidate).
AUTHORITY_SLOTS: dict[str, tuple[str | None, tuple[str, ...]]] = {
    "mfn": (MFN, ("statutory_base_rate",)),
    "ieepa": (IEEPA, ("statutory_rate_ieepa_recip", "statutory_rate_ieepa_fent")),
    "section_122": (S122, ("statutory_rate_s122",)),
    "section_232": (S232_ALUMINUM, ("statutory_rate_232",)),
    "china_section_301": (CHINA_301, ("statutory_rate_301",)),
    "brazil_section_301": (BRAZIL_301, ("statutory_rate_s301br",)),
    "forced_labor_section_301": (FORCED_LABOR_301, ("statutory_rate_s301fl",)),
    "china_semiconductor_section_301": (None, ("statutory_rate_301_cs",)),
    "section_338": (None, ("statutory_rate_s338",)),
    "section_201": (None, ("statutory_rate_section_201",)),
    "other": (None, ("statutory_rate_other",)),
}

#: Exact comparison: both sides are closed-form statutory rates; any
#: difference is a real semantic/encoding/reference difference, never noise.
TOLERANCE = 1e-12

REFERENCE_DIRNAME = Path("reference") / "us-tariff-panel"


@dataclass(frozen=True)
class PanelInterval:
    """One (hts10, census country, validity interval) row of the extract."""

    hts10: str
    country_census: str
    iso2: str
    revision: str
    valid_from: date
    valid_until: date
    rates: dict[str, float]

    @property
    def cell_id(self) -> str:
        return f"{self.hts10}-{self.country_census}-{self.valid_from.isoformat()}"

    @property
    def covered_dates(self) -> tuple[date, ...]:
        """Probe dates: both interval endpoints clipped to the encoded domain.

        Empty when the interval ends before the domain starts (temporal
        debt — counted in the conformance universe, not dropped silently).
        """
        if self.valid_until < DOMAIN_START:
            return ()
        start = max(self.valid_from, DOMAIN_START)
        if start == self.valid_until:
            return (start,)
        return (start, self.valid_until)

    @property
    def statutory_total(self) -> float:
        return sum(self.rates[column] for column in YALE_STATUTORY_COLUMNS)


def dotted_hts(hts10: str) -> str:
    """``7202111000`` -> ``7202.11.10.00`` (the spine's input format)."""
    return f"{hts10[0:4]}.{hts10[4:6]}.{hts10[6:8]}.{hts10[8:10]}"


def load_bridge(reference_dir: Path) -> dict[str, str]:
    """census 4-digit code -> ISO alpha-2, from the committed bridge."""
    bridge: dict[str, str] = {}
    with (reference_dir / "census_iso_bridge.csv").open() as fh:
        for row in csv.DictReader(fh):
            if row["iso2"]:
                bridge[row["census_code"]] = row["iso2"]
    return bridge


def load_provenance(reference_dir: Path) -> dict:
    return json.loads((reference_dir / "yale_panel_provenance.json").read_text())


def load_reference(reference_dir: Path) -> tuple[list[PanelInterval], list[str]]:
    """Load the committed extract.

    Returns the intervals and the census codes with no ISO bridge entry
    (``bridge_artifact`` material — currently none; kept as a hard surface
    so a Schedule C drift can never silently drop countries).
    """
    bridge = load_bridge(reference_dir)
    intervals: list[PanelInterval] = []
    unbridged: set[str] = set()
    with (reference_dir / "yale_panel_slice.csv").open() as fh:
        for row in csv.DictReader(fh):
            census = row["country"]
            iso2 = bridge.get(census)
            if iso2 is None:
                unbridged.add(census)
                continue
            intervals.append(
                PanelInterval(
                    hts10=row["hts10"],
                    country_census=census,
                    iso2=iso2,
                    revision=row["revision"],
                    valid_from=date.fromisoformat(row["valid_from"]),
                    valid_until=date.fromisoformat(row["valid_until"]),
                    rates={
                        column: float(row[column])
                        for column in YALE_STATUTORY_COLUMNS
                    },
                )
            )
    return intervals, sorted(unbridged)


def case_id(interval: PanelInterval, probe: date) -> str:
    return f"panel-{interval.hts10}-{interval.country_census}-{probe.isoformat()}"


def panel_case(interval: PanelInterval, probe: date) -> Case:
    """Engine case for one covered cell at one probe date.

    The customs value is arbitrary (all compared outputs are pure ad-valorem
    rates); the postal flag is False — the panel models line entries.
    """
    line = dotted_hts(interval.hts10)
    return Case(
        case_id=case_id(interval, probe),
        period=probe.isoformat(),
        metadata={
            "locale": "US",
            "axiom_entity": "CustomsEntry",
            "axiom_entity_id": "entry",
            "axiom_inputs": {
                f"{COMPOSITION_MODULE}#input.customs_value": 10_000.0,
                f"{COMPOSITION_MODULE}#input.shipment_value": 10_000.0,
                f"{COMPOSITION_MODULE}#input.hts_number": line,
                f"{COMPOSITION_MODULE}#input.country_of_origin": interval.iso2,
                f"{COMPOSITION_MODULE}#input.is_postal_shipment": False,
            },
        },
        entities=(
            Entity(
                entity_id="entry",
                kind="customs_entry",
                facts={
                    f"{DUTY_MODULE}#hts_number": line,
                    f"{DUTY_MODULE}#country_of_origin": interval.iso2,
                    f"{DUTY_MODULE}#customs_value": 10_000.0,
                },
            ),
        ),
        outputs=OUTPUTS,
    )


def covered_units(
    intervals: list[PanelInterval],
) -> list[tuple[PanelInterval, date]]:
    """All (interval, probe date) comparison units in the covered slice."""
    return [
        (interval, probe)
        for interval in intervals
        for probe in interval.covered_dates
    ]


def temporal_debt(intervals: list[PanelInterval]) -> list[PanelInterval]:
    """Intervals wholly before the encoded domain (in scope, not covered)."""
    return [i for i in intervals if not i.covered_dates]


def straddle_clipped(intervals: list[PanelInterval]) -> list[PanelInterval]:
    """Intervals probed at clipped endpoints whose pre-domain days go unaudited.

    ``covered_dates`` clips ``valid_from`` up to ``DOMAIN_START``, so an
    interval that straddles the domain boundary IS compared — but only over
    its in-domain portion. The days in ``[valid_from, DOMAIN_START)`` are
    temporal debt exactly like wholly-pre-domain intervals, and must be
    surfaced, not silently absorbed by the clip (sol stack review F4).
    """
    return [
        i for i in intervals if i.valid_from < DOMAIN_START <= i.valid_until
    ]


def column_exposure(
    units: list[tuple[PanelInterval, date]],
) -> dict[str, int]:
    """Comparison units with a POSITIVE reference rate, per statutory column.

    A "covered" verdict for a policy whose statutory column never takes a
    positive value anywhere in the covered slice is vacuous — the
    comparison cannot exercise that policy, agreement with an implicit or
    encoded 0 proves nothing. The conformance scoreboard requires a
    positive-exposure witness on a policy's output_vars before granting
    covered (sol stack review F3); these counts are the report-side basis
    for that witness.
    """
    exposure = {column: 0 for column in YALE_STATUTORY_COLUMNS}
    for interval, _probe in units:
        for column in YALE_STATUTORY_COLUMNS:
            if interval.rates[column] > 0:
                exposure[column] += 1
    return exposure


def temporal_debt_records(intervals: list[PanelInterval]) -> list[dict]:
    """Addressable temporal-debt records for the report scope.

    One record per (kind, hts10, validity interval) group — the debt is
    census-panel-uniform across countries, so grouping keeps the record
    list compact while every unaudited interval stays addressable and its
    units countable (an aggregate count alone cannot be burned down or
    audited — sol stack review F4). Kinds:

    - ``pre_domain``: the whole interval predates the encoded domain; no
      probes exist (``interval_count`` intervals, one per country).
    - ``straddle_clipped``: the interval is probed at clipped endpoints,
      but its days in ``[unprobed_from, unprobed_until]`` are unaudited.
    """
    groups: dict[tuple, dict] = {}
    for interval in intervals:
        if not interval.covered_dates:
            kind = "pre_domain"
        elif interval.valid_from < DOMAIN_START:
            kind = "straddle_clipped"
        else:
            continue
        key = (kind, interval.hts10, interval.valid_from, interval.valid_until)
        record = groups.setdefault(
            key,
            {
                "debt_id": (
                    f"debt-{kind}-{interval.hts10}-"
                    f"{interval.valid_from.isoformat()}-"
                    f"{interval.valid_until.isoformat()}"
                ),
                "kind": kind,
                "hts_number": interval.hts10,
                "valid_from": interval.valid_from.isoformat(),
                "valid_until": interval.valid_until.isoformat(),
                "interval_count": 0,
                **(
                    {
                        "unprobed_from": interval.valid_from.isoformat(),
                        "unprobed_until": (
                            DOMAIN_START - timedelta(days=1)
                        ).isoformat(),
                    }
                    if kind == "straddle_clipped"
                    else {}
                ),
            },
        )
        record["interval_count"] += 1
    return sorted(
        groups.values(),
        key=lambda r: (r["kind"], r["hts_number"], r["valid_from"]),
    )
