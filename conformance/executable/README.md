# Computed executable evidence

Executable receipts use `axiom_oracles.executable_reproduction.v1`; the NZ
receipt, written by `scripts/nz_executable_reproduction.py`, uses `.v2`. A program
certificate accepts one only through the producer named in `scripts/certify.py`;
the producer must validate committed artifact bytes, requests, golden outputs,
and the bound transcript and must return a re-derived `executable` Boolean.

The NZ receipt commits the exact 1,153,339-byte compiled comparison artifact whose
SHA-256 was re-derived by rerunning the pinned harness on engine `363c6a6c`.
Its request set is the 19 engine
calls made while evaluating the
`single_parent_three_children_area1_rent` scenario at weekly wages 0 and 740.
Those calls cover all 19 requested RuleSpec output roots and support 22 of the
1,976 comparison cells: the 11 program-view columns at each selected wage.

`python scripts/nz_executable_reproduction.py --check` is hermetic and is the
CI gate: it verifies all committed bytes and re-derives the transcript/golden
matches. `--check --live` is the stronger integration gate. It requires the
pinned RuleSpec checkout and an engine checkout at the pinned commit,
recompiles the composition byte-for-byte, executes every request, and
byte-compares the fresh transcript. Locally it runs the pinned macOS release
binary, whose bytes must match the recorded SHA-256. That binary is not
portable to the Linux CI runner, so CI builds the pinned engine checkout with
`cargo build --locked --release` and runs `--check --live --source-built-engine`:
the same live recompile and replay, with the checkout's commit checked instead
of the binary's bytes.
