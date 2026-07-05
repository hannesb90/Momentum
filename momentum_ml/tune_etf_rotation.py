"""
tune_etf_rotation.py – Finns det NETTO-edge i ETF-rotationens fyra knoppar?

Lärdomen från aktiemodellens svep: brutto-mått ljuger (horisont-ensemblen såg
ut som +0.52 IR brutto och var −6.7 pp CAGR netto). Därför testas ALLT här
genom den riktiga strategimotorn (_run) med transaktionskostnad inbakad, och
domen fälls på OOS-perioden (sista 40%), inte in-sample.

Varianter (alla identiska med produktion utom EN knopp i taget + en all_on
för interaktions-kontroll – aktie-svepet visade att vinnare kan förstöra
varandra i kombination):

  baseline      dagens produktion (topp-3, mom [26,52]v, abs-filter 0%, regim)
  vol_adj       ranka på momentum/vol i stället för rå avkastning
  hysteresis    absolut-filter: enter +5% / exit 0% (stoppar churn kring 0%)
  keep_band     rank-hysteres: behåll innehav tills utanför topp K×2
  corr_cap      hoppa kandidat med >0.8 korr mot redan valt innehav
  fast_windows  mom-fönster [13,26,52] (snabbare rotation – kostar omsättning?)
  all_on        alla ovan samtidigt (interaktionskontroll)

Kör på Pi:n från /opt/momentum/src/momentum_ml (kräver Yahoo-cache/nät):

    /opt/momentum/venv/bin/python tune_etf_rotation.py
"""
import sys
import math
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import config
from etf_rotation import _load_universe, _panel, _scores, _regime, _run, _stats

VARIANTS = {
    "baseline":     {},
    "vol_adj":      {"vol_adj": True},
    "hysteresis":   {"abs_min": 0.05, "abs_exit": 0.0},
    "keep_band":    {"keep_mult": 2.0},
    "corr_cap":     {"corr_max": 0.8},
    "fast_windows": {"windows": [13, 26, 52]},
    "all_on":       {"vol_adj": True, "abs_min": 0.05, "abs_exit": 0.0,
                     "keep_mult": 2.0, "corr_max": 0.8, "windows": [13, 26, 52]},
}


def main():
    uni = _load_universe()
    etfs = [t for t, _, _ in uni]
    defensive = config.ETF_ROT_DEFENSIVE
    bench = config.ETF_ROT_BENCHMARK
    extra = [x for x in ([defensive, bench] + list(getattr(config, "ETF_ROT_BENCHMARKS_EXTRA", []))) if x]
    panel = _panel(etfs + extra)
    have = [t for t in etfs if t in panel.columns]
    if len(have) < config.ETF_ROT_TOP_K:
        print(f"[tune] för få ETF:er med data ({len(have)}).")
        return
    rets = panel.pct_change()
    regime = _regime(panel)
    k, rebal = config.ETF_ROT_TOP_K, config.ETF_ROT_REBAL_WEEKS
    cost = config.ETF_ROT_COST_ONEWAY
    start = max(config.ETF_ROT_ABS_WINDOW, config.ETF_ROT_REGIME_MA) + 1
    idx = panel.index[start:]
    split = int(len(idx) * 0.6)
    oos_start = idx[split]

    print("\n" + "=" * 76)
    print(f"  ETF-ROTATION EDGE-SVEP · {len(have)} ETF:er · kostnad {cost:.2%} enkelriktat")
    print(f"  IS {idx[0].date()}–{idx[split-1].date()}  |  OOS {oos_start.date()}–{idx[-1].date()}"
          f"  ·  regim {'PÅ' if regime is not None else 'AV'}")
    print("=" * 76)

    bench_r = rets[bench].reindex(idx) if bench in rets.columns else None
    b_oos = _stats(bench_r.iloc[split:]) if bench_r is not None else {}

    rows = []
    base_oos = None
    for name, kn in VARIANTS.items():
        rel, absm = _scores(panel, have,
                            vol_adj=kn.get("vol_adj", False),
                            windows=kn.get("windows"))
        r = _run(panel, rel, absm, rets, have, k=k, rebal=rebal,
                 abs_min=kn.get("abs_min", config.ETF_ROT_ABS_MIN),
                 defensive=defensive, regime=regime,
                 keep_mult=kn.get("keep_mult", 1.0),
                 abs_exit=kn.get("abs_exit"),
                 corr_max=kn.get("corr_max"),
                 cost=cost, start=start)
        port = r["port"]
        yrs = max(len(port) / 52.0, 1e-9)
        s_is, s_oos = _stats(port.iloc[:split]), _stats(port.iloc[split:])
        if name == "baseline":
            base_oos = s_oos
        rows.append((name, s_is, s_oos, r["turnover"] / yrs, r["cost_drag"] / yrs))

    print(f"\n  {'variant':<14}{'IS Sharpe':>9}{'IS CAGR':>9} | {'OOS Sharpe':>10}{'OOS CAGR':>9}"
          f"{'OOS maxDD':>10} | {'oms/år':>7}{'kostn/år':>9}")
    print("  " + "-" * 74)
    for name, s_is, s_oos, to, cd in rows:
        flag = ""
        if base_oos and name != "baseline":
            d = s_oos.get("sharpe", -9) - base_oos.get("sharpe", -9)
            flag = "  ← bättre" if d > 0.05 else ("  ← sämre" if d < -0.05 else "")
        print(f"  {name:<14}{s_is.get('sharpe', 0):>9.2f}{s_is.get('cagr', 0):>+8.1%} | "
              f"{s_oos.get('sharpe', 0):>10.2f}{s_oos.get('cagr', 0):>+8.1%}"
              f"{s_oos.get('maxdd', 0):>+9.1%} | {to:>6.1f}×{cd:>8.2%}{flag}")
    if b_oos:
        print("  " + "-" * 74)
        print(f"  {'index ' + bench:<14}{'':>9}{'':>9} | {b_oos.get('sharpe', 0):>10.2f}"
              f"{b_oos.get('cagr', 0):>+8.1%}{b_oos.get('maxdd', 0):>+9.1%} |")

    print("""
  LÄS SÅ HÄR:
    · Domen fälls på OOS-kolumnerna (osedd data) – IS är bara referens.
    · En variant som höjer OOS-Sharpe OCH sänker omsättning/kostnad har en
      trovärdig mekanism. En som bara höjer OOS-CAGR med högre omsättning
      kan vara period-tur.
    · all_on ≠ summan av delarna (aktie-svepets lärdom) – lita inte på en
      kombination som inte testats exakt så.
    · Slår ingen variant indexet på OOS är den ärliga slutsatsen att
      rotationen saknar edge netto – då är bred passiv kärna rätt.""")


if __name__ == "__main__":
    main()
