"""Spar C, steg 2a: feature registry (CORE) + CORE-panelbygge.

CORE = enbart Spar A (pris/volym). Overlevnadssaker per definition, eftersom
Spar A:s VALIDATED-serier redan ar det (se manifest_sparA.json).

Varje feature racknas UTESLUTANDE med data daterat <= panel_date (PIT by
construction - ingen efterhandskontroll kan hitta lackage har eftersom
rullande fonster byggs fran ett index skuret vid panel_date). Ingen
imputering, ingen winsorisering - saknad lookback-historik ger null, aldrig
ett pahittat varde.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

V2 = Path("/home/hannesb/momentum_v2")
PRICES = V2 / "validated/prices/prices_validated.json"
PANELS = V2 / "panels"
REGISTRY = V2 / "docs/probes/feature_registry.json"
CORE_PANEL = PANELS / "core_panel.json"

REBALANCE_WEEKS = 4
UNIVERSUM_START = date(2020, 1, 1)

CORE_REGISTRY = [
    {"id": "mom_4w", "lager": "CORE", "kalla": "adj",
     "formel": "adj[T]/adj[T-4v] - 1", "lookback_veckor": 4,
     "hypotes": "Kortsiktig prismomentum — nyligen stigande pris tenderar fortsätta kort sikt.",
     "missing": "null om <4v historik finns före T."},
    {"id": "mom_13w", "lager": "CORE", "kalla": "adj",
     "formel": "adj[T]/adj[T-13v] - 1", "lookback_veckor": 13,
     "hypotes": "Medelfristig momentum (ett kvartal).",
     "missing": "null om <13v historik finns före T."},
    {"id": "mom_26w", "lager": "CORE", "kalla": "adj",
     "formel": "adj[T]/adj[T-26v] - 1", "lookback_veckor": 26,
     "hypotes": "Halvårsmomentum.",
     "missing": "null om <26v historik finns före T."},
    {"id": "mom_52w", "lager": "CORE", "kalla": "adj",
     "formel": "adj[T]/adj[T-52v] - 1", "lookback_veckor": 52,
     "hypotes": "Standardmomentumfaktorns fulla fönster (Jegadeesh/Titman-traditionen).",
     "missing": "null om <52v historik finns före T."},
    {"id": "mom_12_1", "lager": "CORE", "kalla": "adj",
     "formel": "adj[T-4v]/adj[T-52v] - 1", "lookback_veckor": 52,
     "hypotes": "12-månadersmomentum EXKLUSIVE senaste månaden — undviker kortsiktig "
               "reverseringseffekt, klassisk faktordefinition.",
     "missing": "null om <52v historik finns före T."},
    {"id": "vol_13w", "lager": "CORE", "kalla": "adj (veckoavkastningar)",
     "formel": "std(veckoavkastningar) över trailing 13v", "lookback_veckor": 13,
     "hypotes": "Realiserad volatilitet — lågvolatilitetsanomalin / riskkontroll.",
     "missing": "null om <13v (≥8v krav för stabil std) historik."},
    {"id": "vol_52w", "lager": "CORE", "kalla": "adj (veckoavkastningar)",
     "formel": "std(veckoavkastningar) över trailing 52v", "lookback_veckor": 52,
     "hypotes": "Långsiktig realiserad volatilitet.",
     "missing": "null om <52v (≥26v krav) historik."},
    {"id": "price_vs_sma26w", "lager": "CORE", "kalla": "adj",
     "formel": "adj[T] / mean(adj, trailing 26v) - 1", "lookback_veckor": 26,
     "hypotes": "Trendföljning — avstånd till glidande medelvärde.",
     "missing": "null om <26v historik."},
    {"id": "price_vs_sma52w", "lager": "CORE", "kalla": "adj",
     "formel": "adj[T] / mean(adj, trailing 52v) - 1", "lookback_veckor": 52,
     "hypotes": "Långsiktig trendföljning.",
     "missing": "null om <52v historik."},
    {"id": "high52w_ratio", "lager": "CORE", "kalla": "adj",
     "formel": "adj[T] / max(adj, trailing 52v)", "lookback_veckor": 52,
     "hypotes": "Närhet till 52-veckorshögsta — dokumenterad momentum-/ankareffekt.",
     "missing": "null om <52v historik."},
    {"id": "low52w_ratio", "lager": "CORE", "kalla": "adj",
     "formel": "adj[T] / min(adj, trailing 52v)", "lookback_veckor": 52,
     "hypotes": "Avstånd till 52-veckorslägsta.",
     "missing": "null om <52v historik."},
    {"id": "turnover_13w_msek", "lager": "CORE", "kalla": "adj, v",
     "formel": "mean(adj_dag * volym_dag, trailing 13v) / 1e6", "lookback_veckor": 13,
     "hypotes": "Likviditetsproxy (genomsnittlig daglig omsättning i MSEK) — påverkar "
               "handelsbarhet och kan användas som filter/kontroll, inte alfa i sig.",
     "missing": "null om <13v historik."},
    {"id": "volume_trend_13w", "lager": "CORE", "kalla": "v",
     "formel": "mean(volym, senaste 4v) / mean(volym, föregående 9v) - 1",
     "lookback_veckor": 13,
     "hypotes": "Volymmomentum — ökande handelsintresse föregår ofta prisrörelse.",
     "missing": "null om <13v historik."},
]


def d(s: str) -> date:
    return date.fromisoformat(s[:10])


def panelkalender(första: date, sista: date, steg_veckor: int) -> list:
    off = (4 - första.weekday()) % 7
    start = första + timedelta(days=off)
    ut, cur = [], start
    while cur <= sista:
        ut.append(cur)
        cur += timedelta(weeks=steg_veckor)
    return ut


def main() -> None:  # noqa: C901
    PANELS.mkdir(parents=True, exist_ok=True)
    priser = json.loads(PRICES.read_text(encoding="utf-8"))
    källhash = hashlib.sha256(PRICES.read_bytes()).hexdigest()

    sista_global = max(d(rader[-1]["d"]) for rader in priser.values())
    panel_datum = panelkalender(UNIVERSUM_START, sista_global, REBALANCE_WEEKS)
    print(f"[core] panelkalender: {len(panel_datum)} datum {panel_datum[0]}–{panel_datum[-1]}")

    alla_rader = []
    for i, (kod, rader) in enumerate(priser.items()):
        df = pd.DataFrame(rader)
        df["d"] = pd.to_datetime(df["d"])
        df = df.set_index("d").sort_index()
        # daglig serie -> veckovis avkastning för volatilitetsmåtten (fredagsvärden)
        wk = df["adj"].resample("W-FRI").last().dropna()
        wk_ret = wk.pct_change()

        serie_start, serie_slut = df.index.min().date(), df.index.max().date()
        for pd_ in panel_datum:
            if pd_ < serie_start or pd_ > serie_slut:
                continue
            asof = df.loc[:pd_.isoformat()]
            if asof.empty:
                continue
            t0 = asof.index[-1]
            a0 = asof["adj"].iloc[-1]

            def vid(veckor):
                mål = pd.Timestamp(pd_) - pd.Timedelta(weeks=veckor)
                sub = asof.loc[:mål]
                # tolerans mäts mot MÅLDATUMET (mål), inte mot dagens datum (t0) -
                # annars godkänns i praktiken vilket historiskt pris som helst
                return (sub["adj"].iloc[-1], sub.index[-1]) if not sub.empty and \
                    (mål - sub.index[-1]).days <= 10 else (None, None)

            rad = {"kod": kod, "panel_date": pd_.isoformat(), "price_date": t0.date().isoformat()}

            a4, _ = vid(4)
            rad["mom_4w"] = (a0 / a4 - 1) if a4 else None
            a13, _ = vid(13)
            rad["mom_13w"] = (a0 / a13 - 1) if a13 else None
            a26, _ = vid(26)
            rad["mom_26w"] = (a0 / a26 - 1) if a26 else None
            a52, t52 = vid(52)
            rad["mom_52w"] = (a0 / a52 - 1) if a52 else None
            rad["mom_12_1"] = (a4 / a52 - 1) if (a4 and a52) else None

            wk_asof = wk_ret.loc[:pd_.isoformat()]
            w13 = wk_asof.tail(13)
            rad["vol_13w"] = float(w13.std()) if len(w13) >= 8 else None
            w52 = wk_asof.tail(52)
            rad["vol_52w"] = float(w52.std()) if len(w52) >= 26 else None

            win26 = asof["adj"].loc[(pd.Timestamp(pd_) - pd.Timedelta(weeks=26)):]
            rad["price_vs_sma26w"] = (a0 / win26.mean() - 1) if len(win26) >= 100 else None
            win52 = asof["adj"].loc[(pd.Timestamp(pd_) - pd.Timedelta(weeks=52)):]
            if len(win52) >= 200:
                rad["price_vs_sma52w"] = a0 / win52.mean() - 1
                rad["high52w_ratio"] = a0 / win52.max()
                rad["low52w_ratio"] = a0 / win52.min()
            else:
                rad["price_vs_sma52w"] = rad["high52w_ratio"] = rad["low52w_ratio"] = None

            win13 = asof.loc[(pd.Timestamp(pd_) - pd.Timedelta(weeks=13)):]
            if len(win13) >= 50:
                rad["turnover_13w_msek"] = float((win13["adj"] * win13["v"]).mean() / 1e6)
                vol_sen = asof["v"].loc[(pd.Timestamp(pd_) - pd.Timedelta(weeks=4)):]
                vol_för = asof["v"].loc[(pd.Timestamp(pd_) - pd.Timedelta(weeks=13)):
                                        (pd.Timestamp(pd_) - pd.Timedelta(weeks=4))]
                rad["volume_trend_13w"] = (float(vol_sen.mean() / vol_för.mean() - 1)
                                           if len(vol_för) >= 20 and vol_för.mean() > 0 else None)
            else:
                rad["turnover_13w_msek"] = rad["volume_trend_13w"] = None

            alla_rader.append(rad)
        if (i + 1) % 100 == 0:
            print(f"  [{i+1}/{len(priser)}] instrument klara", flush=True)

    CORE_PANEL.write_text(json.dumps(alla_rader, ensure_ascii=False, separators=(",", ":")),
                          encoding="utf-8")
    kanon = json.dumps(sorted(alla_rader, key=lambda r: (r["kod"], r["panel_date"])),
                       sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    panelhash = hashlib.sha256(kanon.encode()).hexdigest()
    print(f"\n[core] {len(alla_rader)} rader, {len({r['kod'] for r in alla_rader})} instrument")
    print(f"[core] core_panel_sha256: {panelhash}")

    REGISTRY.write_text(json.dumps({"CORE": CORE_REGISTRY}, indent=1, ensure_ascii=False),
                        encoding="utf-8")
    print(f"[core] registry: {len(CORE_REGISTRY)} features -> {REGISTRY}")

    (V2 / "docs/probes/core_panel_build.json").write_text(json.dumps({
        "kalla_prices_sha256": källhash, "n_rader": len(alla_rader),
        "n_instrument": len({r["kod"] for r in alla_rader}),
        "n_features": len(CORE_REGISTRY), "core_panel_sha256": panelhash,
        "panel_datum": [x.isoformat() for x in panel_datum],
    }, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
