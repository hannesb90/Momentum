"""
tune_isk_tax.py – Dokumenterar ISK-schablonskattens kapitaldrag mot en
oskattad baseline. INTE ett svep att optimera - schablonskatten är
lagstadgad (statslåneränta + 1 %-enhet, golv 1.25%, 30% skatt), inte en
fri parameter. Poängen är att VISA hur mycket den urholkar långsiktig
avkastning, så jämförelser mot en (också skattad) passiv benchmark blir
verklighetstrogna - se config.py:s ISK_TAX_ENABLED-docstring för formeln/
källorna och OBS-noten om luckor i ISK_SLR_BY_YEAR (2010-2013 kunde inte
verifieras härifrån).

Laddar SPARAD modell + cache (ingen omträning), bygger signals en gång och
kör om backtesten av/på. Kör på Pi:n:

    /opt/momentum/venv/bin/python tune_isk_tax.py [large|small]
"""
import sys
sys.path.insert(0, '.')
import config
from data.data_loader import (
    fetch_weekly_data, filter_liquid_universe, filter_active_universe, load_sweden_universe,
)
from features.feature_engineering import (
    build_all_features, attach_categorical_features, attach_fundamentals_features, FEATURE_COLS,
)
from models.lgbm_model import MomentumLGBM
from models.ensemble import MomentumEnsemble, build_full_output
from backtest.backtester import MomentumBacktester
from backtest.benchmark import benchmark_report


def main():
    segment = sys.argv[1] if len(sys.argv) > 1 else config.DEFAULT_SEGMENT
    seg = config.SEGMENTS.get(segment) or config.SEGMENTS[config.DEFAULT_SEGMENT]
    config.RESULTS_DIR = seg["results_dir"]
    config.MAX_POSITIONS = seg.get("max_positions", config.MAX_POSITIONS)
    config.CONVICTION_BLEND = seg.get("conviction_blend", config.CONVICTION_BLEND)
    print(f"[Segment] {segment} ({seg['label']}) – modell: {config.RESULTS_DIR}/lgbm_model.pkl")

    tickers, sector_map, cap_tier_map, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    config.SECTOR_MAP.update(sector_map)
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)

    feats = build_all_features(data)
    feats = attach_categorical_features(feats, sector_map=config.SECTOR_MAP, cap_tier_map=cap_tier_map)
    # Tillväxt-features (rev_growth_yoy/eps_growth_yoy/days_since_report) ur MFN-
    # rapporternas hårddata - modellen förväntar sig dessa kolumner (FEATURE_COLS),
    # se main.py:s STEG 2 (samma anropsordning). Saknas underlaget blir kolumnerna
    # bara NaN, ingen krasch.
    feats = attach_fundamentals_features(feats, segment=segment)
    feature_dfs = {t: f.assign(ticker=t) for t, f in feats.items()}

    lgbm = MomentumLGBM.load(f"{config.RESULTS_DIR}/lgbm_model.pkl")
    preds = {t: lgbm.predict(f.dropna(subset=FEATURE_COLS[:5])) for t, f in feats.items() if len(f) > 0}
    sig = build_full_output(preds, None, feature_dfs, MomentumEnsemble(), ta_filter="score")
    hw = config.HOLDOUT_WEEKS

    warned_years_seen = set()

    def evaluate(enabled):
        config.ISK_TAX_ENABLED = enabled
        bt = MomentumBacktester(sig, data, market_filter=True)
        bt.run()
        warned_years_seen.update(getattr(bt, "_isk_warned_years", set()))
        s = bt.statistics()
        b = benchmark_report(bt._results["portfolio_value"], data)
        pv = bt._results["portfolio_value"]
        ho = pv.iloc[-hw:] if len(pv) > hw else pv
        ho_cagr = (ho.iloc[-1] / ho.iloc[0]) ** (52 / max(len(ho) - 1, 1)) - 1
        return s["CAGR"], s["Sharpe"], s["Max Drawdown"], b["alpha_cagr"], ho_cagr, pv.iloc[-1]

    print("\n" + "=" * 78)
    print(f"  ISK-SKATTEDRAG ({seg['label']}) – oskattad vs. schablonbeskattad baslinje")
    print("=" * 78)
    print(f"  {'':>18} {'CAGR':>7} {'Sharpe':>7} {'MaxDD':>8} {'alfa':>7} {'holdout':>8} {'slutkapital':>14}")
    print("-" * 78)
    for label, enabled in (("utan ISK-skatt", False), ("med ISK-skatt", True)):
        cagr, sharpe, maxdd, alpha, ho, final = evaluate(enabled)
        print(f"  {label:>18} {cagr:>7} {sharpe:>7} {maxdd:>8} {alpha*100:>+6.1f}% "
              f"{ho*100:>+7.1f}% {final:>14,.0f}".replace(",", " "))
    config.ISK_TAX_ENABLED = False   # återställ default
    print("-" * 78)
    if warned_years_seen:
        print(f"  OBS: statslåneräntan saknades i config.ISK_SLR_BY_YEAR för {sorted(warned_years_seen)} "
              f"- lagstadgat golv (1.25%) användes som fallback de åren, inte en uppmätt siffra.")
    print("  VIKTIGT: jämför bara mot en benchmark som ANTINGEN OCKSÅ är ISK-skattad, eller")
    print("  ingendera är det. Att jämföra en skattad strategi mot ett oskattat index är att")
    print("  jämföra äpplen mot päron - se användarens ursprungliga poäng om detta.")


if __name__ == "__main__":
    main()
