"""BESLUTSJOURNAL — ett års ägande, beslut för beslut, med kontrafaktiskt utfall.

För varje handelstillfälle loggas: VAD som hände, VARFÖR modellen gjorde det,
och OM det var adekvat — mätt mot vad som faktiskt hände efteråt.

Fyra beslutstyper:
  KÖP        varför togs den in? vad missade vi före? gick det bra efter?
  SÄLJ       varför åkte den ut? vad hände efter att vi sålt?
  ÖKA/MINSKA stämde riktningen mot vad som följde?
  EJ ÄGD     stora rörelser i universumet som aldrig ägdes

Rapporteras på både portfölj- och innehavsnivå. DIAGNOSTISKT.
"""
from __future__ import annotations

import importlib.util, json, math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/beslutsjournal_results.json"
PPY, COST = 13.0, 0.002
AR_PANELER = 13


def ladda():
    s = importlib.util.spec_from_file_location("h2h", V2 / "tools/research_all_6_models_head_to_head.py")
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    core, prices, term = m.load_data()
    rmap, alld = m.execution_engine(core, prices, term)
    vmap, pser = m.compute_vols(prices, window=60)
    rk = m.derive_h0_scores(core, prices)
    cf = m.fetch_fundamental_confirmations(rk, prices)
    return m, rmap, alld, vmap, pser, rk, cf


def sma_bryter(pser, k, dt):
    if k not in pser: return False
    ds, a = pser[k]
    i = next((j for j in range(len(ds) - 1, -1, -1) if ds[j] <= dt), None)
    return i is not None and i >= 200 and a[i] < float(np.mean(a[i - 200:i]))


def bakat(pser, k, dt, dagar):
    if k not in pser: return None
    ds, a = pser[k]
    i = next((j for j in range(len(ds) - 1, -1, -1) if ds[j] <= dt), None)
    if i is None or i < dagar: return None
    return float(a[i] / a[i - dagar] - 1)


def main() -> None:
    m, rmap, alld, vmap, pser, rk, cf = ladda()
    dates = sorted(rk.keys()); anchor = alld.index(m.PHASE_ANCHOR_H0) % 2

    prev, H, RANK = [], [], []
    for dt in dates:
        sched = alld.index(dt) % 2 == anchor
        raw = rk[dt]; elig = {r["kod"] for r in raw}
        sel0 = [r["kod"] for r in raw[:30]] if (sched or not prev) else [k for k in prev if k in elig]
        if not (sched or not prev) and len(sel0) < 30:
            sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][:30 - len(sel0)]
        sel = [k for k in sel0 if not sma_bryter(pser, k, dt)]
        n = len(sel)
        if n:
            vols = np.array([vmap.get((k, dt), 0.25) for k in sel], float)
            iv = 1.0 / (np.maximum(vols, 0.05) ** 1.5)
            w = iv / iv.sum() * (n / 30.0); w = np.clip(w, 0.01, 0.06); w = w / w.sum() * (n / 30.0)
            c = np.array([1.0 if cf.get((k, dt), False) else 0.75 for k in sel])
            w = w * c; w = np.clip(w, 0.01, 0.06); w = w / w.sum() * (n / 30.0)
        else:
            w = np.array([])
        H.append(dict(zip(sel, w))); RANK.append({r["kod"]: i for i, r in enumerate(raw)})
        prev = sel0

    i0 = len(dates) - AR_PANELER - 1
    period = dates[i0:]
    logg = []

    def fwd(k, i, steg=1):
        s = 1.0
        for j in range(i, min(i + steg, len(dates))):
            r = rmap.get((k, dates[j]))
            if r is None: return None
            s *= (1 + r)
        return s - 1

    for idx in range(i0 + 1, len(dates)):
        dt = dates[idx]; f, b = H[idx], H[idx - 1]
        for k, w in f.items():
            if k not in b:
                logg.append({"panel": dt, "typ": "KÖP", "kod": k, "vikt": w,
                             "varfor": "in i topp-30 och klarar SMA200",
                             "missat_fore_4v": bakat(pser, k, dt, 20),
                             "missat_fore_13v": bakat(pser, k, dt, 65),
                             "utfall_1p": fwd(k, idx), "utfall_2p": fwd(k, idx, 2)})
        for k, w in b.items():
            if k not in f:
                orsak = "SMA200-grind" if sma_bryter(pser, k, dt) else "ur topp-30"
                logg.append({"panel": dt, "typ": "SÄLJ", "kod": k, "vikt": w,
                             "varfor": orsak, "rank_fore": RANK[idx - 1].get(k),
                             "rank_nu": RANK[idx].get(k),
                             "utfall_efter_1p": fwd(k, idx), "utfall_efter_2p": fwd(k, idx, 2)})
        for k, w in f.items():
            if k in b:
                d = w / b[k] - 1
                if abs(d) > 0.02:
                    logg.append({"panel": dt, "typ": "ÖKA" if d > 0 else "MINSKA", "kod": k,
                                 "vikt": w, "viktandring": d,
                                 "varfor": "invers volatilitet omräknad",
                                 "utfall_1p": fwd(k, idx)})
        agd = set(f)
        for kod, r in list(RANK[idx].items())[:200]:
            if kod in agd: continue
            x = fwd(kod, idx)
            if x is not None and x > 0.25:
                logg.append({"panel": dt, "typ": "EJ ÄGD", "kod": kod, "rank": r,
                             "varfor": "ej i topp-30" if r >= 30 else "topp-30 men SMA200 blockerade",
                             "utfall_1p": x})

    def sn(rows, f):
        v = [r[f] for r in rows if r.get(f) is not None]
        return float(np.mean(v)) if v else float("nan"), len(v)

    kop = [r for r in logg if r["typ"] == "KÖP"]
    salj = [r for r in logg if r["typ"] == "SÄLJ"]
    oka = [r for r in logg if r["typ"] == "ÖKA"]
    mins = [r for r in logg if r["typ"] == "MINSKA"]
    ejagd = [r for r in logg if r["typ"] == "EJ ÄGD"]

    print("=" * 92)
    print(f"BESLUTSJOURNAL — {period[0]} till {period[-1]}  ({len(period)-1} beslutspaneler)")
    print("=" * 92)
    print(f"\n  {len(kop)} köp · {len(salj)} sälj · {len(oka)} ökningar · {len(mins)} minskningar · "
          f"{len(ejagd)} stora rörelser vi inte ägde\n")

    print("  KÖP — vad missade vi innan, och gick det bra efter?")
    for f_, l in [("missat_fore_4v", "kursen 4 v före köpet"), ("missat_fore_13v", "kursen 13 v före"),
                  ("utfall_1p", "utfall 4 v efter"), ("utfall_2p", "utfall 8 v efter")]:
        mu, n = sn(kop, f_); print(f"    {l:26s} {mu:+7.2%}  (n={n})")
    tr = [r for r in kop if r.get("utfall_1p") is not None and r["utfall_1p"] > 0]
    print(f"    andel köp som steg           {len(tr)/max(len([r for r in kop if r.get('utfall_1p') is not None]),1):.0%}")

    print("\n  SÄLJ — vad hände EFTER att vi sålt?")
    for typ in ["SMA200-grind", "ur topp-30"]:
        g = [r for r in salj if r["varfor"] == typ]
        if not g: continue
        m1, n1 = sn(g, "utfall_efter_1p"); m2, _ = sn(g, "utfall_efter_2p")
        upp = len([r for r in g if (r.get("utfall_efter_1p") or 0) > 0])
        print(f"    {typ:16s} n={len(g):3d}  efter 4 v {m1:+7.2%}  efter 8 v {m2:+7.2%}  "
              f"steg ändå {upp/max(n1,1):.0%}")

    print("\n  VIKTFÖRÄNDRING — stämde riktningen?")
    for l, g in [("ÖKADE", oka), ("MINSKADE", mins)]:
        mu, n = sn(g, "utfall_1p")
        print(f"    {l:10s} n={n:4d}  utfall efter {mu:+7.2%}")

    print("\n  EJ ÄGDA STORA RÖRELSER (> +25 % på en panel)")
    for typ in ["ej i topp-30", "topp-30 men SMA200 blockerade"]:
        g = [r for r in ejagd if r["varfor"] == typ]
        if not g: continue
        mu, n = sn(g, "utfall_1p")
        print(f"    {typ:32s} n={len(g):3d}  medelrörelse {mu:+7.2%}")
    top = sorted(ejagd, key=lambda r: -(r.get("utfall_1p") or 0))[:8]
    print(f"\n    Största missade:")
    for r in top:
        print(f"      {r['panel']}  {r['kod']:10s} {r['utfall_1p']:+7.1%}  rank {r['rank']:3d}  {r['varfor']}")

    OUT.write_text(json.dumps({"version": "BESLUTSJOURNAL_V1",
                               "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               "period": [period[0], period[-1]], "n_beslut": len(logg),
                               "logg": logg}, ensure_ascii=False, indent=2))
    print(f"\n  {len(logg)} beslut loggade → {OUT.name}")


if __name__ == "__main__":
    main()
