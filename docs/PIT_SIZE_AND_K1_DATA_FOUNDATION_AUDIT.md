# PIT SIZE DATA FOUNDATION + K1 MATERIAL VALIDATION

Datum 2026-08-18 · **Data- och valideringsuppdrag. Noll forskningstester körda.**
Pre-flight: `tools/repo_integrity_gate.py` → **PASS**, returkod 0, 0 blockerare.
Reproduktion: `tools/k1_material_validation.py` → `research_k/k1_material_validation_results.json`

---

# DEL I — VAD KAN "SIZE" BETYDA? KÄLLINVENTERING

## Prioritet 1 — historisk faktisk Nasdaq-listtillhörighet: **FINNS INTE**

| Attribut | Avanza `marketListName` | `membership_h1419_v2.json` | Skatteverket Aktiehistorik |
|---|---|---|---|
| **Source** | live REST-endpoint `/market-guide/stock/{id}` | validerat medlemskapslager | 930 arkiverade HTML-sidor |
| **Observation date** | `retrieved_at` = skrapning `AVANZA_SECTOR_RECOVERY_20260809_V2` | 2026-08-15 | 2026-08-07 |
| **Effective date** | **saknas** | — | daterade noteringar/avnoteringar |
| **valid_from / valid_to** | **finns inte** | `member_from: null`, `member_to: null` | — |
| **Availability semantics** | nuvärde vid anrop | `membership_verified: **false**`, basis `DAGENS_MAIN_MARKET_ISIN_BAKATPROJICERAD` | publikationsdaterad |
| **Survivorship risk** | hög — avnoterade saknar listing | hög — 222 av 290 bakåtprojicerade | låg för avnoteringar |
| **Look-ahead risk** | **total** — 2026-etikett på hela historiken | total för medlemskap | låg |
| **Corporate actions** | ej hanterade | ej hanterade | namnbyten daterade |
| **Delisting** | instrumentet försvinner ur källan | 24 via Skatteverket | daterade |
| **Identity mapping** | ISIN, otidsbunden | ISIN bakåtprojicerad | tidsbunden |
| **Segment-täckning** | ett värde per instrument, **inget datum** | **fältet finns inte** | **2 av 930 sidor** nämner ett cap-segment alls, som löptext |

Ingen av de tre källorna kan besvara *"vilket segment låg bolaget på vid panel
T?"*. Avanza-fältet är ett nuvärde; medlemskapsfilen har inget segmentfält och
inte ens verifierat venue-medlemskap; Skatteverket har daterade noteringshändelser
men inte segmenttillhörighet.

## Prioritet 2 — historiskt PIT market cap: **BLOCKERAT, KVANTIFIERAT**

Market cap kräver aktieantal på samma ekonomiska basis som priset.
`number_Of_Shares` finns i `validated/fundamentals/*` med `report_date`
(publikationsdatum), alltså PIT-daterbart. Men täckningen är förödande:

| Population | Instrument med `number_Of_Shares` |
|---|---:|
| Instrument totalt i fundamentalager | 347 |
| 2014-2019 universum (290) | 181 / 290 = **62,4 %** |
| — därav avnoterade | **6 / 68 = 8,8 %** |
| 2020-2026 probe-universum (420) | 346 / 420 = 82,4 % |
| — därav **terminala (68)** | **0 / 68 = 0,0 %** |

**Noll av de 68 avnoterade bolagen har aktieantal.** En market-cap-baserad
storleksklassificering skulle därför vara systematiskt frånvarande **precis för de
bolag som gick under**. Storlek skulle finnas för överlevare och saknas för
förlorare — definitionen av survivorship bias i den betingande variabeln.

Därtill: `fundamental_kpis` är `FORBIDDEN_IN_MODEL_TEST` i governanceregistret, och
K1_K2-auditen har redan fastställt att `number_Of_Shares` är ett rapportperiodfält
utan effektiva datum för emissioner, återköp och splittar.

## Prioritet 3 — proxy

Ingen prövad. En proxy får enligt uppdraget inte användas bara för att den
korrelerar med storlek, och ingen kandidat skulle ändå lösa täckningsproblemet
ovan: varje proxy byggd på pris eller fundamenta ärver samma frånvaro för
avnoterade bolag.

---

# DEL II — PIT SIZE DATA GATE

| # | Krav | Utfall |
|---|---|---|
| **A** | Size bestämbar vid varje paneldatum utan framtidsinformation | **FAIL** — ingen daterad källa existerar |
| **B** | Historiska size-förändringar representerbara | **FAIL** — ingen källa har mer än ett värde per instrument |
| **C** | Reproducerbar från källartefakter | delvis — skrapningen är hashad, men den innehåller ingen historik att reproducera |
| **D** | Inga framtida delistings/terminal events används | **FAIL i befintlig metod** — `Terminal/Avnoterad` tilldelades i samtliga paneler |
| **E** | Historiska instrument som senare försvinner utan survivorship bias | **FAIL** — 0/68 terminala har aktieantal; 6/68 i det tidiga fönstret |
| **F** | Mapping instrument↔size tidsberoende | **FAIL** — ingen tidsdimension finns |
| **G** | Coverage separat per fönster | ej tillämpligt — det finns ingen size att täcka |
| **H** | Missing förblir missing | uppfyllt genom att inget byggs |

## `PIT SIZE DATA GATE: FAIL`

**Stoppregeln är utlöst. Inget size-lager byggs.** Del IV och Del V (utom
look-ahead-mätningen) faller därmed bort, och Del VI får inte skapas eftersom den
kräver att båda datagates passerar.

### Exakt vad som saknas

1. **En daterad segmenthistorik** — Nasdaq Stockholms officiella Large/Mid/Small-
   tillhörighet per instrument och datum, med `valid_from`/`valid_to`, inklusive
   segmentbyten. En källa där inget bolag någonsin byter segment är per definition
   inte en historik.
2. **Alternativt: aktieantal PIT för avnoterade bolag** — de 68 terminala i
   2020-2026 och 62 av 68 i 2014-2019 saknar det helt. Utan dem är varje
   market-cap-baserad tiering survivorship-kontaminerad.
3. **FX-historik** om segmentgränserna ska följa Nasdaqs faktiska EUR-trösklar.

Punkt 1 är den enda vägen som inte kräver att fundamenta-förbudet lyfts.

---

# DEL III — K1 MATERIAL VALIDATION

Verifierat oberoende av frysningshashen, direkt mot
`sector_classification_intervals.json` under den dokumenterade semantiken
`valid_from <= panel_date < valid_to`.

## Fynd 1 — intervallen bär ingen historik

| | |
|---|---:|
| Poster / unika instrument | 420 / **420** |
| **Instrument med fler än ett intervall** | **0** |
| Andel med `valid_from = 2020-01-02` | **82,9 %** |
| `min valid_from` över alla 420 | **2020-01-02** |
| `identity_status` | 352 `EXACT_ISIN_MATCH`, **68 `UNRESOLVED`** |

Strukturen har en tidsdimension i **formen** men **ingen sektorhistorik i
innehållet**. Inget bolag byter någonsin sektor. `valid_from = 2020-01-02` är
prisdatans startdatum, inte ett klassificeringsdatum — 2026-sektorn är
bakåtprojicerad till fönstrets början.

De 68 med olöst identitet är exakt de 68 terminala: **varje avnoterat bolag har
oupplöst identitet.**

## Fynd 2 — noll täckning i det tidiga fönstret

Under strikt dokumenterad semantik:

| Panel | Med sektor | Orsaker |
|---|---:|---|
| 2014-01-01 | **0 / 290 = 0,0 %** | 222 `PANEL_FORE_VALID_FROM`, 68 `SAKNAS_HELT` |
| 2016-01-01 | **0 / 290 = 0,0 %** | samma |
| 2019-12-25 | **0 / 290 = 0,0 %** | samma |
| 2021-07-16 | 359 / 420 = 85,5 % | 43 före `valid_from`, 18 efter `valid_to` |
| 2023-12-01 | 358 / 420 = 85,2 % | 21 / 41 |
| 2026-07-10 | 352 / 420 = 83,8 % | 68 efter `valid_to` |

**K1 ger ingen sektor alls för 2014-2019.** Varje panel i det tidiga fönstret
ligger före det tidigaste `valid_from` som existerar.

Detta motsäger G-HIER-1:s påstådda L2-coverage *"87,1 % / 93,9 %"* — det sena
talet är rimligt (85–87 %), det tidiga är omöjligt. Ytterligare bekräftelse att
G-HIER-1 inte beräknades.

## Fynd 3 — terminalhantering är korrekt

Samtliga **68 / 68** terminala poster har `valid_to` satt till avnoteringsdatumet.
Strikt uppslag ger `dt >= valid_to → ingen sektor`. **Terminalstatus läcker
därför inte bakåt genom sektoruppslaget.** Det är korrekt konstruerat.

Reservation: det booleska fältet `terminal` i samma fil är en **odaterad ex
post-flagga** och får inte läsas som feature vid beslutstidpunkt.

## `K1 MATERIAL VALIDATION: PARTIAL`

| Aspekt | Utfall |
|---|---|
| Intervallsemantik implementerad korrekt | **JA** |
| Terminalstatus läcker ej bakåt | **JA** |
| Framtida sektor läcker bakåt | **JA — sektorn är 2026-klassificeringen bakåtprojicerad till 2020-01-02** |
| Sektorförändringar representerbara | **NEJ — 0 av 420 har mer än ett intervall** |
| Användbar 2020-2026 | **JA, 84–87 % täckning** |
| Användbar 2014-2019 | **NEJ, 0 % täckning** |

Taxonomin är **inte ändrad**. Inga materiella fel har reparerats eller
optimerats runt.

---

# DEL V — LOOK-AHEAD FRÅN DEN GAMLA 2026-METODEN

## Segmentkomponenten: **ej möjlig att kvantifiera**

Kvantifiering kräver `PIT size(panel_date)` att jämföra 2026-etiketten mot. Den
existerar inte. Att uppskatta storleken på felet vore en gissning.

## Terminalkomponenten: **exakt mätt**

Den gamla metoden tilldelade `Terminal/Avnoterad` i samtliga paneler. Mätt mot
faktiska eventdatum i `terminal_events.json` (samtliga 68 har känt datum):

| | |
|---|---:|
| Terminala instrument | 68 |
| Panelrader etiketterade **före** händelsen | **898** |
| Panelrader etiketterade efter händelsen | 1 550 |
| **Andel felaktiga** | **36,7 %** |

**898 panelrader där den gamla metoden visste att bolaget skulle avnoteras.** Det
är en exakt mätning av en komponent av look-aheaden; segmentkomponenten ligger
ovanpå och är ouppmätt.

*(`terminal_events` används här enbart som revisionsmått på historisk
kontaminering, aldrig som feature.)*

---

# DEL IV och DEL VI — GENOMFÖRS INTE

**Del IV:** inget canonical PIT-size-dataset byggs. Size Data Gate = FAIL.
Att konstruera en bekväm approximation är uttryckligen förbjudet och skulle
återskapa exakt det fel som gjorde G-HET-1 och G-SIZE-HET-1 `NOT_IDENTIFIED`.

**Del VI:** preregistreringen av `G-SIZE-PIT-1 → G-HIER-PIT-1 → G-HIER-PIT-2`
kräver att **båda** datagates passerar. Size-gaten failar, så ingen
preregistrering skapas. Stage-strukturen (1–7), stoppdjupskriterierna och
anti-tree-mining-förbuden i uppdraget är väl formulerade och bör återanvändas
ordagrant när datagrunden finns — men de får inte låsas som preregistrering nu,
eftersom Stage 1 inte kan definieras utan en PIT-size-variabel.

---

# SLUTRAPPORT

```
REPOSITORY INTEGRITY:                     PASS
K1 MATERIAL VALIDATION:                   PARTIAL
PIT SIZE DATA AVAILABLE:                  NO
PIT SIZE DATA GATE:                       FAIL
LOOK-AHEAD FROM OLD 2026 SIZE METHOD:     segment: ej möjligt att kvantifiera
                                          terminal: 898 av 2 448 panelrader (36,7 %) EXAKT MÄTT
SIZE RESEARCH PREREGISTERED:              NO
TREE RESEARCH LICENSED TO RUN:            NO
RESEARCH TESTS EXECUTED IN THIS TASK:     0
```

## Konsekvens för K1:s tillåtna användning

K1 var registrerad som `VERIFIED_TAXONOMY` med noteringen att den materiella
intervallrekonstruktionen var oprövad. Den är nu prövad. Tillåten användning
skärps:

* **2020-2026:** populationsstratifiering tillåten, 84–87 % täckning, ingen
  poängtilt. Med uttrycklig reservation att sektorn är 2026-klassificeringen
  bakåtprojicerad till 2020-01-02 och att inga sektorbyten är representerade.
* **2014-2019:** **all användning otillåten** — täckningen är 0 %.
* Fältet `terminal` i intervallfilen får aldrig läsas som feature.

## Ett datauppdrag återstår, och bara ett

En daterad segmenthistorik för Nasdaq Stockholm Large/Mid/Small med
`valid_from`/`valid_to` per instrument, inklusive faktiska segmentbyten, och med
avnoterade bolag representerade fram till sin avnotering. Utan den kan
size-hypotesen inte prövas på ett sätt där vi kan acceptera svaret — vilket var
uppdragets uttalade mål.
