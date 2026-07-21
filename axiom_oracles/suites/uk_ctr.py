"""UK Council Tax Reduction suite for the entitledto recorded-fixture oracle.

Council Tax Reduction (CTR) is set scheme-by-scheme by each of ~300 billing
authorities. PolicyEngine-UK computes the three national schemes (England
pension-age SI 2012/2885, Scotland SSI 2021/249, Wales SI 2013/3029) plus five
named English working-age councils (Merton, Kingston upon Thames, Newham,
Westminster, Oxford); UKMOD is national. For every *other* English council's
working-age scheme neither models the actual local rules — they fall back to a
survey-reported figure (PolicyEngine) or a national treatment (UKMOD). entitledto
models every council, so it is the only per-council reference source (entitledto
publishes estimates, not authoritative awards), which is why this suite's oracle
is the recorded entitledto calculator rather than an engine.

The grid is eight hand-checkable cases chosen for CTR leverage:

1. England pension-age couple on Guarantee Credit (Birmingham) — full 100% award.
2. England pension-age single with earnings over the applicable amount
   (Cornwall) — the 20% taper interior, hand-verifiable.
3. Scotland working-age single earner, private renter (Glasgow) — national scheme.
4. Wales working-age couple with two children, social renter (Cardiff) — national.
5. Kingston upon Thames working-age single earner — a PolicyEngine-*supported*
   local scheme (capital under the £6k tariff threshold).
6. Kingston upon Thames pension-age single — pension-age routes to the England
   national prescribed scheme even in a council with its own working-age scheme.
7. Manchester working-age single earner — an *unsupported* English council;
   PolicyEngine falls back to the reported benefit, so entitledto is the only
   reference. Same £11k single-renter profile as (3) and (5).
8. Birmingham working-age couple with one child — a second unsupported council.

Cases (3), (5) and (7) share an identical single-renter, £11,000-earnings profile
across Scotland, Kingston and Manchester, so a single income point exposes three
different CTR outcomes across three schemes — the per-council variation this
oracle exists to measure.

The ``Case`` carries only oracle-neutral scalars; ``EntitledToInputMapper``
projects them into the calculator's manual-entry record at capture time (the
ACCESS-NYC projection pattern), and ``fixtures/uk_ctr/*.json`` records the
result. No engine-specific payload is stored on the case, so the canonical grid
extraction round-trips it exactly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.case import Case, Concepts, Entity

UK_SCOPE = {"type": "country", "geoid": "UK"}
UK_CTR_METADATA = {"locale": "UK", "scope": UK_SCOPE, "suite": "uk-ctr"}

# The CTR benefit year current at the 2026-07 capture window and the eval date
# the PolicyEngine/RuleSpec cross-check keys off (the sibling Axiom-vs-PE CTR
# grid, comparisons/uk-council-tax-reduction.yaml, uses the same 2026 year).
SCHEME_YEAR = "2026-27"
CALCULATION_DATE = "2026-07-13"
PERIOD = "2026"


@dataclass(frozen=True)
class _Adult:
    age: int
    employment_income: float = 0.0
    state_pension: float = 0.0
    private_pension: float = 0.0


@dataclass(frozen=True)
class _CtrCase:
    case_id: str
    scenario: str
    country: str
    ctr_scheme: str
    local_authority_name: str
    local_authority_gss_code: str
    local_authority_postcode: str
    council_tax_band: str
    annual_council_tax_liability: float
    tenure: str
    monthly_rent: float
    capital: float
    claimant: _Adult
    partner: _Adult | None = None
    children_ages: tuple[int, ...] = field(default_factory=tuple)


# private_rent | social_rent | owner (owner-occupiers pay council tax but claim
# no rent rebate, so monthly_rent is 0).
_PRIVATE_RENT = "private_rent"
_SOCIAL_RENT = "social_rent"
_OWNER = "owner"

_CASES: tuple[_CtrCase, ...] = (
    _CtrCase(
        case_id="ctr-eng-pa-birmingham-couple-gc",
        scenario="england-pension-age-full-award-guarantee-credit",
        country="England",
        ctr_scheme="england-pension-age-prescribed",
        local_authority_name="Birmingham",
        local_authority_gss_code="E08000025",
        local_authority_postcode="B1 1BB",
        council_tax_band="C",
        annual_council_tax_liability=1800.0,
        tenure=_OWNER,
        monthly_rent=0.0,
        capital=2000.0,
        claimant=_Adult(age=70, state_pension=8000.0),
        partner=_Adult(age=68, state_pension=6000.0),
    ),
    _CtrCase(
        case_id="ctr-eng-pa-cornwall-single-taper",
        scenario="england-pension-age-taper-interior",
        country="England",
        ctr_scheme="england-pension-age-prescribed",
        local_authority_name="Cornwall",
        local_authority_gss_code="E06000052",
        local_authority_postcode="TR1 1EN",
        council_tax_band="D",
        annual_council_tax_liability=2000.0,
        tenure=_OWNER,
        monthly_rent=0.0,
        capital=5000.0,
        claimant=_Adult(age=70, state_pension=9000.0, employment_income=8000.0),
    ),
    _CtrCase(
        case_id="ctr-sco-wa-glasgow-single-earner",
        scenario="scotland-working-age-national",
        country="Scotland",
        ctr_scheme="scotland-working-age-national",
        local_authority_name="Glasgow City",
        local_authority_gss_code="S12000049",
        local_authority_postcode="G1 1XW",
        council_tax_band="B",
        annual_council_tax_liability=1300.0,
        tenure=_PRIVATE_RENT,
        monthly_rent=583.33,
        capital=1000.0,
        claimant=_Adult(age=30, employment_income=11000.0),
    ),
    _CtrCase(
        case_id="ctr-wal-wa-cardiff-couple-2kids",
        scenario="wales-working-age-national",
        country="Wales",
        ctr_scheme="wales-working-age-national",
        local_authority_name="Cardiff",
        local_authority_gss_code="W06000015",
        local_authority_postcode="CF10 1EP",
        council_tax_band="C",
        annual_council_tax_liability=1500.0,
        tenure=_SOCIAL_RENT,
        monthly_rent=500.0,
        capital=500.0,
        claimant=_Adult(age=35, employment_income=22000.0),
        partner=_Adult(age=35),
        children_ages=(5, 3),
    ),
    _CtrCase(
        case_id="ctr-eng-wa-kingston-single-earner",
        scenario="kingston-working-age-local-supported",
        country="England",
        ctr_scheme="kingston-upon-thames-working-age-local",
        local_authority_name="Kingston upon Thames",
        local_authority_gss_code="E09000021",
        local_authority_postcode="KT1 1EU",
        council_tax_band="D",
        annual_council_tax_liability=2171.0,
        tenure=_PRIVATE_RENT,
        monthly_rent=900.0,
        capital=3000.0,
        claimant=_Adult(age=30, employment_income=11000.0),
    ),
    _CtrCase(
        case_id="ctr-eng-pa-kingston-single",
        scenario="kingston-pension-age-routes-to-national",
        country="England",
        ctr_scheme="england-pension-age-prescribed",
        local_authority_name="Kingston upon Thames",
        local_authority_gss_code="E09000021",
        local_authority_postcode="KT1 1EU",
        council_tax_band="D",
        annual_council_tax_liability=2171.0,
        tenure=_OWNER,
        monthly_rent=0.0,
        capital=4000.0,
        claimant=_Adult(age=70, state_pension=9000.0),
    ),
    _CtrCase(
        case_id="ctr-eng-wa-manchester-single-earner",
        scenario="manchester-working-age-local-unsupported",
        country="England",
        ctr_scheme="manchester-working-age-local",
        local_authority_name="Manchester",
        local_authority_gss_code="E08000003",
        local_authority_postcode="M1 1AE",
        council_tax_band="B",
        annual_council_tax_liability=1600.0,
        tenure=_PRIVATE_RENT,
        monthly_rent=700.0,
        capital=3000.0,
        claimant=_Adult(age=30, employment_income=11000.0),
    ),
    _CtrCase(
        case_id="ctr-eng-wa-birmingham-couple-1kid",
        scenario="birmingham-working-age-local-unsupported",
        country="England",
        ctr_scheme="birmingham-working-age-local",
        local_authority_name="Birmingham",
        local_authority_gss_code="E08000025",
        local_authority_postcode="B1 1BB",
        council_tax_band="B",
        annual_council_tax_liability=1400.0,
        tenure=_SOCIAL_RENT,
        monthly_rent=500.0,
        capital=2000.0,
        claimant=_Adult(age=35, employment_income=16000.0),
        partner=_Adult(age=33),
        children_ages=(8,),
    ),
)


def _entities(spec: _CtrCase) -> tuple[Entity, ...]:
    people: list[Entity] = [
        Entity(
            entity_id="claimant",
            kind="person",
            facts={
                Concepts.PERSON_AGE: spec.claimant.age,
                Concepts.HOUSEHOLD_RELATION: "HeadOfHousehold",
            },
        )
    ]
    if spec.partner is not None:
        people.append(
            Entity(
                entity_id="partner",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: spec.partner.age,
                    Concepts.HOUSEHOLD_RELATION: "Spouse",
                },
            )
        )
    for index, age in enumerate(spec.children_ages):
        people.append(
            Entity(
                entity_id=f"child-{index}",
                kind="person",
                facts={
                    Concepts.PERSON_AGE: age,
                    Concepts.HOUSEHOLD_RELATION: "Child",
                },
            )
        )
    return tuple(people)


def _metadata(spec: _CtrCase) -> dict:
    couple = spec.partner is not None
    pension_age = spec.claimant.age >= 66 or (
        spec.partner is not None and spec.partner.age >= 66
    )
    meta: dict = {
        **UK_CTR_METADATA,
        "scenario": spec.scenario,
        "scheme_year": SCHEME_YEAR,
        "calculation_date": CALCULATION_DATE,
        "country": spec.country,
        "ctr_scheme": spec.ctr_scheme,
        "local_authority_name": spec.local_authority_name,
        "local_authority_gss_code": spec.local_authority_gss_code,
        "local_authority_postcode": spec.local_authority_postcode,
        "council_tax_band": spec.council_tax_band,
        "annual_council_tax_liability": spec.annual_council_tax_liability,
        "tenure": spec.tenure,
        "monthly_rent": spec.monthly_rent,
        "capital": spec.capital,
        "couple": couple,
        "pension_age": pension_age,
        "claimant_employment_income": spec.claimant.employment_income,
        "claimant_state_pension": spec.claimant.state_pension,
        "claimant_private_pension": spec.claimant.private_pension,
    }
    if spec.partner is not None:
        meta["partner_employment_income"] = spec.partner.employment_income
        meta["partner_state_pension"] = spec.partner.state_pension
        meta["partner_private_pension"] = spec.partner.private_pension
    return meta


def uk_ctr_cases() -> list[Case]:
    """The eight UK Council Tax Reduction cases for the entitledto oracle."""
    return [
        Case(
            case_id=spec.case_id,
            period=PERIOD,
            metadata=_metadata(spec),
            entities=_entities(spec),
            outputs=(
                "uk:policies/govuk/council-tax-reduction"
                "#council_tax_reduction_annual_amount",
            ),
        )
        for spec in _CASES
    ]
