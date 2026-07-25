"""Kausal audit av en separat modell för redan kvalificerade innehav.

Vid första 1→0-avhoppet i produktionssignalen jämförs fortsatt innehav med
den högst rankade köpbara ersättaren samma vecka. Reglerna är fasta:

* trend: kurs över SMA20 och 26v relativ avkastning mot universum > 0
* fundamental förbättring: minst två jämförbara rapportmått och positiv
  medianförändring (omsättning, EBIT, EPS och operativt kassaflöde)
* kombination: trend samt ingen negativ fundamental förbättring

Alla rapporter måste vara publicerade senast beslutsdagen. Resultat före 2024
är utvecklingsperiod; 2024+ är orörd kontrollperiod.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
import numpy as np
import pandas as pd

import config
from data.data_loader import (
    fetch_weekly_data, filter_active_universe, filter_liquid_universe,
    load_sweden_universe,
)

HORIZONS = (13, 26, 52)
QUARANTINES = (4, 8, 13)
METRICS = ("revenue", "ebit", "eps", "operating_cash_flow")
FUND_MAX_AGE_DAYS = 400
ROUND_TRIP_COST = 2 * (
    float(getattr(config, "COMMISSION", .0015))
    + float(getattr(config, "SLIPPAGE", .001))
    + float(getattr(config, "SPREAD_MIN", 0.0))
)


def load_reports(results_dir: Path) -> pd.DataFrame:
    frames = []
    for name in ("fundamentals_from_mfn.csv", "fundamentals_from_pdf.csv",
                 "fundamentals_from_avanza.csv"):
        path = results_dir / name
        if path.exists():
            frames.append(pd.read_csv(path))
    if not frames:
        return pd.DataFrame()
    raw = pd.concat(frames, ignore_index=True, sort=False)
    raw["published"] = pd.to_datetime(
        raw["published"], errors="coerce", utc=True).dt.tz_localize(None)
    raw = raw.dropna(subset=["ticker", "published"])
    for col in METRICS:
        raw[col] = pd.to_numeric(
            raw[col], errors="coerce") if col in raw else np.nan
        prior = f"{col}_prior"
        raw[prior] = pd.to_numeric(
            raw[prior], errors="coerce") if prior in raw else np.nan

    # En händelse kan finnas i både MFN/PDF. Behåll den mest kompletta raden.
    raw["_coverage"] = raw[list(METRICS) + [f"{m}_prior" for m in METRICS]].notna().sum(axis=1)
    raw = raw.sort_values(["ticker", "published", "_coverage"])
    return raw.drop_duplicates(["ticker", "published"], keep="last")


def fundamental_change(reports: pd.DataFrame, ticker: str, asof: pd.Timestamp):
    g = reports[(reports["ticker"] == ticker) & (reports["published"] <= asof)]
    if g.empty:
        return np.nan
    row = g.iloc[-1]
    if asof - row["published"] > pd.Timedelta(days=FUND_MAX_AGE_DAYS):
        return np.nan
    changes = []
    for metric in METRICS:
        now, prior = row[metric], row[f"{metric}_prior"]
        if pd.notna(now) and pd.notna(prior) and abs(prior) > 1e-9:
            changes.append((now - prior) / abs(prior))
    return float(np.median(changes)) if len(changes) >= 2 else np.nan


def stats(df: pd.DataFrame, mask: pd.Series, horizon: int):
    x = df.loc[mask & df[f"delta_{horizon}"].notna(), f"delta_{horizon}"]
    if x.empty:
        return None
    return len(x), float(x.mean()), float(x.median()), float((x > 0).mean())


def main():
    seg = config.SEGMENTS["large"]
    results_dir = Path(config.anchor(seg["results_dir"]))
    sig = pd.read_csv(results_dir / "signals.csv", parse_dates=["Date"])
    sig = sig.sort_values(["ticker", "Date"])
    sig["prev_signal"] = sig.groupby("ticker")["pred_signal"].shift(1)
    exits = sig[(sig["prev_signal"] == 1) & (sig["pred_signal"] == 0)].copy()

    tickers, _, _, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(
        data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)
    px = pd.DataFrame(
        {t: d["Close"] for t, d in data.items() if "Close" in d}).sort_index()
    idx = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    reports = load_reports(results_dir)

    by_date = {d: g for d, g in sig.groupby("Date")}
    rows = []
    for r in exits.itertuples(index=False):
        pos = px.index.searchsorted(r.Date, side="left")
        if pos >= len(px) or r.ticker not in px or pos < 26:
            continue
        candidates = by_date.get(r.Date)
        if candidates is None:
            continue
        candidates = candidates[
            (candidates["pred_signal"] == 1) & (candidates["ticker"] != r.ticker)]
        candidates = candidates[candidates["ticker"].isin(px.columns)]
        if candidates.empty:
            continue
        rank_col = "prob_rank" if "prob_rank" in candidates else "prob_up"
        replacement = candidates.sort_values(rank_col, ascending=False).iloc[0]["ticker"]
        old0, new0 = px[r.ticker].iloc[pos], px[replacement].iloc[pos]
        if pd.isna(old0) or pd.isna(new0) or old0 == 0 or new0 == 0:
            continue
        own26 = old0 / px[r.ticker].iloc[pos - 26] - 1
        idx26 = idx.iloc[pos] / idx.iloc[pos - 26] - 1
        trend = bool(
            old0 > px[r.ticker].iloc[max(0, pos - 19):pos + 1].mean()
            and own26 > idx26)
        fchange = fundamental_change(reports, r.ticker, r.Date)
        out = {"Date": r.Date, "ticker": r.ticker, "replacement": replacement,
               "trend": trend, "fund_change": fchange,
               "exit_rank": getattr(r, "prob_rank", np.nan)}
        for h in HORIZONS:
            if pos + h >= len(px):
                out[f"delta_{h}"] = np.nan
                continue
            old1, new1 = px[r.ticker].iloc[pos + h], px[replacement].iloc[pos + h]
            out[f"delta_{h}"] = (
                old1 / old0 - new1 / new0) if pd.notna(old1) and pd.notna(new1) else np.nan

        # Kausal karantän: äg gamla bolaget i k veckor. På beslutet vecka k
        # behålls det om det åter kvalificerat sig, annars köps dåtidens
        # högst rankade signal. Baslinjen köper ersättaren direkt vid vecka 0.
        for k in QUARANTINES:
            delay_pos = pos + k
            if delay_pos >= len(px):
                continue
            delay_date = px.index[delay_pos]
            delayed_signals = by_date.get(delay_date)
            if delayed_signals is None:
                continue
            old_row = delayed_signals[delayed_signals["ticker"] == r.ticker]
            requalified = (
                not old_row.empty and int(old_row.iloc[-1]["pred_signal"]) == 1)
            delayed_ticker = r.ticker
            delayed_trade = False
            if not requalified:
                dc = delayed_signals[
                    (delayed_signals["pred_signal"] == 1)
                    & delayed_signals["ticker"].isin(px.columns)]
                if dc.empty:
                    continue
                delayed_ticker = dc.sort_values(
                    rank_col, ascending=False).iloc[0]["ticker"]
                delayed_trade = delayed_ticker != r.ticker
            oldk = px[r.ticker].iloc[delay_pos]
            delayed0 = px[delayed_ticker].iloc[delay_pos]
            if pd.isna(oldk) or pd.isna(delayed0) or delayed0 == 0:
                continue
            for h in HORIZONS:
                if h < k or pos + h >= len(px):
                    continue
                base_h = px[replacement].iloc[pos + h]
                delayed_h = px[delayed_ticker].iloc[pos + h]
                if pd.isna(base_h) or pd.isna(delayed_h):
                    continue
                baseline_wealth = (base_h / new0) * (1 - ROUND_TRIP_COST)
                delayed_wealth = (oldk / old0) * (delayed_h / delayed0)
                if delayed_trade:
                    delayed_wealth *= (1 - ROUND_TRIP_COST)
                out[f"q{k}_{h}"] = delayed_wealth - baseline_wealth
            out[f"q{k}_requalified"] = requalified
        rows.append(out)
    audit = pd.DataFrame(rows)
    audit["fund_up"] = audit["fund_change"] > 0
    audit["combined"] = audit["trend"] & (
        audit["fund_change"].isna() | audit["fund_up"])
    # Hysteres: inträdesgränsen är topp-10, men ett befintligt trendintakt
    # innehav får ligga kvar så länge det ännu är i översta 20/30 procent.
    audit["rank80"] = audit["trend"] & (audit["exit_rank"] >= .80)
    audit["rank70"] = audit["trend"] & (audit["exit_rank"] >= .70)
    audit["all_exits"] = True

    print(f"{len(audit)} signalavhopp med köpbar ersättare; "
          f"{audit['fund_change'].notna().sum()} har jämförbar point-in-time-fundamenta.")
    for period, pmask in (
        ("UTVECKLING <2024", audit["Date"] < "2024-01-01"),
        ("KONTROLL 2024+", audit["Date"] >= "2024-01-01"),
    ):
        print(f"\n{period}")
        print("regel                 h      n   medelΔ  medianΔ    vinst")
        for label in ("all_exits", "trend", "rank80", "rank70",
                      "fund_up", "combined"):
            for h in HORIZONS:
                s = stats(audit, pmask & audit[label], h)
                if s:
                    n, mean, median, win = s
                    print(f"{label:<21}{h:>3} {n:>6} {mean:>+8.2%} "
                          f"{median:>+8.2%} {win:>8.1%}")

    modern = audit["Date"] >= "2024-01-01"
    # Kandidat väljs enbart på utvecklingsperioden: högst genomsnittlig
    # median-delta över horisonterna, därefter låses den inför kontrollen.
    candidates = ("trend", "rank80", "rank70", "fund_up", "combined")
    def dev_score(label):
        vals = [stats(audit, (audit["Date"] < "2024-01-01") & audit[label], h)
                for h in HORIZONS]
        return np.mean([s[2] for s in vals if s is not None])
    selected = max(candidates, key=dev_score)
    checks = [stats(audit, modern & audit[selected], h) for h in HORIZONS]
    approved = all(
        s is not None and s[0] >= 30 and s[1] > 0 and s[2] > 0 and s[3] >= .55
        for s in checks)
    print(f"\nFörhandsvald regel från utvecklingsperioden: {selected}")
    print("BESLUT:", "GODKÄND FÖR SHADOW" if approved else "FÖRKASTAD / MER DATA KRÄVS")
    print("Krav per horisont i 2024+: n≥30, medelΔ>0, medianΔ>0, vinstfrekvens≥55%.")

    print(f"\nEXIT-KARANTÄN (endast trendintakta avhopp, kostnad {ROUND_TRIP_COST:.2%})")
    print("period              k/h      n   medelΔ  medianΔ    vinst återkval")
    period_masks = {
        "UTVECKLING <2024": audit["Date"] < "2024-01-01",
        "KONTROLL 2024+": audit["Date"] >= "2024-01-01",
    }
    for period, pmask in period_masks.items():
        for k in QUARANTINES:
            req = audit.loc[pmask & audit["trend"], f"q{k}_requalified"].mean()
            for h in HORIZONS:
                col = f"q{k}_{h}"
                if col not in audit:
                    continue
                x = audit.loc[pmask & audit["trend"], col].dropna()
                if not x.empty:
                    print(f"{period:<19}{k:>2}/{h:<3} {len(x):>6} "
                          f"{x.mean():>+8.2%} {x.median():>+8.2%} "
                          f"{(x > 0).mean():>8.1%} {req:>8.1%}")

    # Välj k endast på utvecklingsperiodens median över alla tre horisonter.
    dev = period_masks["UTVECKLING <2024"] & audit["trend"]
    def qscore(k):
        vals = []
        for h in HORIZONS:
            col = f"q{k}_{h}"
            if col in audit:
                vals.append(audit.loc[dev, col].median())
        return np.nanmean(vals)
    selected_k = max(QUARANTINES, key=qscore)
    control = period_masks["KONTROLL 2024+"] & audit["trend"]
    qchecks = []
    for h in HORIZONS:
        x = audit.loc[control, f"q{selected_k}_{h}"].dropna()
        qchecks.append(
            len(x) >= 30 and x.mean() > 0 and x.median() > 0
            and (x > 0).mean() >= .55)
    print(f"\nFörhandsvald karantän: {selected_k} veckor")
    print("KARANTÄNBESLUT:",
          "GODKÄND FÖR SHADOW" if all(qchecks) else "FÖRKASTAD")


if __name__ == "__main__":
    main()
