"""
tune_takeprofit.py – Kalibrera säljvakten empiriskt: vad är rätt gap-tröskel,
och skiljer bekräftelserna (melt-up/trendbrott) vinnare-som-fortsätter från
vinnare-som-rekylerar?

Event-studie över HELA svenska universumet (båda segmenten, cachad veckodata):
  EVENT = en akties 26v-avkastning minus indexets korsar UPP genom tröskeln X.
  MÄTS  = aktiens EXCESS-avkastning mot index 13v respektive 26v EFTER eventet.

  · excess EFTER event ≈ 0 eller positiv  → att sälja på rå styrka KOSTAR
    avkastning (motiverar trappan: armera, sälj inte).
  · excess tydligt negativ vid tröskel X  → gapet i sig är en säljsignal vid X.
  · splitten med/utan bekräftelse visar om melt-up/trendbrott separerar
    "fortsätter" från "rekylerar" – det är HELA värdet av nivå 2/3.

OBS survivorship: universumet är dagens överlevare – aktier som kraschade och
avnoterades EFTER en topp saknas, så 'efter event'-avkastningen är för SNÄLL.
Verkligheten är alltså MER gynnsam för säljvakten än siffrorna här.

Kör på Pi:n från /opt/momentum/src/momentum_ml (cachad data räcker, ~2 min):

    /opt/momentum/venv/bin/python tune_takeprofit.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import config
from data.data_loader import (
    fetch_weekly_data, filter_liquid_universe, filter_active_universe, load_sweden_universe,
)

GAPS = [0.30, 0.40, 0.50, 0.60, 0.80]
LOOKBACK = 26          # säljvaktens fönster
HORIZONS = [13, 26]    # utvärderingshorisonter efter event
BASE_GAP = 0.50        # splitten med/utan bekräftelser körs vid denna tröskel


def main():
    tickers = set()
    for seg in config.SEGMENTS.values():
        t, _, _, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
        tickers.update(t)
    data = fetch_weekly_data(sorted(tickers), start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)

    px = pd.DataFrame({t: d["Close"] for t, d in data.items() if "Close" in d}).sort_index()
    rets = px.pct_change()
    # Likaviktat, winsoriserat, veckorebalanserat return-index (samma metodik som
    # benchmark.equal_weight_index) – gemensam måttstock för gap och excess.
    thr = float(getattr(config, "SUSPICIOUS_JUMP_THRESHOLD", 0.60))
    idx_ret = rets.clip(lower=-thr, upper=thr).mean(axis=1)
    idx = (1 + idx_ret.fillna(0)).cumprod()

    r26 = px / px.shift(LOOKBACK) - 1
    i26 = idx / idx.shift(LOOKBACK) - 1
    gap = r26.sub(i26, axis=0)

    sma20 = px.rolling(20).mean()
    below = px < sma20
    r4 = px / px.shift(4) - 1
    fwd_excess = {}
    for h in HORIZONS:
        fx = (px.shift(-h) / px - 1).sub(idx.shift(-h) / idx - 1, axis=0)
        fwd_excess[h] = fx

    print("\n" + "=" * 74)
    print(f"  SÄLJVAKTS-KALIBRERING · {px.shape[1]} bolag · 26v-gap mot likaviktat index")
    print("  Mäter EXCESS-avkastning mot index EFTER att gapet korsat tröskeln.")
    print("=" * 74)
    print(f"\n  {'tröskel':>8} {'events':>7} | {'excess 13v':>11} {'träff<0':>8} | "
          f"{'excess 26v':>11} {'träff<0':>8}")
    print("  " + "-" * 62)

    def stats_at(mask):
        out = []
        for h in HORIZONS:
            vals = fwd_excess[h].where(mask).stack().dropna()
            if len(vals) == 0:
                out.append((float("nan"), float("nan"), 0))
            else:
                out.append((float(vals.mean()), float((vals < 0).mean()), len(vals)))
        return out

    for x in GAPS:
        armed = gap >= x
        event = armed & ~armed.shift(1).fillna(False)   # korsning upp = nytt event
        (m13, hit13, n), (m26, hit26, _) = stats_at(event)
        print(f"  {x:>7.0%} {n:>7} | {m13:>+10.1%} {hit13:>8.0%} | {m26:>+10.1%} {hit26:>8.0%}")

    print(f"""
  Läs: 'excess 13/26v' = snitt mot index EFTER eventet. 'träff<0' = andel som
  UNDERPRESTERADE index (dvs. hur ofta en försäljning hade varit rätt).
  ≈50% träff och ≈0 excess → gapet ENSAMT är ingen säljsignal (armera, sälj ej).
""")

    # ── Bekräftelse-split vid BASE_GAP ────────────────────────────────────────
    armed = gap >= BASE_GAP
    event = armed & ~armed.shift(1).fillna(False)
    accel = (r4 / r26.replace(0, np.nan)).where(r26 > 0.10) >= \
        float(getattr(config, "TAKEPROFIT_ACCEL_SHARE", 0.5))
    splits = [
        ("melt-up (accel)", event & accel.fillna(False)),
        ("EJ melt-up", event & ~accel.fillna(False)),
        ("trendbrott (<SMA20)", event & below),
        ("trend intakt", event & ~below),
        ("melt-up + trendbrott", event & accel.fillna(False) & below),
    ]
    print(f"  BEKRÄFTELSE-SPLIT vid tröskel {BASE_GAP:.0%}:")
    print(f"  {'villkor':<24} {'events':>7} | {'excess 13v':>11} {'träff<0':>8} | "
          f"{'excess 26v':>11} {'träff<0':>8}")
    print("  " + "-" * 66)
    for lbl, mask in splits:
        (m13, hit13, n), (m26, hit26, _) = stats_at(mask)
        print(f"  {lbl:<24} {n:>7} | {m13:>+10.1%} {hit13:>8.0%} | {m26:>+10.1%} {hit26:>8.0%}")

    print("""
  Domen: om 'trendbrott'/'melt-up'-raderna är TYDLIGT sämre än 'trend intakt'
  gör bekräftelserna sitt jobb – nivå 2/3 säljer rätt vinnare och nivå 1 låter
  compounders löpa. Är raderna lika har bekräftelserna inget värde och vakten
  bör förbli en ren bevakning. (Survivorship gör alla siffror för snälla –
  verklighetens kraschade vinnare saknas i datan.)""")


if __name__ == "__main__":
    main()
