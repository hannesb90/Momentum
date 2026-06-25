"""
main.py – Kör hela momentum ML-pipelinen.

Användning:
  python main.py
  python main.py --tickers AAPL MSFT NVDA --start 2012-01-01
  python main.py --skip-lstm          # bara LGBM
  python main.py --predict-only       # ladda sparade modeller, generera signaler
"""

import argparse
import sys
import os
import pandas as pd
from pathlib import Path

import config
from data.data_loader import fetch_weekly_data, build_universe_df
from features.feature_engineering import build_all_features, to_model_df, FEATURE_COLS
from models.lgbm_model import MomentumLGBM
from models.lstm_model import MomentumLSTM
from models.ensemble import MomentumEnsemble, build_full_output
from backtest.backtester import MomentumBacktester


def parse_args():
    p = argparse.ArgumentParser(description="Momentum ML Trading System")
    p.add_argument("--tickers",      nargs="+", default=config.DEFAULT_TICKERS)
    p.add_argument("--start",        default=config.START_DATE)
    p.add_argument("--end",          default=config.END_DATE)
    p.add_argument("--skip-lstm",    action="store_true", help="Kör bara LGBM")
    p.add_argument("--predict-only", action="store_true", help="Ladda modeller, ingen träning")
    p.add_argument("--no-cache",     action="store_true", help="Hämta ny data (ignorera cache)")
    return p.parse_args()


def main():
    args = parse_args()
    Path(config.CACHE_DIR).mkdir(exist_ok=True)
    Path(config.RESULTS_DIR).mkdir(exist_ok=True)

    print("\n" + "="*60)
    print("  ML MOMENTUM TRADING SYSTEM")
    print("="*60)
    print(f"  Tickers : {args.tickers}")
    print(f"  Period  : {args.start} → {args.end or 'idag'}")
    print(f"  LSTM    : {'nej' if args.skip_lstm else 'ja'}")
    print("="*60 + "\n")

    # ── 1. Data ───────────────────────────────────────────────────────────────
    print("STEG 1: Hämtar data...")
    data = fetch_weekly_data(
        args.tickers,
        start=args.start,
        end=args.end,
        use_cache=not args.no_cache,
    )

    # ── 2. Features ───────────────────────────────────────────────────────────
    print("\nSTEG 2: Feature engineering...")
    all_features = build_all_features(data)
    model_df     = to_model_df(all_features)
    print(f"  Dataset: {len(model_df):,} samples × {model_df[FEATURE_COLS].shape[1]} features")

    # ── 3. LightGBM ───────────────────────────────────────────────────────────
    print("\nSTEG 3: Tränar LightGBM (walk-forward)...")
    lgbm = MomentumLGBM()

    if not args.predict_only:
        lgbm.fit_walk_forward(model_df)
        lgbm.save()
        lgbm.print_feature_importance(top_n=15)
    else:
        lgbm = MomentumLGBM.load()
        print("  [LGBM] Laddade sparad modell.")

    lgbm_preds_by_ticker = {}
    for ticker, feat_df in all_features.items():
        feat_df_clean = feat_df.dropna(subset=FEATURE_COLS[:5])
        if len(feat_df_clean) > 0:
            lgbm_preds_by_ticker[ticker] = lgbm.predict(feat_df_clean)

    # ── 4. LSTM ───────────────────────────────────────────────────────────────
    lstm_preds_by_ticker = {}

    if not args.skip_lstm:
        print("\nSTEG 4: Tränar LSTM...")
        lstm = MomentumLSTM()

        if not args.predict_only:
            # Enkel train/val-split (sista 20% = validering)
            split = int(len(model_df) * 0.8)
            train_df = model_df.iloc[:split]
            val_df   = model_df.iloc[split:]
            lstm.fit(train_df, val_df)
            lstm.save()
        else:
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

    # ── 5. Ensemble + full output ─────────────────────────────────────────────
    print("\nSTEG 5: Ensemble + positionssizing...")
    ensemble   = MomentumEnsemble()
    signals_df = build_full_output(
        lgbm_preds_by_ticker,
        lstm_preds_by_ticker if not args.skip_lstm else None,
        {t: df.assign(ticker=t) for t, df in all_features.items()},
        ensemble,
    )

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
    backtester.plot(save_path=f"{config.RESULTS_DIR}/backtest.png")

    results.to_csv(f"{config.RESULTS_DIR}/portfolio.csv")
    print(f"\n  Resultat sparade i: {config.RESULTS_DIR}/")
    print("\nKLAR!\n")


if __name__ == "__main__":
    main()
