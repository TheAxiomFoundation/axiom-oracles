"""GETTSIM adapter: pure-projection unit tests + live-when-installed oracle tests.

The projection tests build a hand-written input template and assert the case →
GETTSIM input projection, the dtype-first defaults, the relationship links, and
the input-path guard — all without importing ``gettsim`` (the pure logic lives
in :mod:`axiom_oracles.adapters.gettsim.case`).

The live tests are gated on ``gettsim`` being importable and check statute-exact
2025 German amounts end to end: the verified single-worker seed case, a
one-child Kindergeld case, the full-template "add until clean" property, and the
typed failures for unknown targets and unknown inputs. Expectations are the
hand-verified statutory amounts recorded in the Germany lane bootstrap.
"""

from __future__ import annotations

import sys

import pytest

from axiom_oracles.adapters.gettsim import (
    GettsimCase,
    GettsimInputError,
    GettsimNotInstalledError,
    GettsimRunner,
    GettsimTargetError,
    default_value,
    normalize_person_inputs,
    project_case,
)
from axiom_oracles.adapters.gettsim.case import (
    DEFAULT_ALTER_BEGINN,
    DEFAULT_RENTENEINTRITT_JAHR,
    NO_LINK,
)

# A small hand-written stand-in for the GETTSIM input-dtype template. It carries
# the columns whose defaults are load-bearing or easy to get wrong: real years
# vs. "jahr"-substring booleans/amounts, age-indexed table keys, p_id links, and
# the sole input grouping id (hh_id).
STUB_TEMPLATE: dict[tuple[str, ...], str] = {
    ("p_id",): "IntColumn",
    ("hh_id",): "IntColumn",
    ("alter",): "IntColumn",
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
        # to False / 0.0, not 2020. This is the seed script's latent-bug class.
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


class TestProjection:
    def test_single_person_defaults_and_overlay(self) -> None:
        case = GettsimCase.single_person({"einnahmen__bruttolohn_m": 4000.0})
        projected = project_case(case, STUB_TEMPLATE)
        assert projected.n_persons == 1
        assert projected.data["p_id"] == [0]
        assert projected.data["einnahmen__bruttolohn_m"] == [4000.0]
        # unset demographics take their defaults
        assert projected.data["geburtsjahr"] == [1980]
        assert projected.data["sozialversicherung__rente__jahr_renteneintritt"] == [2020]
        # the nested mapper leaf is the flat column name
        assert projected.mapper["einnahmen"]["bruttolohn_m"] == "einnahmen__bruttolohn_m"
        assert projected.mapper["p_id"] == "p_id"

    def test_nested_and_qualified_person_inputs_mix(self) -> None:
        case = GettsimCase(
            persons=[{"einnahmen": {"bruttolohn_m": 3000.0}, "alter": 33}]
        )
        projected = project_case(case, STUB_TEMPLATE)
        assert projected.data["einnahmen__bruttolohn_m"] == [3000.0]
        assert projected.data["alter"] == [33]

    def test_couple_links_are_symmetric(self) -> None:
        case = GettsimCase(
            persons=[
                {"einnahmen__bruttolohn_m": 4000.0, "einkommensteuer__gemeinsam_veranlagt": True},
                {"einkommensteuer__gemeinsam_veranlagt": True},
            ],
            spouse_pairs=[(0, 1)],
        )
        projected = project_case(case, STUB_TEMPLATE)
        assert projected.data["p_id"] == [0, 1]
        assert projected.data["familie__p_id_ehepartner"] == [1, 0]
        assert projected.data["einkommensteuer__gemeinsam_veranlagt"] == [True, True]

    def test_parent_and_kindergeld_links(self) -> None:
        case = GettsimCase(
            persons=[{"einnahmen__bruttolohn_m": 4000.0}, {"alter": 10}],
            parents={1: (0, None)},
            kindergeld_recipients={1: 0},
        )
        projected = project_case(case, STUB_TEMPLATE)
        assert projected.data["familie__p_id_elternteil_1"] == [NO_LINK, 0]
        assert projected.data["familie__p_id_elternteil_2"] == [NO_LINK, NO_LINK]
        assert projected.data["kindergeld__p_id_empfänger"] == [NO_LINK, 0]

    def test_explicit_grouping_ids_are_added(self) -> None:
        case = GettsimCase(
            persons=[{"alter": 40}, {"alter": 38}],
            grouping_ids={"bg_id": [0, 0], "wthh_id": [0, 1]},
        )
        projected = project_case(case, STUB_TEMPLATE)
        assert projected.data["bg_id"] == [0, 0]
        assert projected.data["wthh_id"] == [0, 1]
        # grouping ids not in the template map at the top level
        assert projected.mapper["bg_id"] == "bg_id"

    def test_unknown_input_path_is_rejected(self) -> None:
        case = GettsimCase.single_person({"einnahmen__brutolohn_m": 4000.0})  # typo
        with pytest.raises(GettsimInputError, match="unknown GETTSIM input path"):
            project_case(case, STUB_TEMPLATE)

    def test_unknown_grouping_id_is_rejected(self) -> None:
        case = GettsimCase(persons=[{"alter": 40}], grouping_ids={"xx_id": [0]})
        with pytest.raises(GettsimInputError, match="unknown grouping id"):
            project_case(case, STUB_TEMPLATE)

    def test_grouping_id_length_must_match_person_count(self) -> None:
        case = GettsimCase(persons=[{"alter": 40}], grouping_ids={"bg_id": [0, 0]})
        with pytest.raises(GettsimInputError, match="values for"):
            project_case(case, STUB_TEMPLATE)

    def test_link_index_out_of_range_is_rejected(self) -> None:
        case = GettsimCase(persons=[{"alter": 40}], spouse_pairs=[(0, 2)])
        with pytest.raises(GettsimInputError, match="outside 0..0"):
            project_case(case, STUB_TEMPLATE)

    def test_empty_case_is_rejected(self) -> None:
        with pytest.raises(GettsimInputError, match="at least one person"):
            project_case(GettsimCase(persons=[]), STUB_TEMPLATE)


class TestNormalizePersonInputs:
    def test_nested_collapses_to_qualified_names(self) -> None:
        flat = normalize_person_inputs(
            {"sozialversicherung": {"kranken": {"beitrag": {"privat_versichert": True}}}}
        )
        assert flat == {"sozialversicherung__kranken__beitrag__privat_versichert": True}

    def test_qualified_keys_pass_through(self) -> None:
        flat = normalize_person_inputs({"einnahmen__bruttolohn_m": 4000.0, "alter": 40})
        assert flat == {"einnahmen__bruttolohn_m": 4000.0, "alter": 40}


class TestDependencyGuard:
    def test_missing_gettsim_raises_typed_error(self, monkeypatch) -> None:
        # Simulate GETTSIM being absent even though it is installed here, so the
        # guard is covered in CI regardless of the extra.
        monkeypatch.setitem(sys.modules, "gettsim", None)
        from axiom_oracles.adapters.gettsim.runner import _gettsim

        with pytest.raises(GettsimNotInstalledError, match="uv pip install"):
            _gettsim()


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

    def test_string_leaves_are_collected_in_order(self) -> None:
        from axiom_oracles.adapters.gettsim.runner import _target_leaves

        assert _target_leaves(SEED_TARGETS_FOR_LEAF_CHECK) == [
            "income_tax_y_sn",
            "health_ee_m",
        ]


# --------------------------------------------------------------------------
# Live oracle tests: require GETTSIM. Expectations are hand-verified 2025 law.
# The pure tests above run everywhere; only the classes below are gated, so a
# missing optional dependency skips the live oracle checks without hiding the
# projection/guard coverage.
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
    reason="install the gettsim extra: uv pip install -e '.[gettsim]'",
)

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

    Employee social-contribution amounts are statute-exact by hand: health
    342.00 (8.55% incl. half the average Zusatzbeitrag), pension 372.00 (9.3%),
    unemployment 52.00 (1.3%), long-term care 96.00 (2.4% childless). Annual
    income tax 6,433; Kindergeld and Soli zero. The five SSC amounts and the
    income tax are identical at the seed date (2025-06-01) and the lane date
    (2025-06-30), so both are pinned.
    """

    @pytest.mark.parametrize("policy_date", ["2025-06-01", "2025-06-30"])
    def test_single_worker_matches_hand_computed_statute(self, policy_date) -> None:
        runner = GettsimRunner(policy_date_str=policy_date)
        out = runner.compute(
            GettsimCase.single_person({"einnahmen__bruttolohn_m": 4000.0}),
            SEED_TARGETS,
        )
        # Statute-exact to the cent; GETTSIM's float arithmetic leaves ~1e-13
        # noise (342.00 stored as 341.99999999999994), so compare with a cent
        # tolerance — the discipline the comparison layer applies too.
        assert out["health_ee_m"] == pytest.approx([342.0], abs=0.01)
        assert out["pension_ee_m"] == pytest.approx([372.0], abs=0.01)
        assert out["unemp_ee_m"] == pytest.approx([52.0], abs=0.01)
        assert out["ltc_ee_m"] == pytest.approx([96.0], abs=0.01)
        assert out["income_tax_y_sn"] == pytest.approx([6433.0], abs=0.01)
        assert out["kindergeld_m"] == pytest.approx([0.0], abs=0.01)
        assert out["soli_y_sn"] == pytest.approx([0.0], abs=0.01)

    def test_result_pins_the_gettsim_version(self) -> None:
        runner = GettsimRunner(policy_date_str="2025-06-01")
        result = runner.run_case(
            GettsimCase.single_person({"einnahmen__bruttolohn_m": 4000.0}),
            {"sozialversicherung": {"kranken": {"beitrag": {"betrag_versicherter_m": "health_ee_m"}}}},
        )
        assert result.gettsim_version == GETTSIM_VERSION
        assert result.policy_date_str == "2025-06-01"
        assert result.scalar("health_ee_m") == pytest.approx(342.0, abs=0.01)
        assert runner.run_metadata()["gettsim_version"] == GETTSIM_VERSION


@gettsim_required
class TestGettsimKindergeldCase:
    """One-child household: the parent is paid Kindergeld for the child.

    At the 2025 policy date GETTSIM returns EUR 255.00/month for the first
    child (verified empirically; the 2026 amount is 259.00, so the value moves
    with the policy date — pinning 255.00 pins the 2025 validation year).
    """

    def _case(self) -> GettsimCase:
        return GettsimCase(
            persons=[
                {"einnahmen__bruttolohn_m": 4000.0},  # parent, p_id 0
                {"alter": 10, "geburtsjahr": 2015},   # child, p_id 1
            ],
            parents={1: (0, None)},
            kindergeld_recipients={1: 0},
        )

    def test_parent_receives_255_per_month_in_2025(self) -> None:
        runner = GettsimRunner(policy_date_str="2025-06-01")
        out = runner.compute(self._case(), {"kindergeld": {"betrag_m": "kindergeld_m"}})
        # Recipient (parent, p_id 0) is paid 255; the child (p_id 1) is paid 0.
        assert out["kindergeld_m"] == pytest.approx([255.0, 0.0], abs=0.01)

    def test_scalar_helper_refuses_multi_person_reduction(self) -> None:
        runner = GettsimRunner(policy_date_str="2025-06-01")
        result = runner.run_case(self._case(), {"kindergeld": {"betrag_m": "kindergeld_m"}})
        with pytest.raises(Exception, match="per-person"):
            result.scalar("kindergeld_m")


@gettsim_required
class TestFullTemplateIsCleanByConstruction:
    """Add-until-clean: the full template covers every transitive dependency.

    Bürgergeld (SGB II) sits deep in the DAG, above income, social-insurance,
    housing, and family subtrees. Discovering the *full* input template and
    defaulting it computes Bürgergeld with no missing-column error — whereas a
    per-target template misses transitive deps. Pruning a single required
    column reproduces the "not clean" state, and the adapter surfaces it as a
    typed error instead of a silent partial result.
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
        assert out["buergergeld_m_bg"][0] >= 0.0

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
