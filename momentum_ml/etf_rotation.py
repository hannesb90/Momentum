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


def _regime(panel):
    """Bull/björn per datum: bred marknad över sin långa glidande medel = risk-on.
    None om regim-filtret är av eller regim-tickern saknar data."""
    if not getattr(config, "ETF_ROT_REGIME_ENABLED", False):
        return None
    t = config.ETF_ROT_REGIME_TICKER
    if t not in panel.columns:
        return None
    ma = panel[t].rolling(config.ETF_ROT_REGIME_MA).mean()
    return panel[t] > ma


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
def backtest():
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
    regime = _regime(panel)
    rets = panel.pct_change()
    k, rebal, abs_min = config.ETF_ROT_TOP_K, config.ETF_ROT_REBAL_WEEKS, config.ETF_ROT_ABS_MIN
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

    reg_txt = (f"regim PÅ ({config.ETF_ROT_REGIME_TICKER} vs {config.ETF_ROT_REGIME_MA}v MA)"
               if regime is not None else "regim AV")
    print(f"\n  ETF-ROTATION (regim-medveten dual momentum) – globalt universum, "
          f"top-{k}, mom {config.ETF_ROT_MOM_WINDOWS}v, ombal var {rebal}v, {len(have)} ETF:er")
    print(f"  Period: {idx[0].date()} – {idx[-1].date()}  ({len(idx)} veckor) · {reg_txt}")
    if regime is not None:
        print(f"  Risk-off (björn → defensivt): {riskoff_wk / len(idx):.0%} av tiden "
              f"(defensivt ben: {defensive or 'kontanter'})")
    print("  (Tematiska ETF:er har kortare historik – valbara först när de fått data.)\n")
    print(_fmt_stats("Rotation (strategi)", _stats(port)))
    print(_fmt_stats("Likaviktad pool (B&H)", _stats(eqw)))
    prim = None
    for b in bmarks:
        if b in rets.columns:
            bs = rets[b].reindex(idx)
            print(_fmt_stats(f"Index {b}", _stats(bs)))
            if prim is None:
                prim = bs
    if prim is not None:   # slå-index-frekvens mot primär benchmark (ACWI)
        roll = (port.rolling(13).apply(lambda x: (1 + x).prod() - 1)
                > prim.rolling(13).apply(lambda x: (1 + x).prod() - 1))
        print(f"\n  Slår {bench} (global) på rullande 13v-fönster: {roll.mean():.0%} av tiden")
    print("\n  (Ombalansering utan transaktionskostnad. Absolut-filtret = skydd i "
          "björnmarknad; sätt ETF_ROT_ABS_MIN högre för mer försiktighet.)")


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

    reg = ("🟢 BULL (risk-on)" if risk_on else "🔴 BJÖRN (risk-off → defensivt)")
    print(f"\n  ETF-ROTATION – aktuell signal ({panel.index[-1].date()}), globalt universum")
    print(f"  Marknadsregim: {reg}  [{config.ETF_ROT_REGIME_TICKER} vs {config.ETF_ROT_REGIME_MA}v MA]\n")
    print(f"  {'#':>2} {'sektor':<24} {'ETF':<9} {'rel.mom':>8} {'abs52v':>8} {'flöde':>10}  håll")
    rows = []
    for t in ranked_now.index:
        rc = (rank_prev.get(t, 99) - rank_now[t]) if rank_prev else 0
        flow = "→ stabil"
        if rc >= 2:
            flow = f"↑ in (+{rc})"
        elif rc <= -2:
            flow = f"↓ ut ({rc})"
        a = absm.iloc[last].get(t)
        hold = "★" if t in held else ""
        print(f"  {rank_now[t]:>2} {sec_map.get(t, '?')[:24]:<24} {t:<9} "
              f"{rel_now[t]:>+7.1%} {(a if pd.notna(a) else float('nan')):>+7.1%} {flow:>10}  {hold}")
        rows.append({"rank": rank_now[t], "sector": sec_map.get(t), "etf": t,
                     "name": name_map.get(t), "rel_mom": round(float(rel_now[t]), 4),
                     "abs_mom": round(float(a), 4) if pd.notna(a) else None,
                     "rank_change": int(rc), "hold": int(t in held)})

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
    print(f"\n  Signal sparad: {out}")


def flow():
    """Ren flödesvy: vilka sektorer klättrar/faller i rank (kapital in/ut)."""
    signal()   # signalen innehåller redan flödeskolumnen; separat kommando för bekvämlighet


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "signal"
    if cmd == "signal":
        signal()
    elif cmd == "backtest":
        backtest()
    elif cmd == "flow":
        flow()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
