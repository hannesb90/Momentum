"""Spar C v2: CORE-panelen, utokad enligt feature blueprint (docs/probes/
feature_blueprint.json). Ersatter forsta CORE-bygget (samma 13 ursprungliga
falt + 13 nya = 26 CORE-falt).

Bygger forst ett INTERNT likaviktat index (PIT-dynamisk medlemskap, enbart
Spar A) som grund for relativa/beta-/regimmatt - se blueprint-posten
'egenbyggt_likaviktat_index'.
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
INDEX_SERIES = V2 / "docs/probes/internal_index_series.json"
MEMBERSHIP = V2 / "validated/membership_main_list_pit.json"

REBALANCE_WEEKS = 4
UNIVERSUM_START = date(2020, 1, 1)
MAX_PRICE_LAG_CALENDAR_DAYS = 8

CORE_REGISTRY = [
    {"id": "mom_4w", "formel": "adj[T]/adj[T-4v]-1", "lookback_veckor": 4,
     "hypotes": "Kortsiktig prismomentum."},
    {"id": "mom_13w", "formel": "adj[T]/adj[T-13v]-1", "lookback_veckor": 13,
     "hypotes": "Medelfristig momentum."},
    {"id": "mom_26w", "formel": "adj[T]/adj[T-26v]-1", "lookback_veckor": 26,
     "hypotes": "Halvårsmomentum."},
    {"id": "mom_52w", "formel": "adj[T]/adj[T-52v]-1", "lookback_veckor": 52,
     "hypotes": "Standard 12-månadersmomentum."},
    {"id": "mom_12_1", "formel": "adj[T-4v]/adj[T-52v]-1", "lookback_veckor": 52,
     "hypotes": "12-1-momentum, undviker kortsiktig reversering."},
    {"id": "mom_relative_index_52w", "formel": "mom_52w[instrument]-mom_52w[index]",
     "lookback_veckor": 52, "hypotes": "Momentum relativt egenbyggt likaviktat marknadsindex."},
    {"id": "residual_momentum_52w", "formel": "kumulativ residual (ret-beta*index_ret), 52v",
     "lookback_veckor": 52, "hypotes": "Momentum i avkastning ej förklarad av marknadsexponering."},
    {"id": "trend_strength_52w", "formel": "t-stat, OLS(log(adj)~tid), 52v",
     "lookback_veckor": 52, "hypotes": "Trendens statistiska styrka/konsekvens."},
    {"id": "trend_consistency_52w", "formel": "andel positiva veckor, 52v",
     "lookback_veckor": 52, "hypotes": "Robust mot enskilda extremveckor."},
    {"id": "momentum_acceleration_13w", "formel": "mom_13w[T]-mom_13w[T-13v]",
     "lookback_veckor": 26, "hypotes": "Accelererar/bromsar momentumet."},
    {"id": "reversal_1w", "formel": "-(adj[T]/adj[T-1v]-1)", "lookback_veckor": 1,
     "hypotes": "Kortsiktig överreaktion, motsatt riktning mot momentum."},
    {"id": "vol_13w", "formel": "std(veckoavkastningar,13v)", "lookback_veckor": 13,
     "hypotes": "Realiserad volatilitet, medelfristig."},
    {"id": "vol_52w", "formel": "std(veckoavkastningar,52v)", "lookback_veckor": 52,
     "hypotes": "Realiserad volatilitet, långsiktig."},
    {"id": "downside_vol_52w", "formel": "std(negativa veckoavkastningar,52v)",
     "lookback_veckor": 52, "hypotes": "Semi-deviation — bara nedsidan bestraffas."},
    {"id": "beta_52w", "formel": "cov(ret,index_ret)/var(index_ret), 52v",
     "lookback_veckor": 52, "hypotes": "Systematisk marknadsexponering."},
    {"id": "idio_vol_52w", "formel": "std(residualer från marknadsmodell), 52v",
     "lookback_veckor": 52, "hypotes": "Bolagsspecifik volatilitet efter beta."},
    {"id": "skew_52w", "formel": "skewness(veckoavkastningar,52v)", "lookback_veckor": 52,
     "hypotes": "Asymmetri i avkastningsfördelningen."},
    {"id": "kurtosis_52w", "formel": "excess kurtosis(veckoavkastningar,52v)",
     "lookback_veckor": 52, "hypotes": "Svansmassa/tail risk."},
    {"id": "price_vs_sma26w", "formel": "adj[T]/mean(adj,26v)-1", "lookback_veckor": 26,
     "hypotes": "Trendföljning."},
    {"id": "price_vs_sma52w", "formel": "adj[T]/mean(adj,52v)-1", "lookback_veckor": 52,
     "hypotes": "Långsiktig trendföljning."},
    {"id": "high52w_ratio", "formel": "adj[T]/max(adj,52v)", "lookback_veckor": 52,
     "hypotes": "Närhet till 52v-högsta."},
    {"id": "low52w_ratio", "formel": "adj[T]/min(adj,52v)", "lookback_veckor": 52,
     "hypotes": "Avstånd till 52v-lägsta."},
    {"id": "drawdown_current_104w", "formel": "adj[T]/max(adj,104v)-1", "lookback_veckor": 104,
     "hypotes": "Aktuell nedgång från topp, bredare fönster."},
    {"id": "max_drawdown_52w", "formel": "min(adj[t]/running_max(adj)-1), 52v",
     "lookback_veckor": 52, "hypotes": "Värsta realiserade nedgången i fönstret."},
    {"id": "risk_adj_momentum_52w", "formel": "mom_52w/vol_52w", "lookback_veckor": 52,
     "hypotes": "Momentum per riskenhet."},
    {"id": "turnover_13w_msek", "formel": "UTESLUTEN: kräver QA-godkänt faktiskt ojusterat handelspris", "lookback_veckor": 13,
     "status": "UTESLUTEN", "hypotes": "Likviditetsproxy."},
    {"id": "volume_trend_13w", "formel": "mean(v,4v)/mean(v,föreg.9v)-1", "lookback_veckor": 13,
     "hypotes": "Volymmomentum."},
    {"id": "illiquidity_amihud_13w", "formel": "UTESLUTEN: kräver QA-godkänt faktiskt ojusterat handelspris", "lookback_veckor": 13,
     "status": "UTESLUTEN", "hypotes": "Amihud illikviditet."},
    {"id": "rank_mom_52w_pct", "formel": "percentilrang av mom_52w, samma panel_date",
     "lookback_veckor": 0, "hypotes": "Tvärsnittsrang, robust för rankingmodeller."},
    {"id": "market_regime_trend", "formel": "index[T]/SMA(index,26v)-1", "lookback_veckor": 26,
     "hypotes": "Marknadstrend, kontext-feature."},
    {"id": "market_regime_vol", "formel": "std(index veckoavkastningar,13v)", "lookback_veckor": 13,
     "hypotes": "Marknadsvolatilitetsregim."},
]
for f in CORE_REGISTRY:
    f["lager"] = "CORE"
    f["kalla"] = "adj, v (Spår A)" if "index" not in f["formel"] else "adj, v (Spår A) + internt index"
    f.setdefault("missing", "null vid otillräcklig lookback-historik, aldrig imputerat")


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


def bygg_index(priser: dict, membership: dict) -> pd.Series:
    """Likaviktat index: medelvärde av veckoavkastningar over PIT-dynamiskt
    noterade instrument (bara de som faktiskt har pris den veckan)."""
    veckoserier = {}
    for kod, rader in priser.items():
        s = pd.Series({r["d"]: r["adj"] for r in rader})
        s.index = pd.to_datetime(s.index)
        mem = membership[kod]
        lo = mem.get("member_from") if mem.get("membership_verified") else mem["observation_window_from"]
        hi = mem.get("member_to")
        s = s.loc[lo:hi] if hi else s.loc[lo:]
        wk = s.resample("W-FRI").last().dropna()
        veckoserier[kod] = wk.pct_change()
    df = pd.DataFrame(veckoserier)
    index_ret = df.mean(axis=1, skipna=True)          # likaviktat, PIT-dynamiskt (NaN ignoreras)
    return index_ret.dropna()


def main() -> None:  # noqa: C901
    PANELS.mkdir(parents=True, exist_ok=True)
    priser = json.loads(PRICES.read_text(encoding="utf-8"))
    membership_rows = json.loads(MEMBERSHIP.read_text(encoding="utf-8"))["rows"]
    membership = {r["kod"]: r for r in membership_rows}
    if set(priser) != set(membership):
        raise RuntimeError("membership ledger and price universe differ")
    källhash = hashlib.sha256(PRICES.read_bytes()).hexdigest()

    print("[core v2] bygger internt likaviktat index …")
    index_ret = bygg_index(priser, membership)
    (INDEX_SERIES).write_text(
        json.dumps({str(k.date()): float(v) for k, v in index_ret.items()},
                  indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"[core v2] index: {len(index_ret)} veckor, "
          f"{index_ret.index.min().date()}–{index_ret.index.max().date()}")

    sista_global = max(d(rader[-1]["d"]) for rader in priser.values())
    panel_datum = panelkalender(UNIVERSUM_START, sista_global, REBALANCE_WEEKS)
    print(f"[core v2] panelkalender: {len(panel_datum)} datum")

    # marknadsregim beräknas EN gång (samma värde för alla instrument per panel_date)
    regim = {}
    for pd_ in panel_datum:
        asof = index_ret.loc[:pd_.isoformat()]
        w26 = asof.tail(26)
        w13 = asof.tail(13)
        idx_niva = (1 + asof).cumprod()
        trend = (idx_niva.iloc[-1] / idx_niva.tail(26).mean() - 1) if len(w26) >= 15 else None
        volr = float(w13.std()) if len(w13) >= 8 else None
        regim[pd_.isoformat()] = {"market_regime_trend": trend, "market_regime_vol": volr}

    alla_rader = []
    for i, (kod, rader) in enumerate(priser.items()):
        df = pd.DataFrame(rader)
        df["d"] = pd.to_datetime(df["d"])
        df = df.set_index("d").sort_index()
        wk = df["adj"].resample("W-FRI").last().dropna()
        wk_ret = wk.pct_change()

        mem = membership[kod]
        effective_from = mem.get("member_from") if mem.get("membership_verified") else mem["observation_window_from"]
        mem_from = d(effective_from)
        mem_to = d(mem["member_to"]) if mem.get("member_to") else None
        serie_start, serie_slut = max(df.index.min().date(), mem_from), df.index.max().date()
        if mem_to:
            serie_slut = min(serie_slut, mem_to)
        for pd_ in panel_datum:
            if pd_ < serie_start or pd_ > serie_slut:
                continue
            asof = df.loc[:pd_.isoformat()]
            if asof.empty:
                continue
            t0 = asof.index[-1]
            if (pd.Timestamp(pd_) - t0).days > MAX_PRICE_LAG_CALENDAR_DAYS:
                continue
            a0 = asof["adj"].iloc[-1]

            def vid(veckor):
                mål = pd.Timestamp(pd_) - pd.Timedelta(weeks=veckor)
                sub = asof.loc[:mål]
                return (sub["adj"].iloc[-1], sub.index[-1]) if not sub.empty and \
                    (mål - sub.index[-1]).days <= 10 else (None, None)

            rad = {"kod": kod, "panel_date": pd_.isoformat(), "price_date": t0.date().isoformat(),
                   "membership_verified": bool(mem.get("membership_verified")),
                   "membership_basis": mem["basis"]}

            a4, _ = vid(4)
            rad["mom_4w"] = (a0 / a4 - 1) if a4 else None
            a13, _ = vid(13)
            rad["mom_13w"] = (a0 / a13 - 1) if a13 else None
            a26, _ = vid(26)
            rad["mom_26w"] = (a0 / a26 - 1) if a26 else None
            a52, _ = vid(52)
            rad["mom_52w"] = (a0 / a52 - 1) if a52 else None
            rad["mom_12_1"] = (a4 / a52 - 1) if (a4 and a52) else None
            rad["reversal_1w"] = -(a0 / vid(1)[0] - 1) if vid(1)[0] else None

            wk_asof = wk_ret.loc[:pd_.isoformat()]
            w13 = wk_asof.tail(13)
            rad["vol_13w"] = float(w13.std()) if len(w13) >= 8 else None
            w52 = wk_asof.tail(52)
            rad["vol_52w"] = float(w52.std()) if len(w52) >= 26 else None
            neg52 = w52[w52 < 0]
            rad["downside_vol_52w"] = float(neg52.std()) if len(neg52) >= 10 else None
            rad["skew_52w"] = float(w52.skew()) if len(w52) >= 26 else None
            rad["kurtosis_52w"] = float(w52.kurt()) if len(w52) >= 26 else None

            # momentum-acceleration: mom_13w nu mot mom_13w 13v tidigare
            a13_prior, _ = (None, None)
            målp = pd.Timestamp(pd_) - pd.Timedelta(weeks=13)
            subp = asof.loc[:målp]
            if not subp.empty and (målp - subp.index[-1]).days <= 10:
                t0p, a0p = subp.index[-1], subp["adj"].iloc[-1]
                subp26 = asof.loc[:(målp - pd.Timedelta(weeks=13))]
                if not subp26.empty and \
                        ((målp - pd.Timedelta(weeks=13)) - subp26.index[-1]).days <= 10:
                    a13_prior = a0p / subp26["adj"].iloc[-1] - 1
            rad["momentum_acceleration_13w"] = ((rad["mom_13w"] - a13_prior)
                                                if (rad["mom_13w"] is not None and
                                                    a13_prior is not None) else None)

            win26 = asof["adj"].loc[(pd.Timestamp(pd_) - pd.Timedelta(weeks=26)):]
            rad["price_vs_sma26w"] = (a0 / win26.mean() - 1) if len(win26) >= 100 else None

            # C-3 (CODEX_SECOND_OPINION_V2_ABC.md): trend_strength_52w/
            # trend_consistency_52w beraknades tidigare fran win26 (26 veckor)
            # trots namn, registry och formel ("52v"). Flyttat till win52,
            # samma 200-dagars tackningskrav som ovriga 52v-falt nedan.
            win52 = asof["adj"].loc[(pd.Timestamp(pd_) - pd.Timedelta(weeks=52)):]
            trend_ok = len(win52) >= 200
            if trend_ok:
                x = np.arange(len(win52))
                y = np.log(win52.values)
                slope, intercept = np.polyfit(x, y, 1)
                resid = y - (slope * x + intercept)
                se = np.sqrt(np.sum(resid ** 2) / (len(x) - 2)) / np.sqrt(np.sum((x - x.mean()) ** 2))
                rad["trend_strength_52w"] = float(slope / se) if se > 0 else None
                rad["trend_consistency_52w"] = float((win52.pct_change().dropna() > 0).mean())
            else:
                rad["trend_strength_52w"] = rad["trend_consistency_52w"] = None

            if trend_ok:
                rad["price_vs_sma52w"] = a0 / win52.mean() - 1
                rad["high52w_ratio"] = a0 / win52.max()
                rad["low52w_ratio"] = a0 / win52.min()
                run_max = win52.cummax()
                rad["max_drawdown_52w"] = float((win52 / run_max - 1).min())
                rad["risk_adj_momentum_52w"] = (rad["mom_52w"] / rad["vol_52w"]) \
                    if (rad["mom_52w"] is not None and rad["vol_52w"]) else None
            else:
                rad["price_vs_sma52w"] = rad["high52w_ratio"] = rad["low52w_ratio"] = None
                rad["max_drawdown_52w"] = rad["risk_adj_momentum_52w"] = None

            win104 = asof["adj"].loc[(pd.Timestamp(pd_) - pd.Timedelta(weeks=104)):]
            rad["drawdown_current_104w"] = (a0 / win104.max() - 1) if len(win104) >= 200 else None

            win13 = asof.loc[(pd.Timestamp(pd_) - pd.Timedelta(weeks=13)):]
            if len(win13) >= 50:
                # EODHD's historical `close` is not demonstrably an unadjusted
                # transaction price for every corporate-action chain (FLERIE is
                # a concrete counterexample). Monetary price×volume features are
                # therefore excluded, never approximated with adjusted_close.
                rad["turnover_13w_msek"] = None
                rad["illiquidity_amihud_13w"] = None
                vol_sen = asof["v"].loc[(pd.Timestamp(pd_) - pd.Timedelta(weeks=4)):]
                vol_för = asof["v"].loc[(pd.Timestamp(pd_) - pd.Timedelta(weeks=13)):
                                        (pd.Timestamp(pd_) - pd.Timedelta(weeks=4))]
                rad["volume_trend_13w"] = (float(vol_sen.mean() / vol_för.mean() - 1)
                                           if len(vol_för) >= 20 and vol_för.mean() > 0 else None)
            else:
                rad["turnover_13w_msek"] = rad["illiquidity_amihud_13w"] = None
                rad["volume_trend_13w"] = None

            # index-beroende: beta, idio_vol, residual momentum, relativt momentum
            idx_asof = index_ret.loc[:pd_.isoformat()].tail(52)
            gemensam = wk_asof.tail(52).index.intersection(idx_asof.index)
            if len(gemensam) >= 26:
                sr, ir = wk_asof.loc[gemensam], idx_asof.loc[gemensam]
                var_i = ir.var()
                beta = float(sr.cov(ir) / var_i) if var_i > 0 else None
                rad["beta_52w"] = beta
                if beta is not None:
                    resid = sr - beta * ir
                    rad["idio_vol_52w"] = float(resid.std())
                    rad["residual_momentum_52w"] = float((1 + resid).prod() - 1)
                else:
                    rad["idio_vol_52w"] = rad["residual_momentum_52w"] = None
                idx_mom_52w = float((1 + ir).prod() - 1)
                rad["mom_relative_index_52w"] = (rad["mom_52w"] - idx_mom_52w) \
                    if rad["mom_52w"] is not None else None
            else:
                rad["beta_52w"] = rad["idio_vol_52w"] = None
                rad["residual_momentum_52w"] = rad["mom_relative_index_52w"] = None

            r = regim.get(pd_.isoformat(), {})
            rad["market_regime_trend"] = r.get("market_regime_trend")
            rad["market_regime_vol"] = r.get("market_regime_vol")

            alla_rader.append(rad)
        if (i + 1) % 100 == 0:
            print(f"  [{i+1}/{len(priser)}] instrument klara", flush=True)

    # -------- cross-sectional: rank_mom_52w_pct, per panel_date -------------
    df_alla = pd.DataFrame(alla_rader)
    df_alla["rank_mom_52w_pct"] = df_alla.groupby("panel_date")["mom_52w"] \
        .transform(lambda s: s.rank(pct=True) if s.notna().sum() >= 5 else np.nan)
    alla_rader = df_alla.to_dict("records")
    for r in alla_rader:
        for k, v in list(r.items()):
            if isinstance(v, float) and np.isnan(v):
                r[k] = None

    CORE_PANEL.write_text(json.dumps(alla_rader, ensure_ascii=False, separators=(",", ":")),
                          encoding="utf-8")
    print(f"\n[core v2] {len(alla_rader)} rader, {len({r['kod'] for r in alla_rader})} instrument, "
          f"{len(CORE_REGISTRY)} features")

    reg = {"CORE": CORE_REGISTRY}
    if REGISTRY.exists():
        gammal = json.loads(REGISTRY.read_text(encoding="utf-8"))
        reg["FUNDAMENTA"] = gammal.get("FUNDAMENTA", [])
    REGISTRY.write_text(json.dumps(reg, indent=1, ensure_ascii=False), encoding="utf-8")

    (V2 / "docs/probes/core_panel_build_v2.json").write_text(json.dumps({
        "kalla_prices_sha256": källhash, "n_rader": len(alla_rader),
        "n_instrument": len({r["kod"] for r in alla_rader}), "n_features": len(CORE_REGISTRY),
        "index_veckor": len(index_ret),
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"artefakt: {CORE_PANEL}")


if __name__ == "__main__":
    main()
