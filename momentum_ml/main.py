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
    filter_active_universe, load_sweden_universe,
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
from backtest.threshold_opt import optimize_buy_threshold, print_threshold_search
from backtest.benchmark import benchmark_report
from backtest.paper_trader import PaperTrader


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
    p.add_argument("--segment", choices=list(config.SEGMENTS.keys()), default=None,
                   help="Storlekssegment (egen modell + egen results-mapp). Sätter "
                        "--market-cap och results-katalog enligt config.SEGMENTS. "
                        f"Val: {', '.join(config.SEGMENTS)}")
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
    p.add_argument("--stale-weeks", type=int, default=config.STALE_MAX_WEEKS,
                   help=f"Ta bort bolag utan ny kurs på fler än så här många veckor "
                        f"(avnoterade/döda; default {config.STALE_MAX_WEEKS})")
    p.add_argument("--rebalance-mode", choices=["calendar", "event"], default=None,
                   help="calendar = var REBALANCE_WEEKS:e vecka (bevisad); event = "
                        "händelsestyrd rotation (tekniken avgör hålltiden). A/B via "
                        "--predict-only. Default = config.REBALANCE_MODE.")
    p.add_argument("--min-history", type=int, default=config.MIN_HISTORY_WEEKS,
                   help="Minsta historik (veckor) för att en ticker ska tas med (default "
                        f"{config.MIN_HISTORY_WEEKS}). OBS: cachen lagrar data efter detta filter "
                        "– kör med --no-cache efter en sänkning för att hämta in fler bolag.")
    p.add_argument("--n-trials",     type=int, default=1,
                   help="Antal testade strategier/parameterval, för Deflated Sharpe Ratio")
    p.add_argument("--optimize-threshold", action=argparse.BooleanOptionalAction, default=False,
                   help="(Legacy) Sök fram en absolut köptröskel. Används EJ i den alltid-"
                        "investerade topp-N-designen, där portföljen alltid håller de N starkaste "
                        "i stället för att kräva en prob_up-gräns. Default: av.")
    p.add_argument("--buy-threshold", type=float, default=None,
                   help="Fast köptröskel för prob_up (åsidosätter sökningen). "
                        "Default: config.BUY_THRESHOLD om sökning är av.")
    p.add_argument("--min-expected-return", type=float, default=config.MIN_EXPECTED_RETURN,
                   help="Minsta förväntade avkastning för att en köpsignal ska utlösas "
                        f"(default {config.MIN_EXPECTED_RETURN:.1%}) – filtrerar bort signaler "
                        "vars uppgång äts upp av transaktionskostnader.")
    p.add_argument("--threshold-objective", choices=["sharpe", "cagr", "calmar"],
                   default=config.THRESHOLD_OBJECTIVE,
                   help="Mål som maximeras när köptröskeln söks fram (default: sharpe)")
    p.add_argument("--market-filter", action=argparse.BooleanOptionalAction, default=True,
                   help="Long-only marknadsfilter: skala ner exponering mot kontanter i svag "
                        "marknad (bull/sidledes/bear) i stället för att blanka (default: på). "
                        "Stäng av med --no-market-filter.")
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
    # Segment: sätt market_cap + results-katalog från config.SEGMENTS. Måste ske
    # FÖRST (innan results skrivs/läses) och driva config.RESULTS_DIR så att
    # modell, signals, stats m.m. hamnar i segmentets egen mapp. Resolvas i varje
    # process (parent + subprocesser) eftersom --segment propageras i base_cmd.
    if args.segment:
        seg = config.SEGMENTS[args.segment]
        args.market_cap = seg["market_cap"]
        config.RESULTS_DIR = seg["results_dir"]
        # Per-segment sizing (se tune_sizing.py-svepet): large=10/0.5, small=20/0.5.
        if "max_positions" in seg:
            config.MAX_POSITIONS = seg["max_positions"]
        if "conviction_blend" in seg:
            config.CONVICTION_BLEND = seg["conviction_blend"]
        print(f"[Segment] {args.segment} ({seg['label']}): "
              f"market_cap={seg['market_cap']} -> {config.RESULTS_DIR}/ "
              f"(N={config.MAX_POSITIONS}, blend={config.CONVICTION_BLEND})")
    # Rebalanseringsläge (calendar/event) – för A/B utan att redigera config.
    if args.rebalance_mode:
        config.REBALANCE_MODE = args.rebalance_mode
    # Gör --min-history globalt verksam (data_loader._clean läser config direkt).
    config.MIN_HISTORY_WEEKS = args.min_history
    # Kostnadsgolv för köpsignaler (ensemble.build_full_output läser config).
    config.MIN_EXPECTED_RETURN = args.min_expected_return
    Path(config.CACHE_DIR).mkdir(exist_ok=True)
    Path(config.RESULTS_DIR).mkdir(parents=True, exist_ok=True)

    cap_tier_map = {}
    if args.tickers:
        tickers = args.tickers
    elif args.universe == "sweden":
        tickers, sweden_sector_map, cap_tier_map, sweden_name_map = load_sweden_universe(min_market_cap=args.market_cap)
        config.SECTOR_MAP.update(sweden_sector_map)
        config.NAME_MAP.update(sweden_name_map)
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

    # ── 1.4 Delisting-filter (avnoterade/döda bolag) ──────────────────────────
    # Ett bolag utan ny kurs på >STALE_MAX_WEEKS veckor tolkas som avnoterat och
    # tas bort – annars dyker döda namn (t.ex. namnbytta/avnoterade) upp som
    # aktuella signaler och förorenar både listan och beräkningarna.
    print("\nSTEG 1.4: Delisting-filter...")
    data = filter_active_universe(data, max_stale_weeks=args.stale_weeks)

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
        lgbm.save(f"{config.RESULTS_DIR}/lgbm_model.pkl")
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
        lstm.save(f"{config.RESULTS_DIR}/lstm_model.pt")
        return

    if not args.predict_only:
        # MINNE: i orkestreringsläget bygger varje subprocess (LGBM/LSTM/predict)
        # om data+features SJÄLV från cachen. Den här parent-processen behöver
        # alltså INTE hålla kvar sina kopior medan barnen kör – annars ligger två
        # fulla universum i RAM samtidigt (parent + barn) och tippar över i swap
        # på en 2GB-Pi (märks tydligt på hela Sverige-universumet, ~483 tickers).
        # Frigör innan vi startar barnen; parent gör bara sys.exit efteråt.
        del data, all_features, model_df, dev_df
        gc.collect()

        # Träning (LGBM, LSTM) och prediktion körs i HELT FRISKA processer
        # var för sig. Bekräftat på Pi 4B (Cortex-A72): körs LightGBMs
        # OpenMP-trådpool och PyTorchs trådpool sekventiellt i samma
        # process kraschar nästa bibliotek med SIGILL – gäller både
        # LGBM-train → LGBM-predict och LGBM-train → LSTM-backward.
        # Trådpool-state överlever uppenbarligen inte en sådan övergång på
        # denna ARM-CPU. Varje steg får därför sin egen process; data-
        # cachen gör att steg 1-2 (hämtning/features) körs snabbt igen.
        base_cmd = [sys.executable, __file__, "--start", args.start,
                    "--min-turnover", str(args.min_turnover),
                    "--stale-weeks", str(args.stale_weeks),
                    "--min-history", str(args.min_history),
                    "--min-expected-return", str(args.min_expected_return)]
        if args.rebalance_mode:
            base_cmd += ["--rebalance-mode", args.rebalance_mode]
        if args.segment:
            # Segmentet re-resolvar market_cap + results_dir i varje subprocess.
            base_cmd += ["--segment", args.segment]
        if args.tickers:
            base_cmd += ["--tickers", *args.tickers]
        else:
            base_cmd += ["--universe", args.universe]
            if args.market_cap and not args.segment:
                base_cmd += ["--market-cap", *args.market_cap]
        if args.end:
            base_cmd += ["--end", args.end]
        if args.no_liquidity_filter:
            base_cmd += ["--no-liquidity-filter"]

        print("\n[Main] Tränar LightGBM i ny process...")
        # --no-cache forwardas ENBART till första processen: den hämtar nytt och
        # skriver cachen, resten (LSTM/predict) läser samma cache.
        lgbm_cmd = base_cmd + ["--train-lgbm-only"]
        if args.no_cache:
            lgbm_cmd += ["--no-cache"]
        result = subprocess.run(lgbm_cmd)
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
        # Köptröskel-inställningar måste följa med till predikt-processen, där
        # signalerna (och därmed sökningen/tröskeln) faktiskt byggs.
        cmd += ["--threshold-objective", args.threshold_objective]
        if not args.market_filter:
            cmd.append("--no-market-filter")
        if not args.optimize_threshold:
            cmd.append("--no-optimize-threshold")
        if args.buy_threshold is not None:
            cmd += ["--buy-threshold", str(args.buy_threshold)]
        if args.n_trials != 1:
            cmd += ["--n-trials", str(args.n_trials)]
        result = subprocess.run(cmd)
        sys.exit(result.returncode)

    # ── Prediktion (laddar sparade modeller) ─────────────────────────────────
    print("\nSTEG 3: Laddar LightGBM...")
    lgbm = MomentumLGBM.load(f"{config.RESULTS_DIR}/lgbm_model.pkl")
    print("  [LGBM] Laddade sparad modell.")

    lgbm_preds_by_ticker = {}
    for ticker, feat_df in all_features.items():
        feat_df_clean = feat_df.dropna(subset=FEATURE_COLS[:5])
        if len(feat_df_clean) > 0:
            lgbm_preds_by_ticker[ticker] = lgbm.predict(feat_df_clean)

    lstm_preds_by_ticker = {}
    if not args.skip_lstm:
        print("\nSTEG 4: Laddar LSTM...")
        lstm = MomentumLSTM().load(f"{config.RESULTS_DIR}/lstm_model.pt")
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
    ensemble    = MomentumEnsemble()
    lstm_preds  = lstm_preds_by_ticker if not args.skip_lstm else None
    feature_dfs = {t: df.assign(ticker=t) for t, df in all_features.items()}

    # ── 5.0 Köptröskel (legacy) ──────────────────────────────────────────────
    # I den alltid-investerade topp-N-designen styr INGEN absolut prob_up-tröskel
    # om kapitalet investeras – portföljen håller alltid de N starkaste bolagen
    # (se ensemble._topn_invested_weights). Tröskelsökningen finns kvar som legacy
    # och körs bara om man uttryckligen anger --optimize-threshold.
    n_trials = args.n_trials
    trial_sr_std = 1.0   # konservativ schablon tills vi kan skatta den empiriskt
    buy_threshold = args.buy_threshold
    threshold_info = None
    if args.optimize_threshold and args.buy_threshold is None:
        print("\n  Söker köptröskel (in-sample/dev)...")
        buy_threshold, grid_results = optimize_buy_threshold(
            lgbm_preds_by_ticker, lstm_preds, feature_dfs, ensemble, data,
            in_sample_end=holdout_start,
            ta_filter=args.ta_filter, ta_strictness=args.ta_strictness,
            objective=args.threshold_objective,
        )
        print_threshold_search(buy_threshold, grid_results, args.threshold_objective)
        n_trials = max(n_trials, len(grid_results))
        # Skatta trial_sr_std för DSR från de testade trösklarnas in-sample-
        # Sharpe (objective='sharpe' ger annualiserad Sharpe per trial; dela med
        # sqrt(52) för per-period-enhet som PSR/DSR använder). Empirisk spridning
        # ger en korrekt kalibrerad Deflated Sharpe i stället för schablonen 1.0.
        if args.threshold_objective == "sharpe":
            import numpy as _np
            finite = [r["score"] for r in grid_results
                      if r["score"] not in (None, float("-inf")) and _np.isfinite(r["score"])]
            if len(finite) >= 2:
                trial_sr_std = max(float(_np.std(finite, ddof=1)) / _np.sqrt(52), 1e-6)
        # JSON tål inte -inf (degenererade trösklar): byt mot None för frontend.
        grid_json = [
            {**r, "score": (None if r["score"] == float("-inf") else round(r["score"], 4))}
            for r in grid_results
        ]
        threshold_info = {
            "optimized": True,
            "objective": args.threshold_objective,
            "grid": grid_json,
            "buy_threshold": buy_threshold,
        }
    print(f"  Portföljläge: alltid-investerad topp-{config.MAX_POSITIONS} "
          f"(conviction-viktat). Kontanter endast via marknadsfiltret. "
          f"Selektivitetsgolv: förv.avk > {config.MIN_EXPECTED_RETURN:.1%}")

    signals_df = build_full_output(
        lgbm_preds_by_ticker,
        lstm_preds,
        feature_dfs,
        ensemble,
        ta_filter=args.ta_filter,
        ta_strictness=args.ta_strictness,
        buy_threshold=buy_threshold,
    )

    # Sektor per ticker – så frontend (portföljfliken) kan visa
    # sektorexponering/koncentrationsrisk över användarens egna innehav,
    # inte bara modellsignal per enskild ticker.
    signals_df["sector"] = signals_df["ticker"].map(config.SECTOR_MAP).fillna("Okänd")
    # Bolagsnamn per ticker – så frontend kan visa namn (inte bara ticker) i
    # listor/aktievyn och låta användaren söka på bolagsnamn. Faller tillbaka på
    # tickern om namn saknas (t.ex. ad-hoc --tickers-körningar).
    signals_df["name"] = signals_df["ticker"].map(config.NAME_MAP).fillna(signals_df["ticker"])

    signals_df.to_csv(f"{config.RESULTS_DIR}/signals.csv")
    print(f"  Signals sparade: {config.RESULTS_DIR}/signals.csv")

    # Per-ticker prishistorik (senaste ~260v) för aktiedetaljvyns kursgraf.
    # Long-format date/ticker/close – kompakt men räcker för utvecklingskurva.
    try:
        price_frames = []
        for ticker, df in data.items():
            s = df["Close"].dropna().tail(260)
            if s.empty:
                continue
            price_frames.append(pd.DataFrame({
                "date": pd.to_datetime(s.index).date.astype(str),
                "ticker": ticker,
                "close": s.values.round(4),
            }))
        if price_frames:
            pd.concat(price_frames, ignore_index=True).to_csv(
                f"{config.RESULTS_DIR}/prices.csv", index=False)
            print(f"  Prishistorik sparad: {config.RESULTS_DIR}/prices.csv "
                  f"({len(price_frames)} tickers)")
    except Exception as e:
        print(f"  [WARN] Kunde inte spara prishistorik (icke-kritiskt): {e}")

    # Visa aktuella signaler (senaste veckan)
    latest = signals_df.groupby("ticker").last().reset_index()
    latest = latest.sort_values("prob_up", ascending=False)
    print("\n  === AKTUELLA SIGNALER (senaste data) ===")
    print(latest[["ticker", "prob_up", "pred_signal", "pred_return", "position_size"]]
          .to_string(index=False, float_format="{:.3f}".format))

    # ── 6. Backtest ───────────────────────────────────────────────────────────
    print("\nSTEG 6: Backtest...")
    if args.market_filter:
        print("  Marknadsfilter: på (long-only de-risking i svag marknad)")
    backtester = MomentumBacktester(signals_df, data, market_filter=args.market_filter)
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
    print_robustness_report(port_rets, n_trials=n_trials, trial_sr_std=trial_sr_std)
    robustness = robustness_report(port_rets, n_trials=n_trials, trial_sr_std=trial_sr_std)

    # ── 6.5 Benchmark (alfa/beta mot passivt köp-och-behåll) ──────────────────
    print("\nSTEG 6.5: Benchmark...")
    bench = benchmark_report(results["portfolio_value"], data)
    benchmark_summary = None
    if bench is not None:
        results["benchmark_value"] = bench["series"].reindex(results.index)
        benchmark_summary = {
            "label":        bench["label"],
            "overall":      bench["overall"],
            "alpha_cagr":   bench["alpha_cagr"],
            "alpha_annual": bench["alpha_annual"],
            "beta":         bench["beta"],
        }
        a = bench["alpha_cagr"]
        print(f"  Benchmark CAGR: {bench['overall']['CAGR']}  |  "
              f"Strategi-alfa: {a:+.1%}  |  beta: {bench['beta']:.2f}")
        if a < 0:
            print("  [VARNING] Negativ alfa: strategin slår inte ett passivt "
                  "köp-och-behåll av universumet.")

    # ── 6.5b OMXS30-linje (visuell jämförelse mot "det du annars köper") ──────
    index_summary = None
    idx_df = data.get(config.INDEX_BENCHMARK_TICKER)
    if idx_df is not None and "Close" in idx_df:
        try:
            idx_close = idx_df["Close"].reindex(
                idx_df.index.union(results.index)).sort_index().ffill().reindex(results.index)
            base = idx_close.dropna().iloc[0] if idx_close.dropna().size else None
            if base:
                idx_value = idx_close / base * config.INITIAL_CAPITAL
                results["omxs30_value"] = idx_value
                weeks = max(len(idx_value.dropna()) - 1, 1)
                idx_cagr = (idx_value.dropna().iloc[-1] / config.INITIAL_CAPITAL) ** (52 / weeks) - 1
                strat_cagr = (results["portfolio_value"].iloc[-1] /
                              results["portfolio_value"].iloc[0]) ** (52 / max(len(results) - 1, 1)) - 1
                index_summary = {
                    "label": config.INDEX_BENCHMARK_LABEL,
                    "CAGR": f"{idx_cagr:.1%}",
                    "alpha_cagr": float(strat_cagr - idx_cagr),
                }
                print(f"  OMXS30 ({config.INDEX_BENCHMARK_LABEL}): {idx_cagr:.1%}/år  |  "
                      f"strategi vs OMXS30: {strat_cagr - idx_cagr:+.1%}")
        except Exception as e:
            print(f"  [WARN] Kunde inte bygga OMXS30-linje (icke-kritiskt): {e}")

    regimes = classify_regimes(data)
    breakdown = regime_breakdown(port_rets, regimes)
    print_regime_breakdown(breakdown)

    # Aktuell marknadsregim + rekommenderad long-only-exponering (för live-
    # signaler, pappershandel och frontend). full=1.0 om filtret är av.
    current_regime = None
    current_exposure = 1.0
    if args.market_filter and len(regimes) > 0:
        try:
            current_regime = regimes.asof(regimes.index.max())
            current_exposure = float(config.MARKET_FILTER_EXPOSURE.get(current_regime, 1.0))
        except Exception:
            current_regime, current_exposure = None, 1.0
    market_summary = {
        "enabled":  bool(args.market_filter),
        "regime":   None if current_regime is None else str(current_regime),
        "exposure": current_exposure,
    }
    print(f"  Aktuell marknadsregim: {current_regime} -> "
          f"rekommenderad exponering {current_exposure:.0%}")

    backtester.plot(save_path=f"{config.RESULTS_DIR}/backtest.png")

    results.to_csv(f"{config.RESULTS_DIR}/portfolio.csv")
    breakdown.to_csv(f"{config.RESULTS_DIR}/regime_breakdown.csv")
    print(f"\n  Resultat sparade i: {config.RESULTS_DIR}/")

    # ── 6.6 Pappershandel (framåtblickande track record) ──────────────────────
    # Stega pappersportföljen ett steg utifrån senaste live-signalerna. Bygger
    # en tidsstämplad out-of-sample-historik som ackumuleras körning för körning.
    try:
        latest_date = signals_df.index.max()
        latest_rows = signals_df.loc[[latest_date]] if latest_date is not None else None
        if latest_rows is not None:
            tw = {r["ticker"]: float(r["position_size"])
                  for _, r in latest_rows.iterrows()
                  if r.get("position_size", 0) and r["position_size"] > 0}
            # Skala live-vikterna med marknadsfiltret så pappersportföljen
            # de-riskar i svag marknad precis som backtesten (ingen blankning).
            if current_exposure < 1.0:
                tw = {t: w * current_exposure for t, w in tw.items()}
            paper = PaperTrader()
            row = paper.step(latest_date, tw, data)
            if row:
                print(f"\nSTEG 6.6: Pappershandel registrerad {row['date']}: "
                      f"värde {row['paper_value']:,.0f} "
                      f"({row['return_since_start']:+.1%} sedan start), "
                      f"{row['n_positions']} positioner.")
            else:
                print("\nSTEG 6.6: Pappershandel – datumet redan registrerat, hoppar.")
    except Exception as e:
        print(f"\nSTEG 6.6: Pappershandel misslyckades (icke-kritiskt): {e}")

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
        "generated_at":  pd.Timestamp.now("UTC").isoformat(),
        "tickers":       tickers,
        "period":        {"start": args.start, "end": args.end},
        "horizon_weeks": config.FORWARD_WEEKS,
        "last_signal_date": str(signals_df.index.max().date()) if len(signals_df) else None,
        "overall":       overall_stats,
        "dev":           dev_stats,
        "holdout":       holdout_stats,
        "benchmark":     benchmark_summary,
        "index_benchmark": index_summary,
        "market":        market_summary,
        "threshold":     threshold_info,
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
