"""
tune_hold_forever_fundamentals.py – Kan FUNDAMENTA vid köptillfället skilja
3-årsvinnarna från förlorarna bland modellens köpsignaler?

Uppföljning på tune_hold_forever.py (2026-07-22), som visade att momentum-
signalens edge klingar av med innehavstiden (median-excess +1.4% @13v → −24%
@156v, win 54% → 37%): det TYPISKA köpet släpar index på 3 år, men medlen bärs
av en liten minoritet extremvinnare. Frågan här: syntes vinnarna i förväg i
FUNDAMENTA (det enda faktorspår som enligt litteraturen håller på fleråriga
horisonter – kvalitet/värde – till skillnad från pris/sektor/text-mönster som
husets logg redan dömt ut: #7/#8 överanpassning, sektor-gap IC≈0, #18 text)?

Poängen är MEDVETET pre-registrerad på husets egna befintliga barrer (samma
anda som quality_screener/buffett-ranken), INTE datadrivet optimerad – vi
letar bekräftelse/falsifiering av en befintlig tes, inte nya mönster att
överanpassa:
    · ROE            (roe_avanza, fallback roe_pct)          – högre bättre
    · rev_growth_yoy ((revenue−prior)/|prior|)                – högre bättre
    · skuldsättning  (debt_equity_avanza, fallback liab/eq)   – LÄGRE bättre
Komposit = medel av tillgängliga percentilranker (≥2 av 3 krävs). Tercilerna
jämförs på median-excess + win% mot likaviktat index (samma metodik/förbehåll
som tune_hold_forever.py: överlappande fönster, survivorship-delat index).

DATABEGRÄNSNINGAR (ärliga, kontrollerade innan bygget):
  · roe_avanza/debt_equity_avanza börjar 2019 (MFN-textens roe_pct är ~tom
    historiskt, ~8 rader/år) → testfönstret är köp 2019 → (idag−156v) ≈
    mitten 2023 för 3-årsutfall. Tunt (~150-200/tercil) men inte tomt.
  · Avanza-raderna är årsdata med syntetiserade publiceringsdatum → grov
    point-in-time (upp till ~15 mån stale vid merge_asof backward). Godtagbart
    för diagnostik, inte för live-signal.
  · Avanza hämtades nyligen för NUVARANDE bolag → avnoterade saknar fundamenta
    → de poängsatta inträdena är extra survivorship-vinklade. Därför skrivs
    även "opoängsatt"-raden ut som jämförelse (är de poängsatta ens
    representativa?).

Kör (Pi:n, lätt jobb – CSV:er + priscache, ingen MFN-rå-cache):
    /opt/momentum/venv/bin/python tune_hold_forever_fundamentals.py
"""
import sys

sys.path.insert(0, ".")
import numpy as np
import pandas as pd

import config
from data.data_loader import (
    fetch_weekly_data, filter_liquid_universe, filter_active_universe, load_sweden_universe,
)

HORIZONS = (13, 26, 52, 104, 156)
MERGE_TOLERANCE_DAYS = 400   # årsrapporter: senaste kända rapport max ~13 mån bakåt
MIN_METRICS = 2              # kräv minst 2 av 3 poängkomponenter


def _load_entries() -> pd.DataFrame:
    seg = config.SEGMENTS["large"]
    p = f"{config.anchor(seg['results_dir'])}/signals.csv"
    sig = pd.read_csv(p, usecols=["Date", "ticker", "pred_signal"], parse_dates=["Date"])
    sig = sig.sort_values(["ticker", "Date"])
    prev = sig.groupby("ticker")["pred_signal"].shift(1)
    entries = sig[(sig["pred_signal"] == 1) & (prev.fillna(0) == 0)]
    return entries[["Date", "ticker"]].reset_index(drop=True)


def _load_fundamentals() -> pd.DataFrame:
    """Alla tre fundamenta-CSV:erna → en rad per rapport med råmetriker."""
    seg = config.SEGMENTS["large"]
    rd = config.anchor(seg["results_dir"])
    frames = []
    for fname in ("fundamentals_from_mfn.csv", "fundamentals_from_pdf.csv",
                  "fundamentals_from_avanza.csv"):
        try:
            frames.append(pd.read_csv(f"{rd}/{fname}"))
        except Exception:  # noqa: BLE001
            pass
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df["published"] = pd.to_datetime(df["published"], errors="coerce", utc=True).dt.tz_localize(None)
    df = df.dropna(subset=["ticker", "published"])

    def col(name):
        return pd.to_numeric(df[name], errors="coerce") if name in df.columns else pd.Series(np.nan, index=df.index)

    roe = col("roe_avanza").where(lambda s: s.notna(), col("roe_pct"))
    rev, rev_prior = col("revenue"), col("revenue_prior")
    growth = (rev - rev_prior) / rev_prior.abs()
    growth[(rev_prior == 0) | rev_prior.isna() | rev.isna()] = np.nan
    liab, eq = col("liabilities"), col("equity")
    de_fallback = (liab / eq).where((eq > 0) & liab.notna())
    debt_eq = col("debt_equity_avanza").where(lambda s: s.notna(), de_fallback)

    out = pd.DataFrame({"ticker": df["ticker"], "published": df["published"],
                        "roe": roe, "growth": growth, "debt_eq": debt_eq})
    out = out.dropna(subset=["roe", "growth", "debt_eq"], how="all")
    return out.sort_values("published")


def main():
    seg = config.SEGMENTS["large"]
    tickers, sector_map, cap_tier_map, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)
    px = pd.DataFrame({t: d["Close"] for t, d in data.items() if "Close" in d}).sort_index()
    idx_level = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    weeks = px.index

    entries = _load_entries()
    entries = entries[entries["Date"] >= "2019-01-01"]   # fundamenta-täckning börjar 2019
    entries["week_pos"] = weeks.searchsorted(entries["Date"], side="left")
    entries = entries[entries["week_pos"] < len(weeks)]

    fund = _load_fundamentals()
    if fund.empty:
        print("Inga fundamenta-CSV:er hittade – kör altdata-pipelinen först.")
        return
    entries = entries.sort_values("Date")
    merged = pd.merge_asof(entries, fund, left_on="Date", right_on="published",
                           by="ticker", direction="backward",
                           tolerance=pd.Timedelta(days=MERGE_TOLERANCE_DAYS))

    # Komposit: medel av percentilranker (debt inverterad), kräver >= MIN_METRICS.
    ranks = pd.DataFrame(index=merged.index)
    ranks["roe"] = merged["roe"].rank(pct=True)
    ranks["growth"] = merged["growth"].rank(pct=True)
    ranks["debt"] = (-merged["debt_eq"]).rank(pct=True)
    n_avail = ranks.notna().sum(axis=1)
    merged["score"] = ranks.mean(axis=1).where(n_avail >= MIN_METRICS)

    scored = merged[merged["score"].notna()].copy()
    unscored = merged[merged["score"].isna()]
    print(f"{len(merged)} köpsignal-inträden sedan 2019 – {len(scored)} poängsatta "
          f"(fundamenta ≤{MERGE_TOLERANCE_DAYS}d före köpet, ≥{MIN_METRICS}/3 metriker), "
          f"{len(unscored)} utan fundamenta.")

    scored["tercil"] = pd.qcut(scored["score"], 3, labels=["T1 (svag)", "T2", "T3 (stark)"])

    def _stats(sub, h):
        rets, excs = [], []
        for _, row in sub.iterrows():
            p0i, p1i = int(row["week_pos"]), int(row["week_pos"]) + h
            if p1i >= len(weeks) or row["ticker"] not in px.columns:
                continue
            p0, p1 = px[row["ticker"]].iloc[p0i], px[row["ticker"]].iloc[p1i]
            if pd.isna(p0) or pd.isna(p1) or p0 == 0:
                continue
            r = p1 / p0 - 1
            b = idx_level.iloc[p1i] / idx_level.iloc[p0i] - 1
            rets.append(r)
            excs.append(r - b)
        if not rets:
            return None
        return (float(np.median(excs)), float(np.mean([e > 0 for e in excs])), len(rets))

    header = (f"  {'grupp':<12}{'n':>6}"
              + "".join(f"{f'{h}v exc':>10}{f'{h}v win%':>9}{f'{h}v n':>7}" for h in HORIZONS))
    print("\n" + "=" * len(header))
    print("  Fundamenta-terciler vid köptillfället – median-excess & win% vs likaviktat index")
    print("=" * len(header))
    print(header)
    print("-" * len(header))
    groups = [(str(t), scored[scored["tercil"] == t]) for t in scored["tercil"].cat.categories]
    groups.append(("opoängsatt", unscored))
    for label, sub in groups:
        cells = f"  {label:<12}{len(sub):>6}"
        for h in HORIZONS:
            st = _stats(sub, h)
            if st is None:
                cells += f"{'–':>10}{'–':>9}{'–':>7}"
            else:
                e, w, n = st
                cells += f"{e:>+10.1%}{w:>8.0%} {n:>7}"
        print(cells)
    print("-" * len(header))
    print("  Läsning: håller fundamenta-tesen ska T3 (stark) slå T1 (svag) tydligt på de")
    print("  långa horisonterna (104/156v). 'opoängsatt' = inträden utan färsk fundamenta –")
    print("  jämförelserad för selektionsbias (poängsatta bolag är survivorship-vinklade).")
    print("  OBS: 156v-kolumnen täcker bara köp t.o.m. ~mitten 2023 (strukturellt, som förut).")

    # Extremutfalls-koll: fångar terciler de STORA vinnarna (den skeva svansen)?
    print("\n  Andel av köpen som blev 156v-dubblare (abs ≥ +100%) resp. halverare (≤ −50%):")
    for label, sub in groups:
        vals = []
        for _, row in sub.iterrows():
            p0i, p1i = int(row["week_pos"]), int(row["week_pos"]) + 156
            if p1i >= len(weeks) or row["ticker"] not in px.columns:
                continue
            p0, p1 = px[row["ticker"]].iloc[p0i], px[row["ticker"]].iloc[p1i]
            if pd.isna(p0) or pd.isna(p1) or p0 == 0:
                continue
            vals.append(p1 / p0 - 1)
        if vals:
            dbl = np.mean([v >= 1.0 for v in vals])
            half = np.mean([v <= -0.5 for v in vals])
            print(f"    {label:<12} n={len(vals):<5} dubblare: {dbl:>5.1%}   halverare: {half:>5.1%}")
        else:
            print(f"    {label:<12} (ingen 156v-data)")


if __name__ == "__main__":
    main()
