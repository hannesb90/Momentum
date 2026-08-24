# Spår J — J2A full Börsdata API data-gap audit

Status: **AUDIT/PROBES SLUTFÖRDA — STOPP**  
Datum: 2026-08-09  
Target, IC, backtest eller feature engineering: **nej**  
MFN-/FI-nyinsamling: **pausad**  
H0/H1/H2 och A–H: **orörda**

## Slutsats

Börsdata innehåller betydligt mer användbar eventdata än vad tidigare V2-beslut speglade, men API:t löser inte ensamt någon av de fyra kvarvarande hypotesfamiljerna fullt survivorship-säkert.

| Familj | Slutklass | Avgörande skäl |
|---|---|---|
| Report / Attention / PEAD | **KRÄVER BÖRSDATA + MFN** | Börsdata har historiska rapportdatum och rapporttyp men bara datum, blandar historik och forwardkalender utan actual/estimated-flagga och saknar terminala insId-bryggor. MFN behövs för verklig publiceringstid, text/eventklass och terminalhistorik. |
| Dividend-gap | **DATA FORTSATT OTILLRÄCKLIG** | Dividendkalendern har endast ex-date, belopp, valuta och typ. Announcement-/decision-/AGM-/record-/payment-tid saknas. Ex-date är inte market-known time. |
| Insider-gap | **KRÄVER BÖRSDATA + FI** | Börsdata har `verificationDate`, transaktionsdatum och ekonomiska fält med mycket hög aktiv täckning, men 0/68 terminalinstrument är adresserbara via verifierad aktuell insId-brygga. FI krävs för survivorship, officiell revisionskedja och QA av tids-/typsemantik. |
| Buyback / shareholder yield | **DATA FORTSATT OTILLRÄCKLIG** | Buybackhistorik finns, men market-known/publication time och explicit issuancehistorik saknas. 8 629 negativa förändringar och 4 900 nollpriser visar att endpointen inte får tolkas som rena kontantåterköp utan vidare metadata/QA. |

Dividend-gap är alltså **inte testbart ännu**. Buyback/shareholder yield är **inte testbart ännu** som PIT-försvarbar alpha-feature.

## Probe och reproducerbarhet

35 små read-only-anrop gjordes: officiell OpenAPI, instrumentlista, fyra endpointfamiljer i dokumenterade max-50-batcher samt splitshistorik. Mottagna bytes sparades verbatim i en ny separat append-only probearea. Befintliga Börsdata RAW-filer ändrades inte.

* Probe: `trackj/j2a_borsdata_api_probe/raw/J2A_PROBE_2026-08-09T120000Z/`
* Manifest SHA256: `a33b20f4939a3030927600f9b47088bc3ffbe98decff783767f877098c88a869`
* Maskinresultat: `trackj/j2a_borsdata_api_probe/J2A_AUDIT_RESULTS.json`
* Resultat-SHA256: `2fa85cac7a6a8e930874d4f51b9af76fe505e60ffd97c010eac10da279a2efcc`
* Verifiering: `python3 tools/verify_sparj_j2a_probe.py`

API-nyckeln finns inte i manifestet. Manifestet innehåller endpoint, icke-hemliga parametrar, retrieval timestamp, HTTP-status, content type, byteantal och SHA256. Endpointfamiljerna har ingen server-side pagination; klienten använder `instList` i batchar om högst 50 enligt Swagger.

## Officiell API-inventering

Den hämtade OpenAPI-specifikationen är `Borsdata API v1.0`, version `1.0`. Relevanta faktiska paths är:

* `/v1/instruments`
* `/v1/instruments/report/calendar`
* `/v1/instruments/dividend/calendar`
* `/v1/holdings/insider`
* `/v1/holdings/buyback`
* `/v1/instruments/StockSplits`
* `/v1/instruments/reports`
* `/v1/instruments/{id}/reports`
* `/v1/instruments/{id}/reports/{reporttype}`
* `/v1/instruments/reports/metadata`
* `/v1/instruments/kpis/metadata`
* KPI- och KPI-history-paths.

Det finns **ingen** OpenAPI-path för estimates, consensus, earnings surprise, dividend announcement eller generell corporate-action-historik. Corporate actions är i praktiken splitendpointen plus dividendkalenderns ex-dates. Börsdatas officiella API-repo anger att kalender- och holdingsanropen introducerades 2023 och hänvisar till Swagger som normativ pathspecifikation. Börsdatas egen nyhet beskriver rapport- och dividendkalendrarna som både historiska och framåtblickande.

### Exakta schemas

| Endpoint | Eventfält i faktisk respons | Identitet |
|---|---|---|
| Report calendar | `releaseDate`, `reportType` | parent `insId` |
| Dividend calendar | `amountPaid`, `currencyShortName`, `distributionFrequency`, `excludingDate`, `dividendType` | parent `insId` |
| Insider | `misc`, `ownerName`, `ownerPosition`, `equityProgram`, `shares`, `price`, `amount`, `currency`, `transactionType`, `verificationDate`, `transactionDate` | parent `insId` |
| Buyback | `change`, `changeProc`, `price`, `currency`, `shares`, `sharesProc`, `date` | parent `insId` |
| Stock splits | `instrumentId`, `splitType`, `ratio`, `splitDate` | `instrumentId` |
| Instrument | `insId`, `isin`, `ticker`, `name`, `listingDate`, market/sector/branch/country och valutor | `insId` + ISIN |

Vanliga rapportobjekt har dessutom `year`, `period`, `report_Start_Date`, `report_End_Date`, `report_Date`, valuta/currency ratio och rapportfält. De har inga consensus-/estimate-/surprisefält. KPI 213–215 är KPI-metadata/aggregat och är inte en ersättning för daterade, publicerade återköps- och emissionshändelser.

## Identitet och universum

Den befintliga Börsdata-matchfilen har 421 kandidater: 352 verifierade ISIN→insId-matchningar, 69 omatchade. Den frysta prisbasen består av 420 instrument: 352 aktiva och 68 verifierade terminalinstrument; den extra omatchade koden `MQ` ingår inte i fryst `prices_validated`.

Samtliga **68/68 terminalinstrument saknar verifierad brygga till dagens `/v1/instruments`**. Därför är terminal endpointcoverage inte noll observerade events utan **0/68 adresserbara**; eventfrånvaro kan inte avgöras. Detta är ett konkret survivorshipproblem. Aktiva eventresultat får inte extrapoleras till terminalpopulationen.

Eventdata kan mappas säkert `insId → aktuell instrumentpost → ISIN` för 352 aktiva instrument. Ticker/fuzzy namn används inte. För namnbyte, aktieslagsbyte, merger, redomiciliering och återanvänd ticker krävs historisk insId/ISIN-brygga eller extern källidentitet; aktuell instrumentlista räcker inte.

## Faktisk coverage 2020–2026

Siffrorna nedan gäller de 352 verifierat mappade aktuella instrumenten. “Instrument” betyder minst ett event, inte att event borde finnas för alla bolag.

| Endpoint | Events 2020–2026 | Instrument med event | Aktiv coverage | Terminal addressability |
|---|---:|---:|---:|---:|
| Report calendar | 9 126 | 352 | 100,0 % | 0/68 |
| Dividend calendar | 3 117 | 350 | 99,4 % | 0/68 |
| Insider | 52 604 | 351 | 99,7 % | 0/68 |
| Buyback | 21 934 | 182 | 51,7 % | 0/68 |

| År | Report events / instr. | Dividend events / instr. | Insider events / instr. | Buyback events / instr. |
|---|---:|---:|---:|---:|
| 2020 | 1 158 / 294 | 361 / 292 | 6 685 / 288 | 1 111 / 56 |
| 2021 | 1 230 / 320 | 410 / 304 | 7 590 / 313 | 1 884 / 61 |
| 2022 | 1 311 / 330 | 448 / 327 | 7 998 / 318 | 3 598 / 88 |
| 2023 | 1 326 / 333 | 466 / 334 | 8 923 / 321 | 3 190 / 84 |
| 2024 | 1 337 / 336 | 464 / 336 | 8 283 / 327 | 4 778 / 106 |
| 2025 | 1 375 / 348 | 488 / 344 | 8 082 / 335 | 5 695 / 112 |
| 2026 | 1 389 / 352 | 480 / 345 | 5 043 / 316 | 1 678 / 76 |

2026-kalendersiffror inkluderar framtida/schemalagda poster. Probeuttaget innehåller 824 rapportdatum efter retrievaldagen och rapportkalendern sträcker sig till 2028. Dividendkalendern sträcker sig till 2027. De är därför inte en ren historisk actual-eventtabell.

Splitendpointen gav 269 events sedan 2020 totalt, varav 57 events och 42 instrument ligger på de 352 verifierade aktuella V2-insId:na. Den är en QA-källa för splits, inte en full corporate-action-källa.

## PIT-semantik

### Report / Attention / PEAD

`releaseDate` är datum vid `00:00:00` för samtliga 16 467 poster. Fyra uppenbara sentinelposter ligger 1899-12-30. Det finns ingen flagga för actual/estimated, ingen publiceringsklocktid och ingen revision/vintage. En konservativ regel “information tidigast efter hela kalenderdatumet, handel nästa handelsdag” kan undvika intradags-look-ahead för en datumkänd eventstudie, men den löser inte att historiska kalendervärden kan vara reviderade och den ger ingen terminalcoverage.

MFN-cachen har däremot verkliga publiceringstider och text: J0 mätte 206 565 poster, 180 857 unika item-id:n, 38 272 rapportliknande events, 378 V2-instrument och 30 terminalinstrument. Den cachen saknar dock verbatim RAW/provenance och måste hämtas om innan VALIDATED. Rekommendation: MFN är primär publiceringstidskälla; Börsdata är rapporttyp-/kalender-QA och fallback för en strikt next-day-definition. Ingen prisreaktion får kopplas innan eventlagret frysts.

### Dividend-gap

Alla 5 462 dividendposter har endast `excludingDate` som datumfält och ligger vid midnatt. `distributionFrequency` är null i 5 462/5 462 svar. Announcement date, decision date, AGM date, record date och payment date saknas. Börsdata gör därför inte utdelningsförändringen market-known vid ex-date; omklassificering är inte motiverad.

### Insider-gap

`transactionDate` är alltid datum vid midnatt. `verificationDate` har verklig klocktid för 58 890/70 819 poster och midnatt för 11 929. Börsdatas officiella insidersida beskriver skillnaden mellan transaction och reported och sortering efter reported date/time. Detta gör `verificationDate` till en plausibel market-known-kandidat, aldrig `transactionDate`.

QA-varningar:

* medianlag verification−transaction är 1 dag, range −25 till 1 518 dagar;
* 69 poster har negativ lag och måste lösas som correction/datafel före VALIDATED;
* 36 olika numeriska `transactionType` förekommer, men OpenAPI saknar kodtabell;
* `ownerPosition` saknas i 29 516 poster;
* tidssträngarna saknar explicit `Z`/offset trots `date-time`-schema; officiell UTC-semantik måste verifieras mot FI.

Börsdata kan alltså bli en stark featurekälla för aktiva instrument efter typ-/revision-QA, men får inte ersätta FI som ensam source of truth för V2-universumet.

### Buyback / shareholder yield

Alla buybackdatum är datum vid midnatt och endpointen saknar publication/verification timestamp. `change` är negativ i 8 629 poster, noll i 5 och `price` är noll i 4 900. Det kan vara ekonomiskt legitim minskning av treasury shares eller aggregeringssemantik, men visar att `change × price` inte får kallas återköpsbelopp utan en dokumenterad typ-/correction-regel.

Ingen OpenAPI-endpoint ger explicita daterade nyemissioner/issuance. Rapporter/KPI kan ge periodiska sharesmått men inte eventets market-known timing. Därför är både buyback-alpha och shareholder yield fortsatt data-/definitionsblockerade.

## Source-of-truth-matris

| Datatyp | Börsdata | MFN | FI | EODHD | Rekommenderad primärkälla | QA-källa |
|---|---|---|---|---|---|---|
| Report events | Datum + Q-typ, aktivt bred | Timestamp + text/event | – | report date svagare | MFN VALIDATED | Börsdata |
| Report publication time | Saknas, datum endast | Finns | – | saknas | MFN | Börsdata next-day sanity |
| PEAD-underlag | Calendar + rapportfält, ej surprise | Eventtimestamp/text | – | PIT-pris/volym | MFN event + V2/EODHD pris | Börsdata calendar |
| Dividend announcement | Saknas | Potentiellt i pressmeddelanden, ej ännu validerat | – | 22,5 % declarationDate i J0 | Ny MFN RAW/VALIDATED om klassificerbar | EODHD/Börsdata |
| Dividend ex-date | Finns | Eventuellt text | – | Finns | EODHD immutable corporate action | Börsdata |
| Insider transactions | Reported/verification + ekonomi, aktivt bred | Eventuellt press | Officiell revisionskälla | – | FI för full historik/revision; Börsdata som strukturerad challenger | Börsdata/FI kors-QA |
| Buybacks | Daterad holdingförändring, ingen known-time | Publicerade återköpsmeddelanden | Eventuella PDMR-delar | – | MFN disclosure + Börsdata economics efter QA | Börsdata |
| Share issuance | Periodiska sharesdata, ingen eventendpoint | Emissionsmeddelanden | Insider endast | splits, ej issuance | MFN + rapport/share reconciliation | Börsdata/EODHD |
| Corporate actions | Splits + dividend ex-date | Pressmeddelanden | – | Splits/dividends | EODHD för prisåtgärder; MFN för announcement | Börsdata |

## Rekommenderad nästa RAW/VALIDATED-arkitektur

1. **Börsdata event RAW:** separat append-only snapshot per endpoint/batch, exakt samma byte/provenanceformat som proben. Bevara nuvarande insId-lista och instrumentlistans bytes i samma freeze.
2. **Identity bridge:** snapshot-specifik `insId ↔ ISIN`; separat historisk terminalbrygga. Ingen automatisk ticker/fuzzy-matchning.
3. **Normalized tables:** en tabell per källa/familj. Bevara både providerfält och råfilens SHA/radlocator. Ingen featurekod eller targetimport.
4. **PIT columns:** `provider_event_time`, `market_known_time`, `time_precision`, `timezone_status`, `actual_estimated_status`, `revision_status`, `pit_approved` och explicit reason.
5. **MFN:** ny verbatim, ISIN-baserad RAW för report/dividend/buyback announcements; deduplicera först i normalized med permanent item-id.
6. **FI:** officiell, fullpaginerad RAW med revisionshistorik; använd som survivorship/source-of-truth och kors-QA av Börsdatas `verificationDate`.
7. **Freeze gates:** separat active/terminal/year coverage, unresolved identities, duplicate/correction tests, schema drift och byte-manifest innan någon feature eller target får läsas.

## Stopp

Audit/probes är klara. Ingen stor ny Börsdata-, MFN- eller FI-hämtning har gjorts, ingen feature har byggts och ingen target/backtest har lästs. Nästa rationella datasteg är MFN- och FI-RAW enligt arkitekturen ovan; dividend-gap och shareholder yield ska förbli blockerade tills verklig announcement/market-known-data finns.

## Primärkällor

* Börsdata officiell OpenAPI/Swagger: `https://apidoc.borsdata.se/swagger/index.html`
* Börsdata officiellt API-repo: `https://github.com/Borsdata-Sweden/API`
* Börsdata Calendar wiki: `https://github.com/Borsdata-Sweden/API/wiki/Calendar`
* Börsdata API holdings-nyhet: `https://borsdata.se/en/news/api-holdings`
* Börsdata insiderbeskrivning: `https://borsdata.se/en/info/holdings/insider`
