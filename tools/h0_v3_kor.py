"""H0 V3 — SAMMA MOTOR SOM V2, ENDAST ELIGIBILITY ÄNDRAD

Derivat av tools/h1419_kor_exakt_h0_v2.py. Enda funktionella skillnaden ar att
kandidater dessutom maste vara PIT-verifierade Nasdaq Stockholm Main Market Stock
vid beslutstidpunkten. Signal, ranking, paneler, N, viktning, kostnader och
returndefinition ar oforandrade.

Ursprunglig docstring foljer:

H1419 STEG 4 — KÖR EXAKT H0 ENLIGT DEN LÅSTA FÖRREGISTRERINGEN

Läser h1419_exakt_h0_preregistration.json, verifierar dess frysningshash och
att alla låsta indatafiler är oförändrade, och kör därefter exakt den
specifikation som står där. Avviker något stannar skriptet.

Ingen parameter i det här skriptet får ändras för att förbättra ett resultat.

Kör: /opt/momentum/venv/bin/python tools/h1419_kor_exakt_h0.py
"""
from __future__ import annotations
import hashlib, json, math, sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from h0_v3_eligibility import medlem as _pit_medlem

# Identitetsnyckel enligt forregistreringen: ISIN anvands ENBART for att slaa upp
# orderbook_code via Nasdaqs egen ISIN-kedja. membership_h1419_v2.json anvands
# ALDRIG som medlemskapskalla — endast dess ISIN-falt som identitetshint.
_ISIN = {r["kod"]: r.get("kalla") for r in json.loads(
    (Path("/home/hannesb/momentum_v2") /
     "validated/prices_h1419/membership_h1419_v2.json").read_text())["rows"]}
_ISIN = {k: (v if isinstance(v, str) and len(v) == 12 and v[:2].isalpha() else None)
         for k, v in _ISIN.items()}

V2 = Path("/home/hannesb/momentum_v2")
PREREG = V2 / "research_k/h1419_exakt_h0_preregistration_v2.json"
FREEZE = V2 / "research_k/H1419_PREREG_FREEZE_V2.json"
OUT = V2 / "research_k/h0_v3/h0_v3_RESULTAT.json"

PPY = 13.0
BLOCK, DRAWS, SEED = 13, 2000, 20260815


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 16), b""):
            h.update(c)
    return h.hexdigest()


def main():
    # ---------- 1. verifiera låset ----------
    frys = json.loads(FREEZE.read_text())
    if sha(PREREG) != frys["sha256"]:
        sys.exit("AVBRYTER: förregistreringen har ändrats efter frysningen.")
    pr = json.loads(PREREG.read_text())
    for f in pr["indata_last"]:
        if sha(V2 / f["fil"]) != f["sha256"]:
            sys.exit(f"AVBRYTER: indatafilen {f['fil']} har ändrats efter frysningen.")
    print("Lås verifierat: förregistrering och samtliga sex indatafiler oförändrade.")

    S = pr["specifikation"]
    N = S["portfoljstorlek_N"]
    COST = 0.002
    priser = json.loads((V2 / "validated/prices_h1419/prices_h1419_universum_v2.json").read_text())

    serie = {k: (np.array([np.datetime64(r["d"]) for r in rs]),
                 np.array([r["adj"] for r in rs], dtype=float)) for k, rs in priser.items()}

    # ---------- 2. panelgitter ----------
    paneler, cur = [], date.fromisoformat(pr["fonster"]["test_start"])
    while cur <= date.fromisoformat(pr["fonster"]["test_slut"]):
        paneler.append(cur.isoformat())
        cur += timedelta(days=int(S["panelfrekvens"].split()[0]))
    assert len(paneler) == pr["fonster"]["n_paneler"], "panelantalet avviker från förregistreringen"

    def idx_vid(k, dt):
        ds, _ = serie[k]
        i = int(np.searchsorted(ds, np.datetime64(dt), side="right")) - 1
        return i if i >= 0 else None

    def handlas(k, dt):
        """Observerbar handel: prisobservation inom 30 dagar före panelen."""
        i = idx_vid(k, dt)
        if i is None:
            return False
        ds, _ = serie[k]
        return int((np.datetime64(dt) - ds[i]) / np.timedelta64(1, "D")) <= 30

    def momentum(k, dt, weeks):
        ds, v = serie[k]
        now = np.datetime64(dt)
        mal = now - np.timedelta64(7 * weeks, "D")
        i = int(np.searchsorted(ds, now, side="right")) - 1
        j = int(np.searchsorted(ds, mal, side="right")) - 1
        if i < 0 or j < 0 or int((mal - ds[j]) / np.timedelta64(1, "D")) > 10:
            return None
        return float(v[i] / v[j] - 1.0)

    # ---------- 3. ranking enligt kanonisk regel ----------
    rankings = {}
    for dt in paneler:
        rows = []
        for k in serie:
            if not handlas(k, dt):
                continue
            # ===== H0 V3: ENDA FUNKTIONELLA SKILLNADEN MOT V2 =====
            # Prisexistens racker inte. Instrumentet maste vara PIT-verifierat
            # Nasdaq Stockholm Main Market Stock vid beslutstidpunkten.
            _elig, _orsak, _m = _pit_medlem(k, _ISIN.get(k), dt)
            if not _elig:
                continue
            # =======================================================
            rows.append({"kod": k, "m12": momentum(k, dt, 52), "m18": momentum(k, dt, 78)})
        for col in ("m12", "m18"):
            giltiga = sorted((r[col], r["kod"]) for r in rows if r[col] is not None)
            grupp = defaultdict(list)
            for val, kod in giltiga:
                grupp[val].append(kod)
            ranks, pos = {}, 1
            for val in sorted(grupp):
                ks = grupp[val]
                snitt = (pos + pos + len(ks) - 1) / 2 / max(1, len(giltiga))
                for kod in ks:
                    ranks[kod] = snitt
                pos += len(ks)
            for r in rows:
                r[col + "_rank"] = ranks.get(r["kod"])
        raa = [0.5 * (r["m12_rank"] + r["m18_rank"])
               if r["m12_rank"] is not None and r["m18_rank"] is not None else None for r in rows]
        med = float(np.median([x for x in raa if x is not None])) if any(x is not None for x in raa) else 0.5
        scored = [{**r, "score": med if v is None else v} for r, v in zip(rows, raa)]
        scored.sort(key=lambda x: (x["score"], x["kod"]), reverse=True)
        rankings[dt] = scored

    # ---------- 4. avkastning panel-till-panel ----------
    retmap = {}
    for k in serie:
        ds, v = serie[k]
        for a in range(len(paneler) - 1):
            dt, nd = paneler[a], paneler[a + 1]
            i = int(np.searchsorted(ds, np.datetime64(dt), side="right"))
            j = int(np.searchsorted(ds, np.datetime64(nd), side="right"))
            if i < len(ds) and j - 1 < len(ds) and j - 1 > i - 1 and i < j:
                retmap[(k, dt)] = float(v[j - 1] / v[i] - 1.0) if v[i] > 0 else 0.0
            else:
                retmap[(k, dt)] = 0.0
        retmap[(k, paneler[-1])] = 0.0

    # ---------- 5. hjälpmått ----------
    def sma_ok(k, dt):
        i = idx_vid(k, dt)
        if i is None or i < 200:
            return True
        _, v = serie[k]
        return v[i] >= float(np.mean(v[i - 200:i]))

    def bekraftad(k, dt):
        i = idx_vid(k, dt)
        if i is None or i < 120:
            return False
        _, v = serie[k]
        ma120 = float(np.mean(v[i - 120:i]))
        r = np.diff(v[i - 60:i + 1]) / v[i - 60:i]
        return bool(v[i] >= ma120 and float(np.std(r) * math.sqrt(252)) < 0.35)

    volm = {}
    for k in serie:
        _, v = serie[k]
        if len(v) > 61:
            r = np.diff(v) / v[:-1]
            for i in range(60, len(r)):
                volm[(k, i)] = float(np.std(r[i - 60:i]) * math.sqrt(252))

    def vol(k, dt):
        i = idx_vid(k, dt)
        return volm.get((k, i - 1), 0.25) if i else 0.25

    # ---------- 6. H0 topp-N, kanoniskt tak inkl. takfelet ----------
    prev, nets, antal = [], [], []
    for a, dt in enumerate(paneler):
        sched = a % 2 == 0                      # fasankare = första panelen
        raw = rankings[dt]
        elig = {r["kod"] for r in raw}
        if sched or not prev:
            sel0 = [r["kod"] for r in raw[:N]]
        else:
            sel0 = [k for k in prev if k in elig]
            if len(sel0) < N:
                sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][: N - len(sel0)]
        turn = 0.0 if not prev else 1.0 - len(set(sel0) & set(prev)) / max(1, len(sel0))
        sel = [k for k in sel0 if sma_ok(k, dt)]
        n = len(sel)
        antal.append(n)
        if n == 0:
            nets.append(0.0); prev = sel0; continue
        inv = 1.0 / (np.maximum(np.array([vol(k, dt) for k in sel]), 0.05) ** 1.5)
        ts = n / N
        w = inv / np.sum(inv) * ts
        w = w * np.array([1.0 if bekraftad(k, dt) else 0.75 for k in sel])
        w = np.clip(w, 0.01, 0.06)              # kanoniskt: clip en gång ...
        w = w / np.sum(w) * ts                  # ... och renormalisera, utan iteration
        rets = np.array([retmap.get((k, dt), 0.0) for k in sel])
        nets.append(float(np.sum(w * rets)) - COST * turn)
        prev = sel0
    h0 = np.array(nets)

    # ---------- 7. likaviktat universum ----------
    univ = np.array([float(np.mean([retmap.get((r["kod"], dt), 0.0) for r in rankings[dt]]))
                     for dt in paneler])

    def stat(x):
        w = np.cumprod(1 + x)
        dd = w / np.maximum.accumulate(w) - 1
        c = float(w[-1] ** (PPY / len(x)) - 1)
        v = float(x.std(ddof=1) * math.sqrt(PPY))
        return c, v, float(dd.min()), (c - 0.0224) / v if v > 0 else 0.0

    rng = np.random.default_rng(SEED)
    nb = int(math.ceil(len(h0) / BLOCK))
    outs = []
    for _ in range(DRAWS):
        idx = []
        for _ in range(nb):
            s = rng.integers(0, len(h0) - BLOCK + 1)
            idx.extend(range(s, s + BLOCK))
        idx = np.array(idx[:len(h0)])
        outs.append(np.cumprod(1 + h0[idx])[-1] ** (PPY / len(h0))
                    - np.cumprod(1 + univ[idx])[-1] ** (PPY / len(h0)))
    lo, hi = np.percentile(outs, [2.5, 97.5])
    d = h0 - univ
    t = float(d.mean() / (d.std(ddof=1) / math.sqrt(len(d))))

    ch, vh, ddh, sh = stat(h0)
    cu, vu, ddu, su = stat(univ)
    stod = bool(lo > 0 or hi < 0)

    res = {"version": "H0_V3_PIT_MEMBERSHIP_RESULTAT",
           "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
           "preregistration_sha256": frys["sha256"],
           "las_verifierat": True,
           "n_paneler": len(paneler), "medelantal_innehav": round(float(np.mean(antal)), 1),
           "h0": {"cagr": round(ch, 4), "vol": round(vh, 4), "maxdd": round(ddh, 4), "sharpe": round(sh, 4)},
           "likaviktat_universum": {"cagr": round(cu, 4), "vol": round(vu, 4),
                                    "maxdd": round(ddu, 4), "sharpe": round(su, 4)},
           "primart_utfall": {"delta_cagr": round(ch - cu, 4),
                              "ki_lo": round(float(lo), 4), "ki_hi": round(float(hi), 4),
                              "t_parvis": round(t, 3),
                              "andel_bootstrap_positiva": round(float(np.mean(np.array(outs) > 0)), 3)},
           "dom": "STÖD" if stod else "INGET STÖD",
           "obligatorisk_redovisning": pr["obligatorisk_redovisning"],
           "nettoserie_h0": [round(float(x), 6) for x in h0],
           "nettoserie_universum": [round(float(x), 6) for x in univ]}
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))

    print(f"\nH0 2014-2019, N={N}, {len(paneler)} paneler, medelinnehav {np.mean(antal):.1f}")
    print(f"  H0:                {ch:7.2%}  vol {vh:6.2%}  DD {ddh:7.2%}  Sharpe {sh:.3f}")
    print(f"  likaviktat univ.:  {cu:7.2%}  vol {vu:6.2%}  DD {ddu:7.2%}  Sharpe {su:.3f}")
    print(f"\n  PRIMÄRT UTFALL: delta-CAGR {ch-cu:+.2%}")
    print(f"    KI [{lo:+.2%}, {hi:+.2%}]   t {t:+.2f}   "
          f"andel positiva bootstraps {np.mean(np.array(outs)>0):.1%}")
    print(f"    DOM: {res['dom']}")
    print(f"\n  Obligatorisk redovisning:")
    for k, v in pr["obligatorisk_redovisning"].items():
        print(f"    {k}: {v}")
    print(f"\nSkrivet: {OUT}")


if __name__ == "__main__":
    main()
