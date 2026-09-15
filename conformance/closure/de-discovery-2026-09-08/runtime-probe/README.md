# Same-child payment comparison capability

This is a synthetic engine-IR experiment, not a RuleSpec module, source proof,
encoded dependency, or certification receipt. It is not an input to the closure
producer. No production encoding files or signatures are produced.

The binary was built with `cargo build --locked --bin axiom-rules-engine` from
clean engine commit `05eac9d2f89dabe5c6673176260762cef3a58f47` in an isolated
checkout. `receipt.json` binds that binary, relevant source files, requests
and responses. The comparison literals are synthetic observed payments, not
statutory amounts.

For each child/month, the request constructs ordered candidate/other-person
pairs from its complete payment-record roster, excluding self-pairs. Each
pair carries the two recorded amounts. `other_payment_is_higher` and
`other_payment_is_equal` are derived comparisons. A candidate-linked relation
counts those derived judgments. The unrelated child's 9,999-unit payment has
no effect on the other children. Unequal payments, equal payments and two
zero payments are distinguished in both explain and fast modes. Removing one
required payment input fails execution instead of treating it as zero.

This corresponds to the pinned formula vocabulary
`count_where(comparison_of_candidate, other_payment_is_higher)` and the equal
comparison, with relation slots `[comparison_id, candidate_id]`. The formula
lowerer accepts derived predicates; it does not require a caller-supplied
legal-result Boolean. Source: `src/formula.rs`, `infer_slots` and the
`count_where` match arm; execution: `src/engine.rs`, `CountRelated`.

The evidence refutes a blanket claim that same-child comparisons require a
maximum-and-identity selector. It does not prove a complete §64 design. Legal
entitlement, family relationships, household admission, waiver and court
selection, §78 transition, and the legal characterization of maintenance
payments remain unencoded. The mechanically complete pair relation must not
be replaced by a caller-supplied list of legally higher-priority people.
Missing relation rows or missing eligibility judgments are not covered by this
probe; no conclusion about complete claimant discovery follows from zero
higher-payment comparisons. A zero count is not itself recipient entitlement.

To replay after building the pinned engine:

```sh
python3 replay.py /absolute/path/to/axiom-rules-engine
```

The replayer validates retained request/response hashes, executes all 28
numeric assertions and the missing-input case, and reports the actual binary
hash. It does not assert that an arbitrary supplied binary has the pinned
source provenance; compare its hash or rebuild that source explicitly.
