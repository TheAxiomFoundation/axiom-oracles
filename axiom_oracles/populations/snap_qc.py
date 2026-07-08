"""SNAP Quality Control public-use-file loader for administrative-grade parity.

The USDA SNAP Quality Control (QC) public-use file (PUF) is a stratified
sample of active SNAP case reviews for a fiscal year. For every retained
review the file carries a **constructed** benefit computation: FNS's contractor
(Mathematica) recomputes the allotment from edited, internally consistent
inputs and the official fiscal-year parameters (the "QC Minimodel"), so
``FSBEN`` is the benefit the rules *should* produce for those inputs — the US
analogue of a full-admin-returns oracle. Replaying each unit's inputs through
an Axiom SNAP composition and comparing allotments (and stage intermediates)
against the QC-constructed values is therefore ground-truth parity.

This module is the loader: it pins each fiscal year's PUF (URL + sha256 +
archive member), downloads and verifies it on demand, streams the CSV with the
standard-library :mod:`csv` reader (the file is ~92 MB; it is never read whole
into memory), and projects each row into a :class:`QcUnit` — participating and
non-participating person records with per-source monthly income, the
household's shelter/utility/medical/dependent-care/child-support facts, the
categorical-eligibility and resource facts, and a :class:`QcExpected` holding
the QC-constructed benefit, income totals, deductions, screens, and error
finding. Units that use a separate benefit procedure (MFIP, SSI-CAP) are
excluded through a counted :class:`QcExclusionLog` rather than silently
dropped. The mapper/comparison harness lives in
:mod:`axiom_oracles.bridges.snap_qc_compare` (Lane B).

Fiscal-year gap
---------------
Only pinned fiscal years load; there is deliberately no allow-unpinned escape
hatch, because the PUFs are immutable postings and an unpinned/moved file would
silently swap the ground truth under a comparison.

Codebook citations
-------------------
Every mapped variable is cited to a page of the FY 2024 SNAP QC Technical
Documentation detailed codebook (Chapter V.B). Page numbers below are PDF pages
of that document (the ``===== PDF PAGE N =====`` markers in the archived
``tech-doc-full.txt``); they equal the printed page plus ten.

Case control and identification
    ``YRMONTH`` sample year+month (p74) -> ``yrmonth``;
    ``STATE`` FIPS code (p77) -> ``state_fips``;
    ``CERTHHSZ`` certified unit size (p75) -> ``certified_size``;
    ``HWGT`` monthly sample weight (p76) -> ``weight``;
    ``STATUS`` status of case error findings, 1/2/3 = correct/over/under (p74)
    -> ``expected.status``;
    ``AMTERR`` amount of benefit in error (p87) -> ``expected.error_amount``;
    ``MN_FIP`` MFIP participation (p73) and ``SSI_CAP`` SSI-CAP participation
    (p73) drive exclusions.

Person-level (i = 1..18)
    ``AGE`` age (p89) -> ``QcMember.age``;
    ``DIS`` disability, age <=59 (p89) and ``DIS64`` disability, age <=64 (p90)
    with age -> ``QcMember.elderly_or_disabled``.
    Earned income (the FSEARN components, p79): ``WAGES`` wages (p97),
    ``SLFEMP`` self-employment (p96), ``OTHERN`` other earned (p96),
    ``RENTMINC`` rental income when managing property >=20 h/wk (p96).
    Unearned income (the FSUNEARN components, p81): ``ALIMNY`` (p95),
    ``ANNUITY`` (p95), ``CONT`` contributions (p95), ``CSUPRT`` child support
    received (p95), ``DEEM`` deemed (p95), ``DIVER`` state diversion (p95),
    ``EDLOAN`` educational grants/loans (p95), ``ENERGY`` energy assistance
    (p95), ``FOSTER`` foster care (p95), ``GA`` general assistance (p95),
    ``GOVDIV`` (p95), ``GOVINTER`` (p95), ``GOVROY`` (p95), ``INTER`` interest
    (p96), ``OLDAGE`` (p96), ``OTHGOV`` other government (p96), ``OTHUN`` other
    unearned (p96), ``PENSION`` (p96), ``RENTINC`` passive rental (p96),
    ``SOCSEC`` Social Security (p96), ``SSI`` (p96), ``STRIKE`` (p96), ``SURV``
    survivor (p97), ``TANF`` (p97), ``TRUST`` (p97), ``UNEMP`` (p97), ``VET``
    veterans (p97), ``WCOMP`` workers' compensation (p97), ``UNK`` unknown
    source (p97), ``WGESUP`` wage supplementation (p97).

Household expenses and resources
    ``RENT`` rent/mortgage (p86) -> ``shelter_expense``;
    ``SUA1`` standard-utility-allowance usage (p86) -> ``utility_tier``
    (``SUA2`` proration, p86, does not change the tier);
    ``UTIL`` utility amount (p86) -> ``utility_amount`` — the QC-applied
    allowance, which the codebook notes SUA1 was edited for consistency with;
    when it disagrees with the tier's standard amount (an actual-expense or
    prorated allowance), the mapper treats ``UTIL`` as authoritative;
    ``FSMEDEXP`` reported medical expenses over $35 (p85) -> ``medical_expenses``;
    ``FSDEPDED`` dependent-care deduction (p84) -> ``dependent_care_expense``;
    ``FSCSEXP`` reported child-support payment (p84) -> ``child_support_expense``;
    ``LIQRESOR`` countable liquid assets (p82) -> ``liquid_resources``;
    ``CAT_ELIG`` categorical-eligibility status (p72) -> ``categorically_eligible``;
    ``HOMEDED`` homelessness indicator (p86; 1 = not homeless, 2 = homeless
    without the standard homeless shelter deduction, 3 = homeless receiving
    it, 4 = homeless applying actual expenses toward excess shelter) ->
    ``homeless`` (codes 2-4) and ``homeless_deduction_claimed`` (code 3;
    the constructed ``HOMELESS_DED`` is positive only for these units and
    ``FSSLTDED`` is zeroed for them by construction).

Expected (QC-constructed benefit computation)
    ``FSBEN`` final calculated benefit (p87) -> ``benefit``;
    ``FSGRINC`` final gross income (p79) -> ``gross_income``;
    ``FSNETINC`` final net income (p80) -> ``net_income``;
    ``FSSTDDED`` standard deduction (p85) -> ``standard_deduction``;
    ``FSERNDED`` earned-income deduction (p84) -> ``earned_income_deduction``;
    ``FSMEDDED`` medical deduction (p84) -> ``medical_deduction``;
    ``FSDEPDED`` dependent-care deduction (p84) -> ``dependent_care_deduction``;
    ``FSCSDED`` child-support deduction (p84) -> ``child_support_deduction``;
    ``FSSLTDED`` calculated excess shelter deduction (p85) -> ``shelter_deduction``;
    ``MINIMUM_BEN`` minimum benefit amount (p87) -> ``minimum_benefit``;
    ``FSMINBEN`` received minimum benefit (p87) -> ``received_minimum_benefit``;
    ``GROSSCRN`` gross income screen (p87) -> ``gross_screen``;
    ``NETSCRN`` net income screen (p88) -> ``net_screen``;
    ``FSGRTEST`` passes gross test (p87) -> ``passes_gross_test``;
    ``FSNETEST`` passes net test (p87) -> ``passes_net_test``.

Codebook ambiguities resolved
------------------------------
* ``shelter_deduction`` maps to **FSSLTDED**, not the reported ``SHELDED``.
  ``SHELDED`` (p86) is the reported, pre-edit shelter deduction and the
  codebook entry itself says "See FSSLTDED for the final value." FSSLTDED
  (p85) is the calculated excess shelter deduction that enters ``FSTOTDED``
  and the benefit formula, so it is the value an engine's excess-shelter
  deduction should reproduce (and the value that matches the worked example's
  672 shelter deduction).
* ``dependent_care_expense`` and ``expected.dependent_care_deduction`` both
  derive from ``FSDEPDED`` because SNAP deducts dependent-care costs one-for-one
  (no cap), so the deducted amount equals the expense; ``FSDEPDED`` is the
  edited value that enters ``FSTOTDED`` (``DPCOSTi`` is the per-person reported
  cost, which the codebook, p90, warns is inconsistent with ``FSDEPDED``).
* ``utility_tier`` derives from ``SUA1``, empirically cross-checked against the
  Colorado FY2024 ``UTIL`` amounts: SUA1 3/4/8 -> heating_cooling (HCSUA 560),
  5 -> limited (LUA 356), 6 -> telephone (91), 7 -> one_utility (single-utility
  67), 1 -> none (0). SUA1 2 ("actual expenses") and 9 ("other") have no
  standard-allowance equivalent and do not occur in the Colorado sample; they
  map to ``none`` (documented, dispositioned) rather than inventing a tier.

Member semantics (important for the mapper, Lane B)
---------------------------------------------------
``QcUnit.members`` holds every person slot with data (``FSAFILi`` or ``AGEi``
present), which includes non-participating members (e.g. an ineligible
noncitizen whose income is counted). This is deliberate: summing member
``earned_income()`` and ``unearned_income()`` reproduces the QC-constructed
``FSEARN``/``FSUNEARN`` exactly for every FY2024 row. It also means
``len(members)`` can exceed ``certified_size``: ``certified_size``
(``CERTHHSZ``) counts only participating members (``FSAFILi == 1``) and is what
governs the SNAP household size, so the mapper must use ``certified_size`` for
``household_size`` — never ``len(members)``. The demonstration-waiver flag
``MED_DED_DEMO`` and every other column stay available on ``QcUnit.raw`` for
the mapper's standard-medical-deduction transform.
"""

from __future__ import annotations

import csv
import hashlib
import io
import os
import zipfile
from collections import Counter
from dataclasses import dataclass, field, fields
from enum import Enum
from pathlib import Path

# ---------------------------------------------------------------------------
# Pins
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SnapQcPin:
    """A content pin for one fiscal year's SNAP QC public-use file.

    ``url`` is the immutable ``snapqcdata.net`` CSV-zip posting, ``sha256`` the
    expected hash of the downloaded **zip**, and ``archive_member`` the CSV name
    inside it. Hashing the zip on every download turns a moved posting or a
    corrupted transfer into a loud failure instead of a silent ground-truth
    swap.
    """

    fiscal_year: int
    url: str
    sha256: str
    archive_member: str


#: Verified pins (recorded 2026-07-08). There is intentionally no way to load an
#: unpinned fiscal year: the PUFs are immutable postings, so an unpinned or
#: moved file would silently change the oracle's ground truth.
SNAP_QC_PINS: dict[int, SnapQcPin] = {
    2024: SnapQcPin(
        fiscal_year=2024,
        url="https://snapqcdata.net/sites/default/files/2026-05/qcfy2024_csv.zip",
        sha256="0f3230a4318307d3088382546095eebfde03e781da6f65c9eac7f077bd4263f4",
        archive_member="qc_pub_fy2024.csv",
    ),
    2023: SnapQcPin(
        fiscal_year=2023,
        url="https://snapqcdata.net/sites/default/files/2025-03/qcfy2023_csv.zip",
        sha256="cf79d4d2152b332a4ebd26c49320e3d64fbf65b918b53168d50a52c7bea20648",
        archive_member="qc_pub_fy2023.csv",
    ),
}


# ``snapqcdata.net`` returns HTTP 403 to non-browser user agents, so downloads
# send a Chrome user-agent string and the data-files page as the referer.
_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
_DOWNLOAD_REFERER = "https://snapqcdata.net/datafiles"

#: Default on-disk cache for downloaded PUFs.
_CACHE_SUBPATH = Path(".cache/axiom-oracles/snap-qc")

#: Environment override: a directory that already contains
#: ``qc_pub_fy{YYYY}.csv`` short-circuits the download entirely.
DATA_DIR_ENV_VAR = "AXIOM_SNAP_QC_DATA_DIR"


# ---------------------------------------------------------------------------
# Income source maps (drive both parsing and the earned/unearned helpers)
# ---------------------------------------------------------------------------

#: QcMember attribute -> per-person CSV column prefix for the four earned-income
#: sources (the FSEARN components; codebook p79).
EARNED_INCOME_SOURCES: dict[str, str] = {
    "wages": "WAGES",
    "self_employment": "SLFEMP",
    "other_earned": "OTHERN",
    "rental_self_employment": "RENTMINC",
}

#: QcMember attribute -> per-person CSV column prefix for the thirty
#: unearned-income sources (the FSUNEARN components; codebook p81).
UNEARNED_INCOME_SOURCES: dict[str, str] = {
    "alimony": "ALIMNY",
    "annuities": "ANNUITY",
    "contributions": "CONT",
    "child_support": "CSUPRT",
    "deemed": "DEEM",
    "diversion": "DIVER",
    "education": "EDLOAN",
    "energy_assistance": "ENERGY",
    "foster_care": "FOSTER",
    "general_assistance": "GA",
    "government_dividends": "GOVDIV",
    "government_interest": "GOVINTER",
    "government_royalties": "GOVROY",
    "interest": "INTER",
    "old_age": "OLDAGE",
    "other_government": "OTHGOV",
    "other_unearned": "OTHUN",
    "pension": "PENSION",
    "rental_passive": "RENTINC",
    "social_security": "SOCSEC",
    "ssi": "SSI",
    "striker": "STRIKE",
    "survivor": "SURV",
    "tanf": "TANF",
    "trust": "TRUST",
    "unemployment": "UNEMP",
    "veterans": "VET",
    "workers_compensation": "WCOMP",
    "unknown_source": "UNK",
    "wage_supplementation": "WGESUP",
}


# ---------------------------------------------------------------------------
# Utility tier
# ---------------------------------------------------------------------------


class UtilityTier(Enum):
    """Which standard utility allowance a unit uses, derived from ``SUA1``."""

    HEATING_COOLING = "heating_cooling"
    LIMITED = "limited"
    ONE_UTILITY = "one_utility"
    TELEPHONE = "telephone"
    NONE = "none"


#: ``SUA1`` code (codebook p86) -> tier. Codes 3/4/8 are HCSUA variants; 5 is the
#: lower/limited standard; 6 is telephone-only; 7 is individual/single-utility
#: standards; 1 is no utilities. Codes 2 ("actual expenses") and 9 ("other")
#: carry no standard allowance and do not occur in the Colorado sample, so they
#: fall to ``NONE`` (see the module docstring).
_SUA1_TO_UTILITY_TIER: dict[int, UtilityTier] = {
    1: UtilityTier.NONE,
    2: UtilityTier.NONE,
    3: UtilityTier.HEATING_COOLING,
    4: UtilityTier.HEATING_COOLING,
    5: UtilityTier.LIMITED,
    6: UtilityTier.TELEPHONE,
    7: UtilityTier.ONE_UTILITY,
    8: UtilityTier.HEATING_COOLING,
    9: UtilityTier.NONE,
}


def _utility_tier_from_sua1(sua1: int | None) -> UtilityTier:
    if sua1 is None:
        return UtilityTier.NONE
    return _SUA1_TO_UTILITY_TIER.get(sua1, UtilityTier.NONE)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QcMember:
    """One person record within a QC unit.

    ``age`` is ``None`` when the review did not report it. The per-source
    monthly income fields default to ``0.0`` (a missing income cell means no
    income of that source, matching how the QC unit-income aggregates
    blind-sum the person slots). ``elderly_or_disabled`` is true when the member
    is age 60 or older or is flagged disabled (``DISi`` or ``DIS64_i``).
    """

    index: int
    age: int | None
    elderly_or_disabled: bool
    # Earned-income sources (FSEARN components).
    wages: float = 0.0
    self_employment: float = 0.0
    other_earned: float = 0.0
    rental_self_employment: float = 0.0
    # Unearned-income sources (FSUNEARN components).
    alimony: float = 0.0
    annuities: float = 0.0
    contributions: float = 0.0
    child_support: float = 0.0
    deemed: float = 0.0
    diversion: float = 0.0
    education: float = 0.0
    energy_assistance: float = 0.0
    foster_care: float = 0.0
    general_assistance: float = 0.0
    government_dividends: float = 0.0
    government_interest: float = 0.0
    government_royalties: float = 0.0
    interest: float = 0.0
    old_age: float = 0.0
    other_government: float = 0.0
    other_unearned: float = 0.0
    pension: float = 0.0
    rental_passive: float = 0.0
    social_security: float = 0.0
    ssi: float = 0.0
    striker: float = 0.0
    survivor: float = 0.0
    tanf: float = 0.0
    trust: float = 0.0
    unemployment: float = 0.0
    veterans: float = 0.0
    workers_compensation: float = 0.0
    unknown_source: float = 0.0
    wage_supplementation: float = 0.0

    def earned_income(self) -> float:
        """Sum of the member's earned-income sources (reproduces FSEARN)."""
        return sum(getattr(self, attr) for attr in EARNED_INCOME_SOURCES)

    def unearned_income(self) -> float:
        """Sum of the member's unearned-income sources (reproduces FSUNEARN)."""
        return sum(getattr(self, attr) for attr in UNEARNED_INCOME_SOURCES)


@dataclass(frozen=True)
class QcExpected:
    """The QC-constructed benefit computation for a unit — the ground truth.

    Every field is a QC Minimodel output (or the reported error finding for
    ``status``/``error_amount``). A value is ``None`` when the source column is
    coded missing for the unit; for the loaded (non-excluded) population these
    are populated.
    """

    benefit: float | None
    gross_income: float | None
    net_income: float | None
    standard_deduction: float | None
    earned_income_deduction: float | None
    medical_deduction: float | None
    dependent_care_deduction: float | None
    child_support_deduction: float | None
    shelter_deduction: float | None
    minimum_benefit: float | None
    received_minimum_benefit: bool | None
    gross_screen: float | None
    net_screen: float | None
    passes_gross_test: bool | None
    passes_net_test: bool | None
    status: int | None
    error_amount: float | None


@dataclass(frozen=True)
class QcUnit:
    """A single SNAP QC case review projected into oracle inputs + ground truth."""

    case_id: str
    fiscal_year: int
    yrmonth: int
    state_fips: int
    certified_size: int | None
    members: tuple[QcMember, ...]
    shelter_expense: float | None
    utility_tier: UtilityTier
    utility_amount: float | None
    medical_expenses: float | None
    dependent_care_expense: float | None
    child_support_expense: float | None
    homeless: bool | None
    homeless_deduction_claimed: bool | None
    categorically_eligible: bool | None
    liquid_resources: float | None
    weight: float | None
    expected: QcExpected
    raw: dict[str, str]

    def earned_income(self) -> float:
        """Total earned income across members (reproduces FSEARN)."""
        return sum(member.earned_income() for member in self.members)

    def unearned_income(self) -> float:
        """Total unearned income across members (reproduces FSUNEARN)."""
        return sum(member.unearned_income() for member in self.members)


# ---------------------------------------------------------------------------
# Exclusion log
# ---------------------------------------------------------------------------

#: Unit uses the Minnesota Family Investment Program benefit procedure (MN_FIP).
EXCLUSION_MFIP = "mfip"
#: Unit uses an SSI Combined Application Project benefit procedure (SSI_CAP).
EXCLUSION_SSI_CAP = "ssi_cap"
#: Data-quality guard: no constructed benefit and no error finding.
EXCLUSION_MISSING_BENEFIT = "missing_benefit_without_status"

#: Human-readable descriptions for :meth:`QcExclusionLog.summary`.
_EXCLUSION_DESCRIPTIONS = {
    EXCLUSION_MFIP: "MFIP unit (separate benefit procedure; MN_FIP=1)",
    EXCLUSION_SSI_CAP: "SSI-CAP unit (separate benefit procedure; SSI_CAP!=0)",
    EXCLUSION_MISSING_BENEFIT: "missing FSBEN with no STATUS error finding",
}


@dataclass
class QcExclusionLog:
    """Counts every unit dropped from a load, by reason, alongside the kept count.

    Each excluded unit is counted once, under the first matching reason in the
    priority order MFIP -> SSI-CAP -> missing-benefit, so the per-reason counts
    sum to :attr:`total_excluded` and ``total_loaded + total_excluded`` equals
    the number of in-scope rows scanned. Rows filtered out by the requested
    ``state_fips``/``months`` scope are out of scope and are not counted here.
    """

    counts: Counter[str] = field(default_factory=Counter)
    total_loaded: int = 0

    def record_loaded(self) -> None:
        self.total_loaded += 1

    def record_excluded(self, reason: str) -> None:
        self.counts[reason] += 1

    @property
    def total_excluded(self) -> int:
        return sum(self.counts.values())

    def summary(self) -> str:
        lines = [
            f"Loaded {self.total_loaded} units; "
            f"excluded {self.total_excluded}."
        ]
        for reason, count in sorted(self.counts.items()):
            description = _EXCLUSION_DESCRIPTIONS.get(reason, reason)
            lines.append(f"  {count:>7,d}  {description}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Cell parsing helpers (missing "." -> None)
# ---------------------------------------------------------------------------


def _cell(value: str | None) -> str | None:
    """Return a stripped cell, or ``None`` for a missing (``.``) or empty cell."""
    if value is None:
        return None
    stripped = value.strip()
    if stripped in {"", "."}:
        return None
    return stripped


def _num(value: str | None) -> float | None:
    cell = _cell(value)
    return None if cell is None else float(cell)


def _int(value: str | None) -> int | None:
    cell = _cell(value)
    # Some numeric codes are stored with a trailing ".0"; go through float.
    return None if cell is None else int(float(cell))


def _flag(value: str | None) -> bool | None:
    """Interpret a 0/1 indicator cell as a bool, missing as ``None``."""
    code = _int(value)
    return None if code is None else code == 1


# ---------------------------------------------------------------------------
# Download / cache resolution
# ---------------------------------------------------------------------------


def _cache_dir() -> Path:
    return Path.home() / _CACHE_SUBPATH


def _csv_name(fiscal_year: int) -> str:
    return f"qc_pub_fy{fiscal_year}.csv"


def _verify_sha256(data: bytes, *, expected: str, source: str) -> None:
    """Raise unless ``data`` hashes to ``expected`` (loud integrity gate)."""
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise RuntimeError(
            f"SNAP QC file {source} failed its sha256 check: expected "
            f"{expected}, got {actual}. The pinned snapqcdata.net posting was "
            "moved or the download is corrupt — refusing to run a comparison "
            "against an unverified ground truth. Delete the cached download and "
            "retry, or update SNAP_QC_PINS if this is an intended, verified "
            "re-pin."
        )


def _download_qc_csv(pin: SnapQcPin, cache_dir: Path) -> Path:
    """Download, verify, and extract a pinned PUF; return the local CSV path.

    ``requests`` is imported lazily inside this function so the rest of the
    loader (and its tests) never require the dependency at import time and can
    patch it through :mod:`sys.modules`, mirroring
    :mod:`axiom_oracles.populations.populace_us`.
    """
    import requests

    response = requests.get(
        pin.url,
        headers={
            "User-Agent": _BROWSER_USER_AGENT,
            "Referer": _DOWNLOAD_REFERER,
        },
        timeout=300,
    )
    response.raise_for_status()
    payload = response.content
    _verify_sha256(payload, expected=pin.sha256, source=pin.url)

    cache_dir.mkdir(parents=True, exist_ok=True)
    destination = cache_dir / _csv_name(pin.fiscal_year)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        with archive.open(pin.archive_member) as member, open(
            destination, "wb"
        ) as handle:
            handle.write(member.read())
    return destination


def _resolve_csv_path(fiscal_year: int, data_dir: str | Path | None) -> Path:
    """Locate the PUF CSV, downloading into the cache only as a last resort.

    Resolution order: an explicit ``data_dir`` that contains the file, then the
    :data:`DATA_DIR_ENV_VAR` directory that contains it (either short-circuits
    the download), then the on-disk cache, then a verified download.
    """
    pin = SNAP_QC_PINS.get(fiscal_year)
    if pin is None:
        raise ValueError(
            f"No SNAP QC pin for fiscal year {fiscal_year}. Loadable fiscal "
            f"years are {sorted(SNAP_QC_PINS)}. Add a verified SnapQcPin "
            "(url + sha256 + archive member) to SNAP_QC_PINS to load another "
            "year — there is no unpinned-load escape hatch, because the PUFs "
            "are immutable postings."
        )

    csv_name = _csv_name(fiscal_year)
    for candidate_dir in (data_dir, os.environ.get(DATA_DIR_ENV_VAR)):
        if not candidate_dir:
            continue
        candidate = Path(candidate_dir) / csv_name
        if candidate.exists():
            return candidate

    cache_dir = _cache_dir()
    cached = cache_dir / csv_name
    if cached.exists():
        return cached
    return _download_qc_csv(pin, cache_dir)


# ---------------------------------------------------------------------------
# Row -> QcUnit projection
# ---------------------------------------------------------------------------


def _slot_present(row: dict[str, str], index: int) -> bool:
    """A person slot exists when its affiliation or age cell carries a value."""
    return (
        _cell(row.get(f"FSAFIL{index}")) is not None
        or _cell(row.get(f"AGE{index}")) is not None
    )


def _member_from_slot(row: dict[str, str], index: int) -> QcMember:
    income = {
        attr: (_num(row.get(f"{prefix}{index}")) or 0.0)
        for attr, prefix in {
            **EARNED_INCOME_SOURCES,
            **UNEARNED_INCOME_SOURCES,
        }.items()
    }
    age = _int(row.get(f"AGE{index}"))
    disabled = (
        _flag(row.get(f"DIS{index}")) is True
        or _flag(row.get(f"DIS64_{index}")) is True
    )
    elderly = age is not None and age >= 60
    return QcMember(
        index=index,
        age=age,
        elderly_or_disabled=elderly or disabled,
        **income,
    )


def _homeless_from_homeded(homeded: int | None) -> bool | None:
    # HOMEDED (p86): 1 = not homeless; 2 = homeless without the standard
    # homeless shelter deduction; 3 = homeless receiving it; 4 = homeless
    # applying actual expenses toward the excess shelter deduction.
    return None if homeded is None else homeded != 1


def _homeless_deduction_claimed(homeded: int | None) -> bool | None:
    # HOMEDED = 3 is the only code that receives the standard homeless shelter
    # deduction; the constructed HOMELESS_DED (p86) is positive only for these
    # units, and FSSLTDED (p85) is set to 0 for them by construction.
    return None if homeded is None else homeded == 3


def _categorically_eligible(cat_elig: int | None) -> bool | None:
    # CAT_ELIG (p72): 0 = not categorically eligible; 1/2/3 = categorically
    # eligible (traditional, BBCE, or recoded pure cash assistance).
    return None if cat_elig is None else cat_elig != 0


def _build_expected(row: dict[str, str]) -> QcExpected:
    return QcExpected(
        benefit=_num(row.get("FSBEN")),
        gross_income=_num(row.get("FSGRINC")),
        net_income=_num(row.get("FSNETINC")),
        standard_deduction=_num(row.get("FSSTDDED")),
        earned_income_deduction=_num(row.get("FSERNDED")),
        medical_deduction=_num(row.get("FSMEDDED")),
        dependent_care_deduction=_num(row.get("FSDEPDED")),
        child_support_deduction=_num(row.get("FSCSDED")),
        shelter_deduction=_num(row.get("FSSLTDED")),
        minimum_benefit=_num(row.get("MINIMUM_BEN")),
        received_minimum_benefit=_flag(row.get("FSMINBEN")),
        gross_screen=_num(row.get("GROSSCRN")),
        net_screen=_num(row.get("NETSCRN")),
        passes_gross_test=_flag(row.get("FSGRTEST")),
        passes_net_test=_flag(row.get("FSNETEST")),
        status=_int(row.get("STATUS")),
        error_amount=_num(row.get("AMTERR")),
    )


def _build_unit(
    row: dict[str, str],
    *,
    fiscal_year: int,
    yrmonth: int,
    state_fips: int,
    row_index: int,
) -> QcUnit:
    members = tuple(
        _member_from_slot(row, index)
        for index in range(1, 19)
        if _slot_present(row, index)
    )
    return QcUnit(
        case_id=f"{fiscal_year}-{yrmonth}-{row_index}",
        fiscal_year=fiscal_year,
        yrmonth=yrmonth,
        state_fips=state_fips,
        certified_size=_int(row.get("CERTHHSZ")),
        members=members,
        shelter_expense=_num(row.get("RENT")),
        utility_tier=_utility_tier_from_sua1(_int(row.get("SUA1"))),
        utility_amount=_num(row.get("UTIL")),
        medical_expenses=_num(row.get("FSMEDEXP")),
        dependent_care_expense=_num(row.get("FSDEPDED")),
        child_support_expense=_num(row.get("FSCSEXP")),
        homeless=_homeless_from_homeded(_int(row.get("HOMEDED"))),
        homeless_deduction_claimed=_homeless_deduction_claimed(
            _int(row.get("HOMEDED"))
        ),
        categorically_eligible=_categorically_eligible(_int(row.get("CAT_ELIG"))),
        liquid_resources=_num(row.get("LIQRESOR")),
        weight=_num(row.get("HWGT")),
        expected=_build_expected(row),
        raw=dict(row),
    )


def _exclusion_reason(
    row: dict[str, str],
    *,
    include_special_programs: bool,
) -> str | None:
    """First matching exclusion reason for a row, or ``None`` to keep it.

    The public file already dropped incomplete reviews, ineligible units, and
    zero-size units during editing (tech doc III.B), so the loader does not
    re-apply eligibility filters; it only removes units whose benefit is
    produced by a separate procedure (MFIP, SSI-CAP) and guards against a unit
    with no constructed benefit and no error finding.
    """
    if not include_special_programs:
        if _int(row.get("MN_FIP")) == 1:
            return EXCLUSION_MFIP
        ssi_cap = _int(row.get("SSI_CAP"))
        if ssi_cap is not None and ssi_cap != 0:
            return EXCLUSION_SSI_CAP
    if _num(row.get("FSBEN")) in (None, 0.0) and _int(row.get("STATUS")) is None:
        return EXCLUSION_MISSING_BENEFIT
    return None


def load_qc_units(
    fiscal_year: int,
    *,
    state_fips: int | None = None,
    months: int | list[int] | tuple[int, ...] | set[int] | None = None,
    data_dir: str | Path | None = None,
    include_special_programs: bool = False,
) -> tuple[list[QcUnit], QcExclusionLog]:
    """Load a fiscal year's SNAP QC public-use file into units + an exclusion log.

    Only pinned fiscal years load (:data:`SNAP_QC_PINS`); an unpinned year
    raises. ``state_fips`` and ``months`` (a YRMONTH int or collection of them)
    restrict the load to a scope; rows outside the scope are skipped and are not
    counted in the log. Within scope, MFIP and SSI-CAP units are excluded and
    counted unless ``include_special_programs`` is set. The CSV is streamed with
    the standard-library reader, so the ~92 MB file is never held in memory
    whole.
    """
    if months is not None and isinstance(months, int):
        months = (months,)
    month_filter = set(months) if months is not None else None

    csv_path = _resolve_csv_path(fiscal_year, data_dir)
    log = QcExclusionLog()
    units: list[QcUnit] = []

    with open(csv_path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row_index, row in enumerate(reader):
            state_code = _int(row.get("STATE"))
            yrmonth = _int(row.get("YRMONTH"))
            # Scope filtering (out-of-scope rows are not exclusions).
            if state_fips is not None and state_code != state_fips:
                continue
            if month_filter is not None and yrmonth not in month_filter:
                continue

            reason = _exclusion_reason(
                row, include_special_programs=include_special_programs
            )
            if reason is not None:
                log.record_excluded(reason)
                continue

            units.append(
                _build_unit(
                    row,
                    fiscal_year=fiscal_year,
                    yrmonth=yrmonth if yrmonth is not None else 0,
                    state_fips=state_code if state_code is not None else 0,
                    row_index=row_index,
                )
            )
            log.record_loaded()

    return units, log


def _member_income_field_names() -> set[str]:
    """The QcMember float fields that hold per-source income (drift guard)."""
    return {
        f.name
        for f in fields(QcMember)
        if f.name not in {"index", "age", "elderly_or_disabled"}
    }


__all__ = [
    "DATA_DIR_ENV_VAR",
    "EARNED_INCOME_SOURCES",
    "EXCLUSION_MFIP",
    "EXCLUSION_MISSING_BENEFIT",
    "EXCLUSION_SSI_CAP",
    "QcExclusionLog",
    "QcExpected",
    "QcMember",
    "QcUnit",
    "SNAP_QC_PINS",
    "SnapQcPin",
    "UNEARNED_INCOME_SOURCES",
    "UtilityTier",
    "load_qc_units",
]
