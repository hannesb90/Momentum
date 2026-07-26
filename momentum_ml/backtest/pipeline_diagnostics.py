"""
backtest/pipeline_diagnostics.py – samlar "tysta fel"-signaler genom hela
pipelinen (universumskonsistens, NaN-drift, feature-drift, targetbalans,
eligible-tratt, datumsync) till en enda Pipeline Health Report.

Bakgrund: efter ETF-universum-läckan (value_screener.py, fixad 2026-07-19)
gjordes en granskning av tänkbara "tysta fel" som gradvis försämrar signalen
utan att pipelinen kraschar. Den granskningen hittade fyra kontroller som var
delvis loggade men aldrig sammanställda (universumskonsistens, kalibrerings-
upplösning, eligible-tratt, datumsync) och fem som saknades helt (NaN-drift,
feature-drift, targetbalans, överfiltrering, pipeline-fingeravtryck). Den här
modulen bygger de saknade/delvisa bitarna (utom kalibreringsupplösning, se
backtest/calibration_check.py::prob_resolution_stats, och pipeline-
fingeravtryck, se backtest/pipeline_fingerprint.py – de har egna filer).

Modul-nivå-ackumulatorer (inte klasser/instanser): main.py kör hela
nattkedjan i EN process (predict-only-grenen, se main.py STEG 8b) och
importerar data_loader/feature_engineering/ensemble en gång – en process-
global lista räcker och slipper att bära runt ett diagnostik-objekt genom
funktionssignaturer (data_loader.py, feature_engineering.py, ensemble.py)
som annars inte bryr sig om det. reset_all() finns för testisolering.
"""
import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config  # noqa: E402


_UNIVERSE_STAGES: List[dict] = []
_NAN_LOG: List[dict] = []
_ELIGIBLE_FUNNEL: List[dict] = []
_DATE_ALIGNMENT_LOG: List[dict] = []


def reset_all() -> None:
    """Töm alla ackumulatorer – används av testerna (varje test ska se en
    tom logg) och kan användas av main.py inför en ny körning om samma
    process någonsin kör pipelinen mer än en gång (görs inte idag – varje
    nattlig subprocess är färsk – men billigt att erbjuda)."""
    _UNIVERSE_STAGES.clear()
    _NAN_LOG.clear()
    _ELIGIBLE_FUNNEL.clear()
    _DATE_ALIGNMENT_LOG.clear()


def record_date_alignment(step: str, result: dict) -> dict:
    """Sparar EN sammanslagen datumsync-kontroll (se assert_date_alignment)
    per pipeline-steg – anroparen summerar själv per-ticker-resultat till en
    aggregerad dict innan den skickas hit, så loggen inte svämmar över av en
    rad per ticker och natt."""
    entry = {"step": step, **result}
    _DATE_ALIGNMENT_LOG.append(entry)
    return entry


def get_date_alignment_log() -> List[dict]:
    return list(_DATE_ALIGNMENT_LOG)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Universumskonsistens
# ─────────────────────────────────────────────────────────────────────────────

def record_universe_stage(stage: str, tickers: Sequence[str]) -> dict:
    """Loggar antal tickers + en hash av tickerlistan vid ett givet
    pipeline-steg (t.ex. 'fetch', 'delisting_filter', 'liquidity_filter').
    Hashen (inte hela listan) gör det billigt att jämföra två stegs
    tickerlista utan att spara tusentals strängar i JSON-rapporten – en
    ändrad hash med oförändrat antal avslöjar en tyst BYTT (inte bara
    krympt/växt) universum, exakt den typen av fel ETF-läckan var."""
    uniq = sorted(set(tickers))
    h = hashlib.sha1(",".join(uniq).encode()).hexdigest()[:12]
    entry = {"stage": stage, "n": len(uniq), "tickers_hash": h}
    _UNIVERSE_STAGES.append(entry)
    return entry


def get_universe_stages() -> List[dict]:
    return list(_UNIVERSE_STAGES)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Silent NaN-propagation
# ─────────────────────────────────────────────────────────────────────────────

def record_nan(step: str, before: pd.DataFrame, after: pd.DataFrame,
                cols: Optional[Sequence[str]] = None) -> dict:
    """Loggar rader/NaN-antal kring ett dropna()/fillna()-steg. `cols`
    begränsar vilka kolumner som räknas (default: alla kolumner i `before`)
    – annars svämmar loggen över av kolumner som aldrig var målet för just
    det droppet."""
    cols = [c for c in (cols if cols is not None else before.columns) if c in before.columns]
    entry = {
        "step": step,
        "rows_before": int(len(before)), "rows_after": int(len(after)),
        "rows_dropped": int(len(before) - len(after)),
        "nan_before": {c: int(before[c].isna().sum()) for c in cols},
    }
    _NAN_LOG.append(entry)
    return entry


def get_nan_log() -> List[dict]:
    return list(_NAN_LOG)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Feature drift
# ─────────────────────────────────────────────────────────────────────────────

_DRIFT_PERCENTILES = (5, 25, 50, 75, 95)


def feature_distribution_report(
    df: pd.DataFrame,
    feature_cols: Sequence[str],
    train_mask,
    current_mask,
    std_flag: Optional[float] = None,
) -> pd.DataFrame:
    """Per feature: median/mean/std/p5/p25/p50/p75/p95 i träningsfönstret
    (train_mask) jämfört med det senaste fönstret (current_mask) – båda
    booleska masker mot df.index. drift_flag = |current_mean - train_mean|
    > std_flag * train_std (default config.FEATURE_DRIFT_STD_FLAG). Ett
    tomt/NaN-bara fönster för en feature hoppas över (ingen rad), inte en
    krasch – konsekvent med resten av modulens icke-kritiska disciplin."""
    std_flag = config.FEATURE_DRIFT_STD_FLAG if std_flag is None else std_flag
    train_df = df.loc[train_mask]
    current_df = df.loc[current_mask]

    rows = []
    for col in feature_cols:
        if col not in df.columns:
            continue
        tr = train_df[col].dropna()
        cu = current_df[col].dropna()
        if tr.empty or cu.empty:
            continue
        tr_mean, tr_std = float(tr.mean()), float(tr.std())
        cu_mean = float(cu.mean())
        row = {
            "feature": col,
            "train_n": int(len(tr)), "current_n": int(len(cu)),
            "train_mean": tr_mean, "train_std": tr_std,
            "current_mean": cu_mean, "current_std": float(cu.std()),
        }
        for p in _DRIFT_PERCENTILES:
            row[f"train_p{p}"] = float(np.percentile(tr, p))
            row[f"current_p{p}"] = float(np.percentile(cu, p))
        # tr_std==0 (konstant feature i träningsfönstret) hoppar INTE över
        # flaggan - std_flag * 0 = 0, så varje faktisk avvikelse (cu_mean !=
        # tr_mean) flaggas korrekt i stället för att tystas av en div-by-
        # zero-vakt som råkar dölja precis den mest misstänkta driften.
        row["drift_flag"] = bool(abs(cu_mean - tr_mean) > std_flag * tr_std)
        rows.append(row)
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Rank-gap / bytesfrekvens ("är rangordningen brus vid urvalsgränsen?")
# ─────────────────────────────────────────────────────────────────────────────
#
# Uppstod ur en ad hoc-analys (2026-07-26) av results/signals.csv: median-
# skillnaden i KALIBRERAD prob_up mellan rank 10 och 11 var exakt 0.0 mer än
# hälften av veckorna (isotonic-platån, samma fenomen som
# calibration_check.py::prob_resolution_stats mäter på ett annat sätt), och
# tickern på rank 10 bytte identitet 100% av gångerna mellan rebalanseringar
# (62/62). Jämfört med hur mycket EN akties egen prob_raw normalt rör sig
# vecka till vecka var gapet vid gränsen i samma storleksordning som rent
# brus - dvs urvalet mellan namn 10 och 11 är i praktiken inte statistiskt
# särskiljbart. Loggas här som en permanent, rullande hälsomätning (inte en
# engångsanalys) så att en framtida förändring (gapet krymper ytterligare,
# eller bytesfrekvensen stiger mot 100% även längre ner i listan) syns i
# pipeline_health_history.csv innan den märks som lägre CAGR.

_RANK_GAP_PAIRS = ((5, 6), (10, 11), (20, 21))
_TURNOVER_MAX_RANK = 20


def rank_gap_and_turnover_report(
    signals_df: pd.DataFrame,
    rank_pairs: Sequence[tuple] = _RANK_GAP_PAIRS,
    max_turnover_rank: int = _TURNOVER_MAX_RANK,
    recent_weeks: Optional[int] = None,
    rebalance_weeks: Optional[int] = None,
) -> dict:
    """
    signals_df: long-format med DatetimeIndex (en rad per ticker/datum, som
    ensemble.py::build_full_output producerar) och kolumnerna ticker,
    prob_up, prob_raw, selection_rank, selection_eligible.

    Beräknas över bara de senaste `recent_weeks` veckorna (default
    config.DRIFT_WINDOW_WEEKS, 26) - ett heltäckande 15-årssnitt skulle
    knappt röra sig natt till natt och missa poängen (en NUVARANDE,
    rörlig hälsomätning). Sorteringen inom varje datum är EXAKT densamma
    som ensemble.py::_size_date faktiskt använder för urvalet
    (selection_rank -> prob_up -> prob_raw, fallande) - det är den ordning
    som avgör vem som hamnar i portföljen, inte en godtycklig rank.

    Returnerar en platt dict:
      - gap_prob_raw_{a}_{b}: median(prob_raw[rank a] - prob_raw[rank b])
        för varje par i rank_pairs.
      - turnover_rank_{n}: andel rebalanseringar (var
        config.REBALANCE_WEEKS:e vecka) där tickern på rank n bytte
        identitet mot föregående rebalansering, n i 1..max_turnover_rank
        (= universe_exit + filter_exit + score_reorder nedan).
      - turnover_rank_{n}_universe_exit_frac: andel av dessa övergångar där
        föregångaren helt lämnat universumet (ingen rad alls nästa
        rebalansering - avnoterad, likviditets-/historikfiltrerad, etc.).
      - turnover_rank_{n}_filter_exit_frac: andel där föregångaren
        fortfarande finns i universumet men blivit ineligible
        (selection_eligible=0 - momentumgrind, förv.avk-golv, etc.).
      - turnover_rank_{n}_score_reorder_frac: andel där föregångaren
        fortfarande finns OCH är eligible, men helt enkelt blivit omrankad
        av ändrade poäng.
      - turnover_rank_{n}_common_universe_turnover: bytesfrekvens BEGRÄNSAD
        till fall där föregångaren fanns kvar i universumet nästa gång (dvs
        universe_exit-fallen exkluderade helt ur nämnaren) - #1 i ordern:
        "rankstabilitet endast för aktier som finns i universum vid båda
        rebalanseringarna". NaN om inga sådana övergångar finns.
      - own_score_weekly_median/_std: hur mycket EN akties egen prob_raw
        normalt rör sig vecka till vecka (brus-referens).
      - signal_to_noise_{a}_{b}: gap_prob_raw_{a}_{b} / own_score_weekly_median
        - <1 betyder att gapet vid den rankgränsen är MINDRE än modellens
        egen normala veckobrus, dvs statistiskt icke-särskiljbart.
    """
    recent_weeks = config.DRIFT_WINDOW_WEEKS if recent_weeks is None else recent_weeks
    rebalance_weeks = int(getattr(config, "REBALANCE_WEEKS", 13)) if rebalance_weeks is None else rebalance_weeks

    result: dict = {"n_weeks_checked": 0}
    if signals_df.empty or not isinstance(signals_df.index, pd.DatetimeIndex):
        return result
    if "ticker" not in signals_df.columns or "selection_eligible" not in signals_df.columns:
        return result

    all_dates = signals_df.index.unique().sort_values()
    cutoff = all_dates[-recent_weeks] if len(all_dates) > recent_weeks else all_dates[0]
    recent = signals_df[signals_df.index >= cutoff]

    sort_cols = [c for c in ("selection_rank", "prob_up", "prob_raw") if c in recent.columns]
    if not sort_cols or "prob_raw" not in recent.columns:
        return result

    max_rank_needed = max([max_turnover_rank] + [b for _, b in rank_pairs])
    universe_by_date: Dict[pd.Timestamp, set] = {}
    eligible_by_date: Dict[pd.Timestamp, set] = {}
    ticker_at_rank: Dict[pd.Timestamp, Dict[int, str]] = {}
    gap_samples: Dict[tuple, list] = {pair: [] for pair in rank_pairs}

    for date, g in recent.groupby(level=0):
        universe_by_date[date] = set(g["ticker"])
        elig_g = g[g["selection_eligible"] == 1]
        eligible_by_date[date] = set(elig_g["ticker"])
        if len(elig_g) < max_rank_needed:
            continue
        elig_sorted = elig_g.sort_values(sort_cols, ascending=False).reset_index(drop=True)
        ticker_at_rank[date] = {
            n: elig_sorted.iloc[n - 1]["ticker"] for n in range(1, max_turnover_rank + 1)
        }
        for a, b in rank_pairs:
            gap_samples[(a, b)].append(
                float(elig_sorted.iloc[a - 1]["prob_raw"]) - float(elig_sorted.iloc[b - 1]["prob_raw"]))

    result["n_weeks_checked"] = len(ticker_at_rank)
    for (a, b), samples in gap_samples.items():
        result[f"gap_prob_raw_{a}_{b}"] = float(np.median(samples)) if samples else float("nan")

    rebal_dates = sorted(ticker_at_rank)[::rebalance_weeks] if ticker_at_rank else []
    for n in range(1, max_turnover_rank + 1):
        causes = {"stable": 0, "universe_exit": 0, "filter_exit": 0, "score_reorder": 0}
        total = 0
        for t, t1 in zip(rebal_dates, rebal_dates[1:]):
            ticker_t = ticker_at_rank[t].get(n)
            ticker_t1 = ticker_at_rank[t1].get(n)
            if ticker_t is None or ticker_t1 is None:
                continue
            total += 1
            if ticker_t1 == ticker_t:
                causes["stable"] += 1
            elif ticker_t not in universe_by_date.get(t1, set()):
                causes["universe_exit"] += 1
            elif ticker_t not in eligible_by_date.get(t1, set()):
                causes["filter_exit"] += 1
            else:
                causes["score_reorder"] += 1
        if not total:
            continue
        result[f"turnover_rank_{n}"] = 1.0 - causes["stable"] / total
        result[f"turnover_rank_{n}_universe_exit_frac"] = causes["universe_exit"] / total
        result[f"turnover_rank_{n}_filter_exit_frac"] = causes["filter_exit"] / total
        result[f"turnover_rank_{n}_score_reorder_frac"] = causes["score_reorder"] / total
        common_denom = causes["stable"] + causes["filter_exit"] + causes["score_reorder"]
        result[f"turnover_rank_{n}_common_universe_turnover"] = (
            (causes["filter_exit"] + causes["score_reorder"]) / common_denom
            if common_denom else float("nan")
        )

    idx_name = recent.index.name or "Date"
    diffs = (
        recent.rename_axis(idx_name).reset_index()
              .sort_values(["ticker", idx_name])
              .groupby("ticker")["prob_raw"]
              .apply(lambda s: s.diff().abs())
              .dropna()
    )
    own_median = float(diffs.median()) if len(diffs) else float("nan")
    result["own_score_weekly_median"] = own_median
    result["own_score_weekly_std"] = float(diffs.std()) if len(diffs) else float("nan")

    for a, b in rank_pairs:
        gap = result.get(f"gap_prob_raw_{a}_{b}")
        if gap is not None and own_median and not np.isnan(own_median):
            result[f"signal_to_noise_{a}_{b}"] = gap / own_median

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Modell-trädhälsa ("varför blir score identiska?" - uppföljning 2026-07-26)
# ─────────────────────────────────────────────────────────────────────────────
#
# Grävde vidare i rank-gap-fyndet ovan: två genuint olika bolag fick
# BIT-IDENTISK rå LGBM-poäng. Orsaken visade sig vara att den split som
# faktiskt används för dagens/live-prediktioner bara hade num_trees()==1 -
# LightGBM:s EGNA interna "no further splits with positive gain"-
# terminering (INTE den konfigurerade 50-rundors tålamodsregeln - den hade
# krävt >=51 körda rundor; num_trees==current_iteration==best_iteration==1
# betyder att runda 2 aldrig ens kördes). ~en tredjedel av alla 31
# walk-forward-splits visade samma mönster. Den AKTIVA splitten (den
# `_select_model_idx` faktiskt väljer för "idag") är den enda som spelar
# roll för LIVE-signaler - en gammal, degenererad split långt bak i
# historiken är bara ett kuriosum, men om den AKTIVA splitten degenererar
# ska det stoppa live-servering, inte bara loggas.

def model_tree_health_report(lgbm_model, as_of=None) -> dict:
    """
    lgbm_model: en laddad MomentumLGBM (eller vad som helst med samma
    kontrakt: .cls_models (lista lgb.Booster), .split_starts,
    ._select_model_idx(dates) -> array).
    as_of: datumet "idag" avser - vilken split som är AKTIV beror på detta
    (default: nu). Backtest-/forskningskod bör skicka in det historiska
    datum den faktiskt undersöker, inte låta det defaulta till "nu".

    Returnerar:
      - splits: lista {split_index, split_start, num_trees, best_iteration,
        degenerate (num_trees<=1), active}
      - active_split_index/_start/_num_trees/_best_iteration: den split som
        `as_of` faktiskt skulle använda för prediktion.
      - degenerate_split_count: totalt antal degenererade splits (alla,
        inte bara den aktiva) - ett stigande antal över tid är i sig ett
        varningstecken även innan den AKTIVA splitten träffas.
      - critical: True om den AKTIVA splitten är degenererad - detta (inte
        degenerate_split_count) är vad som ska trigga fallback till senast
        godkända modell, se main.py STEG 3.
    """
    as_of = pd.Timestamp.now("UTC").tz_localize(None) if as_of is None else pd.Timestamp(as_of)
    cls_models = getattr(lgbm_model, "cls_models", None) or []
    split_starts = getattr(lgbm_model, "split_starts", None) or []

    splits = []
    for i, (model, start) in enumerate(zip(cls_models, split_starts)):
        num_trees = int(model.num_trees())
        best_iter = getattr(model, "best_iteration", None)
        splits.append({
            "split_index": i,
            "split_start": str(pd.Timestamp(start).date()),
            "num_trees": num_trees,
            "best_iteration": int(best_iter) if best_iter is not None else None,
            "degenerate": bool(num_trees <= 1),
        })

    active_idx = None
    if splits and hasattr(lgbm_model, "_select_model_idx"):
        active_idx = int(lgbm_model._select_model_idx(pd.DatetimeIndex([as_of]))[0])
    for s in splits:
        s["active"] = (s["split_index"] == active_idx)
    active = splits[active_idx] if active_idx is not None else None

    return {
        "as_of": str(as_of.date()),
        "n_splits": len(splits),
        "degenerate_split_count": sum(1 for s in splits if s["degenerate"]),
        "active_split_index": active_idx,
        "active_split_start": active["split_start"] if active else None,
        "active_num_trees": active["num_trees"] if active else None,
        "active_best_iteration": active["best_iteration"] if active else None,
        "critical": bool(active and active["degenerate"]),
        "splits": splits,
    }


def reproducibility_metadata() -> dict:
    """
    Minimal "hur skulle jag återskapa den här modellen"-metadata:
    slumpfrö, LGBM-parametrar, featurelistans hash och en kodhash (samma
    _code_hash() som models/lgbm_model.py använder för sin checkpoint-
    nyckel och för att bevara underkända splits, se
    MomentumLGBM._preserve_rejected_split). Loggas varje natt i
    pipeline_health.json så en framtida "varför skiljer sig den här
    modellen från förra veckans" går att slå upp direkt utan att gräva i
    git-historik.
    """
    from features.feature_engineering import FEATURE_COLS
    from models.lgbm_model import _code_hash

    return {
        "code_hash": _code_hash(),
        "random_seed": config.RANDOM_SEED,
        "lgbm_params": {k: v for k, v in config.LGBM_PARAMS.items() if k != "num_threads"},
        "feature_cols_count": len(FEATURE_COLS),
        "feature_cols_hash": hashlib.sha1(",".join(FEATURE_COLS).encode()).hexdigest()[:16],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5/9. Eligible-mask-tratt / överfiltrering
# ─────────────────────────────────────────────────────────────────────────────

def record_eligible_funnel(date, n_scored: int, n_eligible: int,
                            n_after_gate: int, n_final: int) -> None:
    """En rad per historiskt datum: universum-storlek (n_scored, dvs alla
    tickers med en prediktion det datumet) -> eligible (förv.avk-golvet i
    ensemble.build_full_output) -> efter momentumgrind (selection_eligible)
    -> slutligt urval (position_size > 0). Krympande n_final/n_eligible-kvot
    över tid = gradvis överfiltrering, exakt det #9 i granskningslistan
    efterlyste."""
    _ELIGIBLE_FUNNEL.append({
        "date": str(pd.Timestamp(date).date()),
        "n_scored": int(n_scored), "n_eligible": int(n_eligible),
        "n_after_gate": int(n_after_gate), "n_final": int(n_final),
    })


def get_eligible_funnel() -> List[dict]:
    return list(_ELIGIBLE_FUNNEL)


# ─────────────────────────────────────────────────────────────────────────────
# 7. Datumsynkronisering
# ─────────────────────────────────────────────────────────────────────────────

def assert_date_alignment(df: pd.DataFrame, date_col: str = "Date") -> dict:
    """Kollar att datum är måndags-ankrade (weekday==0, se data_loader._clean:s
    W-MON-normalisering) och att en ev. 'published'-kolumn (fundamenta,
    point-in-time as-of-kopplad i attach_fundamentals_features) aldrig ligger
    EFTER date_col – det vore en lookahead-läcka. `date_col` läses ur
    kolumnerna om den finns, annars ur indexet (merge_asof-resultat har
    'Date' som index, inte kolumn). Loggar och returnerar avvikelser men
    kraschar aldrig pipelinen – samma icke-kritiska disciplin som main.py:s
    STEG 8b."""
    dates = pd.to_datetime(df[date_col] if date_col in df.columns else pd.Series(df.index))
    non_monday = int((dates.dt.weekday != 0).sum())
    future_published = 0
    if "published" in df.columns:
        published = pd.to_datetime(df["published"], errors="coerce")
        future_published = int((published.reset_index(drop=True) > dates.reset_index(drop=True)).sum())
    result = {
        "n": int(len(dates)),
        "non_monday_dates": non_monday,
        "future_published_rows": future_published,
    }
    if non_monday or future_published:
        print(f"  [WARN] pipeline_diagnostics.assert_date_alignment: "
              f"{non_monday} icke-måndags-datum, {future_published} rader med "
              f"published > Date (lookahead-misstanke).")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 8. Targetbalans
# ─────────────────────────────────────────────────────────────────────────────

def target_balance_stats(model_df: pd.DataFrame) -> dict:
    """Andel positiva exempel, kvantilgränsen som faktiskt används
    (config.XS_TARGET_QUANTILE om XS_TARGET är på), och median-
    framtidsavkastning. Loggad varje körning (via build_and_write_report:s
    historik-CSV) blir detta en tidsserie – #8 i granskningslistan efterlyste
    just en trend, inte bara ett engångsvärde (jfr models/lgbm_model.py:s
    _sanity_check, som bara varnar en gång per träning om andelen är
    extrem)."""
    sig = model_df["target_signal"].dropna()
    ret = model_df["target_return"].dropna()
    return {
        "n": int(len(sig)),
        "positive_share": float(sig.mean()) if len(sig) else float("nan"),
        "xs_target_enabled": bool(getattr(config, "XS_TARGET", False)),
        "quantile_used": float(getattr(config, "XS_TARGET_QUANTILE", float("nan"))),
        "median_forward_return": float(ret.median()) if len(ret) else float("nan"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Samlad rapport
# ─────────────────────────────────────────────────────────────────────────────

def _read_last_history_row(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        hist = pd.read_csv(path)
        return None if hist.empty else hist.iloc[-1].to_dict()
    except Exception:  # noqa: BLE001 - historikfilen är diagnostik, aldrig kritisk
        return None


def build_and_write_report(
    *,
    feature_drift: pd.DataFrame,
    target_balance: dict,
    calibration_resolution: dict,
    latest_drift: Optional[dict] = None,
    rank_gap_turnover: Optional[dict] = None,
    tree_health: Optional[dict] = None,
    reproducibility: Optional[dict] = None,
    out_dir: Optional[str] = None,
) -> dict:
    """Slår ihop alla insamlade diagnostik-bitar (universumskonsistens,
    NaN-logg, eligible-tratt, plus argumenten ovan som anroparen redan har
    beräknat) till EN rapport. Skriver:
      - {out_dir}/pipeline_health.json      – atomärt, senaste snapshot
        (samma .tmp+replace-mönster som momentum_readiness.py::build())
      - {out_dir}/pipeline_health_history.csv – en appendad rad per körning,
        för trend över tid (universum-antal, targetbalans, tratt-totaler,
        antal feature-drift-flaggor, kalibreringsupplösning, rank-gap/brus)
      - {out_dir}/feature_drift_report.csv  – full per-feature-detalj för
        SENASTE körningen (överskrivs, som drift_report.csv)
      - {out_dir}/eligible_funnel_history.csv – full per-datum-tratt
        (överskrivs – hela historiken är redan deriverbar från signals.csv,
        ingen append behövs)
      - {out_dir}/rank_gap_turnover.csv – bytesfrekvens per rank (1-20) för
        SENASTE körningen (överskrivs, som feature_drift_report.csv)
    """
    out_dir = out_dir or config.RESULTS_DIR
    out_path = Path(out_dir) / "pipeline_health.json"
    history_path = Path(out_dir) / "pipeline_health_history.csv"
    drift_path = Path(out_dir) / "feature_drift_report.csv"
    funnel_path = Path(out_dir) / "eligible_funnel_history.csv"
    rank_path = Path(out_dir) / "rank_gap_turnover.csv"
    tree_path = Path(out_dir) / "model_tree_health.csv"
    rank_gap_turnover = rank_gap_turnover or {}
    tree_health = tree_health or {}
    reproducibility = reproducibility or {}

    universe_stages = get_universe_stages()
    nan_log = get_nan_log()
    funnel = get_eligible_funnel()
    n_drift_flagged = int(feature_drift["drift_flag"].sum()) if len(feature_drift) else 0

    funnel_totals = {
        "n_scored": sum(f["n_scored"] for f in funnel),
        "n_eligible": sum(f["n_eligible"] for f in funnel),
        "n_after_gate": sum(f["n_after_gate"] for f in funnel),
        "n_final": sum(f["n_final"] for f in funnel),
    } if funnel else {}

    report = {
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "universe_stages": universe_stages,
        "nan_log": nan_log,
        "date_alignment_log": get_date_alignment_log(),
        "feature_drift_n_checked": int(len(feature_drift)),
        "feature_drift_n_flagged": n_drift_flagged,
        "target_balance": target_balance,
        "calibration_resolution": calibration_resolution,
        "eligible_funnel_last_date": funnel[-1] if funnel else None,
        "eligible_funnel_totals": funnel_totals,
        "drift": latest_drift,
        "rank_gap_turnover": rank_gap_turnover,
        "tree_health": tree_health,
        "reproducibility": reproducibility,
    }

    prev = _read_last_history_row(history_path)
    change: Dict[str, float] = {}
    if prev is not None:
        current_values = {
            "universe_n": universe_stages[-1]["n"] if universe_stages else None,
            "positive_share": target_balance.get("positive_share"),
            "n_final": funnel_totals.get("n_final"),
            "feature_drift_n_flagged": n_drift_flagged,
        }
        for key, cur_val in current_values.items():
            prev_val = prev.get(key)
            if cur_val is None or prev_val is None:
                continue
            try:
                change[key] = float(cur_val) - float(prev_val)
            except (TypeError, ValueError):
                pass
    report["change_vs_previous"] = change

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    tmp.replace(out_path)

    history_row = {
        "generated_at": report["generated_at"],
        "universe_n": universe_stages[-1]["n"] if universe_stages else None,
        "positive_share": target_balance.get("positive_share"),
        "median_forward_return": target_balance.get("median_forward_return"),
        "n_scored": funnel_totals.get("n_scored"),
        "n_eligible": funnel_totals.get("n_eligible"),
        "n_after_gate": funnel_totals.get("n_after_gate"),
        "n_final": funnel_totals.get("n_final"),
        "feature_drift_n_flagged": n_drift_flagged,
        "calibration_n_unique_prob_up": calibration_resolution.get("n_unique"),
        "calibration_largest_plateau_frac": calibration_resolution.get("largest_plateau_frac"),
        "gap_prob_raw_5_6": rank_gap_turnover.get("gap_prob_raw_5_6"),
        "gap_prob_raw_10_11": rank_gap_turnover.get("gap_prob_raw_10_11"),
        "gap_prob_raw_20_21": rank_gap_turnover.get("gap_prob_raw_20_21"),
        "own_score_weekly_std": rank_gap_turnover.get("own_score_weekly_std"),
        "signal_to_noise_10_11": rank_gap_turnover.get("signal_to_noise_10_11"),
        "turnover_rank_10": rank_gap_turnover.get("turnover_rank_10"),
        "turnover_rank_10_universe_exit_frac": rank_gap_turnover.get("turnover_rank_10_universe_exit_frac"),
        "turnover_rank_10_filter_exit_frac": rank_gap_turnover.get("turnover_rank_10_filter_exit_frac"),
        "turnover_rank_10_score_reorder_frac": rank_gap_turnover.get("turnover_rank_10_score_reorder_frac"),
        "turnover_rank_10_common_universe_turnover": rank_gap_turnover.get("turnover_rank_10_common_universe_turnover"),
        "active_num_trees": tree_health.get("active_num_trees"),
        "active_best_iteration": tree_health.get("active_best_iteration"),
        "degenerate_split_count": tree_health.get("degenerate_split_count"),
        "tree_health_critical": tree_health.get("critical"),
        "model_fallback_used": tree_health.get("fallback_used"),
        "code_hash": reproducibility.get("code_hash"),
    }
    write_header = not history_path.exists()
    pd.DataFrame([history_row]).to_csv(history_path, mode="a", header=write_header, index=False)

    if len(feature_drift):
        feature_drift.to_csv(drift_path, index=False)
    if funnel:
        pd.DataFrame(funnel).to_csv(funnel_path, index=False)
    turnover_rows = [
        {
            "rank": n,
            "turnover_frac": rank_gap_turnover.get(f"turnover_rank_{n}"),
            "universe_exit_frac": rank_gap_turnover.get(f"turnover_rank_{n}_universe_exit_frac"),
            "filter_exit_frac": rank_gap_turnover.get(f"turnover_rank_{n}_filter_exit_frac"),
            "score_reorder_frac": rank_gap_turnover.get(f"turnover_rank_{n}_score_reorder_frac"),
            "common_universe_turnover": rank_gap_turnover.get(f"turnover_rank_{n}_common_universe_turnover"),
        }
        for n in range(1, _TURNOVER_MAX_RANK + 1)
        if f"turnover_rank_{n}" in rank_gap_turnover
    ]
    if turnover_rows:
        pd.DataFrame(turnover_rows).to_csv(rank_path, index=False)
    if tree_health.get("splits"):
        pd.DataFrame(tree_health["splits"]).to_csv(tree_path, index=False)

    critical_note = ""
    if tree_health.get("critical"):
        critical_note = (f" [KRITISKT: aktiv split {tree_health.get('active_split_start')} "
                          f"har bara {tree_health.get('active_num_trees')} träd]")
    print(f"[PipelineHealth] Rapport skriven: {out_path} (+{history_path.name}, "
          f"{n_drift_flagged}/{len(feature_drift)} features flaggade för drift)"
          f"{critical_note}")
    return report
