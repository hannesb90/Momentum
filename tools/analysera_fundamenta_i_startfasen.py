"""ANALYS AV FUNDAMENTA OCH VOLYM I STARTFASEN

Testar om icke-prisbaserade faktorer i core_fundamenta_panel.json
kan skilja Stora Vinnare från Falska Utbrott för kortsiktiga utbrott (M13 Top 30 + M52 Rank > 100).

Mäter:
  1. Omsättningstillväxt YoY (revenue_growth_yoy)
  2. Vinsttillväxt YoY (eps_growth_yoy)
  3. Volymtrend 13v (volume_trend_13w)
  4. Rörelsemarginal (operating_margin_ttm)
  5. Avkastning på eget kapital (roe_ttm)
  6. Rapportreaktion (return_since_last_report_ttm)
  7. Aktieutveckling YoY (shares_growth_yoy)

DIAGNOSTISKT.
Kör: /opt/momentum/venv/bin/python tools/analysera_fundamenta_i_startfasen.py
"""
from __future__ import annotations
import json, math, statistics
from pathlib import Path
import pandas as pd
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/fundamenta_startfas_results.json"


def main():
    print("Laddar core_fundamenta_panel.json...")
    fp = V2 / "panels/core_fundamenta_panel.json"
    df = pd.read_json(fp)
    print(f"  Totalt {len(df)} rader.")

    # Ladda target_table.json (dict: kod -> list of dicts)
    tp = V2 / "panels/target_table.json"
    target_rows = []
    if tp.exists():
        t_data = json.loads(tp.read_text())
        for k, rows in t_data.items():
            for r in rows:
                target_rows.append({
                    "kod": k,
                    "panel_date": r["panel_date"],
                    "target_52w": r.get("target_fwd52w"),
                })
        tdf = pd.DataFrame(target_rows)
        df = df.merge(tdf, on=["kod", "panel_date"], how="inner")
        print(f"  Merge med target: {len(df)} rader.")

    # Filtrera för kortsiktigt utbrott: mom_13w i Topp 30 OCH mom_52w LÅG (rank > 100)
    df["rank_13w"] = df.groupby("panel_date")["mom_13w"].rank(ascending=False)
    df["rank_52w"] = df.groupby("panel_date")["mom_52w"].rank(ascending=False)

    sub = df[(df["rank_13w"] <= 30) & (df["rank_52w"] > 100) & (df["target_52w"].notna())].copy()
    print(f"  Antal tidiga utbrottsobservationer (13w Top 30 & 52w Rank > 100): {len(sub)}")

    vinnare = sub[sub["target_52w"] >= 0.50]
    forlorare = sub[sub["target_52w"] <= -0.15]

    print(f"  Vinnare (target 52v ≥ +50%): {len(vinnare)}")
    print(f"  Förlorare (target 52v ≤ -15%): {len(forlorare)}")

    metrics = [
        ("Revenue Growth YoY", "revenue_growth_yoy", "pct"),
        ("EPS Growth YoY", "eps_growth_yoy", "pct"),
        ("Volume Trend 13w", "volume_trend_13w", "float"),
        ("Operating Margin TTM", "operating_margin_ttm", "pct"),
        ("ROE TTM", "roe_ttm", "pct"),
        ("Return Since Last Report", "return_since_last_report_ttm", "pct"),
        ("Shares Growth YoY (Utspädning/Återköp)", "shares_growth_yoy", "pct"),
        ("Amihud Illiquidity 13w", "illiquidity_amihud_13w", "float"),
        ("Momentum Acceleration 13w", "momentum_acceleration_13w", "float"),
    ]

    print(f"\n{'='*95}")
    print("FUNDAMENTA OCH VOLYM I STARTFASEN (Medianer)")
    print(f"{'='*95}")
    print(f"  {'Egenskap':42s} {'Vinnare (≥+50%)':>18s} {'Förlorare (≤-15%)':>18s} {'Diff':>12s}")

    def med(series):
        s = series.dropna()
        return float(s.median()) if len(s) > 0 else None

    def fmt(v, fmt_type):
        if v is None or not math.isfinite(v):
            return "N/A"
        if fmt_type == "pct":
            return f"{v:.1%}"
        return f"{v:.2f}"

    results = {}
    for label, col, fmt_type in metrics:
        v_m = med(vinnare[col])
        f_m = med(forlorare[col])
        diff = (v_m - f_m) if v_m is not None and f_m is not None else None
        print(f"  {label:42s} {fmt(v_m, fmt_type):>18s} {fmt(f_m, fmt_type):>18s} {fmt(diff, fmt_type):>12s}")
        results[col] = {"vinnare": v_m, "forlorare": f_m, "diff": diff}

    # Test kombinerat filter på fundamenta och volym
    print(f"\n{'='*95}")
    print("TEST AV FUNDAMENTALA OCH VOLYMBASERADE REGLER FÖR TIDIGA UTBROTT")
    print(f"{'='*95}")

    rules = [
        ("Ingen filter (alla M13 Top30 & M52 > 100)", lambda d: pd.Series(True, index=d.index)),
        ("Positiv omsättningstillväxt (Revenue Growth > 0)", lambda d: d["revenue_growth_yoy"] > 0),
        ("Stark omsättningstillväxt (Revenue Growth > 15%)", lambda d: d["revenue_growth_yoy"] > 0.15),
        ("Positiv vinsttillväxt (EPS Growth > 0)", lambda d: d["eps_growth_yoy"] > 0),
        ("Positiv Volymtrend (Volume Trend > 1.0)", lambda d: d["volume_trend_13w"] > 1.0),
        ("Lönsamt bolag (Operating Margin > 0)", lambda d: d["operating_margin_ttm"] > 0),
        ("Kombination: RevGrowth>10% OCH OpMargin>0 OCH VolTrend>1.0",
         lambda d: (d["revenue_growth_yoy"] > 0.10) & (d["operating_margin_ttm"] > 0) & (d["volume_trend_13w"] > 1.0)),
    ]

    for r_label, r_fn in rules:
        cond = r_fn(sub)
        sub_rule = sub[cond].copy()
        if len(sub_rule) == 0:
            continue
        n = len(sub_rule)
        w = len(sub_rule[sub_rule["target_52w"] >= 0.50])
        l = len(sub_rule[sub_rule["target_52w"] <= -0.15])
        med_ret = sub_rule["target_52w"].median()
        print(f"  {r_label:58s}: N={n:4d} | Vinnare: {w/n:.1%} | Förlorare: {l/n:.1%} | MedRet 52v: {fmt(med_ret, 'pct')}")

    OUT.write_text(json.dumps({
        "version": "FUNDAMENTA_STARTFAS_ANALYS_V1",
        "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "results": results,
    }, ensure_ascii=False, indent=2))
    print(f"\n  → {OUT.name}")


if __name__ == "__main__":
    main()
