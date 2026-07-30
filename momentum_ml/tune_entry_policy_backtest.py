"""
tune_entry_policy_backtest.py – Kausal historisk backtest av
models/entry_policy.py::decide_entry() (EDGE_RISK_SCENARIO_TESTKO.md Tier 1
#1, [SCN-KÖP-1], högst prioriterad öppen post 2026-07-30).

decide_entry() anropas idag ENDAST i main.py:702 (apply_entry_policy=True)
för signals_serving.csv - den skarpa serveringsvägen. backtest/backtester.py
importerar entry_policy ALDRIG. Reglerna som styr vad en LEVANDE ANVÄNDARE
ser/blockeras från att köpa i appen (portfolio.py::_new_entry_allowed) har
alltså ALDRIG körts genom ett historiskt backtest - ren obevisad
domänheuristik fram tills nu.

Läsning av models/entry_policy.py (innan detta skript skrevs) visar att
BARA regeln `blocked_overextended` faktiskt sätter eligible=False - och
BARA för segment="small" (roc_13w>=1.0 UTAN fundamental bekräftelse). De
tre andra actions (cooldown_review/long_runup_review/early_second_opinion)
är rena etikett-strängar, de ändrar aldrig `eligible`. Alltså: för
segment="large" har decide_entry() per konstruktion NOLL effekt på
`eligible` - detta skript testar därför bara segment="small".

portfolio.py::_new_entry_allowed(entry_allowed, is_owned) blockerar bara
NYA köp - en redan ägd position tvingas aldrig säljas av policyn. Detta
skript replikerar EXAKT det beteendet via en MomentumBacktester-subklass
som filtrerar bort blockerade NYA kandidater ur target_weights i
_rebalance() innan köpet exekveras (path-dependent - kräver `self._portfolio`s
faktiska historiska tillstånd, går inte att göra vektoriserat i
build_full_output). Blockerad plats fylls INTE med nästa kandidat (enklaste,
mest konservativa tolkningen - kapitalet blir kassa den veckan) - en
påfyllnadsvariant är ett eget uppföljningssteg, inte gjort här.

Modellen som används är segment "small"s befintliga produktionsarkitektur
(LambdaRank, production_params() från tune_lambdarank_common.py, 52v-horisont
per config.SEGMENTS["small"]) - tränas om här eftersom cachead
results/small/lgbm_model.pkl är från FÖRE Nivå 3-migreringen (2026-07-28,
binär/gammal arkitektur, verifierat via mtime). Ingen konfidensskillnad
mellan de två backtest-varianterna kommer alltså från olika modeller - båda
använder EXAKT samma tränade modell/signaler, bara olika post-hoc-filtrering
av nya köp.

Faser (kör i ordning):
    fetch    – hämtar small-universumet (Small+Micro Cap), bygger features.
    train    – tränar EN riktig MomentumLGBM.fit_walk_forward() (small-segmentets
               52v-horisont, production_params()).
    backtest – bygger signals_df (apply_entry_policy=True), kör baseline- och
               policy-varianten, rapporterar CAGR/Sharpe/MaxDD/turnover +
               diagnostik över hur många blockeringar som faktiskt var
               "bindande" (skulle annars köpts som ny position).

    /opt/momentum/venv/bin/python3 tune_entry_policy_backtest.py fetch
    /opt/momentum/venv/bin/python3 tune_entry_policy_backtest.py train
    /opt/momentum/venv/bin/python3 tune_entry_policy_backtest.py backtest
"""
import sys
from pathlib import Path

sys.path.insert(0, ".")
import config

seg = config.SEGMENTS["small"]
config.RESULTS_DIR      = "results"   # skriv INTE in i results/small (produktionens riktiga small-state)
config.MAX_POSITIONS    = seg.get("max_positions", config.MAX_POSITIONS)
config.CONVICTION_BLEND = seg.get("conviction_blend", config.CONVICTION_BLEND)
config.ACTIVE_SEGMENT   = "small"
if "index_ticker" in seg: config.INDEX_BENCHMARK_TICKER = seg["index_ticker"]
if "index_label"  in seg: config.INDEX_BENCHMARK_LABEL  = seg["index_label"]
if "gate_enabled" in seg: config.MOMENTUM_GATE_ENABLED  = seg["gate_enabled"]
if "gate_min"     in seg: config.MOMENTUM_GATE_MIN      = seg["gate_min"]
if "atr_stop_enabled" in seg: config.ATR_STOP_ENABLED = seg["atr_stop_enabled"]
if "market_filter_exposure" in seg:
    config.MARKET_FILTER_EXPOSURE = seg["market_filter_exposure"]
if "forward_weeks" in seg:
    config.FORWARD_WEEKS   = seg["forward_weeks"]
    config.REBALANCE_WEEKS = seg["rebalance_weeks"]
    config.EMBARGO_WEEKS   = seg["embargo_weeks"]
if "rank_ema_span" in seg: config.RANK_EMA_SPAN = seg["rank_ema_span"]
if "drop_features" in seg:
    config.DROP_FEATURES = seg["drop_features"]

import numpy as np
import pandas as pd

from data.data_loader import (
    fetch_weekly_data, filter_active_universe, filter_liquid_universe, load_sweden_universe,
)
from features.feature_engineering import (
    build_all_features, attach_categorical_features, attach_fundamentals_features,
    to_model_df, FEATURE_COLS,
)
from models.lgbm_model import MomentumLGBM
from models.ensemble import MomentumEnsemble, build_full_output
from models.entry_policy import decide_entry
from backtest.backtester import MomentumBacktester

FEATURES_PKL = Path("results/entry_policy_small_features.pkl")
DATA_PKL     = Path("results/entry_policy_small_price_data.pkl")
LGBM_PKL     = Path("results/entry_policy_small_lgbm.pkl")


# ── Fas 1: hämta + bygg features ─────────────────────────────────────────────

def cmd_fetch():
    tickers, sector_map, cap_tier_map, name_map = load_sweden_universe(min_market_cap=seg["market_cap"])
    config.SECTOR_MAP.update(sector_map)
    config.CAP_TIER_MAP.update(cap_tier_map)
    config.NAME_MAP.update(name_map)
    print(f"[entry_policy] {len(tickers)} tickers i small-universumet (Small+Micro Cap). Hämtar data...")

    data = fetch_weekly_data(tickers, start=config.START_DATE, end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)
    print(f"[entry_policy] {len(data)} tickers kvar efter filter.")

    feats = build_all_features(data)
    feats = attach_categorical_features(feats, sector_map=config.SECTOR_MAP, cap_tier_map=cap_tier_map)
    feats = attach_fundamentals_features(feats, segment="small", prices=data)

    model_features = {t: f for t, f in feats.items() if config.CAP_TIER_MAP.get(t, "") != "Fond"}
    excluded = len(feats) - len(model_features)
    print(f"[entry_policy] Exkluderar {excluded} ETF/fonder ur modelluniversumet.")

    pd.to_pickle(model_features, FEATURES_PKL)
    pd.to_pickle(data, DATA_PKL)
    print(f"[entry_policy] Sparat: {FEATURES_PKL} ({len(model_features)} tickers), {DATA_PKL} ({len(data)} tickers)")


# ── Fas 2: träna (EXAKT produktionskoden för small-segmentet) ───────────────

def cmd_train():
    if not FEATURES_PKL.exists():
        raise SystemExit(f"{FEATURES_PKL} saknas - kör 'fetch' först.")
    model_features = pd.read_pickle(FEATURES_PKL)
    model_df = to_model_df(model_features)
    print(f"[entry_policy] model_df: {len(model_df):,} rader, {model_df['ticker'].nunique()} tickers.")
    missing = [c for c in FEATURE_COLS if c not in model_df.columns]
    if missing:
        raise SystemExit(f"Saknade kolumner i model_df: {missing}")

    all_dates = model_df.index.unique().sort_values()
    if len(all_dates) > config.HOLDOUT_WEEKS + config.FORWARD_WEEKS:
        holdout_start = all_dates[-config.HOLDOUT_WEEKS]
        purge_start = all_dates[-(config.HOLDOUT_WEEKS + config.FORWARD_WEEKS)]
        dev_df = model_df[model_df.index < purge_start]
        print(f"[entry_policy] Frusen holdout: {holdout_start.date()} -> slut.")
    else:
        holdout_start = None
        dev_df = model_df
        print("[entry_policy] [VARNING] för kort historik för en frusen holdout.")

    lgbm = MomentumLGBM()
    lgbm.fit_walk_forward(dev_df)   # EXAKT samma anrop som main.py --train-lgbm-only
    lgbm.print_fold_diagnostics()

    pd.to_pickle({"lgbm": lgbm, "holdout_start": holdout_start}, LGBM_PKL)
    print(f"[entry_policy] Sparat: {LGBM_PKL}")


# ── Fas 3: bygg signaler (bas + policy) + kör riktig backtest ───────────────

def _load_state():
    for p in (FEATURES_PKL, DATA_PKL, LGBM_PKL):
        if not p.exists():
            raise SystemExit(f"{p} saknas - kör 'fetch'/'train' först.")
    model_features = pd.read_pickle(FEATURES_PKL)
    data = pd.read_pickle(DATA_PKL)
    state = pd.read_pickle(LGBM_PKL)
    return model_features, data, state["lgbm"], state["holdout_start"]


class PolicyBacktester(MomentumBacktester):
    """Identisk med MomentumBacktester, förutom att NYA köp (tickers som INTE
    redan ägs) blockeras om entry_policy.py::decide_entry() satte
    eligible=False för det (datum, ticker)-paret. Redan ägda positioner
    tvingas ALDRIG säljas av detta - exakt portfolio.py::_new_entry_allowed-
    semantiken, bara flyttad in i backtestern så den faktiskt påverkar
    portföljutfallet i stället för bara ett UI-textfilter."""

    def __init__(self, *args, blocked_new_entries: set, **kwargs):
        super().__init__(*args, **kwargs)
        self._blocked_new_entries = blocked_new_entries   # {(date, ticker)}
        self.n_blocks_binding = 0   # diagnostik: faktiskt strukna nya köp

    def _rebalance(self, date, target_weights, portfolio_value, cash):
        owned = set(self._portfolio.keys())
        filtered = {}
        for ticker, w in target_weights.items():
            if ticker not in owned and (date, ticker) in self._blocked_new_entries:
                self.n_blocks_binding += 1
                continue   # ny position, blockerad -> kapitalet blir kassa denna vecka
            filtered[ticker] = w
        return super()._rebalance(date, filtered, portfolio_value, cash)


def _run_backtest(signals_df: pd.DataFrame, price_data: dict, holdout_start,
                   blocked_new_entries: set = None) -> dict:
    if blocked_new_entries is None:
        bt = MomentumBacktester(signals_df, price_data)
    else:
        bt = PolicyBacktester(signals_df, price_data, blocked_new_entries=blocked_new_entries)
    bt.run()
    overall = bt.statistics()
    dev = bt.statistics_for_period(end=holdout_start) if holdout_start is not None else overall
    holdout = bt.statistics_for_period(start=holdout_start) if holdout_start is not None else None
    n_binding = getattr(bt, "n_blocks_binding", None)
    return {"overall": overall, "dev": dev, "holdout": holdout, "n_binding": n_binding}


def cmd_backtest():
    model_features, data, lgbm, holdout_start = _load_state()
    print(f"[entry_policy] {len(model_features)} tickers, holdout_start={holdout_start}")

    lgbm_preds_by_ticker = {}
    for ticker, feat_df in model_features.items():
        feat_df_clean = feat_df.dropna(subset=FEATURE_COLS[:5])
        if len(feat_df_clean) > 0:
            lgbm_preds_by_ticker[ticker] = lgbm.predict(feat_df_clean)
    ensemble = MomentumEnsemble()
    feature_dfs = {t: df.assign(ticker=t) for t, df in model_features.items()}

    print("[entry_policy] Bygger signals_df (apply_entry_policy=True för entry_action-kolumnen)...")
    signals_df = build_full_output(
        lgbm_preds_by_ticker, None, feature_dfs, ensemble, apply_entry_policy=True,
    )

    blocked_mask = signals_df["entry_action"] == "blocked_overextended"
    blocked_new_entries = set(
        zip(signals_df.index[blocked_mask], signals_df.loc[blocked_mask, "ticker"])
    )
    n_blocked_rows = int(blocked_mask.sum())
    n_blocked_dates = signals_df.index[blocked_mask].nunique()
    print(f"[entry_policy] blocked_overextended: {n_blocked_rows} (datum,ticker)-observationer "
          f"över {n_blocked_dates} unika datum.")

    print("[entry_policy] Kör baseline-backtest (ingen entry-policy)...")
    baseline = _run_backtest(signals_df, data, holdout_start)
    print("[entry_policy] Kör policy-backtest (blocked_overextended aktiv för NYA köp)...")
    policy = _run_backtest(signals_df, data, holdout_start, blocked_new_entries=blocked_new_entries)

    def _pct(stat_dict, key):
        return float(str(stat_dict[key]).rstrip("%")) / 100.0

    print("\n" + "=" * 100)
    print("Full backtest (small-segment, MAX_POSITIONS=20, 52v-horisont)")
    print("=" * 100)
    for name, res in (("baseline (ingen policy)", baseline), ("policy (blocked_overextended)", policy)):
        d, h = res["dev"], res["holdout"]
        print(f"  {name:<32}: dev CAGR={_pct(d,'CAGR'):+.2%} Sharpe={float(d['Sharpe']):.2f} "
              f"MaxDD={_pct(d,'Max Drawdown'):.1%} | "
              f"holdout CAGR={_pct(h,'CAGR'):+.2%} Sharpe={float(h['Sharpe']) if h else 0.0:.2f} "
              f"MaxDD={_pct(h,'Max Drawdown'):.1%} | bindande blockeringar={res['n_binding']}")

    print(f"\n[entry_policy] Diagnostik: {n_blocked_rows} rå blocked_overextended-observationer, "
          f"varav {policy['n_binding']} faktiskt hindrade ett NYTT köp i backtesten "
          f"(resten var antingen inte i topp-{config.MAX_POSITIONS} den veckan, eller redan ägda).")
    print("[entry_policy] Klart.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "backtest"
    {"fetch": cmd_fetch, "train": cmd_train, "backtest": cmd_backtest}[cmd]()
