"""Pre-flight a state's SNAP QC subset before building its oracle suite.

Replicates the FNS QC Minimodel benefit arithmetic in pandas over one state's
FY2024 public-use rows — no engine, no rulespec checkout — to predict the
replay ceiling and profile every field the mapper must handle (playbook §9).
A state whose full chain reproduces here will replay exactly once its
conventions are projected; a state that does not reproduce has an editing
quirk to understand *before* any engine work.

For a jurisdiction already configured in the harness the standard-allowance
table comes from its shipped overlay (the same single source the replay
uses); for a new state pass ``--sua tier=amount`` (repeatable, region-suffixed
amounts allowed: ``--sua heating_cooling=992 --sua heating_cooling=923 ...``)
straight from tech doc Table F.7.

Usage:
    uv run --with pandas scripts/snap_qc_preflight.py --state-fips 36
    uv run --with pandas scripts/snap_qc_preflight.py --state-fips 48 \
        --sua heating_cooling=xxx --sua limited=yyy --sua telephone=zz

The QC CSV resolves exactly like the loader: an explicit --data-dir, then
AXIOM_SNAP_QC_DATA_DIR, then the ~/.cache/axiom-oracles/snap-qc cache.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

FY2024_MAX = {1: 291, 2: 535, 3: 766, 4: 973, 5: 1155, 6: 1386, 7: 1532, 8: 1751}
FY2024_ADDITIONAL_MEMBER = 219
FY2024_SHELTER_CAP = 672.0
FY2024_MINIMUM_BENEFIT = 23.0

COLUMNS = [
    "STATE", "YRMONTH", "SSI_CAP", "MN_FIP", "FSBEN", "RAWBEN", "CERTHHSZ",
    "RENT", "SUA1", "SUA2", "UTIL", "HOMEDED", "HOMELESS_DED", "FSMEDEXP",
    "FSMEDDED", "FSDEPDED", "FSCSDED", "FSCSEXP", "FSGRINC", "FSNETINC",
    "FSERNDED", "FSSTDDED", "FSSLTDED", "FSEARN", "FSUNEARN", "CAT_ELIG",
    "LIQRESOR", "FSNELDER", "FSNDIS", "FSMINBEN", "STATUS", "HWGT",
]


def _max_allotment(size: int) -> int:
    size = int(size)
    if size <= 0:
        return 0
    if size in FY2024_MAX:
        return FY2024_MAX[size]
    return FY2024_MAX[8] + (size - 8) * FY2024_ADDITIONAL_MEMBER


def _resolve_csv(data_dir: str | None) -> Path:
    name = "qc_pub_fy2024.csv"
    for candidate in (data_dir, os.environ.get("AXIOM_SNAP_QC_DATA_DIR")):
        if candidate and (Path(candidate) / name).exists():
            return Path(candidate) / name
    cached = Path.home() / ".cache/axiom-oracles/snap-qc" / name
    if cached.exists():
        return cached
    raise SystemExit(
        f"{name} not found; pass --data-dir, set AXIOM_SNAP_QC_DATA_DIR, or "
        "let the oracle loader download it once"
    )


def _sua_amounts(args: argparse.Namespace) -> dict[str, list[float]]:
    if args.sua:
        table: dict[str, list[float]] = {}
        for item in args.sua:
            tier, _, amount = item.partition("=")
            table.setdefault(tier.strip(), []).append(float(amount))
        return table
    try:
        from axiom_oracles.bridges.rulespec_overlay import load_overlay_spec
        from axiom_oracles.bridges.snap_qc_compare import (
            QC_JURISDICTIONS,
            sua_amounts_from_overlay,
        )
    except ImportError:
        return {}
    for config in QC_JURISDICTIONS.values():
        if config.state_fips == args.state_fips:
            spec = load_overlay_spec(config.overlay)
            nested = sua_amounts_from_overlay(spec, config)
            return {
                tier: list(entries.values()) for tier, entries in nested.items()
            }
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-fips", type=int, required=True)
    parser.add_argument("--data-dir", default=None)
    parser.add_argument(
        "--sua",
        action="append",
        default=None,
        help="tier=amount (repeatable; overrides any configured overlay table)",
    )
    args = parser.parse_args()

    import numpy as np
    import pandas as pd

    frame = pd.read_csv(
        _resolve_csv(args.data_dir),
        usecols=lambda c: c in set(COLUMNS),
        na_values=["."],
        low_memory=False,
    )
    state = frame[frame.STATE == args.state_fips]
    print(f"state FIPS {args.state_fips}: {len(state)} rows")
    if not len(state):
        return 1

    print(
        "SSI_CAP:",
        state.SSI_CAP.fillna(-1).astype(int).value_counts().sort_index().to_dict(),
        "| MN_FIP=1:",
        int((state.MN_FIP.fillna(0) == 1).sum()),
    )
    kept = state[
        state.SSI_CAP.fillna(0).isin([0, 4]) & (state.MN_FIP.fillna(0) != 1)
    ]
    kept = kept[(kept.FSBEN.fillna(0) > 0) & (kept.CERTHHSZ.fillna(0) > 0)].copy()
    print(f"in scope (loader rules): {len(kept)}")

    # Field profile the mapper must handle.
    print("SUA1:", kept.SUA1.fillna(-1).astype(int).value_counts().sort_index().to_dict())
    print("HOMEDED:", kept.HOMEDED.fillna(-1).astype(int).value_counts().sort_index().to_dict())
    print("CAT_ELIG:", kept.CAT_ELIG.fillna(-1).astype(int).value_counts().sort_index().to_dict())
    cs = kept[kept.FSCSEXP.fillna(0) > 0]
    disallowed = int((cs.FSCSDED.fillna(0) == 0).sum()) if len(cs) else 0
    print(
        f"child support: {len(cs)} rows report payments, "
        f"{disallowed} disallowed as deductions (feed FSCSDED, not FSCSEXP)"
    )
    smd = kept[
        (kept.FSMEDDED.fillna(0) > 0)
        & ((kept.FSMEDDED - kept.FSMEDEXP.fillna(0)).abs() > 0.5)
    ]
    print(f"standard-medical-deduction rows (FSMEDDED != FSMEDEXP): {len(smd)}")

    table = _sua_amounts(args)
    if table:
        full = sorted({a for amounts in table.values() for a in amounts if a})
        util = kept.UTIL
        print(
            f"UTIL: missing {int(util.isna().sum())}, zero {int((util == 0).sum())}, "
            f"matches a standard {int(util.isin(full).sum())}, "
            f"other nonzero {int(((~util.isin(full)) & util.notna() & (util != 0)).sum())}"
        )
    else:
        print("UTIL: no SUA table (pass --sua tier=amount from Table F.7)")

    # Minimodel replication: whole-dollar chain over the file's own inputs.
    nbs = (
        kept.FSGRINC.fillna(0)
        - kept.FSERNDED.fillna(0)
        - kept.FSSTDDED.fillna(0)
        - kept.FSMEDDED.fillna(0)
        - kept.FSDEPDED.fillna(0)
        - kept.FSCSDED.fillna(0)
        - (kept.HOMELESS_DED.fillna(0) if "HOMELESS_DED" in kept else 0)
    ).clip(lower=0)
    elderly_disabled = (kept.FSNELDER.fillna(0) > 0) | (kept.FSNDIS.fillna(0) > 0)
    shelter = kept.RENT.fillna(0) + kept.UTIL.fillna(0)
    excess = (shelter - np.floor(nbs / 2)).clip(lower=0)
    shelter_ded = np.where(
        elderly_disabled, excess, excess.clip(upper=FY2024_SHELTER_CAP)
    )
    shelter_ded = np.where(kept.HOMEDED.fillna(1) == 3, 0.0, shelter_ded)
    net = (nbs - shelter_ded).clip(lower=0)
    maxima = kept.CERTHHSZ.apply(_max_allotment)
    benefit = (maxima - np.ceil(0.3 * net)).clip(lower=0)
    benefit = np.where(
        kept.CERTHHSZ <= 2, np.maximum(benefit, FY2024_MINIMUM_BENEFIT), benefit
    )

    shelter_ok = int(((shelter_ded - kept.FSSLTDED.fillna(-9)).abs() <= 1).sum())
    net_ok = int(((net - kept.FSNETINC.fillna(-9)).abs() <= 1).sum())
    benefit_ok = int((benefit == kept.FSBEN).sum())
    print(
        f"Minimodel replication: shelter {shelter_ok}/{len(kept)}, "
        f"net {net_ok}/{len(kept)}, benefit exact {benefit_ok}/{len(kept)}"
    )
    if benefit_ok == len(kept):
        print("ceiling: 100% — every in-scope review reproduces; build the suite")
    else:
        misses = kept[benefit != kept.FSBEN]
        print(
            "ceiling below 100% — inspect these rows' editing quirks first: "
            f"{misses.index.tolist()[:10]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
