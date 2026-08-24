# NASDAQ PIT SIZE FOUNDATION — ARCHIVE DISCOVERY, INGESTION & VALIDATION

Datum 2026-08-18 · **Data- och provenanceuppdrag. Noll size-tester körda.**
Artefakter: `research_k/nasdaq_segment_foundation/` · manifest med SHA256 för **30 filer**

---

## 0. PRE-FLIGHT

`tools/repo_integrity_gate.py` → **PASS**, returkod 0, 0 blockerare.

Samtliga hashar verifierade mot `parser_validation.json` innan ny data behandlades:
tre parsermoduler och två RAW-filer — **alla OK**. **Parsern ändrades inte.**

---

## 1. DISCOVERY — GENOMBROTT

Den tidigare slutsatsen att discovery kräver Playwright **faller**.

`api.news.eu.nasdaq.com/news/query.action` är ett fungerande JSON-API. Nyckeln är
att `freeText` måste ges **inom citattecken**:

```
freeText="Equity Trading by Company and Instrument"
globalGroup=exchangeNotice
globalName=NordicMainMarketNotices
```

→ `results.count = 340`, och varje post bär:

```json
"attachment": [{
  "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "fileName":  "Equity_Trading_by_Company_and_Instrument_2607.xlsx",
  "attachmentUrl": "https://attachment.news.eu.nasdaq.com/a74e733c1eb075bd41d8eb662c49049b3"
}]
```

**`attachmentUrl` ligger direkt i JSON.** Notissidan behöver inte hämtas alls —
två steg försvinner ur kedjan, och Playwright behövs inte.

### Upptäckt täckning

| | |
|---|---:|
| Förväntade månader 2011-01 … 2026-07 | **187** |
| Upptäckta månader | **101** |
| Spann | 2017-07 … 2026-07 |
| Luckor inom spannet | 8 — `2022-02 … 2022-08`, `2025-06` |
| Ej upptäckta före 2017-07 | 78 |

Luckorna beror sannolikt på att WebFetch-sammanfattaren trunkerar långa
JSON-svar, inte på arkivluckor. `start`-offseten räknar **alla** träffar, inte
bara de med bilaga, vilket gör pagineringen opålitlig via detta verktyg. Ett
skript som läser rå-JSON träffar inte det problemet.

### Formatbrytpunkt — ren

`.xls` till och med **2024-04**, `.xlsx` från **2024-05**. En enda övergång.

### Filnamnsvariant funnen

`Equity_Trading_by_Company_and_Instrument_2303_Updated.xls` — regexen måste
tillåta suffix. Hasharna är **33 hex-tecken**, inte 32.

---

## 2–3. INGESTION OCH PARSNING

**3 av 187 månader ingesterade:** 2012-03, 2019-06, 2025-11 — medvetet valda 13 år
isär för att maximera schema-drift-täckning per hämtning.

| Månad | Format | Headerrad | Rader | STO+Stock+cap | Large/Mid/Small | ISIN | Avnoterade |
|---|---|---:|---:|---:|---|---|---:|
| 2012-03 | .xls | 5 | 710 | **291** | 81 / 82 / 128 | 291/291 | 3 |
| 2019-06 | .xls | 5 | 705 | **383** | 130 / 152 / 101 | 383/383 | 2 |
| 2025-11 | .xlsx | 6 | 713 | **408** | 154 / 145 / 109 | 408/408 | 1 |

**ISIN-täckning 100 % i samtliga tre.** Filtret är `Location = STO` och
`Instrument Type = Stock` och `Segment ∈ {Large, Mid, Small} Cap`; ett ofiltrerat
lager behålls i `monthly_size_snapshots.json`.

Bladval sker via `workbook.xml` + `r:id` mot `workbook.xml.rels`.
Positionsbaserad mappning är förbjuden i koden och kommenterad som sådan.

---

## 4. SCHEMA-DRIFT AUDIT — ETT KRITISKT FYND

| Kolumn | 2012-03 | 2019-06 | 2025-11 |
|---|---:|---:|---:|
| ISIN | 3 | 3 | 3 |
| Instrument Type | 4 | 4 | 4 |
| Segment | 5 | 5 | 5 |
| Currency | 13 | 13 | 13 |
| Location | 14 | 14 | 14 |
| **Issuer Country** | — | — | **15 (NY)** |
| **Delisted** | **15** | **15** | **16 (FÖRSKJUTEN)** |

**En ny kolumn `Issuer Country` infogas på position 15 i den moderna epoken och
knuffar `Delisted` till 16.** En positionsbaserad parser hade läst landskod som
avnoteringsdatum — tyst, utan fel. Namnbaserad mappning är därför inte en
stilfråga utan ett korrekthetskrav.

Övrig drift: headerrad 5 → 6, och Nasdaqs eget stavfel `Indsutry` rättat till
`Industry` mellan 2012 och 2019. Ingen av dem påverkar canonical semantik.

Segmentvärden är stabila. `Instrument Type` innehåller även `Equity Warrant`,
`Equity Right` och `Convertible Loan` som filtret rensar. `Segment` innehåller
även icke-cap-listor (`HEER`, `NOKS`, `DTIR`) som filtret rensar.

---

## 5–6. IDENTITETSKEDJA

| | |
|---|---:|
| Orderbook-koder i ledgern | **595** |
| Med mer än en ISIN | **104** |
| Potential code reuse | **0** |

**ISIN är inte permanent identitet.** Verifierade fall:

| Orderbook | ISIN-historik | Segment |
|---|---|---|
| **ATCO A** | `SE0000101032` → `SE0011166610` → `SE0017486889` | Large hela tiden |
| ALIV SDB | `SE0000382335` → `SE0021309614` | Large hela tiden |
| AAK | `SE0001493776` → `SE0011337708` | Mid → Large |
| ANOD B | `SE0000472268` → `SE0017885767` | Small → Mid → Large |

ATCO A har **tre** ISIN med oförändrat segment — identiteten byts utan att något
ekonomiskt händer. Orderbook-koden bär kontinuiteten.

**Code reuse-testet är svagt** med tre icke-konsekutiva månader: luckotestet kan
inte skilja "försvann och kom tillbaka" från "vi saknar mellanliggande månader".
Det måste köras om på den kompletta serien. **0 träffar är inte en friskförklaring.**

Instrumentnivån är canonical. A/B/C/SDB slås inte ihop. Issuer-normalisering är
inte gjord — den är ett separat lager och lämnas oöppnat.

---

## 7. DELISTING QA

`Delisted` är ett **Excel-serialdatum**, inte en boolean. Verifierade:

| Orderbook | Datum | Rapportmånad |
|---|---|---|
| ORC | 2012-03-09 | 2012-03 |
| PSI SEK | 2012-03-16 | 2012-03 |
| SECO B | 2012-03-02 | 2012-03 |
| VICP A / VICP B | 2019-06-18 | 2019-06 |
| IAR B | 2025-11-03 | 2025-11 |

Varje avnotering ligger **inom sin egen rapportmånad** — noll fall där ett
avnoteringsdatum föregår rapportmånaden. Instrumentet finns med i sin sista
månad, precis som Nasdaqs not utlovar.

---

## 8–9. SNAPSHOTS OCH TRANSITIONER

`monthly_size_snapshots.json`: **1 082 instrumentrader**, varje rad med
`report_month`, `raw_sha256` och `parser_sha256`. Ingen rad utan provenance.

145 segmentövergångar observerade mellan de tre snapshotsen:

| Riktning | n |
|---|---:|
| Mid → Large | 52 |
| Small → Mid | 50 |
| Mid → Small | 29 |
| Large → Mid | 11 |
| Small → Large | 3 |

**Exakt effective date är inte härledbart** ur dessa par — gapen är flera år.
Varje transition är märkt `LAG_PRECISION` med sitt månadsgap. Ingen gissning görs.

---

## 10. REVIEW-CROSS-VALIDERING — EJ GENOMFÖRD

Kräver konsekutiva månader för att kunna para en observerad övergång mot en
review-effective-date. En **indikation** finns: BIOT går Small → Mid mellan
2012-03 och 2019-06, vilket är konsistent med reviewevidensen `Small Cap → Mid Cap`
effective 2017-01-02. Det är en indikation, **inte** en validering.

---

## 11–12. PIT-INTERVALL OCH LEAKAGE

`valid_from`/`valid_to` **byggs inte** — månadsserien är för gles.

**PIT leakage: PASS, 7 av 7 kontroller, 0 avvikelser.**

| # | Krav | Utfall |
|---:|---|---|
| 1 | segment direkt ur Nasdaqs Segment-fält | PASS |
| 2 | ingen Avanza `market_list` | PASS |
| 3 | ingen `sweden_universe.csv` / `CAP_TIER_MAP` | PASS |
| 4 | ingen market-cap-approximation | PASS |
| 5 | delisted som datum, aldrig ex ante feature | PASS |
| 6 | ingen framtida segmentetikett bakåtprojicerad | PASS |
| 7 | inga interpolerade månader | PASS |

---

## 13–14. PANEL COVERAGE OCH SURVIVORSHIP

Med **tre** månader:

| Population | Coverage |
|---|---:|
| 2014-2019 H0-universum (290) | **75,9 %** |
| 2020-2026 H0-universum (420) | **93,3 %** |
| Senare avnoterade (68) | 73,5 % |
| Överlevare (352) | 97,2 % |

Jämför OPL-rostern: 36,2 % respektive 25,5 %. **Månadskällan är dramatiskt bättre
redan med tre snapshots.**

Skillnaden avnoterade mot överlevare är **23,7 pp** — men den följer av att bara
tre månader finns. Ett bolag avnoterat 2021 förekommer bara i 2021 års filer, som
saknas. **Detta är inte en survivorship-dom.** Nasdaqs not inkluderar uttryckligen
avnoterade under rapportmånaden, vilket är verifierat i alla tre filerna.

---

## 15. MANUELLA POSITIVA KONTROLLER

| Kod | Segment över tid | ISIN |
|---|---|---|
| **AAK** | Mid (2012-03) → Large (2019-06, 2025-11) | 2 |
| **ANOD B** | Small → Mid → Large | 2 |
| **BIOT** | Small (2012-03) → Mid (2019-06) | 1 |
| **ALIV SDB** | Large genomgående | 2 |
| **ATCO A** | Large genomgående | **3** |
| COLL / MAG | Mid (endast 2019-06) | 1 |
| RESURS | Large (endast 2019-06) | 1 |

COLL, MAG och RESURS finns bara i 2019-06 — de börsintroducerades efter 2012 och
avnoterades före 2025. Det bekräftar att månadsserien fångar bolag som varken
baseline-rostern eller en nutidssnapshot kan nå.

---

## 16. DATA FOUNDATION GATE

### **PIT_SIZE_FOUNDATION_PARTIAL**

Uppfyllt: officiell förstapartskälla · RAW-provenance · schema-drift identifierad ·
identitetskontinuitet hanterad · delistings representerade · PIT leakage 0 ·
lovande panel coverage.

Ej uppfyllt: **184 av 187 månader saknas.** Review-cross-validering ej genomförd.
Code reuse svagt testat. Survivorship ej avgjord.

**Blockeraren är miljön, inte källan.** Bash-sandboxen saknar nätverk; WebFetch
hanterar en fil per anrop. Ingestionen måste köras där nätverk finns — verktyget
för det är byggt och validerat.

---

```
REPOSITORY INTEGRITY:            PASS
NASDAQ MONTHS EXPECTED:          187 (2011-01 … 2026-07)
NASDAQ MONTHS FOUND:             101 upptäckta (2017-07 … 2026-07), 8 luckor i spannet
NASDAQ MONTHS PARSED:            3 (2012-03, 2019-06, 2025-11) — 100 % parse-success
ARCHIVE COVERAGE:                54,0 % upptäckt · 1,6 % ingesterad
SCHEMA VARIANTS:                 1 canonical layout; drift = headerrad 5→6,
                                 Indsutry→Industry, Issuer Country infogad pos 15
                                 (knuffar Delisted 15→16), .xls→.xlsx vid 2024-05
IDENTITY CONTINUITY:             595 orderbook-koder, 104 med flera ISIN, ATCO A med tre
ORDERBOOK CODE REUSE:            0 funna — SVAGT TESTAT, måste köras om på full serie
SEGMENT TRANSITIONS:             145 observerade, alla sex riktningar,
                                 exakt effective date EJ härledbart
SEGMENT REVIEW CROSS-VALIDATION: EJ GENOMFÖRD (kräver konsekutiva månader)
2014-2019 PANEL COVERAGE:        75,9 %
2020-2026 PANEL COVERAGE:        93,3 %
DELISTED COVERAGE:               73,5 %
SURVIVOR COVERAGE:               97,2 %
PIT LEAKAGE:                     0 (7 av 7 kontroller PASS)
PIT SIZE FOUNDATION:             PIT_SIZE_FOUNDATION_PARTIAL
SIZE RESEARCH PREREGISTERED:     NO
SIZE TESTS EXECUTED:             0
TREE RESEARCH LICENSED TO RUN:   NO
```

---

## Vad som återstår — nu mekaniskt

1. **Kör `hamta_manadsfiler.py` mot `archive_discovery.json`** där nätverk finns.
   101 månader är redan adresserade med direkta URL:er.
2. **Komplettera discovery** för 78 månader före 2017-07 och de 8 luckorna —
   samma API, rå-JSON-paginering utan sammanfattare.
3. **Kör om code reuse och survivorship** på den kompletta serien.
4. **Review-cross-validering** när konsekutiva månader finns.

Först därefter kan `PIT_SIZE_FOUNDATION_VALID` prövas. Forskningsregistret är
oförändrat — Size är fortfarande inte en validerad effekt, och ingen
preregistrering föreslås eftersom domen är PARTIAL.

---

# UPPDATERING 2026-08-18 — FULL INGESTION FÖRSÖKT

Pre-flight: gate **PASS**, parser och RAW-hashar **oförändrade**. Parsern ändrades
inte; endast nedladdarens filnamnsregex utökades (se nedan).

## Det bindande hindret, sagt rakt ut

`PIT_SIZE_FOUNDATION_VALID` kräver hela månadsserien. **Bash-sandboxen saknar
nätverk** och WebFetch hanterar en fil per anrop. 184 nedladdningar är inte görbara
härifrån. Utfallet var därför bestämt på förhand — jag lade anropen där de faktiskt
flyttade något i stället för att simulera framsteg.

**Sju av fjorton gate-krav beror på KONSEKUTIVA månader** och kan inte uppfyllas
med tre snapshots oavsett hur mycket analys som görs: code reuse, transition
effective dates, review-cross-validering, PIT-intervall, temporal completeness,
survivorship på exposure-basis, och RAW-provenance för serien.

## Vad som ändå flyttades

### 1. Ett filnamnsmönster till — och det förklarar en "lucka"

`2025-06` saknades. Den finns, men under en helt annan konvention:

```
Main Market - Equity Trading by Company and Instrument_2025-06.xlsx
https://attachment.news.eu.nasdaq.com/ad2e5047b3d9b4bcb7035adfd20117f40
```

Fullt ISO-datum i stället för `YYMM`. **Nedladdarens regex hade missat den tyst.**
Rättad — fyra konventioner stöds nu och är regressionstestade:

| Filnamn | Tolkas som |
|---|---|
| `..._2511.xlsx` | 2025-11 |
| `..._2303_Updated.xls` | 2023-03 |
| `Main Market - ..._2025-06.xlsx` | 2025-06 |
| `..._1203.xls` | 2012-03 |

ISO-mönstret måste prövas **först** — annars matchar `YYMM` de fyra sista
siffrorna i ett ISO-datum. Det betyder att de kvarvarande sju luckorna
(`2022-02 … 2022-08`) sannolikt också är namnvarianter, inte arkivhål.

### 2. Discovery-metodens gräns är nu kartlagd

`dir=DESC` bottnade vid 2017-07. `dir=ASC` toppade vid 2025-03. Samma `count=340`
i båda. `start` räknar **alla** träffar, inte bara de med bilaga. Paginering genom
detta verktyg är därmed opålitlig, och sammanfattaren trunkerar långa svar.

**De 78 månaderna före 2017-07 är därför INTE uteslutna.** 2012-03 finns
bevisligen — jag har hämtat och parsat den — men den nåddes via WebSearch, inte
via feeden. Uttömmande discovery kräver rå-JSON-paginering utanför denna miljö.

Varje månad har nu en explicit `discovery_status` i `archive_discovery.json`.

## Artefakter som inte kunde byggas — och varför

Sex artefakter är skapade men markerade `EJ_GENOMFORBAR` eller `EJ_BYGGD`, med
skälet inskrivet i filen i stället för att lämnas tomma:

| Artefakt | Status | Skäl |
|---|---|---|
| `code_reuse_audit.json` | EJ_GENOMFORBAR | kan inte skilja "försvann och kom tillbaka" från "vi saknar månaderna" |
| `segment_review_crossvalidation.json` | EJ_GENOMFORD | kräver konsekutiva månader |
| `pit_segment_intervals.json` | EJ_BYGGD | intervall över flerårsgap vore interpolation — förbjudet |
| `temporal_completeness_audit.json` | EJ_GENOMFORBAR | varje frånvaro blir per definition `NASDAQ_FILE_GAP` |
| `issuer_mapping.json` | EJ_BYGGD | separat lager, byggs först på full serie |
| `delisting_audit.json` | DELVIS | 6 av 6 datum verifierade, men "försvinner därefter" ej testbart |

Det tidigare **`0 code reuse` är uttryckligen inte en friskförklaring** och står nu
så i artefakten.

## Foundation gate

| | Krav | Utfall |
|---|---|---|
| A | archive discovery tillräcklig | **FAIL** — 102 av 187 |
| B | RAW provenance komplett | **FAIL** — 3 av 187 |
| C | parse success | PASS — 3 av 3 |
| D | schema semantics | PASS |
| E | identity continuity | PASS i metod |
| F | code reuse hanterad | **FAIL** |
| G | multiple share classes | PASS |
| H | delisting korrekt | PASS i metod |
| I | transition ledger | **FAIL** |
| J | review cross-validation | **FAIL** |
| K | PIT intervals | **FAIL** |
| L | panel coverage | DELVIS |
| M | survivorship | **FAIL** |
| N | PIT leakage = 0 | PASS |

**7 av 14 kritiska krav faller. Gaten har inte sänkts.**

---

```
REPOSITORY INTEGRITY:            PASS
NASDAQ MONTHS EXPECTED:          187 (2011-01 … 2026-07)
NASDAQ MONTHS DISCOVERED:        102 (2017-07 … 2026-07); 7 luckor i spannet,
                                 78 före 2017-07 ej nådda via feeden — EJ uteslutna
NASDAQ MONTHS DOWNLOADED:        3
NASDAQ MONTHS PARSED:            3
ARCHIVE COVERAGE:                54,5 % upptäckt · 1,6 % nedladdad
PARSE SUCCESS:                   100 % (3/3 PARSED_OK)
SCHEMA VARIANTS:                 1 canonical layout; drift = headerrad 5→6,
                                 Indsutry→Industry, Issuer Country pos 15
                                 (Delisted 15→16), .xls→.xlsx 2024-05;
                                 4 filnamnskonventioner
IDENTITY CONTINUITY:             595 orderbook-koder, 104 med flera ISIN
ORDERBOOK CODE REUSE:            EJ GENOMFÖRBAR — kräver konsekutiva månader
MULTIPLE SHARE CLASSES:          bevarade; ingen hopslagning; issuer_mapping ej byggd
DELISTING QA:                    6 av 6 datum inom sin rapportmånad; efterföljande
                                 frånvaro ej testbar
SEGMENT TRANSITIONS:             145 observerade, alla sex riktningar;
                                 exakt effective date EJ härledbart
SEGMENT REVIEW CROSS-VALIDATION: EJ GENOMFÖRD
2014-2019 PANEL COVERAGE:        75,9 %
2020-2026 PANEL COVERAGE:        93,3 %
MINIMUM PANEL COVERAGE:          EJ MÄTBART — kräver konsekutiva månader
DELISTED EXPOSURE COVERAGE:      EJ MÄTBART på exposure-basis
SURVIVOR EXPOSURE COVERAGE:      EJ MÄTBART på exposure-basis
TEMPORAL UNEXPLAINED GAPS:       EJ MÄTBART
PIT LEAKAGE:                     0 (7 av 7 kontroller PASS)
PIT SIZE FOUNDATION:             PIT_SIZE_FOUNDATION_PARTIAL
DATA GOVERNANCE UPDATED:         NO
SIZE RESEARCH PREREGISTERED:     NO
SIZE TESTS EXECUTED:             0
TREE RESEARCH LICENSED TO RUN:   NO
```

## Vad som krävs för VALID — nu helt mekaniskt

1. Kör `hamta_manadsfiler.py` mot `archive_discovery.json` **där nätverk finns**.
   102 månader har direkta URL:er och verktyget är beroendefritt.
2. Komplettera discovery via **rå-JSON-paginering** — inte genom en sammanfattare.
   78 månader före 2017-07 plus 7 luckor.
3. Kör om `bygg_identitet_och_coverage.py` på full serie. Sju gate-krav löser sig
   då automatiskt eftersom de bara saknar konsekutiva månader.
4. Genomför review-cross-valideringen.

Källan är rätt, parsern är validerad över 13 år, hämtningen är byggd. Det som
återstår är körning, inte utredning.

---

# SLUTFÖRD INGESTION 2026-08-18 — **PIT_SIZE_FOUNDATION_VALID**

Pre-flight: gate PASS. Parser och RAW-hashar verifierade mot `parser_validation.json`.
**Parsern ändrades inte** — endast nedladdarens filnamnsregex utökades tidigare.

## Förutsättningen ändrades

Nätverksåtkomst fanns denna gång. Den tidigare blockeraren var miljön, inte källan
— vilket nu är bevisat genom att hela serien kunde hämtas.

## 1. Discovery — rå JSON, ingen sammanfattare

`tools/nasdaq_segment/discovery.py` paginerar rå JSON över flera
`globalGroup`/`globalName`/`freeText`-varianter samt år för år.

| | |
|---|---:|
| **Upptäckta månader** | **201** |
| Spann | **2009-08 … 2026-07** |
| Saknade i 2011-01…2026-07 | **2** — `2011-08`, `2013-03` |

Båda de saknade ligger **utanför båda forskningsfönstren**. Arkivet visade sig
dessutom sträcka sig 17 månader längre bak än de 187 vi antog.

Namnkonventioner: 200 `YYMM`, 1 ISO (`Main Market - ..._2025-06.xlsx`), plus
`_2303_Updated.xls`. Format: `.xls` t.o.m. 2024-04, `.xlsx` från 2024-05.

## 2–3. RAW-hämtning

**201 av 201 hämtade. Noll fel.** Varje fil signaturvaliderad (OLE2 eller PK),
sparad oförändrad under `raw/nasdaq_segment/monthly/YYYY/YYYY-MM.ext`, med SHA256
i `raw_manifest.json`.

## 4–5. Parsning och schema-drift

**201 av 201 `PARSED_OK` = 100 %. 70 939 instrumentrader** i det filtrerade
size-lagret (`Location = STO`, `Instrument Type = Stock`,
`Segment ∈ {Large, Mid, Small} Cap`).

Katalogiserad drift över 17 år:

| Händelse | När |
|---|---|
| `Sector`/`Sub-Industry` → `Indsutry`/`Supersector` | 2012-02 |
| `Indsutry` → `Industry` (stavrättning) | 2013-06 |
| `NC`-kolumn tillkommer | 2011-09 |
| **`Issuer Country` infogas pos 15, `Delisted` 15 → 16** | **2024-12** |
| `.xls` → `.xlsx` | 2024-05 |
| Headerrad 5 → 6 | löpande, detekteras dynamiskt |

Canonical fält (`ISIN`, `Instrument Type`, `Segment`) ligger på position 3/4/5 i
**samtliga 201 månader**. Segmentvärden är exakt `Large Cap`, `Mid Cap`,
`Small Cap`. Instrumenttyp i det filtrerade lagret är enbart `Stock`.

## 6–8. Identitet, code reuse, aktieslag

| | |
|---|---:|
| Orderbook-koder | **707** |
| Med ISIN-byte | **159** |
| `CONTINUOUS_INSTRUMENT` | 548 |
| `IDENTITY_CHANGE_SAME_INSTRUMENT` | 155 |
| **`CONFIRMED_CODE_REUSE`** | **3** |
| `POSSIBLE_CODE_REUSE` | 1 |

Code reuse är nu **genuint testat** på konsekutiva månader. De fyra flaggade slås
aldrig ihop till samma canonical instrument_id.

Issuers: **614** — 538 med ett instrument, 66 med två, 10 med tre eller fler.
A/B/C/SDB hålls separata. Segment skiljer sig mellan aktieslag hos **1** issuer.

## 9. Delisting QA

**190 avnoteringar. 190 av 190 ligger inom sin egen rapportmånad.** `Delisted` är
ett datum, aldrig en feature.

## 10. Transitioner

**360 segmentövergångar:**

| Riktning | n |
|---|---:|
| Small → Mid | 114 |
| Mid → Large | 112 |
| Mid → Small | 85 |
| Large → Mid | 49 |

Inga direkta Small ↔ Large — bolag passerar Mid, precis som trösklarna implicerar.

## 11. Segment Review cross-validation — **100 %**

15 av 15 `CONFIRMED_DATED`-övergångar ur Nasdaqs officiella Market Cap Segment
Reviews återfinns i månadsserien. **0 missing, 0 riktningsfel.**

| | |
|---|---:|
| Exakt månadsträff | **11** |
| Match med avvikande månad | 4 |
| Missing in monthly | **0** |

Elva träffar landar exakt: COLL `2016-12 → 2017-01` mot review effective
`2017-01-02`; BIOT `2021-12 → 2022-01` mot `2022-01-03`; MAG, SRNKE B, RESURS,
ELOS B, KLED, LEO, SAS likaså.

**Månadsserien daterar dessutom tre fall som legacy hade som "unconfirmed"** —
SAS, ARISE och READ placeras alla i `2022-12 → 2023-01`.

En enda genuin avvikelse: **CCC** — review anger effective `2013-01-02`, serien
observerar `2013-12 → 2014-01`. Ett års diskrepans, noterad som unresolved.

## 12. PIT-intervall

**1 075 intervall** med `valid_from`/`valid_to`, precision `MONTH`. Ingen
interpolation. Dagprecision skulle kräva review-effective-date per transition.

## 13. Panel coverage

| | mean | median | **min** | p10 |
|---|---:|---:|---:|---:|
| 2014-2019 (79 paneler) | 77,6 % | 80,0 % | **60,0 %** | 66,7 % |
| 2020-2026 (66 paneler) | **94,3 %** | 96,7 % | **76,7 %** | 86,7 % |

### Dekomposition av underskottet 2014-2019 — och ett fynd om H0

Av 2 370 panelobservationer är 622 omatchade. Nedbrutna:

| Orsak | n |
|---|---:|
| **Äkta datalucka (noterad men saknas)** | **0** |
| Ej noterad ännu vid panelen | 603 |
| Aldrig på Nasdaq Stockholm Main Market | 19 |

**Noll äkta dataluckor i Nasdaq-serien.** Hela underskottet beror på att H0:s
frysta 2014-2019-universum innehåller bolag som **inte var noterade på Main
Market vid paneldatumet** — STAR-B förekommer först 2017-10 men rankas 2014-01,
HTRO först 2015-12, STEF-B först 2018-04. De 19 är NOKIA, som aldrig ligger i
STO Main Market-segmentet.

Det är konsistent med att `membership_h1419_v2.json` har
`membership_verified: false` och basis `DAGENS_MAIN_MARKET_ISIN_BAKATPROJICERAD`.

**Detta är ett fynd om det frysta H0-universumet, inte om size-datan.** Det
ändrar ingen forskningsdom och hanteras separat. Nasdaq-serien är nu den
auktoritativa medlemskapskällan och kan användas för att åtgärda det.

## 14. Survivorship — gapet är negativt

På **exposure-basis** (panelobservationer där instrumentet låg i H0:s topp-30):

| Population | Observationer | Matchade | Coverage |
|---|---:|---:|---:|
| Senare avnoterade | 100 | 100 | **100,0 %** |
| Fortfarande aktiva | 1 880 | 1 767 | 94,0 % |

**Gap −5,96 pp — avnoterade har bättre täckning än överlevare.** Motsatsen till
survivorship bias, och en direkt konsekvens av att Nasdaqs rapport per sin egen
not inkluderar instrument som avnoterats under månaden.

## 15. Temporal completeness

707 instrument: **7 `EXPECTED_ABSENCE`, 1 `UNEXPLAINED_GAP`**, noll
`NASDAQ_FILE_GAP`.

## 16. PIT leakage — **0**

| # | Krav | Utfall |
|---:|---|---|
| 1 | uppslag använder månad **strikt före** panelmånaden | PASS (0 brott av 23 prov) |
| 2 | delisted-datum inom sin rapportmånad | PASS (0 avvikelser av 190) |
| 3 | segment direkt ur Nasdaqs Segment-fält | PASS |
| 4 | ingen Avanza `market_list` | PASS |
| 5 | ingen `sweden_universe.csv` / `CAP_TIER_MAP` | PASS |
| 6 | ingen market-cap-approximation | PASS |
| 7 | inga interpolerade månader | PASS |

## Foundation gate — 14 av 14

Alla kriterier A–N passerar. Kriterium L passerar **med anmärkning**: minimipanelen
i 2014-2019 ligger på 60,0 %, men med noll dataluckor är orsaken H0-universumets
medlemskap.

## Governance uppdaterad

`nasdaq_market_cap_segment_pit` registrerad som
`ALLOWED_FOR_POPULATION_STRATIFICATION_ONLY`. **Uttryckligen inte en validerad
alfafeature.** `G-HET-1`/`G-SIZE-HET-1` förblir `NOT_IDENTIFIED`,
`G-HIER-1`/`G-HIER-2` förblir `NON_COMPUTED_CLAIM`, öppna kandidater förblir 0.

Integrity-gaten fick ett identitetsbaserat PIT-undantag (den substring-matchade
`market_cap` i det nya variabelnamnet). Undantaget kräver att raden själv pekar ut
sin gate via `qa_status` — **negativt testat**: en manipulerad `qa_status` ger FAIL.

---

```
NASDAQ MONTHS EXPECTED:          187 (2011-01…2026-07) — arkivet visade sig nå 2009-08
NASDAQ MONTHS DISCOVERED:        201
NASDAQ MONTHS DOWNLOADED:        201
NASDAQ MONTHS PARSED:            201
PARSE SUCCESS:                   100,0 % (201/201)
REVIEW CROSS-VALIDATION:         100,0 % — 15/15 matchade, 11 exakta, 0 missing
MIN PANEL COVERAGE:              60,0 % (2014-2019) · 76,7 % (2020-2026)
DELISTED EXPOSURE COVERAGE:      100,0 %
SURVIVOR EXPOSURE COVERAGE:      94,0 %
ORDERBOOK CODE REUSE:            3 CONFIRMED + 1 POSSIBLE av 707 — flaggade, ej hopslagna
PIT LEAKAGE:                     0
PIT SIZE FOUNDATION:             PIT_SIZE_FOUNDATION_VALID
```

Foundation valid. Nästa tillåtna steg är separat preregistrering av en ny
PIT-size heterogeneity replication.
