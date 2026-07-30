"""
tune_borsdata_fundamental_lgbm.py – Fristående experiment:
Har Börsdata-fundamenta kombinerad prediktiv signal i LightGBM
som univariat IC-analys missar?

Forskningsfrågor:
  1. Hittar LightGBM en kombinerad signal som IC-testet missar?
  2. Vilka fundamentala variabler bidrar faktiskt?
  3. Är signalen tillräcklig för integration i huvudmodellen?
  4. Om inte – motivera varför.

Design:
  · Bara Börsdata-features (f_score, rev_growth, rev_accel, margin_delta,
    ni_growth, fcf_margin, roa) – ingen teknisk analys, inget MFN, inget sentiment.
  · Point-in-time: årsrapport för år Y antas känd från 1 maj år Y+1
    (konservativt, samma antagande som tune_fundamentals.py).
  · Walk-forward 3 folds: Train 2016-2020->Test 2021, 2016-2021->2022,
    2016-2022->2023-2024.
  · Target: binär (top 30% / bottom 30% excess 26v-avkastning inom
    årskohorter). Mellersta 40% exkluderas för renare signal.
  · Baselines: ROA-ranking, F-score-ranking, LogisticRegression.
  · Rapporterar: IC, Hit Rate, Q5-Q1, CAGR/Sharpe/MaxDD/Alpha, SHAP.

Körs på Pi:n:
    /opt/momentum/venv/bin/python tune_borsdata_fundamental_lgbm.py
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).parent))
import config
from data.data_loader import fetch_weekly_data

# ── Konstanter ────────────────────────────────────────────────────────────────
FEATURES = ["f_score", "rev_growth", "rev_accel", "margin_delta",
            "ni_growth", "fcf_margin", "roa"]
HORIZON_W = 26          # framåtfönster i veckor
TOP_FRAC  = 0.30        # top-quantil för label=1
BOT_FRAC  = 0.30        # bottom-quantil för label=0
# Walk-forward: (train_max_year, test_years)
WF_FOLDS  = [
    (2020, [2021]),
    (2021, [2022]),
    (2022, [2023, 2024]),
]
LGBM_PARAMS = dict(
    objective="binary",
    n_estimators=400,
    learning_rate=0.05,
    num_leaves=15,          # grunt träd – liten dataset, undvik overfit
    min_child_samples=20,
    subsample=0.8,
    colsample_bytree=0.8,
    reg_alpha=0.1,
    reg_lambda=1.0,
    random_state=42,
    n_jobs=2,
    verbose=-1,
)
ANNUAL_WEEKS = 52


# ── 1. Ladda och bygg point-in-time dataset ───────────────────────────────────
def build_signal_panel():
    fp = Path(config.anchor(config.RESULTS_DIR)) / "fundamentals.csv"
    if not fp.exists():
        raise FileNotFoundError(
            "fundamentals.csv saknas – kör 'python -m altdata.fundamentals build' först."
        )
    fund = pd.read_csv(fp)
    fund = fund.replace("None", np.nan)
    for c in FEATURES + ["f_n"]:
        if c in fund.columns:
            fund[c] = pd.to_numeric(fund[c], errors="coerce")

    tickers = sorted(fund["ticker"].unique())
    print(f"[build] {len(fund)} bolagsår · {len(tickers)} bolag – hämtar prisdata...",
          flush=True)

    data = fetch_weekly_data(tickers, start="2015-01-01", end=None, use_cache=True)
    px = pd.DataFrame(
        {t: d["Close"] for t, d in data.items() if d is not None and "Close" in d}
    ).sort_index()
    px.index = pd.to_datetime(px.index)
    print(f"[build] prisdata: {px.shape[1]} tickers · {px.shape[0]} veckor", flush=True)

    rows = []
    for _, r in fund.iterrows():
        tk = r["ticker"]
        year = int(r["year"])
        if tk not in px.columns:
            continue
        t0 = pd.Timestamp(year + 1, 5, 1)
        s = px[tk].dropna()
        idx0 = s.index.searchsorted(t0)
        if idx0 >= len(s) - HORIZON_W:
            continue
        fwd_ret = s.iloc[idx0 + HORIZON_W] / s.iloc[idx0] - 1
        row = {"ticker": tk, "year": year, "signal_date": s.index[idx0],
               "fwd_26w": fwd_ret}
        for f in FEATURES:
            row[f] = r.get(f, np.nan)
        rows.append(row)

    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("Inga matchande rader – kontrollera prisdata och fundamentals.csv.")

    df["excess_26w"] = df["fwd_26w"] - df.groupby("year")["fwd_26w"].transform("mean")

    def _label(g):
        hi = g["excess_26w"].quantile(1 - TOP_FRAC)
        lo = g["excess_26w"].quantile(BOT_FRAC)
        lbl = pd.Series(np.nan, index=g.index)
        lbl[g["excess_26w"] >= hi] = 1.0
        lbl[g["excess_26w"] <= lo] = 0.0
        return lbl

    df["label"] = df.groupby("year", group_keys=False).apply(_label)
    df_all = df.copy()
    df = df.dropna(subset=["label"] + FEATURES, how="any")
    df = df.dropna(subset=["label"])
    print(f"[build] {len(df)} obs efter PIT + label-filter "
          f"(label=1: {int(df['label'].sum())}, label=0: {int((df['label']==0).sum())})",
          flush=True)
    return df.reset_index(drop=True), df_all.reset_index(drop=True)


# ── 2. Walk-forward ───────────────────────────────────────────────────────────
def run_walkforward(df):
    import lightgbm as lgb
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    oos_parts = []
    fold_stats = []
    last_model = None
    last_X_tr = None

    for fold_i, (train_max, test_years) in enumerate(WF_FOLDS):
        tr = df[df["year"] <= train_max].copy()
        te = df[df["year"].isin(test_years)].copy()
        if len(tr) < 50 or len(te) < 10:
            print(f"[fold {fold_i+1}] för få obs – hoppar.", flush=True)
            continue

        X_tr = tr[FEATURES].fillna(tr[FEATURES].median())
        y_tr = tr["label"]
        X_te = te[FEATURES].fillna(X_tr.median())

        model = lgb.LGBMClassifier(**LGBM_PARAMS)
        model.fit(X_tr, y_tr)
        te = te.copy()
        te["lgbm_score"] = model.predict_proba(X_te)[:, 1]

        scaler = StandardScaler()
        X_tr_s = scaler.fit_transform(X_tr)
        X_te_s = scaler.transform(X_te)
        lr = LogisticRegression(max_iter=500, C=1.0, random_state=42)
        lr.fit(X_tr_s, y_tr)
        te["lr_score"] = lr.predict_proba(X_te_s)[:, 1]

        for col in ("roa", "f_score"):
            if col in te.columns:
                te[f"{col}_score"] = te[col].rank(pct=True)

        oos_parts.append(te)
        last_model = model
        last_X_tr = X_tr

        fold_ic = {}
        for scol in ("lgbm_score", "lr_score", "roa_score", "f_score_score"):
            if scol in te.columns:
                mask = te[scol].notna() & te["excess_26w"].notna()
                if mask.sum() > 10:
                    rho, _ = stats.spearmanr(te.loc[mask, scol], te.loc[mask, "excess_26w"])
                    fold_ic[scol] = round(rho, 3)
        fold_stats.append({
            "fold": fold_i + 1,
            "train_years": f"2016-{train_max}",
            "test_years": "+".join(str(y) for y in test_years),
            "n_train": len(tr),
            "n_test": len(te),
            **fold_ic,
        })
        print(f"[fold {fold_i+1}] train=2016-{train_max} test={test_years} IC: {fold_ic}", flush=True)

    oos = pd.concat(oos_parts, ignore_index=True) if oos_parts else pd.DataFrame()
    return {"oos": oos, "fold_stats": fold_stats,
            "last_model": last_model, "last_X_tr": last_X_tr}


# ── 3. Portföljsimulering ─────────────────────────────────────────────────────
def portfolio_metrics(oos, score_col, px, top_q=0.3):
    results = []
    for sig_date, g in oos.groupby("signal_date"):
        if score_col not in g.columns or g[score_col].isna().all():
            continue
        threshold = g[score_col].quantile(1 - top_q)
        longs = g[g[score_col] >= threshold]["ticker"].tolist()
        if not longs:
            continue
        date = pd.Timestamp(sig_date)
        end_date = date + pd.Timedelta(weeks=HORIZON_W)
        period_rets = []
        for tk in longs:
            if tk not in px.columns:
                continue
            s = px[tk].dropna()
            i0 = s.index.searchsorted(date)
            i1 = s.index.searchsorted(end_date)
            if i0 < len(s) and i1 < len(s) and i1 > i0:
                period_rets.append(s.iloc[i1] / s.iloc[i0] - 1)
        if period_rets:
            results.append({"date": date, "ret": np.mean(period_rets), "n": len(period_rets)})

    if not results:
        return {}
    res_df = pd.DataFrame(results).sort_values("date")

    bm_rets = []
    for _, row in res_df.iterrows():
        date = row["date"]
        end_date = date + pd.Timedelta(weeks=HORIZON_W)
        pr = []
        for tk in px.columns:
            s = px[tk].dropna()
            i0 = s.index.searchsorted(date)
            i1 = s.index.searchsorted(end_date)
            if i0 < len(s) and i1 < len(s) and i1 > i0:
                pr.append(s.iloc[i1] / s.iloc[i0] - 1)
        bm_rets.append(np.mean(pr) if pr else 0.0)
    res_df["bm_ret"] = bm_rets
    res_df["alpha"] = res_df["ret"] - res_df["bm_ret"]

    periods_per_year = ANNUAL_WEEKS / HORIZON_W
    n = len(res_df)
    total_ret = (1 + res_df["ret"]).prod() - 1
    cagr = (1 + total_ret) ** (periods_per_year / n) - 1
    sharpe = (res_df["alpha"].mean() / res_df["alpha"].std() * np.sqrt(periods_per_year)
              if res_df["alpha"].std() > 0 else 0)
    cum = (1 + res_df["ret"]).cumprod()
    roll_max = cum.cummax()
    max_dd = ((cum - roll_max) / roll_max).min()
    hit_rate = (res_df["ret"] > res_df["bm_ret"]).mean()
    alpha_ann = res_df["alpha"].mean() * periods_per_year

    return {"cagr": round(cagr, 4), "sharpe": round(sharpe, 3),
            "max_dd": round(max_dd, 4), "alpha_ann": round(alpha_ann, 4),
            "hit_rate": round(hit_rate, 3), "n_periods": n}


# ── 4. SHAP ───────────────────────────────────────────────────────────────────
def shap_importance(model, X_tr):
    import shap
    explainer = shap.TreeExplainer(model)
    shap_vals = explainer.shap_values(X_tr)
    if isinstance(shap_vals, list):
        shap_vals = shap_vals[1]
    imp = pd.DataFrame({
        "feature":   FEATURES,
        "shap_mean": np.abs(shap_vals).mean(axis=0),
        "gain":      model.booster_.feature_importance(importance_type="gain"),
    }).sort_values("shap_mean", ascending=False)
    return imp


# ── 5. Helpers ────────────────────────────────────────────────────────────────
def ic_per_model(oos):
    out = {}
    for col in ("lgbm_score", "lr_score", "roa_score", "f_score_score"):
        if col not in oos.columns:
            continue
        mask = oos[col].notna() & oos["excess_26w"].notna()
        if mask.sum() > 20:
            rho, pval = stats.spearmanr(oos.loc[mask, col], oos.loc[mask, "excess_26w"])
            out[col] = {"ic": round(rho, 4), "pval": round(pval, 4), "n": int(mask.sum())}
    return out


def q5q1_spread(oos, score_col):
    if score_col not in oos.columns:
        return None
    mask = oos[score_col].notna() & oos["excess_26w"].notna()
    sub = oos[mask]
    if len(sub) < 20:
        return None
    q5 = sub[sub[score_col] >= sub[score_col].quantile(0.8)]["excess_26w"].mean()
    q1 = sub[sub[score_col] <= sub[score_col].quantile(0.2)]["excess_26w"].mean()
    return round(q5 - q1, 4)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 72)
    print("  BÖRSDATA FUNDAMENTALS – LGBM KOMBINATIONSTEST")
    print("=" * 72)

    df, _df_all = build_signal_panel()
    wf = run_walkforward(df)
    oos = wf["oos"]
    if oos.empty:
        print("Inga OOS-resultat – för lite data.")
        return

    # IC-rapport
    ics = ic_per_model(oos)
    print("\n" + "-" * 72)
    print("  IC-RAPPORT (poolad OOS · Spearman)")
    print("-" * 72)
    print(f"  {'modell':<22} {'IC':>8} {'p-val':>8} {'n':>6} {'Q5-Q1':>9}")
    print("  " + "-" * 56)
    for col, v in ics.items():
        label = col.replace("_score", "").replace("_", " ")
        q = q5q1_spread(oos, col)
        q_str = f"{q:+.1%}" if q is not None else "  n/a"
        pstar = "***" if v["pval"] < 0.01 else ("**" if v["pval"] < 0.05
                else ("*" if v["pval"] < 0.10 else "   "))
        print(f"  {label:<22} {v['ic']:>+8.4f} {v['pval']:>8.4f}{pstar} "
              f"{v['n']:>6} {q_str:>9}")

    # Per-fold
    print("\n  Per-fold IC (lgbm / lr / roa / f_score):")
    for fs in wf["fold_stats"]:
        def _f(k):
            val = fs.get(k)
            return f"{val:>+7.3f}" if isinstance(val, float) else "    n/a"
        print(f"  fold {fs['fold']} train={fs['train_years']} test={fs['test_years']:10}"
              f"  lgbm={_f('lgbm_score')}  lr={_f('lr_score')}"
              f"  roa={_f('roa_score')}  fscore={_f('f_score_score')}")

    # Portföljsimulering
    data = fetch_weekly_data(sorted(oos["ticker"].unique()),
                             start="2015-01-01", end=None, use_cache=True)
    px = pd.DataFrame(
        {t: d["Close"] for t, d in data.items() if d is not None and "Close" in d}
    ).sort_index()
    px.index = pd.to_datetime(px.index)

    print("\n" + "-" * 72)
    print("  PORTFÖLJSIMULERING (long top-30%, 26v hållperiod)")
    print("-" * 72)
    print(f"  {'modell':<22} {'CAGR':>8} {'Sharpe':>8} {'MaxDD':>8} {'Alpha/år':>9} {'Hit%':>7}")
    print("  " + "-" * 63)
    for col in ("lgbm_score", "lr_score", "roa_score", "f_score_score"):
        if col not in oos.columns:
            continue
        m = portfolio_metrics(oos, col, px)
        if not m:
            continue
        label = col.replace("_score", "").replace("_", " ")
        print(f"  {label:<22} {m['cagr']:>+8.1%} {m['sharpe']:>8.3f} "
              f"{m['max_dd']:>+8.1%} {m['alpha_ann']:>+9.1%} {m['hit_rate']:>6.0%}")

    # SHAP / Gain
    print("\n" + "-" * 72)
    print("  FEATURE IMPORTANCE (senaste fold – SHAP |mean| + gain-andel)")
    print("-" * 72)
    try:
        imp = shap_importance(wf["last_model"], wf["last_X_tr"])
        print(f"  {'feature':<16} {'SHAP':>10} {'gain%':>8}  bar")
        print("  " + "-" * 50)
        max_shap = imp["shap_mean"].max() or 1
        total_gain = imp["gain"].sum() or 1
        for _, row in imp.iterrows():
            bar = "=" * max(1, int(row["shap_mean"] / max_shap * 20))
            print(f"  {row['feature']:<16} {row['shap_mean']:>10.4f} "
                  f"{row['gain']/total_gain:>7.1%}  {bar}")
    except Exception as e:
        print(f"  [SHAP ej tillgänglig: {e}]")
        imp_gain = pd.DataFrame({
            "feature": FEATURES,
            "gain": wf["last_model"].booster_.feature_importance(importance_type="gain"),
        }).sort_values("gain", ascending=False)
        total = imp_gain["gain"].sum() or 1
        for _, row in imp_gain.iterrows():
            bar = "=" * max(1, int(row["gain"] / total * 20))
            print(f"  {row['feature']:<16} gain={row['gain']/total:>6.1%}  {bar}")

    # Slutsats
    pooled_lgbm_ic = ics.get("lgbm_score", {}).get("ic", 0.0)
    pooled_roa_ic  = ics.get("roa_score",  {}).get("ic", 0.0)
    n_folds = len(wf["fold_stats"])
    consistent = sum(
        1 for fs in wf["fold_stats"] if isinstance(fs.get("lgbm_score"), float) and fs["lgbm_score"] > 0
    ) >= max(2, n_folds - 1)
    beats_baseline = pooled_lgbm_ic > pooled_roa_ic + 0.02

    print("\n" + "=" * 72)
    print("  SLUTSATS")
    print("=" * 72)
    print(f"  LightGBM OOS IC: {pooled_lgbm_ic:+.4f}  |  ROA-baseline IC: {pooled_roa_ic:+.4f}")
    print(f"  Konsistent (>0 i >= {max(2,n_folds-1)}/{n_folds} folds): {consistent}")
    print(f"  Slår ROA-baseline med >0.02: {beats_baseline}")

    if pooled_lgbm_ic >= 0.05 and consistent and beats_baseline:
        rec = (
            "INTEGRERA: LightGBM hittar kombinerad signal (IC "
            f"{pooled_lgbm_ic:+.3f}) som ar konsistent och slar ROA-baseline. "
            "Lagg till i FEATURE_COLS och attach_fundamentals_features()."
        )
    elif pooled_lgbm_ic >= 0.03 and (consistent or beats_baseline):
        rec = (
            f"TVEKSAMT: IC {pooled_lgbm_ic:+.3f} ar svagt och/eller inkonsistent. "
            "Integrera inte i detta lage – foljd upp med mer data."
        )
    else:
        rec = (
            f"INTEGRERA INTE: LightGBM IC {pooled_lgbm_ic:+.3f} nar inte troskeln "
            "och/eller slar inte enkel ROA-ranking. Borsdata-fundamenta tillfor "
            "ingen matbar signal utover det modellen redan har via MFN/Avanza.\n"
            "  Skäl 1: Arsrapportdata har ~12-manaders latens; MFN-pipeline har kvartal.\n"
            "  Skäl 2: Maj-antagandet introducerar brus vs MFNs exakta publishertampel.\n"
            "  Skäl 3: Svaga univariata IC + liten dataset ger LGBM inget att kombinera."
        )
    print(f"\n  {rec}\n")


if __name__ == "__main__":
    main()
