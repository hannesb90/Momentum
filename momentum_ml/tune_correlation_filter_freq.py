"""
tune_correlation_filter_freq.py – Hur ofta slår `_correlation_filter` ihop
kandidater, och hur många EFFEKTIVA unika innehav har portföljen då jämfört
med MAX_POSITIONS? [SCN-KÖP-2] steg 1 i docs/EDGE_RISK_SCENARIO_TESTKO.md.

BAKGRUND: `backtest/backtester.py::_correlation_filter` slår ihop vikt på
"vinnaren" av ett kraftigt korrelerat par (MAX_PAIRWISE_CORRELATION) men
ERSÄTTER INTE föloraren med nästa lediga rankade kandidat - portföljen kan
sluta med FÄRRE effektiva unika namn än MAX_POSITIONS trots fler kvalificerade
kandidater i kön. Steg 1 (denna körning) är REN MÄTNING - ingen ny logik,
importerar och anropar den FAKTISKA produktionsfunktionen direkt (inte en
omskriven kopia), mot FAKTISKA historiska modellsignaler.

METOD (kausal, ingen ny träning): återanvänder `results/signals.csv`
(large-segmentets redan genererade historiska signaler) + cachad prisdata
(`fetch_weekly_data`, `use_cache=True`, ingen nätåtkomst om redan cachad).
Bygger en `MomentumBacktester`-instans (bara för att återanvända EXAKT
samma `_correlation_filter`-metod som produktionen kör, ingen egen kopia)
och kör den på VARJE schemalagd rebalanseringsdatum (samma `i % REBALANCE_
WEEKS == 0`-logik som backtesterns egen `run()`), med target_weights byggda
exakt som i `run()` (pred_signal==1, position_size>0).

Kör:
    /opt/momentum/venv/bin/python3 tune_correlation_filter_freq.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, ".")
import config
from data.data_loader import fetch_weekly_data, load_sweden_universe
from backtest.backtester import MomentumBacktester


def main() -> None:
    seg = config.SEGMENTS["large"]
    if "max_positions" in seg:
        config.MAX_POSITIONS = seg["max_positions"]
    if "forward_weeks" in seg:
        config.FORWARD_WEEKS = seg["forward_weeks"]
        config.REBALANCE_WEEKS = seg["rebalance_weeks"]
    if "atr_stop_enabled" in seg:
        config.ATR_STOP_ENABLED = seg["atr_stop_enabled"]
    if "market_filter_exposure" in seg:
        config.MARKET_FILTER_EXPOSURE = seg["market_filter_exposure"]
    _, sector_map, _, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    config.SECTOR_MAP.update(sector_map)
    sig_path = Path("results/signals.csv")
    if not sig_path.exists():
        print(f"{sig_path} saknas.")
        return
    signals = pd.read_csv(sig_path, parse_dates=["Date"], index_col="Date")
    tickers = sorted(signals["ticker"].dropna().unique())
    print(f"[data] {len(signals)} signalrader, {len(tickers)} tickers, "
          f"{signals.index.min().date()} -> {signals.index.max().date()}")

    print("[data] hämtar prisdata (cachad)...")
    price_data = fetch_weekly_data(tickers, use_cache=True)
    price_data = {t: d for t, d in price_data.items() if d is not None and "Close" in d}
    print(f"[data] {len(price_data)} tickers med prisdata")

    bt = MomentumBacktester(signals, price_data)

    dates = signals.index.unique().sort_values()
    rebalance_weeks = max(int(getattr(config, "REBALANCE_WEEKS", 1)), 1)
    mode = getattr(config, "REBALANCE_MODE", "calendar")
    print(f"[config] REBALANCE_WEEKS={rebalance_weeks}  REBALANCE_MODE={mode}  "
          f"MAX_PAIRWISE_CORRELATION={config.MAX_PAIRWISE_CORRELATION}  "
          f"MAX_POSITIONS={config.MAX_POSITIONS}  "
          f"CORRELATION_LOOKBACK_WEEKS={config.CORRELATION_LOOKBACK_WEEKS}")
    if mode != "calendar":
        print(f"  OBS: REBALANCE_MODE={mode!r}, inte 'calendar' - _correlation_filter "
              "anropas ändå bara på schemalagda 'calendar'-datum i denna mätning "
              "(_event_rebalance har en egen kod-väg, mäts inte här).")

    rows = []
    for i, date in enumerate(dates):
        if i % rebalance_weeks != 0:
            continue
        day = signals.loc[date]
        if isinstance(day, pd.Series):
            day = day.to_frame().T
        target_weights = {}
        for _, row in day.iterrows():
            if row.get("pred_signal") == 1 and row.get("position_size", 0) > 0:
                target_weights[row["ticker"]] = row["position_size"]
        n_before = len(target_weights)
        if n_before < 2:
            continue
        filtered = bt._correlation_filter(target_weights, date)
        n_after = len(filtered)
        merged = n_before - n_after
        rows.append({"date": date, "n_before": n_before, "n_after": n_after, "merged": merged})

    res = pd.DataFrame(rows).set_index("date")
    if res.empty:
        print("Inga rebalanseringsdatum med >=2 kandidater hittades.")
        return

    n_rebal = len(res)
    n_with_merge = int((res["merged"] > 0).sum())
    print("\n" + "=" * 80)
    print("  KORRELATIONSFILTRETS MERGE-FREKVENS (verklig historik, large-segmentet)")
    print("=" * 80)
    print(f"  Rebalanseringstillfällen (>=2 kandidater): {n_rebal}")
    print(f"  Tillfällen med >=1 sammanslagning:         {n_with_merge} "
          f"({n_with_merge / n_rebal:.1%})")
    print(f"  Medel antal sammanslagningar per tillfälle: {res['merged'].mean():.2f}")
    print(f"  Medel n_before (kvalificerade kandidater):  {res['n_before'].mean():.1f}")
    print(f"  Medel n_after (effektiva unika namn):       {res['n_after'].mean():.1f}")
    print(f"  MAX_POSITIONS (large):                      {config.MAX_POSITIONS}")
    shortfall = config.MAX_POSITIONS - res["n_after"]
    shortfall_when_full = shortfall[res["n_before"] >= config.MAX_POSITIONS]
    if len(shortfall_when_full):
        print(f"  Bland tillfällen där >= MAX_POSITIONS kandidater fanns TILLGÄNGLIGA "
              f"({len(shortfall_when_full)} st):")
        print(f"    Medel 'saknade' platser pga merge (ej fyllda av ersättare): "
              f"{shortfall_when_full.clip(lower=0).mean():.2f}")
        print(f"    Andel sådana tillfällen med >=1 saknad plats: "
              f"{(shortfall_when_full > 0).mean():.1%}")

    print("\n  De 10 tillfällena med FLEST sammanslagningar:")
    print(res.sort_values("merged", ascending=False).head(10).to_string())

    print("""
  Tolkning: om "andel tillfällen med >=1 saknad plats" (bland de där nog
  kandidater fanns) är hög, är SCN-KÖP-2 steg 2 (bygg en variant som fyller
  på med nästa okorrelerade kandidat i stället för att bara slå ihop vikt)
  motiverad. Om låg/sällsynt är frågan mest akademisk - notera och gå vidare.""")


if __name__ == "__main__":
    main()
