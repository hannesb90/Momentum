"""
altdata/fundamentals.py – Fundamenta-features ur BörsAPI-cachen.

Bygger per bolag/år ur årsrapporterna (RR/BR/KA):
  · Piotroski F-score (0–1, normaliserad över TILLGÄNGLIGA signaler – BörsAPI
    saknar t.ex. current assets/aktieantal, så vi poängsätter det som finns
    och rapporterar antalet signaler i stället för att gissa)
  · Fundamental momentum: omsättningstillväxt + ACCELERATION, marginaltrend,
    vinsttillväxt, FCF-marginal, ROA

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


def _cache_dir() -> Path:
    return Path(config.anchor(getattr(config, "BORSAPI_CACHE_DIR", "cache/borsapi")))


def _id_to_ticker() -> dict:
    """company_id → vår ticker (BörsAPI:s 'INVE-A' → 'INVE-A.ST') ur bolagslist-cachen."""
    out = {}
    for f in _cache_dir().glob("companies_all_*.json"):
        try:
            for c in json.loads(f.read_text(encoding="utf-8")).get("data", []):
                tk = (c.get("ticker") or "").strip().upper()
                if c.get("id") and tk:
                    out[c["id"]] = f"{tk}.ST"
        except Exception:  # noqa: BLE001
            pass
    return out


def load_reports() -> dict:
    """
    {ticker: {år: {fält: värde}}} ur alla cachade rapportsvar. Raderna kommer som
    en per rapporttyp (RR/BR/KA) och period – vi slår ihop till ett fältset per
    bolagsår (icke-null vinner; RR/BR/KA överlappar inte i fältnamn).
    """
    id2tk = _id_to_ticker()
    out: dict = {}
    for f in _cache_dir().glob("reports_*.json"):
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
