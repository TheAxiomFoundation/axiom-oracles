from pathlib import Path

from axiom_programs.audit.accessnyc_rules import audit_accessnyc_rules


def write(path: Path, text: str) -> None:
    path.write_text(text)


def test_accessnyc_static_audit(tmp_path: Path) -> None:
    write(
        tmp_path / "S2R038.drl",
        """
rule "s2_r038 3"
when
  (MembersMedicaid(value == 1) and IncomeMedicaidTotalYearly(amount <= 35591))
then
  $programcode.setCode("S2R038")
end

rule "s2_r038 5"
when
  (MembersMedicaid(value == 1) and IncomeMedicaidTotalYearly(amount <= 24579))
then
  $programcode.setCode("S2R038")
end

rule "s2_r038 6"
when
  (MembersMedicaid(value == 1) and IncomeMedicaidTotalYearly(amount <= 22025))
  or (MembersMedicaid(value == 6) and IncomeMedicaidTotalYearly(amount <= 61217))
then
  $programcode.setCode("S2R038")
end
""",
    )
    write(
        tmp_path / "S2R058.drl",
        """
rule "s2_r058"
when
  (Household(members == 1) and IncomeHouseholdTotalYearly(amount > 21597, amount <= 39125))
  or (Household(members == 6) and IncomeHouseholdTotalYearly(amount > 66451, amount <= 107875))
then
  $programcode.setCode("S2R058")
end
""",
    )
    write(
        tmp_path / "S2R057.drl",
        """
rule "s2_r057 age under 1"
when
  (Household(members == 1) and IncomeHouseholdTotalYearly(amount > 33584))
then
  $programcode.setCode("S2R057")
end

rule "s2_r057 age 1-18"
when
  (Household(members == 1) and IncomeHouseholdTotalYearly(amount > 23193))
then
  $programcode.setCode("S2R057")
end
""",
    )
    write(
        tmp_path / "S2R037.drl",
        """
rule "s2_r037 disabled/blind, 65+, medicaid or disability medicaid"
when
  (Person(disabled == true) or Person(age >= 65)) and
  (Person(benefitsMedicaid == true) or Person(benefitsMedicaidDisability == true))
then
  $programcode.setCode("S2R037")
end
""",
    )
    write(
        tmp_path / "S2R029.drl",
        """
rule "S2R029 pregnant, medicaid or disability medicaid"
when
  (Person( pregnant == true ))
  (Person(benefitsMedicaid == true) or Person(benefitsMedicaidDisability == true))
then
  $programcode.setCode("S2R029")
end
""",
    )
    write(
        tmp_path / "S2R060.drl",
        """
rule "s2_r060"
when
  Person(benefitsMedicaid == true)
then
  $programcode.setCode("S2R060")
end
""",
    )

    findings = audit_accessnyc_rules(
        tmp_path,
        dataset_codes={"S2R029", "S2R037", "S2R038", "S2R057", "S2R058"},
    )
    kinds = {finding.kind for finding in findings}

    assert "active_code_missing_from_dataset" in kinds
    assert "medicaid_essential_plan_gap" in kinds
    assert "medicaid_essential_plan_overlap" in kinds
    assert "medicaid_child_health_plus_overlap" in kinds
    assert "home_care_medicaid_same_person" in kinds
    assert "nurse_family_partnership_medicaid_same_person" in kinds

    child_overlap = next(
        finding
        for finding in findings
        if finding.kind == "medicaid_child_health_plus_overlap"
        and finding.details
        and finding.details["age_group"] == "child"
    )
    assert child_overlap.line == 11
