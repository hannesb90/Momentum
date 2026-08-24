# PIT SIZE FOUNDATION — NASDAQ HISTORICAL SEGMENT RECONSTRUCTION

Datum 2026-08-18 · **Rent data- och provenanceuppdrag. Noll size-tester körda.**
Steg 0 pre-flight: `tools/repo_integrity_gate.py` → **PASS**, returkod 0, 0 blockerare.
Artefakter: `research_k/nasdaq_segment_foundation/` · manifest med SHA256 för samtliga 10 filer.

H0 V2 och K1 orörda. Hysteres och G97-P orörda. G-HET-1, G-SIZE-HET-1, G-HIER-1
och G-HIER-2 har inte lästs, citerats eller använts.

---

## SAMMANFATTNING

**Två genombrott och en blockerare.**

Genombrott 1: **En PIT-valid baseline roster hittades och är hämtad.** NASDAQ OMX
Nordics *Official Price List — The Nordic List*, 25 april 2013, 168 sidor, med
separata sektioner för Large/Mid/Small Cap, ISIN och exchange-kod per rad.
Parsad: **290 Nasdaq Stockholm-instrument — 84 Large, 75 Mid, 131 Small.** Sparad
lokalt som RAW med SHA256 `f2608a6f…`.

Genombrott 2: **Change-ledgerns semantik är fastställd ur källan, inte antagen.**

Blockerare: **ISIN är inte tidsinvariant.** Vårt identitetslager bär *dagens* ISIN
bakåtprojicerade; 2013-rostern bär 2013-ISIN. Endast 36,2 % joinar — och
**61,4 % av universumet handlades på rosterns datum men går inte att joina.**
Det är ett identitetsproblem, inte ett täckningsproblem i källan.

---

## STEG 1 + 2 — REVIEW-TÄCKNING, EXAKT

Ingen uppskattning. Årgångar med *effective date* i den behövda perioden
2014-01-02 – 2026-01-02, alltså 13 årgångar:

| Effective | Status | Lokal RAW | Källa |
|---|---|:---:|---|
| 2014-01-02 | **SAKNAS** | — | — |
| 2015-01-02 | **SAKNAS** | — | — |
| 2016-01-04 | **SAKNAS** | — | — |
| 2017-01-02 | URL känd, ej verifierad | **NEJ** | globenewswire (dansk utgåva) |
| 2018-01-02 | **SAKNAS** | — | — |
| 2019-01-02 | URL känd, ej verifierad | **NEJ** | globenewswire |
| 2020-01-02 | URL känd, ej verifierad | **NEJ** | view.news.eu.nasdaq.com |
| 2021-01-04 | **SAKNAS** | — | — |
| 2022-01-03 | **FÖRSTA PARTS VERIFIERAD 2026-08-18** | nej | view.news.eu.nasdaq.com |
| ~2023 | URL känd, datum obekräftat | **NEJ** | view.news.eu.nasdaq.com |
| 2024-01-02 | **SAKNAS** | — | — |
| 2025-01-02 | URL känd, ej verifierad | **NEJ** | view.news.eu.nasdaq.com |
| 2026-01-02 | **SAKNAS** | — | — |

**6 av 13 har känd URL · 7 saknas helt · 1 är verifierad mot källan · 0 har lokal RAW.**

### Ett provenance-fynd om Stage 79

`run_nasdaq_segment_evidence_stage79.py` **sparade aldrig någon RAW-artefakt.**
Evidensfilens pressmeddelanden har endast fälten `effective`, `url`, `note` — ingen
`sha256`, ingen lokal sökväg. Sökning efter lokalt sparade Nasdaq-dokument i hela
arbetsytan: **noll träffar.**

De 7 årgångarna är alltså **andrahandstranskriptioner utan lokalt verifierbar
artefakt**. Det ändrar deras status: de är discovery-material, inte canonical
evidence. Den enda årgång som nu har verifierad förstapartsprovenance är den jag
hämtade om själv (2022-01-03).

---

## STEG 4 — VAD REVIEWN FAKTISKT INNEHÅLLER

Avgjort ur källan, verbatim, inte antaget:

> **"Effective January 3, 2022, the following 51 companies will change segment:
> 47 companies will change to a larger segment, while 4 companies will change to
> a smaller segment."**

**Svar: alternativ B — samtliga segmentBYTEN för den reviewn, men INGEN roster.**

Formuleringen *"the following 51 companies will change segment"* är ett
fullständighetsanspråk för *byten* i just den reviewn. Den säger ingenting om
medlemskap för bolag som inte bytte.

**PIT-semantiken är verifierad och korrekt:**

| | |
|---|---|
| Publication date | 2021-12-20 09:00 CET |
| Effective date | 2022-01-03 |
| Observationsperiod | november 2021 genomsnittligt börsvärde |
| Publicering före ikraftträdande | **14 dagar** |
| Trösklar | Large ≥ EUR 1 mdr · Mid EUR 150 m–1 mdr · Small < EUR 150 m |
| Marknader | Stockholm, Helsinki, Copenhagen, Reykjavik |

**Klassificering: `COMPLETE_CHANGE_EVIDENCE_PER_VINTAGE_BUT_NO_ROSTER`.**

### Den konsekvens som inte var förutsedd

Eftersom reviewn redovisar **byten**, får ett bolag som börsintroduceras direkt in
i ett segment **inget PIT-segmentursprung ur denna källa**. Baseline + samtliga
reviews räcker alltså inte — en **tredje datastrom** krävs: admission notices som
anger segment vid upptagande till handel.

---

## STEG 3 — BASELINE ROSTER: HITTAD OCH VERIFIERAD

| | |
|---|---|
| Dokument | NASDAQ OMX Nordic — *Official Price List, The Nordic List* |
| Datum | **torsdag 25 april 2013** |
| Källtyp | **förstaparts Nasdaq** |
| Omfång | 168 sidor |
| SHA256 | `f2608a6fe4fef8e85787273bf3713bf3dad7f87fc6312f0757ccb0b8d8a91a51` |
| Fullständig? | **JA** — innehållsförteckningen har separata sektioner *Nordic Large Cap* (s. 3), *Nordic Mid Cap* (s. 8), *Nordic Small Cap* (s. 13) |
| Fält per rad | Name · Trading currency · Nominal value · **ISIN** · **Exchange** (XSTO/XCSE/XHEL/XICE) · pris/volym |
| Parsade rader | 605 totalt · **290 XSTO** |
| XSTO per segment | **84 LARGE · 75 MID · 131 SMALL** |
| Flera aktieslag | hanteras korrekt som separata rader med egen ISIN (SEB A / SEB C, Handelsbanken A / B) |
| Avnoterade representerade | **JA** |
| PIT-bedömning | **PIT_VALID** — daterad, publicerad samtidigt som den gäller |

**Källan är inte survivorship-filtrerad.** 22 av de 68 instrument som senare
avnoterades finns i 2013-rostern: ABLI, ARISE, ATRE, BIOT, CCOR-B, COIC, DORO,
ELOS-B, ETX, FEEL med flera. Det är den avgörande skillnaden mot
`sweden_universe.csv`, där avnoterade saknas helt.

Ingen baseline har konstruerats genom att rulla dagens segment bakåt.

---

## STEG 6 — IDENTITETSBLOCKERAREN, KVANTIFIERAD

Detta är uppdragets kritiska fynd.

| 2014-2019-universum (290 instrument) | n | andel |
|---|---:|---:|
| **A** joinar OPL 2013 via ISIN | 105 | **36,2 %** |
| **B** handlades 2013-04-25 men joinar **inte** | **178** | **61,4 %** |
| **C** handlades genuint inte då | 7 | 2,4 % |

Endast 2,4 % var faktiskt inte på marknaden. Diagnos av grupp B:

| Kod | Vårt ISIN (bakåtprojicerat) | OPL 2013-ISIN | OPL 2013-namn |
|---|---|---|---|
| ALIV-SDB | `SE0021309614` | **`SE0000382335`** | Autoliv SDB |
| AAK | `SE0011337708` | **`SE0001493776`** | AarhusKarlshamn |
| AQ | `SE0022062196` | — | — |
| ANOD-B | `SE0017885767` | — | — |

Autoliv SDB **finns i rostern**, klassad LARGE. Den joinar inte eftersom bolaget
bytt ISIN. AarhusKarlshamn heter idag AAK och har ny ISIN. `SE0021…` och `SE0022…`
är serier utgivna 2021-2022.

**ISIN är inte en tidsinvariant identifierare, och vårt identitetslager bär
`DAGENS_MAIN_MARKET_ISIN_BAKATPROJICERAD`.** Namnbaserad matchning
(*Autoliv SDB* → `ALIV-SDB`) är precis den fuzzy match som Steg 6 förbjuder att
tyst acceptera. **Samtliga 178 står som `UNRESOLVED`. Ingen har fyllts.**

Vad som krävs: en **tidsberoende ISIN-/identitetshistorik** per instrument med
`valid_from`/`valid_to`. Med en sådan skulle täckningen kunna nå ~97 % i det
tidiga fönstret (283 av 290 handlades på rosterns datum).

---

## STEG 7 — VERIFIERADE TIDSLINJER

### BIOT (Biotage) — det begärda testfallet

| Tidpunkt | Segment | Provenance |
|---|---|---|
| 2013-04-25 | **SMALL** (`SE0000454746`) | **förstaparts verifierad** — OPL-rostern |
| 2017-01-02 | → MID | legacy-transkription, **ej lokalt verifierad** |
| 2022-01-03 | → **LARGE** | **förstaparts verifierad 2026-08-18** |

Tidslinjen `Small → Mid 2017-01-02 → Large 2022-01-03` **bekräftas**, med två av
tre punkter nu förstahandsverifierade.

### Övriga, mot samma två verifierade källor

| Kod | OPL 2013-04-25 | Verifierad förändring |
|---|---|---|
| SAS | **MID** (`SE0003366871`) | → Large 2022-01-03 ✓ |
| ELOS-B | **SMALL** (`SE0000120776`) | → Mid 2022-01-03 ✓ |
| KLED (Kungsleden) | **MID** (`SE0000549412`) | → Large 2017-01-02 (ej verifierad) |
| **COLL** (Collector) | **finns ej i rostern** | kan **inte** ankras |
| **MAG** (Magnolia) | **finns ej i rostern** | kan **inte** ankras |
| **RESURS** | **finns ej i rostern** | → Mid 2022-01-03 ✓, men ursprunget okänt |

**Konsistenskontroll:** baseline 2013 och den verifierade 2022-reviewn är
ömsesidigt konsistenta för BIOT, SAS, ELOS-B och KLED — rosterns 2013-segment
ligger på eller under det segment reviewn senare flyttar bolaget *från*, i rätt
riktning. Två oberoende förstapartskällor som stämmer.

COLL, MAG, RESURS, LEO, READ och SRNKE-B börsintroducerades efter 2013-04-25.
Deras segmentursprung finns i **ingen** av källorna — den strukturella luckan från
Steg 4.

---

## STEG 5 och 8 — GENOMFÖRS INTE

**Steg 5 (rekonstruera PIT-intervall):** kräver *både* en PIT-valid baseline *och*
tillräckligt verifierad change-ledger. Baseline finns. Change-ledgern är verifierad
för **1 av 13** årgångar och har ingen lokal RAW för de övriga. Dessutom saknas
identitetsbryggan. **Ingen canonical intervallserie har byggts.**

**Steg 8 (checkpoint-validering):** kräver minst två fullständiga rosters. Endast
**en** finns. Kan inte utföras.

---

## STEG 9 — PANEL COVERAGE

Redovisas som **tak** för vad dagens identitetslager kan joina, **inte** som
täckning för en rekonstruerad serie:

| | 2014-2019 | 2020-2026 |
|---|---:|---:|
| Unika instrument | 290 | 420 |
| Joinbara mot baseline | 105 | 107 |
| **Coverage** | **36,2 %** | **25,5 %** |
| Unresolved identity | 178 | ej mätbart (prisdata börjar 2020) |
| Terminala/avnoterade | — | **22 av 68 = 32,4 %** |

Tak om identitetsbryggan fanns: **~97 %** i det tidiga fönstret.

---

## STEG 10 — PIT LEAKAGE AUDIT: **PASS**

| # | Krav | Utfall |
|---:|---|---|
| 1 | ingen `publication_date > panel_date` | PASS_BY_CONSTRUCTION — ingen serie byggd; baseline 2013-04-25 föregår varje panel |
| 2 | ingen förändring före `effective_date` | PASS_BY_CONSTRUCTION — publicering 14 dagar före ikraftträdande |
| 3 | framtida avnotering aldrig som feature | **PASS** — `terminal_events` lästes enbart för att räkna hur många avnoterade som finns i rostern |
| 4 | Avanza `market_list` aldrig använd | **PASS** — endast `expected_isin` och terminal-flaggan lästes |
| 5 | `sweden_universe.csv` / `CAP_TIER_MAP` aldrig använd | **PASS** — ej läst |
| 6 | ingen 2026-etikett bakåtprojicerad | **PASS** — endast två daterade förstapartskällor |
| 7 | ingen market-cap-proxy för att fylla luckor | **PASS** — 178 står som UNRESOLVED, inget fylldes |

Fail closed. Kontroll 1 och 2 är `PASS_BY_CONSTRUCTION` och får inte tolkas som
att en serie har validerats.

---

## STEG 11 — SLUTDOM

### **PIT_SIZE_FOUNDATION_PARTIAL**

Legitim PIT-information finns — och betydligt mer än före detta uppdrag — men
coverage och provenance räcker inte för forskningsbruk.

**Vad som nu är etablerat och som inte var det innan:**

1. En **förstaparts, daterad, fullständig baseline roster** existerar, är hämtad,
   hashad, parsad och innehåller avnoterade bolag. 84/75/131 XSTO-instrument.
2. Change-ledgerns semantik är **avgjord ur källan**: byten, inte roster, med
   verifierad 14-dagars publiceringsmarginal.
3. BIOT-tidslinjen är **bekräftad** med två av tre punkter förstahandsverifierade.
4. Två oberoende förstapartskällor är **ömsesidigt konsistenta** för fyra bolag.

**Tre kvarvarande blockerare, i prioritetsordning:**

| # | Blockerare | Vad som krävs |
|---:|---|---|
| **1** | **Identitetsbryggan** — ISIN ej tidsinvariant, 61,4 % ojoinbara | tidsberoende ISIN-historik per instrument (`valid_from`/`valid_to`) |
| **2** | **Post-baseline-entranter** — reviews täcker bara byten | admission notices med segment vid upptagande, ~300 dokument |
| **3** | **7 av 13 årgångar saknas, 0 har lokal RAW** | hämta och spara som RAW med SHA256 |

Blockerare 1 är den avgörande. Utan den är baselinens värde begränsat till drygt en
tredjedel av universumet, och de övriga två blockerarna kan inte ens mätas korrekt.

---

```
REPOSITORY INTEGRITY:          PASS
NASDAQ REVIEW COVERAGE:        6 av 13 årgångar har känd URL · 7 saknas helt
                               · 1 förstaparts verifierad · 0 lokal RAW
BASELINE ROSTER:               HITTAD OCH VERIFIERAD — OPL Nordic List 2013-04-25,
                               förstaparts, fullständig, 290 XSTO (84/75/131),
                               SHA256 f2608a6f…, avnoterade representerade
CHANGE-LEDGER COMPLETENESS:    COMPLETE_CHANGE_EVIDENCE_PER_VINTAGE_BUT_NO_ROSTER
                               (verbatim källbelagd), täcker inte nyintroduktioner
PIT SIZE FOUNDATION:           PIT_SIZE_FOUNDATION_PARTIAL
2014-2019 PANEL COVERAGE:      36,2 % (105/290) — tak, ej rekonstruerad serie
2020-2026 PANEL COVERAGE:      25,5 % (107/420) — tak, ej rekonstruerad serie
TERMINAL/DELISTED COVERAGE:    32,4 % (22/68) — källan är EJ survivorship-filtrerad
PIT LEAKAGE:                   0 (PASS, 7 av 7 kontroller)
SIZE RESEARCH PREREGISTERED:   NO
SIZE TESTS EXECUTED:           0
TREE RESEARCH LICENSED TO RUN: NO
```

Forskningsregistret har **inte** uppdaterats till att licensiera size-forskning.
Eftersom domen är `PARTIAL` och inte `VALID` föreslås **inget**
preregistreringssteg.
