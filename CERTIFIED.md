# What certified means

This is the canonical definition of the registry's `certified` claim. Every
certificate links here; a certificate making a claim this document does not
license is a certificate defect. Changes to this document are definition
changes: they land through their own reviewed PR, never as a side effect,
and every strengthening re-derives every certificate (a program that
certified under a weaker definition loses the flag until it meets the
current one — the flag falls by derivation, never by hand-editing).

## The predicate

```
certified = computed(conformant AND exercised AND closed AND executable)
            with zero open defects
```

A premise counts only when its mode is `computed` — derived by a producer
from committed artifacts, reproducible by `--check` — AND its value is
true. Attested premises (sha-pinned external receipts, ops attestations)
are scaffolding and never satisfy the predicate. Nobody sets any flag by
hand: `certified` and each premise are pure derivations, and hand-editing
any computed block fails validation as internally inconsistent. The human
layer is the committed decisions the producers consume — exclusion reasons,
dispositions, leaf classifications — each typed, versioned, and
adversarially audited.

## The four premises

- **conformant** — independent reference implementations (EUROMOD, GETTSIM,
  PolicyEngine, TAXSIM, administrative data where available) compute the
  same program from their own reading of the law; every mismatch is
  dispositioned with a text-grounded explanation, none unexplained.
- **exercised** — the comparison evidence actually executed: bound case
  corpora, validated bridge manifests with the strict opt-in, a census that
  binds every manifest sha so no evidence edit is invisible.
- **closed** — source completeness (the substance of this document; below).
- **executable** — a pinned engine binary recompiles the composed programs
  at the recorded commit and reproduces every committed case value exactly;
  the receipt binds the producer commits together.

## What closed requires (the completeness claim)

Closed asserts that the program's **entire legal dependency graph** is
accounted for — "we have to encode everything that is potentially upstream
of the policy, every single dependency, whether it's a reg or not" (Max,
2026-08-20). Concretely, all of:

1. **Spine closure.** Every provision of the governing act (derived from
   the pinned corpus release, body-hashed per row) is encoded, classified,
   or excluded with a text-grounded reason. Zero pending.
2. **Instrument closure.** Every subordinate or bearing instrument the
   official registry links to the act — regulations, circulars, guidance,
   appeals precedents, amendment acts, plus search-discovered supplements —
   is dispositioned from a sha-bound snapshot of the registry's own graph.
   The link graph is one discovery channel and is demonstrably incomplete
   (the 2026-08-20 launch audit found current bearing precedents and a
   cross-act regulation outside it); subject-matter search and, as it
   lands, the corpus citation scan (axiom-corpus#611) are mandatory
   supplements, and an instrument found by any channel enters the frontier
   as a pending row until dispositioned.
   An instrument that bears on a computed surface must be **encoded**, not
   classified around: a classification is only honest for instruments with
   no bearing on any computed output (not in force, superseded regime,
   outside the certified period, or bearing solely on surfaces the spine
   already excludes).
3. **Dependency closure (leaf discipline).** Every formula input is one of:
   - **encoded** — derived by encoded rules from other inputs; or
   - an **observable act** (`leaf_kind: world_fact`) — a fact with
     independent existence that no captured or capturable legal rule
     defines how to compute: a date, a CPR/register entry, an issued
     assessment or judgment, a filing, an event. These are the only
     permissible leaves.

   A quantity that any legal instrument defines how to compute from
   observable facts (`leaf_kind: law_derived`) — an accrual month
   constructed from register days, an income basis defined by another act's
   section, an annually regulated amount — is an **open dependency**: it
   may not be case-supplied, and its presence computes `closed = false`
   until the defining rules are encoded and the boundary moves down to
   observable facts. Narrowing the certificate's scope around such a leaf
   ("supplied under a documented contract") does not close it; that was
   ruled insufficient for the word certified (Max, 2026-08-20, twice).
4. **Boundary honesty.** Every leaf carries a committed grounding row:
   its kind, its reason, and — for anything touching law — the governing
   instrument cited. The frontier is explicit, typed, and auditable; the
   claim never relies on an implicit "we didn't look there."

## What certified still does not claim

Even a certified program does not claim: correctness or availability of the
external systems that produce the observable acts it consumes (courts,
registers, tax authorities); instruments the registry links to the act
after the committed snapshot date (the graph refreshes by rerun); or effect
interactions with programs outside the certified composition. These are
disclosed per-certificate, and each is a fact about the world's interfaces,
never an unencoded rule.

## Process gates

Producer artifacts and derived flags are necessary, not sufficient: a
certified claim ships only after a launch-grade adversarial audit of the
committed decisions themselves (the validators prove consistency; audits
prove honesty — they have caught a gerrymandered exclusion, a
misclassified regulation, and pages nobody had read). And no certification
is announced anywhere, in any words, without Max's explicit clear.

## Definition history

- v1 (2026-08-14): spine closure + input frontier (captured/uncaptured).
- v2 (2026-08-19): + instrument closure (oracles#491, PR#494/#495) after
  the first certified=yes was retracted for never dispositioning the
  regulations under the act.
- v3 (2026-08-20, this document): + dependency closure with leaf
  discipline, after the second certified=yes was ruled an overclaim for
  case-supplying law-derived inputs (BEK 1563's optjening construction,
  personskatteloven § 7's income basis) and scoping around instruments that
  bear on encoded surfaces (§ 23's post-death collection bar, §§ 16-18's
  convention overrides). Under v3, no program currently certifies. Certify
  enforces the block centrally — a closure artifact without a complete
  dependency-closure block computes closed=false, whatever its producer
  reports — and each certificate's closed verdict carries either its
  enumerated worklist or the missing-block marker.
