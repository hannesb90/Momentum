"""RETROSPEKTIV ANALYS AV STORA VINNARE (MEGA-WINNERS)

1. Identifierar alla "Stora Vinnare" i universumet: aktier som steg ≥ 100%
   under en 12-24 månaders period utan att omedelbart krascha tillbaka.
2. Går tillbaka till deras STARTFAS (månad 1-3 av uppgången).
3. Jämför startfasen hos Stora Vinnare mot "Falska Utbrott" (aktier som steg +30% på 12v men var −20% efter 12m).

Mäter i startfasen (vecka 1-12):
  - Riktad jämnhet (Linearity / R² i log-pris)
  - Max drawdown under de första 12v
  - Lutning på SMA50 / vinkel på trenden
  - Avstånd till 52w low vs 52w high vid starten
  - Volatilitetskvot (12v avkastning / 12v volatilitet = Sharpe-liknande kortsiktigt mått)

DIAGNOSTISKT.
Kör: /opt/momentum/venv/bin/python tools/analysera_stora_vinnare_startfas.py
"""
from __future__ import annotations
import importlib.util, json, math, statistics
from datetime import date, timedelta, datetime, timezone
from pathlib import Path

import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/stora_vinnare_startfas_results.json"


def ladda():
    s = importlib.util.spec_from_file_location(
        "h2h", V2 / "tools/research_all_6_models_head_to_head.py")
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    core, prices, term = m.load_data()
    return m, prices, core


def main():
    print("Loading data...")
    m, prices, core = ladda()

    price_lists = {k: sorted(rs, key=lambda r: r["d"])
                   for k, rs in prices.items()}

    # Find candidate trajectories: look at non-overlapping or rolling 1-year / 2-year windows
    dates = sorted(core.panel_date.unique())
    dates = [d for d in dates if "2021-07-16" <= d <= "2025-07-10"]  # leave room for 1y+ fwd

    mega_winners = []
    false_pumps = []

    for dt in dates:
        panel = core[core.panel_date == dt]
        for k in panel.kod:
            rs = price_lists.get(k, [])
            if not rs:
                continue

            # Get price at dt, price at dt-12w, price at dt+52w
            p_dt = next((r["adj"] for r in reversed(rs) if r["d"] <= dt), None)
            if not p_dt or p_dt <= 0:
                continue

            dt_12w_ago = (date.fromisoformat(dt) - timedelta(days=84)).isoformat()
            p_12w_ago = next((r["adj"] for r in reversed(rs) if r["d"] <= dt_12w_ago), None)
            if not p_12w_ago or p_12w_ago <= 0:
                continue

            dt_52w_fwd = (date.fromisoformat(dt) + timedelta(days=364)).isoformat()
            p_52w_fwd = next((r["adj"] for r in reversed(rs) if r["d"] <= dt_52w_fwd), None)
            if not p_52w_fwd or p_52w_fwd <= 0:
                continue

            ret_12w_past = p_dt / p_12w_ago - 1.0
            ret_52w_fwd = p_52w_fwd / p_dt - 1.0

            # Filter for initial 12w breakout (ret_12w_past >= 20%)
            if ret_12w_past >= 0.20:
                # Features over trailing 12w (the start phase)
                w12 = [r for r in rs if dt_12w_ago <= r["d"] <= dt and r.get("adj") and r["adj"] > 0]
                if len(w12) < 40:
                    continue

                adj12 = np.array([r["adj"] for r in w12], float)

                # 1. Linearity R² in log-prices
                y = np.log(adj12)
                x = np.arange(len(y), dtype=float)
                r_corr = np.corrcoef(x, y)[0, 1]
                r2 = r_corr ** 2 if math.isfinite(r_corr) else 0.0

                # 2. Max DD during initial 12w
                peak = adj12[0]
                m_dd = 0.0
                for p in adj12:
                    peak = max(peak, p)
                    m_dd = min(m_dd, p / peak - 1.0)

                # 3. Daily volatility over 12w
                rets = np.diff(adj12) / adj12[:-1]
                vol12 = float(np.std(rets)) if len(rets) > 0 else 0.0

                # 4. Return-to-Vol ratio (Signal-to-Noise in start phase)
                s2n = ret_12w_past / (vol12 * math.sqrt(60)) if vol12 > 0 else 0.0

                # 5. Trailing 52w window prior to dt (to see background)
                dt_52w_ago = (date.fromisoformat(dt) - timedelta(days=364)).isoformat()
                w52_bg = [r for r in rs if dt_52w_ago <= r["d"] <= dt and r.get("adj") and r["adj"] > 0]
                adj52_bg = np.array([r["adj"] for r in w52_bg], float) if len(w52_bg) >= 150 else None

                p_to_52w_high = (p_dt / np.max(adj52_bg)) if adj52_bg is not None else None
                p_to_52w_low = (p_dt / np.min(adj52_bg)) if adj52_bg is not None else None

                obj = {
                    "kod": k,
                    "date": dt,
                    "ret_12w_past": ret_12w_past,
                    "ret_52w_fwd": ret_52w_fwd,
                    "r2_log_price": r2,
                    "max_dd_12w": m_dd,
                    "vol_12w": vol12,
                    "s2n_ratio": s2n,
                    "p_to_52w_high": p_to_52w_high,
                    "p_to_52w_low": p_to_52w_low,
                }

                # Mega winner: +80% or more over next 52 weeks
                if ret_52w_fwd >= 0.80:
                    mega_winners.append(obj)
                # False pump: +20% on 12w, but negative (-15% or worse) over next 52 weeks
                elif ret_52w_fwd <= -0.15:
                    false_pumps.append(obj)

    print(f"\n{'='*85}")
    print(f"RETROSPEKTIV ANALYS: STORA VINNARE vs FALSKA UTBROTT I STARTFASEN (12v)")
    print(f"{'='*85}")
    print(f"  Stora Vinnare (framtida 52v avk ≥ +80%):  N = {len(mega_winners)}")
    print(f"  Falska Utbrott (framtida 52v avk ≤ -15%): N = {len(false_pumps)}")

    def med(arr):
        v = [x for x in arr if x is not None and math.isfinite(x)]
        return statistics.median(v) if v else None

    def fmtp(v): return f"{v:.1%}" if v is not None else "N/A"
    def fmtf(v): return f"{v:.2f}" if v is not None else "N/A"

    metrics = [
        ("Signal-to-Noise Kvot (12v avk / 12v vol)", "s2n_ratio", fmtf),
        ("Trend-Linjäritet R² (1.0 = spikrak uppgång)", "r2_log_price", fmtf),
        ("Max Drawdown under 12v startfas", "max_dd_12w", fmtp),
        ("Daglig Volatilitet under 12v startfas", "vol_12w", fmtp),
        ("Pris / 52w High i startfasen", "p_to_52w_high", fmtp),
        ("Pris / 52w Low i startfasen", "p_to_52w_low", fmtf),
    ]

    print(f"\n  Egenskaper i startfasen (medianer):")
    print(f"  {'Egenskap':42s} {'Stora Vinnare':>16s} {'Falska Utbrott':>16s} {'Skillnad':>12s}")

    for label, key, fmt in metrics:
        mw = med([x[key] for x in mega_winners])
        fp = med([x[key] for x in false_pumps])
        diff = (mw - fp) if mw is not None and fp is not None else None
        print(f"  {label:42s} {fmt(mw):>16s} {fmt(fp):>16s} {fmt(diff):>12s}")

    OUT.write_text(json.dumps({
        "version": "RETROSPECTIVE_MEGA_WINNERS_V1",
        "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_mega_winners": len(mega_winners),
        "n_false_pumps": len(false_pumps),
    }, ensure_ascii=False, indent=2))
    print(f"\n  → {OUT.name}")


if __name__ == "__main__":
    main()
