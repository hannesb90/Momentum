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
    out_dir: Optional[str] = None,
) -> dict:
    """Slår ihop alla insamlade diagnostik-bitar (universumskonsistens,
    NaN-logg, eligible-tratt, plus de tre argumenten ovan som anroparen
    redan har beräknat) till EN rapport. Skriver:
      - {out_dir}/pipeline_health.json      – atomärt, senaste snapshot
        (samma .tmp+replace-mönster som momentum_readiness.py::build())
      - {out_dir}/pipeline_health_history.csv – en appendad rad per körning,
        för trend över tid (universum-antal, targetbalans, tratt-totaler,
        antal feature-drift-flaggor, kalibreringsupplösning)
      - {out_dir}/feature_drift_report.csv  – full per-feature-detalj för
        SENASTE körningen (överskrivs, som drift_report.csv)
      - {out_dir}/eligible_funnel_history.csv – full per-datum-tratt
        (överskrivs – hela historiken är redan deriverbar från signals.csv,
        ingen append behövs)
    """
    out_dir = out_dir or config.RESULTS_DIR
    out_path = Path(out_dir) / "pipeline_health.json"
    history_path = Path(out_dir) / "pipeline_health_history.csv"
    drift_path = Path(out_dir) / "feature_drift_report.csv"
    funnel_path = Path(out_dir) / "eligible_funnel_history.csv"

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
    }
    write_header = not history_path.exists()
    pd.DataFrame([history_row]).to_csv(history_path, mode="a", header=write_header, index=False)

    if len(feature_drift):
        feature_drift.to_csv(drift_path, index=False)
    if funnel:
        pd.DataFrame(funnel).to_csv(funnel_path, index=False)

    print(f"[PipelineHealth] Rapport skriven: {out_path} (+{history_path.name}, "
          f"{n_drift_flagged}/{len(feature_drift)} features flaggade för drift)")
    return report
