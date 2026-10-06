"""Arithmetic check for mfs-statutory-hand-computation.md (tax year 2026).

Every parameter below is copied from a quote in mfs-statute-extracts.md; the
section number of that file is given next to each one. This script only
redoes the arithmetic of the hand computation so a typo cannot slip through.
It is not an engine and encodes no legal conclusion that the .md does not
argue from the statute.
"""
from decimal import Decimal as D, ROUND_HALF_UP

# Rev. Proc. 2025-32 §4.01 Table 4 (MFS) and Table 2 (HoH)  [extracts 11.2]
MFS = [(0, 0, D("0.10")), (12400, 1240, D("0.12")), (50400, 5800, D("0.22")),
       (105700, 17966, D("0.24")), (201775, 41024, D("0.32")),
       (256225, 58448, D("0.35")), (384350, D("103291.75"), D("0.37"))]
HOH = [(0, 0, D("0.10")), (17700, 1770, D("0.12")), (67450, 7740, D("0.22")),
       (105700, 16155, D("0.24")), (201750, 39207, D("0.32")),
       (256200, 56631, D("0.35")), (640600, 191171, D("0.37"))]
# Rev. Proc. 2025-32 §4.14  [extracts 11.5]
SD = {"MFS": D(16100), "HOH": D(24150)}
AGED_MARRIED = D(1650)          # §63(f)(1)(A); $2,050 only if unmarried (f)(3)
# SSA / §3121(a)(1)  [extracts 7.1]
OASDI_BASE = D(184500)
# §3101  [extracts 7]
OASDI, HI, ADDMED = D("0.062"), D("0.0145"), D("0.009")
ADDMED_THRESH = {"MFS": D(125000), "HOH": D(200000)}   # (b)(2)(B) vs (b)(2)(C)
# §32(b)(1) percentages [extracts 6]; Rev. Proc. 2025-32 §4.06 amounts [11.4]
EITC = {1: dict(cp=D("0.34"), pp=D("0.1598"), eia=D(13020), po=D(23890)),
        0: dict(cp=D("0.0765"), pp=D("0.0765"), eia=D(8680), po=D(10860))}
# §24(h)(2)/(i)(2) and (h)(5)/(i)(1) via Rev. Proc. 2025-32 §4.05 [11.3]; (h)(6) $2,500
CTC_MAX, ACTC_CAP, ACTC_FLOOR, ACTC_RATE = D(2200), D(1700), D(2500), D("0.15")
# Rev. Proc. 2025-32 §4.10 [extracts 15.9]; §55(b)(1)(C), (d)(1)(C), (d)(2)
AMT_EX_MFS, AMT_PO_MFS, AMT_ZERO_MFS, AMT_28_MFS = D(70100), D(500000), D(640200), D(122250)
AMT_EX_HOH, AMT_28_OTHER = D(90100), D(244500)


def tax(ti, table):
    base = [r for r in table if ti > r[0]] or [table[0]]
    lo, b, r = base[-1]
    return D(b) + r * (ti - lo)


def ss_taxable(magi, ss, base, adj):
    """§86(a)-(b) with base/adjusted base from §86(c)."""
    prov = magi + ss / 2                      # (b)(1)(A)
    if prov <= base:
        return D(0)
    a1 = min(ss / 2, (prov - base) / 2)       # (a)(1)
    if prov <= adj:
        return a1
    return min(D("0.85") * (prov - adj) + min(a1, (adj - base) / 2),   # (a)(2)(A)
               D("0.85") * ss)                                           # (a)(2)(B)


def eitc(earned, agi, n):
    p = EITC[n]
    credit = p["cp"] * min(earned, p["eia"])                      # §32(a)(1)
    cap = p["cp"] * p["eia"] - p["pp"] * max(D(0), max(agi, earned) - p["po"])  # (a)(2)
    return max(D(0), min(credit, cap))


def ctc(n_kids, tax_before, earned):
    """§24(a),(d)(1),(h),(i) with §26(a) limit = regular tax (AMT is zero here)."""
    if n_kids == 0:
        return D(0), D(0)
    full = CTC_MAX * n_kids
    allowed_no_d = min(full, tax_before)                          # subpart A, §26(a)
    bump = ACTC_RATE * max(D(0), earned - ACTC_FLOOR)            # (d)(1)(B)(i), (h)(6)
    b = min(full, tax_before + bump) - allowed_no_d
    a = min(full, ACTC_CAP * n_kids)                              # (d)(1)(A), (h)(5)
    actc = min(a, b)
    nonref = min(full - actc, tax_before)                         # concluding sentence of (d)(1)
    return nonref, actc


def tmt(amti, ex, thresh28):
    te = max(D(0), amti - ex)
    return D("0.26") * min(te, thresh28) + D("0.28") * max(D(0), te - thresh28)


def fica(w):
    oasdi = OASDI * min(w, OASDI_BASE)
    hi = HI * w
    return oasdi, hi, oasdi + hi


def q(x):
    return x.quantize(D("0.01"), rounding=ROUND_HALF_UP)


cases = []
for w in (40000, 150000, 250000, 450000, 750000):
    cases.append(dict(id=f"mfs-wages-{w}", st="MFS", wages=D(w), ss=D(0), aged=False,
                      kids=0, base=None, eitc_ok=False))
for w in (15000, 45000):
    cases.append(dict(id=f"mfs-child-wages-{w}", st="HOH", wages=D(w), ss=D(0), aged=False,
                      kids=1, base=None, eitc_ok=True))
cases.append(dict(id="mfs-ss-cohabiting-wages-20000-ss-24000", st="MFS", wages=D(20000),
                  ss=D(24000), aged=True, kids=0, base=(D(0), D(0)), eitc_ok=False))
cases.append(dict(id="mfs-ss-cohabiting-ss-30000", st="MFS", wages=D(0), ss=D(30000),
                  aged=True, kids=0, base=(D(0), D(0)), eitc_ok=False))
cases.append(dict(id="mfs-ss-lived-apart-wages-20000-ss-24000", st="MFS", wages=D(20000),
                  ss=D(24000), aged=True, kids=0, base=(D(25000), D(34000)), eitc_ok=False))
for w in (6000, 11000, 16000):
    cases.append(dict(id=f"mfs-eitc-wages-{w}", st="MFS", wages=D(w), ss=D(0), aged=False,
                      kids=0, base=None, eitc_ok=False))

for c in cases:
    tss = ss_taxable(c["wages"], c["ss"], *c["base"]) if c["base"] else D(0)
    agi = c["wages"] + tss
    sd = SD[c["st"]] + (AGED_MARRIED if c["aged"] else 0)
    ti = max(D(0), agi - sd)
    tbc = tax(ti, MFS if c["st"] == "MFS" else HOH)
    e = eitc(c["wages"], agi, c["kids"]) if c["eitc_ok"] else D(0)
    e_cf = eitc(c["wages"], agi, c["kids"])   # counterfactual: §32(d) ignored
    nonref, actc = ctc(c["kids"], tbc, c["wages"])
    liab = tbc - nonref - actc - e
    oasdi, hi, fi = fica(c["wages"])
    am = ADDMED * max(D(0), c["wages"] - ADDMED_THRESH[c["st"]])
    # AMT upper bound: AMTI <= AGI (+ MFS add-on), exemption per Rev. Proc. §4.10
    if c["st"] == "MFS":
        amti = agi
        ex = max(D(0), AMT_EX_MFS - D("0.5") * max(D(0), amti - AMT_PO_MFS))
        addon = min(D("0.5") * max(D(0), amti - AMT_ZERO_MFS), AMT_EX_MFS)  # 50% reading (larger)
        t = tmt(amti + addon, ex, AMT_28_MFS)
    else:
        t = tmt(agi, AMT_EX_MFS, AMT_28_MFS)   # conservative: smaller MFS exemption and bracket
    print(f"{c['id']}: taxable_ss={q(tss)} agi={q(agi)} sd={q(sd)} ti={q(ti)} tax={q(tbc)} "
          f"eitc={q(e)} (cf {q(e_cf)}) ctc_nonref={q(nonref)} actc={q(actc)} liab={q(liab)} "
          f"oasdi={q(oasdi)} hi={q(hi)} fica={q(fi)} addmed={q(am)} tmt_upper={q(t)} amt={q(max(D(0), t - tbc))}")

# Counterfactual: child cases filed MFS (not HoH)
for w in (15000, 45000):
    w = D(w)
    ti = max(D(0), w - SD["MFS"])
    tbc = tax(ti, MFS)
    nonref, actc = ctc(1, tbc, w)
    e = eitc(w, w, 1)
    print(f"CF mfs-child-wages-{w} as MFS: ti={q(ti)} tax={q(tbc)} ctc_nonref={q(nonref)} "
          f"actc={q(actc)} eitc={q(e)} liab={q(tbc - nonref - actc - e)}")
# Rev. Proc.-rounded max credit variant for 1 child
for w in (15000, 45000):
    w = D(w)
    alt = max(D(0), min(D(4427), D(4427) - EITC[1]["pp"] * max(D(0), w - EITC[1]["po"])))
    print(f"EITC 1-child with Rev. Proc. printed max $4,427, wages {w}: {q(alt)}")
