"""H1419 STEG 2 — AVNOTERADE GENOM QA OCH SAMMANSLAGET UNIVERSUM

Steg 1 gav ett QA-klassificerat lager om 222 ÖVERLEVARE. Filtret krävde Main
Market-ISIN i dagens lista, och avnoterade bolag har per definition ingen. Utan
dem är lagret rent survivorship.

Detta steg:
  1. plockar de avnoterade serier som täckningsmatrisen visade sig täcka,
  2. kör samma bevisbaserade brottklassificering på dem,
  3. slår ihop till ett universum och skriver medlemskapsfilen med
     membership_basis per namn — samma form som validated/membership_main_list_pit.json.

Medlemskapet är INTE verifierat. Överlevarna identifieras via dagens Main
Market-ISIN bakåtprojicerat; de avnoterade via Skatteverkets avnoteringsorsak.
Båda grunderna skrivs ut explicit per namn så att ingen kan förväxla dem med
daterad Nasdaq-referensdata.

Kör: /opt/momentum/venv/bin/python tools/h1419_steg2_universum.py
"""
from __future__ import annotations
import gzip, json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
EOD = Path("/home/hannesb/momentum_prod_work/momentum_ml/cache/eodhd_archive/ST")
INDIR = V2 / "validated/prices_h1419"
OUT_PRIS = INDIR / "prices_h1419_universum.json"
OUT_MEDL = INDIR / "membership_h1419.json"
OUT_QA = V2 / "research_k/h1419_steg2_universum_results.json"

BROTT_RET, RUNDRESA, DIVERGENS, SPLITTOL, KONTINUITET = 0.40, 0.10, 0.15, 0.01, 3.0
R4_FONSTER = 10
VANLIGA = [2, 3, 4, 5, 6, 8, 10, 20, 100]


def las(p: Path):
    if not p.exists():
        return []
    try:
        with gzip.open(p, "rt", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def narmaste(kvot):
    return min([(v, abs(kvot - v) / v) for q in VANLIGA for v in (float(q), 1.0 / q)],
               key=lambda x: x[1])


def klassificera(serie, raw, splitdatum):
    """Samma bevislogik som steg 1c. Returnerar (beslut, datum_att_utesluta)."""
    beslut, uteslut = [], set()
    for i in range(1, len(serie)):
        a0, a1 = serie[i - 1]["adj"], serie[i]["adj"]
        if a0 <= 0:
            continue
        ret = a1 / a0 - 1.0
        if abs(ret) < BROTT_RET:
            continue
        dt = serie[i]["d"]
        c0, c1 = serie[i - 1].get("c"), serie[i].get("c")
        ret_close = (c1 / c0 - 1.0) if (c0 and c1 and c0 > 0) else None
        div = (ret - ret_close) if ret_close is not None else None
        nasta = (serie[i + 1]["adj"] / a1 - 1.0) if i + 1 < len(serie) and a1 > 0 else None
        rund = (1.0 + ret) * (1.0 + nasta) if nasta is not None else None
        kvot = a1 / a0
        nara, avvik = narmaste(kvot)
        vol = raw.get(dt, {}).get("volume")
        hist = [raw.get(serie[j]["d"], {}).get("volume") for j in range(max(0, i - 20), i)]
        hist = [h for h in hist if h]
        volkvot = (vol / float(np.median(hist))) if (vol and hist and np.median(hist) > 0) else None

        if rund is not None and abs(rund - 1.0) < RUNDRESA:
            kl, r4 = "R4_ENDAGSSPIK", True
        elif div is not None and abs(div) > DIVERGENS:
            kl, r4 = "R4_JUSTERINGSFEL", True
        elif avvik < SPLITTOL and (volkvot is None or volkvot < 3.0) \
                and (nasta is None or abs(nasta) < 0.25):
            kl, r4 = "R4_OJUSTERAD_SPLIT", True
        elif kvot > KONTINUITET or kvot < 1.0 / KONTINUITET:
            kl, r4 = "R4_KONTINUITETSBROTT", True
        else:
            kl, r4 = "REELL_ROERELSE", False
        if r4:
            uteslut.update(serie[j]["d"] for j in
                           range(max(0, i - R4_FONSTER), min(len(serie), i + R4_FONSTER + 1)))
        beslut.append({"datum": dt, "klassificering": kl,
                       "ret_adjusted": round(ret, 4),
                       "divergens": round(div, 4) if div is not None else None,
                       "rundresa": round(rund, 4) if rund is not None else None,
                       "kvot": round(kvot, 5),
                       "volym_mot_20d_median": round(volkvot, 2) if volkvot else None})
    return beslut, uteslut


def main():
    tack = json.loads((V2 / "research_k/h1419_tackningsmatris_results.json").read_text())
    man = json.loads((INDIR / "manifest_h1419.json").read_text())
    prelim = json.loads((INDIR / "prices_h1419_preliminar.json").read_text())
    overlevare = json.loads((INDIR / "prices_h1419_klassificerad.json").read_text())
    filmeta = {f["kod"]: f for f in man["filer"]}

    avn = [r for r in tack["rader"] if r["tacker_avnotering"] and r.get("eodhd_kod")]
    print(f"Avnoterade med täckt prisserie: {len(avn)}")

    statistik, alla_beslut, tillagda = Counter(), [], {}
    for r in avn:
        kod = r["eodhd_kod"]
        serie = prelim.get(kod)
        if not serie:
            statistik["saknas_i_prislagret"] += 1
            continue
        kat = filmeta.get(kod, {}).get("katalog", "delisted")
        raw = {x["date"]: x for x in las(EOD / kat / "eod" / f"{kod}.json.gz")}
        splits = {str(s.get("date") or s.get("Date"))[:10]
                  for s in las(EOD / kat / "splits" / f"{kod}.json.gz")}
        beslut, uteslut = klassificera(serie, raw, splits)
        for b in beslut:
            statistik[b["klassificering"]] += 1
            alla_beslut.append({"kod": kod, "namn": r["namn"], **b})
        kvar = [x for x in serie if x["d"] not in uteslut]
        if len(kvar) < 60:
            statistik["for_kort_efter_r4"] += 1
            continue
        tillagda[kod] = [{"d": x["d"], "adj": x["adj"]} for x in kvar]
        statistik["tillagda_serier"] += 1

    universum = dict(overlevare)
    universum.update(tillagda)
    OUT_PRIS.write_text(json.dumps(universum, ensure_ascii=False))

    # ---- medlemskapsfil ----
    rader = []
    for kod in sorted(universum):
        if kod in tillagda:
            post = next(x for x in avn if x["eodhd_kod"] == kod)
            rader.append({"kod": kod, "namn": post["namn"],
                          "member_from": None, "member_to": post["avnoterad_datum"],
                          "membership_verified": False,
                          "basis": "SKATTEVERKET_AVNOTERINGSORSAK_MAIN_MARKET",
                          "kalla": post["orsak"],
                          "observation_window_from": "2014-01-01"})
        else:
            f = filmeta.get(kod, {})
            rader.append({"kod": kod, "namn": f.get("namn"),
                          "member_from": None, "member_to": None,
                          "membership_verified": False,
                          "basis": "DAGENS_MAIN_MARKET_ISIN_BAKATPROJICERAD",
                          "kalla": f.get("isin"),
                          "observation_window_from": "2014-01-01"})
    OUT_MEDL.write_text(json.dumps({
        "definition": "Nasdaq Stockholm Main Market (Large/Mid/Small), not First North/NGM/Spotlight",
        "study_start": "2014-01-01", "study_end": "2019-12-31",
        "status": "EJ VERIFIERAT MEDLEMSKAP — två grunder, båda utskrivna per namn",
        "coverage": {"n_codes": len(rader),
                     "overlevare_via_dagens_isin": len(rader) - len(tillagda),
                     "avnoterade_via_skatteverket": len(tillagda),
                     "kanda_main_market_avnoteringar_i_perioden":
                         tack["totalt"]["kanda_main_market_avnoteringar"],
                     "avnoteringstackning": tack["totalt"]["tackningsgrad"],
                     "unknown_handling": "member_from=null; observerad handel behålls från "
                                         "fönstret men beskrivs aldrig som verifierat medlemskap."},
        "rows": rader}, ensure_ascii=False, indent=1))

    OUT_QA.write_text(json.dumps({
        "version": "H1419_STEG2_UNIVERSUM_V1",
        "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "KLASSIFICERAD PÅ DATABEVIS — medlemskap ej verifierat",
        "avnoterade_provade": len(avn), "statistik": dict(statistik),
        "universum_storlek": len(universum),
        "beslut": alla_beslut}, ensure_ascii=False, indent=1))

    print(f"\nKLASSIFICERING AV DE AVNOTERADE:")
    for k, v in statistik.most_common():
        print(f"  {k:<26} {v:>4}")
    print(f"\nUNIVERSUM: {len(universum)} namn "
          f"({len(overlevare)} överlevare + {len(tillagda)} avnoterade)")
    print(f"  avnoteringstäckning: {tack['totalt']['tackningsgrad']:.0%} "
          f"({tack['totalt']['tacker_avnoteringen']} av "
          f"{tack['totalt']['kanda_main_market_avnoteringar']})")
    print(f"\nSkrivet:\n  {OUT_PRIS}\n  {OUT_MEDL}\n  {OUT_QA}")


if __name__ == "__main__":
    main()
