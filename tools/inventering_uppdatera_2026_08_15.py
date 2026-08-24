"""UPPDATERAR FORSKNINGSINVENTERINGEN MED 2026-08-15

Inventeringen stod på +N_RANK_TAKFEL_2026-08-14 och kände varken dagens sex
avfärdade regelfamiljer, placebometodiken, dataauditen eller H1419-resultatet.
Den är projektets do_not_repeat-lista; utan detta körs sveparna om.

Kör: /opt/momentum/venv/bin/python tools/inventering_uppdatera_2026_08_15.py
"""
from __future__ import annotations
import json, shutil
from datetime import datetime, timezone
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
INV = V2 / "research_k/FINAL_RESEARCH_INVENTORY_AFTER_K1_K3_K5.json"

NYA = [
    {"family": "Topp-5-spärr (behåll stämplat innehav tills rank > 40)",
     "status": "INGET STÖD",
     "evidence": "2026-08-15. N=20: 16,65 % mot baslinjens 16,83 % (−0,18 pp), sämre drawdown. "
                 "N=30: −0,74 pp. Dripsvepet monotont åt fel håll (>30 +1,64 → >50 −0,90). "
                 "Mekanik: de förlängda panelerna gav −3,17 % mot ersättarnas +1,62 %, t −1,71; "
                 "samma tecken vid N=30 (−5,40 mot +0,60, t −1,72).",
     "do_not_repeat": "Ingen variant av att förlänga innehav i tidigare topp-5-namn."},
    {"family": "Snäv utgång för topp-5-stämplade (sälj vid rank > 5/10/15)",
     "status": "INGET STÖD",
     "evidence": "2026-08-15. 24 armar (T × karens × beslutsfrekvens), median −0,83 pp, 20 av 24 "
                 "negativa. Bästa cellen +1,93 pp är bästa-av-24 och ger p ≈ 0,12 mot sitt eget "
                 "placebo. De enda KI som utesluter noll är negativa (N=30, T5, 4v: −2,35 och "
                 "−3,55 pp). Utkastade namn avkastade +1,74 % mot ersättarnas +1,92 % (n=1 294).",
     "do_not_repeat": "Inga fler utgångströsklar innanför topp-N."},
    {"family": "Snabbare beslutsfrekvens (4 veckor i stället för 8)",
     "status": "INGET STÖD",
     "evidence": "2026-08-15. N=20: 16,83 → 15,16 % (−1,67 pp), omsättning 214 → 291 %. "
                 "N=30: 14,34 → 13,91 %. Varje regelvariant är sämre i sin 4v-version än i "
                 "sin 8v-tvilling. Rankens autokorrelation över fyra veckor är 0,939, "
                 "implicerad daglig 0,9969 — tätare mätning bär ingen ny information.",
     "do_not_repeat": "Ingen tätare beslutsfrekvens, och ingen daglig panelberäkning: "
                      "t = mu*sqrt(T)/sigma beror på kalendertid, inte samplingsfrekvens. "
                      "Empiriskt verifierat: t = 2,61/2,44/2,69/2,54 vid 4/8/12/24 veckors "
                      "observationslängd över samma fem år."},
    {"family": "Återinträdesspärr för tidigare topp-5-namn (X fönster)",
     "status": "INGET STÖD — MOTBEVISAD RIKTNING",
     "evidence": "2026-08-15. Alla X negativa (−0,02 till −1,40 pp). Motbevisas av frekvens och "
                 "riktning: bara 20 av 237 inträden är stämplade återinträden, och de är den "
                 "BÄSTA inträdeskohorten (+6,28 % på en panel mot färska namns +1,97 %, "
                 "t mot färska 2,46 på tre paneler vid N=30, n=19).",
     "do_not_repeat": "Spärra aldrig återvändare. Om något ska prövas är det motsatsen, och då "
                      "förregistrerat."},
    {"family": "Reserverad satellitplats för stigande återvändare utanför gränsen",
     "status": "INGET STÖD",
     "evidence": "2026-08-15. k=2 ger +1,33 pp, men kontrollen utan topp-5-krav ger +1,30 och "
                 "kontrollen utan historikkrav +2,22. Stämpeln bidrar noll. 20 % av placebona "
                 "(slumpnamn ur topp-25 respektive topp-60) är minst lika bra. Regeln binder "
                 "bara 28 gånger på 33 beslutspaneler.",
     "do_not_repeat": "Ingen satellitkonstruktion byggd på tidigare topp-5."},
    {"family": "Två fönster: separat köpband och ägandegräns (hysteres)",
     "status": "INGET STÖD",
     "evidence": "2026-08-15. 23 celler. Bästa: N=10 med köp i band 15–25 och ägande till 30 ger "
                 "20,37 % och Sharpe 0,878 mot kanonisk N=10 16,58 % — men KI [−9,52, +10,09], "
                 "t 0,35, och cellen är bästa av 23. Runway-mekanismen motbevisad: hypotetiska "
                 "innehav från band 21–25 ger −0,34 % totalt mot band 6–10:s +7,28 %, och "
                 "gapkontrollen över 16 celler visar att effekten följer bandet UPPÅT, inte "
                 "gapet. Platser är billiga — poängkurvan är platt, 0,003 per plats.",
     "do_not_repeat": "Ingen hysteres, inget separat köpband, ingen tidig rekrytering."},
]

METOD = {
    "placebokravet": {
        "regel": "Varje portföljregel som ändrar VILKA namn som hålls måste jämföras mot ett "
                 "placebo som gör lika många byten på slumpvalda namn, med samma karens och "
                 "samma kostnad. Utan det är CAGR-differensen oläsbar.",
        "uppmatt_band": "sd 1,4–1,8 pp, 5–95 % ≈ ±2,4 pp på 66 paneler",
        "varfor": "Medianpanelen i topp-30 ger −0,18 % medan medelvärdet ger +0,77 %. "
                  "Medianavkastningen per hypotetiskt innehav är negativ i VARJE rankband "
                  "(−0,59 till −7,57 %). Hela avkastningen bor i en tunn svans, så varje "
                  "omfördelning av vilka svanshändelser som fångas ger ±2 pp av ingenting.",
        "teckentest_ogiltigt": "Teckenräkning över korrelerade armar (t.ex. 20 av 24 negativa) "
                               "är INTE bevis — armarna delar baslinje och data.",
        "baslinjekrav": "Varje nytt testskript måste reproducera baslinjen (16,83 % vid N=20, "
                        "16,58 % vid N=10, 14,34 % vid N=30 waterfill) på två decimaler innan "
                        "deltan läses. Fångade två skriptbuggar på en dag.",
        "kraftreferens": "Grundsignalen ger +15,77 pp med t = 2,61 på 5,08 år. Om 10–15 pp ger "
                         "t ≈ 2,6 ger 2 pp t ≈ 0,35. Marginella regler kräver storleksordningen "
                         "26 års kalendertid.",
    },
}

DATAAUDIT = {
    "datum": "2026-08-15",
    "friskt": ["ingen look-ahead (momentum på sista pris <= paneldatum, avkastning startar "
               "dagen EFTER panelen)",
               "universum 353 namn/panel, point-in-time, 70 serier slutar tidigt varav 68 med "
               "terminal-event",
               "medianpoäng-fallbacken landar på rank ~177 och rör aldrig topp-30",
               "exakta nollor 2,1–2,6 % jämnt över alla rankband",
               "extremvärden (+527 %) ligger alla på rank 271+"],
    "fynd": [
        {"fynd": "FR-overlayen binder knappt", "detalj": "81 % av ägda positioner är obekräftade "
         "och får 0,75x. Efter renormalisering är den bara en tilt mot de 19 % bekräftade — och "
         "bekräftade namn är ÖVERrepresenterade bland genomfarterna (27 % mot 17 %)."},
        {"fynd": "execution_engine returnerar tyst 0.0 vid saknad data", "detalj": "harmlöst här "
         "(2,4 % jämnt) men ett tyst felläge som döljer framtida dataförsämring."},
        {"fynd": "y52 (framåtblickande) ligger med i varje rankrad", "detalj": "används inte i "
         "poängen men är en rad från att bli look-ahead i nästa skript."},
        {"fynd": "justeringsfel i produktionslagret", "detalj": "Betsson 2022-05-13 (+45,9 %), "
         "SSAB-A 2020-04-02 (+44,3 %), Beijer 2020-04-17 (+44,9 %): utdelning applicerad framåt "
         "utan att historiken skalats om. Betsson nådde rank 1 och låg i topp-30 i 16 paneler. "
         "Uteslutning av de sju berörda namnen sänker N=30 med 0,89 pp, och bara 2 % av "
         "placebona är lika negativa. Identiteten adj_t/adj_(t-1) == (close_t*split + utd_t)/"
         "close_(t-1) håller inom 0,005 % för 99 % av dagarna i övrigt."},
        {"fynd": "rundresetestet krävs", "detalj": "(1+r_t)(1+r_t+1) ≈ 1 fångar korruption där "
         "BÅDE close och adjusted_close är fel och divergenstest därför missar. 33 sådana fel i "
         "det historiska arkivet, 4 i produktionslagret."},
    ],
    "ablation": "Svansen kommer från momentumurvalet, inte från add-onerna. Likaviktat universum "
                "är nästan symmetriskt (skevhet 0,17, kurtos −0,24). Ren rank topp-20 utan "
                "add-ons har redan skevhet 0,42, kurtos 1,32 och 87,9 % av uppgången ur de tre "
                "bästa panelerna. Varje add-on DÄMPAR svansen (topp3-panelandel 87,9 → 63,5 %, "
                "namnkoncentration 39,4 → 26,1 %). Nedbrytning N=20: universum 1,06 % → urval "
                "+10,39 → SMA +3,32 → invvol +2,61 → tak −1,51 → FR +0,96 = 16,83 %.",
}

H1419 = {
    "status": "HISTORICAL ROBUSTNESS — RESEARCH EXPOSED, aldrig oberoende holdback",
    "datum": "2026-08-15",
    "resultat_v2": "H0 N=30 på 2014-2019: 29,99 % mot likaviktat universum 17,84 % → "
                   "delta +12,15 pp, KI [+4,25, +23,74], t = 3,27, 99,9 % positiva bootstraps. "
                   "DOM: STÖD. Första t>3 i projektet.",
    "replikation": "Samma specifikation på 2020-2026 gav +12,73 pp. Två sexårsperioder, olika "
                   "regimer, en halv procentenhets skillnad. Det är replikationen som bär.",
    "resultat_v1": "246-namnsuniversumet gav +8,62 pp, KI [+3,30, +15,19], t 2,46. Ersatt för "
                   "dokumenterad defekt (ISIN-filtret uteslöt 44 bolag som låg på Main Market "
                   "hela fönstret men avnoterades 2020-2026). V1 får aldrig utelämnas när V2 "
                   "citeras.",
    "forbehall": "Citera aldrig de absoluta nivåerna. Universumet är 290 av periodens ~330 och "
                 "saknar stora uppköp (Meda, Com Hem, Arcam, IFS). Drawdownen är mätt på "
                 "fyraveckorsgittret och underskattar. Survivorship-riktningen är NEGATIV "
                 "(−2,26 pp mätt på 2020-2026, eftersom avnoteringar är uppköp med budpremie), "
                 "så deltat är ett GOLV.",
    "filer": ["research_k/h1419_exakt_h0_RESULTAT_V2.json",
              "research_k/h1419_exakt_h0_preregistration_v2.json",
              "research_k/H1419_PREREG_FREEZE_V2.json",
              "validated/prices_h1419/prices_h1419_universum_v2.json"],
}


def main():
    inv = json.loads(INV.read_text())
    shutil.copy(INV, INV.with_suffix(".json.bak_2026-08-15"))

    fanns = {f["family"] for f in inv["tested_families"]}
    lagt = 0
    for n in NYA:
        if n["family"] not in fanns:
            inv["tested_families"].append(n)
            lagt += 1
    inv["version"] = inv["version"] + " +REGELFAMILJER_METOD_DATAAUDIT_H1419_2026-08-15"
    inv["metodkrav_2026_08_15"] = METOD
    inv["dataaudit_2026_08_15"] = DATAAUDIT
    inv["h1419_historisk_robusthet"] = H1419
    inv["uppdaterad_utc"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    INV.write_text(json.dumps(inv, ensure_ascii=False, indent=1))

    from collections import Counter
    c = Counter(f.get("status", "?") for f in inv["tested_families"])
    print(f"Inventeringen uppdaterad. {lagt} nya familjer tillagda, "
          f"totalt {len(inv['tested_families'])}.")
    print(f"  version: {inv['version']}")
    print(f"  backup:  {INV.with_suffix('.json.bak_2026-08-15').name}")
    print("\n  statusfördelning:")
    for k, v in c.most_common():
        print(f"    {v:>3}  {k}")


if __name__ == "__main__":
    main()
