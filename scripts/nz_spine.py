#!/usr/bin/env python3
"""Hermetic NZ CERTIFIED.md v3 spine-scope audit helper.

This module deliberately performs no file or network I/O.  Callers may pass the
decoded ``closure/nz/source.json`` mapping to :func:`build_spine_frontier`, or
pass the already-derived union of citations.  The pinned 57-citation legal
subgraph and all three candidate scope ledgers are ratcheted below so a
changed citation cannot silently preserve only the aggregate count.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


class NZSpineError(ValueError):
    """Raised when the pinned NZ spine evidence or a scope constant drifts."""


@dataclass(frozen=True)
class _ScopeCount:
    key: str
    instrument: str
    citation_prefix: str
    total: int
    encoded: int
    pending: int


EXPECTED_PROGRAMS = (
    "nz/acc-earners-levy",
    "nz/accommodation-supplement",
    "nz/income-tax",
    "nz/independent-earner-tax-credit",
    "nz/main-benefits",
    "nz/winter-energy-payment",
    "nz/working-for-families",
)


EXPECTED_CANDIDATE_CITATIONS = (
    "nz/regulation/regulation/public/2018/0202/regulation/17",
    "nz/regulation/regulation/public/2018/0202/regulation/18",
    "nz/regulation/regulation/public/2018/0202/regulation/19",
    "nz/regulation/regulation/public/2025/0018/regulation/4",
    "nz/regulation/regulation/public/2025/0018/regulation/5",
    "nz/regulation/regulation/public/2026/0036/regulation/5",
    "nz/statute/act/public/2007/0097/schedule/1/part/a/clause/1",
    "nz/statute/act/public/2007/0097/section/bb-1",
    "nz/statute/act/public/2007/0097/section/bc-2",
    "nz/statute/act/public/2007/0097/section/bc-3",
    "nz/statute/act/public/2007/0097/section/bc-4",
    "nz/statute/act/public/2007/0097/section/bc-5",
    "nz/statute/act/public/2007/0097/section/bd-1",
    "nz/statute/act/public/2007/0097/section/bd-2",
    "nz/statute/act/public/2007/0097/section/lc-13",
    "nz/statute/act/public/2007/0097/section/ma-4",
    "nz/statute/act/public/2007/0097/section/mb-1",
    "nz/statute/act/public/2007/0097/section/mb-10",
    "nz/statute/act/public/2007/0097/section/mb-11",
    "nz/statute/act/public/2007/0097/section/mb-12",
    "nz/statute/act/public/2007/0097/section/mb-12b",
    "nz/statute/act/public/2007/0097/section/mb-13",
    "nz/statute/act/public/2007/0097/section/mb-2",
    "nz/statute/act/public/2007/0097/section/mb-3",
    "nz/statute/act/public/2007/0097/section/mb-4",
    "nz/statute/act/public/2007/0097/section/mb-7",
    "nz/statute/act/public/2007/0097/section/mb-7b",
    "nz/statute/act/public/2007/0097/section/mb-8",
    "nz/statute/act/public/2007/0097/section/mc-10",
    "nz/statute/act/public/2007/0097/section/mc-3",
    "nz/statute/act/public/2007/0097/section/mc-5",
    "nz/statute/act/public/2007/0097/section/md-10",
    "nz/statute/act/public/2007/0097/section/md-13",
    "nz/statute/act/public/2007/0097/section/md-2",
    "nz/statute/act/public/2007/0097/section/md-3",
    "nz/statute/act/public/2007/0097/section/md-4",
    "nz/statute/act/public/2007/0097/section/md-5",
    "nz/statute/act/public/2007/0097/section/md-6",
    "nz/statute/act/public/2007/0097/section/md-7",
    "nz/statute/act/public/2007/0097/section/md-8",
    "nz/statute/act/public/2007/0097/section/md-9",
    "nz/statute/act/public/2007/0097/section/me-1",
    "nz/statute/act/public/2007/0097/section/me-3",
    "nz/statute/act/public/2007/0097/section/mg-1",
    "nz/statute/act/public/2007/0097/section/mg-2",
    "nz/statute/act/public/2007/0097/section/mg-3",
    "nz/statute/act/public/2018/0032/schedule/2/definition/income-test-1",
    "nz/statute/act/public/2018/0032/schedule/2/definition/income-test-2",
    "nz/statute/act/public/2018/0032/schedule/2/definition/income-test-3",
    "nz/statute/act/public/2018/0032/schedule/2/definition/income-test-4",
    "nz/statute/act/public/2018/0032/schedule/4/part/1/clause/lms118447",
    "nz/statute/act/public/2018/0032/schedule/4/part/2/clause/lms118467",
    "nz/statute/act/public/2018/0032/schedule/4/part/7/clause/lms118453",
    "nz/statute/act/public/2018/0032/schedule/4/part/8/clause/lms118454",
    "nz/statute/act/public/2018/0032/section/65aaa",
    "nz/statute/act/public/2026/0008/section/105",
    "nz/statute/act/public/2026/0008/section/2",
)


DIRECT_SCOPE_COUNTS = (
    _ScopeCount(
        "income_tax_act_2007",
        "Income Tax Act 2007",
        "nz/statute/act/public/2007/0097/",
        40,
        40,
        0,
    ),
    _ScopeCount(
        "social_security_act_2018",
        "Social Security Act 2018",
        "nz/statute/act/public/2018/0032/",
        9,
        9,
        0,
    ),
    _ScopeCount(
        "annual_rates_act_2026",
        "Annual Rates for 2025–26, Taxation (KiwiSaver), and Remedial "
        "Matters Act 2026",
        "nz/statute/act/public/2026/0008/",
        2,
        2,
        0,
    ),
    _ScopeCount(
        "social_security_regulations_2018",
        "Social Security Regulations 2018",
        "nz/regulation/regulation/public/2018/0202/",
        3,
        3,
        0,
    ),
    _ScopeCount(
        "acc_earners_levy_regulations_2025",
        "Accident Compensation (Earners' Levy) Regulations 2025",
        "nz/regulation/regulation/public/2025/0018/",
        2,
        2,
        0,
    ),
    _ScopeCount(
        "social_security_rates_order_2026",
        "Social Security (Rates of Benefits and Allowances) Order 2026",
        "nz/regulation/regulation/public/2026/0036/",
        1,
        1,
        0,
    ),
)


def _section_paths(prefix: str, names: Iterable[str]) -> tuple[str, ...]:
    return tuple(f"{prefix}/section/{name}" for name in names)


EXPECTED_DEPENDENCY_ROOT_CITATIONS = tuple(
    sorted(
        (
            *_section_paths(
                "nz/statute/act/public/2001/0049",
                (
                    "6",
                    "9",
                    "10",
                    "11",
                    "12",
                    "13",
                    "14",
                    "15",
                    "25",
                    "26",
                    "103",
                    "105",
                    "221",
                ),
            ),
            *_section_paths(
                "nz/statute/act/public/2007/0097",
                (
                    "hr-8",
                    "ma-7",
                    "mc-2",
                    "mc-4",
                    "mc-6",
                    "mc-7",
                    "mc-8",
                    "mc-9",
                    "md-1",
                    "md-11",
                    "md-12",
                    "md-12b",
                    "md-16",
                    "me-2",
                    "rd-3b",
                    "rd-3c",
                    "mz-1",
                    "mz-2",
                    "ya-1",
                    "yd-1",
                ),
            ),
            *_section_paths(
                "nz/statute/act/public/2018/0032",
                (
                    "7",
                    "8",
                    "16",
                    "19",
                    "20",
                    "21",
                    "22",
                    "23",
                    "24",
                    "25",
                    "26",
                    "29",
                    "30",
                    "31",
                    "32",
                    "33",
                    "65",
                    "66",
                    "67",
                    "68",
                    "69",
                    "71",
                    "72",
                    "73",
                    "205",
                    "220",
                    "225",
                    "226",
                    "227",
                    "228",
                    "229",
                    "234",
                    "235",
                    "236",
                    "237",
                    "238",
                    "423",
                ),
            ),
            "nz/statute/act/public/2018/0032/schedule/5",
            "nz/statute/act/public/2018/0032/schedule/5/part/1",
            "nz/statute/act/public/2018/0032/schedule/5/part/2",
            "nz/statute/act/public/2018/0032/schedule/5/part/3",
            "nz/statute/act/public/2018/0032/schedule/2/definition/additional-resident",
            "nz/statute/act/public/2018/0032/schedule/2/definition/contributions",
            "nz/statute/act/public/2018/0032/schedule/2/definition/full-time-student",
            "nz/statute/act/public/2018/0032/schedule/2/definition/living-with-a-parent",
            "nz/statute/act/public/2018/0032/schedule/2/definition/social-housing",
            "nz/regulation/regulation/public/2018/0202/regulation/6",
            "nz/regulation/regulation/public/2018/0202/regulation/7",
            "nz/regulation/regulation/public/2018/0202/regulation/7a",
            "nz/regulation/regulation/public/2018/0202/regulation/15",
            "nz/regulation/regulation/public/2025/0018/regulation/8",
            "nz/statute/act/public/2025/0009/section/105",
            "nz/statute/act/public/1992/0076/section/2",
            *(
                f"nz/regulation/regulation/public/1998/0277/regulation/{number}"
                for number in (
                    2,
                    3,
                    4,
                    5,
                    6,
                    7,
                    8,
                    12,
                    "12a",
                    13,
                    14,
                    15,
                    16,
                    20,
                    26,
                    28,
                    29,
                    30,
                    31,
                    34,
                    35,
                    40,
                    44,
                    45,
                    46,
                    "47b",
                    "47c",
                    "47d",
                    "47e",
                    48,
                )
            ),
            "nz/statute/act/public/1994/0166/section/91aas",
        )
    )
)


# The corpus citation scan exposes the full 80K administrative cluster. The
# transitional 80KLB section is easy to lose if the range is transcribed as a
# simple alphabetic sequence, so it is an explicit ratchet entry here.
EXPECTED_ALL_CHANNEL_ADDITIONAL_CITATIONS = tuple(
    sorted(
        (
            "nz/statute/act/public/1985/0141/section/5",
            "nz/statute/act/public/1985/0141/section/8",
            "nz/statute/act/public/1985/0141/section/10",
            *_section_paths(
                "nz/statute/act/public/1994/0166",
                (
                    "80ka",
                    "80kb",
                    "80kc",
                    "80kd",
                    "80ke",
                    "80kf",
                    "80kg",
                    "80kh",
                    "80ki",
                    "80kj",
                    "80kk",
                    "80kl",
                    "80klb",
                    "80kn",
                    "80ko",
                    "80kp",
                    "80kq",
                    "80kr",
                    "80ks",
                    "80kt",
                    "80ku",
                    "80kv",
                    "80kw",
                ),
            ),
        )
    )
)

EXPECTED_OFF_RELEASE_EXACT_CITATIONS = (
    "nz/statute/act/public/2025/0009/section/105",
)


DEPENDENCY_ROOT_SCOPE_COUNTS = (
    _ScopeCount(
        "accident_compensation_act_2001",
        "Accident Compensation Act 2001",
        "nz/statute/act/public/2001/0049/",
        13,
        0,
        13,
    ),
    _ScopeCount(
        "income_tax_act_2007",
        "Income Tax Act 2007",
        "nz/statute/act/public/2007/0097/",
        60,
        40,
        20,
    ),
    _ScopeCount(
        "public_and_community_housing_management_act_1992",
        "Public and Community Housing Management Act 1992",
        "nz/statute/act/public/1992/0076/",
        1,
        0,
        1,
    ),
    _ScopeCount(
        "tax_administration_act_1994",
        "Tax Administration Act 1994",
        "nz/statute/act/public/1994/0166/",
        1,
        0,
        1,
    ),
    _ScopeCount(
        "social_security_act_2018",
        "Social Security Act 2018",
        "nz/statute/act/public/2018/0032/",
        55,
        9,
        46,
    ),
    _ScopeCount(
        "taxation_annual_rates_2024_25_act_2025",
        "Taxation (Annual Rates for 2024–25, Emergency Response, and Remedial "
        "Measures) Act 2025",
        "nz/statute/act/public/2025/0009/",
        1,
        0,
        1,
    ),
    _ScopeCount(
        "annual_rates_act_2026",
        "Annual Rates for 2025–26, Taxation (KiwiSaver), and Remedial "
        "Matters Act 2026",
        "nz/statute/act/public/2026/0008/",
        2,
        2,
        0,
    ),
    _ScopeCount(
        "student_allowances_regulations_1998",
        "Student Allowances Regulations 1998",
        "nz/regulation/regulation/public/1998/0277/",
        30,
        0,
        30,
    ),
    _ScopeCount(
        "social_security_regulations_2018",
        "Social Security Regulations 2018",
        "nz/regulation/regulation/public/2018/0202/",
        7,
        3,
        4,
    ),
    _ScopeCount(
        "acc_earners_levy_regulations_2025",
        "Accident Compensation (Earners' Levy) Regulations 2025",
        "nz/regulation/regulation/public/2025/0018/",
        3,
        2,
        1,
    ),
    _ScopeCount(
        "social_security_rates_order_2026",
        "Social Security (Rates of Benefits and Allowances) Order 2026",
        "nz/regulation/regulation/public/2026/0036/",
        1,
        1,
        0,
    ),
)


ALL_CHANNEL_SCOPE_COUNTS = (
    *DEPENDENCY_ROOT_SCOPE_COUNTS[:1],
    _ScopeCount(
        "goods_and_services_tax_act_1985",
        "Goods and Services Tax Act 1985",
        "nz/statute/act/public/1985/0141/",
        3,
        0,
        3,
    ),
    *DEPENDENCY_ROOT_SCOPE_COUNTS[1:3],
    _ScopeCount(
        "tax_administration_act_1994",
        "Tax Administration Act 1994",
        "nz/statute/act/public/1994/0166/",
        24,
        0,
        24,
    ),
    *DEPENDENCY_ROOT_SCOPE_COUNTS[4:],
)


F1_SEVEN_BODY_SCOPE_COUNTS = (
    _ScopeCount(
        "accident_compensation_act_2001",
        "Accident Compensation Act 2001",
        "nz/statute/act/public/2001/0049/",
        535,
        0,
        535,
    ),
    _ScopeCount(
        "income_tax_act_2007",
        "Income Tax Act 2007",
        "nz/statute/act/public/2007/0097/",
        3099,
        40,
        3059,
    ),
    _ScopeCount(
        "social_security_act_2018",
        "Social Security Act 2018",
        "nz/statute/act/public/2018/0032/",
        1001,
        9,
        992,
    ),
    _ScopeCount(
        "annual_rates_act_2026",
        "Annual Rates for 2025–26, Taxation (KiwiSaver), and Remedial "
        "Matters Act 2026",
        "nz/statute/act/public/2026/0008/",
        255,
        2,
        253,
    ),
    _ScopeCount(
        "social_security_regulations_2018",
        "Social Security Regulations 2018",
        "nz/regulation/regulation/public/2018/0202/",
        427,
        3,
        424,
    ),
    _ScopeCount(
        "acc_earners_levy_regulations_2025",
        "Accident Compensation (Earners' Levy) Regulations 2025",
        "nz/regulation/regulation/public/2025/0018/",
        10,
        2,
        8,
    ),
    _ScopeCount(
        "social_security_rates_order_2026",
        "Social Security (Rates of Benefits and Allowances) Order 2026",
        "nz/regulation/regulation/public/2026/0036/",
        13,
        1,
        12,
    ),
)


WHOLE_GOVERNING_ACT_SCOPE_COUNTS = (
    F1_SEVEN_BODY_SCOPE_COUNTS[0],
    _ScopeCount(
        "goods_and_services_tax_act_1985",
        "Goods and Services Tax Act 1985",
        "nz/statute/act/public/1985/0141/",
        3,
        0,
        3,
    ),
    F1_SEVEN_BODY_SCOPE_COUNTS[1],
    _ScopeCount(
        "public_and_community_housing_management_act_1992",
        "Public and Community Housing Management Act 1992",
        "nz/statute/act/public/1992/0076/",
        1,
        0,
        1,
    ),
    _ScopeCount(
        "tax_administration_act_1994",
        "Tax Administration Act 1994",
        "nz/statute/act/public/1994/0166/",
        24,
        0,
        24,
    ),
    F1_SEVEN_BODY_SCOPE_COUNTS[2],
    _ScopeCount(
        "taxation_annual_rates_2024_25_act_2025",
        "Taxation (Annual Rates for 2024–25, Emergency Response, and Remedial "
        "Measures) Act 2025",
        "nz/statute/act/public/2025/0009/",
        1,
        0,
        1,
    ),
    _ScopeCount(
        "annual_rates_act_2026",
        "Annual Rates for 2025–26, Taxation (KiwiSaver), and Remedial "
        "Matters Act 2026",
        "nz/statute/act/public/2026/0008/",
        2,
        2,
        0,
    ),
    _ScopeCount(
        "student_allowances_regulations_1998",
        "Student Allowances Regulations 1998",
        "nz/regulation/regulation/public/1998/0277/",
        30,
        0,
        30,
    ),
    _ScopeCount(
        "social_security_regulations_2018",
        "Social Security Regulations 2018",
        "nz/regulation/regulation/public/2018/0202/",
        7,
        3,
        4,
    ),
    _ScopeCount(
        "acc_earners_levy_regulations_2025",
        "Accident Compensation (Earners' Levy) Regulations 2025",
        "nz/regulation/regulation/public/2025/0018/",
        3,
        2,
        1,
    ),
    _ScopeCount(
        "social_security_rates_order_2026",
        "Social Security (Rates of Benefits and Allowances) Order 2026",
        "nz/regulation/regulation/public/2026/0036/",
        1,
        1,
        0,
    ),
)


def _validate_scope_counts(
    rows: tuple[_ScopeCount, ...],
    *,
    expected_total: int,
    expected_encoded: int,
    expected_pending: int,
) -> None:
    keys = [row.key for row in rows]
    prefixes = [row.citation_prefix for row in rows]
    if len(keys) != len(set(keys)) or len(prefixes) != len(set(prefixes)):
        raise NZSpineError("NZ spine scope constants contain a duplicate")
    if any(
        min(row.total, row.encoded, row.pending) < 0
        or row.encoded + row.pending != row.total
        for row in rows
    ):
        raise NZSpineError("NZ spine scope constants have an invalid disposition")
    if (
        sum(row.total for row in rows),
        sum(row.encoded for row in rows),
        sum(row.pending for row in rows),
    ) != (expected_total, expected_encoded, expected_pending):
        raise NZSpineError("NZ spine scope aggregate constants drifted")


def _validate_citation_ownership(
    citations: tuple[str, ...], rows: tuple[_ScopeCount, ...]
) -> None:
    actual: dict[str, int] = {}
    for row in rows:
        actual[row.key] = sum(
            citation.startswith(row.citation_prefix) for citation in citations
        )
    for citation in citations:
        matches = [row for row in rows if citation.startswith(row.citation_prefix)]
        if len(matches) != 1:
            raise NZSpineError(
                f"candidate citation has {len(matches)} instrument owners: {citation}"
            )
    expected = {row.key: row.total for row in rows}
    if actual != expected:
        raise NZSpineError(
            f"NZ candidate per-instrument citation constants drifted: {actual!r}"
        )


def _validate_constants() -> None:
    citation_sets = (
        ("direct", EXPECTED_CANDIDATE_CITATIONS, 57),
        ("dependency-root", EXPECTED_DEPENDENCY_ROOT_CITATIONS, 117),
        ("all-channel-additional", EXPECTED_ALL_CHANNEL_ADDITIONAL_CITATIONS, 26),
    )
    for label, citations, expected_count in citation_sets:
        if citations != tuple(sorted(set(citations))):
            raise NZSpineError(f"NZ {label} citations must be unique and sorted")
        if len(citations) != expected_count:
            raise NZSpineError(
                f"NZ {label} citation denominator drifted from {expected_count}"
            )
    if set(EXPECTED_CANDIDATE_CITATIONS) & set(EXPECTED_DEPENDENCY_ROOT_CITATIONS):
        raise NZSpineError("NZ direct and dependency-root citations overlap")
    if set(EXPECTED_ALL_CHANNEL_ADDITIONAL_CITATIONS) & (
        set(EXPECTED_CANDIDATE_CITATIONS)
        | set(EXPECTED_DEPENDENCY_ROOT_CITATIONS)
    ):
        raise NZSpineError("NZ all-channel additions are not set additions")
    audited_off_release = tuple(
        citation
        for citation in EXPECTED_DEPENDENCY_ROOT_CITATIONS
        if citation.startswith("nz/statute/act/public/2025/0009/")
    )
    if audited_off_release != EXPECTED_OFF_RELEASE_EXACT_CITATIONS:
        raise NZSpineError("NZ off-release exact-root exception drifted")

    scope_expectations = (
        (DIRECT_SCOPE_COUNTS, 57, 57, 0),
        (DEPENDENCY_ROOT_SCOPE_COUNTS, 174, 57, 117),
        (ALL_CHANNEL_SCOPE_COUNTS, 200, 57, 143),
        (F1_SEVEN_BODY_SCOPE_COUNTS, 5340, 57, 5283),
        (WHOLE_GOVERNING_ACT_SCOPE_COUNTS, 4707, 57, 4650),
    )
    for rows, total, encoded, pending in scope_expectations:
        _validate_scope_counts(
            rows,
            expected_total=total,
            expected_encoded=encoded,
            expected_pending=pending,
        )

    dependency_union = tuple(
        sorted(
            set(EXPECTED_CANDIDATE_CITATIONS)
            | set(EXPECTED_DEPENDENCY_ROOT_CITATIONS)
        )
    )
    all_channel_union = tuple(
        sorted(
            set(dependency_union) | set(EXPECTED_ALL_CHANNEL_ADDITIONAL_CITATIONS)
        )
    )
    _validate_citation_ownership(EXPECTED_CANDIDATE_CITATIONS, DIRECT_SCOPE_COUNTS)
    _validate_citation_ownership(dependency_union, DEPENDENCY_ROOT_SCOPE_COUNTS)
    _validate_citation_ownership(all_channel_union, ALL_CHANNEL_SCOPE_COUNTS)


def _source_candidate_citations(source: Mapping[str, Any]) -> tuple[str, ...]:
    """Derive the legal-subgraph citation union from a decoded source mapping."""

    program_roots = source.get("program_roots")
    rulespec = source.get("rulespec")
    if not isinstance(program_roots, Mapping) or not isinstance(rulespec, Mapping):
        raise NZSpineError("NZ source mapping lacks program_roots or rulespec")
    if tuple(sorted(program_roots)) != EXPECTED_PROGRAMS:
        raise NZSpineError("NZ source program set drifted")
    files = rulespec.get("files")
    if not isinstance(files, list):
        raise NZSpineError("NZ source rulespec.files must be a list")

    nodes_by_id: dict[str, Mapping[str, Any]] = {}
    nodes_by_name: dict[str, Mapping[str, Any]] = {}
    for file_row in files:
        if not isinstance(file_row, Mapping):
            raise NZSpineError("NZ source contains a non-mapping RuleSpec file row")
        nodes = file_row.get("nodes")
        if not isinstance(nodes, list):
            raise NZSpineError("NZ source RuleSpec file row lacks nodes")
        for node in nodes:
            if not isinstance(node, Mapping):
                raise NZSpineError("NZ source contains a non-mapping node")
            node_id = node.get("id")
            name = node.get("name")
            citations = node.get("citations")
            dependencies = node.get("dependencies")
            if (
                not isinstance(node_id, str)
                or not isinstance(name, str)
                or not isinstance(citations, list)
                or not isinstance(dependencies, list)
                or not all(isinstance(value, str) for value in citations)
                or not all(isinstance(value, str) for value in dependencies)
            ):
                raise NZSpineError("NZ source node has an invalid shape")
            if node_id in nodes_by_id or name in nodes_by_name:
                raise NZSpineError(f"duplicate NZ source node {node_id!r}")
            nodes_by_id[node_id] = node
            nodes_by_name[name] = node

    citations: set[str] = set()
    for program in EXPECTED_PROGRAMS:
        roots = program_roots[program]
        if not isinstance(roots, list) or not all(
            isinstance(root, str) for root in roots
        ):
            raise NZSpineError(f"{program}: invalid root-node list")
        reached: set[str] = set()
        stack = list(roots)
        while stack:
            node_id = stack.pop()
            if node_id in reached:
                continue
            node = nodes_by_id.get(node_id)
            if node is None:
                raise NZSpineError(f"{program}: unknown subgraph node {node_id!r}")
            reached.add(node_id)
            citations.update(node["citations"])
            for dependency in node["dependencies"]:
                dependency_node = nodes_by_name.get(dependency)
                if dependency_node is None:
                    raise NZSpineError(
                        f"{program}: unknown dependency node {dependency!r}"
                    )
                stack.append(str(dependency_node["id"]))
    return tuple(sorted(citations))


def _coerce_candidate_citations(
    candidate_citations: Mapping[str, Any] | Iterable[str],
) -> tuple[str, ...]:
    if isinstance(candidate_citations, Mapping):
        citations = _source_candidate_citations(candidate_citations)
    else:
        if isinstance(candidate_citations, (str, bytes)):
            raise NZSpineError("candidate citations must not be a scalar string")
        citations = tuple(candidate_citations)
        if not all(isinstance(citation, str) for citation in citations):
            raise NZSpineError("candidate citations must all be strings")
        citations = tuple(sorted(set(citations)))
    missing = sorted(set(EXPECTED_CANDIDATE_CITATIONS) - set(citations))
    if missing:
        raise NZSpineError(
            "NZ requested legal-subgraph citation union drifted from the pinned "
            f"57-path ratchet (missing={missing!r})"
        )
    return citations


def _coerce_exact_ratchet(
    values: Iterable[str], *, expected: tuple[str, ...], label: str
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise NZSpineError(f"{label} citations must not be a scalar string")
    citations = tuple(values)
    if not all(isinstance(citation, str) for citation in citations):
        raise NZSpineError(f"{label} citations must all be strings")
    citations = tuple(sorted(set(citations)))
    missing = sorted(set(expected) - set(citations))
    unexpected = sorted(set(citations) - set(expected))
    if missing or unexpected:
        raise NZSpineError(
            f"NZ {label} citation union drifted from the pinned "
            f"{len(expected)}-path ratchet (missing={missing!r}, "
            f"unexpected={unexpected!r})"
        )
    return citations


def _scope_row(row: _ScopeCount) -> dict[str, Any]:
    return {
        "key": row.key,
        "instrument": row.instrument,
        "citation_prefix": row.citation_prefix,
        "total": row.total,
        "by_status": {
            "encoded": row.encoded,
            "classified": 0,
            "excluded": 0,
            "pending": row.pending,
        },
    }


def _scope_rows_with_extras(
    scope_counts: tuple[_ScopeCount, ...], extra_citations: tuple[str, ...]
) -> list[dict[str, Any]]:
    rows = [_scope_row(row) for row in scope_counts]
    unmapped: list[str] = []
    for citation in extra_citations:
        matches = [
            row
            for row in rows
            if citation.startswith(str(row["citation_prefix"]))
        ]
        if len(matches) == 1:
            matches[0]["total"] += 1
            matches[0]["by_status"]["pending"] += 1
        else:
            unmapped.append(citation)
    if unmapped:
        rows.append(
            {
                "key": "new_unmapped_legal_roots",
                "instrument": "New legal root(s) requiring scope ownership",
                "citation_prefix": None,
                "total": len(unmapped),
                "by_status": {
                    "encoded": 0,
                    "classified": 0,
                    "excluded": 0,
                    "pending": len(unmapped),
                },
                "citation_paths": unmapped,
            }
        )
    return rows


def build_spine_frontier(
    candidate_citations: Mapping[str, Any] | Iterable[str],
    *,
    dependency_root_citations: Iterable[
        str
    ] = EXPECTED_DEPENDENCY_ROOT_CITATIONS,
    all_channel_additional_citations: Iterable[
        str
    ] = EXPECTED_ALL_CHANNEL_ADDITIONAL_CITATIONS,
) -> dict[str, Any]:
    """Return the honest NZ v3 spine-scope positions.

    ``candidate_citations`` may be the decoded NZ closure source document or an
    iterable containing its already-computed transitive program-root citation
    union. Either form is checked against the exact pinned 57-path ratchet. The
    dependency and discovery-channel supplements have separate exact ratchets
    so dropping a legal root cannot be hidden by preserving an aggregate count.
    """

    citations = _coerce_candidate_citations(candidate_citations)
    dependency_citations = _coerce_exact_ratchet(
        dependency_root_citations,
        expected=EXPECTED_DEPENDENCY_ROOT_CITATIONS,
        label="dependency-root",
    )
    all_channel_citations = _coerce_exact_ratchet(
        all_channel_additional_citations,
        expected=EXPECTED_ALL_CHANNEL_ADDITIONAL_CITATIONS,
        label="all-channel-additional",
    )
    direct_extras = tuple(
        citation
        for citation in citations
        if citation not in EXPECTED_CANDIDATE_CITATIONS
    )
    direct_paths = tuple(sorted(set(citations)))
    dependency_paths = tuple(
        sorted(set(direct_paths) | set(dependency_citations))
    )
    all_channel_paths = tuple(
        sorted(set(dependency_paths) | set(all_channel_citations))
    )
    return {
        "schema": "axiom_oracles.nz_spine_frontier.v2",
        "complete": False,
        "scope_adjudication_pending": True,
        "body_hash_ledger_complete": False,
        "precedent": {
            "source": (
                "oracles merge e77c93099 (DE PR #485): closure/de/source.json "
                "programs.de/kindergeld root_nodes and evidence_roots "
                "resolution=self_and_descendants; certificates/de-kindergeld.json "
                "subgraph.scope=amount; docs/de-kindergeld-certification.md"
            ),
            "rule": (
                "DE scoped spine closure to the attested amount/legal subgraph "
                "rather than silently treating every provision in each cited Act "
                "as part of the encoded surface."
            ),
            "nz_candidate_application": (
                "Apply the same dependency-root scoping rule to the transitive "
                "program-root union, then add the concrete roots quantified by "
                "strict leaf typing and the pinned-corpus citation scan. Subject-"
                "search, other off-release, and open-ended roots remain unquantified "
                "work and make the resulting count only a lower bound."
            ),
        },
        "certified_v3_ambiguity": {
            "literal_reading": (
                "CERTIFIED.md v3 can also be read to require disposition of the "
                "whole body of every declared legal spine instrument."
            ),
            "unresolved_question": (
                "Whether the 3,099-provision Income Tax Act 2007 and the other "
                "two governing Acts are whole-Act roots or only hosts for the "
                "dependency-root legal subgraph requires explicit adjudication."
            ),
            "effect": (
                "Neither scope is certified closed until that choice is recorded "
                "and a complete provision/body-hash ledger binds the chosen scope."
            ),
        },
        "direct_encoded_subgraph_scope": {
            "label": "direct encoded program-root subgraph (insufficient alone)",
            "total": 57 + len(direct_extras),
            "by_status": {
                "encoded": 57,
                "classified": 0,
                "excluded": 0,
                "pending": len(direct_extras),
            },
            "instrument_counts": _scope_rows_with_extras(
                DIRECT_SCOPE_COUNTS, direct_extras
            ),
            "citation_paths": list(direct_paths),
            "complete_for_v3": False,
            "incomplete_reason": (
                "This was F1's source-citation union. It omits defining provisions "
                "for law-derived leaves and search-discovered bearing rules."
            ),
        },
        "requested_legal_subgraph_scope": {
            "label": "DE-style dependency-root legal subgraph lower bound",
            "total": 174 + len(direct_extras),
            "by_status": {
                "encoded": 57,
                "classified": 0,
                "excluded": 0,
                "pending": 117 + len(direct_extras),
            },
            "instrument_counts": _scope_rows_with_extras(
                DEPENDENCY_ROOT_SCOPE_COUNTS, direct_extras
            ),
            "citation_paths": list(dependency_paths),
            "pinned_corpus_path_count": 173 + len(direct_extras),
            "official_web_only_exact_path_count": 1,
            "official_web_only_exact_paths": list(
                EXPECTED_OFF_RELEASE_EXACT_CITATIONS
            ),
            "lower_bound": True,
            "provisional": True,
            "provisional_reason": (
                "The 117 pending roots conservatively expand every concrete "
                "provision named by the strict dependency audit. Imported "
                "definitions, open-ended ranges, implementing regulations, and "
                "determinations still require provision-level expansion."
            ),
        },
        "all_channel_legal_subgraph_scope": {
            "label": "all-channel legal-subgraph lower bound",
            "total": 200 + len(direct_extras),
            "by_status": {
                "encoded": 57,
                "classified": 0,
                "excluded": 0,
                "pending": 143 + len(direct_extras),
            },
            "instrument_counts": _scope_rows_with_extras(
                ALL_CHANNEL_SCOPE_COUNTS, direct_extras
            ),
            "citation_paths": list(all_channel_paths),
            "pinned_corpus_path_count": 199 + len(direct_extras),
            "official_web_only_exact_path_count": 1,
            "official_web_only_exact_paths": list(
                EXPECTED_OFF_RELEASE_EXACT_CITATIONS
            ),
            "lower_bound": True,
            "set_union_note": (
                "TAA s 91AAS appears in both dependency and citation-scan evidence "
                "and is counted once. The scan adds 23 distinct ss 80K* roots "
                "(including s 80KLB), and GST ss 5, 8, and 10 add three more."
            ),
            "unquantified_roots": (
                "Subject-search provisions, other off-corpus guidance and cases, "
                "open-ended provision ranges, imported definitions, implementing "
                "regulations, and emergency determinations are retained in the "
                "instrument/dependency worklists but are not assigned a false "
                "provision denominator here."
            ),
        },
        "whole_body_scope": {
            "label": (
                "whole governing-Act alternative plus exact other legal roots"
            ),
            "total": 4707,
            "by_status": {
                "encoded": 57,
                "classified": 0,
                "excluded": 0,
                "pending": 4650,
            },
            "instrument_counts": [
                _scope_row(row) for row in WHOLE_GOVERNING_ACT_SCOPE_COUNTS
            ],
            "lower_bound": True,
            "pinned_corpus_row_count": 4706,
            "official_web_only_exact_path_count": 1,
            "governing_acts_only": {
                "total": 4635,
                "encoded": 49,
                "pending": 4586,
            },
            "f1_seven_whole_bodies_not_selected": {
                "total": 5340,
                "encoded": 57,
                "pending": 5283,
                "reason": (
                    "That denominator promotes four subordinate/evidence "
                    "instruments to whole governing spines. DK keeps such "
                    "instruments in the instrument/dependency frontier, so this "
                    "alternative instead retains only their 8 encoded and 64 "
                    "pending exact legal roots."
                ),
            },
            "minimum_reason": (
                "The three governing Acts are counted whole (4,635 rows), while "
                "the 72 quantified legal roots in other instruments remain exact-path "
                "rows. Vague ranges and imported definitions can only increase "
                "this denominator."
            ),
        },
        "blockers": [
            "spine_scope_adjudication_pending",
            "spine_body_hash_ledger_incomplete",
        ],
    }


_validate_constants()
