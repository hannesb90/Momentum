"""H1419 STEG 3 — FÖRREGISTRERING AV EXAKT H0 PÅ 2014-2019

Auditens krav 8: "separat preregistrering av exakt H0, utan alternativa
horisonter, Top-N, vikt eller rebalancefas."

Skriptet skriver förregistreringen OCH låser den kryptografiskt mot de
datafiler den ska köras på. Efter frysningen kan varken specifikationen eller
indata ändras utan att låset bryts synligt.

Ingen körning sker här. Ingen avkastning beräknas. Ingen ranking byggs.

Kör: /opt/momentum/venv/bin/python tools/h1419_forregistrering.py
"""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
PREREG = V2 / "research_k/h1419_exakt_h0_preregistration_v2.json"
FREEZE = V2 / "research_k/H1419_PREREG_FREEZE_V2.json"

INDATA = [
    "validated/prices_h1419/prices_h1419_universum_v2.json",
    "validated/prices_h1419/membership_h1419_v2.json",
    "validated/prices_h1419/manifest_h1419.json",
    "research_k/h1419_tackningsmatris_results.json",
    "research_k/h1419_brottklassificering_results.json",
    "research_k/h1419_steg2_universum_results.json",
    "research_k/h1419_universum_v2_results.json",
]


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 16), b""):
            h.update(c)
    return h.hexdigest()


def main():
    prereg = {
        "preregistration_id": "H1419_EXAKT_H0_NASDAQ_STOCKHOLM_2014_2019_V2",
        "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "created_before_any_return_computed": False,
        "ersatter": {
            "v1_id": "H1419_EXAKT_H0_NASDAQ_STOCKHOLM_2014_2019_V1",
            "v1_sha256": "87cb01d623d6beacd07bf3c1d11ab75567f7998d3091cd1a7b4111cf1f74133e",
            "v1_resultat_publicerat_i": "research_k/h1419_exakt_h0_RESULTAT.json",
            "v1_utfall": "delta-CAGR +8,62 pp, KI [+3,30, +15,19], t 2,46, DOM STOD",
            "varfor_ersatt": "V1:s universumfilter kravde Main Market-ISIN i DAGENS lista och "
                             "uteslot darmed varje bolag som lag pa Main Market under 2014-2019 "
                             "men avnoterades 2020-2026. 44 sadana bolag med data over hela "
                             "fonstret saknades, varav 38 med terminal-event. Defekten "
                             "upptacktes EFTER att V1 korts, genom att arsavkastningen for det "
                             "likaviktade universumet (+18,77 %/ar) lag orimligt hogt over "
                             "index (~12 %/ar) och maxdrawdown var for grund (-12,09 %).",
            "hederlighetsklausul": "V1:s resultat far aldrig utelamnas nar V2 rapporteras. "
                                   "Bada koringarna ar gjorda pa samma hypotes och samma "
                                   "specifikation; endast universumet skiljer.",
        },
        "research_status": "HISTORICAL ROBUSTNESS — RESEARCH EXPOSED",
        "får_aldrig_kallas": "oberoende holdback eller untouched forward. Legacy innehåller "
                             "157 skript som startar 2010-01-01; perioden är exponerad.",

        # ---------- den enda frågan ----------
        "hypotes": "Kärnsignalen i H0 — rankning på 0,5*(rank(mom_12m) + rank(mom_18m)) — "
                   "producerar positiv överavkastning mot ett likaviktat universum även "
                   "under 2014-2019.",
        "primart_utfallsmatt": "CAGR för H0 topp-30 minus CAGR för likaviktat universum, "
                               "över samtliga paneler i fönstret.",
        "beslutsregel": {
            "stod": "block-bootstrapat 95 %-KI för delta-CAGR utesluter noll, med "
                    "13-panelsblock och 2000 dragningar, seed 20260815",
            "inget_stod": "KI innehåller noll",
            "ingen_efterhandsjustering": "inga alternativa N, horisonter, vikter eller "
                                         "ombalanseringsfaser får prövas och rapporteras "
                                         "som utfall av detta test",
        },

        # ---------- exakt specifikation, inga alternativ ----------
        "specifikation": {
            "signal": "0.5 * (percentilrank(mom_12m) + percentilrank(mom_18m))",
            "mom_12m": "52 veckors prisförändring på adjusted_close, sista pris <= paneldatum",
            "mom_18m": "78 veckors prisförändring på adjusted_close, sista pris <= paneldatum",
            "saknad_momentum": "namnet får medianpoäng (kanonisk regel, oförändrad)",
            "portfoljstorlek_N": 30,
            "urval": "topp-N vid schemalagd ombalansering; mellan ombalanseringar behålls "
                     "innehav som ligger kvar i universumet, påfyllnad i rankordning",
            "entrégrind": "SMA200-skip — namn under 200-dagars glidande medelvärde utesluts "
                          "ur viktningen den panelen",
            "viktning": "invers volatilitet upphöjt till 1,5, 60 dagars fönster",
            "fr_overlay": "0,75x för obekräftade namn (pris >= MA120 och vol60 < 0,35 = bekräftad)",
            "vikttak": "clip(w, 0.01, 0.06) följt av w/sum(w)*target_sum UTAN iteration — "
                       "den kanoniska implementationen inklusive det dokumenterade takfelet, "
                       "så att talen är jämförbara med 2020+",
            "target_sum": "n_kvar_efter_SMA / N",
            "panelfrekvens": "28 dagar",
            "ombalansering": "varannan panel (56 dagar)",
            "fasankare": "första panelen i fönstret; ingen fasoptimering får göras",
            "transaktionskostnad": "20 baspunkter enkelriktat på omsättningen",
            "avkastningsdefinition": "panel-till-panel på adjusted_close, från första "
                                     "handelsdag efter panelen till första handelsdag efter "
                                     "nästa panel",
        },

        # ---------- fönster ----------
        "fonster": {"lookback_start": "2012-07-01", "test_start": "2014-01-01",
                    "test_slut": "2019-12-31", "n_paneler": 79, "n_ombalanseringar": 39},

        # ---------- vad som MÅSTE publiceras med resultatet ----------
        "obligatorisk_redovisning": {
            "avnoteringstackning": "24 av 45 unika kända Main Market-avnoteringar = 53 %",
            "universumsstorlek": "290 namn mot periodens uppskattade ~330",
            "medlemskapsgrund": "EJ VERIFIERAT. 222 namn via dagens Main Market-ISIN "
                                "bakatprojicerad, 24 via Skatteverkets avnoteringsorsak, "
                                "44 via 2020+-universumet med data i fonstret (38 av dem "
                                "avnoterade 2020-2026).",
            "survivorship_riktning": "NEGATIV. Mätt på 2020-2026 sänker survivorship-bortfall "
                                     "resultatet med 2,26 pp vid både N=20 och N=30, eftersom "
                                     "avnoteringar övervägande är uppköp med budpremie. "
                                     "Resultatet ska därför läsas som ett GOLV.",
            "uppskattad_restbias": "-1 till -2 pp, konservativ riktning",
            "qa": "770 rader uteslutna i överlevarlagret (0,058 %), 82 brott klassificerade "
                  "i de avnoterade. Korrupta arkivdatum 2013-05-10 och 2019-06-10 hanterade "
                  "via rundresetestet.",
        },

        # ---------- vad som är förbjudet ----------
        "forbjudet": [
            "att pröva andra N än 30 och rapportera som utfall av detta test",
            "att pröva andra momentumhorisonter",
            "att ändra vikttak, viktmetod eller FR-overlay",
            "att flytta ombalanseringsfasen",
            "att utvidga eller begränsa fönstret efter att ett resultat setts",
            "att lägga till eller ta bort namn ur universumet efter frysning",
            "att beskriva perioden som oberoende holdback",
        ],
        "indata_last": [],
    }

    for rel in INDATA:
        p = V2 / rel
        prereg["indata_last"].append({"fil": rel, "sha256": sha(p), "n_bytes": p.stat().st_size})

    PREREG.write_text(json.dumps(prereg, ensure_ascii=False, indent=1))
    FREEZE.write_text(json.dumps({
        "version": "H1419_PREREG_FREEZE_V2",
        "locked_file": "h1419_exakt_h0_preregistration_v2.json",
        "sha256": sha(PREREG), "n_bytes": PREREG.stat().st_size,
        "status": "LOCKED_BEFORE_ANY_RESULT",
        "locked_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }, ensure_ascii=False, indent=1))

    print("FÖRREGISTRERING SKRIVEN OCH LÅST")
    print(f"  {PREREG}")
    print(f"  {FREEZE}")
    print(f"\n  hypotes: kärnsignalen bär även 2014-2019")
    print(f"  N=30, 79 paneler, 39 ombalanseringar, kanoniskt vikttak inkl. takfelet")
    print(f"\n  låsta indatafiler:")
    for f in prereg["indata_last"]:
        print(f"    {f['sha256'][:16]}…  {f['n_bytes']:>10} B  {f['fil']}")
    print(f"\n  frysningshash: {sha(PREREG)}")


if __name__ == "__main__":
    main()
