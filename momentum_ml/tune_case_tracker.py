"""
tune_case_tracker.py – Har caseförändringssignalen (altdata/case_tracker.py)
en ärlig OOS-edge? Validate-first, som backtest_sentiment.py.

Hypotes (Steg 2 i återkopplingen): "Positiv caseförändring leder till bättre
framtida avkastning."

Metod – återanvänder DEN REDAN TESTADE case_tracker.compute()-logiken, kallad
vid historiska snapshot-datum i stället för nu(). compute(now=t) tittar bara på
PM med published < t (fönstren är redan relativa till `now`), så varje snapshot
är automatiskt point-in-time-korrekt – ingen separat läckage-logik att bygga
eller få fel.

Mäter, per snapshot var STEP_WEEKS:e vecka i OOS-fönstret:
  1) Spread: förbättrat vs försämrat, FORWARD_WEEKS framåtavkastning
  2) IC: score (kontinuerlig) vs framåtavkastning, Spearman, poolat + per år
  3) Hit rate: andel förbättrat med positiv fwd-avkastning, försämrat med negativ
  4) Baskorgarnas kumulativa kurva + maxDD (förbättrat vs försämrat, likaviktat)

Körs på Pi:n efter fetch + score (kan ta en stund – en compute()-snapshot
skannar hela sentiment-cachen):

    /opt/momentum/venv/bin/python tune_case_tracker.py large
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import numpy as np
import pandas as pd
import config
from data.data_loader import (
    fetch_weekly_data, filter_liquid_universe, filter_active_universe, load_sweden_universe,
)
from altdata.case_tracker import compute as case_compute

STEP_WEEKS = 4   # snapshot-intervall (kostnad: en full cache-skanning per snapshot)


def main():
    segment = sys.argv[1] if len(sys.argv) > 1 else config.DEFAULT_SEGMENT
    seg = config.SEGMENTS.get(segment) or config.SEGMENTS[config.DEFAULT_SEGMENT]
    print(f"[Segment] {segment} ({seg['label']})")

    tickers, sector_map, _, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    config.SECTOR_MAP.update(sector_map)
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)
    if not data:
        print("[FEL] Inget prisdata.")
        return

    fwd = config.FORWARD_WEEKS
    oos_start = pd.Timestamp(config.SENTIMENT_OOS_START)
    all_dates = sorted(set().union(*[set(d.index) for d in data.values()]))
    all_dates = [pd.Timestamp(d) for d in all_dates if pd.Timestamp(d) >= oos_start]
    snapshots = all_dates[::STEP_WEEKS]
    print(f"[snapshots] {len(snapshots)} st, var {STEP_WEEKS}:e vecka, "
          f"{snapshots[0].date() if snapshots else '–'}–{snapshots[-1].date() if snapshots else '–'}")

    rows = []
    for i, t0 in enumerate(snapshots):
        try:
            cases = case_compute(now=t0.to_pydatetime())
        except Exception as e:  # noqa: BLE001
            print(f"  [{t0.date()}] hoppar (fel: {e})")
            continue
        if not cases:
            continue
        for c in cases:
            tk = c["ticker"]
            if tk not in data:
                continue
            close = data[tk]["Close"]
            idx = close.index.searchsorted(t0, side="right")
            if idx + fwd >= len(close):
                continue
            fwd_ret = float(close.iloc[idx + fwd] / close.iloc[idx] - 1)
            rows.append({"date": t0, "ticker": tk, "status": c["status"], "score": c["score"],
                         "fwd_ret": fwd_ret})
        if (i + 1) % 20 == 0:
            print(f"  ...{i+1}/{len(snapshots)} snapshots, {len(rows)} observationer hittills")

    ev = pd.DataFrame(rows)
    if ev.empty:
        print("\n[FEL] Inga matchande observationer – kör mfn_fetch + sentiment score + "
              "case_tracker build på fler bolag/perioder först.")
        return
    print(f"\n{len(ev)} bolag-snapshot-observationer, {ev['ticker'].nunique()} bolag")

    # ── 1. Spread ──────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print(f"  SPREAD – {fwd}v framåtavkastning per case-status")
    print("=" * 72)
    for status in ("förbättrat", "oförändrat", "försämrat"):
        s = ev[ev["status"] == status]["fwd_ret"]
        if len(s):
            print(f"  {status:<12} snitt {s.mean():+6.1%}  median {s.median():+6.1%}  (n={len(s):,})")
    imp = ev[ev["status"] == "förbättrat"]["fwd_ret"]
    wor = ev[ev["status"] == "försämrat"]["fwd_ret"]
    if len(imp) >= 15 and len(wor) >= 15:
        spread = imp.mean() - wor.mean()
        print("-" * 72)
        print(f"  SPREAD (förbättrat − försämrat): {spread:+.1%}-enheter  "
              f"{'(positiv = hypotesen håller)' if spread > 0 else '(NEGATIV = ingen/omvänd edge)'}")
    else:
        print(f"\n  För få event (förbättrat n={len(imp)}, försämrat n={len(wor)}) för slutsats.")

    # ── 2. IC (poolat + per år) ────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("  IC – score (kontinuerlig) vs framåtavkastning, Spearman")
    print("=" * 72)
    changed = ev[ev["status"] != "oförändrat"]
    if len(changed) >= 20:
        ic = changed["score"].rank().corr(changed["fwd_ret"].rank())
        print(f"  Poolat IC: {ic:+.3f}  (n={len(changed):,})")
        print("  Per år:")
        changed = changed.copy()
        changed["year"] = changed["date"].dt.year
        for y, g in changed.groupby("year"):
            if len(g) >= 15:
                yic = g["score"].rank().corr(g["fwd_ret"].rank())
                print(f"    {y}: IC {yic:+.3f}  (n={len(g)})")
    else:
        print(f"  För få observationer (n={len(changed)}) för IC.")

    # ── 3. Hit rate ────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("  HIT RATE – rätt tecken på framåtavkastningen")
    print("=" * 72)
    if len(imp):
        print(f"  Förbättrat → positiv fwd-avkastning: {(imp > 0).mean():.0%}  (n={len(imp)})")
    if len(wor):
        print(f"  Försämrat  → negativ fwd-avkastning: {(wor < 0).mean():.0%}  (n={len(wor)})")

    # ── 4. Baskorgar: kumulativ kurva + maxDD ────────────────────────────────
    print("\n" + "=" * 72)
    print(f"  BASKORGAR (likaviktat, {fwd}v-hållperiod, ombalans var {STEP_WEEKS}:e vecka)")
    print("=" * 72)
    for status in ("förbättrat", "försämrat"):
        sub = ev[ev["status"] == status]
        if sub.empty:
            continue
        basket = sub.groupby("date")["fwd_ret"].mean()
        eq = (1 + basket.fillna(0)).cumprod()
        dd = (eq / eq.cummax() - 1).min()
        total = eq.iloc[-1] - 1 if len(eq) else float("nan")
        print(f"  {status:<12} total {total:+.1%}  maxDD {dd:+.1%}  ({len(basket)} ombalanser)")

    print("""
  Dom: positiv spread + |IC|≥0.05 (stabilt tecken över år) + hit rate klart
  över 50% → hypotesen håller, caseförändringssignalen har en ärlig OOS-edge
  och kan tas in som viktad komponent (t.ex. i sammanvägningen/kvant-
  screenern, aldrig som ensam köp-/säljgrund). Annars: observationsverktyg
  kvar i appen, men inget som får flytta en enda krona ännu.""")


if __name__ == "__main__":
    main()
