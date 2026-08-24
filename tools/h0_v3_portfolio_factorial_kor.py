"""H0_V3_PORTFOLIO_LAYER_FACTORIAL_IDENTIFICATION — faktoriell, icke-sekventiell.

Forregistrering: research_k/h0_v3_portfolio_factorial/preregistration.json
Frysning:        research_k/h0_v3_portfolio_factorial/PREREG_FREEZE.json

INGEN H0-LOGIK DUPLICERAS. Datapipelinen (priser, paneler, ranking, retmap,
sma_ok, bekraftad, vol) extraheras som KALLTEXT ur den frysta tools/h0_v3_kor.py
och exekveras ovarierad. Endast viktslingan skrivs om, och endast for att
exponera de fem faktorflaggorna.

Reproduktionsgate: armen (E1, invvol1.5, FR pa, legacy-tak) AR H0 V3 och maste
ge 26,61 % respektive 12,99 %. Avviker den stannar skriptet.

Kor: /opt/momentum/venv/bin/python tools/h0_v3_portfolio_factorial_kor.py
"""
from __future__ import annotations
import hashlib, json, math, re, sys
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
UT = V2 / "research_k/h0_v3_portfolio_factorial"
PREREG, FREEZE = UT / "preregistration.json", UT / "PREREG_FREEZE.json"
PPY, RF = 13.0, 0.0224
BLOCK, DRAWS, SEED = 13, 2000, 20260815
KANON_SHA = "f844eaea4492d539"


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def hamta_pipeline_kalltext() -> str:
    """Klipper ut den deterministiska datadelen av h0_v3_kor.main() ordagrant."""
    src = (V2 / "tools/h0_v3_kor.py").read_text()
    a = src.index('    S = pr["specifikation"]')
    b = src.index("    # ---------- 6. H0 topp-N")
    blk = src[a:b]
    return "\n".join(l[4:] if l.startswith("    ") else l for l in blk.split("\n"))


def stat(x):
    x = np.asarray(x, float)
    w = np.cumprod(1 + x)
    cagr = w[-1] ** (PPY / len(x)) - 1
    vol = float(x.std(ddof=1) * math.sqrt(PPY))
    dd = float((w / np.maximum.accumulate(w) - 1).min())
    return {"cagr": float(cagr), "vol": vol, "maxdd": dd,
            "sharpe": float((cagr - RF) / vol) if vol else float("nan")}


def kor_arm(NS, exponering, viktning, fr, tak):
    """Exakt H0 V3:s slinga (rad 182-208) med de fem faktorerna som flaggor."""
    N, COST = NS["N"], NS["COST"]
    paneler, rankings, retmap = NS["paneler"], NS["rankings"], NS["retmap"]
    sma_ok, bekraftad, vol = NS["sma_ok"], NS["bekraftad"], NS["vol"]
    prev, nets, antal, kassa = [], [], [], []
    for a, dt in enumerate(paneler):
        sched = a % 2 == 0
        raw = rankings[dt]
        elig = {r["kod"] for r in raw}
        if sched or not prev:
            sel0 = [r["kod"] for r in raw[:N]]
        else:
            sel0 = [k for k in prev if k in elig]
            if len(sel0) < N:
                sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][: N - len(sel0)]
        turn = 0.0 if not prev else 1.0 - len(set(sel0) & set(prev)) / max(1, len(sel0))
        # ---- K4a namnfilter
        sel = [k for k in sel0 if sma_ok(k, dt)] if exponering in ("E1", "E2") else list(sel0)
        n = len(sel)
        antal.append(n)
        if n == 0:
            nets.append(0.0); kassa.append(1.0); prev = sel0; continue
        # ---- K4b kassakanal
        ts = n / N if exponering == "E1" else 1.0
        kassa.append(1.0 - ts)
        # ---- K5 viktning
        if viktning == "invvol1.5":
            inv = 1.0 / (np.maximum(np.array([vol(k, dt) for k in sel]), 0.05) ** 1.5)
            w = inv / np.sum(inv) * ts
        else:
            w = np.full(n, ts / n)
        # ---- K6 bekraftelsemultiplikator
        if fr:
            w = w * np.array([1.0 if bekraftad(k, dt) else 0.75 for k in sel])
        # ---- K7 vikttak
        if tak == "legacy":
            w = np.clip(w, 0.01, 0.06)
            w = w / np.sum(w) * ts
        elif tak == "waterfill":
            for _ in range(200):
                w = np.clip(w, 0.01, 0.06)
                d = ts - float(np.sum(w))
                if abs(d) < 1e-12: break
                fri = (w > 0.01 + 1e-12) & (w < 0.06 - 1e-12)
                if not fri.any(): break
                s = float(np.sum(w[fri]))
                w[fri] += d * (w[fri] / s if s > 0 else 1.0 / fri.sum())
            w = np.clip(w, 0.01, 0.06)
        else:
            w = w / np.sum(w) * ts
        rets = np.array([retmap.get((k, dt), 0.0) for k in sel])
        nets.append(float(np.sum(w * rets)) - COST * turn)
        prev = sel0
    return np.array(nets), float(np.mean(antal)), float(np.mean(kassa))


def armar():
    for e, v, f, t in product(("E0", "E1", "E2"), ("likavikt", "invvol1.5"),
                              (False, True), ("inget", "legacy", "waterfill")):
        if e == "E0" and False:  # E0 har ingen kassakanal; K4b ar inert (en arm)
            continue
        yield e, v, f, t


def bygg(prereg_path, freeze_path, isin, redirect):
    import h0_v3_kor as H
    frys = json.loads(Path(freeze_path).read_text())
    if sha(prereg_path) != frys["sha256"]:
        sys.exit("AVBRYTER: H0 V3-forregistreringen har andrats efter frysningen.")
    pr = json.loads(Path(prereg_path).read_text())
    for fdef in pr["indata_last"]:
        if sha(V2 / fdef["fil"]) != fdef["sha256"]:
            sys.exit(f"AVBRYTER: indatafilen {fdef['fil']} har andrats efter frysningen.")
    g = dict(vars(H)); g.update({"pr": pr, "np": np, "_ISIN": isin})
    if redirect:
        import revalidation_sandbox as S
        S.install(redirect, [], "H0V3-FACT", "H0_V3_PORTFOLIO_LAYER_FACTORIAL")
    exec(compile(hamta_pipeline_kalltext(), "<h0_v3_kor:pipeline>", "exec"), g)
    if redirect:
        S.uninstall()
    return g


def main():
    if sha(PREREG) != json.loads(FREEZE.read_text())["sha256"]:
        sys.exit("AVBRYTER: den faktoriella forregistreringen har andrats efter frysningen.")
    if not sha(V2 / "tools/h0_v3_kor.py").startswith(KANON_SHA):
        sys.exit("AVBRYTER: tools/h0_v3_kor.py ar inte den frysta filen.")
    import h0_v3_window2_kor as W

    fonster = {
        "W1_2014_2019": dict(
            prereg=V2 / "research_k/h1419_exakt_h0_preregistration_v2.json",
            freeze=V2 / "research_k/H1419_PREREG_FREEZE_V2.json",
            isin=None, redirect=None, fryst=0.2661, n_paneler=79),
        "W2_2020_2026": dict(
            prereg=V2 / "research_k/h0_v3_window2/preregistration.json",
            freeze=V2 / "research_k/h0_v3_window2/PREREG_FREEZE.json",
            isin=W.bygg_isin_hint(),
            redirect={str(W.PRICES_W1): str(W.PRICES_W2)},
            fryst=0.1299, n_paneler=86),
    }
    ut = {"version": "H0_V3_PORTFOLIO_FACTORIAL_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "prereg_sha256": sha(PREREG), "h0_v3_kor_sha256": sha(V2 / "tools/h0_v3_kor.py"),
          "fonster": {}}

    for wn, cfg in fonster.items():
        import h0_v3_kor as H
        isin = cfg["isin"] if cfg["isin"] is not None else H._ISIN
        NS = bygg(cfg["prereg"], cfg["freeze"], isin, cfg["redirect"])
        assert len(NS["paneler"]) == cfg["n_paneler"], f"{wn}: panelantalet avviker"
        res, serier = {}, {}
        for e, v, f, t in armar():
            nets, mn, mk = kor_arm(NS, e, v, f, t)
            key = f"{e}|{v}|{'FR' if f else 'noFR'}|{t}"
            res[key] = {**stat(nets), "medelinnehav": round(mn, 3), "medelkassa": round(mk, 5)}
            serier[key] = [round(float(x), 8) for x in nets]
        champ = "E1|invvol1.5|FR|legacy"
        avv = abs(res[champ]["cagr"] - cfg["fryst"])
        print(f"{wn}: championarm {res[champ]['cagr']:.4%} mot fryst {cfg['fryst']:.4%}  avvikelse {avv:.6f}")
        if avv >= 1e-4:
            sys.exit(f"STOPP: reproduktionsgaten faller i {wn}. Ingen faktoriell analys rapporteras.")
        ut["fonster"][wn] = {"n_paneler": len(NS["paneler"]), "n_armar": len(res),
                             "reproduktionsgate": "PASS", "champion_cagr": res[champ]["cagr"],
                             "fryst_cagr": cfg["fryst"], "armar": res}
        (UT / f"nettoserier_{wn}.json").write_text(json.dumps(serier, indent=1))
    (UT / "results.json").write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    print("skrivet:", UT / "results.json")


if __name__ == "__main__":
    main()
