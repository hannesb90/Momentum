"""H1419 — RÄTTAT UNIVERSUM V2

V1 hade ett systematiskt hål: filtret krävde Main Market-ISIN i DAGENS lista,
vilket uteslöt varje bolag som låg på Main Market under 2014-2019 men lämnade
börsen någon gång fram till 2026. Täckningsmatrisen fångade bara avnoteringar
INOM fönstret och missade därför hela den gruppen.

Mätt: 44 bolag som finns i 2020+-universumet och har prisdata över hela
2014-2019 saknades i V1. 38 av dem har terminal-event, alltså avnoterade
2020-2026. Det är precis den population vars frånvaro blåser upp både
universumsindex och strategin.

Detta skript lägger till dem, kör samma bevisbaserade brottklassificering, och
skriver universum V2 plus uppdaterad medlemskapsfil.

V1:s resultat raderas inte. Det står kvar i h1419_exakt_h0_RESULTAT.json och
refereras explicit från förregistrering V2.

Kör: /opt/momentum/venv/bin/python tools/h1419_universum_v2.py
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
OUT_PRIS = INDIR / "prices_h1419_universum_v2.json"
OUT_MEDL = INDIR / "membership_h1419_v2.json"
OUT_QA = V2 / "research_k/h1419_universum_v2_results.json"

BROTT_RET, RUNDRESA, DIVERGENS, SPLITTOL, KONTINUITET, R4_FONSTER = 0.40, 0.10, 0.15, 0.01, 3.0, 10
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


def klassificera(serie, raw):
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
        rc = (c1 / c0 - 1.0) if (c0 and c1 and c0 > 0) else None
        div = (ret - rc) if rc is not None else None
        nasta = (serie[i + 1]["adj"] / a1 - 1.0) if i + 1 < len(serie) and a1 > 0 else None
        rund = (1.0 + ret) * (1.0 + nasta) if nasta is not None else None
        kvot = a1 / a0
        _, avvik = narmaste(kvot)
        vol = raw.get(dt, {}).get("volume")
        hist = [raw.get(serie[j]["d"], {}).get("volume") for j in range(max(0, i - 20), i)]
        hist = [h for h in hist if h]
        vk = (vol / float(np.median(hist))) if (vol and hist and np.median(hist) > 0) else None
        if rund is not None and abs(rund - 1.0) < RUNDRESA:
            kl, r4 = "R4_ENDAGSSPIK", True
        elif div is not None and abs(div) > DIVERGENS:
            kl, r4 = "R4_JUSTERINGSFEL", True
        elif avvik < SPLITTOL and (vk is None or vk < 3.0) and (nasta is None or abs(nasta) < 0.25):
            kl, r4 = "R4_OJUSTERAD_SPLIT", True
        elif kvot > KONTINUITET or kvot < 1.0 / KONTINUITET:
            kl, r4 = "R4_KONTINUITETSBROTT", True
        else:
            kl, r4 = "REELL_ROERELSE", False
        if r4:
            uteslut.update(serie[j]["d"] for j in
                           range(max(0, i - R4_FONSTER), min(len(serie), i + R4_FONSTER + 1)))
        beslut.append({"datum": dt, "klassificering": kl, "ret_adjusted": round(ret, 4)})
    return beslut, uteslut


def main():
    prelim = json.loads((INDIR / "prices_h1419_preliminar.json").read_text())
    v1 = json.loads((INDIR / "prices_h1419_universum.json").read_text())
    medl1 = json.loads((INDIR / "membership_h1419.json").read_text())
    man = json.loads((INDIR / "manifest_h1419.json").read_text())
    filmeta = {f["kod"]: f for f in man["filer"]}
    prod = json.loads((V2 / "validated/prices/prices_validated.json").read_text())
    term = json.loads((V2 / "validated/terminal_events.json").read_text())

    # namn i 2020+-universumet med data över hela fönstret som saknas i V1
    nya = [k for k in prod if k in prelim and k not in v1
           and prelim[k][0]["d"] <= "2014-01-15" and prelim[k][-1]["d"] >= "2019-12-15"]
    print(f"Kandidater att lägga till: {len(nya)} "
          f"(varav {sum(1 for k in nya if k in term)} med terminal-event)")

    statistik, tillagda, beslut_alla = Counter(), {}, []
    for kod in sorted(nya):
        kat = filmeta.get(kod, {}).get("katalog", "active")
        raw = {x["date"]: x for x in las(EOD / kat / "eod" / f"{kod}.json.gz")}
        beslut, uteslut = klassificera(prelim[kod], raw)
        for b in beslut:
            statistik[b["klassificering"]] += 1
            beslut_alla.append({"kod": kod, **b})
        kvar = [x for x in prelim[kod] if x["d"] not in uteslut]
        if len(kvar) < 60:
            statistik["for_kort_efter_r4"] += 1
            continue
        tillagda[kod] = [{"d": x["d"], "adj": x["adj"]} for x in kvar]
        statistik["tillagda"] += 1

    universum = dict(v1)
    for k, v in tillagda.items():
        assert k not in universum, f"kodkrock: {k}"
        universum[k] = v
    OUT_PRIS.write_text(json.dumps(universum, ensure_ascii=False))

    rader = list(medl1["rows"])
    for kod in sorted(tillagda):
        rader.append({"kod": kod, "namn": filmeta.get(kod, {}).get("namn"),
                      "member_from": None,
                      "member_to": term.get(kod, {}).get("event_date") if kod in term else None,
                      "membership_verified": False,
                      "basis": "V2_MAIN_MARKET_UNIVERSUM_2020PLUS_MED_DATA_I_FONSTRET",
                      "kalla": "validated/prices/prices_validated.json + terminal_events.json",
                      "observation_window_from": "2014-01-01"})
    OUT_MEDL.write_text(json.dumps({
        **{k: v for k, v in medl1.items() if k != "rows"},
        "status": "EJ VERIFIERAT MEDLEMSKAP — tre grunder, alla utskrivna per namn. "
                  "V2 rättar V1:s hål: bolag som låg på Main Market i fönstret men "
                  "avnoterades 2020-2026 saknades helt.",
        "coverage": {**medl1["coverage"], "n_codes": len(rader),
                     "tillagda_i_v2": len(tillagda),
                     "darav_med_terminal_event": sum(1 for k in tillagda if k in term)},
        "rows": rader}, ensure_ascii=False, indent=1))

    OUT_QA.write_text(json.dumps({
        "version": "H1419_UNIVERSUM_V2_V1",
        "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "rattar": "V1:s ISIN-filter uteslöt bolag som avnoterades 2020-2026",
        "kandidater": len(nya), "statistik": dict(statistik),
        "universum_v1": len(v1), "universum_v2": len(universum),
        "beslut": beslut_alla}, ensure_ascii=False, indent=1))

    print(f"\nKLASSIFICERING AV DE TILLAGDA:")
    for k, v in statistik.most_common():
        print(f"  {k:<24} {v:>4}")
    print(f"\nUNIVERSUM V1: {len(v1)}  ->  V2: {len(universum)}")
    print(f"Skrivet:\n  {OUT_PRIS}\n  {OUT_MEDL}\n  {OUT_QA}")


if __name__ == "__main__":
    main()
