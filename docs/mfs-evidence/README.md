# Married-filing-separately evidence (tax year 2026)

This is the statutory ground truth for adjudicating the `us-mfs` comparison suites (`comparisons/us-mfs-*.yaml`). The dispositions in `dispositions/us-mfs-*.yaml` cite it.

- `mfs-statute-extracts.md` holds verbatim extracts. Each block records its document, the version it is current through, the heading it sits under, who it applies to, and its URL. It covers:
  - 26 USC §§1(j), 2(b)-(c), 7703, 63(c) and (f), 86(c), 32(d), 3101(b)(2), 151(d)(5), 24 and 164(b)(6)-(7);
  - Rev. Proc. 2025-32;
  - the SSA 2026 contribution and benefit base;
  - the TAXSIM-35 documentation.
- `mfs-statutory-hand-computation.md` applies those extracts to the 13 `us-mfs` cases. `hand_compute_check.py` reruns that arithmetic in exact decimals.

No engine output was used to derive these values. TAXSIM, PolicyEngine and Axiom outputs are hypotheses that get graded against this text.

The raw fetches (statute HTML, PDFs and their text conversions) are about 8 MB and are not committed. The extracts refer to them as `raw/...`. `SHA256SUMS.txt` lists the hash of every raw file, so a re-fetch from the URLs in the extracts can be checked byte for byte. A US Code page can differ from the recorded bytes only when its "current through" release point changes.
