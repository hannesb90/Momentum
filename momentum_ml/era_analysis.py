"""
era_analysis.py – Håller edgen i den algo-dominerade eran (och blir den sämre
mot nutid)?

Stockholmsbörsen blev algo/HFT-dominerad ca 2010-2013 (Nasdaq INET okt 2010 +
MiFID I). Vår walk-forward testar dessutom bara 2016+ (allt OOS). Här skär vi
strategins faktiska resultat per startår och jämför CAGR/Sharpe + alfa mot
likaviktat och mot OMXS30, för att se om försprånget håller i sig mot nutid.

Ren efter-bearbetning av results/portfolio.csv (ingen omträning/backtest):

    /opt/momentum/venv/bin/python era_analysis.py [large|small]
"""
import sys, math
sys.path.insert(0, '.')
import pandas as pd
import config


def cagr_sharpe(s):
    s = s.dropna()
    if len(s) < 10:
        return None, None
    r = s.pct_change().dropna()
    weeks = len(r)
    cagr = (s.iloc[-1] / s.iloc[0]) ** (52 / weeks) - 1
    sharpe = (r.mean() / r.std()) * math.sqrt(52) if r.std() > 0 else 0.0
    return cagr, sharpe


def main():
    seg = sys.argv[1] if len(sys.argv) > 1 else config.DEFAULT_SEGMENT
    segcfg = config.SEGMENTS.get(seg) or config.SEGMENTS[config.DEFAULT_SEGMENT]
    rd = segcfg["results_dir"]
    # Rätt index per segment (small jämförs mot småbolagsindex, inte OMXS30).
    ilabel = segcfg.get("index_label", "index")
    df = pd.read_csv(f"{rd}/portfolio.csv", index_col=0, parse_dates=True)
    has_ew = "benchmark_value" in df.columns
    has_omx = "omxs30_value" in df.columns

    # Walk-forward testar 2016+ → de rena OOS-fönstren. 2010-2015 = uppvärmning
    # (visas för referens, mindre rent OOS).
    starts = [("2010", "hela (m. uppvärmning)"),
              ("2016", "algo-era OOS"),
              ("2018", "senaste ~6 år"),
              ("2021", "senaste ~4 år"),
              ("2023", "senaste ~2 år")]

    print("\n" + "=" * 78)
    print(f"  ERA-TEST ({seg}) – håller edgen mot nutid? (alfa mot likaviktat / {ilabel})")
    print("=" * 78)
    print(f"  {'från':>6} {'CAGR':>7} {'Sharpe':>7} {'alfa(EW)':>9} {'alfa(idx)':>10}  period")
    print(f"  (idx = {ilabel})")
    print("-" * 78)
    for st, label in starts:
        sub = df[df.index >= st]
        if len(sub) < 30:
            continue
        sc, ss = cagr_sharpe(sub["portfolio_value"])
        ew = f"{sc - cagr_sharpe(sub['benchmark_value'])[0]:+.1%}" if has_ew else "  –"
        idx = f"{sc - cagr_sharpe(sub['omxs30_value'])[0]:+.1%}" if has_omx else "   –"
        print(f"  {st+'+':>6} {sc:>+7.1%} {ss:>7.2f} {ew:>9} {idx:>10}  {label}")
    print("-" * 78)
    print(f"  Håller alfa({ilabel}) positiv även i 2021+/2023+ -> edgen lever i algo-eran.")


if __name__ == "__main__":
    main()
