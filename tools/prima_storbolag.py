"""KAN VI PRIMA STÖRRE BOLAG IN I PORTFÖLJEN?

Frågan är inte alfa utan exponering. Modellen har storbolagsbeta −0,11 och
småbolagsbeta +0,64, vilket gör att den står utanför en storbolagsledd uppgång
och kan ligga −18 % mot index ett helt år. Målet här är att minska det, inte
att höja avkastningen.

Storleksproxy: ADV, 20 dagars medelvärde av pris x volym ur EODHD-arkivet.
Finns för båda fönstren. Korrelerar starkt med börsvärde.

Tre sätt att prima:
  P1  ADV-kvot   reservera k platser åt de mest omsatta namnen i topp-60
  P2  blandad poäng   (1-a) x momentumrank + a x ADV-rank
  P3  ADV-golv   köp bara namn över en percentil i omsättning

Mäts på fyra saker, inte bara CAGR:
  avkastning, volatilitet, tracking error mot XACT Sverige, och sämsta
  rullande tolvmånadersfönster relativt index.

Kör: /opt/momentum/venv/bin/python tools/prima_storbolag.py
"""
from __future__ import annotations
import bisect, gzip, json, math, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
EOD = Path("/home/hannesb/momentum_prod_work/momentum_ml/cache/eodhd_archive/ST")
sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S
import h1419_motor as M

OUT = V2 / "research_k/prima_storbolag_results.json"
COST = 0.002

# ---------- ADV ur arkivet ----------
_adv = {}


def adv(k, dt):
    if k not in _adv:
        rows = None
        for kat in ("active", "delisted"):
            p = EOD / kat / "eod" / f"{k}.json.gz"
            if p.exists():
                try:
                    with gzip.open(p, "rt") as f:
                        rows = json.load(f)
                    break
                except Exception:
                    pass
        if rows:
            ds = [r["date"] for r in rows]
            v = [(r.get("close") or 0) * (r.get("volume") or 0) for r in rows]
            _adv[k] = (ds, np.array(v, dtype=float))
        else:
            _adv[k] = ([], np.array([]))
    ds, v = _adv[k]
    if not ds:
        return None
    i = bisect.bisect_right(ds, dt) - 1
    if i < 20:
        return None
    x = v[i - 20:i]
    x = x[x > 0]
    return float(np.median(x)) if len(x) else None


def index_serie(dts):
    with gzip.open(EOD / "active/eod/XACT-SVERIGE.json.gz", "rt") as f:
        rows = json.load(f)
    ds = [r["date"] for r in rows]; a = [r["adjusted_close"] for r in rows]

    def px(dt):
        i = bisect.bisect_right(ds, dt) - 1
        return a[i] if i >= 0 else None
    return np.array([(px(dts[j + 1]) / px(dts[j]) - 1) if j < len(dts) - 1 and px(dts[j]) else 0.0
                     for j in range(len(dts))])


def sim(F, N=30, adv_kvot=0, adv_vikt=0.0, adv_golv=None, hyst_rank=35):
    dts, ret = F["eval_dates"], F["returns_map"]
    volf, smaf, conff, schedf = F["vol_fn"], F["sma_fn"], F["conf_fn"], F["sched_fn"]
    prev, prevw, nets = [], {}, []
    for pi, dt in enumerate(dts):
        sched = schedf(pi, dt)
        raw = F["rankings"][dt]
        elig = {r["kod"] for r in raw}
        rm = {r["kod"]: i + 1 for i, r in enumerate(raw)}
        # ADV-rank inom topp-100
        topp = [r["kod"] for r in raw[:100]]
        av = {k: adv(k, dt) for k in topp}
        giltiga = sorted([(v, k) for k, v in av.items() if v], reverse=True)
        advrank = {k: i + 1 for i, (v, k) in enumerate(giltiga)}
        golv = None
        if adv_golv is not None and giltiga:
            golv = float(np.percentile([v for v, _ in giltiga], adv_golv * 100))
        if sched or not prev:
            keep = [k for k in (prev or []) if rm.get(k, 999) <= hyst_rank and k in elig]
            kand = [r["kod"] for r in raw if r["kod"] not in keep]
            if golv is not None:
                kand = [k for k in kand if (av.get(k) or 0) >= golv]
            if adv_vikt:
                nk = len(kand)
                po = {k: (1 - adv_vikt) * (rm.get(k, 999) / max(1, nk))
                         + adv_vikt * (advrank.get(k, 100) / 100.0) for k in kand}
                kand = sorted(kand, key=lambda k: po[k])
            if adv_kvot and prev:
                stora = [k for k in kand if advrank.get(k, 999) <= 30][:adv_kvot]
                kand = stora + [k for k in kand if k not in stora]
            sel0 = (keep + kand)[:N]
        else:
            sel0 = [k for k in prev if k in elig]
            if len(sel0) < N:
                sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][: N - len(sel0)]
        sel = [k for k in sel0 if smaf(k, dt)]
        n = len(sel)
        if n == 0:
            nets.append(0.0); prev, prevw = sel0, {}; continue
        ts = n / N
        inv = 1.0 / (np.maximum(np.array([volf(k, dt) for k in sel]), 0.05) ** 1.5)
        w = inv / np.sum(inv) * ts
        w = w * np.array([1.0 if conff(k, dt) else 0.75 for k in sel])
        w = np.clip(w, 0.01, 0.06); w = w / np.sum(w) * ts
        if prevw:
            w = np.array([prevw.get(k, 0.0) if (abs(w[i] - prevw.get(k, 0.0)) < 0.005
                                                and prevw.get(k, 0.0) > 0) else w[i]
                          for i, k in enumerate(sel)])
            w = w / np.sum(w) * ts
        curr = dict(zip(sel, w))
        turn = float(np.sum(w)) if not prev else \
            sum(abs(curr.get(k, 0.0) - prevw.get(k, 0.0)) for k in set(prevw) | set(curr)) / 2.0
        nets.append(float(np.sum(w * np.array([ret.get((k, dt), 0.0) for k in sel]))) - COST * turn)
        prev, prevw = sel0, curr
    return np.array(nets)


def matt(x, idx):
    w = np.cumprod(1 + x); dd = w / np.maximum.accumulate(w) - 1
    c = float(w[-1] ** (13 / len(x)) - 1)
    v = float(x.std(ddof=1) * math.sqrt(13))
    te = float((x - idx).std(ddof=1) * math.sqrt(13))
    W = 13
    rel = [float(np.prod(1 + x[i:i + W]) - 1) - float(np.prod(1 + idx[i:i + W]) - 1)
           for i in range(len(x) - W + 1)]
    return {"cagr": round(c, 4), "vol": round(v, 4), "maxdd": round(float(dd.min()), 4),
            "sharpe": round((c - 0.0224) / v, 3),
            "tracking_error": round(te, 4),
            "samsta_12m_rel": round(float(min(rel)), 4),
            "senaste_12m_rel": round(float(rel[-1]), 4),
            "andel_12m_bakom": round(float(np.mean(np.array(rel) < 0)), 3)}


def main():
    IDX = {"26": index_serie(S.DT26), "19": index_serie(M.PANELER)}
    ut = {"version": "PRIMA_STORBOLAG_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "storleksproxy": "ADV = 20 dagars median av close x volume ur EODHD-arkivet",
          "varianter": {}}
    varianter = [("baslinje STACK_H", {}),
                 ("ADV-kvot 3 platser", dict(adv_kvot=3)),
                 ("ADV-kvot 6 platser", dict(adv_kvot=6)),
                 ("ADV-kvot 10 platser", dict(adv_kvot=10)),
                 ("blandad poäng a=0,25", dict(adv_vikt=0.25)),
                 ("blandad poäng a=0,50", dict(adv_vikt=0.50)),
                 ("ADV-golv median", dict(adv_golv=0.50)),
                 ("ADV-golv 75:e percentil", dict(adv_golv=0.75))]
    print(f"{'variant':<26}{'CAGR26':>8}{'TE26':>7}{'sämst12m':>10}{'senaste':>9}"
          f"{'CAGR19':>8}{'TE19':>7}{'sämst12m':>10}")
    for namn, kw in varianter:
        a26, a19 = sim(S.F26, **kw), sim(S.F19, **kw)
        m26, m19 = matt(a26, IDX["26"]), matt(a19, IDX["19"])
        ut["varianter"][namn] = {"f2020_2026": m26, "f2014_2019": m19}
        print(f"{namn:<26}{m26['cagr']:>8.2%}{m26['tracking_error']:>7.1%}"
              f"{m26['samsta_12m_rel']:>10.2%}{m26['senaste_12m_rel']:>9.2%}"
              f"{m19['cagr']:>8.2%}{m19['tracking_error']:>7.1%}{m19['samsta_12m_rel']:>10.2%}")
    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    print(f"\nSkrivet: {OUT}")


if __name__ == "__main__":
    main()
