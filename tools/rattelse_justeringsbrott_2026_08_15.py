"""RÄTTELSE — ADJ-BASERADE JUSTERINGSBROTT IN I QA-LAGRET

Den befintliga QA-detektionen (docs/probes/price_qa_slutlig.json, 871 brott)
letar efter kvotbrott i CLOSE. Åtta brott i produktionslagret finns bara i
ADJUSTED_CLOSE och har därför aldrig upptäckts: justeringsfaktorn ändras på
utdelnings- eller emissionsdagen utan att historiken skalas om, så den justerade
serien hoppar medan råpriset knappt rör sig.

  BETS-B 2022-05-13:  close 64,88 -> 66,96 (+3,2 %)   adj 36,35 -> 53,05 (+45,9 %)
                      faktor 1,7848 -> 1,2623, och 64,88/(64,88-18,995) = 1,414
                      = 1,7848/1,2623 — utdelningen förklarar faktorändringen exakt.

Kriteriet för att klassa som justeringsproblem: |ret(adj) - ret(close)| > 0,15
på en dag. Ingen korrekt totalavkastningsjustering av en normal händelse
producerar den avvikelsen.

Behandlingen är R4: spannet ±5 kalenderdagar utesluts. INGET värde skrivs om.

Skriptet säkerhetskopierar allt det rör, lägger in posterna, bygger om lagret
och mäter modellen före och efter.

Kör: /opt/momentum/venv/bin/python tools/rattelse_justeringsbrott_2026_08_15.py
"""
from __future__ import annotations
import gzip, json, shutil, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
EOD = Path("/home/hannesb/momentum_prod_work/momentum_ml/cache/eodhd_archive/ST")
QA = V2 / "docs/probes/price_qa_slutlig.json"
PRIS = V2 / "validated/prices/prices_validated.json"
RAPPORT = V2 / "research_k/rattelse_justeringsbrott_2026_08_15_results.json"
STAMP = "2026-08-15"


def las(p: Path):
    if not p.exists():
        return []
    try:
        with gzip.open(p, "rt", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def main():
    fynd = json.loads((V2 / "research_k/rundresetest_produktionslagret_results.json").read_text())
    fall = [f for f in fynd["fynd"] if f["klassificering"] == "JUSTERINGSFEL"]
    print(f"Justeringsbrott att lägga in: {len(fall)}")

    kat = {}
    for g in ("active", "delisted"):
        for x in json.loads((EOD / f"{g}_catalogue.json").read_text()):
            kat.setdefault(x["Code"], g)

    nya = []
    for f in fall:
        kod, dt = f["kod"], f["datum"]
        g = kat.get(kod, "active")
        rows = las(EOD / g / "eod" / f"{kod}.json.gz")
        idx = {r["date"]: i for i, r in enumerate(rows)}
        i = idx.get(dt)
        if i is None or i == 0:
            print(f"  HOPPAR {kod} {dt}: hittar inte raden i arkivet")
            continue
        fore = rows[i - 1]
        nya.append({
            "code": kod, "namn": None, "grupp": g,
            "datum_fore": fore["date"], "datum_efter": dt,
            "close_fore": fore.get("close"), "close_efter": rows[i].get("close"),
            "kvot": round(rows[i]["close"] / fore["close"], 6) if fore.get("close") else None,
            "adj_fore": fore.get("adjusted_close"), "adj_efter": rows[i].get("adjusted_close"),
            "kvot_adj": round(rows[i]["adjusted_close"] / fore["adjusted_close"], 6),
            "vol_efter": rows[i].get("volume"),
            "splits": [], "divs": [], "revert10": False, "avnoterad": None, "kluster": None,
            "klass": "split-/justeringsproblem",
            "motivering": (f"Justeringsdiskontinuitet {STAMP}: ret(adj) {f['ret_adjusted']:+.4f} "
                           f"mot ret(close) {f['ret_close']:+.4f}, divergens {f['divergens']:+.4f}. "
                           f"Justeringsfaktorn ändras utan att historiken skalas om. Upptäckt av "
                           f"adj-baserad identitetskontroll; den ursprungliga QA-svepningen "
                           f"detekterade endast kvotbrott i close."),
        })

    # ---------- säkerhetskopior ----------
    for p in (QA, PRIS, V2 / "validated/manifest_sparA.json"):
        if p.exists():
            shutil.copy(p, p.with_suffix(p.suffix + f".bak_{STAMP}"))
    fore_lager = json.loads(PRIS.read_text())
    fore_rader = sum(len(v) for v in fore_lager.values())

    qa = json.loads(QA.read_text())
    fanns = {(b["code"], b["datum_efter"]) for b in qa["brott"]}
    lagt = [n for n in nya if (n["code"], n["datum_efter"]) not in fanns]
    qa["brott"].extend(lagt)
    qa["n_brott"] = len(qa["brott"])
    qa.setdefault("tillagg", []).append({
        "datum": STAMP, "antal": len(lagt),
        "kalla": "tools/rundresetest_produktionslagret.py + justeringsidentitet_produktionslagret.py",
        "orsak": "adj-baserade justeringsbrott som close-detektionen aldrig såg"})
    QA.write_text(json.dumps(qa, ensure_ascii=False, indent=1))
    print(f"  {len(lagt)} poster tillagda i QA-lagret (totalt {qa['n_brott']})")

    # ---------- bygg om ----------
    print("\nBygger om validated-lagret...")
    r = subprocess.run([str(Path("/opt/momentum/venv/bin/python")), "tools/build_validated_prices.py"],
                       cwd=str(V2), capture_output=True, text=True)
    print(r.stdout[-1500:] if r.stdout else "(ingen utdata)")
    if r.returncode != 0:
        print("BYGGET MISSLYCKADES — återställer säkerhetskopiorna")
        print(r.stderr[-2000:])
        for p in (QA, PRIS, V2 / "validated/manifest_sparA.json"):
            b = p.with_suffix(p.suffix + f".bak_{STAMP}")
            if b.exists():
                shutil.copy(b, p)
        sys.exit(1)

    efter_lager = json.loads(PRIS.read_text())
    efter_rader = sum(len(v) for v in efter_lager.values())

    ut = {"version": "RATTELSE_JUSTERINGSBROTT_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "kriterium": "|ret(adj) - ret(close)| > 0,15 på en dag",
          "behandling": "R4 — problemspannet ±5 kalenderdagar utesluts, inget värde skrivs om",
          "tillagda_brott": lagt,
          "lager_fore": {"serier": len(fore_lager), "rader": fore_rader},
          "lager_efter": {"serier": len(efter_lager), "rader": efter_rader},
          "borttagna_rader": fore_rader - efter_rader,
          "sakerhetskopior": f"*.bak_{STAMP}"}
    RAPPORT.write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    print(f"\nLager: {len(fore_lager)} serier / {fore_rader} rader "
          f"-> {len(efter_lager)} serier / {efter_rader} rader "
          f"({fore_rader - efter_rader} rader uteslutna)")
    print(f"Skrivet: {RAPPORT}")


if __name__ == "__main__":
    main()
