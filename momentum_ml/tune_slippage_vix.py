"""
tune_slippage_vix.py – A/B:ar VIX-driven dynamisk spread/slippage mot
baslinjen med fast spread.

_half_spread() (config.py) fångar redan TVÄRSNITTS-variation (småbolag
dyrare att handla än storbolag, via ADV) men INTE TIDSVARIATION - den
implicita spreaden vidgas historiskt kraftigt när marknaden panikar. Det här
multiplicerar slippage+halv-spread med SLIPPAGE_VIX_STRESS_MULT under samma
VIX+kreditspread-stress-flagga etf_rotation.py:s regim-gate redan använder
(macro_data.stress_series, ingen ny datakälla).

Effekten är i sig en KOSTNAD (backtesten blir strikt dyrare i stress-
perioder) - poängen är INTE att höja CAGR, utan att inte KÖPA/SÄLJA för
billigt i turbulenta perioder där spreadarna historiskt vidgats (annars
överdriver backtesten hur mycket som faktiskt gick att exekvera till de
priserna). Rätt fråga är alltså: hur mycket sämre ser strategin ut när
kostnaden är mer verklighetstrogen, INTE "vilken multipel maximerar CAGR"
(en högre multipel gör ALLTID backtesten sämre eller oförändrad, aldrig
bättre - det är bara en kostnad, ingen edge att optimera).

Laddar SPARAD modell + cache (ingen omträning), bygger signals en gång och
kör om backtesten per multipel. Kräver macro_data.py:s cache
(kör 'python macro_data.py fetch' först om den saknas). Kör på Pi:n:

    /opt/momentum/venv/bin/python tune_slippage_vix.py [large|small]
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

# (etikett, enabled, mult). Baslinjen (fast spread, av) först.
SETTINGS = [
    ("av (fast spread)", False, None),
    ("1.5x under stress", True,  1.5),
    ("2.0x under stress", True,  2.0),
    ("2.5x under stress", True,  2.5),
    ("3.0x under stress", True,  3.0),
]


def main():
    segment = sys.argv[1] if len(sys.argv) > 1 else config.DEFAULT_SEGMENT
    seg = config.SEGMENTS.get(segment) or config.SEGMENTS[config.DEFAULT_SEGMENT]
    config.RESULTS_DIR = seg["results_dir"]
    config.MAX_POSITIONS = seg.get("max_positions", config.MAX_POSITIONS)
    config.CONVICTION_BLEND = seg.get("conviction_blend", config.CONVICTION_BLEND)
    print(f"[Segment] {segment} ({seg['label']}) – modell: {config.RESULTS_DIR}/lgbm_model.pkl")

    try:
        import macro_data
        macro_data.load()
    except FileNotFoundError:
        print("[VARNING] macro_data-cache saknas - kör 'python macro_data.py fetch' först. Avbryter.")
        return

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

    # Signals byggs en gång – spreaden påverkar bara EXEKVERINGSKOSTNADEN i
    # backtesten, inte vilka bolag modellen rankar högt.
    sig = build_full_output(preds, None, feature_dfs, MomentumEnsemble(), ta_filter="score")
    hw = config.HOLDOUT_WEEKS

    def evaluate(enabled, mult):
        config.SLIPPAGE_VIX_ENABLED = enabled
        if mult is not None:
            config.SLIPPAGE_VIX_STRESS_MULT = mult
        bt = MomentumBacktester(sig, data, market_filter=True)
        bt.run()
        s = bt.statistics()
        b = benchmark_report(bt._results["portfolio_value"], data)
        pv = bt._results["portfolio_value"]
        ho = pv.iloc[-hw:] if len(pv) > hw else pv
        ho_cagr = (ho.iloc[-1] / ho.iloc[0]) ** (52 / max(len(ho) - 1, 1)) - 1
        n_stress = int(bt._stress_series.sum()) if bt._stress_series is not None else 0
        return s["CAGR"], s["Sharpe"], s["Sortino"], s["Max Drawdown"], b["alpha_cagr"], ho_cagr, n_stress

    print("\n" + "=" * 90)
    print(f"  VIX-DRIVEN SPREAD-SVEP ({seg['label']}) – hur mycket dyrare/sämre ser strategin ut")
    print("  med verklighetstrogen exekveringskostnad i stress-perioder?")
    print("=" * 90)
    print(f"  {'multipel':>18} {'CAGR':>7} {'Sharpe':>7} {'Sortino':>8} {'MaxDD':>8} "
          f"{'alfa':>7} {'holdout':>8} {'stress-v':>9}")
    print("-" * 90)
    for label, enabled, mult in SETTINGS:
        cagr, sharpe, sortino, maxdd, alpha, ho, n_stress = evaluate(enabled, mult)
        print(f"  {label:>18} {cagr:>7} {sharpe:>7} {sortino:>8} {maxdd:>8} "
              f"{alpha*100:>+6.1f}% {ho*100:>+7.1f}% {n_stress:>9}")
    # återställ default
    config.SLIPPAGE_VIX_ENABLED = False
    print("-" * 90)
    print("  OBS: det här är INTE ett svep att maximera - en högre multipel gör ALLTID")
    print("  backtesten lika bra eller sämre (kostnaden kan bara öka). Poängen är att se")
    print("  HUR KÄNSLIG strategin är för realistisk stress-spread: en liten degradering =")
    print("  strategin churnar inte mycket i stress-perioder (robust); en stor degradering =")
    print("  strategin handlar aktivt rakt in i de dyraste veckorna (sårbar, värt att åtgärda).")


if __name__ == "__main__":
    main()
