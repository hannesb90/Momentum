"""
portfolio.py – Portfölj-medveten analys + nytt-kapital-plan.

Läser dina innehav (cache/portfolio_holdings.csv – GITIGNORERAD, personlig data),
klassar per hink (broad/sweden/theme/leverage), jämför mot en diversifierad
mål-fördelning (config.PORTFOLIO_TARGET) och riktar NYTT kapital mot det du är
underviktad i. Fyll-mot-mål via inflöden – ingen försäljning, ingen skatt, ingen
timing. Innehav läggs in manuellt (CLI eller i appen, som skriver samma fil).

    python portfolio.py analyze
    python portfolio.py newcapital 10000
    python portfolio.py backtest 5000 36    # "nästa köp" mot index: 5000 kr/mån, 36 mån
"""
import sys
import csv
import json
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config

BUCKETS = ("broad", "sweden", "theme", "leverage")
BUCKET_LABEL = {"broad": "Bred kärna (World/US/EM)", "sweden": "Sverige",
                "theme": "Tematiskt", "leverage": "Hävstång"}


def holdings_path() -> Path:
    return Path(config.PORTFOLIO_HOLDINGS_FILE)


def load_holdings() -> list:
    p = holdings_path()
    if not p.exists():
        return []
    rows = []
    with open(p, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                rows.append({"name": r["name"].strip(), "value": float(r["value_sek"]),
                             "bucket": (r.get("bucket") or "theme").strip()})
            except (ValueError, KeyError):
                continue
    return rows


def save_holdings(rows) -> None:
    p = holdings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["name", "value_sek", "bucket"])
        w.writeheader()
        for r in rows:
            b = r.get("bucket", "theme")
            w.writerow({"name": r.get("name", ""),
                        "value_sek": float(r.get("value", r.get("value_sek", 0)) or 0),
                        "bucket": b if b in BUCKETS else "theme"})


def _kinds():
    out = {}
    uf = Path(getattr(config, "ETF_ROT_UNIVERSE_FILE", ""))
    if uf and uf.exists():
        with open(uf, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                out[r["ticker"]] = r.get("kind", "")
    return out


_RESEARCH_FIRMS = ("analyst group", "redeye", "emergers", "carlsquare", "erik penser",
                   "penser", "mangold", "kalqyl", "analysguiden", "nordic issuing")
_RIKTKURS = re.compile(r"riktkurs\D{0,25}(\d[\d\s.,]*)\s*(kr|sek)", re.I)


def _research_note(ticker):
    """Token-fri skanning av MFN-cachen: senaste uppdragsanalys-PM + ev. riktkurs.
    OBS: uppdragsanalys är BETALD av bolaget → positivt biased. Visas som narrativ,
    inte signal."""
    p = Path(config.MFN_CACHE_DIR) / f"{ticker}.json"
    if not p.exists():
        return None
    try:
        items = json.loads(p.read_text(encoding="utf-8")).get("items", [])
    except Exception:  # noqa: BLE001
        return None
    for it in sorted(items, key=lambda x: x.get("published", ""), reverse=True)[:40]:
        blob = (str(it.get("title", "")) + " " + str(it.get("text", "")))
        low = blob.lower()
        if any(f in low for f in _RESEARCH_FIRMS) or "uppdragsanalys" in low:
            m = _RIKTKURS.search(blob)
            return {"date": str(it.get("published", ""))[:10],
                    "riktkurs": (m.group(1).strip() if m else None),
                    "title": str(it.get("title", ""))[:70]}
    return None


def _momentum_picks():
    """Momentum-köpsignaler för svenska småbolag (Signaler-vyn). Loser mot index –
    idéer, inte edge."""
    seg = config.SEGMENTS.get("small", {})
    sp = Path(seg.get("results_dir", "")) / "signals.csv"
    if not sp.exists():
        return []
    last = {}
    try:
        for r in csv.DictReader(open(sp, encoding="utf-8")):
            if r.get("ticker"):
                last[r["ticker"]] = r         # sista raden per ticker = senaste vecka
    except Exception:  # noqa: BLE001
        return []
    def pu(r):
        try:
            return float(r.get("prob_up") or 0)
        except ValueError:
            return 0.0
    buys = [r for r in last.values() if str(r.get("pred_signal")) in ("1", "1.0")]
    buys.sort(key=pu, reverse=True)
    return [{"name": r.get("name") or r.get("ticker"), "ticker": r.get("ticker"),
             "note": f"momentum P(upp) {pu(r):.0%}", "source": "momentum"} for r in buys[:5]]


def _candidates() -> dict:
    """Konkreta idéer från övriga vyer, per hink – bolag/teman, inte bara breda ETF:er.
    sweden = kvalitets-screenern + momentum-signaler (+ uppdragsanalys om funnen);
    theme = rotationens starkaste teman."""
    out = {"sweden": [], "theme": []}
    seen = set()

    def add_sweden(name, ticker, note, source):
        if not ticker or ticker in seen:
            return
        seen.add(ticker)
        c = {"name": name, "ticker": ticker, "note": note, "source": source}
        r = _research_note(ticker)
        if r:
            c["analys"] = r
        out["sweden"].append(c)

    # Kvalitets-screenern → svenska kvalitetsbolag (hög composite + billig/rimlig).
    qp = Path("results/quality_shortlist.csv")
    if qp.exists():
        try:
            rows = list(csv.DictReader(open(qp, encoding="utf-8")))
            def comp(r):
                try:
                    return float(r.get("composite") or 0)
                except ValueError:
                    return 0.0
            picks = sorted([r for r in rows if comp(r) >= 4.0 and r.get("zone") in ("billig", "rimlig")],
                           key=comp, reverse=True)
            for r in picks[:5]:
                add_sweden(r.get("name") or r.get("ticker"), r.get("ticker"),
                           f"kvalitet {r.get('composite')} · {r.get('zone')}", "kvalitet")
        except Exception:  # noqa: BLE001
            pass
    # Momentum-signaler → svenska småbolag.
    for m in _momentum_picks():
        add_sweden(m["name"], m["ticker"], m["note"], "momentum")

    # Rotationen → starkaste tema-ETF:erna (för temadelen).
    rp = Path("results/etf_rotation.csv")
    if rp.exists():
        try:
            kinds = _kinds()
            rows = list(csv.DictReader(open(rp, encoding="utf-8")))
            themes = [r for r in rows if kinds.get(r.get("etf")) == "theme"]
            def mom(r):
                try:
                    return float(r.get("rel_mom") or 0)
                except ValueError:
                    return 0.0
            for r in sorted(themes, key=mom, reverse=True)[:5]:
                out["theme"].append({"name": r.get("sector"), "ticker": r.get("etf"),
                                     "note": f"rel.mom {mom(r):+.0%}", "source": "rotation"})
        except Exception:  # noqa: BLE001
            pass
    return out


def compute(rows, amount=None) -> dict:
    total = sum(r["value"] for r in rows) or 0.0
    buckets = {b: 0.0 for b in BUCKETS}
    for r in rows:
        buckets[r["bucket"] if r["bucket"] in buckets else "theme"] += r["value"]
    warnings = []
    if total > 0:
        if buckets["broad"] / total < 0.10:
            warnings.append("Ingen bred diversifierad kärna – allt är riktade vad.")
        if buckets["leverage"] > 0:
            warnings.append(f"Hävstång i portföljen ({buckets['leverage']/total:.0%}) – decay/ruinrisk på sikt.")
        if buckets["theme"] / total > 0.30:
            warnings.append(f"Hög tema-koncentration ({buckets['theme']/total:.0%}) – rör sig ofta ihop.")
        big = max(rows, key=lambda r: r["value"], default=None)
        if big and big["value"] / total > 0.12:
            warnings.append(f"Störst enskilt innehav: {big['name']} ({big['value']/total:.0%}).")

    out = {"total": round(total, 0),
           "buckets": {b: (round(buckets[b] / total, 4) if total else 0.0) for b in BUCKETS},
           "buckets_sek": {b: round(buckets[b], 0) for b in BUCKETS},
           "target": config.PORTFOLIO_TARGET,
           "warnings": warnings,
           "candidates": _candidates(),
           "holdings": [{"name": r["name"], "value": round(r["value"], 0), "bucket": r["bucket"]} for r in rows]}

    if amount:
        after = total + amount
        gaps = {b: max(0.0, config.PORTFOLIO_TARGET.get(b, 0.0) * after - buckets[b]) for b in BUCKETS}
        gsum = sum(gaps.values()) or 1.0
        plan = {b: round(amount * g / gsum) for b, g in gaps.items() if g > 0}
        broad_etfs = {}
        if plan.get("broad", 0) > 0:
            n = len(config.PORTFOLIO_BROAD_ETFS) or 1
            broad_etfs = {lbl: {"ticker": tk, "kr": round(plan["broad"] / n)}
                          for lbl, tk in config.PORTFOLIO_BROAD_ETFS.items()}
        out["newcapital"] = {"amount": amount, "plan": plan, "broad_etfs": broad_etfs}
    return out


# ── Backtest: "nästa köp" (fyll-mot-mål) mot index ────────────────────────────
# Ärlig fråga: "nästa köp" styr BARA vart nytt kapital går (säljer aldrig). Rätt
# jämförelse är därför SAMMA gamla bok, men varje ny krona i index istället. Vi visar
# också "allt om till index nu" som aggressiv referens (säljer allt → index idag).
# Buckets proxas av ETF:er: broad = korg av PORTFOLIO_BROAD_ETFS, sweden = småbolags-
# index, theme = likaviktad korg av tema-ETF:erna, index = ETF_ROT_BENCHMARK (ACWI).
# Hävstångs-sleeven proxas av broad-korgen; den får ändå aldrig nytt kapital (mål 0)
# och är identisk i båda strategierna → påverkar inte A-vs-index-domen.

def _fill_split(bucket_vals, amount, targets) -> dict:
    """Fördela `amount` mot målvikterna: allt till de underviktade hinkarna (gap),
    proportionellt. Om alla ligger på/över mål → fördela efter målvikt."""
    after = sum(bucket_vals.values()) + amount
    gaps = {b: max(0.0, targets.get(b, 0.0) * after - bucket_vals.get(b, 0.0)) for b in bucket_vals}
    gsum = sum(gaps.values())
    if gsum <= 0:
        tsum = sum(targets.get(b, 0.0) for b in bucket_vals) or 1.0
        return {b: amount * targets.get(b, 0.0) / tsum for b in bucket_vals}
    return {b: amount * g / gsum for b, g in gaps.items()}


def _irr_monthly(cfs):
    """Månads-IRR via bisektion (cfs = kassaflöden per månad, sista inkl. slutvärde)."""
    def npv(r):
        return sum(c / (1 + r) ** k for k, c in enumerate(cfs))
    lo, hi = -0.9, 1.0
    if npv(lo) * npv(hi) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def _proxy_prices(months=None):
    """Prispanel (vecka × proxy) för hinkarna + index. Nät → körs på Pi:n."""
    import pandas as pd
    from data.data_loader import fetch_weekly_data
    broad = list(config.PORTFOLIO_BROAD_ETFS.values())
    theme = [t for t, k in _kinds().items() if k == "theme"]
    sweden = [config.SEGMENTS.get("small", {}).get("index_ticker", "XACT-SMABOLAG.ST")]
    index = [config.ETF_ROT_BENCHMARK]
    allt = sorted(set(broad + theme + sweden + index))
    data = fetch_weekly_data(allt, use_cache=True)
    close = {t: d["Close"] for t, d in data.items()
             if d is not None and not d["Close"].dropna().empty}
    px = pd.DataFrame(close).sort_index().ffill(limit=1)
    px.index = pd.to_datetime(px.index)

    def basket(tickers):
        cols = [t for t in tickers if t in px.columns]
        if not cols:
            return None
        sub = px[cols]
        norm = sub / sub.apply(lambda c: c[c.first_valid_index()] if c.first_valid_index() is not None else float("nan"))
        return norm.mean(axis=1)

    proxies = {"broad": basket(broad), "sweden": basket(sweden),
               "theme": basket(theme), "index": basket(index)}
    proxies["leverage"] = proxies["broad"]
    out = pd.DataFrame({k: v for k, v in proxies.items() if v is not None}).dropna()
    if months:
        out = out[out.index >= out.index[-1] - pd.DateOffset(months=months)]
    return out


def _dca_backtest(px, targets, start_book, monthly):
    """Simulerar månatliga insättningar på en prispanel. Returnerar värde-serier +
    sammanfattning för tre strategier med IDENTISK startbok (utom 'allt-in-index')."""
    idx = list(px.index)
    p0 = px.iloc[0]
    cols = [b for b in BUCKETS if b in px.columns]
    uA = {b: (start_book.get(b, 0.0) / p0[b] if p0.get(b, 0) else 0.0) for b in cols}
    uB_legacy = dict(uA)                      # index-för-nytt: samma gamla bok
    uB_index = 0.0
    V0 = float(sum(start_book.values()))
    uC_index = V0 / p0["index"] if p0.get("index", 0) else 0.0   # allt om till index nu
    valsA, valsB, valsC, contrib_months = [], [], [], 0
    prev_m = None
    for ts in idx:
        p = px.loc[ts]
        if prev_m is not None and (ts.year, ts.month) != prev_m:
            c = monthly
            contrib_months += 1
            split = _fill_split({b: uA[b] * p[b] for b in cols}, c, targets)
            for b, amt in split.items():
                if p.get(b, 0):
                    uA[b] += amt / p[b]
            if p.get("index", 0):
                uB_index += c / p["index"]
                uC_index += c / p["index"]
        prev_m = (ts.year, ts.month)
        valsA.append(sum(uA[b] * p[b] for b in cols))
        valsB.append(sum(uB_legacy[b] * p[b] for b in cols) + uB_index * p.get("index", 0))
        valsC.append(uC_index * p.get("index", 0))
    invested = V0 + monthly * contrib_months
    cfs = [-V0] + [-monthly] * contrib_months
    def summarize(vals):
        import pandas as pd
        s = pd.Series(vals, index=idx)
        final = float(s.iloc[-1])
        cf = list(cfs); cf[-1] = cf[-1] + final
        r = _irr_monthly(cf)
        maxdd = float((s / s.cummax() - 1).min())
        return {"final": final, "invested": invested,
                "irr_year": ((1 + r) ** 12 - 1) if r is not None else None,
                "maxdd": maxdd, "series": s}
    return {"A": summarize(valsA), "B": summarize(valsB), "C": summarize(valsC),
            "months": contrib_months, "years": len(idx) / 52.0}


def backtest(monthly=5000, months=None):
    rows = load_holdings()
    start_book = {b: 0.0 for b in BUCKETS}
    for r in rows:
        start_book[r["bucket"] if r["bucket"] in start_book else "theme"] += r["value"]
    V0 = sum(start_book.values())
    try:
        px = _proxy_prices(months=months)
    except Exception as e:  # noqa: BLE001
        print(f"[backtest] kunde inte bygga prispanel: {e}\n  (kör på Pi:n – molnet saknar nät)")
        return
    if px.empty or "index" not in px.columns or len(px) < 30:
        print("[backtest] för lite prisdata för proxyserierna – cachea ETF:erna först.")
        return
    res = _dca_backtest(px, config.PORTFOLIO_TARGET, start_book, monthly)
    a, b, c = res["A"], res["B"], res["C"]
    print(f"\n  \"NÄSTA KÖP\" (fyll-mot-mål) MOT INDEX")
    print(f"  Startbok {V0:,.0f} kr · {monthly:,.0f} kr/mån · {res['months']} insättningar "
          f"· {res['years']:.1f} år".replace(",", " "))
    print(f"  Totalt insatt: {a['invested']:,.0f} kr\n".replace(",", " "))
    def line(name, s):
        irr = f"{s['irr_year']:+.1%}" if s["irr_year"] is not None else "  n/a"
        print(f"   {name:<34}slutvärde {s['final']:>10,.0f} kr   IRR/år {irr:>7}   maxDD {s['maxdd']:>6.1%}"
              .replace(",", " "))
    line("A) Nästa köp → fyll mot mål", a)
    line("B) Nästa köp → allt i index", b)
    line("C) Sälj allt → index idag", c)
    print()
    da = a["final"] - b["final"]
    print(f"  A − B (allokeringens effekt på NYTT kapital): {da:>+10,.0f} kr "
          f"({da / b['final']:+.1%})".replace(",", " "))
    print("  A vs B isolerar det enda 'nästa köp' styr: vart nya pengar går (ingen försäljning).")
    print("  C är referens om du säljer om HELA boken till index idag (skatt/spread ej medräknat).")
    if da < 0:
        print("  → Att styra nytt kapital mot mål-mixen SLÅR INTE ren index-insättning här.")
    else:
        print("  → Fyll-mot-mål gav ett litet övertag mot ren index-insättning i perioden.")
    _write_json({"backtest": {k: {kk: vv for kk, vv in res[k].items() if kk != "series"}
                              for k in ("A", "B", "C")},
                 "monthly": monthly, "months": res["months"], "years": res["years"]})


def _write_json(data):
    out = Path("results/portfolio_analysis.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False))


def analyze():
    rows = load_holdings()
    if not rows:
        print("[portfolio] inga innehav – lägg in i appen eller cache/portfolio_holdings.csv")
        return
    d = compute(rows)
    print(f"\n  PORTFÖLJ – {d['total']:,.0f} kr, {len(rows)} innehav\n".replace(",", " "))
    print(f"  {'Hink':<26}{'nu':>8}{'mål':>8}{'diff':>8}")
    for b in BUCKETS:
        cur, tgt = d["buckets"][b], d["target"].get(b, 0.0)
        print(f"  {BUCKET_LABEL[b]:<26}{cur:>7.0%}{tgt:>8.0%}{cur - tgt:>+8.0%}")
    print("\n  Varningar:")
    for w in d["warnings"]:
        print(f"   ⚠ {w}")
    _write_json(d)


def newcapital(amount):
    rows = load_holdings()
    if not rows:
        print("[portfolio] inga innehav – lägg in dem först.")
        return
    d = compute(rows, amount=amount)
    print(f"\n  NYTT KAPITAL: {amount:,.0f} kr → fyll mot målet (ingen försäljning)\n".replace(",", " "))
    for b, kr in sorted(d["newcapital"]["plan"].items(), key=lambda x: -x[1]):
        print(f"   {BUCKET_LABEL[b]:<26}{kr:>10,.0f} kr   ({kr/amount:.0%})".replace(",", " "))
    for lbl, e in d["newcapital"]["broad_etfs"].items():
        print(f"     {lbl:<20}{e['ticker']:<10}{e['kr']:>9,.0f} kr".replace(",", " "))
    _write_json(d)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "analyze"
    if cmd == "analyze":
        analyze()
    elif cmd == "newcapital":
        newcapital(float(sys.argv[2]) if len(sys.argv) > 2 else 10000)
    elif cmd == "backtest":
        monthly = float(sys.argv[2]) if len(sys.argv) > 2 else 5000
        months = int(sys.argv[3]) if len(sys.argv) > 3 else None
        backtest(monthly, months)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
