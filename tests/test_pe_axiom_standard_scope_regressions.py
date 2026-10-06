"""A RuleSpec dispute's identity must not depend on its submitted companion."""

from __future__ import annotations

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from axiom_oracles.comparison.pe_axiom_standard import (
    CompanionResolver,
    Ratchet,
    Record,
    SourceUnavailable,
    check_records,
    companion_scope_problems,
    validate_axiom_side_fields,
)


OLD_MERGED_SHA = "0a8d9dd557c120bc081c0b152e149faf43ccef1a"
MAIN_SHA = "2066cef61139ebe381b617b37eb6dabcbae109e7"
SALT = "us:policies/income_tax/salt_deduction_pipeline#federal_salt_deduction"
SALT_PATH = "us/policies/income_tax/salt_deduction_pipeline.test.yaml"
SAVER = "us:policies/income_tax/savers_credit_pipeline#federal_savers_credit"
SAVER_PATH = "us/policies/income_tax/savers_credit_pipeline.test.yaml"
SAVER_CASE = "single-at-50-percent-limit-inclusive"


def _case(name: str, concept: str, value: str) -> str:
    return yaml.safe_dump([{"name": name, "output": {concept: value}}])


def _salt_with_saver(
    *, sha: str = OLD_MERGED_SHA, repo: str = "rulespec-us"
) -> Record:
    return Record(
        source="dispositions/us-salt-deduction-grid.yaml",
        id="salt-low-agi-engine-cap",
        suite="us-salt-deduction-grid",
        concept=SALT,
        basis="rows",
        pe_issue="https://github.com/PolicyEngine/policyengine-us/issues/9167",
        entry={
            "kind": "amount_difference",
            "axiom_companion": {
                "legal_ids": [SAVER],
                "tests": [f"{repo}@{sha}:{SAVER_PATH}#{SAVER_CASE}"],
            },
        },
        case_ids=("salt-low-agi-engine-cap",),
        axiom_values={"salt-low-agi-engine-cap": (10000.0,)},
    )


class _Source:
    def __init__(self, *, sha=OLD_MERGED_SHA, repo="rulespec-us"):
        # These are the real old/current RuleSpec file-presence relationships:
        # the saver case predates SALT, remains unchanged on main, and the
        # disputed SALT output is now asserted by its own companion on main.
        saver = _case(SAVER_CASE, SAVER, "1000")
        self.files = {
            (repo, sha, SAVER_PATH): saver,
            (repo, MAIN_SHA, SAVER_PATH): saver,
            ("rulespec-us", MAIN_SHA, SALT_PATH): _case(
                "salt-low-agi-engine-cap", SALT, "10000"
            ),
        }

    def read(self, repo, sha, path):
        return self.files.get((repo, sha, path))

    def is_merged(self, repo, sha):
        return True

    def main_sha(self, repo):
        return MAIN_SHA


def test_older_merged_saver_pin_cannot_back_the_salt_dispute() -> None:
    record = _salt_with_saver()
    source = _Source()
    assert source.read("rulespec-us", OLD_MERGED_SHA, SALT_PATH) is None
    assert validate_axiom_side_fields(record.entry, record.label()) == []
    assert companion_scope_problems(record) == []
    assert check_records([record], Ratchet(0)) == []

    problems = CompanionResolver(source).resolve(record)
    assert any("declare it among legal_ids" in problem for problem in problems)


def test_disputed_concept_discovery_uses_its_canonical_repository() -> None:
    record = _salt_with_saver(repo="rulespec-us-ca")
    source = _Source(repo="rulespec-us-ca")
    assert companion_scope_problems(record) == []

    problems = CompanionResolver(source).resolve(record)
    assert any("declare it among legal_ids" in problem for problem in problems)


@pytest.mark.parametrize("unavailable", ["head", "document"])
def test_omitted_disputed_concept_cannot_hide_behind_unavailable_main(
    unavailable: str,
) -> None:
    class Unavailable(_Source):
        def main_sha(self, repo):
            return None if unavailable == "head" else super().main_sha(repo)

        def read(self, repo, sha, path):
            if unavailable == "document" and (repo, sha, path) == (
                "rulespec-us", MAIN_SHA, SALT_PATH
            ):
                raise SourceUnavailable("503")
            return super().read(repo, sha, path)

    problems = CompanionResolver(Unavailable(), require_merged=False).resolve(
        _salt_with_saver()
    )
    assert problems and any("disputed concept" in problem for problem in problems)


def test_absent_comparison_surface_module_keeps_country_scoped_companions() -> None:
    record = _salt_with_saver()
    record.concept = "us:tax/federal-income-tax#eitc"
    assert CompanionResolver(_Source()).resolve(record) == []


def test_pinned_rulespec_output_is_required_even_if_removed_from_main() -> None:
    source = _Source()
    source.files.pop(("rulespec-us", MAIN_SHA, SALT_PATH))
    source.files[("rulespec-us", OLD_MERGED_SHA, SALT_PATH)] = _case(
        "salt-low-agi-engine-cap", SALT, "10000"
    )
    problems = CompanionResolver(source).resolve(_salt_with_saver())
    assert any("declare it among legal_ids" in problem for problem in problems)


@settings(max_examples=300, deadline=None, derandomize=True)
@given(
    sha_number=st.integers(min_value=0, max_value=2**128 - 1),
    repo=st.sampled_from(["rulespec-us", "rulespec-us-ca"]),
    require_merged=st.booleans(),
)
def test_main_rulespec_output_requires_its_id_for_every_submitted_pin(
    sha_number: int, repo: str, require_merged: bool
) -> None:
    """Changing a companion's commit or repo cannot change dispute scope."""
    sha = f"{sha_number:040x}"
    problems = CompanionResolver(
        _Source(sha=sha, repo=repo), require_merged=require_merged
    ).resolve(_salt_with_saver(sha=sha, repo=repo))
    assert any("declare it among legal_ids" in problem for problem in problems)
