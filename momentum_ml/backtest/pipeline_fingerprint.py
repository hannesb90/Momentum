"""
backtest/pipeline_fingerprint.py – #10 i pipeline-granskningslistan.

Verifierar att featurevektor -> LGBM-score -> LSTM-score -> ensemble-score
-> prob_raw -> prob_up blir IDENTISKT när SAMMA sparade modeller körs mot
SAMMA featurevektor två gånger i samma process. Skiljer resultatet sig här
är det ett determinism-fel (en icke-seedad slumpkälla någonstans i
prediktionsvägen), inte en tränings-vs-inference-pipeline-drift i sig – men
det är precis den typen av "tyst fel" som gör en verklig
tränings-vs-inference-jämförelse omöjlig att lita på. Se lstm_model.py:s
seed-fix (2026-07-26, samma granskning) som gjorde detta test meningsfullt
för LSTM-benet – innan dess seedades varken nätverksinitieringen eller
DataLoader-shufflingen, så två "identiska" körningar kunde ge olika vikter.

    python backtest/pipeline_fingerprint.py large
    python backtest/pipeline_fingerprint.py large --ticker ERIC-B.ST
"""
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
import config  # noqa: E402
from features.feature_engineering import FEATURE_COLS  # noqa: E402
from models.ensemble import MomentumEnsemble  # noqa: E402


def compute_fingerprint(feature_row: pd.DataFrame, lgbm_model, lstm_model=None) -> dict:
    """
    feature_row: EN tickers hela feature-historik fram t.o.m. det önskade
    datumet (sista raden i indexet) – LSTM behöver hela sekvensen, inte bara
    en enstaka rad, samma kontrakt som MomentumLGBM.predict()/
    MomentumLSTM.predict() redan kräver i main.py.

    Returnerar en platt dict med de mellanliggande poängen i hela kedjan.
    Två anrop med SAMMA feature_row/modeller ska ge en BYTE-IDENTISK dict
    (LGBM) och en numeriskt identisk dict (LSTM, om seedad korrekt – se
    lstm_model.py::fit).
    """
    lgbm_out = lgbm_model.predict(feature_row)
    lstm_out = lstm_model.predict(feature_row) if lstm_model is not None else None

    last_date = feature_row.index[-1]
    ensemble = MomentumEnsemble()
    combined = ensemble.combine(lgbm_out, lstm_out)

    fingerprint = {
        "date": str(pd.Timestamp(last_date).date()),
        "lgbm_prob_up": float(lgbm_out.loc[last_date, "prob_up"]),
        "lgbm_prob_raw": float(lgbm_out.loc[last_date, "prob_raw"]),
        "lgbm_pred_return": float(lgbm_out.loc[last_date, "pred_return"]),
        "lstm_prob_up": None,
        "ensemble_prob_up": None,
        "ensemble_prob_raw": None,
    }
    if lstm_out is not None and last_date in lstm_out.index:
        fingerprint["lstm_prob_up"] = float(lstm_out.loc[last_date, "prob_up"])
    if last_date in combined.index:
        fingerprint["ensemble_prob_up"] = float(combined.loc[last_date, "prob_up"])
        if "prob_raw" in combined.columns:
            fingerprint["ensemble_prob_raw"] = float(combined.loc[last_date, "prob_raw"])
    return fingerprint


if __name__ == "__main__":
    import argparse
    from data.data_loader import fetch_weekly_data, load_sweden_universe
    from features.feature_engineering import (
        build_all_features, attach_categorical_features, attach_fundamentals_features,
    )
    from models.lgbm_model import MomentumLGBM
    from models.lstm_model import MomentumLSTM

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("segment", choices=list(config.SEGMENTS.keys()), nargs="?", default=config.DEFAULT_SEGMENT)
    p.add_argument("--ticker", default=None,
                   help="Ticker att fingeravtrycksa (default: första i segmentets universum)")
    p.add_argument("--skip-lstm", action="store_true")
    args = p.parse_args()

    seg = config.SEGMENTS[args.segment]
    results_dir = seg["results_dir"]

    print(f"[fingerprint] Laddar modeller från {results_dir}/...")
    lgbm = MomentumLGBM.load(f"{results_dir}/lgbm_model.pkl")
    lstm: Optional[MomentumLSTM] = None
    if not args.skip_lstm:
        lstm_path = Path(f"{results_dir}/lstm_model.pt")
        if lstm_path.exists():
            lstm = MomentumLSTM().load(str(lstm_path))
        else:
            print(f"  [WARN] {lstm_path} saknas – fingeravtryck blir LGBM-only.")

    tickers, sector_map, cap_tier_map, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    ticker = args.ticker or tickers[0]

    print(f"[fingerprint] Bygger features för {ticker}...")
    data = fetch_weekly_data([ticker], start=config.START_DATE, end=None, use_cache=True)
    if ticker not in data:
        raise SystemExit(f"Ingen (tillräcklig) prisdata för {ticker}.")

    # build_all_features (inte build_features direkt) - den senare bygger bara
    # per-ticker-features och saknar tvärsnittskolumnerna (rs_4w/rank_4w/...)
    # som add_cross_sectional lägger till, vilka FEATURE_COLS/predict() kräver.
    feat_dict = build_all_features(data)
    feat_dict = attach_categorical_features(feat_dict, sector_map=sector_map, cap_tier_map=cap_tier_map)
    feat_dict = attach_fundamentals_features(feat_dict, segment=args.segment, prices=data)
    feature_row = feat_dict[ticker].dropna(subset=FEATURE_COLS[:5])

    if lstm is not None and len(feature_row) < config.LSTM_SEQUENCE_LEN + 10:
        print("  [WARN] För kort historik för LSTM-sekvensen – kör LGBM-only.")
        lstm = None

    print("[fingerprint] Kör fingeravtrycket två gånger i samma process...")
    fp1 = compute_fingerprint(feature_row, lgbm, lstm)
    fp2 = compute_fingerprint(feature_row, lgbm, lstm)

    diffs = {k: (fp1[k], fp2[k]) for k in fp1 if fp1[k] != fp2[k]}
    if diffs:
        print(f"  [FEL] Icke-deterministiskt resultat mellan de två körningarna: {diffs}")
        raise SystemExit(1)
    print(f"  OK – identiskt resultat båda körningarna: {fp1}")
