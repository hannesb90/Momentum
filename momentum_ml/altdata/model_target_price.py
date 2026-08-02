"""
altdata/model_target_price.py – "MODELLENS RIKTKURS": Otto-metodens
(OT Analytics, otanalytics.se) princip formaliserad som en systematisk,
sparad beräkning - ett bolags EGEN historiska Börsvärde/EBIT(DA)-multipel
(lägsta↔högsta percentil av dess egen historik) applicerad på DAGENS
rullande 12-månaders-resultat.

Det ANDRA av två riktkursspår (se altdata/public_target_price.py för det
första, "offentlig riktkurs" - externa analytikers estimat). Två
oberoende beräkningar, avsiktligt separata så de kan jämföras.

VALIDERAT (tune_otto_valuation_band.py, #25 i docs/UTVECKLINGSLOGG.md):
  · SÄLJ-sidan håller: framåtavkastning EFTER att ett bolag nått sin egen
    historiskt HÖGSTA multipel vänder tydligt negativ (26v -3,8%, 52v
    -25,0%) - "modellens riktkurs" (byggd på HÖG-percentilen) är alltså en
    rimlig grund för en TA-HEM-VINSTEN-varning.
  · KÖP-sidan håller INTE: att ett bolag handlas till sin egen historiskt
    LÄGSTA multipel är i den här mikrobolagspopulationen snarare en
    varningssignal än ett köpläge (13v -5,7%, 26v -10,5%). "modellens
    golv" beräknas ändå och sparas (transparens, framtida omprövning) men
    ska INTE tolkas som ett köpsignal-tröskel i sin nuvarande form.

BEGRÄNSNING (samma som forskningsskriptet): Ottos EGEN metod använder
FRAMÅTBLICKANDE guidade/estimerade EBIT(DA)-nivåer (bolagets finansiella
mål eller hans egna prognoser) - ingen sådan källa finns systematiskt för
hela microcap-universumet, så den här modulen använder i stället DAGENS
rullande 12-månaders-resultat. En BESLÄKTAD, enklare regel, inte exakt
Ottos framåtblickande metod.

    python -m altdata.model_target_price fetch [large|small|all]
    python -m altdata.model_target_price show <ticker>
"""
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config  # noqa: E402

MIN_PROFITABLE_YEARS = 3
LOW_PCT, HIGH_PCT = 0.10, 0.90
COLS = ["date", "ticker", "name", "price_now", "metric", "n_years",
        "ttm_value", "own_low_mult", "own_high_mult",
        "model_floor", "model_target", "warn_sell"]


def _out_path(segment: str) -> Path:
    seg_cfg = config.SEGMENTS.get(segment, {})
    results_dir = Path(config.anchor(seg_cfg.get("results_dir", config.RESULTS_DIR)))
    return results_dir / "model_target_price.csv"


def compute_one(ticker: str) -> dict:
    """Bygger bolagets EGNA historiska multipelband (>= MIN_PROFITABLE_YEARS
    lönsamma år krävs, annars för tunt) och applicerar det på TTM-resultatet.
    Föredrar EBIT om den har nog lönsamma år, annars EBITDA (fler bolag har
    positiv EBITDA än EBIT - samma fallback-logik som quant_screener.py)."""
    import yfinance as yf
    import pandas as pd
    try:
        tk = yf.Ticker(ticker)
        info = tk.get_info()
        shares = info.get("sharesOutstanding")
        price_now = info.get("currentPrice") or info.get("regularMarketPrice")
        if shares is None or price_now is None:
            return None
        fin = tk.financials
        q = tk.quarterly_financials
        if fin is None or q is None:
            return None
    except Exception as e:  # noqa: BLE001
        print(f"  [WARN] {ticker}: {e}")
        return None

    for metric in ("EBIT", "EBITDA"):
        if metric not in fin.index or metric not in q.index:
            continue
        annual = {c.year: float(v) for c, v in fin.loc[metric].items() if pd.notna(v)}
        annual_px = {}
        try:
            d = yf.download(ticker, start="2010-01-01", interval="3mo",
                             auto_adjust=True, progress=False)
            close = (d["Close"][ticker] if isinstance(d.columns, pd.MultiIndex) else d["Close"]).dropna()
            close.index = pd.DatetimeIndex(close.index).tz_localize(None)
            for dt, px in close.resample("YE").last().dropna().items():
                annual_px[dt.year] = float(px)
        except Exception:  # noqa: BLE001
            pass
        mults = []
        for yr, val in annual.items():
            px = annual_px.get(yr)
            if val > 0 and px is not None:
                mults.append((float(px) * shares) / val)
        if len(mults) < MIN_PROFITABLE_YEARS:
            continue

        mults_s = pd.Series(mults)
        low_mult, high_mult = mults_s.quantile(LOW_PCT), mults_s.quantile(HIGH_PCT)

        ttm = sum(float(v) for v in q.loc[metric].iloc[:4] if pd.notna(v))
        if ttm <= 0:
            return {"ticker": ticker, "name": info.get("longName") or ticker,
                    "price_now": price_now, "metric": metric, "n_years": len(mults),
                    "ttm_value": ttm, "own_low_mult": float(low_mult), "own_high_mult": float(high_mult),
                    "model_floor": None, "model_target": None, "warn_sell": False}

        model_floor = (ttm * low_mult) / shares
        model_target = (ttm * high_mult) / shares
        warn_sell = price_now >= model_target
        return {"ticker": ticker, "name": info.get("longName") or ticker,
                "price_now": price_now, "metric": metric, "n_years": len(mults),
                "ttm_value": round(ttm, 1), "own_low_mult": round(float(low_mult), 1),
                "own_high_mult": round(float(high_mult), 1),
                "model_floor": round(model_floor, 2), "model_target": round(model_target, 2),
                "warn_sell": warn_sell}
    return None


def fetch(segment: str = "all") -> None:
    from data.data_loader import load_sweden_universe
    segments = ["large", "small"] if segment == "all" else [segment]
    for seg in segments:
        seg_cfg = config.SEGMENTS.get(seg)
        if seg_cfg is None:
            print(f"[model_target_price] okänt segment '{seg}'.")
            continue
        tickers, *_ = load_sweden_universe(min_market_cap=seg_cfg["market_cap"])
        out_path = _out_path(seg)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_header = not out_path.exists()
        n_found, n_warn = 0, 0
        today = datetime.now(timezone.utc).date().isoformat()
        with open(out_path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLS)
            if write_header:
                w.writeheader()
            for i, t in enumerate(tickers, 1):
                row = compute_one(t)
                if row and row.get("model_target") is not None:
                    row["date"] = today
                    w.writerow(row)
                    n_found += 1
                    if row["warn_sell"]:
                        n_warn += 1
                if i % 50 == 0:
                    print(f"  ... {i}/{len(tickers)} ({seg})")
        print(f"[model_target_price] {seg}: {n_found} bolag fick modellens riktkurs beräknad "
              f"({n_warn} redan över riktkurs - ta-hem-vinsten-varning), skrivet till {out_path}")


def show(ticker: str) -> None:
    for seg in config.SEGMENTS:
        p = _out_path(seg)
        if not p.exists():
            continue
        with open(p, encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if r["ticker"] == ticker]
        for r in rows:
            print(r)


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "fetch":
        fetch(args[1] if len(args) > 1 else "all")
    elif args and args[0] == "show" and len(args) > 1:
        show(args[1])
    else:
        print("Användning: python -m altdata.model_target_price fetch [large|small|all]")
        print("            python -m altdata.model_target_price show <ticker>")
