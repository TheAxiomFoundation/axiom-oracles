The itemizer fixture uses the 2024 `MFJ_ITEM_2024` inputs in
[`tests/test_state_zero_salt.py` at 200b9b3e](https://github.com/PolicyEngine/policyengine-taxsim/blob/200b9b3e2c3a087a2750bf0f5ffafc3369883f59/tests/test_state_zero_salt.py),
at state 0 and state 44. Both spouses are 45, there are no dependents,
wages are $300,000, property tax is $3,000, mortgage interest is $30,000,
and `idtl=2`. Omitted financial inputs are zero. The inputs also appear in
the discussion of [PR #1204](https://github.com/PolicyEngine/policyengine-taxsim/pull/1204);
the local checkout's commit 3bffdf3136b2d0b7ce9c7ddb98c9443179abff25
records its reported outputs. `gh pr view` and the web fallback were
unavailable in this sandbox, so the fixture was verified against local git
objects. The probe report records observations rather than asserting that
discussion's values.

The `pension-only-2024.csv` and `pension-only-2025.csv` files are byte-for-byte
copies (including CRLF) of
[`tests/fixtures/maryland_taxsim_crash/` at 3a58992a](https://github.com/PolicyEngine/policyengine-taxsim/tree/3a58992ad6330920a1dc93bc6d83efe5de954d13/tests/fixtures/maryland_taxsim_crash).
The source README describes a batch-dependent September Linux failure;
default bisection can recover both records. The probe also runs with a
zero-rerun budget to retain a failing batch as explicit `engine_error` rows.
No PolicyEngine simulation runs for these crash fixtures.
