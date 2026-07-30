"""
altdata/fundamentals.py – Fundamenta-features ur BörsAPI + Börsdata Pro+.

Bygger per bolag/år ur årsrapporterna (RR/BR/KA):
  · Piotroski F-score (0–1, normaliserad över TILLGÄNGLIGA signaler)
  · Fundamental momentum: omsättningstillväxt + ACCELERATION, marginaltrend,
    vinsttillväxt, FCF-marginal, ROA

DATAKÄLLOR (sammanslagna – BörsAPI vinner där båda har data):
  · BörsAPI  (cache/borsapi/)  – huvudlista, verifierade fält, begränsad kvot
  · Börsdata (cache/borsdata/) – Pro+, 20 år historik, täcker First North/
    Spotlight/micro cap som BörsAPI saknar. Fältnamn mappas via
    BORSDATA_FIELD_MAP.

Detta är den första edge-axeln som INTE är prismomentum. Ordningen är som
alltid: bygg → IC-validera mot framåtavkastning (tune_fundamentals.py) →
först därefter får den påverka köp (via kvant-screenern/sammanvägningen).

    python -m altdata.fundamentals build   # → results/fundamentals.csv (alla bolag/år)
    python -m altdata.fundamentals show    # topplista senaste året
"""
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config


def _num(v):
    try:
        f = float(v)
        return f
    except (TypeError, ValueError):
        return None


def _borsapi_cache_dir() -> Path:
    return Path(config.anchor(getattr(config, "BORSAPI_CACHE_DIR", "cache/borsapi")))


def _borsdata_cache_dir() -> Path:
    return Path(config.anchor(getattr(config, "BORSDATA_CACHE_DIR", "cache/borsdata")))


# ── Börsdata → kanoniskt fältnamn ────────────────────────────────────────────
# Verifierade mot skarpa cachade svar (cache/borsdata/reports_*_max20.json).
# Börsdata använder mixed camelCase (revenues, operating_Income, ...); vi
# normaliserar till det snake_case-schema resten av systemet förväntar sig.
BORSDATA_FIELD_MAP = {
    # Resultaträkning
    "revenues":                              "revenue",
    "net_Sales":                             "revenue",       # alias, samma belopp
    "gross_Income":                          "gross_profit",
    "operating_Income":                      "operating_income",
    "profit_Before_Tax":                     "pre_tax_income",
    "profit_To_Equity_Holders":              "net_income",
    "earnings_Per_Share":                    "eps",
    "number_Of_Shares":                      "shares_outstanding",
    "dividend":                              "dividend",
    # Balansräkning
    "intangible_Assets":                     "intangible_assets",
    "tangible_Assets":                       "tangible_assets",
    "financial_Assets":                      "financial_assets",
    "non_Current_Assets":                    "non_current_assets",
    "cash_And_Equivalents":                  "cash_and_equivalents",
    "current_Assets":                        "current_assets",
    "total_Assets":                          "total_assets",
    "total_Equity":                          "total_equity",
    "non_Current_Liabilities":               "long_term_debt",
    "current_Liabilities":                   "current_liabilities",
    "total_Liabilities_And_Equity":          "total_liabilities_and_equity",
    "net_Debt":                              "net_debt",
    # Kassaflöde
    "cash_Flow_From_Operating_Activities":   "operating_cash_flow",
    "cash_Flow_From_Investing_Activities":   "investing_cash_flow",
    "cash_Flow_From_Financing_Activities":   "financing_cash_flow",
    "cash_Flow_For_The_Year":                "net_cash_flow",
    "free_Cash_Flow":                        "free_cash_flow",
    # Metadata
    "report_Date":                           "report_date",
    "report_Start_Date":                     "report_start_date",
    "report_End_Date":                       "report_end_date",
}


def _id_to_ticker_borsapi() -> dict:
    """company_id → vår ticker (BörsAPI:s 'INVE-A' → 'INVE-A.ST') ur bolagslist-cachen."""
    out = {}
    for f in _borsapi_cache_dir().glob("companies_all_*.json"):
        try:
            for c in json.loads(f.read_text(encoding="utf-8")).get("data", []):
                tk = (c.get("ticker") or "").strip().upper()
                if c.get("id") and tk:
                    out[c["id"]] = f"{tk}.ST"
        except Exception:  # noqa: BLE001
            pass
    return out


def _insid_to_ticker_borsdata() -> dict:
    """insId → vår ticker ur Börsdatas instruments_all.json.
    Börsdatas 'yahoo'-fält är redan 'AAK.ST', 'INVE-A.ST' etc."""
    out = {}
    fp = _borsdata_cache_dir() / "instruments_all.json"
    if not fp.exists():
        return out
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        items = data.get("instruments") or data.get("data") or []
        for it in items:
            ins_id = it.get("insId")
            # yahoo-fältet har '.ST'-suffix; annars bygg det från ticker
            yahoo = (it.get("yahoo") or "").strip()
            ticker = (it.get("ticker") or "").strip().upper()
            tk = yahoo.upper() if yahoo else (f"{ticker}.ST" if ticker else "")
            if ins_id and tk:
                out[ins_id] = tk
    except Exception:  # noqa: BLE001
        pass
    return out


def _load_borsapi_reports() -> dict:
    """
    {ticker: {år: {fält: värde}}} ur BörsAPI-cachen (cache/borsapi/).
    Raderna kommer som en per rapporttyp (RR/BR/KA) och period – vi slår ihop
    till ett fältset per bolagsår (icke-null vinner).
    """
    id2tk = _id_to_ticker_borsapi()
    out: dict = {}
    for f in _borsapi_cache_dir().glob("reports_*.json"):
        try:
            rows = json.loads(f.read_text(encoding="utf-8")).get("data", [])
        except Exception:  # noqa: BLE001
            continue
        for r in rows:
            tk = id2tk.get(r.get("company_id"))
            m = re.match(r"^(20\d\d)", str(r.get("period") or ""))
            if not tk or not m:
                continue
            year = int(m.group(1))
            slot = out.setdefault(tk, {}).setdefault(year, {})
            for k, v in r.items():
                nv = _num(v)
                if nv is not None and slot.get(k) is None:
                    slot[k] = nv
    return out


def _load_borsdata_reports() -> dict:
    """
    {ticker: {år: {fält: värde}}} ur Börsdata Pro+-cachen (cache/borsdata/).

    Cachade filer har formatet:
        {"instrument": N, "reportsYear": [...], "reportsQuarter": [...], "reportsR12": [...]}
    Vi läser bara reportsYear och mappar fältnamn via BORSDATA_FIELD_MAP till
    det kanoniska schemat (revenue, net_income, total_assets, ...).
    """
    insid2tk = _insid_to_ticker_borsdata()
    bd_cache = _borsdata_cache_dir()
    if not bd_cache.exists():
        return {}

    out: dict = {}
    for fp in bd_cache.glob("reports_*_max20.json"):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue

        # Hitta insId → ticker
        ins_id = data.get("instrument")
        tk = insid2tk.get(ins_id) if ins_id else None
        if not tk:
            # Försök extrahera insId ur filnamn: reports_{insId}_max20.json
            m = re.search(r"reports_(\d+)_max20", fp.name)
            if m:
                tk = insid2tk.get(int(m.group(1)))
        if not tk:
            continue

        # Extrahera årsrapporter
        year_rows = data.get("reportsYear") or data.get("reports") or []
        for row in year_rows:
            year = row.get("year")
            if not year or year < 2000:
                continue
            slot = out.setdefault(tk, {}).setdefault(year, {})
            for bd_key, canon_key in BORSDATA_FIELD_MAP.items():
                val = _num(row.get(bd_key))
                if val is not None and slot.get(canon_key) is None:
                    slot[canon_key] = val
    return out


def load_reports() -> dict:
    """
    {ticker: {år: {fält: värde}}} – SAMMANSLAGET från BörsAPI + Börsdata Pro+.

    BörsAPI-data vinner där båda har samma fält (redan manuellt verifierat).
    Börsdata fyller luckorna – framför allt First North/Spotlight/micro cap
    som BörsAPI inte täcker.
    """
    # Börsdata först (bredd), BörsAPI ovanpå (precision)
    merged = _load_borsdata_reports()
    borsapi = _load_borsapi_reports()

    for tk, years in borsapi.items():
        for yr, fields in years.items():
            slot = merged.setdefault(tk, {}).setdefault(yr, {})
            for k, v in fields.items():
                # BörsAPI vinner – skriver över Börsdata-värdet
                slot[k] = v

    return merged


def _ratio(a, b):
    return a / b if a is not None and b not in (None, 0) else None


def fscore(cur: dict, prev: dict) -> tuple:
    """
    Piotroski-signaler på tillgängliga fält. Returnerar (score01, n_signaler, detalj).
    Signaler (1/0), utelämnas när data saknas:
      lönsamhet: ROA>0 · CFO>0 · ΔROA>0 · CFO>vinst (accruals)
      soliditet: Δ(långfristig skuld/tillgångar)<0
      effektivitet: Δbruttomarginal>0 · Δkapitalomsättning>0
    """
    sig = {}
    roa_c = _ratio(cur.get("net_income"), cur.get("total_assets"))
    roa_p = _ratio(prev.get("net_income"), prev.get("total_assets"))
    if roa_c is not None:
        sig["roa_pos"] = int(roa_c > 0)
    if cur.get("operating_cash_flow") is not None:
        sig["cfo_pos"] = int(cur["operating_cash_flow"] > 0)
    if roa_c is not None and roa_p is not None:
        sig["roa_up"] = int(roa_c > roa_p)
    if cur.get("operating_cash_flow") is not None and cur.get("net_income") is not None:
        sig["accruals"] = int(cur["operating_cash_flow"] > cur["net_income"])
    lev_c = _ratio(cur.get("long_term_debt"), cur.get("total_assets"))
    lev_p = _ratio(prev.get("long_term_debt"), prev.get("total_assets"))
    if lev_c is not None and lev_p is not None:
        sig["lev_down"] = int(lev_c <= lev_p)
    gm_c = _ratio(cur.get("gross_profit"), cur.get("revenue"))
    gm_p = _ratio(prev.get("gross_profit"), prev.get("revenue"))
    if gm_c is not None and gm_p is not None:
        sig["gm_up"] = int(gm_c > gm_p)
    at_c = _ratio(cur.get("revenue"), cur.get("total_assets"))
    at_p = _ratio(prev.get("revenue"), prev.get("total_assets"))
    if at_c is not None and at_p is not None:
        sig["at_up"] = int(at_c > at_p)
    n = len(sig)
    return (sum(sig.values()) / n if n else None), n, sig


def _growth(cur, prev):
    if cur is None or prev is None or prev == 0:
        return None
    return cur / abs(prev) - 1


def metric_rows(reports: dict = None) -> list:
    """En rad per bolag/år (kräver föregående år): F-score + momentum-mått."""
    reports = reports if reports is not None else load_reports()
    rows = []
    for tk, years in reports.items():
        ys = sorted(years)
        for i, y in enumerate(ys):
            if i == 0:
                continue
            cur, prev = years[y], years[ys[i - 1]]
            if ys[i - 1] != y - 1:
                continue                      # kräver konsekutiva år
            score, n, _sig = fscore(cur, prev)
            rev_g = _growth(cur.get("revenue"), prev.get("revenue"))
            # acceleration kräver även året före föregående
            rev_g_prev = None
            if i >= 2 and ys[i - 2] == y - 2:
                rev_g_prev = _growth(prev.get("revenue"), years[ys[i - 2]].get("revenue"))
            om_c = _ratio(cur.get("operating_income"), cur.get("revenue"))
            om_p = _ratio(prev.get("operating_income"), prev.get("revenue"))
            rows.append({
                "ticker": tk, "year": y,
                "f_score": round(score, 3) if score is not None else None,
                "f_n": n,
                "rev_growth": round(rev_g, 4) if rev_g is not None else None,
                "rev_accel": (round(rev_g - rev_g_prev, 4)
                              if rev_g is not None and rev_g_prev is not None else None),
                "margin_delta": (round(om_c - om_p, 4)
                                 if om_c is not None and om_p is not None else None),
                "ni_growth": round(_growth(cur.get("net_income"), prev.get("net_income")), 4)
                             if _growth(cur.get("net_income"), prev.get("net_income")) is not None else None,
                "fcf_margin": round(_ratio(cur.get("free_cash_flow"), cur.get("revenue")), 4)
                              if _ratio(cur.get("free_cash_flow"), cur.get("revenue")) is not None else None,
                "roa": round(_ratio(cur.get("net_income"), cur.get("total_assets")), 4)
                       if _ratio(cur.get("net_income"), cur.get("total_assets")) is not None else None,
            })
    return rows


def build():
    rows = metric_rows()
    if not rows:
        print("Inga rapporter i cachen än – kör backfill först.")
        return
    out = Path(config.anchor(config.RESULTS_DIR)) / "fundamentals.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    n_tk = len({r["ticker"] for r in rows})
    print(f"fundamentals.csv: {len(rows)} bolagsår · {n_tk} bolag → {out}")


def show():
    rows = metric_rows()
    latest = {}
    for r in rows:
        if r["ticker"] not in latest or r["year"] > latest[r["ticker"]]["year"]:
            latest[r["ticker"]] = r
    top = sorted(latest.values(), key=lambda r: (r["f_score"] or 0), reverse=True)[:20]
    print(f"{'ticker':<14}{'år':>5}{'F':>6}{'n':>3}{'omsättn.tillv':>14}{'accel':>8}{'Δmarginal':>10}")
    for r in top:
        print(f"{r['ticker']:<14}{r['year']:>5}"
              f"{(f'{r0:.2f}' if (r0 := r['f_score']) is not None else '–'):>6}{r['f_n']:>3}"
              f"{(f'{v:+.0%}' if (v := r['rev_growth']) is not None else '–'):>14}"
              f"{(f'{v:+.0%}' if (v := r['rev_accel']) is not None else '–'):>8}"
              f"{(f'{v:+.1%}' if (v := r['margin_delta']) is not None else '–'):>10}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "build":
        build()
    elif cmd == "show":
        show()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
