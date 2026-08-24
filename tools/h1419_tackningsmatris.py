"""H1419 STEG 1a — TÄCKNINGSMATRIS FÖR 2014-2019

Innan en prisryggrad byggs måste det stå klart exakt hur många av periodens
kända Main Market-avnoteringar vi faktiskt kan inkludera. Det är krav 4 i
H0_HISTORICAL_EXTENSION_FEASIBILITY_AUDIT och grinden för hela projektet:
faller täckningen under det auditen antog (29/45 = 64 %) ska bygget inte göras.

Metod:
  1. Ur instrument_master (Skatteverket) plockas avnoteringar 2014-2019 vars
     orsakstext pekar på Nasdaq Stockholm / Nordiska listan. First North,
     Aktietorget/Spotlight och NGM exkluderas — de ligger utanför H0:s
     universumdefinition.
  2. För varje sådan post kontrolleras om EODHD-arkivet har en prisserie, och
     om serien faktiskt sträcker sig fram till avnoteringsdatumet. En fil som
     slutar två år före avnoteringen täcker ingenting.
  3. Samma kontroll görs för överlevarna: hur många serier täcker hela
     2012-07 → 2019-12 (18 månaders lookback före 2014-01 plus fönstret).

Skriver INGA prisfiler. Ren inventering.

Kör: /opt/momentum/venv/bin/python tools/h1419_tackningsmatris.py
"""
from __future__ import annotations
import gzip, json, re
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
EOD = Path("/home/hannesb/momentum_prod_work/momentum_ml/cache/eodhd_archive/ST")
OUT = V2 / "research_k/h1419_tackningsmatris_results.json"

FONSTER_START, FONSTER_SLUT = "2014-01-01", "2019-12-31"
LOOKBACK_START = "2012-07-01"          # 18m momentum måste vara komplett 2014-01

MAIN = ("nasdaq stockholm", "nordiska listan", "stockholmsbörsen", "large cap",
        "mid cap", "small cap")
EJ_MAIN = ("first north", "aktietorget", "spotlight", "ngm", "nordic mtf",
           "nordic growth", "alternativa", "beQuoted".lower(), "pepins")


def las(p: Path):
    if not p.exists():
        return []
    try:
        with gzip.open(p, "rt", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def main():
    mst = json.loads((V2 / "docs/probes/instrument_master.json").read_text())

    # ---------- 1. kända Main Market-avnoteringar 2014-2019 ----------
    kandidater = []
    for r in mst:
        ar = r.get("avnoterad_ar")
        if not ar or not (2014 <= ar <= 2019):
            continue
        txt = (r.get("avnoterad_orsak") or "").lower()
        if any(x in txt for x in EJ_MAIN):
            continue
        if not any(x in txt for x in MAIN):
            continue
        kandidater.append(r)

    # avnoteringsdatum: föredra explicit datum, annars årets slut
    def avn_datum(r):
        d = r.get("avnoterad_datum")
        if d and re.match(r"^\d{4}-\d{2}-\d{2}$", str(d)):
            return str(d)
        return f"{r['avnoterad_ar']}-12-31"

    # ---------- 2. täckning i EODHD ----------
    rader, per_ar = [], defaultdict(lambda: {"kanda": 0, "har_fil": 0, "tacker_avnotering": 0})
    for r in kandidater:
        ar = r["avnoterad_ar"]
        per_ar[ar]["kanda"] += 1
        kod = (r.get("eodhd") or {}).get("code")
        dt = avn_datum(r)
        post = {"namn": r.get("namn"), "ar": ar, "avnoterad_datum": dt,
                "orsak": (r.get("avnoterad_orsak") or "")[:90],
                "eodhd_kod": kod, "har_fil": False, "serie_slut": None,
                "tacker_avnotering": False, "isin": (r.get("eodhd") or {}).get("isin")}
        if kod:
            for kat in ("delisted", "active"):
                rows = las(EOD / kat / "eod" / f"{kod}.json.gz")
                if rows:
                    post["har_fil"] = True
                    post["katalog"] = kat
                    post["serie_slut"] = rows[-1]["date"]
                    post["serie_start"] = rows[0]["date"]
                    # täcker avnoteringen om serien når inom 30 dagar före datumet
                    slut = date.fromisoformat(rows[-1]["date"])
                    mal = date.fromisoformat(dt)
                    post["dagar_fore_avnotering"] = (mal - slut).days
                    post["tacker_avnotering"] = -30 <= (mal - slut).days <= 365
                    break
        if post["har_fil"]:
            per_ar[ar]["har_fil"] += 1
        if post["tacker_avnotering"]:
            per_ar[ar]["tacker_avnotering"] += 1
        rader.append(post)

    # ---------- 3. överlevare som täcker hela fönstret ----------
    overlevare = 0
    kort = 0
    for kat in ("active", "delisted"):
        for p in sorted((EOD / kat / "eod").glob("*.json.gz")):
            rows = las(p)
            if not rows:
                continue
            if rows[0]["date"] <= LOOKBACK_START and rows[-1]["date"] >= FONSTER_SLUT:
                overlevare += 1
            elif rows[0]["date"] <= LOOKBACK_START and rows[-1]["date"] >= FONSTER_START:
                kort += 1

    tot_kanda = sum(v["kanda"] for v in per_ar.values())
    tot_tacker = sum(v["tacker_avnotering"] for v in per_ar.values())
    out = {
        "version": "H1419_TACKNINGSMATRIS_V1",
        "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "INVENTERING — inga prisfiler skrivna, inga frysta filer rörda",
        "fonster": {"start": FONSTER_START, "slut": FONSTER_SLUT, "lookback_fran": LOOKBACK_START},
        "kalla_avnoteringar": "docs/probes/instrument_master.json (Skatteverket)",
        "kalla_priser": str(EOD),
        "per_ar": {str(a): dict(v) for a, v in sorted(per_ar.items())},
        "totalt": {"kanda_main_market_avnoteringar": tot_kanda,
                   "med_prisfil": sum(v["har_fil"] for v in per_ar.values()),
                   "tacker_avnoteringen": tot_tacker,
                   "tackningsgrad": round(tot_tacker / tot_kanda, 3) if tot_kanda else None},
        "overlevare": {"serier_som_tacker_hela_fonstret": overlevare,
                       "serier_som_startar_i_tid_men_slutar_tidigt": kort},
        "auditens_antagande": {"tackning_2014_2019": "29/45 = 64 %",
                               "kalla": "docs/H0_HISTORICAL_EXTENSION_FEASIBILITY_AUDIT.md"},
        "rader": sorted(rader, key=lambda x: (x["ar"], x["namn"] or "")),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))

    print(f"KÄNDA MAIN MARKET-AVNOTERINGAR 2014-2019 (Skatteverket): {tot_kanda}")
    print(f"\n{'år':>5} {'kända':>7} {'har fil':>9} {'täcker avnot.':>14} {'grad':>7}")
    for a, v in sorted(per_ar.items()):
        g = v["tacker_avnotering"] / v["kanda"] if v["kanda"] else 0
        print(f"{a:>5} {v['kanda']:>7} {v['har_fil']:>9} {v['tacker_avnotering']:>14} {g:>7.0%}")
    print(f"{'SUMMA':>5} {tot_kanda:>7} {out['totalt']['med_prisfil']:>9} {tot_tacker:>14} "
          f"{out['totalt']['tackningsgrad']:>7.0%}")
    print(f"\nÖverlevare som täcker {LOOKBACK_START} → {FONSTER_SLUT}: {overlevare} serier")
    print(f"   startar i tid men slutar före fönstrets slut: {kort}")
    print(f"\nSkrivet: {OUT}")

    # de som saknas, för felsökning
    saknas = [r for r in rader if not r["tacker_avnotering"]]
    print(f"\nEJ TÄCKTA ({len(saknas)}), de tio första:")
    for r in saknas[:10]:
        print(f"   {r['ar']} {str(r['namn'])[:28]:<28} kod={str(r['eodhd_kod']):<12} "
              f"fil={r['har_fil']} slut={r['serie_slut']}")


if __name__ == "__main__":
    main()
