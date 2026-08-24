# Spår A: pris-QA — klassificering och behandlingsregler

Datum: 2026-08-08. **Ingen clipping, ingen automatisk korrigering, ingen modellträning.**
Verktyg: `tools/price_qa.py`, `tools/price_qa2.py`.
Artefakter: `docs/probes/price_qa_slutlig.json`, `price_qa_v1_paverkan.json`,
`skv_corporate_actions.json`, `avnoteringstyper.json`.

## 0. Omfattning

Den ursprungliga skanningen hittade 206 *serier* med minst ett nivåbrott. Fullständig
genomsökning ger **871 enskilda brott** över dessa 206 serier. Alla 871 är klassificerade.

Bevisen som samlades per brott: EODHD:s split- och utdelningsfiler (±7 dagar),
**Skatteverkets corporate action-tabell** (4 000 rader över 865 instrument, ±12 dagar),
`adjusted_close` kontra `close`, platshållar- och golvvärden, datumkluster,
avnoteringsdatum ur `instrument_master`, samt om kursen återvänder inom 10 dagar.

## 1. Klassificering av samtliga 871 brott

| klass | brott | serier | andel |
|---|---|---|---|
| leverantörs-/datafel | 571 | 64 | 65,6 % |
| legitim corporate action | 183 | 138 | 21,0 % |
| split-/justeringsproblem | 39 | 26 | 4,5 % |
| instrumentåteranvändning | 1 | 1 | 0,1 % |
| **oklassificerad** | **77** | **31** | 8,8 % |

De 77 oklassificerade ligger nästan uteslutande före 2015 och på instrument utanför det
låsta universumet (se §2). De domineras av omvända sammanläggningar utan registrerad split
hos vare sig EODHD eller Skatteverket (PA Resources, Nischer, Siem Offshore, Kopparbergs).

## 2. Vad som faktiskt påverkar dataset_v1.0

Universumet är Nasdaq Stockholm från 2020-01-01 — **429 instrument med EODHD-kod**.

| | brott |
|---|---|
| totalt i arkivet | 871 |
| på instrument i universumet | 121 |
| **på instrument i universumet OCH datum ≥ 2020-01-01** | **24** |

De 24 fördelar sig på 11 legitima corporate actions, 11 leverantörsfel (samtliga i ett enda
instrument), ett fall av instrumentåteranvändning och ett justeringsproblem.

### Den generella regeln, kvantitativt verifierad

Samma kontroll körd på `adjusted_close` i stället för `close`, för universumet 2020+:

| fält | nivåbrott | instrument |
|---|---|---|
| `close` | 24 | 13 |
| **`adjusted_close`** | **14** | **4** |

**Samtliga 11 legitima corporate actions försvinner** när `adjusted_close` används — de är
korrekt hanterade i den justerade serien. Kvar blir fyra instrument:

| instrument | datum | adjusted_close | klass |
|---|---|---|---|
| **MQ** | 2020-02-13 | 0,0019 → 17,61 | split-/justeringsproblem (även justerad serie trasig) |
| **HIQ** | 2020-11-09 | 72,10 → 0,0945 | instrumentåteranvändning |
| **ORRON** | 2022-06-23 | 406,50 → 7,30 | **annan verifierad orsak**: Lundin Energy → Orrön efter Aker BP-affären; aktieägarna fick Aker BP-aktier, vilket `adjusted_close` inte fångar |
| **FLERIE** | 11 tillfällen 2023–2024 | pendlar 0,005 ↔ 0,42 | leverantörs-/datafel |

**Hela pris-QA-blockeraren för v1.0 reduceras alltså till tre instrument plus en generell
fältregel.**

## 3. Behandlingsregler per klass

Ingen regel klipper, interpolerar eller skriver om ett värde.

| klass | behandlingsregel |
|---|---|
| **legitim corporate action** | Använd `adjusted_close` som avkastningsserie. Ingen ytterligare åtgärd. `close` behålls i RAW men får aldrig användas för avkastning. Verifierat: alla 11 fall i universumet försvinner. |
| **split-/justeringsproblem** | Instrumentet flaggas `adjustering_opålitlig` för det berörda fönstret (±10 handelsdagar). Fönstret **utesluts** ur avkastningsberäkningen — värdet skrivs inte om. Gäller MQ 2020-02-13. |
| **instrumentåteranvändning** | Serien **trunkeras vid avnoteringsdagen** ur `instrument_master`. Rader efter avnoteringen tillhör ett annat instrument och får aldrig ingå. Gäller HIQ (avnoterad 2020-11-13; alla rader efter det datumet stryks). |
| **leverantörs-/datafel** | Berörda rader **utesluts** (flaggas `pris_ogiltig`). Ingen interpolering, ingen framåtfyllning. Gäller FLERIE:s 11 tillfällen samt golv- och platshållarvärden generellt (`close` = 0,0001 respektive 1 000 000,00). |
| **annan verifierad orsak** | Kräver explicit totalavkastningsjustering eller uteslutning av händelseveckan, dokumenterat per fall. Gäller ORRON 2022-06-23 (Aker BP-utskiftningen). |
| **oklassificerad** | Behandlas som `split-/justeringsproblem`: fönstret utesluts. Ingen gissning görs. Påverkar inget instrument i v1.0. |

Två hårda regler utöver ovanstående:

- **`close` används aldrig för avkastning.** Endast `adjusted_close`.
- **Ingen generell clipping eller winsorisering av priser.** Ett värde är antingen giltigt
  eller uteslutet, och alltid med registrerad orsak.

## 4. Avnoteringstyp i instrument_master

Krav: namnbyten, redomiciliering, uppköp och verklig avnotering ska hanteras korrekt.
Samtliga 68 Nasdaq Stockholm-avnoteringar 2020–2026 är typade:

| typ | antal |
|---|---|
| avnotering utan känd efterföljare | 45 |
| uppköp/fusion (via Skatteverkets bytestabell) | 17 |
| bolagshändelse, handeln fortsatte | 3 |
| oklar, serien fortsatte | 3 |

**Sex bolag är inte bolagsdöd och får inte räknas som survivorship-händelse:**

| bolag | år | typ | serie t.o.m. |
|---|---|---|---|
| Besqab Bostadsutveckling AB | 2024 | bolagshändelse | 2026-07-24 |
| Cavotec SA | 2025 | bolagshändelse | 2026-07-24 |
| SSM Holding AB | 2021 | bolagshändelse | 2021-12-20 |
| Feelgood Svenska AB | 2021 | oklar | 2021-12-17 |
| Nordic Waterproofing Holding A/S | 2020 | oklar (redomiciliering A/S → AB) | 2025-03-24 |
| **HiQ International AB** | 2020 | oklar — **men fortsättningen är instrumentåteranvändning, inte handel** | 2021-12-20 |

`instrument_master` får därmed fältet `handelsetyp` med värdena ovan. Regel: endast
`uppköp/fusion`, `konkurs/likvidation` och `avnotering utan känd efterföljare` räknas som
survivorship-händelser. Namnbyte, redomiciliering och aktieslagsförändring gör det inte.

## 4b. Implementering i VALIDATED — reglerna behövde skärpas

Reglerna i §3 implementerades i `tools/build_validated_prices.py` med
acceptanskriteriet **noll nivåbrott i VALIDATED**. Första körningen klarade det inte,
och rättelserna är en del av resultatet:

| upptäckt vid verifiering | rättelse |
|---|---|
| HIQ:s brott ligger **fyra dagar före** det formella avnoteringsdatumet, så trunkering vid avnoteringsdagen missade det | **R2 ändrad:** trunkera vid *brottet* eller avnoteringen, det som infaller först |
| Punktvis radering av felaktiga rader skapade **nya** brott i pendlande serier (FLERIE) | **R3/R4/R5 ändrade:** hela det klassade problemspannet ±5 dagar utesluts, inte enskilda rader |
| Spann definierade av klassade brottdatum räckte inte — korruptionen sträckte sig utanför | **R7 (ny):** slutningsregel, spannet utvidgas iterativt tills noll brott återstår |
| Att kasta hela instrumentet vid utebliven konvergens skulle kasta äkta observationer | **R8 (ny):** serien **delas** vid det olösta brottet och längsta segmentet behålls; instrumentet utesluts bara om segmentet < 60 rader |

Utfall av R7/R8 (de enda tre instrument som krävde det):

| instrument | behandling | resultat |
|---|---|---|
| FLERIE | segmenterad | behåller 2020-01-02 – 2023-02-10 (787 rader) |
| ORRON | segmenterad | behåller 2022-08-09 – 2026-07-24 (994 rader); tiden dessförinnan var **Lundin Energy**, en annan ekonomisk enhet |
| **MQ** | segmenterad, segmentet 25 rader < 60 | **instrumentet uteslutet** — MQ Holdings konkurs 2020 går förlorad som observation |

**MQ-förlusten ska stå kvar synlig:** det är en av de 68 avnoteringarna i universumet, och
just konkurser är de observationer survivorship-arbetet syftade till att bevara. Den kan
återvinnas om en alternativ prisserie för MQ hittas.

## 5. Status för spår A

| krav | status |
|---|---|
| samtliga nivåbrott klassificerade individuellt | **klart** (871/871, varav 77 som "oklassificerad" med konservativ behandlingsregel) |
| explicit behandlingsregel per klass | **klart** (§3) |
| ingen generell clipping eller automatisk korrigering | **uppfyllt** |
| namnbyte/redomiciliering/uppköp/avnotering korrekt i instrument_master | **klart** (§4) |

Spår A är klart för frysning under förutsättning att reglerna i §3 implementeras i
VALIDATED-steget och att de tre instrumenten MQ, HIQ och FLERIE plus ORRON hanteras enligt
tabellen. **Frysning sker först när även spår B passerat.**
