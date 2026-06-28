"""
tune_gate.py – A/B:ar momentum-kvalitetsgrinden (+ villkorad kontant) mot
alltid-investerad baslinje.

Hypotes (din observation): alltid-investerad topp-N späder ut de få äkta
vinnarna med "minst dåliga" namn när momentum är ont om. Grinden håller bara
namn med genuint momentum och låter kontanter byggas annars – koncentrera i det
som faktiskt trendar (jfr kap-viktning).

Grinden ändrar bara SIZING (ej modellen) → ingen omträning. Laddar sparad modell,
bygger om signals per inställning och backtestar. "Invested" visar hur mycket
kontant som byggs; holdout/alfa avgör om det lönar sig. Kör på Pi:n efter träning:

    /opt/momentum/venv/bin/python tune_gate.py [large|small]
"""
import sys
sys.path.insert(0, '.')
import pandas as pd
import config
from data.data_loader import (
    fetch_weekly_data, filter_liquid_universe, filter_active_universe, load_sweden_universe,
)
from features.feature_engineering import build_all_features, attach_categorical_features, FEATURE_COLS
from models.lgbm_model import MomentumLGBM
from models.ensemble import MomentumEnsemble, build_full_output
from backtest.backtester import MomentumBacktester
from backtest.benchmark import benchmark_report

# (etikett, grind på?, min-momentum, läge, concentrate-tak). Baslinjen först.
SETTINGS = [
    ("av (baslinje)",       False, 0.0,  "cash",        0.0),
    ("grind+kontant >0",    True,  0.0,  "cash",        0.0),
    ("grind+kontant >5%",   True,  0.05, "cash",        0.0),
    ("grind+koncentr >0",   True,  0.0,  "concentrate", 0.34),
    ("grind+koncentr >5%",  True,  0.05, "concentrate", 0.34),
    ("grind+koncentr 100/2",True,  0.05, "concentrate", 0.50),
]


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
    feature_dfs = {t: f.assign(ticker=t) for t, f in feats.items()}

    lgbm = MomentumLGBM.load(f"{config.RESULTS_DIR}/lgbm_model.pkl")
    preds = {t: lgbm.predict(f.dropna(subset=FEATURE_COLS[:5])) for t, f in feats.items() if len(f) > 0}
    hw = config.HOLDOUT_WEEKS

    def evaluate(enabled, gate_min, mode, cap):
        config.MOMENTUM_GATE_ENABLED = enabled
        config.MOMENTUM_GATE_MIN = gate_min
        config.MOMENTUM_GATE_MODE = mode
        if cap:
            config.MOMENTUM_GATE_CONCENTRATE_CAP = cap
        sig = build_full_output(preds, None, feature_dfs, MomentumEnsemble(), ta_filter="score")
        bt = MomentumBacktester(sig, data, market_filter=True)
        bt.run()
        s = bt.statistics()
        b = benchmark_report(bt._results["portfolio_value"], data)
        pv = bt._results["portfolio_value"]
        ho = pv.iloc[-hw:] if len(pv) > hw else pv
        ho_cagr = (ho.iloc[-1] / ho.iloc[0]) ** (52 / max(len(ho) - 1, 1)) - 1
        return s["CAGR"], s["Sharpe"], s["Max Drawdown"], s.get("Invested", "—"), b["alpha_cagr"], ho_cagr

    print("\n" + "=" * 86)
    print(f"  MOMENTUM-GRIND-SVEP ({seg['label']}) – koncentrera i äkta momentum, kontant annars")
    print("=" * 86)
    print(f"  {'inställning':>16} {'CAGR':>7} {'Sharpe':>7} {'MaxDD':>8} {'Invest':>7} {'alfa':>7} {'holdout':>8}")
    print("-" * 86)
    base_alpha = None
    for label, enabled, gate_min, mode, cap in SETTINGS:
        cagr, sharpe, maxdd, invested, alpha, ho = evaluate(enabled, gate_min, mode, cap)
        note = ""
        if base_alpha is None:
            base_alpha = alpha
        elif alpha > base_alpha:
            note = "  <-- bättre alfa än baslinjen"
        print(f"  {label:>16} {cagr:>7} {sharpe:>7} {maxdd:>8} {invested:>7} "
              f"{alpha*100:>+6.1f}% {ho*100:>+7.1f}%{note}")
    config.MOMENTUM_GATE_ENABLED = False
    print("-" * 86)
    print("  'Invest' = genomsnittlig investerad andel (resten kontant). Behåll grinden")
    print("  bara om alfa/holdout förbättras – inte om kontant-draget kostar mer än det räddar.")


if __name__ == "__main__":
    main()
