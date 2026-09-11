# Candidate-child pair scope

This synthetic engine IR tests four distinct `CandidateChildPair` entity IDs
in one dataset: two candidate persons, each paired with two children. Both
children's delivery records name person A. Matching the recorded person IDs
holds for both A pairs and fails for both B pairs, in explain and fast modes.
The receipt binds the exact request/response bytes and the pinned engine
commit and local binary hash. Replay with `python3 replay.py <engine-binary>`.

This proves pair-scoped storage and identifier comparisons avoid the scalar
Person/child collision in draft rulespec-de#46. It does not prove legal
motherhood, childbirth occurrence, record-to-child linkage, temporal
persistence, register-change effects, complete candidate enumeration or
RuleSpec companion-test support. Those remain signed-module requirements.
The requests are synthetic runtime IR, not manually authored RuleSpec, and
are not a closure premise or an encoded-source declaration.
