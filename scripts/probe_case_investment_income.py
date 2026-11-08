#!/usr/bin/env python3
"""Print the artifact figures docs/case-investment-income.md cites.

Reads the person table of the certified Populace US 2024 artifact, which the
population loader resolves and checks against its sha256 pin, and prints raw
2024 values, unweighted, as JSON. It runs no PolicyEngine simulation.

- ``columns``: each dividend and capital-gain column's nonzero persons, sum
  and the tax-unit roles (``tax_unit_role_input``) that carry it.
- ``legacy_dividend_income``: the stored legacy ``dividend_income`` column
  against the qualified and non-qualified split the loader reads instead.
- ``schedule_d_fold``: the loader's fold, per return (a tax unit's head and
  spouse together, each other member alone).
- ``household_cases``: household Cases (person 0 the head, anyone under 18
  "Child", every other adult "Other", in artifact row order, as
  ``populations/populace_us.py`` builds them) where the two oldest adults,
  whom PolicyEngine and the Axiom bridge price as filers when a Case names
  no spouse, pair one person's line 7a with another's Schedule D amount.

    uv run python scripts/probe_case_investment_income.py [out.json]
"""

from __future__ import annotations

import json
import sys

import pandas as pd

from axiom_oracles.populations.populace_us import (
    POPULACE_PINS,
    POPULACE_US_DATASET,
    _resolve_populace_dataset,
)

COLUMNS = (
    "dividend_income",
    "qualified_dividend_income",
    "non_qualified_dividend_income",
    "non_sch_d_capital_gains",
    "long_term_capital_gains",
    "short_term_capital_gains",
)
FILER_ROLES = {"HEAD", "SPOUSE"}
PERSON_COLUMNS = (
    *COLUMNS,
    "person_tax_unit_id",
    "person_household_id",
    "tax_unit_role_input",
    "age",
    "employment_income",
)


def _column_figures(person: pd.DataFrame) -> dict[str, dict]:
    figures = {}
    for column in COLUMNS:
        values = person[column]
        nonzero = values != 0
        figures[column] = {
            "nonzero_persons": int(nonzero.sum()),
            "negative_persons": int((values < 0).sum()),
            "sum": float(values.sum()),
            "nonzero_persons_by_role": person.loc[nonzero, "role"]
            .value_counts()
            .to_dict(),
        }
    return figures


def _legacy_dividend_income(person: pd.DataFrame) -> dict[str, float | int]:
    legacy = person["dividend_income"]
    qualified = person["qualified_dividend_income"]
    non_qualified = person["non_qualified_dividend_income"]
    both = (legacy != 0) & (qualified != 0)
    legacy_only = (legacy != 0) & (qualified == 0) & (non_qualified == 0)
    return {
        "persons_with_legacy_and_qualified": int(both.sum()),
        "of_those_legacy_below_qualified": int((both & (legacy < qualified)).sum()),
        "persons_with_legacy_and_no_split": int(legacy_only.sum()),
        "legacy_sum_on_persons_with_no_split": float(legacy[legacy_only].sum()),
    }


def _fold(person: pd.DataFrame) -> pd.DataFrame:
    """Form 1040 line 7 Exception 1, per return, as fold_tax_unit_returns."""
    schedule_d = (person["long_term_capital_gains"] != 0) | (
        person["short_term_capital_gains"] != 0
    )
    filer = person["role"].isin(FILER_ROLES)
    # A filer's return is every filer of the tax unit; anyone else files alone.
    return_id = (
        person["person_tax_unit_id"]
        .astype(str)
        .where(filer, "person-" + person["row"].astype(str))
    )
    files_schedule_d = schedule_d.groupby(return_id).transform("any")
    distributions = person["non_sch_d_capital_gains"].clip(lower=0)
    return person.assign(
        schedule_d=schedule_d,
        line_7a=distributions.where(~files_schedule_d, 0.0),
        folded=(distributions > 0) & files_schedule_d,
    )


def _schedule_d_fold(person: pd.DataFrame) -> dict[str, object]:
    with_line_7a = person["non_sch_d_capital_gains"] > 0
    capital_loss = (person["long_term_capital_gains"] < 0) | (
        person["short_term_capital_gains"] < 0
    )
    return {
        "persons_with_line_7a": int(with_line_7a.sum()),
        "persons_with_line_7a_by_role": person.loc[with_line_7a, "role"]
        .value_counts()
        .to_dict(),
        "persons_with_schedule_d_by_role": person.loc[person["schedule_d"], "role"]
        .value_counts()
        .to_dict(),
        "tax_units_with_line_7a": int(
            person.loc[with_line_7a, "person_tax_unit_id"].nunique()
        ),
        "persons_folded": int(person["folded"].sum()),
        "persons_folded_with_a_capital_loss": int(
            (person["folded"] & capital_loss).sum()
        ),
        "tax_units_with_line_7a_after_the_fold": int(
            person.loc[person["line_7a"] > 0, "person_tax_unit_id"].nunique()
        ),
    }


def _household_cases(person: pd.DataFrame) -> dict[str, object]:
    with_line_7a = person["line_7a"] > 0
    households = person.loc[with_line_7a, "person_household_id"].unique()
    beside = paired = 0
    paired_line_7a = 0.0
    for _, people in person[person["person_household_id"].isin(households)].groupby(
        "person_household_id", sort=False
    ):
        line_7a_units = set(people.loc[people["line_7a"] > 0, "person_tax_unit_id"])
        if (
            people["schedule_d"] & ~people["person_tax_unit_id"].isin(line_7a_units)
        ).any():
            beside += 1
        # runner._tax_filers: adults by age, then earned income, descending;
        # a stable sort keeps row order on ties.
        pair = (
            people[people["age"] >= 18]
            .sort_values(
                ["age", "employment_income", "row"],
                ascending=[False, False, True],
            )
            .head(2)
        )
        if (
            len(pair) == 2
            and pair["schedule_d"].any()
            and (pair["line_7a"] > 0).any()
            and pair["person_tax_unit_id"].nunique() == 2
        ):
            paired += 1
            paired_line_7a += float(pair["line_7a"].sum())
    return {
        "households": int(person["person_household_id"].nunique()),
        "households_with_line_7a": int(len(households)),
        "households_with_line_7a_beside_another_tax_units_schedule_d": beside,
        "households_whose_two_oldest_adults_pair_line_7a_with_schedule_d": paired,
        "line_7a_on_those_pairs": paired_line_7a,
    }


def main(argv: list[str]) -> int:
    reference = POPULACE_US_DATASET.removeprefix("populace://")
    repo_id, _, filename = reference.rpartition("/")
    path = _resolve_populace_dataset(POPULACE_US_DATASET)
    with pd.HDFStore(path, mode="r") as store:
        person = store["/person"][list(PERSON_COLUMNS)].copy()
    person = person.assign(
        role=person["tax_unit_role_input"].astype(str),
        row=range(len(person)),
        **{
            column: person[column].astype(float)
            for column in (*COLUMNS, "age", "employment_income")
        },
    )
    person = _fold(person)
    figures = {
        "artifact": {
            "repo_id": repo_id,
            "filename": filename,
            "revision": POPULACE_PINS[(repo_id, filename)].revision,
            "sha256": POPULACE_PINS[(repo_id, filename)].sha256,
            "persons": int(len(person)),
            "tax_units": int(person["person_tax_unit_id"].nunique()),
        },
        "columns": _column_figures(person),
        "legacy_dividend_income": _legacy_dividend_income(person),
        "schedule_d_fold": _schedule_d_fold(person),
        "household_cases": _household_cases(person),
    }
    text = json.dumps(figures, indent=1, sort_keys=True)
    if len(argv) > 1:
        with open(argv[1], "w") as handle:
            handle.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
