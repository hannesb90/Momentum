"""
capture_analysis.py – Fångar modellen de stora rörelserna?

Systematiskt test (inte bara SAAB-anekdoten): hitta de N största uthålliga
FORWARD_WEEKS-rörelserna i universumet historiskt och mät hur stor andel
modellen faktiskt rankade högt / gav köpsignal på. Plus en kvantil-spread:
ger högre prob_up i snitt högre faktisk framtida avkastning? (Det rätta måttet
på om en tvärsnitts-signal har edge.)

Kör på Pi:n från /opt/momentum/momentum_ml EFTER en Large/Mid-körning (läser
results/signals.csv + datacachen, tränar inget):

    /opt/momentum/venv/bin/python capture_analysis.py
"""
import sys
sys.path.insert(0, '.')
import pandas as pd
import numpy as np
import config
from data.data_loader import (
    fetch_weekly_data, filter_liquid_universe, filter_active_universe, load_sweden_universe,
)

TOP_N = 50   # antal största rörelser att granska


def main():
    # Valfritt segment som argument: python capture_analysis.py [large|small]
    segment = sys.argv[1] if len(sys.argv) > 1 else config.DEFAULT_SEGMENT
    seg = config.SEGMENTS.get(segment) or config.SEGMENTS[config.DEFAULT_SEGMENT]
    results_dir = seg["results_dir"]
    print(f"[Segment] {segment} ({seg['label']}) – läser {results_dir}/signals.csv")

    tickers, sector_map, _, name_map = load_sweden_universe(min_market_cap=seg["market_cap"])
    config.SECTOR_MAP.update(sector_map)
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)

    fwd = config.FORWARD_WEEKS

    # Faktisk framåtavkastning per ticker/datum (det modellen försöker rangordna)
    rows = []
    for t, df in data.items():
        c = df["Close"]
        fr = c.shift(-fwd) / c - 1
        for date, r in fr.dropna().items():
            rows.append((date, t, float(r)))
    act = pd.DataFrame(rows, columns=["Date", "ticker", "fwd_ret"])

    sig = pd.read_csv(f"{results_dir}/signals.csv", parse_dates=["Date"])
    keep = [c for c in ["Date", "ticker", "prob_up", "pred_signal", "position_size", "name"] if c in sig.columns]
    m = act.merge(sig[keep], on=["Date", "ticker"], how="inner")
    if m.empty:
        print("[FEL] Ingen överlappning mellan signals.csv och prisdata – kör en Large/Mid-träning först.")
        return

    # Referens: vad är "hög" prob_up? (prob_up tar få diskreta nivåer)
    hi = m["prob_up"].quantile(0.80)   # topp-20%-nivån

    # ── 1. Fångade modellen de största rörelserna? ───────────────────────────
    big = m.sort_values("fwd_ret", ascending=False).head(TOP_N).copy()
    ranked_hi = (big["prob_up"] >= hi).mean()
    bought = (big["pred_signal"] == 1).mean()
    print("\n" + "=" * 70)
    print(f"  DE {TOP_N} STÖRSTA {fwd}-VECKORSRÖRELSERNA – fångade modellen dem?")
    print("=" * 70)
    print(f"  Rankade högt (prob_up >= {hi:.2f}, topp-20%):  {ranked_hi:.0%}")
    print(f"  Fick köpsignal (pred_signal=1, topp-10):       {bought:.0%}")
    print(f"  (jämför: slumpen rankar ~20% högt; topp-10 av ~{m['ticker'].nunique()} ≈ "
          f"{10.0/max(m['ticker'].nunique(),1):.0%} per vecka)")
    print("-" * 70)
    big["d"] = big["Date"].dt.date
    show = big[["d", "ticker", "name", "fwd_ret", "prob_up", "pred_signal"]].head(25)
    for _, r in show.iterrows():
        flag = "KÖP " if r["pred_signal"] == 1 else ("rank+" if r["prob_up"] >= hi else "MISS")
        nm = str(r.get("name", ""))[:22]
        print(f"  {r['d']}  {r['ticker']:<12} {nm:<24} fwd {r['fwd_ret']:+6.0%}  "
              f"prob {r['prob_up']:.2f}  [{flag}]")

    # ── 2. Kvantil-spread: ger hög prob_up högre faktisk avkastning? ──────────
    print("\n" + "=" * 70)
    print(f"  KVANTIL-SPREAD – snittlig faktisk {fwd}v-avkastning per prob_up-nivå")
    print("=" * 70)
    by = m.groupby("prob_up").agg(snitt_fwd=("fwd_ret", "mean"),
                                  antal=("fwd_ret", "size")).reset_index()
    for _, r in by.iterrows():
        print(f"  prob_up {r['prob_up']:.3f}:  snitt fwd {r['snitt_fwd']:+6.1%}   (n={int(r['antal']):,})")
    top = m[m["prob_up"] >= hi]["fwd_ret"].mean()
    bot = m[m["prob_up"] < hi]["fwd_ret"].mean()
    print("-" * 70)
    print(f"  Hög prob_up (>= {hi:.2f}):  snitt fwd {top:+.1%}")
    print(f"  Låg prob_up (<  {hi:.2f}):  snitt fwd {bot:+.1%}")
    print(f"  SPREAD (edge):           {top - bot:+.1%}-enheter  "
          f"{'(positiv = modellen rangordnar rätt)' if top > bot else '(NEGATIV = anti-signal!)'}")


if __name__ == "__main__":
    main()
