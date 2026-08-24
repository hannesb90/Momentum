# momentum_v2 — fristående data- och forskningsplattform

Startad 2026-08-07. Målet för denna fas är **ett fristående, dokumenterat och
reproducerbart `dataset_v1.0`** som kan frysas och därefter användas som gemensam
datagrund för alla modelljämförelser.

## Hårda regler

1. **Ingen import från legacy.** V2 importerar inte kod, config, cache, features,
   paneler eller modeller från `/home/hannesb/momentum_prod_work/`. Legacy är
   LEGACY/read-only och får läsas som *referens*, aldrig som beroende.
2. **Ingen gammal endpoint eller global default följer med implicit.** Varje endpoint,
   parameter och default deklareras på nytt i v2:s endpointregister.
3. **Rådata migreras först efter verifiering** av källa, endpoint, definition,
   PIT-egenskaper och hash.
4. **RAW sparas oförändrad.** Aldrig överskrivning, aldrig transformering i RAW-lagret.
5. **Explicita steg:** RAW → VALIDATED → PIT → FEATURES. Varje steg testbart och
   reproducerbart, med egen QA-rapport.
6. **En katalog per Börsdata-endpoint/datatyp**, dokumenterad.
7. **Datadictionary, endpointregister, QA-rapporter, manifests och
   dataset-hash/versionering** hör till leveransen, inte till efterarbetet.
8. **Inga modeller, backtester eller featureoptimeringar** körs innan datalagret är
   färdiggranskat.

## Status

> **AKTUELL SLUTSTATUS 2026-08-08: REDO FÖR SPÅR D.** Se
> `docs/CODEX_FINAL_PRE_SPARD_AUDIT_2026-08-08.md`. Detta betyder att inga
> kända reparerbara blockerare återstår; det betyder inte full historisk
> membership. Membership är verifierad för 9/420 instrument och explicit okänd
> för övriga. CORE är huvudbenchmark; CORE+FUNDAMENTA är en separat challenger
> med dokumenterad fundamental survivorship (67/68 avnoterade saknar data).
> Ingen modellträning har körts.

> **HISTORISK, ERSATT STOPPSTATUS (second review 2026-08-08):** A/C var inte
> frysta eller redo för Spår D. `docs/probes/membership_pit_audit.json` visar
> minst 254 panelrader för åtta instrument före verifierat huvudlisteinträde,
> medan 343/420 panelkoder saknar komplett explicit entrysignal. Äldre rader
> nedan som säger “fryst/godkänd” är historik och har återkallats.

| fas | status |
|---|---|
| Inventering och klassificering av legacy | **klar** — `docs/INVENTERING_OCH_KLASSIFICERING.md` |
| Börsdata: kan API:t ge avnoterade instrument? | **klar — NEJ**, se `docs/UNIVERSUM_OCH_KALLBESLUT.md` steg 1 |
| Universum- och prisryggrad | **EODHD-arkivet** (active + delisted), steg 2 |
| Instrumentmappning EODHD ↔ Börsdata | **klar** — ISIN är enda giltiga nyckel, steg 3 |
| Hashverifiering av kategori 1 | **klar — underkänd**; rådatalagret omklassat till kategori 3, steg 5 |
| Historiskt universum ur Skatteverket (1 648 bolag, 634 avnoterade) | **klar** — `docs/SURVIVORSHIP_SKATTEVERKET_MOT_EODHD.md` |
| Universumreparation (instrument_master, entity resolution) | **klar** — `docs/UNIVERSUMREPARATION.md` |
| Universum verifierat bolag för bolag och **låst** | **klart** — Nasdaq Stockholm från 2020-01-01, `docs/UNIVERSUM_V1_LASNING.md` |
| **Spår A, pris-QA**: 871 nivåbrott klassificerade + behandlingsregler | **klart** — `docs/PRIS_QA_KLASSIFICERING.md` |
| **Spår A VALIDATED byggt och fryst** | **klart** — 404 instrument, 546 004 rader, 0 nivåbrott, `validated/manifest_sparA.json`, sha256 `f0182d35…` |
| **Spår B, legacy-inventering (68 avnoterade)** | **klart** — 1/68 (Besqab, redundant med Track A), 67/68 utan data. `docs/FUNDAMENTAL_QA.md §1` |
| **Spår B, Track A (V2 RAW, live Börsdata)** | **klart** — 358 instrument, 1 077 hämtningar, 0 fel, verbatim + sha256. `raw/borsdata/` |
| **Spår B, splitverifiering EPS/dividend** | **klart** — mot spår A:s EODHD-splitdata; båda uppgraderade till GODKÄND. `docs/FUNDAMENTAL_QA.md §7b` |
| **Spår B, kvartals-/R12-QA** | **klart** — 3 tabeller korsverifierade (R12@Q4 mot årsdata: 100,0 % exakt). `docs/FUNDAMENTAL_QA.md §9` |
| **Spår B, fältklassificering** | **SLUTLIG, samtliga 29 fält** — 22 GODKÄNDA, 2 UTESLUTNA, 0 kvar i KRÄVER ÅTGÄRD. `docs/FUNDAMENTAL_QA.md §10` |
| **Spår B VALIDATED (år+kvartal+R12) byggt och fryst** | **klart** — 4 847/12 280/12 269 rader, `kombinerad_sha256 9da73a883721b9cb…`, `validated/manifest_sparB.json` |
| Fundamenta för avnoterade bolag | **avgjort empiriskt, inte lösbart** — 67/68 saknar data i alla tre upplösningar; explicit varningstext krävs vid varje användning |
| `dataset_v1.0`, spår A + spår B | **BÅDA FRYSTA** — se `docs/FUNDAMENTAL_QA.md §12` för godkänt innehåll och kvarstående begränsningar |
| **Spår C, feature blueprint (68 kandidater, 12 informationsfamiljer)** | **klart** — `docs/SPAR_C_BLUEPRINT_OCH_CLOSURE.md` |
| **Spår C, target (preregistrerad, byggd separat)** | **klart** — 52v horisont/embargo, 4v rebalance, 28 539 rader (oförändrad) |
| **Spår C, feature registry (52 fält: 31 CORE + 21 FUNDAMENTA)** | **klart — SAMTLIGA GODKÄNDA, 0 KRÄVER ÅTGÄRD** |
| **Spår C, materialitetsregel** | **klart** — preregistrerad 1%-tröskel löste de 6 tidigare KRÄVER ÅTGÄRD-fälten (23–257× reduktion av extremvärden) |
| **Spår C, CORE-panel v2** | **klart, fryst, survivorship-säker** — `panels/core_panel.json`, sha256 `8515697d…` |
| **Spår C, CORE+FUNDAMENTA-panel v2** | **klart, fryst — INTE survivorship-säker för fundamenta** (67/68 avnoterade saknar data) — `panels/core_fundamenta_panel.json`, sha256 `79bbaffb…` |
| **Spår C, PIT-/läckage-QA + coverage-QA** | **klart — samtliga 6 kontroller passerade** på de utökade panelerna |
| `dataset_v1.0`, spår A + B + C | ~~SPÅR C SLUTLIGT FRYST~~ — **STATUS ÅTERKALLAD, se rad nedan** |
| **Oberoende pre-model audit (2026-08-08)** | BUGG HITTAD — `docs/PREMODEL_AUDIT_2026-08-08.md`. 7 instrument felaktigt trunkerade pga aktieslagsförväxling. Åtgärdad, se raden nedan. |
| **Spår A, reparation (2026-08-08)** | **KLAR** — `docs/UNIVERSUMREPARATION_V2.md`. 6 strukturella buggar i Skatteverket-parsningen åtgärdade med generell logik (aktieslagskonflation, byten-alias, icke-determinism, avknoppnings-/uppköpskonflation i efterföljarfallbacken, kodåteranvändningsdisambiguering) + 3 mindre parsningsfixar. Samtliga 7 kända fall + ytterligare fynd (Gambro/ABB, Gränges, AcadeMedia, Medicover m.fl.) verifierat korrekta. Spår A ombyggt från RAW: **420 instrument, 581 115 rader** (tidigare 404/546 004), sha256 `c75d3de5…`. Pris-QA omkört (`price_qa.py`+`price_qa2.py`) — identisk klassificering (871 brott: 571/183/77/39/1), stabil. **Betraktas som fryst baslinje — rörs inte utan nytt verifierat fel.** |
| **Spår B, KRITISKT valutafel funnet OCH ÅTGÄRDAT (2026-08-08)** | `docs/SPAR_B_VALUTAUTREDNING_2026-08-08.md` + `docs/SPAR_B_VALUTAFEL_REPARATION.md`. Den tidigare frysta fundamentadatan dubbelkonverterade valuta för 40 icke-SEK-bolag (AstraZeneca, ABB, Evolution, Hexagon, Nordea m.fl.) — värden uppräknade ~9–11× (EUR/USD/PLN) eller nerräknade (ISK). Rotorsak: `/reports`-endpointen levererar redan SEK-konverterade värden; byggskriptet multiplicerade en gång till. **Åtgärdat, ombyggt från RAW, full diff + QA genomförd.** Gammal data bevarad i `validated/_SUPERSEDED_2026-08-08_valutabugg/` (INTE tyst överskriven). |
| **Oberoende second-opinion audit (2026-08-08)** | `docs/CODEX_SECOND_OPINION_V2_ABC.md`. Bekräftade valutafixen (0 avvikelser). Hittade 9 ytterligare fynd (1 CRITICAL, 4 HIGH, 3 MEDIUM, 1 LOW), varav flera verifierade och åtgärdade samma dag — se raden nedan. |
| **Fynd från second-opinion-auditen — åtgärdade (2026-08-08)** | **A-2** (nullvolym→0): verifierat no-op mot aktuell data, koden städad. **B-2** (insId=147/ISIN-kollision EMPIR-B/SAFETY-B): löst generellt i `instrument_master_v2.py` (BUG-FIX 7), Spår B ombyggt. **C-2** (avnotering behandlades som vanlig höger-censurering i target): fixat med delisting-return-metodik — 893/30 370 rader (2,9 %) får nu ett beräknat, verkligt utfall istället för att blankas. **C-3** (`trend_strength_52w`/`trend_consistency_52w` beräknades på 26 veckor): fixat till korrekt 52-veckorsfönster. **C-4** (target-QA återräknade aldrig faktiska värden): utökad till fullständig oberoende återräkning av samtliga 30 370 rader — 0 fel. **Ej åtgärdat denna omgång:** V-1 (git-identitet/legacy-läsning, infrastruktur), A-1 (historiskt segmentmedlemskap, redan dokumenterad begränsning), B-3 (151 R12-rader med EPS-avvikelse, kräver radvis klassning). |
| **Spår C, ombyggd och fullt QA-godkänd (2026-08-08)** | `validated/manifest_sparC.json`. Byggd från aktuell Spår A (`c75d3de5…`, 420 instrument) och reparerad Spår B (`725b9db6…`). CORE 30 370 rader/420 instrument/31 fält, CORE+FUNDAMENTA 89,3 % `has_fundamenta`-täckning. Full QA: nyckelkonsistens, PIT (CORE stickprov + FUND samtliga rader), **target fullständigt återräknat för alla 30 370 rader (0 PIT-/värde-/typfel)** — samtliga strukturella kontroller passerade. `panels/core_panel.json` sha256 `14b44f11…`, `core_fundamenta_panel.json` sha256 `757acc41…`, `target_table.json` sha256 `492c2a5d…`. |

## Vad som INTE ligger här

Ingenting är ännu kopierat från legacy. Katalogen innehåller bara ny dokumentation.

Produktionsmodellen i legacy är **fryst** sedan 2026-08-07: ingen ytterligare tuning
eller optimering av den utförs.
