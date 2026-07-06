# NYC school tax credit rate-reduction base-amount convention

The NYC school tax credit rate-reduction component has an exact, source-backed
convention difference against PolicyEngine in second-band cases.

The IT-201 instructions print rounded second-band base amounts:

- joint or surviving spouse: `$37 plus 0.228% of excess over $21,600`
- single or separate: `$21 plus 0.228% of excess over $12,000`
- head of household: `$25 plus 0.228% of excess over $14,400`

Axiom encodes those printed base amounts directly. PolicyEngine models the
component as a marginal-rate table, so the second-band carry-in is derived from
the first-band threshold and rate:

- joint or surviving spouse: `21,600 * 0.00171 = 36.936`, which is `$0.064`
  below the printed `$37`
- single or separate: `12,000 * 0.00171 = 20.52`, which is `$0.48` below the
  printed `$21`
- head of household: `14,400 * 0.00171 = 24.624`, which is `$0.376` below the
  printed `$25`

This explains all NYC school-rate mismatches in the component diagnostics:
zero/negative, first-band, and over-limit cases match; only second-band cases
carry the constant sub-dollar differences above. The residual is tracked
upstream in PolicyEngine/policyengine-us#8947.
