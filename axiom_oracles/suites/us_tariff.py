"""US tariff duty T0 suite — statutory-rate grid vs the encoded duty spine.

Companion to TheAxiomFoundation/rulespec-us#1190 (US tariff lane charter) and
TheAxiomFoundation/axiom-oracles#444 (oracle program). Grades the composed
rulespec-us pipeline ``us:policies/cbp/us-tariff-duty/composition`` —
``us_tariff_duty`` over supplied (HTS-10 line, origin country, customs value,
entry date, postal flag) — against duty amounts frozen directly from the
official USITC Harmonized Tariff Schedule editions retained in axiom-corpus
(2026 Rev 3 / Rev 4 / Rev 12 / Rev 14 snapshots plus the Rev 14 chapter-99
notes) and the Federal Register instruments that switch the overlays on and
off. The reference side is the statute itself, not another microsimulation
engine: every expected duty is a hand-verified statutory computation whose
components each cite a retained corpus artifact (see ``rate_components`` in
each case's metadata). Line-level comparison against the USITC machine-readable
schedule is the T0 primary gate per axiom-oracles#444; reconciliation against
the Budget Lab at Yale / TPC aggregate trackers is deliberately deferred to T1.

Grid design is frozen in the lane workspace ``grid-design.md`` (v3,
9903.01.20-corrected): three pilot HTS-10 lines across chapters 72 / 76 / 95, three
origins each, at four entry dates chosen one per retained HTS revision window
so the temporal machinery is exercised on day one:

- **2026-02-15** (Rev 3): full IEEPA stack — fentanyl 9903.01.24 (the
  9903.01.20 note 2(s) window covered entries 2025-02-04..2025-03-04 only and
  is inoperative at every grid date), reciprocal 9903.01.25 + 9903.02.xx with
  the annex (9903.01.32) and §232 metals (9903.01.33) carve-outs, Brazil IEEPA
  9903.01.77. Chosen before the 2026-02-20 EO 14389 signature to avoid the
  wind-down ambiguity.
- **2026-03-15** (Rev 4): IEEPA ad valorem duties terminated for entries on or
  after 2026-02-24 (EO 14389 §1) and the §122 balance-of-payments surcharge
  9903.03.01 +10% active with its annex (9903.03.03) and §232 (9903.03.06)
  carve-outs; postal sub-$800 shipments pay a flat 10% in lieu (EO 14388
  §3(b)).
- **2026-07-23** (Rev 12): last full §122 day; Brazil Section 301 9903.05.01
  +25% active for entries on or after 2026-07-22 (FR 2026-14542); §232
  aluminum consolidated to 9903.82.02/.82.04; last day of the postal flat-10%
  regime.
- **2026-08-01** (Rev 14): §122 expired (150-day statutory sunset, Rev 14
  p221 compiler's note); forced-labor Section 301 note 52 tiers
  (9903.05.27/.31/.84 +12.5%) with annex (9903.05.86) and metals (9903.05.90)
  carve-outs; CBP postal informal-entry process live (FR 2026-12669, eff
  2026-07-24) so postal shipments pay regular duties.

De-minimis doctrine: the 19 USC 1321(a)(2)(C) $800 exemption is suspended at
every grid date (EO 14324, continued by EO 14388; CBP IFRs 2026-12669 /
2026-12670), so no case receives it — cases D1–D4 exercise the suspension, the
postal flat-rate window, and its 2026-07-24 closure.

Judgment calls are documented here and in each affected case's
``rate_components`` (the dispositions schema requires non-empty mismatch
entries, and this suite has none, so there is no dispositions file — the
free-text IDs below are documentation labels, not registered dispositions):

- Brazil 2026-08-01 stacks Brazil-301 9903.05.01 (+25%) with the forced-labor
  Brazil tier 9903.05.27 (+12.5%) on the explicit "shall also be subject to
  any additional duty" language of Rev 14 notes 50(a)/52(a); no cross-carve
  found in (a)(ii)–(vi)/(b)–(k).
- The Rev 14 static line file drops the 9903.88.03/.88.15 footnotes on the
  pilot lines while the headings and note 20 lists are unchanged; the China
  Section 301 duties are treated as still applicable.
- The four Korea zero cells treat ``country_of_origin: KR`` as implying a
  qualifying KORUS special-program claim (General Note 3(c)(i) symbol "KR").
  General Note 3 program-eligibility machinery (claim codes, origin
  qualification) is deferred at T0 alongside the 19 USC 1401a customs-value
  machinery — origin alone selects the Special subcolumn here.

The 2026-02-20..02-23 EO 14389 wind-down window is deliberately not exercised.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.case import Case, Entity

US_SCOPE = {"type": "country", "geoid": "US"}

# The hand-authored composition wrapper (rulespec-us
# us/policies/cbp/us-tariff-duty/composition.yaml) and its supplied inputs.
COMPOSITION_MODULE = "us:policies/cbp/us-tariff-duty/composition"
US_TARIFF_DUTY = f"{COMPOSITION_MODULE}#us_tariff_duty"

_CUSTOMS_VALUE = f"{COMPOSITION_MODULE}#input.customs_value"
_SHIPMENT_VALUE = f"{COMPOSITION_MODULE}#input.shipment_value"
_HTS_NUMBER = f"{COMPOSITION_MODULE}#input.hts_number"
_ORIGIN = f"{COMPOSITION_MODULE}#input.country_of_origin"
_IS_POSTAL = f"{COMPOSITION_MODULE}#input.is_postal_shipment"

US_TARIFF_METADATA = {
    "locale": "US",
    "scope": US_SCOPE,
    "axiom_entity": "CustomsEntry",
    "axiom_entity_id": "entry",
}

# Customs value for the 36 line cases; $10,000 keeps every expected duty an
# exact decimal number of dollars at the statutory ad valorem rates.
LINE_CASE_CUSTOMS_VALUE = 10_000.0
# Shipment value for the postal / de-minimis cases (below the suspended $800
# 19 USC 1321(a)(2)(C) threshold, so the suspension is what binds).
POSTAL_CASE_CUSTOMS_VALUE = 750.0

GRID_DATES = ("2026-02-15", "2026-03-15", "2026-07-23", "2026-08-01")


@dataclass(frozen=True)
class TariffCase:
    """One frozen grid cell: expected duty plus its statutory decomposition."""

    case_id: str
    entry_date: str
    hts_number: str
    origin: str  # ISO 3166-1 alpha-2
    customs_value: float
    is_postal: bool
    expected_rate: float  # total ad valorem rate, e.g. 0.464
    expected_duty: float  # customs_value x expected_rate (or flat amount)
    rate_components: tuple[str, ...]  # citation-bearing decomposition


def _line(
    line: str,
    origin: str,
    date: str,
    rate_pct: float,
    components: tuple[str, ...],
) -> TariffCase:
    return TariffCase(
        case_id=f"us-tariff-{line.replace('.', '')}-{origin.lower()}-{date}",
        entry_date=date,
        hts_number=line,
        origin=origin,
        customs_value=LINE_CASE_CUSTOMS_VALUE,
        is_postal=False,
        expected_rate=round(rate_pct / 100.0, 6),
        expected_duty=round(LINE_CASE_CUSTOMS_VALUE * rate_pct / 100.0, 2),
        rate_components=components,
    )


# Recurring component citations (retained corpus artifacts; page cites are
# us/statute/hts/chapter-99/page-N in 2026-08-01-usitc-hts-2026-rev14-notes).
_MFN_A = "MFN 1.4% (7202.11.10.00 general rate, HTS 2026 Rev3/4/12/14 line files)"
_MFN_B = "MFN 2.6% (7601.10.30.00 general rate, HTS 2026 Rev3/4/12/14 line files)"
_MFN_C = "MFN Free (9506.62.40.40 general rate, HTS 2026 Rev3/4/12/14 line files)"
_KR_FREE = "Special rate Free incl. KR (7202.11.10.00 special subcolumn, KORUS)"
_C301_L1 = (
    "China-301 9903.88.03 +25% (Rev14 note 20(e) p268; 7202.11.10 in the "
    "note 20(f) list, p287; heading in all revisions)"
)
_C301_4A = (
    "China-301 List 4A 9903.88.15 +7.5% (Rev14 note 20(r) p328, list hit p340; "
    "Rev14 static line file drops the footnote, heading and note unchanged — "
    "disposition us-tariff-rev14-footnote-drop)"
)
_C301_2024 = "China 2024-301 9903.91.01 +25% (aluminum, Rev14 note 31)"
_FENT_20_INOP = (
    "IEEPA fentanyl 9903.01.20 inoperative: note 2(s) window covers entries "
    "2025-02-04..2025-03-04 only (Rev14-notes p175)"
)
_FENT_24 = "IEEPA fentanyl 9903.01.24 +10% China+HK (Rev3 heading; note 2(u), entries on/after 2025-11-10)"
_RECIP_BASE = "IEEPA reciprocal baseline 9903.01.25 +10% (Rev3 heading)"
_RECIP_VN = "IEEPA reciprocal Vietnam 9903.02.69 +20% (Rev3 heading)"
_RECIP_BR = "IEEPA reciprocal Brazil 9903.02.09 +10% (Rev3 heading)"
_BR_IEEPA = "Brazil IEEPA 9903.01.77 +40% (EO 14323; Rev3 heading)"
_IEEPA_END = (
    "IEEPA ad valorem duties terminated for entries on/after 2026-02-24 "
    "(EO 14389 §1, FR 2026-03832)"
)
_S122 = "§122 surcharge 9903.03.01 +10%, entries 2026-02-24..2026-07-23 (FR 2026-03824)"
_S122_ANNEX = "§122 annex exemption 9903.03.03 (7202.11.10.00 in annex, Rev14 p226)"
_S122_232 = "§122 §232-article exemption 9903.03.06 (aluminum articles)"
_S122_END = "§122 expired after 2026-07-23 (150-day sunset; Rev14 p221 compiler's note, 91 FR 9339)"
_RECIP_ANNEX = (
    "reciprocal annex exemption 9903.01.32 (note 2(v)(iii)(a); 7202.11.10.00 "
    "on Rev14-notes p182)"
)
_RECIP_METALS = "reciprocal §232-metals exemption 9903.01.33"
_S232_AL = (
    "§232 aluminum +50%: 9903.85.02 (Rev3/4 note 19 p254) / 9903.82.02 "
    "(Rev12/14 note 16(c)(i) p236)"
)
_S232_AL_UK = "§232 aluminum UK tier +25%: 9903.85.12 (Rev3/4) / 9903.82.04 (Rev12/14)"
_NOT_S232_A = "7202.11.10.00 not a §232 steel article (absent from Rev14 note 16(c)(iii) p236)"
_BR301 = "Brazil-301 9903.05.01 +25%, entries on/after 2026-07-22 (FR 2026-14542)"
_BR301_EXEMPT_B = "Brazil-301 exemption 9903.05.07 covers 7601.10.30.00 (Rev14 p553)"
_FL_CN = "FL-301 China tier 9903.05.31 +12.5%, from 2026-07-24 (Rev14 note 52)"
_FL_VN = "FL-301 Vietnam tier 9903.05.84 +12.5%, from 2026-07-24 (Rev14 note 52)"
_FL_BR = "FL-301 Brazil tier 9903.05.27 +12.5%, from 2026-07-24 (Rev14 note 52)"
_FL_ANNEX_A = "FL-301 annex exemption 9903.05.86 covers 7202.11.10.00 (Rev14 p558)"
_FL_METALS = "FL-301 metals exemption 9903.05.90 covers §232 aluminum articles (Rev14 p566)"
_BR_STACK = (
    "Brazil-301 and FL-301 stack per Rev14 notes 50(a) p540 / 52(a) p553 "
    "('shall also be subject to any additional duty'); no cross-carve in "
    "(a)(ii)-(vi)/(b)-(k) — disposition us-tariff-brazil-301-fl-stacking"
)
_SA_ANNEX = "South Africa reciprocal 9903.02.55 inapplicable: 7202.11.10.00 annex-exempt (9903.01.32)"
_POSTAL_FLAT = (
    "postal sub-$800 flat 10% in lieu of ad valorem, 2026-02-24..2026-07-23 "
    "(EO 14388 §3(b), FR 2026-03829)"
)
_POSTAL_END = (
    "CBP postal informal-entry process effective 2026-07-24 (FR 2026-12669): "
    "postal shipments pay regular duties"
)
_DM_SUSPENDED = (
    "19 USC 1321(a)(2)(C) $800 de minimis suspended (EO 14324, continued by "
    "EO 14388; CBP IFRs 2026-12669/2026-12670) — never operative at grid dates"
)


def _frozen_grid() -> tuple[TariffCase, ...]:
    a, b, c = "7202.11.10.00", "7601.10.30.00", "9506.62.40.40"
    d1, d2, d3, d4 = GRID_DATES
    cases: list[TariffCase] = [
        # ---- Line A: 7202.11.10.00 ferromanganese (base 1.4%) ----
        _line(a, "CN", d1, 36.4, (_MFN_A, _C301_L1, _FENT_24, _FENT_20_INOP, _RECIP_ANNEX, _NOT_S232_A)),
        _line(a, "CN", d2, 26.4, (_MFN_A, _C301_L1, _IEEPA_END, _S122_ANNEX)),
        _line(a, "CN", d3, 26.4, (_MFN_A, _C301_L1, _S122_ANNEX)),
        _line(a, "CN", d4, 26.4, (_MFN_A, _C301_L1, _S122_END, _FL_ANNEX_A)),
        _line(a, "ZA", d1, 1.4, (_MFN_A, _SA_ANNEX)),
        _line(a, "ZA", d2, 1.4, (_MFN_A, _IEEPA_END, _S122_ANNEX)),
        _line(a, "ZA", d3, 1.4, (_MFN_A, _S122_ANNEX)),
        _line(a, "ZA", d4, 1.4, (_MFN_A, _S122_END, _FL_ANNEX_A)),
        _line(a, "KR", d1, 0.0, (_KR_FREE, _RECIP_ANNEX)),
        _line(a, "KR", d2, 0.0, (_KR_FREE, _IEEPA_END, _S122_ANNEX)),
        _line(a, "KR", d3, 0.0, (_KR_FREE, _S122_ANNEX)),
        _line(a, "KR", d4, 0.0, (_KR_FREE, _S122_END, _FL_ANNEX_A)),
        # ---- Line B: 7601.10.30.00 unwrought aluminum (base 2.6%) ----
        _line(b, "CN", d1, 87.6, (_MFN_B, _S232_AL, _C301_2024, _FENT_24, _FENT_20_INOP, _RECIP_METALS)),
        _line(b, "CN", d2, 77.6, (_MFN_B, _S232_AL, _C301_2024, _IEEPA_END, _S122_232)),
        _line(b, "CN", d3, 77.6, (_MFN_B, _S232_AL, _C301_2024, _S122_232)),
        _line(b, "CN", d4, 77.6, (_MFN_B, _S232_AL, _C301_2024, _S122_END, _FL_METALS)),
        _line(b, "AE", d1, 52.6, (_MFN_B, _S232_AL, _RECIP_METALS)),
        _line(b, "AE", d2, 52.6, (_MFN_B, _S232_AL, _IEEPA_END, _S122_232)),
        _line(b, "AE", d3, 52.6, (_MFN_B, _S232_AL, _S122_232)),
        _line(b, "AE", d4, 52.6, (_MFN_B, _S232_AL, _S122_END, _FL_METALS)),
        _line(b, "GB", d1, 27.6, (_MFN_B, _S232_AL_UK, _RECIP_METALS)),
        _line(b, "GB", d2, 27.6, (_MFN_B, _S232_AL_UK, _IEEPA_END, _S122_232)),
        _line(b, "GB", d3, 27.6, (_MFN_B, _S232_AL_UK, _S122_232)),
        _line(b, "GB", d4, 27.6, (_MFN_B, _S232_AL_UK, _S122_END, _FL_METALS)),
        # ---- Line C: 9506.62.40.40 footballs (base Free) ----
        _line(c, "CN", d1, 27.5, (_MFN_C, _C301_4A, _FENT_24, _FENT_20_INOP, _RECIP_BASE)),
        _line(c, "CN", d2, 17.5, (_MFN_C, _C301_4A, _IEEPA_END, _S122)),
        _line(c, "CN", d3, 17.5, (_MFN_C, _C301_4A, _S122)),
        _line(c, "CN", d4, 20.0, (_MFN_C, _C301_4A, _S122_END, _FL_CN)),
        _line(c, "VN", d1, 20.0, (_MFN_C, _RECIP_VN)),
        _line(c, "VN", d2, 10.0, (_MFN_C, _IEEPA_END, _S122)),
        _line(c, "VN", d3, 10.0, (_MFN_C, _S122)),
        _line(c, "VN", d4, 12.5, (_MFN_C, _S122_END, _FL_VN)),
        _line(c, "BR", d1, 50.0, (_MFN_C, _RECIP_BR, _BR_IEEPA)),
        _line(c, "BR", d2, 10.0, (_MFN_C, _IEEPA_END, _S122)),
        _line(c, "BR", d3, 35.0, (_MFN_C, _S122, _BR301)),
        _line(c, "BR", d4, 37.5, (_MFN_C, _S122_END, _BR301, _FL_BR, _BR_STACK)),
    ]
    # ---- Postal / de-minimis cases (shipment value $750, footballs) ----
    cases.extend(
        [
            TariffCase(
                case_id="us-tariff-postal-d1-vn-nonpostal-2026-02-15",
                entry_date=d1,
                hts_number=c,
                origin="VN",
                customs_value=POSTAL_CASE_CUSTOMS_VALUE,
                is_postal=False,
                expected_rate=0.20,
                expected_duty=150.0,
                rate_components=(_DM_SUSPENDED, _MFN_C, _RECIP_VN),
            ),
            TariffCase(
                case_id="us-tariff-postal-d2-cn-postal-2026-03-15",
                entry_date=d2,
                hts_number=c,
                origin="CN",
                customs_value=POSTAL_CASE_CUSTOMS_VALUE,
                is_postal=True,
                expected_rate=0.10,
                expected_duty=75.0,
                rate_components=(_DM_SUSPENDED, _POSTAL_FLAT),
            ),
            TariffCase(
                case_id="us-tariff-postal-d3-cn-postal-2026-07-23",
                entry_date=d3,
                hts_number=c,
                origin="CN",
                customs_value=POSTAL_CASE_CUSTOMS_VALUE,
                is_postal=True,
                expected_rate=0.10,
                expected_duty=75.0,
                rate_components=(_DM_SUSPENDED, _POSTAL_FLAT),
            ),
            TariffCase(
                case_id="us-tariff-postal-d4-cn-postal-2026-08-01",
                entry_date=d4,
                hts_number=c,
                origin="CN",
                customs_value=POSTAL_CASE_CUSTOMS_VALUE,
                is_postal=True,
                expected_rate=0.20,
                expected_duty=150.0,
                rate_components=(_DM_SUSPENDED, _POSTAL_END, _MFN_C, _C301_4A, _S122_END, _FL_CN),
            ),
        ]
    )
    return tuple(cases)


FROZEN_GRID: tuple[TariffCase, ...] = _frozen_grid()


def us_tariff_cases() -> list[Case]:
    """The 40 frozen T0 grid cases (36 line cells + 4 postal/de-minimis)."""

    return [_to_case(cell) for cell in FROZEN_GRID]


def _to_case(cell: TariffCase) -> Case:
    return Case(
        case_id=cell.case_id,
        period=cell.entry_date,
        metadata={
            **US_TARIFF_METADATA,
            "scenario": "postal" if cell.is_postal else "line-entry",
            "hts_number": cell.hts_number,
            "country_of_origin": cell.origin,
            "entry_date": cell.entry_date,
            "expected_rate": cell.expected_rate,
            "expected_duty": cell.expected_duty,
            "rate_components": list(cell.rate_components),
            "axiom_inputs": {
                _CUSTOMS_VALUE: cell.customs_value,
                _SHIPMENT_VALUE: cell.customs_value,
                _HTS_NUMBER: cell.hts_number,
                _ORIGIN: cell.origin,
                _IS_POSTAL: cell.is_postal,
            },
        },
        entities=(
            Entity(
                entity_id="entry",
                kind="customs_entry",
                facts={
                    "us:policies/cbp/us-tariff-duty#hts_number": cell.hts_number,
                    "us:policies/cbp/us-tariff-duty#country_of_origin": cell.origin,
                    "us:policies/cbp/us-tariff-duty#customs_value": cell.customs_value,
                },
            ),
        ),
        outputs=(US_TARIFF_DUTY,),
    )
