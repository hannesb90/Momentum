"""
altdata/mfn_events.py – TOKEN-FRI händelse-skanning av MFN-cachen:
INSYNSHANDEL (PDMR-transaktioner) + SENASTE RAPPORTDATUM per bolag.

Två av de mest robust dokumenterade signalerna som INTE kräver någon ny
datakälla – allt ligger redan i cache/mfn/{ticker}.json:

  · INSYNSKÖP: kluster av köp från personer i ledande ställning är en av de
    starkast belagda positiva signalerna i litteraturen (insiders säljer av
    många skäl, men köper bara av ett). Vi räknar köp-/sälj-PM per bolag de
    senaste 90 dagarna. MAR kräver att bolag publicerar PDMR-transaktioner
    som PM → de finns i MFN-flödet.
  · RAPPORTDATUM (för PEAD-disciplin): senaste rapport-PM:ets datum. Nedströms
    använder köp-vakten det för (a) "rapport väntas snart (~kvartalsrytm) –
    köp inte ryktet" och (b) "färsk rapport + bekräftad drift = PEAD-läge".

Körs NATTLIGT (eller manuellt) på Pi:n – ALDRIG i API-vägen (genomläsningen
av hela MFN-cachen är dyr, samma läxa som _research_note-hängningen):

    python -m altdata.mfn_events scan large
    python -m altdata.mfn_events scan small

Skriver <segmentets results_dir>/mfn_events.csv som portfolio._load_scores
plockar upp (mtime-invaliderad, som övriga score-filer).

MEDVETNA avgränsningar:
  · "Återköp av egna aktier" (bolagets buyback) räknas INTE som insynsköp –
    annat fenomen, egen signal, utanför scope.
  · PM där riktningen inte kan avgöras (både köp- och säljord, eller inget)
    ignoreras hellre än gissas.
  · Incitamentsprogram/optionsinlösen går inte att skilja från äkta köp ur
    titeln ensam – en känd brusnivå (klustertröskeln ≥ 2 nedströms dämpar).
"""
import sys
import csv
import json
import datetime as dt
import re
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from altdata.mfn_fundamentals import is_report_pm

# PDMR-/insyns-PM identifieras på TITELN (gate), riktningen ur titel+ingress.
_INSIDER_TITLE_RE = re.compile(
    r"insynshandel|insynsperson|insynsanmälan"
    r"|ledande befattningshavares?\s+transaktion|person(?:er)?\s+i\s+ledande\s+ställning"
    r"|managers'?\s+transactions?|pdmr",
    re.I)
# Bolagets egna återköp är INTE insynshandel – exkludera innan riktning avgörs.
_BUYBACK_RE = re.compile(r"återköp\s+av\s+egna\s+aktier|share\s+buy-?back", re.I)
_BUY_RE = re.compile(r"förvärv|köp\w*|teckna\w*|öka\w*\s+sitt\s+innehav|purchase|acquisition\s+of\s+shares", re.I)
# sål[dt]\w* täcker sålt/sålde/sålda; försälj\w* täcker försäljning/försäljningar.
_SELL_RE = re.compile(r"avyttr\w*|försälj\w*|sål[dt]\w*|säljer|minska\w*\s+sitt\s+innehav|\bsale\b|\bsold\b|disposal", re.I)


def _parse_date(s) -> Optional[dt.date]:
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        return None


def classify_insider(item: dict) -> Optional[str]:
    """'buy'/'sell' för ett PDMR-PM, None om inte insyns-PM eller oklar riktning.
    Riktningen avgörs på titel + PM-ingressens första ~800 tecken; PM med BÅDE
    köp- och säljord (blandade transaktioner) ignoreras hellre än gissas."""
    title = str(item.get("title") or "")
    if not _INSIDER_TITLE_RE.search(title) or _BUYBACK_RE.search(title):
        return None
    blob = title + " " + str(item.get("text") or "")[:800]
    has_buy, has_sell = bool(_BUY_RE.search(blob)), bool(_SELL_RE.search(blob))
    if has_buy and not has_sell:
        return "buy"
    if has_sell and not has_buy:
        return "sell"
    return None


def load_insider_events(cache_dir) -> "list[dict]":
    """cache/mfn/<ticker>.json → [{ticker, published, side}] för ALLA PDMR-
    transaktioner i hela cachen (inte bara scan()s rullande 90-dagarsfönster
    från idag - det här ger fulla historiken, en rad per köp/sälj-PM, som
    behövs för att backtesta signalen över tid).

    Strömmande (en fil i taget, kastar den råa MFN-posten direkt efter
    klassificering) av samma skäl som altdata/pead.load_report_dates: att
    hålla alla ~1 GB rå JSON i minnet samtidigt är vad som fällde
    momentum-Pi:n 2026-07-19."""
    cache_dir = Path(cache_dir)
    rows = []
    if not cache_dir.exists():
        return rows
    for f in cache_dir.glob("*.json"):
        if f.name.startswith("_"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        items = data.get("items") if isinstance(data, dict) else data
        if not isinstance(items, list):
            continue
        for it in items:
            side = classify_insider(it)
            if side is None:
                continue
            d = _parse_date(it.get("published"))
            if d is None:
                continue
            rows.append({"ticker": f.stem, "published": d, "side": side})
    return rows


def scan(segment: Optional[str] = None, window_days: int = 90) -> None:
    from data.data_loader import load_sweden_universe

    seg_name = segment or config.DEFAULT_SEGMENT
    seg_cfg = config.SEGMENTS.get(seg_name, config.SEGMENTS[config.DEFAULT_SEGMENT])
    tickers, _, _, _ = load_sweden_universe(min_market_cap=seg_cfg["market_cap"])
    cache_dir = Path(config.MFN_CACHE_DIR)
    today = dt.date.today()
    cutoff = today - dt.timedelta(days=window_days)

    rows = []
    n_ins = 0
    for t in tickers:
        p = cache_dir / f"{t}.json"
        if not p.exists():
            continue
        try:
            items = json.loads(p.read_text(encoding="utf-8")).get("items", [])
        except Exception:  # noqa: BLE001
            continue
        buys = sells = 0
        last_buy = last_sell = last_report = None
        for it in items:
            d = _parse_date(it.get("published"))
            if d is None:
                continue
            if is_report_pm(it):
                if last_report is None or d > last_report:
                    last_report = d
                continue
            side = classify_insider(it)
            if side == "buy":
                if last_buy is None or d > last_buy:
                    last_buy = d
                if d >= cutoff:
                    buys += 1
            elif side == "sell":
                if last_sell is None or d > last_sell:
                    last_sell = d
                if d >= cutoff:
                    sells += 1
        if buys or sells or last_report:
            n_ins += (buys + sells)
            rows.append({
                "ticker": t,
                "insider_buys_90d": buys, "insider_sells_90d": sells,
                "last_insider_buy": last_buy.isoformat() if last_buy else "",
                "last_insider_sell": last_sell.isoformat() if last_sell else "",
                "last_report_date": last_report.isoformat() if last_report else "",
            })

    out = Path(config.anchor(seg_cfg["results_dir"])) / "mfn_events.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ticker", "insider_buys_90d", "insider_sells_90d",
                                          "last_insider_buy", "last_insider_sell",
                                          "last_report_date"])
        w.writeheader()
        w.writerows(rows)
    kluster = [r for r in rows if r["insider_buys_90d"] - r["insider_sells_90d"] >= 2]
    print(f"[mfn_events] {len(rows)} bolag med händelser ({n_ins} insyns-PM inom {window_days}d) → {out}")
    if kluster:
        print(f"  KLUSTER AV INSYNSKÖP (netto ≥ 2 på {window_days}d) – starkaste signalen:")
        for r in sorted(kluster, key=lambda r: -(r["insider_buys_90d"] - r["insider_sells_90d"]))[:15]:
            print(f"    {r['ticker']:<14} +{r['insider_buys_90d']} köp / -{r['insider_sells_90d']} sälj"
                  f"  (senaste köp {r['last_insider_buy']})")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "scan"
    seg = sys.argv[2] if len(sys.argv) > 2 else None
    if cmd == "scan":
        scan(seg)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
