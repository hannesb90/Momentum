"""
leadlag_discover.py – DATADRIVEN, token-fri lead-lag-upptäckt ur historiska priser.

Istället för att skriva kausalsambanden för hand (eller låta en LLM gissa dem)
letar detta upp dem empiriskt: för varje ordnat par (Ledare X, Följare Y) och
ledtid L testas om X:s L-dagarsavkastning predikterar Y:s NÄSTA L-dagarsavkastning
(Granger-liknande lagged korrelation). Ger en if-then-tabell:
    "Om <Ledare> rört sig → <Följare> tenderar följa efter ~L dagar."

Token-fritt, backtestbart, skalar till alla par. Motsvarigheten till världsträdet,
men UPPTÄCKT ur data. Kan slås ihop in i grafen (--merge) så 'etf_thesis leadlag'
använder empiriskt funna samband.

VARNING: in-sample-samband + multipeltestning (tusentals par) → risk för falska
träffar. Tröskeln är strikt (t≥3.5) men validera topparna out-of-sample innan du
litar på dem. Korrelation ≠ kausalitet.

Körs på Pi:n (Yahoo-åtkomst krävs):
    python leadlag_discover.py discover           # bygg if-then-tabellen
    python leadlag_discover.py discover --merge    # + skriv in i sector_causal_graph.json
"""
import sys
import csv
import json
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import config

try:
    import yfinance as yf
except ImportError:
    yf = None


def _daily_prices(tickers):
    if yf is None:
        raise RuntimeError("paketet 'yfinance' saknas – pip install yfinance")
    raw = yf.download(tickers, start=config.START_DATE, interval="1d",
                      auto_adjust=True, progress=False, threads=True)
    cols = {}
    for t in tickers:
        try:
            s = raw["Close"][t] if isinstance(raw.columns, pd.MultiIndex) else raw["Close"]
            s = s.dropna()
            if len(s) > 300:
                cols[t] = s
        except (KeyError, TypeError):
            pass
    df = pd.DataFrame(cols).sort_index()
    df.index = pd.to_datetime(df.index)
    return df


def discover(merge=False):
    from etf_rotation import _load_universe
    uni = _load_universe()
    tk2group = {t: g for t, g, _ in uni}
    tickers = list(tk2group)
    print(f"[leadlag] hämtar dagsdata för {len(tickers)} ETF:er...")
    px = _daily_prices(tickers)
    have = [t for t in tickers if t in px.columns]
    print(f"[leadlag] {len(have)} med data – testar {len(have) * (len(have) - 1)} par × "
          f"{len(config.LEADLAG_LAGS_DAYS)} ledtider")

    rows, tests = [], 0
    for L in config.LEADLAG_LAGS_DAYS:
        cum = px[have] / px[have].shift(L) - 1          # överlappande L-dagarsavkastning
        samp = cum.iloc[::L]                            # sampla icke-överlappande
        for x in have:
            xa = samp[x]
            for y in have:
                if x == y:
                    continue
                tests += 1
                d = pd.concat([xa, samp[y].shift(-1)], axis=1).dropna()   # följare = nästa block
                if len(d) < 20:
                    continue
                c = d.iloc[:, 0].corr(d.iloc[:, 1])
                if pd.isna(c):
                    continue
                n = len(d)
                t = c * np.sqrt(max(n - 2, 1)) / np.sqrt(max(1 - c * c, 1e-9))
                if t >= config.LEADLAG_MIN_T and c >= config.LEADLAG_MIN_CORR:
                    rows.append({"leader": tk2group.get(x), "leader_etf": x,
                                 "follower": tk2group.get(y), "follower_etf": y,
                                 "lag_days": L, "corr": round(float(c), 3),
                                 "tstat": round(float(t), 2), "n": n})
    rows.sort(key=lambda r: r["tstat"], reverse=True)
    out = Path("results/leadlag_matrix.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["leader", "leader_etf", "follower",
                                          "follower_etf", "lag_days", "corr", "tstat", "n"])
        w.writeheader(); w.writerows(rows)

    print(f"\n  DATADRIVEN LEAD-LAG (top {min(20, len(rows))} av {len(rows)} signifikanta, "
          f"av {tests} test)")
    print("  ⚠ in-sample + multipeltestning – validera OOS. Korrelation ≠ kausalitet.\n")
    for r in rows[:20]:
        print(f"   t={r['tstat']:>4}  {r['leader'][:20]:<20} →({r['lag_days']:>2}d)  "
              f"{r['follower'][:20]:<20}  corr {r['corr']:+.2f}  (n={r['n']})")
    print(f"\n  Sparad: {out}")

    if merge:
        _merge_into_graph(rows)


def _merge_into_graph(rows):
    """Skriv in de funna sambanden i grafen som source='empirical' (dedup mot X→Y)."""
    gp = Path(__file__).parent / "data" / "sector_causal_graph.json"
    g = json.loads(gp.read_text(encoding="utf-8"))
    existing = {(e["from"], e["to"]) for e in g["edges"]}
    added = 0
    for r in rows:
        key = (r["leader"], r["follower"])
        if r["leader"] == r["follower"] or key in existing:
            continue
        g["edges"].append({"from": r["leader"], "to": r["follower"], "sign": "+",
                           "lag_m": round(r["lag_days"] / 21.0, 1),
                           "conf": round(min(0.6, r["corr"]), 2),
                           "why": f"empiriskt (lead-lag t={r['tstat']}, {r['lag_days']}d)",
                           "source": "empirical"})
        existing.add(key); added += 1
    gp.write_text(json.dumps(g, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [merge] +{added} empiriska kanter → grafen ({len(g['edges'])} totalt). "
          "'etf_thesis leadlag' använder dem nu.")


def main():
    args = sys.argv[1:]
    if args and args[0] == "discover":
        discover(merge=("--merge" in args))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
