# C3 — tariff closure ledger

## 2026-08-16

- Worked on `tariff/certification-arc`; no push.
- Adopted the closure-producer contract and mutant-test pattern from
  axiom-oracles PR #475 (`5402e5bf6`, hardened by `75bb586ae`; branch tip
  supplied as `d236e5320`). Imported only the producer/test surface, not the DK
  ledger or DK executable data, then adapted the producer to the tariff roots.
- Read the full upstream producer, ledger, and mutant suite before authoring the
  tariff decisions. Preserved the generated-facts / committed-decisions /
  computed trust split, immutable Git-object reads, byte-exact `--check`, input
  frontier, and derived `closed` semantics.
- Verified both declared corpus releases exist in
  `axiom-corpus-b1-full`, and pinned RuleSpec census to merge `96d5e7c1`.
- Fresh census: 29,845 schedule provisions; 13,786 distinct provisions contain
  a General-rate field, including five 9802 rated provisions. The task's 13,790
  figure appears to combine those 13,786 generated rows with four hand-authored
  witness modules; it is not a distinct-provision count, so the ledger keeps the
  reproducible 13,786 denominator.
- Fresh notes census: 805 Chapter-99 pages plus eight GN3 pages and two document
  nodes (815 JSONL rows total). Chapter-99 family counts are page-denominator
  classifications; incidence membership cardinalities (301/232/201/122) are
  recorded as evidence and are not incorrectly added to the page denominator.
- Honest result: `closed: false`. Named partial/pending families include 9802,
  the unclassified remainder of Chapter 99, section 338/note 51, non-metal 232,
  original 2018 China-301 instruments, the four encoded-but-uncomposed action
  families, and historical vintages.
- Checks run: producer generate; producer check; five focused mutant tests.
