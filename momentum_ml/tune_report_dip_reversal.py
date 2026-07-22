"""
tune_report_dip_reversal.py – Finns en REVERSAL-edge efter ett ovanligt kraftigt
negativt rapportvecko-utfall (en "överreaktion"), i motsats till klassisk PEAD
(tune_pead.py), som mäter FORTSATT drift i samma riktning som reaktionen?

Bakgrund (användarens hypotes, 2026-07-22): "aktien dök även om rapporten var
bra/neutral" och "aktien dök på missade förväntningar men nedgången var orimligt
stor" - båda handlar om samma underliggande fråga: när rapportveckans utfall är
ovanligt negativt, ÄR DET EN ÖVERREAKTION SOM STUDSAR TILLBAKA, eller fortsätter
priset ner (klassisk PEAD-drift, samma riktning)? Vi har inga analytikerestimat
(skulle krävt en betaltjänst) och ingen historisk logg av report_analysis.py:s
LLM-bedömning (ny funktion, ingen historik än) - så "var rapporten bra/dålig"
kan INTE testas direkt här. I stället testas den RENA, token-fria, historiskt
tillgängliga versionen: är sambandet mellan rapportveckans abnormala avkastning
och FRAMÅTavkastningen olinjärt (V-format - botten-decilen studsar upp trots
att resten av kurvan fortsätter nedåt = överreaktion) i stället för linjärt
(ren PEAD-fortsättning hela vägen)? Om edgen finns SKA den synas i botten-
decilen oavsett "varför" reaktionen var negativ.

Återanvänder EXAKT samma abnormal-avkastningsdefinition som altdata.pead.py
(aktiens veckoavkastning minus likaviktad marknadsavkastning samma vecka) och
samma MFN-rapportdatum-extraktion, för att vara jämförbar med tune_pead.py:s
redan etablerade resultat - bara analysen (decilvis medel i stället för en
enda linjär IC) skiljer sig, eftersom en reversal-effekt är en OLINJÄR
hypotes som en enda Spearman-IC kan dölja helt (positiv i mitten, negativ i
botten tar ut varandra i snittet).

Kör (från /opt/momentum/src/momentum_ml, kräver MFN-cache, se tune_pead.py):
    /opt/momentum/venv/bin/python tune_report_dip_reversal.py
"""
import sys

sys.path.insert(0, ".")
import numpy as np
import pandas as pd

import config
from data.data_loader import (
    fetch_weekly_data, filter_liquid_universe, filter_active_universe, load_sweden_universe,
)
from altdata.pead import load_report_dates
from features.feature_engineering import _load_fundamentals_growth

# 156v (~3 år) tillagd 2026-07-22 på användarens begäran - många av
# innehaven hålls på 3-årig horisont, inte de 26v (~6 mån) som redan
# testats. OBS databegränsning: prisdata börjar 2010-01-01 och slutar idag,
# så EVENT som ligger inom de sista ~156 veckorna saknar 156v framåtdata
# helt (per-rad-kollen "wi >= len(px.index)" nedan hoppar över dem tyst,
# vilket är rätt - annars censurerad/ofullständig utfallsdata) - "holdout"
# (sista HOLDOUT_WEEKS=104v ≈ 2 år) kommer därför visa "–" rakt igenom
# 156v-kolumnen, det är väntat, inte en bugg: de händelserna är för färska
# för att ha hunnit realisera ett 3-årsutfall än.
HORIZONS = (1, 4, 8, 13, 26, 156)   # veckor framåt att mäta studs/fortsatt fall mot
N_BUCKETS = 10                       # deciler av rapportveckans abnormala avkastning
GROWTH_TERCILE = 2.0 / 3.0            # tillväxtbolag = översta tercilen av rev_growth_yoy


def _report_reactions(px: pd.DataFrame, report_dates: dict) -> pd.DataFrame:
    """EN rad per (ticker, rapportvecka): reaction = abnormal avkastning
    rapportveckan. Samma definition som compute_pead_panel() i pead.py -
    bara utan drift-avklingningen, vi vill ha den RÅA reaktionen per
    händelse för decil-analysen. Behåller det RÅA rapportdatumet (inte bara
    veckans startdatum) så vi kan slå ihop mot tillväxtsiffror per faktisk
    rapport nedan."""
    rets = px.pct_change()
    market = rets.mean(axis=1)          # likaviktad marknadsproxy, som pead.py
    abn = rets.sub(market, axis=0)
    weeks = px.index

    rows = []
    for ticker, dates in report_dates.items():
        if ticker not in px.columns or not dates:
            continue
        col_abn = abn[ticker]
        for d in dates:
            pos = weeks.searchsorted(pd.Timestamp(d).normalize(), side="left")
            if pos >= len(weeks):
                continue
            ann_week = weeks[pos]
            reaction = col_abn.get(ann_week, np.nan)
            if pd.isna(reaction):
                continue
            rows.append({"ticker": ticker, "week": ann_week, "week_pos": pos,
                         "reaction": reaction, "report_date": pd.Timestamp(d).normalize()})
    return pd.DataFrame(rows)


def _attach_growth(events: pd.DataFrame) -> pd.DataFrame:
    """Slår ihop rev_growth_yoy (samma källa som feature_engineering.py:s
    modell-feature, se _load_fundamentals_growth) mot varje händelse via
    (ticker, närmast rapportdatum) - MFN:s eget publiceringsdatum och
    fundamenta-extraktionens 'published' kommer från samma rapport men
    parsas separat, så en exakt datummatch missar ibland med någon dag."""
    growth = _load_fundamentals_growth("large")
    if growth.empty:
        events["rev_growth_yoy"] = np.nan
        return events
    growth = growth.sort_values("published")
    events = events.sort_values("report_date")
    merged = pd.merge_asof(
        events, growth[["ticker", "published", "rev_growth_yoy"]],
        left_on="report_date", right_on="published", by="ticker",
        direction="nearest", tolerance=pd.Timedelta(days=5),
    )
    return merged.drop(columns=["published"])


def _decile_table(label: str, ev: pd.DataFrame, px: pd.DataFrame, n_buckets: int = N_BUCKETS) -> None:
    print("\n" + "=" * 78)
    print(f"  {label} ({len(ev)} händelser)")
    print("=" * 78)
    if len(ev) < n_buckets * 5:
        print(f"  (för få händelser för {n_buckets}-bucketanalys, hoppar över)")
        return
    ev = ev.copy()
    ev["bucket"] = pd.qcut(ev["reaction"], n_buckets, labels=False, duplicates="drop")
    bucket_react = ev.groupby("bucket")["reaction"].agg(["mean", "count"])

    print(f"  {'bucket':<7}{'reaktion':>10}{'n':>6}" +
          "".join(f"{f'{h}v fwd':>10}" for h in HORIZONS) +
          "".join(f"{f'{h}v hit%':>10}" for h in HORIZONS))
    print("-" * 78)
    for b in sorted(ev["bucket"].dropna().unique()):
        sub = ev[ev["bucket"] == b]
        fwd_means, hit_rates = [], []
        for h in HORIZONS:
            vals = []
            for _, row in sub.iterrows():
                wi = row["week_pos"] + h
                if wi >= len(px.index):
                    continue
                t = row["ticker"]
                if t not in px.columns:
                    continue
                p0, p1 = px[t].iloc[int(row["week_pos"])], px[t].iloc[int(wi)]
                if pd.isna(p0) or pd.isna(p1) or p0 == 0:
                    continue
                vals.append(p1 / p0 - 1)
            fwd_means.append(np.mean(vals) if vals else float("nan"))
            hit_rates.append(np.mean([v > 0 for v in vals]) if vals else float("nan"))
        react_mean = bucket_react.loc[b, "mean"]
        n = int(bucket_react.loc[b, "count"])
        print(f"  {int(b):<7}{react_mean:>10.2%}{n:>6}" +
              "".join(f"{v:>10.2%}" if pd.notna(v) else f"{'–':>10}" for v in fwd_means) +
              "".join(f"{v:>10.1%}" if pd.notna(v) else f"{'–':>10}" for v in hit_rates))
    print("-" * 78)
    print("  Tolkning: PEAD (fortsättning) → botten-bucketen SÄMST framåt, monotont stigande")
    print("  uppåt. REVERSAL/överreaktion → botten-bucketen (mest negativ reaktion) har")
    print("  BÄTTRE framåtavkastning än nästa bucket, bryter mönstret - en 'studs'.")


def main():
    seg = config.SEGMENTS["large"]
    tickers, sector_map, cap_tier_map, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)
    px = pd.DataFrame({t: d["Close"] for t, d in data.items() if "Close" in d}).sort_index()

    report_dates = load_report_dates(config.MFN_CACHE_DIR)
    if not report_dates:
        print(f"Ingen MFN-cache i {config.MFN_CACHE_DIR}. Kör fetch_universe först (se tune_pead.py).")
        return

    events = _report_reactions(px, report_dates)
    if events.empty:
        print("Inga rapporthändelser matchade universum-tickers.")
        return
    events = _attach_growth(events)
    n_growth = events["rev_growth_yoy"].notna().sum()
    print(f"\n{len(events)} rapporthändelser, {events['ticker'].nunique()} bolag "
          f"({n_growth} med rev_growth_yoy matchad, {len(events) - n_growth} utan - "
          f"exkluderas ur tillväxtdelen nedan, ingår i 'alla bolag').")

    holdout_start_pos = len(px.index) - config.HOLDOUT_WEEKS if len(px.index) > config.HOLDOUT_WEEKS else 0
    last_valid_156v_pos = len(px.index) - 156

    print(f"\n[OBS 156v/3-årshorisont]: kräver att händelsen inträffat före veckoindex "
          f"{last_valid_156v_pos} ({px.index[last_valid_156v_pos].date() if 0 <= last_valid_156v_pos < len(px.index) else 'n/a'}) "
          f"för att ha fullständig framåtdata - holdout (sista {config.HOLDOUT_WEEKS}v) ligger "
          f"per definition EFTER den punkten, så 156v-kolumnen blir tom där. Väntat, inte en bugg.")

    _decile_table("alla bolag – hela perioden", events, px)
    _decile_table("alla bolag – holdout", events[events["week_pos"] >= holdout_start_pos], px)

    # "Moget" 3-års-holdout: den SENASTE HOLDOUT_WEEKS-perioden av händelser som
    # ändå hunnit få fullständig 156v-framåtdata (dvs. direkt före
    # last_valid_156v_pos, inte samma fönster som standardholdouten ovan - den
    # kan strukturellt aldrig ha 156v-data, se OBS ovan). Fortfarande den mest
    # "ute-av-sample" delen möjlig för just den här horisonten.
    lh_start = max(0, last_valid_156v_pos - config.HOLDOUT_WEEKS)
    lh_end = last_valid_156v_pos
    lh_events = events[(events["week_pos"] >= lh_start) & (events["week_pos"] < lh_end)]
    print(f"\n[Moget 3-års-holdout]: händelser {px.index[lh_start].date()} till "
          f"{px.index[lh_end - 1].date()} ({len(lh_events)} händelser) - senaste "
          f"{config.HOLDOUT_WEEKS}v som ändå hunnit realisera ett 156v-utfall.")
    _decile_table("alla bolag – moget 3-års-holdout", lh_events, px)

    growth_cut = events["rev_growth_yoy"].quantile(GROWTH_TERCILE)
    growth_events = events[events["rev_growth_yoy"] >= growth_cut]
    print(f"\n[Tillväxtbolag-definition]: översta tercilen rev_growth_yoy vid rapporttillfället "
          f"(>= {growth_cut:.1%} YoY, n={len(growth_events)} av {n_growth} med känd tillväxt).")
    _decile_table("tillväxtbolag – hela perioden", growth_events, px, n_buckets=5)
    _decile_table("tillväxtbolag – holdout", growth_events[growth_events["week_pos"] >= holdout_start_pos], px, n_buckets=5)
    _decile_table("tillväxtbolag – moget 3-års-holdout",
                   growth_events[(growth_events["week_pos"] >= lh_start) & (growth_events["week_pos"] < lh_end)],
                   px, n_buckets=5)


if __name__ == "__main__":
    main()
