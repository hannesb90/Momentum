"""
tune_global_relative_value.py – systematiskt svep på frågan som Sivers-
exemplet (manuellt, n=1) väckte: kan man hitta svenska mikrobolag som ser
BILLIGA ut jämfört med sin GLOBALA jämförelsegrupp (inte bara svensk
sektor-median), och predicerar det framåtavkastning - särskilt när
sektorn/temat är "hett" (globala korgens egen värdering är historiskt hög)?

Metod (årliga ögonblicksbilder, inte veckovis - se begränsningar nedan):
  1. Två globala jämförelsekorgar (handplockade small-cap-bolag i samma
     tema, INTE en generell bransch-multipel):
       · halvledare/foton/RF: AKTS, POET, AAOI, CEVA, SITM, MTSI, AEHR, PXLW
       · medtech/diagnostik:  IRTC, TMDX, ATEC, CDXS, PGEN, NVCR, ICUI, NARI
  2. Svenskt universum: Information Technology + Health Care,
     Small/Micro/Nano Cap (samma två sektorer som korgarna matchar mot).
  3. För varje bolag/år: P/S = (årsslut-kurs x DAGENS aktieantal) / årets
     rapporterade omsättning. Samma "dagens aktieantal på historiskt pris"-
     approximation som redan flaggats som en svaghet i konversationen
     (utspädning över tid gör äldre år mindre tillförlitliga) - ÄRLIGT
     KVAR HÄR, inte dolt.
  4. "Billig-händelse" = bolagets P/S ligger i UNDRE TERCILEN av dess
     matchade globala korgs P/S-fördelning SAMMA ÅR (kräver >= 4 korg-
     bolag med giltig data det året för en meningsfull tercil).
  5. Sektor-"hetta" vid händelsen: korgens EGEN median-P/S det året,
     percentilrankad mot korgens EGEN 2010-idag-historik (fetch_weekly_data
     + samma årliga P/S-metod) - "het" = översta tercilen av korgens EGEN
     historiska värderingsnivå, "sval" = undre tercilen.
  6. Framåtavkastning (13v/26v/52v/104v) från årsslutet, mot likaviktat
     svenskt index - samma metodik som #19/tidigare svep denna session.

BEGRÄNSNINGAR (ärliga, innan resultatet läses):
  · n är litet per cell när det delas på tercil x hett/svalt/normalt -
    detta är en FÖRSTA fingervisning, inte ett statistiskt bevis.
  · Peer-korgarna är handplockade (samma osäkerhet som diskuterades för
    Sivers - "rätt" jämförelsebolag är en bedömningsfråga).
  · Årliga (inte veckovisa) ögonblicksbilder - missar intra-års-rörelser.
  · Aktieantal = dagens, applicerat på historiska kurser (utspädnings-
    snedvridning för äldre år, se konversationen).

Kör (nät krävs, kan ta 20-40 min för ~300 tickers):
    /opt/momentum/venv/bin/python tune_global_relative_value.py
"""
import sys
import pickle
import time
from pathlib import Path

sys.path.insert(0, '.')
import numpy as np
import pandas as pd

import config
from data.data_loader import fetch_weekly_data, filter_active_universe, filter_liquid_universe, load_sweden_universe

PEER_BASKETS = {
    "Information Technology": ["AKTS", "POET", "AAOI", "CEVA", "SITM", "MTSI", "AEHR", "PXLW"],
    "Health Care": ["IRTC", "TMDX", "ATEC", "CDXS", "PGEN", "NVCR", "ICUI", "NARI"],
}
HORIZONS_WEEKS = [13, 26, 52, 104]
CACHE_DIR = Path(__file__).parent / "cache" / "global_relval"


def _cache(key: str):
    p = CACHE_DIR / f"{key.replace('.', '_').replace('^', '')}.pkl"
    return p


def annual_ps_snapshots(ticker: str, shares_now: float = None) -> pd.DataFrame:
    """{year: {price, revenue, ps, shares}} - årsslut-kurs (dagens aktier)
    / årsrapporterad omsättning. None-fält vid saknad data."""
    cp = _cache(f"ps_{ticker}")
    if cp.exists():
        return pickle.loads(cp.read_bytes())
    import yfinance as yf
    out = {}
    try:
        tk = yf.Ticker(ticker)
        info = tk.get_info()
        shares = shares_now or info.get("sharesOutstanding")
        fin = tk.financials
        rev_by_year = {}
        if fin is not None and "Total Revenue" in fin.index:
            for c, v in fin.loc["Total Revenue"].items():
                if pd.notna(v):
                    rev_by_year[c.year] = float(v)
        d = yf.download(ticker, start="2010-01-01", interval="3mo", auto_adjust=True, progress=False)
        if isinstance(d.columns, pd.MultiIndex):
            close = d["Close"][ticker].dropna()
        else:
            close = d["Close"].dropna()
        close.index = pd.DatetimeIndex(close.index).tz_localize(None)
        yearly_px = close.resample("YE").last().dropna()
        for dt, px in yearly_px.items():
            yr = dt.year
            rev = rev_by_year.get(yr)
            if rev is None or rev <= 0 or shares is None:
                continue
            mcap = float(px) * shares
            out[yr] = {"price": float(px), "revenue": rev, "shares": shares, "ps": mcap / rev,
                       "date": dt.normalize()}
    except Exception as e:  # noqa: BLE001
        print(f"  [WARN] {ticker}: {e}")
    df = pd.DataFrame.from_dict(out, orient="index")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cp.write_bytes(pickle.dumps(df))
    return df


def main():
    print("[tune_global_relative_value] bygger P/S-historik för globala jämförelsekorgar...")
    peer_ps: dict = {}
    for sector, tickers in PEER_BASKETS.items():
        for t in tickers:
            df = annual_ps_snapshots(t)
            if not df.empty:
                peer_ps[t] = df
            time.sleep(0.3)
    print(f"  {len(peer_ps)} korg-bolag med giltig P/S-historik.")

    # Korgens EGEN "hetta" per sektor/år: median-P/S bland korg-bolag med
    # data det året, percentilrankad mot korgens EGEN historik (alla år).
    heat_by_sector: dict = {}
    for sector, tickers in PEER_BASKETS.items():
        rows = []
        for t in tickers:
            df = peer_ps.get(t)
            if df is None or df.empty:
                continue
            for yr, row in df.iterrows():
                rows.append({"year": yr, "ticker": t, "ps": row["ps"]})
        if not rows:
            continue
        panel = pd.DataFrame(rows)
        yearly_median = panel.groupby("year")["ps"].median()
        heat_rank = yearly_median.rank(pct=True)
        heat_by_sector[sector] = {"yearly_median": yearly_median, "heat_rank": heat_rank}
        print(f"  {sector}: korg-median P/S per år: "
              f"{ {int(y): round(v, 1) for y, v in yearly_median.items()} }")

    print("\n[tune_global_relative_value] hämtar svenskt IT+Health Care small/micro/nano-universum...")
    tickers, sector_map, cap_map, name_map = load_sweden_universe(
        min_market_cap=["Small Cap", "Micro Cap", "Nano Cap"])
    se_universe = [t for t in tickers if sector_map.get(t) in PEER_BASKETS]
    print(f"  {len(se_universe)} svenska bolag (IT: "
          f"{sum(1 for t in se_universe if sector_map.get(t)=='Information Technology')}, "
          f"HC: {sum(1 for t in se_universe if sector_map.get(t)=='Health Care')})")

    print("[tune_global_relative_value] bygger P/S-historik för svenska bolag (kan ta lång tid)...")
    se_ps: dict = {}
    for i, t in enumerate(se_universe, 1):
        df = annual_ps_snapshots(t)
        if not df.empty:
            se_ps[t] = df
        if i % 40 == 0:
            print(f"  ... {i}/{len(se_universe)} bolag klara")
        time.sleep(0.2)
    print(f"  {len(se_ps)} svenska bolag med giltig P/S-historik.")

    # ── Bygg händelselista: bolag/år där P/S i undre tercilen av matchad korg ──
    events = []
    for t in se_ps:
        sector = sector_map.get(t)
        basket = PEER_BASKETS.get(sector, [])
        for yr, row in se_ps[t].iterrows():
            peer_vals = [peer_ps[p].loc[yr, "ps"] for p in basket
                         if p in peer_ps and yr in peer_ps[p].index]
            if len(peer_vals) < 4:
                continue
            p33 = np.quantile(peer_vals, 1 / 3)
            is_cheap = row["ps"] <= p33
            heat = heat_by_sector.get(sector, {}).get("heat_rank", pd.Series(dtype=float)).get(yr)
            events.append({"ticker": t, "sector": sector, "year": yr, "date": row["date"],
                           "ps": row["ps"], "peer_median": float(np.median(peer_vals)),
                           "is_cheap": is_cheap, "n_peers": len(peer_vals), "heat_rank": heat})

    ev_df = pd.DataFrame(events)
    cheap = ev_df[ev_df["is_cheap"]].copy()
    print(f"\n[tune_global_relative_value] {len(ev_df)} bolag/år-observationer totalt, "
          f"{len(cheap)} 'billig vs global korg'-händelser.")
    if cheap.empty:
        print("Inga händelser - avbryter.")
        return

    cheap["heat_bucket"] = pd.cut(cheap["heat_rank"], [0, 1 / 3, 2 / 3, 1.0],
                                   labels=["sval sektor", "normal sektor", "het sektor"], include_lowest=True)

    print("\n  Billig-händelser per sektor-hetta:")
    print(cheap["heat_bucket"].value_counts())

    # ── Framåtavkastning ──
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)
    px = pd.DataFrame({t: d["Close"] for t, d in data.items() if "Close" in d}).sort_index()
    idx_level = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    weeks = px.index

    def _fwd_excess(ticker, date, h):
        pos = weeks.searchsorted(date, side="left")
        p1i = pos + h
        if ticker not in px.columns or pos >= len(weeks) or p1i >= len(weeks):
            return None
        p0, p1 = px[ticker].iloc[pos], px[ticker].iloc[p1i]
        if pd.isna(p0) or pd.isna(p1) or p0 == 0:
            return None
        r = p1 / p0 - 1
        b = idx_level.iloc[p1i] / idx_level.iloc[pos] - 1
        return r - b

    header = (f"  {'grupp':<16}{'n':>6}"
              + "".join(f"{f'{h}v exc':>10}{f'{h}v win%':>9}{f'{h}v n':>7}" for h in HORIZONS_WEEKS))
    print("\n" + "=" * len(header))
    print("  'Billig vs global jämförelsekorg' - framåtavkastning, uppdelat på sektor-hetta")
    print("=" * len(header))
    print(header)
    print("-" * len(header))
    for bucket in ["sval sektor", "normal sektor", "het sektor"]:
        sub = cheap[cheap["heat_bucket"] == bucket]
        cells = f"  {bucket:<16}{len(sub):>6}"
        for h in HORIZONS_WEEKS:
            excs = [_fwd_excess(r["ticker"], r["date"], h) for _, r in sub.iterrows()]
            excs = [e for e in excs if e is not None]
            if not excs:
                cells += f"{'–':>10}{'–':>9}{'–':>7}"
            else:
                cells += f"{np.median(excs):>+10.1%}{np.mean([e>0 for e in excs]):>8.0%} {len(excs):>7}"
        print(cells)
    # Alla billig-händelser oavsett hetta, som baslinje
    cells = f"  {'ALLA billiga':<16}{len(cheap):>6}"
    for h in HORIZONS_WEEKS:
        excs = [_fwd_excess(r["ticker"], r["date"], h) for _, r in cheap.iterrows()]
        excs = [e for e in excs if e is not None]
        if excs:
            cells += f"{np.median(excs):>+10.1%}{np.mean([e>0 for e in excs]):>8.0%} {len(excs):>7}"
        else:
            cells += f"{'–':>10}{'–':>9}{'–':>7}"
    print(cells)
    print("-" * len(header))

    print("\n  Enskilda 'het sektor'-händelser (mest relevanta för Sivers-tesen):")
    hot = cheap[cheap["heat_bucket"] == "het sektor"].sort_values("date")
    for _, r in hot.iterrows():
        e52 = _fwd_excess(r["ticker"], r["date"], 52)
        e52s = f"{e52:+.1%}" if e52 is not None else "n/a"
        print(f"    {r['ticker']:<12} {r['year']}  P/S {r['ps']:.1f} (korgmedian {r['peer_median']:.1f})  52v excess: {e52s}")

    print("\n  Läsning: håller Sivers-tesen ska 'het sektor'-raden ha klart bättre excess/win% än")
    print("  'sval sektor' och 'normal sektor' - annars är billig-vs-global-korg en generell signal")
    print("  (eller ingen alls), inte specifikt kopplad till överhettade sektorer.")


if __name__ == "__main__":
    main()
