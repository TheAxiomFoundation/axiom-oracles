# `axiom_oracles.bridges`

This package owns the shared Axiom oracle bridges consumed by axiom-oracles
and axiom-encode. Heavy PolicyEngine and Populace dependencies remain lazy so
the package and its mapping registry can be imported without an oracle runtime.

## RuleSpec execution contract

Every bridge uses one pre-launch RuleSpec layout:

```text
rulespec-<country>/
  <jurisdiction>/
    legislation/
    policies/
    programs/
    regulations/
    statutes/
```

Only `.yaml` files beneath those five roots are RuleSpec modules. Callers pass
the exact `rulespec-<country>` checkout and the exact executable
`axiom-rules-engine` binary. The bridges do not discover workspaces, sibling
checkouts, `_axiom` directories, Git-origin aliases, environment-provided
RuleSpec roots, flat `rulespec-<jurisdiction>` checkouts, or partially migrated
layouts. Engine subprocesses receive only the caller-authorized checkout in
the required explicit engine argument:

The canonical CLI inputs are:

```text
--rulespec-root /path/to/rulespec-<country>
--axiom-binary /path/to/axiom-rules-engine
```

## Module map

| Module | Purpose |
|---|---|
| `population.py` | Certified, hash-verified Populace artifact loading |
| `tax_populace.py` | US federal tax population comparison |
| `snap_populace.py` | SNAP population comparison |
| `us_populace.py` | Generic direct-variable US comparison |
| `medicaid_populace.py` | Medicaid population comparison |
| `efrs_uk.py` | UK tax and benefit Populace comparison |
| `coverage.py` | Canonical RuleSpec-to-PolicyEngine coverage reports |
| `repo_routing.py` | Exact country-checkout and jurisdiction-root identity |
| `rulespec_paths.py` | Exact module, checkout, binary, and engine-environment validation |
| `adapters.py` | Declarative PolicyEngine-US variable adapters |
| `registry.py` | Legal-ID keyed PolicyEngine oracle mapping registry |
| `snapscreener.py` | SnapScreener diagnostic cross-check |

The old `ecps_tax` and `ecps_snap` module aliases were removed. Import
`tax_populace` and `snap_populace` directly.

## Public API

`axiom_oracles.bridges` exports the shared engine-neutral case types,
Populace pins and loader, and PolicyEngine registry types. Comparison modules
are imported explicitly, for example:

```python
from axiom_oracles.bridges import tax_populace
```

`POPULACE_PINS` in `population.py` is the single certified pin table for
`populace://` artifacts. `axiom_oracles.populations.populace_us` derives its
repo-and-filename keyed view from that table.

Underscored helpers remain implementation details. The supported RuleSpec
execution helpers are `require_rulespec_checkout`, `require_rulespec_module`,
`resolve_rulespec_program`, `require_axiom_binary`, and `rulespec_engine_env` in
`rulespec_paths.py`.
