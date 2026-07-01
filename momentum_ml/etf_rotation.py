"""
etf_rotation.py – D-spåret: dual-momentum sektor-ETF-rotation ("trend, inte bolag").

Rankar sektor-ETF:ernas EGNA kurser (till skillnad från backtest/sector_momentum.py
som härleder sektor-styrka från svenska aktier). Strategin (Antonacci dual momentum):
  1. RELATIV momentum – ranka ETF:erna på sammanvägd avkastning, håll de hetaste K.
  2. ABSOLUT momentum – håll en ETF bara om dess EGEN 52v-trend är positiv; annars
     går slotten till ett defensivt ben (lågvol/utdelning eller kontanter).
  → fångar heta sektorer tidigt OCH går i skydd när inget trendar (2022-typ).

Till skillnad från kvalitets-screenern är detta ÄRLIGT BACKTESTBART: rena ETF-kurser,
ingen survivorship-bias på sektornivå, mekanisk regel utan LLM/look-ahead.

Körs på Pi:n (molncontainern når inte Yahoo):
    python etf_rotation.py signal      # dagens rotation: vilka ETF:er hålls nu + flöde
    python etf_rotation.py backtest    # strategin vs index & köp-och-behåll
    python etf_rotation.py flow        # ren flödesvy (rank-förändring per sektor)
"""
import sys
import csv
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import config


# ── Universum ─────────────────────────────────────────────────────────────────
def _load_universe():
    """Kurerat globalt tema/region/sektor-universum (data/rotation_universe.csv) om
    det finns, annars fallback till sector_etfs.csv filtrerat på region.
    Returnerar [(ticker, grupp-etikett, namn)]."""
    uf = Path(__file__).parent / getattr(config, "ETF_ROT_UNIVERSE_FILE", "")
    if getattr(config, "ETF_ROT_UNIVERSE_FILE", "") and uf.exists():
        out = []
        with open(uf, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                out.append((row["ticker"], row.get("group") or row.get("kind") or "?", row["name"]))
        return out
    region = config.ETF_ROT_REGION
    want = {"EU": {"EU"}, "US": {"US-UCITS"}, "ALL": {"EU", "US-UCITS"}}.get(region, {"EU"})
    out = []
    with open(Path(__file__).parent / "data" / "sector_etfs.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("region") in want:
                out.append((row["ticker"], row["sector"], row["name"]))
    return out


def _panel(tickers):
    """Prispanel (veckoslut × tickers) från Yahoo, justerade stängningskurser."""
    from data.data_loader import fetch_weekly_data
    data = fetch_weekly_data(tickers, use_cache=True)
    cols = {t: d["Close"] for t, d in data.items() if d is not None and not d["Close"].dropna().empty}
    panel = pd.DataFrame(cols).sort_index()
    panel.index = pd.to_datetime(panel.index)
    return panel.ffill(limit=1)   # olika börskalendrar (.DE/.L) → jämna ut enstaka glapp


def _scores(panel, etfs):
    """Sammanvägd relativ momentum + absolut 52v-momentum, per datum × ETF."""
    px = panel[etfs]
    rel = sum(px / px.shift(w) - 1 for w in config.ETF_ROT_MOM_WINDOWS) / len(config.ETF_ROT_MOM_WINDOWS)
    absm = px / px.shift(config.ETF_ROT_ABS_WINDOW) - 1
    return rel, absm


def _sector_breadth():
    """Global sektor-bredd (bekräftelse-lager, EJ svenska aktier): för varje GICS-
    sektor, hur står sig EU- OCH US-versionen av sektor-ETF:en? Båda upp = globalt
    bekräftad trend; splittrat = varning. Returnerar sector -> {mom, up, total}."""
    pairs = {}
    with open(Path(__file__).parent / "data" / "sector_etfs.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            pairs.setdefault(row["sector"], []).append(row["ticker"])
    tickers = [t for ts in pairs.values() for t in ts]
    if not tickers:
        return {}
    panel = _panel(tickers)
    win, absw, amin = config.ETF_ROT_MOM_WINDOWS, config.ETF_ROT_ABS_WINDOW, config.ETF_ROT_ABS_MIN
    out = {}
    for sector, ts in pairs.items():
        moms, ups, tot = [], 0, 0
        for t in ts:
            if t not in panel.columns:
                continue
            s = panel[t].dropna()
            if len(s) <= absw:
                continue
            rel = sum(s.iloc[-1] / s.iloc[-1 - w] - 1 for w in win) / len(win)
            absm = s.iloc[-1] / s.iloc[-1 - absw] - 1
            moms.append(rel); tot += 1
            if absm > amin:
                ups += 1
        if moms:
            out[sector] = {"mom": sum(moms) / len(moms), "up": ups, "total": tot}
    return out


def _volume_flow(tickers):
    """Token-fri kapitalflödes-signal ur dagsfärsk OHLCV (ingen NLP/GPR-index).
    Chaikin Money Flow (13v) = ackumulation (kapital in) vs distribution (ut);
    relativ volym (4v vs 26v) = flaggar när kapitalet RUSAR in (volymspik)."""
    from data.data_loader import fetch_weekly_data
    data = fetch_weekly_data(tickers, use_cache=True)
    out = {}
    need = {"High", "Low", "Close", "Volume"}
    for t, d in data.items():
        if d is None or d.empty or not need.issubset(d.columns):
            continue
        df = d.dropna(subset=list(need)).tail(26)
        if len(df) < 13:
            continue
        hl = (df["High"] - df["Low"]).replace(0, float("nan"))
        mfm = ((df["Close"] - df["Low"]) - (df["High"] - df["Close"])) / hl  # -1..+1
        mfv = mfm.fillna(0.0) * df["Volume"]
        vol13 = float(df["Volume"].tail(13).sum()) or 1.0
        cmf = float(mfv.tail(13).sum()) / vol13
        base = float(df["Volume"].mean()) or 1.0
        relvol = float(df["Volume"].tail(4).mean()) / base
        out[t] = {"cmf": round(cmf, 3), "relvol": round(relvol, 2)}
    return out


def _flow_label(cmf, relvol, rc):
    """Flödesetikett från volym (CMF/relvol); faller tillbaka på rank-förändring."""
    if cmf is None:
        if rc >= 2:
            return "↑ in (rank)"
        if rc <= -2:
            return "↓ ut (rank)"
        return "→ stabil"
    surge = " ⚡" if (relvol and relvol >= 1.3) else ""
    if cmf >= 0.10:
        return f"↑↑ inflöde{surge}"
    if cmf >= 0.03:
        return f"↑ inflöde{surge}"
    if cmf <= -0.10:
        return "↓↓ utflöde"
    if cmf <= -0.03:
        return "↓ utflöde"
    return "→ stabil"


def _regime(panel):
    """Bull/björn per datum = risk-on. Trend (bred marknad över sin långa MA) OCH,
    om makro-overlay är på, INTE i makro-stress (VIX + kreditspread). None om av."""
    if not getattr(config, "ETF_ROT_REGIME_ENABLED", False):
        return None
    t = config.ETF_ROT_REGIME_TICKER
    if t not in panel.columns:
        return None
    ma = panel[t].rolling(config.ETF_ROT_REGIME_MA).mean()
    risk_on = panel[t] > ma
    if getattr(config, "ETF_ROT_MACRO_REGIME", False):
        try:
            from macro_data import stress_series
            stress = stress_series(panel.index)
            if stress is not None:
                risk_on = risk_on & (~stress.astype(bool))   # stress → tvinga risk-off
        except Exception:  # noqa: BLE001 – makro valfritt; trend-only om det fallerar
            pass
    return risk_on


# ── Rotationsbeslut ───────────────────────────────────────────────────────────
def _decide(rel_row, abs_row, k, defensive, abs_min):
    """Top-K på relativ momentum; en ETF utan positiv absolut trend → defensivt ben.
    Returnerar (vikter dict, lista av (ticker, hålls, abs_mom)) för insyn."""
    ranked = rel_row.dropna().sort_values(ascending=False)
    picks, weights = [], {}
    cash = defensive or "_CASH"
    for t in ranked.index[:k]:
        a = abs_row.get(t)
        hold = pd.notna(a) and a > abs_min
        tgt = t if hold else cash
        weights[tgt] = weights.get(tgt, 0.0) + 1.0 / k
        picks.append((t, bool(hold), float(a) if pd.notna(a) else np.nan))
    return weights, picks


# ── Statistik ─────────────────────────────────────────────────────────────────
def _stats(rets: pd.Series):
    rets = rets.dropna()
    if rets.empty:
        return {}
    eq = (1 + rets).cumprod()
    yrs = len(rets) / 52.0
    cagr = eq.iloc[-1] ** (1 / yrs) - 1 if yrs > 0 else np.nan
    vol = rets.std() * np.sqrt(52)
    sharpe = (rets.mean() * 52) / vol if vol > 0 else np.nan
    dd = (eq / eq.cummax() - 1).min()
    return {"total": eq.iloc[-1] - 1, "cagr": cagr, "vol": vol, "sharpe": sharpe, "maxdd": dd}


def _fmt_stats(name, s):
    if not s:
        return f"  {name:<22} (för lite data)"
    return (f"  {name:<22} avk {s['total']:>+7.1%}  CAGR {s['cagr']:>+6.1%}  "
            f"vol {s['vol']:>5.1%}  Sharpe {s['sharpe']:>4.2f}  maxDD {s['maxdd']:>6.1%}")


# ── Backtest ──────────────────────────────────────────────────────────────────
def backtest(always_invested=False):
    uni = _load_universe()
    etfs = [t for t, _, _ in uni]
    defensive = config.ETF_ROT_DEFENSIVE
    bench = config.ETF_ROT_BENCHMARK
    bmarks = [b for b in ([bench] + list(getattr(config, "ETF_ROT_BENCHMARKS_EXTRA", []))) if b]
    extra = [x for x in ([defensive] + bmarks) if x]
    panel = _panel(etfs + extra)
    have = [t for t in etfs if t in panel.columns]
    if len(have) < config.ETF_ROT_TOP_K:
        print(f"[backtest] för få ETF:er med data ({len(have)}) – kolla nätet/tickers.")
        return
    rel, absm = _scores(panel, have)
    regime = None if always_invested else _regime(panel)   # alltid-investerad → ingen kontant
    rets = panel.pct_change()
    k, rebal, abs_min = config.ETF_ROT_TOP_K, config.ETF_ROT_REBAL_WEEKS, config.ETF_ROT_ABS_MIN
    if always_invested:
        abs_min = -1e9    # slå av absolut-filtret → top-3 hålls ALLTID, 100% investerat
    start = max(config.ETF_ROT_ABS_WINDOW, config.ETF_ROT_REGIME_MA) + 1
    if len(panel) <= start + rebal:
        print("[backtest] för kort historik för ETF-universumet.")
        return
    cash = defensive or "_CASH"

    weights, port, riskoff_wk = {}, [], 0
    idx = panel.index[start:]
    for j, i in enumerate(range(start, len(panel))):
        if weights:                                   # veckans avkastning på FÖRRA beslutets vikter
            wr = 0.0
            for t, w in weights.items():
                r = rets.iloc[i].get(t) if t in rets.columns else np.nan
                wr += w * (r if pd.notna(r) else 0.0)  # saknad/kontant slot = 0
            port.append(wr)
        else:
            port.append(0.0)
        if j % rebal == 0:                            # nytt beslut vid stängning i → nästa vecka
            if regime is not None and not bool(regime.iloc[i]):
                weights = {cash: 1.0}                  # BJÖRN → allt defensivt/kontanter
                riskoff_wk += rebal
            else:
                weights, _ = _decide(rel.iloc[i], absm.iloc[i], k, defensive, abs_min)

    port = pd.Series(port, index=idx)
    eqw = rets[have].reindex(idx).mean(axis=1)        # köp-och-behåll, likaviktad hela poolen

    reg_txt = ("ALLTID 100% INVESTERAD (ingen kontant, inget absolut-filter)" if always_invested
               else (f"regim PÅ ({config.ETF_ROT_REGIME_TICKER} vs {config.ETF_ROT_REGIME_MA}v MA)"
                     if regime is not None else "regim AV"))
    mode = "alltid-investerad top-K" if always_invested else "regim-medveten dual momentum"
    print(f"\n  ETF-ROTATION ({mode}) – globalt universum, "
          f"top-{k}, mom {config.ETF_ROT_MOM_WINDOWS}v, ombal var {rebal}v, {len(have)} ETF:er")
    print(f"  Period: {idx[0].date()} – {idx[-1].date()}  ({len(idx)} veckor) · {reg_txt}")
    if regime is not None:
        print(f"  Risk-off (björn → defensivt): {riskoff_wk / len(idx):.0%} av tiden "
              f"(defensivt ben: {defensive or 'kontanter'})")
    print("  (Tematiska ETF:er har kortare historik – valbara först när de fått data.)\n")
    print(_fmt_stats("Rotation (strategi)", _stats(port)))
    print(_fmt_stats("Likaviktad pool (B&H)", _stats(eqw)))
    prim = None
    bench_series = {}
    for b in bmarks:
        if b in rets.columns:
            bs = rets[b].reindex(idx)
            print(_fmt_stats(f"Index {b}", _stats(bs)))
            bench_series[b] = bs
            if prim is None:
                prim = bs
    if prim is not None:   # slå-index-frekvens mot primär benchmark (ACWI)
        roll = (port.rolling(13).apply(lambda x: (1 + x).prod() - 1)
                > prim.rolling(13).apply(lambda x: (1 + x).prod() - 1))
        print(f"\n  Slår {bench} (global) på rullande 13v-fönster: {roll.mean():.0%} av tiden")

    # Konkret: så här hade besparingarna vuxit (samma fönster för alla).
    start = float(getattr(config, "ETF_ROT_START_CAPITAL", 100000))
    def _final(s):
        s = s.dropna()
        return start * float((1 + s).prod()) if len(s) else float("nan")
    print(f"\n  TILLVÄXT AV {start:,.0f} kr ({idx[0].date()} → {idx[-1].date()}):".replace(",", " "))
    print(f"    Rotation (top-{k}):     {_final(port):>14,.0f} kr".replace(",", " "))
    print(f"    Likaviktad pool:       {_final(eqw):>14,.0f} kr".replace(",", " "))
    for b, bs in bench_series.items():
        print(f"    Index {b:<12}     {_final(bs):>14,.0f} kr".replace(",", " "))
    print("\n  (Ombalansering utan transaktionskostnad/skatt. Absolut-filtret + regim = "
          "skydd i björnmarknad; jämför särskilt maxDD, inte bara slutvärdet.)")


# ── Parametersvep med in-sample/OOS-split (mot curve-fitting) ─────────────────
def _sim(panel, rel, absm, rets, have, k, rebal, defensive):
    """Alltid-investerad top-K (ingen regim, inget absolut-filter) → port-avk-serie."""
    start = max(config.ETF_ROT_ABS_WINDOW, config.ETF_ROT_REGIME_MA) + 1
    weights, port = {}, []
    idx = panel.index[start:]
    for j, i in enumerate(range(start, len(panel))):
        wr = 0.0
        for t, w in weights.items():
            r = rets.iloc[i].get(t) if t in rets.columns else None
            if r is not None and pd.notna(r):
                wr += w * r
        port.append(wr)
        if j % rebal == 0:
            weights, _ = _decide(rel.iloc[i], absm.iloc[i], k, defensive, -1e9)
    return pd.Series(port, index=idx)


def sweep():
    uni = _load_universe()
    etfs = [t for t, _, _ in uni]
    defensive = config.ETF_ROT_DEFENSIVE
    bench = config.ETF_ROT_BENCHMARK
    panel = _panel(etfs + [x for x in (defensive, bench) if x])
    have = [t for t in etfs if t in panel.columns]
    rel, absm = _scores(panel, have)
    rets = panel.pct_change()
    start = max(config.ETF_ROT_ABS_WINDOW, config.ETF_ROT_REGIME_MA) + 1
    idx = panel.index[start:]
    split = int(len(idx) * 0.6)
    is_sl, oos_sl = slice(0, split), slice(split, None)
    bench_r = rets[bench].reindex(idx) if bench in rets.columns else None

    grid_k, grid_r = [1, 3, 5, 8, 12], [4, 13, 26]
    res = []
    for K in grid_k:
        for R in grid_r:
            port = _sim(panel, rel, absm, rets, have, K, R, defensive)
            res.append((K, R, _stats(port.iloc[is_sl]), _stats(port.iloc[oos_sl])))
    res.sort(key=lambda x: x[2].get("sharpe", -9), reverse=True)   # ranka på IN-SAMPLE Sharpe

    b_is = _stats(bench_r.iloc[is_sl]) if bench_r is not None else {}
    b_oos = _stats(bench_r.iloc[oos_sl]) if bench_r is not None else {}
    isd, ood = idx[is_sl], idx[oos_sl]
    print(f"\n  ROTATIONS-SVEP (alltid-investerad top-K) – {len(have)} ETF:er")
    print(f"  IN-SAMPLE {isd[0].date()}–{isd[-1].date()}  |  OOS {ood[0].date()}–{ood[-1].date()}")
    print(f"  Rankat på IN-SAMPLE Sharpe. OOS = osedd data (det enda som räknas).\n")
    print(f"  {'K':>2} {'ombal':>6} | {'IS Sharpe':>9} {'IS CAGR':>8} | {'OOS Sharpe':>10} "
          f"{'OOS CAGR':>8} {'OOS maxDD':>9}  slår index OOS?")
    beats = 0
    for K, R, IS, OO in res:
        win = OO.get("cagr", -9) > b_oos.get("cagr", 9)
        beats += int(win)
        print(f"  {K:>2} {R:>5}v | {IS.get('sharpe',0):>9.2f} {IS.get('cagr',0):>+7.1%} | "
              f"{OO.get('sharpe',0):>10.2f} {OO.get('cagr',0):>+7.1%} {OO.get('maxdd',0):>+8.1%}"
              f"   {'JA' if win else 'nej'}")
    if bench_r is not None:
        print(f"\n  INDEX {bench} (baslinje): IS Sharpe {b_is.get('sharpe',0):.2f} "
              f"CAGR {b_is.get('cagr',0):+.1%}  |  OOS Sharpe {b_oos.get('sharpe',0):.2f} "
              f"CAGR {b_oos.get('cagr',0):+.1%} maxDD {b_oos.get('maxdd',0):+.1%}")
        best = res[0]
        print(f"\n  → Bästa IN-SAMPLE (K={best[0]}, ombal {best[1]}v): "
              f"OOS CAGR {best[3].get('cagr',0):+.1%} vs index {b_oos.get('cagr',0):+.1%} "
              f"→ {'SLÅR index OOS' if best[3].get('cagr',-9) > b_oos.get('cagr',9) else 'FÖRLORAR mot index OOS'}")
        print(f"  → {beats}/{len(res)} configs slår index på OOS "
              f"({'≈ slump/ingen edge' if beats <= len(res) * 0.5 else 'värt en närmare titt'}).")
    print("\n  Om den bästa in-sample-configen förlorar OOS finns ingen robust rotation "
          "– parametrarna var bara efterhands-tur.")


# ── Aktuell signal + flöde ────────────────────────────────────────────────────
def signal():
    uni = _load_universe()
    name_map = {t: n for t, n, _ in [(t, n, s) for t, s, n in uni]}
    sec_map = {t: s for t, s, _ in uni}
    etfs = [t for t, _, _ in uni]
    panel = _panel(etfs + [x for x in (config.ETF_ROT_DEFENSIVE, config.ETF_ROT_BENCHMARK) if x])
    have = [t for t in etfs if t in panel.columns]
    rel, absm = _scores(panel, have)
    last, look = -1, config.ETF_ROT_FLOW_LOOKBACK
    rel_now = rel.iloc[last].dropna()
    ranked_now = rel_now.sort_values(ascending=False)
    rank_now = {t: i + 1 for i, t in enumerate(ranked_now.index)}
    rank_prev = {t: i + 1 for i, t in enumerate(rel.iloc[last - look].dropna().sort_values(ascending=False).index)} \
        if len(rel) > look else {}

    regime = _regime(panel)
    risk_on = True if regime is None else bool(regime.iloc[last])
    weights, picks = _decide(rel_now, absm.iloc[last], config.ETF_ROT_TOP_K,
                             config.ETF_ROT_DEFENSIVE, config.ETF_ROT_ABS_MIN)
    held = {t for t, hold, _ in picks if hold}

    breadth = _sector_breadth()   # global bekräftelse (EU+US per GICS-sektor)
    vflow = _volume_flow(list(ranked_now.index))   # token-fritt kapitalflöde (CMF/volym)

    reg = ("🟢 BULL (risk-on)" if risk_on else "🔴 BJÖRN (risk-off → defensivt)")
    print(f"\n  ETF-ROTATION – aktuell signal ({panel.index[-1].date()}), globalt universum")
    print(f"  Marknadsregim: {reg}  [{config.ETF_ROT_REGIME_TICKER} vs {config.ETF_ROT_REGIME_MA}v MA]\n")
    print(f"  {'#':>2} {'sektor':<24} {'ETF':<9} {'rel.mom':>8} {'abs52v':>8} {'flöde (volym)':>16} {'glob.bredd':>11}  håll")
    rows = []
    for t in ranked_now.index:
        rc = (rank_prev.get(t, 99) - rank_now[t]) if rank_prev else 0
        vf = vflow.get(t)
        cmf = vf["cmf"] if vf else None
        relvol = vf["relvol"] if vf else None
        flow = _flow_label(cmf, relvol, rc)
        a = absm.iloc[last].get(t)
        hold = "★" if t in held else ""
        b = breadth.get(sec_map.get(t))
        bstr = f"{b['up']}/{b['total']} {b['mom']:+.0%}" if b else "—"
        print(f"  {rank_now[t]:>2} {sec_map.get(t, '?')[:24]:<24} {t:<9} "
              f"{rel_now[t]:>+7.1%} {(a if pd.notna(a) else float('nan')):>+7.1%} {flow:>16} {bstr:>11}  {hold}")
        row = {"rank": rank_now[t], "sector": sec_map.get(t), "etf": t,
               "name": name_map.get(t), "rel_mom": round(float(rel_now[t]), 4),
               "abs_mom": round(float(a), 4) if pd.notna(a) else None,
               "rank_change": int(rc), "cmf": cmf, "relvol": relvol,
               "hold": int(t in held)}
        if b:
            row.update(breadth_mom=round(b["mom"], 4), breadth_up=b["up"], breadth_total=b["total"])
        rows.append(row)

    if not risk_on:
        dgt = config.ETF_ROT_DEFENSIVE or "kontanter"
        print(f"\n  → REGIM = BJÖRN: hela portföljen i defensivt ({dgt}). Rotationen nedan "
              "visas för insyn men aktiveras först när regimen vänder till bull.")
    hold_list = [t for t, h, _ in picks if h]
    defslots = config.ETF_ROT_TOP_K - len(hold_list)
    print(f"\n  → HÅLL NU (top-{config.ETF_ROT_TOP_K}): "
          f"{', '.join(hold_list) if hold_list else '(inget klarar absolut-filtret)'}")
    if defslots:
        dgt = config.ETF_ROT_DEFENSIVE or "kontanter"
        print(f"    {defslots} slot(s) → defensivt ({dgt}) – dessa sektorer trendar inte (absolut mom ≤ "
              f"{config.ETF_ROT_ABS_MIN:.0%}).")
    out = Path("results/etf_rotation.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False)
    # Metadata (regim + innehav) så frontend kan visa bull/björn utan att räkna om.
    import json as _json
    meta = {
        "date": str(panel.index[-1].date()),
        "risk_on": bool(risk_on),
        "regime_ticker": config.ETF_ROT_REGIME_TICKER,
        "regime_ma": config.ETF_ROT_REGIME_MA,
        "top_k": config.ETF_ROT_TOP_K,
        "held": hold_list,
        "defensive_slots": defslots,
        "defensive": config.ETF_ROT_DEFENSIVE or "kontanter",
    }
    try:   # bifoga makroläget (valfritt – kräver macro_data-cache)
        from macro_data import indicators as _macro_ind
        meta["macro"] = _macro_ind()
    except Exception:  # noqa: BLE001
        meta["macro"] = None
    (out.parent / "etf_rotation_meta.json").write_text(_json.dumps(meta, ensure_ascii=False))
    print(f"\n  Signal sparad: {out}")


def detect(ticker, weeks=156):
    """Facit: för en ETF, hur många veckor EFTER botten tände varje signal, och hur
    mycket priset redan hade rört sig då? Visar latensen ⚡volym → CMF → momentum-rank."""
    from data.data_loader import fetch_weekly_data
    uni = _load_universe()
    etfs = [t for t, _, _ in uni]
    data = fetch_weekly_data(etfs, use_cache=True)
    closes = {t: d["Close"] for t, d in data.items() if d is not None and not d["Close"].dropna().empty}
    panel = pd.DataFrame(closes).sort_index()
    panel.index = pd.to_datetime(panel.index)
    have = [t for t in etfs if t in panel.columns]
    if ticker not in panel.columns or data.get(ticker) is None:
        print(f"[detect] ingen data för {ticker}. Universum: {', '.join(have)}")
        return
    rel, _ = _scores(panel, have)
    ranks = rel.rank(axis=1, ascending=False)   # 1 = starkast

    d = data[ticker].dropna(subset=["High", "Low", "Close", "Volume"]).copy()
    d.index = pd.to_datetime(d.index)
    hl = (d["High"] - d["Low"]).replace(0, np.nan)
    mfm = ((d["Close"] - d["Low"]) - (d["High"] - d["Close"])) / hl
    mfv = mfm.fillna(0.0) * d["Volume"]
    cmf = mfv.rolling(13).sum() / d["Volume"].rolling(13).sum()
    relvol = d["Volume"].rolling(4).mean() / d["Volume"].rolling(26).mean()

    px = d["Close"].tail(weeks)
    trough_date = px.idxmin()
    peak_date = px.loc[trough_date:].idxmax()
    run = float(px.loc[peak_date] / px.loc[trough_date] - 1)
    K = config.ETF_ROT_TOP_K

    def first_true(mask):
        m = mask.loc[trough_date:].dropna()
        m = m[m]
        return m.index[0] if len(m) else None

    fv = first_true(relvol >= 1.3)
    fc = first_true(cmf >= 0.05)
    tkrank = ranks[ticker] if ticker in ranks.columns else None
    fm = first_true(tkrank <= K) if tkrank is not None else None

    def wk(dt):
        return None if dt is None else int((dt - trough_date).days / 7)

    def gain(dt):
        return None if dt is None else float(px.loc[:dt].iloc[-1] / px.loc[trough_date] - 1)

    print(f"\n  DETEKTIONS-FACIT: {ticker} ({uni and dict((t,g) for t,g,_ in uni).get(ticker,'')})")
    print(f"  Största rörelsen i fönstret: botten {trough_date.date()} → topp {peak_date.date()}  "
          f"(+{run:.0%})\n")
    print(f"  {'Signal':<26}{'först vid':>12}{'v efter botten':>15}{'pris rört då':>14}")
    for lbl, dt in (("⚡ Volymspik (relvol≥1.3)", fv),
                    ("CMF+ (ackumulation)", fc),
                    (f"Momentum topp-{K}", fm)):
        w = wk(dt); g = gain(dt)
        ws = f"{w}v" if w is not None else "—"
        gs = f"+{g:.0%}" if g is not None else "—"
        ds = dt.date().isoformat() if dt is not None else "aldrig"
        print(f"  {lbl:<26}{ds:>12}{ws:>15}{gs:>14}")
    print("\n  Läs: ⚡ tänder tidigast men brusigt; momentum-rank sist – ofta efter att en stor "
          "del av uppgången redan skett. Det är exakt 'går in sent'-problemet.")


def flowstudy():
    """Event-studie: när varje signal TÄNDER (volymspik ⚡ / CMF+ / momentum topp-K),
    vad blir framåtavkastningen på 1–26v – över ALLA ETF:er och hela historiken?
    Avgör (a) falsklarms-nivån (edge vs baslinje) och (b) 'tidigt ut vs rid vidare'
    (är vinsten front-laddad eller ackumuleras den?)."""
    from data.data_loader import fetch_weekly_data
    uni = _load_universe()
    etfs = [t for t, _, _ in uni]
    data = fetch_weekly_data(etfs, use_cache=True)
    closes = {t: d["Close"] for t, d in data.items() if d is not None and not d["Close"].dropna().empty}
    panel = pd.DataFrame(closes).sort_index()
    panel.index = pd.to_datetime(panel.index)
    have = [t for t in etfs if t in panel.columns]
    rel, _ = _scores(panel, have)
    ranks = rel.rank(axis=1, ascending=False)
    K = config.ETF_ROT_TOP_K
    horizons = [1, 2, 4, 8, 13, 26]
    acc = {s: {h: [] for h in horizons} for s in ("baseline", "volspike", "cmf_pos", "mom_top")}

    def firings(mask):
        m = mask.fillna(False).astype(bool)
        return m & (~m.shift(1).fillna(False))     # övergång Falskt→Sant = ny signal

    for t in have:
        d = data[t].dropna(subset=["High", "Low", "Close", "Volume"])
        if len(d) < 60:
            continue
        d.index = pd.to_datetime(d.index)
        close = d["Close"]
        hl = (d["High"] - d["Low"]).replace(0, np.nan)
        mfm = ((close - d["Low"]) - (d["High"] - close)) / hl
        cmf = (mfm.fillna(0.0) * d["Volume"]).rolling(13).sum() / d["Volume"].rolling(13).sum()
        relvol = d["Volume"].rolling(4).mean() / d["Volume"].rolling(26).mean()
        rk = ranks[t].reindex(close.index) if t in ranks.columns else pd.Series(np.nan, index=close.index)
        fires = {"volspike": firings(relvol >= 1.3),
                 "cmf_pos": firings(cmf >= 0.05),
                 "mom_top": firings(rk <= K)}
        for h in horizons:
            fwd = close.shift(-h) / close - 1
            acc["baseline"][h].extend(fwd.dropna().tolist())
            for s, mask in fires.items():
                acc[s][h].extend(fwd[mask.reindex(close.index, fill_value=False)].dropna().tolist())

    def stat(lst):
        a = np.array(lst, dtype=float)
        return (float(a.mean()), float((a > 0).mean()), len(a)) if len(a) else (float("nan"), float("nan"), 0)

    base = {h: stat(acc["baseline"][h]) for h in horizons}
    print("\n  FLÖDES-SIGNAL EVENT-STUDIE – snitt framåtavkastning EFTER att signalen tänt")
    print("  (över alla ETF:er/historik; 'edge' = snitt minus baslinje för samma horisont)\n")
    print(f"  {'baslinje (alla v)':<22}" + "".join(f"{f'{h}v':>9}" for h in horizons))
    print(f"  {'  snitt':<22}" + "".join(f"{base[h][0]:>+8.1%} " for h in horizons))
    for s, lbl in (("volspike", "⚡ Volymspik"), ("cmf_pos", "CMF+ (ackum.)"),
                   ("mom_top", f"Momentum topp-{K}")):
        print(f"\n  {lbl}  (n={stat(acc[s][horizons[0]])[2]} event)")
        print(f"  {'  edge vs baslinje':<22}" +
              "".join(f"{stat(acc[s][h])[0] - base[h][0]:>+8.1%} " for h in horizons))
        print(f"  {'  träffsäkerhet':<22}" +
              "".join(f"{stat(acc[s][h])[1]:>8.0%} " for h in horizons))
    print("\n  Tolkning: positiv 'edge' som är STÖRST tidigt (1–4v) och sedan krymper → "
          "TIDIGT IN, TIDIGT UT lönar sig. Edge som växer mot 13–26v → rid vidare. "
          "Edge ≈ 0 på alla horisonter → signalen är brus (falsklarm dominerar).")


def leverage(ticker=None):
    """Simulerar daglig-ombalanserad hävstång (1x/2x/3x) på ett index – visar
    volatilitetsdecay + förstärkt drawdown. Svarar 'är Bull 2x bäst?' (nästan aldrig
    på lång sikt). Kostnad ~2%/år för hävstången (TER + finansiering)."""
    import yfinance as yf
    ticker = ticker or config.ETF_ROT_BENCHMARK
    raw = yf.download(ticker, start=config.START_DATE, interval="1d",
                      auto_adjust=True, progress=False)
    close = raw["Close"]
    if isinstance(close, pd.DataFrame):
        close = close[ticker] if ticker in close.columns else close.iloc[:, 0]
    close = close.dropna()
    r = close.pct_change().dropna()
    yrs = len(r) / 252.0
    ann_cost = 0.02        # TER + finansieringskostnad för hävstången
    start = 100000

    def sim(L):
        dr = L * r - (ann_cost / 252.0 if L > 1 else 0.0)   # daglig ombalansering
        eq = (1 + dr).cumprod()
        total = float(eq.iloc[-1] - 1)
        cagr = float(eq.iloc[-1] ** (1 / yrs) - 1)
        dd = float((eq / eq.cummax() - 1).min())
        worst_1y = float((eq / eq.shift(252) - 1).min())     # värsta rullande år
        return start * float(eq.iloc[-1]), cagr, dd, worst_1y

    print(f"\n  HÄVSTÅNGS-SIMULERING på {ticker}  ({close.index[0].date()} → {close.index[-1].date()}, "
          f"{yrs:.0f} år)")
    print(f"  Daglig ombalansering, hävstångskostnad ~{ann_cost:.0%}/år.\n")
    print(f"  {'':<10}{'100 000 kr →':>16}{'CAGR':>9}{'maxDD':>9}{'värsta år':>11}")
    for L in (1, 2, 3):
        fin, cagr, dd, w1 = sim(L)
        lbl = "1x (index)" if L == 1 else f"{L}x (Bull {L})"
        print(f"  {lbl:<10}{fin:>14,.0f} kr{cagr:>+8.1%}{dd:>+9.1%}{w1:>+11.1%}".replace(",", " "))
    print("\n  Läs: 2x/3x ser ofta bra ut i slutvärde EFTER en lång tjurmarknad – men titta på "
          "maxDD och 'värsta år'. Där ligger ruinrisken: ett −75% år kräver +300% för att "
          "återhämtas. Daglig ombalansering = decay i skakiga perioder. Bra för dagar, "
          "livsfarligt för besparingar.")


def flow():
    """Ren flödesvy: vilka sektorer klättrar/faller i rank (kapital in/ut)."""
    signal()   # signalen innehåller redan flödeskolumnen; separat kommando för bekvämlighet


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "signal"
    if cmd == "signal":
        signal()
    elif cmd == "backtest":
        backtest(always_invested=("--always-invested" in sys.argv or "--always" in sys.argv))
    elif cmd == "sweep":
        sweep()
    elif cmd == "detect":
        detect(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 156)
    elif cmd == "flowstudy":
        flowstudy()
    elif cmd == "leverage":
        leverage(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "flow":
        flow()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
