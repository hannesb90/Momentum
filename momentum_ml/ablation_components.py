"""
ablation_components.py – KOMPONENT-ablation: LGBM-only vs LSTM-only vs
ensemble vs ensemble+regimefilter, SAMMA holdout, CAGR/Sharpe/MaxDD/alfa
sida vid sida i en tabell.

Skiljer sig från tune_ablation.py, som skär bort FEATURE-GRUPPER inom LGBM
ensamt ("ablationen körs på LGBM ENBART", se den filens egen docstring) –
den svarar INTE på om LSTM-benet eller regimfiltret faktiskt bidrar med
något. Den här filen gör precis det, en komponent i taget, mot samma
dev/holdout-uppdelning som main.py själv använder.

VARFÖR INTE en "+Kelly"-variant också (Kelly-sizing mot naiv likaviktad
storlek, efterfrågat i samma kodgranskning): en rättvis jämförelse kräver
att ändra hur build_full_output normaliserar portföljvikter
(MIN_POSITION/MAX_POSITIONS-golvet), inte bara byta ut
kelly_position_size mot en konstant – en hastig implementation här hade
riskerat att jämföra äpplen mot päron. Lämnat som en separat, senare
uppgift snarare än att pressa in en missvisande siffra i den här PR:n.

Fyra varianter, alla mot SAMMA dev/holdout-split:
  lgbm_only  – bara LGBM (combine() med lstm_preds=None, se _variant_inputs)
  lstm_only  – bara LSTM, samma mekanism fast tvärtom
  ensemble   – LGBM+LSTM viktat (config.ENSEMBLE_LGBM_WEIGHT/_LSTM_WEIGHT)
  regime     – ensemble + marknadsregimfilter (backtesterns market_filter)

SIGILL-varning (samma som main.py/tune_ablation.py): LightGBM-träning följt
av LightGBM/LSTM-predikt (eller tvärtom) i SAMMA process kraschar på Pi:ns
ARM-CPU. Träning körs därför i en egen subprocess per modell; eval (bara
predikt, ingen träning) laddar BÅDA modellerna i en tredje process – exakt
samma mönster som main.py:s redan fungerande --predict-only-steg (som
redan gör precis detta), inte ett nytt riskabelt mönster.

    python ablation_components.py large
"""
import sys
import json
import subprocess

sys.path.insert(0, ".")
import config  # noqa: E402
from data.data_loader import (  # noqa: E402
    fetch_weekly_data, filter_active_universe, filter_liquid_universe, load_sweden_universe,
)
from features.feature_engineering import build_all_features, attach_categorical_features, to_model_df, FEATURE_COLS  # noqa: E402

_LGBM_MODEL = "ablation_components_lgbm.pkl"
_LSTM_MODEL = "ablation_components_lstm.pt"
_VARIANTS = ["lgbm_only", "lstm_only", "ensemble", "regime"]


def _load(seg: dict):
    tickers, sector_map, cap_tier_map, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    config.SECTOR_MAP.update(sector_map)
    data = fetch_weekly_data(tickers, start=config.START_DATE, end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)
    feats = build_all_features(data)
    feats = attach_categorical_features(feats, sector_map=config.SECTOR_MAP, cap_tier_map=cap_tier_map)
    return data, feats


def _dev_df(model_df):
    dates = model_df.index.unique().sort_values()
    if len(dates) <= config.HOLDOUT_WEEKS:
        return model_df
    return model_df[model_df.index < dates[-config.HOLDOUT_WEEKS]]


def variant_inputs(variant: str, lgbm_preds: dict, lstm_preds: dict):
    """
    Ren funktion (testbar utan riktiga modeller): given en variant och de
    två prediktionsordlistorna, avgör (a) vad som skickas som FÖRSTA/ANDRA
    argument till build_full_output (combine() bryr sig bara om att
    input-dictar har prob_up/pred_return-kolumner, inte VILKEN modell som
    producerade dem – att skicka LSTM:s prediktioner som "första" argument
    med lstm_preds=None ger alltså en giltig "LSTM-only"-körning utan
    särskild kod i ensemble.py), och (b) om marknadsregimfiltret ska vara
    på. Kastar ValueError på okänd variant.
    """
    if variant == "lgbm_only":
        return lgbm_preds, None, False
    if variant == "lstm_only":
        return lstm_preds, None, False
    if variant == "ensemble":
        return lgbm_preds, lstm_preds, False
    if variant == "regime":
        return lgbm_preds, lstm_preds, True
    raise ValueError(f"Okänd variant: {variant!r} (giltiga: {_VARIANTS})")


def format_result_row(variant: str, stats: dict, alpha_cagr) -> str:
    alpha_str = f"{alpha_cagr*100:+6.1f}%" if alpha_cagr is not None else "    n/a"
    return (f"  {variant:>10}  {stats['CAGR']:>8}  {stats['Sharpe']:>7}  "
            f"{stats['Max Drawdown']:>9}  alfa {alpha_str}")


def worker_train(seg_name: str, which: str) -> None:
    """which: 'lgbm' eller 'lstm' – en modell per subprocess (SIGILL-säkert)."""
    from models.lgbm_model import MomentumLGBM
    from models.lstm_model import MomentumLSTM

    seg = config.SEGMENTS[seg_name]
    _, feats = _load(seg)
    model_df = to_model_df(feats)
    dev_df = _dev_df(model_df)

    if which == "lgbm":
        lgbm = MomentumLGBM()
        lgbm.fit_walk_forward(dev_df)
        lgbm.save(f"{seg['results_dir']}/{_LGBM_MODEL}")
        print("[train] LGBM klar.")
    elif which == "lstm":
        lstm = MomentumLSTM()
        split = int(len(dev_df) * 0.8)
        lstm.fit(dev_df.iloc[:split], dev_df.iloc[split:])
        lstm.save(f"{seg['results_dir']}/{_LSTM_MODEL}")
        print("[train] LSTM klar.")
    else:
        raise ValueError(f"Okänt which={which!r}")


def worker_eval(seg_name: str, variant: str) -> None:
    from models.lgbm_model import MomentumLGBM
    from models.lstm_model import MomentumLSTM
    from models.ensemble import MomentumEnsemble, build_full_output
    from backtest.backtester import MomentumBacktester
    from backtest.benchmark import benchmark_report

    seg = config.SEGMENTS[seg_name]
    data, feats = _load(seg)
    feature_dfs = {t: f.assign(ticker=t) for t, f in feats.items()}

    lgbm_preds = {}
    if variant in ("lgbm_only", "ensemble", "regime"):
        lgbm = MomentumLGBM.load(f"{seg['results_dir']}/{_LGBM_MODEL}")
        lgbm_preds = {t: lgbm.predict(f.dropna(subset=FEATURE_COLS[:5]))
                      for t, f in feats.items() if len(f) > 0}

    lstm_preds = {}
    if variant in ("lstm_only", "ensemble", "regime"):
        lstm = MomentumLSTM()
        lstm.load(f"{seg['results_dir']}/{_LSTM_MODEL}")
        lstm_preds = {t: lstm.predict(f) for t, f in feats.items() if len(f) > 0}

    first, second, market_filter = variant_inputs(variant, lgbm_preds, lstm_preds)
    ensemble = MomentumEnsemble()
    sig = build_full_output(first, second, feature_dfs, ensemble, ta_filter="score")

    bt = MomentumBacktester(sig, data, market_filter=market_filter)
    bt.run()
    stats = bt.statistics()
    bench = benchmark_report(bt._results["portfolio_value"], data)
    out = {
        "variant": variant, "CAGR": stats["CAGR"], "Sharpe": stats["Sharpe"],
        "Max Drawdown": stats["Max Drawdown"],
        "alpha_cagr": bench["alpha_cagr"] if bench else None,
    }
    print("ABLATION_COMPONENT_RESULT " + json.dumps(out))


def _run_variant(seg_name: str, variant: str) -> dict:
    base = [sys.executable, __file__, "--worker", "--segment", seg_name]
    p = subprocess.run(base + ["--variant", variant, "--mode", "eval"], capture_output=True, text=True)
    for line in p.stdout.splitlines():
        if line.startswith("ABLATION_COMPONENT_RESULT "):
            return json.loads(line[len("ABLATION_COMPONENT_RESULT "):])
    print(p.stdout[-2000:])
    print(p.stderr[-1000:])
    return {"variant": variant, "error": "eval failed"}


def run(seg_name: str) -> None:
    seg = config.SEGMENTS[seg_name]
    print(f"\n{'='*70}\nKOMPONENT-ABLATION – {seg['label']}\n{'='*70}")

    print("\n[1/3] Tränar LGBM (egen process)...")
    r = subprocess.run([sys.executable, __file__, "--worker", "--segment", seg_name,
                        "--mode", "train", "--which", "lgbm"])
    if r.returncode != 0:
        print("LGBM-träning misslyckades, avbryter.")
        return

    print("\n[2/3] Tränar LSTM (egen process)...")
    r = subprocess.run([sys.executable, __file__, "--worker", "--segment", seg_name,
                        "--mode", "train", "--which", "lstm"])
    if r.returncode != 0:
        print("LSTM-träning misslyckades, avbryter.")
        return

    print("\n[3/3] Utvärderar alla varianter (egen process per variant)...")
    print(f"\n  {'variant':>10}  {'CAGR':>8}  {'Sharpe':>7}  {'Max DD':>9}  alfa")
    for variant in _VARIANTS:
        result = _run_variant(seg_name, variant)
        if "error" in result:
            print(f"  {variant:>10}  FEL: {result['error']}")
            continue
        print(format_result_row(variant, result, result.get("alpha_cagr")))

    print("\n  Alfa = strategi-CAGR minus indexets CAGR (samma fönster). Om "
          "'ensemble' inte tydligt slår både lgbm_only OCH lstm_only, "
          "tillför inte kombinationen mycket. Om 'regime' inte tydligt slår "
          "'ensemble', bär regimfiltret inte sin komplexitet på just den "
          "här perioden.")


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("segment", nargs="?", default=config.DEFAULT_SEGMENT, choices=list(config.SEGMENTS.keys()))
    p.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--mode", choices=["train", "eval"])
    p.add_argument("--which", choices=["lgbm", "lstm"])
    p.add_argument("--variant", choices=_VARIANTS)
    args = p.parse_args()

    if args.worker:
        if args.mode == "train":
            worker_train(args.segment, args.which)
        elif args.mode == "eval":
            worker_eval(args.segment, args.variant)
        else:
            raise SystemExit("--worker kräver --mode train|eval")
    else:
        run(args.segment)
