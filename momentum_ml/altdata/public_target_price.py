"""
altdata/public_target_price.py – "OFFENTLIG RIKTKURS": samlar in externa
analytikers riktkurser (Yahoo Finances aggregerade targetMeanPrice/High/Low,
som i sin tur samlar Redeye/Carnegie/Pareto/SEB m.fl.) - se konversationen
2026-07-23, verifierat mot Otto-diagrammens externa riktkurser (Physitrack
20,08 = Redeye 20 kr exakt, Smart Eye 120/108 = Redeye/Carnegie exakt,
Sedana 18,0 = Pareto exakt).

Detta är den ENA av två riktkursspår (se konversationen): "offentlig
riktkurs" (marknadens/analytikernas syn, DEN HÄR modulen) vs "modellens
riktkurs" (Otto-metodens egna-historiska-multipelband, se
model_target_price.py) - två oberoende estimat, avsiktligt separata så de
kan jämföras.

Skiljer sig från portfolio.py::_research_note() (MFN-pressmeddelande-
regex, bara BETALD uppdragsanalys, ingen historik sparas, bara narrativ)
genom att (1) fånga OBEROENDE täckning också (Carnegie/SEB syns aldrig i
_research_note), (2) spara en RIKTIG tidsserie (en rad per körning, inte
bara senaste), (3) vara en tydlig, fristående datakälla - inte bara text
i en kommentar.

BEGRÄNSNING: småbolag har ofta 0-1 analytiker (se ENVAR.ST: ingen
täckning alls) - `n_analysts` följer med i varje rad så konsumenter kan
vikta/filtrera bort tunt underlag.

    python -m altdata.public_target_price fetch [large|small|all]
    python -m altdata.public_target_price show <ticker>
"""
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config  # noqa: E402

COLS = ["date", "ticker", "name", "price_now", "target_mean", "target_high",
        "target_low", "n_analysts", "recommendation"]


def _out_path(segment: str) -> Path:
    seg_cfg = config.SEGMENTS.get(segment, {})
    results_dir = Path(config.anchor(seg_cfg.get("results_dir", config.RESULTS_DIR)))
    return results_dir / "public_target_price.csv"


def fetch_one(ticker: str) -> dict:
    import yfinance as yf
    try:
        info = yf.Ticker(ticker).get_info()
    except Exception as e:  # noqa: BLE001
        print(f"  [WARN] {ticker}: {e}")
        return None
    tgt = info.get("targetMeanPrice")
    if tgt is None:
        return None
    return {
        "date": datetime.now(timezone.utc).date().isoformat(),
        "ticker": ticker,
        "name": info.get("longName") or info.get("shortName") or ticker,
        "price_now": info.get("currentPrice") or info.get("regularMarketPrice"),
        "target_mean": tgt,
        "target_high": info.get("targetHighPrice"),
        "target_low": info.get("targetLowPrice"),
        "n_analysts": info.get("numberOfAnalystOpinions"),
        "recommendation": info.get("recommendationKey"),
    }


def fetch(segment: str = "all") -> None:
    from data.data_loader import load_sweden_universe
    segments = ["large", "small"] if segment == "all" else [segment]
    for seg in segments:
        seg_cfg = config.SEGMENTS.get(seg)
        if seg_cfg is None:
            print(f"[public_target_price] okänt segment '{seg}'.")
            continue
        tickers, *_ = load_sweden_universe(min_market_cap=seg_cfg["market_cap"])
        out_path = _out_path(seg)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_header = not out_path.exists()
        n_found, n_total = 0, 0
        with open(out_path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLS)
            if write_header:
                w.writeheader()
            for i, t in enumerate(tickers, 1):
                row = fetch_one(t)
                n_total += 1
                if row:
                    w.writerow(row)
                    n_found += 1
                if i % 50 == 0:
                    print(f"  ... {i}/{len(tickers)} ({seg})")
        print(f"[public_target_price] {seg}: {n_found}/{n_total} bolag hade en riktkurs, "
              f"skrivet till {out_path}")


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
        print("Användning: python -m altdata.public_target_price fetch [large|small|all]")
        print("            python -m altdata.public_target_price show <ticker>")
