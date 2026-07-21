"""GETTSIM adapter: pure-projection unit tests + live-when-installed oracle tests.

The projection tests build a hand-written input template and assert the case →
GETTSIM input projection, the dtype-first defaults, the joint demographic
resolution, the relationship-graph validation, and the fail-closed input
guards — all without importing ``gettsim`` (the pure logic lives in
:mod:`axiom_oracles.adapters.gettsim.case`).

The live tests are gated on ``gettsim`` being importable and check statute-exact
German amounts end to end. Statutory anchors for the pinned expectations:

- Employee social-insurance contributions for a 4,000 EUR/month worker:
  health 342.00 = 4,000 x (14.6 % general rate + 2.5 % average Zusatzbeitrag
  for 2025) / 2; pension 372.00 = 4,000 x 18.6 % / 2 (rate set by BSV 2018,
  continued for 2025 by the RVBeitrSBek 2025 notice under s. 158(4) SGB VI);
  unemployment 52.00 = 4,000 x 2.6 % / 2; long-term care 96.00 = 4,000 x
  (3.6 % / 2 + 0.6 % childless surcharge), the 3.6 % set by PBAV 2025.
- Kindergeld 255 EUR/month for 2025 and 259 EUR/month from 2026 — the two
  stages of the Steuerfortentwicklungsgesetz (BGBl. 2024 I Nr. 449), Art. 1
  Nr. 4 and Art. 2 Nr. 4 amending s. 66(1) EStG; both stages are executed
  below, which also proves the runner's date parameterisation end to end.
- Annual income tax 6,433 and the Buergergeld amounts are engine-pinned
  regression values (the s. 32a tariff plus deduction chain is not hand-derived
  here); the Buergergeld Regelbedarf component 563 EUR matches
  Regelbedarfsstufe 1 continued for 2025 by the RBSFV 2025 (BGBl. 2024 I
  Nr. 312).
"""

from __future__ import annotations

import sys
from datetime import date

import pytest

from axiom_oracles.adapters.gettsim import (
    GettsimAdapterError,
    GettsimCase,
    GettsimInputError,
    GettsimNotInstalledError,
    GettsimRunner,
    GettsimTargetError,
    default_value,
    normalize_person_inputs,
    project_case,
    resolve_demographics,
)
from axiom_oracles.adapters.gettsim.case import (
    DEFAULT_ALTER_BEGINN,
    DEFAULT_RENTENEINTRITT_JAHR,
    NO_LINK,
)

LANE_DATE = date(2025, 6, 30)

# A small hand-written stand-in for the GETTSIM input-dtype template. It carries
# the columns whose defaults are load-bearing or easy to get wrong: the four
# jointly-resolved demographics, real years vs. "jahr"-substring
# booleans/amounts, age-indexed table keys, p_id links, and the sole input
# grouping id (hh_id).
STUB_TEMPLATE: dict[tuple[str, ...], str] = {
    ("p_id",): "IntColumn",
    ("hh_id",): "IntColumn",
    ("alter",): "IntColumn",
    ("alter_monate",): "IntColumn",
    ("geburtsjahr",): "IntColumn",
    ("geburtsmonat",): "IntColumn",
    ("einnahmen", "bruttolohn_m"): "FloatColumn",
    ("familie", "p_id_ehepartner"): "IntColumn",
    ("familie", "p_id_elternteil_1"): "IntColumn",
    ("familie", "p_id_elternteil_2"): "IntColumn",
    ("kindergeld", "p_id_empfänger"): "IntColumn",
    ("einkommensteuer", "gemeinsam_veranlagt"): "BoolColumn",
    ("lohnsteuer", "steuerklasse"): "IntColumn",
    ("wohngeld", "mietstufe_hh"): "IntColumn",
    ("sozialversicherung", "rente", "jahr_renteneintritt"): "IntColumn",
    ("sozialversicherung", "pflege", "beitrag", "hat_kinder"): "BoolColumn",
    (
        "einkommensteuer",
        "einkünfte",
        "sonstige",
        "rente",
        "alter_beginn_leistungsbezug_sonstige_private_vorsorge",
    ): "IntColumn",
    # "jahr"-substring columns that are NOT years — must default by dtype:
    ("bürgergeld", "bezug_im_vorjahr"): "BoolColumn",
    ("elterngeld", "zu_versteuerndes_einkommen_vorjahr_y_sn"): "FloatColumn",
}

# Two-leaf targets tree for the pure leaf-collection test (depth-first order).
SEED_TARGETS_FOR_LEAF_CHECK = {
    "einkommensteuer": {"betrag_y_sn": "income_tax_y_sn"},
    "sozialversicherung": {
        "kranken": {"beitrag": {"betrag_versicherter_m": "health_ee_m"}}
    },
}


class TestDefaults:
    def test_dtype_first_bool_and_float(self) -> None:
        assert default_value("sozialversicherung__pflege__beitrag__hat_kinder", "BoolColumn") is False
        assert default_value("einnahmen__bruttolohn_m", "FloatColumn") == 0.0

    def test_jahr_substring_is_not_treated_as_a_year(self) -> None:
        # A bool and a money amount both carry "jahr" (vorjahr) — they must fall
        # to False / 0.0, not a year. This is the seed script's latent-bug class.
        assert default_value("bürgergeld__bezug_im_vorjahr", "BoolColumn") is False
        assert (
            default_value(
                "elterngeld__zu_versteuerndes_einkommen_vorjahr_y_sn", "FloatColumn"
            )
            == 0.0
        )

    def test_real_year_and_age_guards(self) -> None:
        assert (
            default_value("sozialversicherung__rente__jahr_renteneintritt", "IntColumn")
            == DEFAULT_RENTENEINTRITT_JAHR
        )
        assert (
            default_value(
                "einkommensteuer__einkünfte__sonstige__rente__"
                "alter_beginn_leistungsbezug_sonstige_private_vorsorge",
                "IntColumn",
            )
            == DEFAULT_ALTER_BEGINN
        )

    def test_p_id_links_default_to_no_link(self) -> None:
        assert default_value("familie__p_id_ehepartner", "IntColumn") == NO_LINK
        assert default_value("kindergeld__p_id_empfänger", "IntColumn") == NO_LINK

    def test_grouping_and_lookup_key_defaults(self) -> None:
        assert default_value("hh_id", "IntColumn") == 0
        assert default_value("lohnsteuer__steuerklasse", "IntColumn") == 1
        assert default_value("wohngeld__mietstufe_hh", "IntColumn") == 3


class TestResolveDemographics:
    """One birth date explains alter/alter_monate/geburtsjahr/geburtsmonat."""

    def test_no_demographics_default_to_a_coherent_adult(self) -> None:
        resolved = resolve_demographics({}, LANE_DATE, person_index=0)
        assert resolved == {
            "alter": 40,
            "alter_monate": 480,
            "geburtsjahr": 1985,
            "geburtsmonat": 6,
        }

    def test_alter_alone_back_derives_the_birth_date(self) -> None:
        resolved = resolve_demographics({"alter": 67}, LANE_DATE, person_index=0)
        assert resolved["geburtsjahr"] == 1958
        assert resolved["alter_monate"] == 67 * 12
        assert resolved["alter"] == 67

    def test_geburtsjahr_alone_derives_age_at_the_policy_date(self) -> None:
        resolved = resolve_demographics({"geburtsjahr": 2015}, LANE_DATE, person_index=0)
        # Born January 2015 (default month): 125 months old in June 2025.
        assert resolved == {
            "alter": 10,
            "alter_monate": 125,
            "geburtsjahr": 2015,
            "geburtsmonat": 1,
        }

    def test_alter_monate_alone_is_exact_to_the_month(self) -> None:
        resolved = resolve_demographics({"alter_monate": 480}, LANE_DATE, person_index=0)
        assert resolved == {
            "alter": 40,
            "alter_monate": 480,
            "geburtsjahr": 1985,
            "geburtsmonat": 6,
        }

    def test_newborn_months_stay_a_newborn(self) -> None:
        resolved = resolve_demographics({"alter_monate": 3}, LANE_DATE, person_index=0)
        assert resolved["alter"] == 0
        assert resolved["geburtsjahr"] == 2025
        assert resolved["geburtsmonat"] == 3

    def test_consistent_pair_is_accepted(self) -> None:
        resolved = resolve_demographics(
            {"alter": 10, "geburtsjahr": 2015}, LANE_DATE, person_index=0
        )
        assert resolved["alter_monate"] == 125

    def test_lone_geburtsmonat_combines_with_the_default_age(self) -> None:
        # A lone birth month is a valid sparse shape for every month, not just
        # the policy month: the default adult born in that month.
        for month in range(1, 13):
            resolved = resolve_demographics(
                {"geburtsmonat": month}, LANE_DATE, person_index=0
            )
            assert resolved["geburtsmonat"] == month
            assert resolved["alter"] == 40
            expected_year = 1985 if month <= LANE_DATE.month else 1984
            assert resolved["geburtsjahr"] == expected_year

    def test_alter_with_geburtsmonat_honours_the_month(self) -> None:
        resolved = resolve_demographics(
            {"alter": 30, "geburtsmonat": 11}, LANE_DATE, person_index=0
        )
        # Birthday (November) not yet passed in June → born 1994.
        assert resolved["geburtsjahr"] == 1994
        assert resolved["geburtsmonat"] == 11
        assert resolved["alter"] == 30

    def test_none_demographic_raises_typed_error(self) -> None:
        with pytest.raises(GettsimInputError, match="must be an integer"):
            resolve_demographics({"alter": None}, LANE_DATE, person_index=0)

    def test_contradictory_alter_and_geburtsjahr_raise(self) -> None:
        with pytest.raises(GettsimInputError, match="contradicts the birth date"):
            resolve_demographics(
                {"alter": 40, "geburtsjahr": 2024}, LANE_DATE, person_index=0
            )

    def test_contradictory_alter_monate_raise(self) -> None:
        with pytest.raises(GettsimInputError, match="contradicts the birth date"):
            resolve_demographics(
                {"alter_monate": 0, "alter": 40}, LANE_DATE, person_index=0
            )

    def test_birth_after_the_policy_date_raises(self) -> None:
        with pytest.raises(GettsimInputError, match="after the policy date"):
            resolve_demographics({"geburtsjahr": 2030}, LANE_DATE, person_index=0)

    def test_non_integer_demographic_raises(self) -> None:
        with pytest.raises(GettsimInputError, match="must be an integer"):
            resolve_demographics({"alter": 40.5}, LANE_DATE, person_index=0)
        with pytest.raises(GettsimInputError, match="must be an integer"):
            resolve_demographics({"alter": True}, LANE_DATE, person_index=0)

    def test_geburtsmonat_out_of_range_raises(self) -> None:
        with pytest.raises(GettsimInputError, match="not in 1..12"):
            resolve_demographics({"geburtsmonat": 13}, LANE_DATE, person_index=0)


class TestProjection:
    def test_single_person_defaults_and_overlay(self) -> None:
        case = GettsimCase.single_person({"einnahmen__bruttolohn_m": 4000.0})
        projected = project_case(case, STUB_TEMPLATE, policy_date=LANE_DATE)
        assert projected.n_persons == 1
        assert projected.data["p_id"] == [0]
        assert projected.data["einnahmen__bruttolohn_m"] == [4000.0]
        # unset demographics resolve to one coherent adult, not per-column picks
        assert projected.data["alter"] == [40]
        assert projected.data["alter_monate"] == [480]
        assert projected.data["geburtsjahr"] == [1985]
        assert projected.data["geburtsmonat"] == [6]
        assert projected.data["sozialversicherung__rente__jahr_renteneintritt"] == [2020]
        # the nested mapper leaf is the flat column name
        assert projected.mapper["einnahmen"]["bruttolohn_m"] == "einnahmen__bruttolohn_m"
        assert projected.mapper["p_id"] == "p_id"

    def test_supplied_age_keeps_alter_monate_in_lockstep(self) -> None:
        # The blocker class this guards: an adult must never look like a
        # benefit-establishing newborn because alter_monate fell to 0.
        case = GettsimCase.single_person({"alter": 40})
        projected = project_case(case, STUB_TEMPLATE, policy_date=LANE_DATE)
        assert projected.data["alter"] == [40]
        assert projected.data["alter_monate"] == [480]

    def test_nested_and_qualified_person_inputs_mix(self) -> None:
        case = GettsimCase(
            persons=[{"einnahmen": {"bruttolohn_m": 3000.0}, "alter": 33}]
        )
        projected = project_case(case, STUB_TEMPLATE, policy_date=LANE_DATE)
        assert projected.data["einnahmen__bruttolohn_m"] == [3000.0]
        assert projected.data["alter"] == [33]

    def test_nested_and_qualified_collision_raises(self) -> None:
        case = GettsimCase(
            persons=[
                {
                    "einnahmen": {"bruttolohn_m": 1000.0},
                    "einnahmen__bruttolohn_m": 2000.0,
                }
            ]
        )
        with pytest.raises(GettsimInputError, match="set twice"):
            project_case(case, STUB_TEMPLATE, policy_date=LANE_DATE)

    def test_couple_links_are_symmetric(self) -> None:
        case = GettsimCase(
            persons=[
                {"einnahmen__bruttolohn_m": 4000.0, "einkommensteuer__gemeinsam_veranlagt": True},
                {"einkommensteuer__gemeinsam_veranlagt": True},
            ],
            spouse_pairs=[(0, 1)],
        )
        projected = project_case(case, STUB_TEMPLATE, policy_date=LANE_DATE)
        assert projected.data["p_id"] == [0, 1]
        assert projected.data["familie__p_id_ehepartner"] == [1, 0]
        assert projected.data["einkommensteuer__gemeinsam_veranlagt"] == [True, True]

    def test_parent_and_kindergeld_links(self) -> None:
        case = GettsimCase(
            persons=[{"einnahmen__bruttolohn_m": 4000.0}, {"alter": 10}],
            parents={1: (0, None)},
            kindergeld_recipients={1: 0},
        )
        projected = project_case(case, STUB_TEMPLATE, policy_date=LANE_DATE)
        assert projected.data["familie__p_id_elternteil_1"] == [NO_LINK, 0]
        assert projected.data["familie__p_id_elternteil_2"] == [NO_LINK, NO_LINK]
        assert projected.data["kindergeld__p_id_empfänger"] == [NO_LINK, 0]

    def test_explicit_grouping_ids_are_added(self) -> None:
        case = GettsimCase(
            persons=[{"alter": 40}, {"alter": 38}],
            grouping_ids={"bg_id": [0, 0], "wthh_id": [0, 1]},
        )
        projected = project_case(case, STUB_TEMPLATE, policy_date=LANE_DATE)
        assert projected.data["bg_id"] == [0, 0]
        assert projected.data["wthh_id"] == [0, 1]
        # grouping ids not in the template map at the top level
        assert projected.mapper["bg_id"] == "bg_id"

    def test_unknown_input_path_is_rejected(self) -> None:
        case = GettsimCase.single_person({"einnahmen__brutolohn_m": 4000.0})  # typo
        with pytest.raises(GettsimInputError, match="unknown GETTSIM input path"):
            project_case(case, STUB_TEMPLATE, policy_date=LANE_DATE)

    def test_p_id_is_reserved(self) -> None:
        case = GettsimCase(persons=[{"p_id": 5}])
        with pytest.raises(GettsimInputError, match="reserved"):
            project_case(case, STUB_TEMPLATE, policy_date=LANE_DATE)

    def test_grouping_ids_have_a_single_channel(self) -> None:
        # Every grouping id — including template-backed hh_id — goes through
        # the grouping_ids field, so the two channels can never silently
        # overwrite each other.
        for qname in ("bg_id", "hh_id"):
            case = GettsimCase(persons=[{qname: 0}])
            with pytest.raises(GettsimInputError, match="grouping_ids field"):
                project_case(case, STUB_TEMPLATE, policy_date=LANE_DATE)

    def test_structured_link_columns_cannot_be_set_raw(self) -> None:
        # Raw links bypass the graph validation (one-sided or self links run
        # silently and can shift joint assessment by thousands of euros).
        case = GettsimCase(persons=[{"familie__p_id_ehepartner": 1}, {}])
        with pytest.raises(GettsimInputError, match="structured relationship"):
            project_case(case, STUB_TEMPLATE, policy_date=LANE_DATE)

    def test_raw_link_columns_without_a_channel_are_graph_validated(self) -> None:
        # Link columns with no structured channel stay settable per person but
        # the final graph is still checked: range, self-links, integer type.
        template = dict(STUB_TEMPLATE)
        template[("bürgergeld", "p_id_einstandspartner")] = "IntColumn"
        out_of_range = GettsimCase(
            persons=[{"bürgergeld__p_id_einstandspartner": 99}, {}]
        )
        with pytest.raises(GettsimInputError, match="outside 0..1"):
            project_case(out_of_range, template, policy_date=LANE_DATE)
        self_link = GettsimCase(
            persons=[{"bürgergeld__p_id_einstandspartner": 0}, {}]
        )
        with pytest.raises(GettsimInputError, match="to itself"):
            project_case(self_link, template, policy_date=LANE_DATE)
        valid = GettsimCase(
            persons=[{"bürgergeld__p_id_einstandspartner": 1}, {}]
        )
        projected = project_case(valid, template, policy_date=LANE_DATE)
        assert projected.data["bürgergeld__p_id_einstandspartner"] == [1, NO_LINK]

    def test_malformed_relationship_tuples_raise_typed_errors(self) -> None:
        with pytest.raises(GettsimInputError, match="index pairs"):
            project_case(
                GettsimCase(persons=[{}, {}], spouse_pairs=[(0,)]),
                STUB_TEMPLATE,
                policy_date=LANE_DATE,
            )
        with pytest.raises(GettsimInputError, match="parent_1, parent_2"):
            project_case(
                GettsimCase(persons=[{}, {}], parents={1: (0,)}),
                STUB_TEMPLATE,
                policy_date=LANE_DATE,
            )

    def test_unknown_grouping_id_is_rejected(self) -> None:
        case = GettsimCase(persons=[{"alter": 40}], grouping_ids={"xx_id": [0]})
        with pytest.raises(GettsimInputError, match="unknown grouping id"):
            project_case(case, STUB_TEMPLATE, policy_date=LANE_DATE)

    def test_grouping_id_length_must_match_person_count(self) -> None:
        case = GettsimCase(persons=[{"alter": 40}], grouping_ids={"bg_id": [0, 0]})
        with pytest.raises(GettsimInputError, match="values for"):
            project_case(case, STUB_TEMPLATE, policy_date=LANE_DATE)

    def test_link_index_out_of_range_is_rejected(self) -> None:
        case = GettsimCase(persons=[{"alter": 40}], spouse_pairs=[(0, 2)])
        with pytest.raises(GettsimInputError, match="outside 0..0"):
            project_case(case, STUB_TEMPLATE, policy_date=LANE_DATE)

    def test_self_spouse_pair_is_rejected(self) -> None:
        case = GettsimCase(persons=[{}, {}], spouse_pairs=[(0, 0)])
        with pytest.raises(GettsimInputError, match="with itself"):
            project_case(case, STUB_TEMPLATE, policy_date=LANE_DATE)

    def test_polygamous_spouse_links_are_rejected(self) -> None:
        case = GettsimCase(persons=[{}, {}, {}], spouse_pairs=[(0, 1), (0, 2)])
        with pytest.raises(GettsimInputError, match="more than once"):
            project_case(case, STUB_TEMPLATE, policy_date=LANE_DATE)

    def test_child_cannot_be_its_own_parent(self) -> None:
        case = GettsimCase(persons=[{}, {}], parents={1: (1, None)})
        with pytest.raises(GettsimInputError, match="its own parent"):
            project_case(case, STUB_TEMPLATE, policy_date=LANE_DATE)

    def test_duplicate_parent_is_rejected(self) -> None:
        case = GettsimCase(persons=[{}, {}], parents={1: (0, 0)})
        with pytest.raises(GettsimInputError, match="both parents"):
            project_case(case, STUB_TEMPLATE, policy_date=LANE_DATE)

    def test_empty_case_is_rejected(self) -> None:
        with pytest.raises(GettsimInputError, match="at least one person"):
            project_case(GettsimCase(persons=[]), STUB_TEMPLATE, policy_date=LANE_DATE)


class TestCaseFromMapping:
    def test_unknown_case_field_is_rejected(self) -> None:
        # A typo like spouse_pair must not silently drop the relationship.
        with pytest.raises(GettsimInputError, match="unknown GETTSIM case field"):
            GettsimCase.from_mapping(
                {"persons": [{}], "spouse_pair": [(0, 1)]}
            )

    def test_round_trips_the_constructor_fields(self) -> None:
        case = GettsimCase.from_mapping(
            {
                "persons": [{}, {}],
                "spouse_pairs": [(0, 1)],
                "kindergeld_recipients": {},
            }
        )
        assert case.n_persons == 2
        assert case.spouse_pairs == [(0, 1)]


class TestNormalizePersonInputs:
    def test_nested_collapses_to_qualified_names(self) -> None:
        flat = normalize_person_inputs(
            {"sozialversicherung": {"kranken": {"beitrag": {"privat_versichert": True}}}}
        )
        assert flat == {"sozialversicherung__kranken__beitrag__privat_versichert": True}

    def test_qualified_keys_pass_through(self) -> None:
        flat = normalize_person_inputs({"einnahmen__bruttolohn_m": 4000.0, "alter": 40})
        assert flat == {"einnahmen__bruttolohn_m": 4000.0, "alter": 40}

    def test_non_string_key_is_rejected(self) -> None:
        with pytest.raises(GettsimInputError, match="must be a string"):
            normalize_person_inputs({("einnahmen", "bruttolohn_m"): 4000.0})


class TestDependencyGuard:
    def test_missing_gettsim_raises_typed_error(self, monkeypatch) -> None:
        # Simulate GETTSIM being absent even though it is installed here, so the
        # guard is covered in CI regardless of the extra.
        monkeypatch.setitem(sys.modules, "gettsim", None)
        from axiom_oracles.adapters.gettsim.runner import _gettsim

        with pytest.raises(GettsimNotInstalledError, match="uv sync"):
            _gettsim()

    def test_input_template_without_gettsim_raises_typed_error(self, monkeypatch) -> None:
        # The template path must go through the same typed guard, not leak a
        # ModuleNotFoundError from the direct import.
        monkeypatch.setitem(sys.modules, "gettsim", None)
        from axiom_oracles.adapters.gettsim.runner import _input_template_tree

        _input_template_tree.cache_clear()
        with pytest.raises(GettsimNotInstalledError, match="uv sync"):
            GettsimRunner(policy_date_str="1999-01-01").input_template()

    def test_invalid_policy_date_raises_typed_error(self) -> None:
        with pytest.raises(GettsimInputError, match="not a valid ISO date"):
            GettsimRunner(policy_date_str="not-a-date")
        with pytest.raises(GettsimInputError, match="not a valid ISO date"):
            GettsimRunner(policy_date_str=None)


class TestTargetLeafValidation:
    """Target validation is pure and fails fast, before the GETTSIM import."""

    def test_empty_targets_tree_is_rejected(self) -> None:
        from axiom_oracles.adapters.gettsim.runner import _target_leaves

        with pytest.raises(GettsimTargetError, match="empty targets tree"):
            _target_leaves({})

    def test_none_leaf_is_rejected(self) -> None:
        from axiom_oracles.adapters.gettsim.runner import _target_leaves

        with pytest.raises(GettsimTargetError, match="non-empty string leaf"):
            _target_leaves({"einkommensteuer": {"betrag_y_sn": None}})

    def test_duplicate_alias_is_rejected(self) -> None:
        # GETTSIM returns one result column per alias; a repeated alias would
        # silently drop one requested target.
        from axiom_oracles.adapters.gettsim.runner import _target_leaves

        with pytest.raises(GettsimTargetError, match="one target would be"):
            _target_leaves({"alter": "same", "geburtsjahr": "same"})

    def test_non_string_target_key_is_rejected(self) -> None:
        from axiom_oracles.adapters.gettsim.runner import _target_leaves

        with pytest.raises(GettsimTargetError, match="invalid tt_targets tree"):
            _target_leaves({("einkommensteuer", "betrag_y_sn"): "x"})

    def test_string_leaves_are_collected_in_order(self) -> None:
        from axiom_oracles.adapters.gettsim.runner import _target_leaves

        assert _target_leaves(SEED_TARGETS_FOR_LEAF_CHECK) == [
            "income_tax_y_sn",
            "health_ee_m",
        ]


# --------------------------------------------------------------------------
# Live oracle tests: require GETTSIM. Expectations carry statutory anchors in
# the module docstring; engine-pinned regression values are labeled as such.
# The pure tests above run everywhere; only the classes below are gated, so a
# missing optional dependency skips the live oracle checks without hiding the
# projection/guard coverage. A dedicated CI job (gettsim-live) syncs the
# gettsim fork and runs exactly these, so main cannot go green without them.
# --------------------------------------------------------------------------

try:
    import gettsim as _gettsim_mod

    GETTSIM_AVAILABLE = True
    GETTSIM_VERSION = _gettsim_mod.__version__
except ImportError:  # pragma: no cover - exercised in CI without the extra
    GETTSIM_AVAILABLE = False
    GETTSIM_VERSION = None

gettsim_required = pytest.mark.skipif(
    not GETTSIM_AVAILABLE,
    reason="install the gettsim extra: uv sync --extra gettsim",
)

#: GETTSIM's float arithmetic carries ~1e-13 noise on statute-exact amounts
#: (342.00 stored as 341.99999999999994); 1e-6 absorbs it while still failing
#: on any real cent-level regression.
FLOAT_NOISE = 1e-6

SEED_TARGETS = {
    "einkommensteuer": {"betrag_y_sn": "income_tax_y_sn"},
    "sozialversicherung": {
        "kranken": {"beitrag": {"betrag_versicherter_m": "health_ee_m"}},
        "rente": {"beitrag": {"betrag_versicherter_m": "pension_ee_m"}},
        "arbeitslosen": {"beitrag": {"betrag_versicherter_m": "unemp_ee_m"}},
        "pflege": {"beitrag": {"betrag_versicherter_m": "ltc_ee_m"}},
    },
    "kindergeld": {"betrag_m": "kindergeld_m"},
    "solidaritätszuschlag": {"betrag_y_sn": "soli_y_sn"},
}


@gettsim_required
class TestGettsimSeedCase:
    """The bootstrap-verified single worker at EUR 4,000/month gross.

    Employee social-contribution anchors (module docstring has the instrument
    chain): health 342.00, pension 372.00, unemployment 52.00, long-term care
    96.00 (childless). Annual income tax 6,433 is an engine-pinned regression
    value. The amounts are identical at the seed date (2025-06-01) and the
    lane date (2025-06-30), so both are pinned.
    """

    @pytest.mark.parametrize("policy_date", ["2025-06-01", "2025-06-30"])
    def test_single_worker_matches_hand_computed_statute(self, policy_date) -> None:
        runner = GettsimRunner(policy_date_str=policy_date)
        out = runner.compute(
            GettsimCase.single_person({"einnahmen__bruttolohn_m": 4000.0}),
            SEED_TARGETS,
        )
        assert out["health_ee_m"] == pytest.approx([342.0], abs=FLOAT_NOISE)
        assert out["pension_ee_m"] == pytest.approx([372.0], abs=FLOAT_NOISE)
        assert out["unemp_ee_m"] == pytest.approx([52.0], abs=FLOAT_NOISE)
        assert out["ltc_ee_m"] == pytest.approx([96.0], abs=FLOAT_NOISE)
        assert out["income_tax_y_sn"] == pytest.approx([6433.0], abs=FLOAT_NOISE)
        assert out["kindergeld_m"] == pytest.approx([0.0], abs=FLOAT_NOISE)
        assert out["soli_y_sn"] == pytest.approx([0.0], abs=FLOAT_NOISE)

    def test_result_pins_the_gettsim_version(self) -> None:
        runner = GettsimRunner(policy_date_str="2025-06-01")
        result = runner.run_case(
            GettsimCase.single_person({"einnahmen__bruttolohn_m": 4000.0}),
            {"sozialversicherung": {"kranken": {"beitrag": {"betrag_versicherter_m": "health_ee_m"}}}},
        )
        assert result.gettsim_version == GETTSIM_VERSION
        assert result.policy_date_str == "2025-06-01"
        assert result.scalar("health_ee_m") == pytest.approx(342.0, abs=FLOAT_NOISE)
        assert runner.run_metadata()["gettsim_version"] == GETTSIM_VERSION

    def test_unsupported_gettsim_version_fails_loud(self, monkeypatch) -> None:
        # The adapter's pinned expectations are validated against exactly the
        # locked engine; a drifted install must not shift oracle values quietly.
        monkeypatch.setattr(_gettsim_mod, "__version__", "9.9.9")
        from axiom_oracles.adapters.gettsim.runner import _gettsim

        with pytest.raises(GettsimAdapterError, match="not been validated"):
            _gettsim()


@gettsim_required
class TestGettsimKindergeldCase:
    """One-child household across the two SteFeG Kindergeld stages.

    Steuerfortentwicklungsgesetz (BGBl. 2024 I Nr. 449): Art. 1 Nr. 4 sets
    s. 66(1) EStG to 255 EUR/month for 2025; Art. 2 Nr. 4 to 259 EUR/month
    from 2026 (Art. 10 staging). Executing both dates pins the 2025 validation
    year AND proves the runner's date parameterisation is real — a runner
    hard-coded to mid-2025 would fail the 2026 leg.
    """

    def _case(self) -> GettsimCase:
        # The child carries only its birth year; age is derived per policy
        # date (a fixed alter would contradict the birth date at one of the
        # two dates below — the coherence guard enforces that).
        return GettsimCase(
            persons=[
                {"einnahmen__bruttolohn_m": 4000.0},  # parent, p_id 0
                {"geburtsjahr": 2015},                # child, p_id 1
            ],
            parents={1: (0, None)},
            kindergeld_recipients={1: 0},
        )

    @pytest.mark.parametrize(
        ("policy_date", "monthly_amount"),
        [("2025-06-01", 255.0), ("2026-01-01", 259.0)],
    )
    def test_recipient_is_paid_the_staged_statutory_amount(
        self, policy_date, monthly_amount
    ) -> None:
        runner = GettsimRunner(policy_date_str=policy_date)
        out = runner.compute(self._case(), {"kindergeld": {"betrag_m": "kindergeld_m"}})
        # Recipient (parent, p_id 0) is paid; the child (p_id 1) is paid 0.
        assert out["kindergeld_m"] == pytest.approx(
            [monthly_amount, 0.0], abs=FLOAT_NOISE
        )

    def test_scalar_helper_refuses_multi_person_reduction(self) -> None:
        runner = GettsimRunner(policy_date_str="2025-06-01")
        result = runner.run_case(self._case(), {"kindergeld": {"betrag_m": "kindergeld_m"}})
        with pytest.raises(Exception, match="per-person"):
            result.scalar("kindergeld_m")


@gettsim_required
class TestFullTemplateIsCleanByConstruction:
    """Add-until-clean: the full template covers every dependency uniformly.

    Buergergeld (SGB II) sits deep in the DAG, above income, social-insurance,
    housing, and family subtrees. Discovering the *full* input template and
    defaulting it computes Buergergeld with no missing-column error, and
    pruning a single required column reproduces the "not clean" state, which
    the adapter surfaces as a typed error instead of a silent partial result.
    """

    def test_deep_target_computes_from_full_template(self) -> None:
        runner = GettsimRunner(policy_date_str="2025-06-01")
        case = GettsimCase.single_person(
            {
                "einnahmen__bruttolohn_m": 1200.0,
                "wohnen__bruttokaltmiete_m_hh": 600.0,
                "wohnen__heizkosten_m_hh": 80.0,
                "wohnen__wohnfläche_hh": 45.0,
            }
        )
        out = runner.compute(case, {"bürgergeld": {"betrag_m_bg": "buergergeld_m_bg"}})
        # Engine-pinned regression value for this exact case (1,200 EUR gross,
        # 680 EUR housing): the 563 EUR RBSFV-2025 Regelbedarf plus housing
        # minus counted income.
        assert out["buergergeld_m_bg"] == pytest.approx(
            [584.4539882548477], abs=FLOAT_NOISE
        )

    def test_pruned_template_surfaces_missing_columns_loudly(self, monkeypatch) -> None:
        runner = GettsimRunner(policy_date_str="2025-06-01")
        full = runner.flat_input_template()
        dropped = "sozialversicherung__rente__jahr_renteneintritt"
        pruned = {path: dt for path, dt in full.items() if "__".join(path) != dropped}
        monkeypatch.setattr(runner, "flat_input_template", lambda: pruned)
        with pytest.raises(GettsimInputError, match="missing input columns"):
            runner.compute(
                GettsimCase.single_person({"einnahmen__bruttolohn_m": 4000.0}),
                {"einkommensteuer": {"betrag_y_sn": "income_tax_y_sn"}},
            )


@gettsim_required
class TestExplicitGroupingIdsChangeTheMeansTest:
    """The complex-household escape hatch is semantic, not just column-adding.

    Two unlinked adults in one household derive separate Bedarfsgemeinschaften
    (flatmates): the earner gets 0, the other draws the full 563 EUR
    Regelbedarfsstufe 1 (RBSFV 2025). Forcing both into ONE
    Bedarfsgemeinschaft via explicit grouping ids makes the 2,500 EUR earner's
    income count against the joint claim, extinguishing it — the ids override
    GETTSIM's derivation and change the means test.
    """

    def _duo(self, grouping_ids) -> GettsimCase:
        return GettsimCase(
            persons=[{"einnahmen__bruttolohn_m": 2500.0}, {}],
            grouping_ids=grouping_ids,
        )

    def test_derived_flatmates_get_separate_claims(self) -> None:
        out = GettsimRunner().compute(
            self._duo({}), {"bürgergeld": {"betrag_m_bg": "bg"}}
        )
        assert out["bg"] == pytest.approx([0.0, 563.0], abs=FLOAT_NOISE)

    def test_forced_single_bg_is_jointly_means_tested(self) -> None:
        out = GettsimRunner().compute(
            self._duo(
                {
                    "bg_id": [0, 0],
                    "eg_id": [0, 0],
                    "fg_id": [0, 0],
                    "wthh_id": [0, 0],
                    "sn_id": [0, 1],
                }
            ),
            {"bürgergeld": {"betrag_m_bg": "bg"}},
        )
        assert out["bg"] == pytest.approx([0.0, 0.0], abs=FLOAT_NOISE)


@gettsim_required
class TestGettsimTypedFailures:
    def test_unknown_target_raises_typed_error(self) -> None:
        runner = GettsimRunner(policy_date_str="2025-06-01")
        with pytest.raises(GettsimTargetError, match="unknown GETTSIM target"):
            runner.compute(
                GettsimCase.single_person({"einnahmen__bruttolohn_m": 4000.0}),
                {"einkommensteuer": {"does_not_exist_y_sn": "x"}},
            )

    def test_unknown_input_is_caught_before_gettsim_ignores_it(self) -> None:
        # GETTSIM silently ignores unknown input columns; the adapter must fail
        # first. Uses the real template so the guard is exercised end to end.
        runner = GettsimRunner(policy_date_str="2025-06-01")
        with pytest.raises(GettsimInputError, match="unknown GETTSIM input path"):
            runner.compute(
                GettsimCase.single_person({"einnahmen__brutto_lohn_m": 4000.0}),  # typo
                {"einkommensteuer": {"betrag_y_sn": "income_tax_y_sn"}},
            )

    def test_incoherent_demographics_never_reach_gettsim(self) -> None:
        # The chimera-person blocker class: an adult with newborn months must
        # raise, not run (it flips Elterngeld-style eligibility silently).
        runner = GettsimRunner(policy_date_str="2025-06-01")
        with pytest.raises(GettsimInputError, match="contradicts the birth date"):
            runner.compute(
                GettsimCase.single_person({"alter": 40, "alter_monate": 0}),
                {"einkommensteuer": {"betrag_y_sn": "income_tax_y_sn"}},
            )
