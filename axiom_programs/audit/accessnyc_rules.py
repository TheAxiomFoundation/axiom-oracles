from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class AuditFinding:
    severity: str
    kind: str
    message: str
    file: str | None = None
    line: int | None = None
    details: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def audit_accessnyc_rules(
    rules_dir: str | Path,
    dataset_codes: set[str] | None = None,
) -> list[AuditFinding]:
    rules_path = Path(rules_dir)
    findings: list[AuditFinding] = []

    active_codes = extract_active_rule_codes(rules_path)
    if dataset_codes is not None:
        findings.extend(_audit_dataset_code_drift(active_codes, dataset_codes))

    findings.extend(_audit_health_threshold_boundaries(rules_path))
    findings.extend(_audit_same_person_risks(rules_path))
    return findings


def extract_active_rule_codes(rules_dir: Path) -> dict[str, tuple[Path, int]]:
    codes: dict[str, tuple[Path, int]] = {}
    for path in sorted(rules_dir.glob("S2R*.drl")):
        for line_number, line in enumerate(path.read_text().splitlines(), start=1):
            if line.strip().startswith("//"):
                continue
            match = re.search(r'\.setCode\("(S2R\d{3})"\)', line)
            if match:
                codes[match.group(1)] = (path, line_number)
    return codes


def _audit_dataset_code_drift(
    active_codes: dict[str, tuple[Path, int]],
    dataset_codes: set[str],
) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    for code in sorted(set(active_codes) - dataset_codes):
        path, line = active_codes[code]
        findings.append(
            AuditFinding(
                severity="warning",
                kind="active_code_missing_from_dataset",
                message=(
                    f"{code} is returned by a rule but is absent from the public "
                    "NYC benefits dataset."
                ),
                file=str(path),
                line=line,
                details={"code": code},
            )
        )

    for code in sorted(dataset_codes - set(active_codes)):
        findings.append(
            AuditFinding(
                severity="info",
                kind="dataset_code_without_active_rule",
                message=(
                    f"{code} appears in the public NYC benefits dataset but has "
                    "no active setCode return in the Drools rules."
                ),
                details={"code": code},
            )
        )
    return findings


def _audit_health_threshold_boundaries(rules_dir: Path) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    medicaid_path = rules_dir / "S2R038.drl"
    essential_path = rules_dir / "S2R058.drl"
    chp_path = rules_dir / "S2R057.drl"

    if medicaid_path.exists() and essential_path.exists():
        adult_medicaid = _extract_member_thresholds(
            _rule_block(medicaid_path, "s2_r038 6"),
            r"MembersMedicaid\(value == (?P<size>\d+)\).*?amount <= (?P<limit>\d+(?:\.\d+)?)",
        )
        essential_lower = _extract_member_thresholds(
            essential_path.read_text(),
            r"Household\(members == (?P<size>\d+)\).*?amount > (?P<limit>\d+(?:\.\d+)?)",
        )
        for size in sorted(set(adult_medicaid) & set(essential_lower)):
            medicaid_limit = adult_medicaid[size]
            essential_start = essential_lower[size]
            if essential_start > medicaid_limit:
                findings.append(
                    AuditFinding(
                        severity="error",
                        kind="medicaid_essential_plan_gap",
                        message=(
                            "Adult Medicaid ends below the Essential Plan lower "
                            f"bound for household size {size}."
                        ),
                        file=str(essential_path),
                        line=_first_line_containing(
                            essential_path, f"Household(members == {size})"
                        ),
                        details={
                            "household_size": size,
                            "medicaid_limit": medicaid_limit,
                            "essential_plan_lower_bound": essential_start,
                            "gap": [medicaid_limit, essential_start],
                        },
                    )
                )
            elif essential_start < medicaid_limit:
                findings.append(
                    AuditFinding(
                        severity="warning",
                        kind="medicaid_essential_plan_overlap",
                        message=(
                            "Adult Medicaid and Essential Plan thresholds overlap "
                            f"for household size {size}."
                        ),
                        file=str(essential_path),
                        line=_first_line_containing(
                            essential_path, f"Household(members == {size})"
                        ),
                        details={
                            "household_size": size,
                            "medicaid_limit": medicaid_limit,
                            "essential_plan_lower_bound": essential_start,
                            "overlap": [essential_start, medicaid_limit],
                        },
                    )
                )

    if medicaid_path.exists() and chp_path.exists():
        infant_medicaid = _extract_member_thresholds(
            _rule_block(medicaid_path, "s2_r038 3"),
            r"MembersMedicaid\(value == (?P<size>\d+)\).*?amount <= (?P<limit>\d+(?:\.\d+)?)",
        )
        child_medicaid = _extract_member_thresholds(
            _rule_block(medicaid_path, "s2_r038 5"),
            r"MembersMedicaid\(value == (?P<size>\d+)\).*?amount <= (?P<limit>\d+(?:\.\d+)?)",
        )
        infant_chp = _extract_member_thresholds(
            _rule_block(chp_path, "s2_r057 age under 1"),
            r"Household\(members == (?P<size>\d+)\).*?amount > (?P<limit>\d+(?:\.\d+)?)",
        )
        child_chp = _extract_member_thresholds(
            _rule_block(chp_path, "s2_r057 age 1-18"),
            r"Household\(members == (?P<size>\d+)\).*?amount > (?P<limit>\d+(?:\.\d+)?)",
        )
        findings.extend(
            _chp_overlap_findings(
                "infant",
                infant_medicaid,
                infant_chp,
                chp_path,
                "s2_r057 age under 1",
            )
        )
        findings.extend(
            _chp_overlap_findings(
                "child",
                child_medicaid,
                child_chp,
                chp_path,
                "s2_r057 age 1-18",
            )
        )

    return findings


def _chp_overlap_findings(
    age_group: str,
    medicaid_thresholds: dict[int, float],
    chp_lower_bounds: dict[int, float],
    chp_path: Path,
    rule_name: str,
) -> list[AuditFinding]:
    findings = []
    for size in sorted(set(medicaid_thresholds) & set(chp_lower_bounds)):
        medicaid_limit = medicaid_thresholds[size]
        chp_start = chp_lower_bounds[size]
        if chp_start < medicaid_limit:
            findings.append(
                AuditFinding(
                    severity="warning",
                    kind="medicaid_child_health_plus_overlap",
                    message=(
                        f"Medicaid and Child Health Plus {age_group} thresholds "
                        f"overlap for household size {size}."
                    ),
                    file=str(chp_path),
                    line=_first_line_containing_rule_block(
                        chp_path, rule_name, f"Household(members == {size})"
                    ),
                    details={
                        "age_group": age_group,
                        "household_size": size,
                        "medicaid_limit": medicaid_limit,
                        "child_health_plus_lower_bound": chp_start,
                        "overlap": [chp_start, medicaid_limit],
                        "rule": rule_name,
                    },
                )
            )
    return findings


def _audit_same_person_risks(rules_dir: Path) -> list[AuditFinding]:
    checks = [
        (
            "S2R037.drl",
            "home_care_medicaid_same_person",
            "Home Care Services Program checks age/disability/blindness and Medicaid in separate Person patterns, so different household members can satisfy each side.",
            "benefitsMedicaid",
        ),
        (
            "S2R029.drl",
            "nurse_family_partnership_medicaid_same_person",
            "Nurse-Family Partnership checks pregnancy and Medicaid in separate Person patterns, so different household members can satisfy each side.",
            "Person( pregnant",
        ),
    ]
    findings = []
    for filename, kind, message, needle in checks:
        path = rules_dir / filename
        if not path.exists():
            continue
        text = path.read_text()
        if (
            len(re.findall(r"Person\(", _rule_block(path, _first_rule_name(path)))) >= 2
            and needle in text
        ):
            findings.append(
                AuditFinding(
                    severity="warning",
                    kind=kind,
                    message=message,
                    file=str(path),
                    line=_first_line_containing(path, needle),
                )
            )
    return findings


def _rule_block(path: Path, rule_name: str) -> str:
    text = path.read_text()
    pattern = rf'rule "{re.escape(rule_name)}".*?\nend'
    match = re.search(pattern, text, flags=re.DOTALL)
    return match.group(0) if match else ""


def _first_rule_name(path: Path) -> str:
    match = re.search(r'rule "([^"]+)"', path.read_text())
    return match.group(1) if match else ""


def _extract_member_thresholds(block: str, pattern: str) -> dict[int, float]:
    thresholds = {}
    for match in re.finditer(pattern, block):
        thresholds[int(match.group("size"))] = float(match.group("limit"))
    return thresholds


def _first_line_containing(path: Path, needle: str) -> int | None:
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if needle in line:
            return line_number
    return None


def _first_line_containing_rule_block(
    path: Path,
    rule_name: str,
    needle: str,
) -> int | None:
    in_rule = False
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if line.strip() == f'rule "{rule_name}"':
            in_rule = True
        elif in_rule and line.strip() == "end":
            return None
        if in_rule and needle in line:
            return line_number
    return None
