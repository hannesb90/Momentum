"""
main.py – Kör hela momentum ML-pipelinen.

Användning:
  python main.py
  python main.py --tickers AAPL MSFT NVDA --start 2012-01-01
  python main.py --skip-lstm          # bara LGBM
  python main.py --predict-only       # ladda sparade modeller, generera signaler
"""

import argparse
import gc
import json
import subprocess
import sys
import os
import pandas as pd
from pathlib import Path

import config
from data.data_loader import (
    fetch_weekly_data, build_universe_df, filter_liquid_universe,
    load_sweden_universe,
)
from features.feature_engineering import (
    build_all_features, to_model_df, attach_categorical_features, FEATURE_COLS,
)
from models.lgbm_model import MomentumLGBM
from models.lstm_model import MomentumLSTM
from models.ensemble import MomentumEnsemble, build_full_output
from backtest.backtester import MomentumBacktester
from backtest.bootstrap import print_robustness_report, robustness_report
from backtest.drift_monitor import attach_realized_outcomes, rolling_drift_report, print_drift_summary
from backtest.regime import classify_regimes, regime_breakdown, print_regime_breakdown
from backtest.sector_momentum import sector_momentum_snapshot, print_sector_momentum


def parse_args():
    p = argparse.ArgumentParser(description="Momentum ML Trading System")
    p.add_argument("--tickers",      nargs="+", default=None,
                   help="Egen tickerlista. Om satt åsidosätter den --universe.")
    p.add_argument("--universe",     choices=["sweden"], default="sweden",
                   help="Förbyggt universum (default: 'sweden' - alla svenska börsbolag "
                        "+ fonder, data/sweden_universe.csv + sweden_funds.csv). "
                        "Ignoreras om --tickers anges.")
    p.add_argument("--market-cap",   nargs="+", default=None,
                   choices=["Mega Cap", "Large Cap", "Mid Cap", "Small Cap", "Micro Cap", "Nano Cap"],
                   help="Begränsa --universe till dessa marketcap-kategorier (default: alla)")
    p.add_argument("--start",        default=config.START_DATE)
    p.add_argument("--end",          default=config.END_DATE)
    p.add_argument("--skip-lstm",    action="store_true", help="Kör bara LGBM")
    p.add_argument("--predict-only", action="store_true", help="Ladda modeller, ingen träning")
    p.add_argument("--train-lgbm-only", action="store_true",
                   help="(internt) Tränar bara LightGBM i denna process")
    p.add_argument("--train-lstm-only", action="store_true",
                   help="(internt) Tränar bara LSTM i denna process")
    p.add_argument("--no-cache",     action="store_true", help="Hämta ny data (ignorera cache)")
    p.add_argument("--no-liquidity-filter", action="store_true",
                   help="Kör inte likviditetsfiltret (alla tickers med tillräcklig historik tas med)")
    p.add_argument("--min-turnover", type=float, default=config.UNIVERSE_MIN_AVG_TURNOVER,
                   help="Min genomsnittlig omsättning/vecka (lokal valuta) för att tas med i universumet")
    p.add_argument("--n-trials",     type=int, default=1,
                   help="Antal testade strategier/parameterval, för Deflated Sharpe Ratio")
    p.add_argument("--ta-filter",    choices=["gate", "score"], default=None,
                   help="Valbart TA-bekräftelsefilter ovanpå modellsignalerna: "
                        "'gate' nollar köpsignaler som tekniska analysen inte bekräftar, "
                        "'score' skalar position_size med andelen uppfyllda TA-villkor. "
                        "Default: av.")
    p.add_argument("--ta-strictness", choices=["loose", "moderate", "strict"],
                   default=config.TA_FILTER_STRICTNESS,
                   help="Hur strikt TA-filtret är (default: moderate)")
    return p.parse_args()


def main():
    args = parse_args()
    Path(config.CACHE_DIR).mkdir(exist_ok=True)
    Path(config.RESULTS_DIR).mkdir(exist_ok=True)

    cap_tier_map = {}
    if args.tickers:
        tickers = args.tickers
    elif args.universe == "sweden":
        tickers, sweden_sector_map, cap_tier_map = load_sweden_universe(min_market_cap=args.market_cap)
        config.SECTOR_MAP.update(sweden_sector_map)
    else:
        tickers = config.DEFAULT_TICKERS

    print("\n" + "="*60)
    print("  ML MOMENTUM TRADING SYSTEM")
    print("="*60)
    print(f"  Tickers : {len(tickers)} st" if len(tickers) > 20 else f"  Tickers : {tickers}")
    print(f"  Period  : {args.start} → {args.end or 'idag'}")
    print(f"  LSTM    : {'nej' if args.skip_lstm else 'ja'}")
    print("="*60 + "\n")

    # ── 1. Data ───────────────────────────────────────────────────────────────
    print("STEG 1: Hämtar data...")
    data = fetch_weekly_data(
        tickers,
        start=args.start,
        end=args.end,
        use_cache=not args.no_cache,
    )

    # ── 1.5 Likviditetsfilter ─────────────────────────────────────────────────
    if not args.no_liquidity_filter:
        print("\nSTEG 1.5: Likviditetsfilter...")
        data = filter_liquid_universe(data, min_avg_turnover=args.min_turnover)
        if not data:
            raise RuntimeError(
                "Inga tickers kvar efter likviditetsfiltret – sänk "
                "--min-turnover eller kör med --no-liquidity-filter."
            )

    # ── 2. Features ───────────────────────────────────────────────────────────
    print("\nSTEG 2: Feature engineering...")
    all_features = build_all_features(data)
    all_features = attach_categorical_features(
        all_features, sector_map=config.SECTOR_MAP, cap_tier_map=cap_tier_map,
    )
    model_df     = to_model_df(all_features)
    print(f"  Dataset: {len(model_df):,} samples × {model_df[FEATURE_COLS].shape[1]} features")
    gc.collect()

    # Frusen holdout: de sista HOLDOUT_WEEKS veckorna får modellen aldrig
    # träna på, så backtesten över den perioden är en äkta out-of-sample-test.
    all_dates = model_df.index.unique().sort_values()
    if len(all_dates) > config.HOLDOUT_WEEKS:
        holdout_start = all_dates[-config.HOLDOUT_WEEKS]
        dev_df = model_df[model_df.index < holdout_start]
        print(f"  Frusen holdout: {holdout_start.date()} → slut "
              f"({config.HOLDOUT_WEEKS}v, modellen tränas aldrig på dessa)")
    else:
        holdout_start = None
        dev_df = model_df
        print("  [WARN] För kort historik för en frusen holdout, tränar på all data.")

    # ── 3. LightGBM + LSTM (träning) ─────────────────────────────────────────
    if args.train_lgbm_only:
        print("\nSTEG 3: Tränar LightGBM (walk-forward)...")
        lgbm = MomentumLGBM()
        lgbm.fit_walk_forward(dev_df)
        lgbm.save()
        lgbm.print_feature_importance(top_n=15)
        return

    if args.train_lstm_only:
        print("\nSTEG 4: Tränar LSTM...")
        lstm = MomentumLSTM()
        # Enkel train/val-split (sista 20% av dev-perioden = validering)
        split = int(len(dev_df) * 0.8)
        train_df = dev_df.iloc[:split]
        val_df   = dev_df.iloc[split:]
        lstm.fit(train_df, val_df)
        lstm.save()
        return

    if not args.predict_only:
        # Träning (LGBM, LSTM) och prediktion körs i HELT FRISKA processer
        # var för sig. Bekräftat på Pi 4B (Cortex-A72): körs LightGBMs
        # OpenMP-trådpool och PyTorchs trådpool sekventiellt i samma
        # process kraschar nästa bibliotek med SIGILL – gäller både
        # LGBM-train → LGBM-predict och LGBM-train → LSTM-backward.
        # Trådpool-state överlever uppenbarligen inte en sådan övergång på
        # denna ARM-CPU. Varje steg får därför sin egen process; data-
        # cachen gör att steg 1-2 (hämtning/features) körs snabbt igen.
        base_cmd = [sys.executable, __file__, "--start", args.start,
                    "--min-turnover", str(args.min_turnover)]
        if args.tickers:
            base_cmd += ["--tickers", *args.tickers]
        else:
            base_cmd += ["--universe", args.universe]
            if args.market_cap:
                base_cmd += ["--market-cap", *args.market_cap]
        if args.end:
            base_cmd += ["--end", args.end]
        if args.no_liquidity_filter:
            base_cmd += ["--no-liquidity-filter"]

        print("\n[Main] Tränar LightGBM i ny process...")
        result = subprocess.run(base_cmd + ["--train-lgbm-only"])
        if result.returncode != 0:
            sys.exit(result.returncode)

        if not args.skip_lstm:
            print("\n[Main] Tränar LSTM i ny process...")
            result = subprocess.run(base_cmd + ["--train-lstm-only"])
            if result.returncode != 0:
                sys.exit(result.returncode)
        else:
            print("\nSTEG 4: LSTM hoppas över.")

        print("\n[Main] Träning klar. Kör prediktion/backtest i ny process...")
        cmd = base_cmd + ["--predict-only"]
        if args.skip_lstm:
            cmd.append("--skip-lstm")
        if args.ta_filter:
            cmd += ["--ta-filter", args.ta_filter, "--ta-strictness", args.ta_strictness]
        result = subprocess.run(cmd)
        sys.exit(result.returncode)

    # ── Prediktion (laddar sparade modeller) ─────────────────────────────────
    print("\nSTEG 3: Laddar LightGBM...")
    lgbm = MomentumLGBM.load()
    print("  [LGBM] Laddade sparad modell.")

    lgbm_preds_by_ticker = {}
    for ticker, feat_df in all_features.items():
        feat_df_clean = feat_df.dropna(subset=FEATURE_COLS[:5])
        if len(feat_df_clean) > 0:
            lgbm_preds_by_ticker[ticker] = lgbm.predict(feat_df_clean)

    lstm_preds_by_ticker = {}
    if not args.skip_lstm:
        print("\nSTEG 4: Laddar LSTM...")
        lstm = MomentumLSTM().load()
        print("  [LSTM] Laddade sparad modell.")

        for ticker, feat_df in all_features.items():
            feat_df_clean = feat_df.dropna(subset=FEATURE_COLS[:5])
            if len(feat_df_clean) >= config.LSTM_SEQUENCE_LEN + 10:
                try:
                    lstm_preds_by_ticker[ticker] = lstm.predict(feat_df_clean)
                except Exception as e:
                    print(f"  [WARN] LSTM prediktion för {ticker} misslyckades: {e}")
    else:
        print("\nSTEG 4: LSTM hoppas över.")

    # ── 4.5 Sektor-momentum ───────────────────────────────────────────────────
    print("\nSTEG 4.5: Sektor-momentum...")
    sector_df = sector_momentum_snapshot(all_features)
    print_sector_momentum(sector_df)
    sector_df.to_csv(f"{config.RESULTS_DIR}/sector_momentum.csv", index=False)

    # ── 5. Ensemble + full output ─────────────────────────────────────────────
    print("\nSTEG 5: Ensemble + positionssizing...")
    if args.ta_filter:
        print(f"  TA-filter: {args.ta_filter} (stränghet: {args.ta_strictness})")
    ensemble   = MomentumEnsemble()
    signals_df = build_full_output(
        lgbm_preds_by_ticker,
        lstm_preds_by_ticker if not args.skip_lstm else None,
        {t: df.assign(ticker=t) for t, df in all_features.items()},
        ensemble,
        ta_filter=args.ta_filter,
        ta_strictness=args.ta_strictness,
    )

    # Sektor per ticker – så frontend (portföljfliken) kan visa
    # sektorexponering/koncentrationsrisk över användarens egna innehav,
    # inte bara modellsignal per enskild ticker.
    signals_df["sector"] = signals_df["ticker"].map(config.SECTOR_MAP).fillna("Okänd")

    signals_df.to_csv(f"{config.RESULTS_DIR}/signals.csv")
    print(f"  Signals sparade: {config.RESULTS_DIR}/signals.csv")

    # Visa aktuella signaler (senaste veckan)
    latest = signals_df.groupby("ticker").last().reset_index()
    latest = latest.sort_values("prob_up", ascending=False)
    print("\n  === AKTUELLA SIGNALER (senaste data) ===")
    print(latest[["ticker", "prob_up", "pred_signal", "pred_return", "position_size"]]
          .to_string(index=False, float_format="{:.3f}".format))

    # ── 6. Backtest ───────────────────────────────────────────────────────────
    print("\nSTEG 6: Backtest...")
    backtester = MomentumBacktester(signals_df, data)
    results    = backtester.run()
    backtester.print_statistics()
    overall_stats = backtester.statistics()

    dev_stats = holdout_stats = None
    if holdout_start is not None and (results.index >= holdout_start).any():
        dev_stats = backtester.statistics_for_period(end=holdout_start)
        backtester.print_statistics(dev_stats, title="DEV-PERIOD (tränad på)")
        holdout_stats = backtester.statistics_for_period(start=holdout_start)
        backtester.print_statistics(holdout_stats, title="HOLDOUT (frusen, aldrig sedd)")

    port_rets = results["portfolio_value"].pct_change().dropna()
    print_robustness_report(port_rets, n_trials=args.n_trials)
    robustness = robustness_report(port_rets, n_trials=args.n_trials)

    regimes = classify_regimes(data)
    breakdown = regime_breakdown(port_rets, regimes)
    print_regime_breakdown(breakdown)

    backtester.plot(save_path=f"{config.RESULTS_DIR}/backtest.png")

    results.to_csv(f"{config.RESULTS_DIR}/portfolio.csv")
    breakdown.to_csv(f"{config.RESULTS_DIR}/regime_breakdown.csv")
    print(f"\n  Resultat sparade i: {config.RESULTS_DIR}/")

    # ── 7. Modell-drift ───────────────────────────────────────────────────────
    print("\nSTEG 7: Modell-drift...")
    signals_with_outcomes = attach_realized_outcomes(signals_df, all_features)
    drift_report = rolling_drift_report(signals_with_outcomes)
    print_drift_summary(drift_report)
    drift_report.to_csv(f"{config.RESULTS_DIR}/drift_report.csv")

    # ── 8. Sammanfattning för frontend ───────────────────────────────────────
    drift_valid = drift_report.dropna(subset=["auc"])
    latest_drift = drift_valid.iloc[-1] if not drift_valid.empty else None

    summary = {
        "generated_at":  pd.Timestamp.utcnow().isoformat(),
        "tickers":       tickers,
        "period":        {"start": args.start, "end": args.end},
        "overall":       overall_stats,
        "dev":           dev_stats,
        "holdout":       holdout_stats,
        "robustness":    robustness,
        "drift": None if latest_drift is None else {
            "auc":            float(latest_drift["auc"]),
            "hit_rate":       float(latest_drift["hit_rate"]),
            "auc_floor":      config.DRIFT_AUC_FLOOR,
            "flagged":        bool(latest_drift["flag"]),
            "n_flagged":      int(drift_valid["flag"].sum()),
            "n_periods":      len(drift_valid),
        },
        "sector_momentum": sector_df.head(5).to_dict(orient="records"),
    }
    with open(f"{config.RESULTS_DIR}/stats.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"  Sammanfattning sparad: {config.RESULTS_DIR}/stats.json")

    print("\nKLAR!\n")


if __name__ == "__main__":
    main()
