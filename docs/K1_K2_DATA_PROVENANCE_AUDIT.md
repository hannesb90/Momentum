# Spår K — K1/K2 data- och provenanceaudit

Datum: 2026-08-09  
Scope: endast data/provenance. Ingen target, IC, alpha eller backtest har lästs eller körts. H0/H1/H2 och frysta V2-artefakter är oförändrade.

Maskinläsbar audit: `research_k/data_audit_k1_k2/audit.json`. Per-instrumentklassning: `research_k/data_audit_k1_k2/k1_instrument_classification.json`.

## Slutsats

K1 är **fortsatt blockerad för historiska V2-test**. V1 innehåller användbar sektorinformation, men den består av aktuella snapshots från juni–augusti 2026. De tre Börsdata-snapshotsen ger samstämmig `sectorId`/`branchId` för samtliga 352 nuvarande instrument, men inget av de 68 terminalinstrumenten. V2-panelens sista datum är 2026-07-10, före den tidigaste verifierbara Börsdata-snapshoten 2026-07-27. Därför kan exakt **0 instrumentperioder och 0 panelrader** sektorbestämmas vid beslutstid utan bakåtantagande.

K2:s tidigare blockering var materiellt motiverad, men behöver preciseras. V2 har mycket god numerisk täckning för `number_Of_Shares`, resultat, FCF, omsättning, eget kapital och nettoskuld bland överlevande bolag. Det som saknas är inte främst fundamentatalet utan en verifierad historisk market-cap-nämnare. `number_Of_Shares` är ett rapportperiodfält som nästan exakt reproducerar rapporterad EPS; API-schemat anger inte att det är utestående aktier vid paneldatum. Det saknar effektiva datum för emissioner/återköp/splittar. Varken rå close eller totalavkastningsjusterad close kan därför paras med fältet utan separat basis-QA. Exakt PIT-market cap och samtliga efterfrågade price/value-yields är fortsatt blockerade. En uttryckligt benämnd proxy kan byggas senare, men får inte kallas historiskt market cap.

## K1 — vad V1 faktiskt innehåller

### Identifierade issuer-mappingar

| Källa | Evidensdatum | Identitet | Granularitet | V2 coverage | Terminal | Historik |
|---|---:|---|---|---:|---:|---|
| `momentum_ml/cache/borsdata/instruments_all.json` | fil 2026-07-27 | ISIN/insId | `sectorId`, `branchId` | 352/420 | 0/68 | snapshot |
| `momentum_ml/cache/borsdata/instruments_all_refresh.json` | fil 2026-08-02 | ISIN/insId | `sectorId`, `branchId` | 352/420 | 0/68 | snapshot |
| `docs/probes/instruments_live.json` | J2A 2026-08-09 | ISIN/insId | `sectorId`, `branchId` | 352/420 | 0/68 | snapshot |
| `momentum_ml/cache/avanza_sectors.csv` | extraktor verifierad 2026-07-18; fil 2026-07-27 | ticker | fine/mid/broad | 342 tickerträffar | 0 | snapshot, skrivs över per ticker |
| `momentum_ml/data/sweden_universe.csv` | git 2026-06-26–2026-07-15 | ticker | bred sektor | 374 tickerträffar | 27 | current/non-delisted FinanceDatabase-universum |

SHA256, bytes, mtime och fulla paths finns i den maskinläsbara auditen. Exportkopiorna från 2026-08-02 är byte-identiska backups, inte oberoende äldre snapshots.

Git-historiken för `sweden_universe.csv` börjar 2026-06-26. Senare commits lägger till eller tar bort instrument; ingen version innehåller effektiva sektorintervall. Börsdata-cachefilerna är inte versionshistorik i git. Ingen äldre, tidsstämplad sektor-/branschkälla med historiska `valid_from`/`valid_to` hittades i repo, legacy, cache, manifests eller exporter.

### Provenance och klassificering

`sweden_universe.csv` kommer enligt aktiv V1-kod från FinanceDatabase STO och filtrerades till icke-avnoterade svenska aktier. `avanza_sectors.csv` kommer från live-Avanza; extraktorn säger uttryckligen att ny hämtning vinner per ticker. De är användbara som cross-check av nuvarande bolag men inte som automatisk historisk identitet. Fuzzy namnmatchning användes inte.

De tre Börsdata-snapshotsen har inga sektor-/branschkonflikter för de 352 exakt mappade instrumenten. De skiljer sig endast genom tre borttagna instrument i hela nordiska katalogen, inte genom klassificeringsändringar för V2-träffarna. Per-instrumentutfall:

| Klass | Instrument | Tolkning |
|---|---:|---|
| PIT VERIFIED | 0 | ingen snapshot finns senast vid ett historiskt paneldatum |
| STABLE CLASSIFICATION SUPPORTED | 352 | samma nuvarande ID i flera snapshots 2026-07-27–2026-08-09; stöder inte bakåtfyllning |
| CURRENT ONLY | 0 | — |
| CONFLICT | 0 | — |
| UNKNOWN | 68 | samtliga terminalinstrument |

FinanceDatabase ger 27 tickerträffar bland terminalinstrumenten, men ticker utan ISIN/insId och utan giltighetsperiod accepteras inte som mapping. Det kan annars sammanblanda aktieslag, återanvänd ticker, predecessor/successor eller namnbyte.

### K1-beslut

| Hypotes | Beslut | Exakt användbar historik utan antagande |
|---|---|---:|
| Sector momentum | FORTSATT BLOCKERAD | 0 panelrader |
| Sector-relative momentum | FORTSATT BLOCKERAD | 0 panelrader |
| Sector breadth | FORTSATT BLOCKERAD | 0 panelrader |
| Industry-relative momentum (`branchId`) | FORTSATT BLOCKERAD | 0 panelrader |

Det går att preregistrera ett **framtida** test från första immutable snapshot som finns senast vid beslutstid. Klassificeringen får då hållas konstant endast till nästa observerade snapshot; ingen gissning mellan motstridiga snapshots och ingen backfill före första snapshot.

## K2 — market cap och value

### Vad V2 faktiskt har

Fryst R12 innehåller 12 269 rader för 347 instrument. `number_Of_Shares` är positivt på samtliga rader. På panelnivå finns senaste PIT-kända fundamentarad för 26 907/30 073 rader (89,47 %) och 345/420 instrument (82,14 %). Täckningen är:

| Dimension | Panelrader | Instrument | Terminalinstrument |
|---|---:|---:|---:|
| `number_Of_Shares` | 26 907 | 345 | 0 |
| vinst till aktieägare | 26 907 | 345 | 0 |
| FCF | 26 890 | 344 | 0 |
| omsättning | 26 907 | 345 | 0 |
| eget kapital | 26 907 | 345 | 0 |
| nettoskuld | 26 907 | 345 | 0 |

Rapportens staleness vid paneldatum är 0–629 dagar, median 84 dagar. Nuvarande exakt mappade instrument har prisvaluta SEK 344, DKK 4 och EUR 4. Även efter en lösning för aktieantal krävs alltså explicit valutamatchning för åtta instrument.

### Aktieantalets semantik

`profit_To_Equity_Holders / number_Of_Shares` matchar rapporterad `earnings_Per_Share` inom 1 % på 95,16 % och inom 10 % på 98,77 % av 12 263 kontrollerbara R12-rader. Enheten är därmed empiriskt miljoner aktier när rapportbeloppen är MSEK. Men identiteten visar också att fältet är rapportens EPS-denominator eller närliggande rapportperiodmått. Börsdatas OpenAPI-schema beskriver endast typen `number`, inte:

* shares outstanding kontra weighted-average shares,
* period-end kontra genomsnitt,
* basic kontra diluted,
* effective dates för emissioner, återköp eller splittar,
* om äldre rader restateras efter corporate actions.

Senaste `report_Date` gör observationen PIT-känd, men gör inte aktieantalet exakt för varje senare paneldatum.

### Pris- och splitbasis

Market cap kräver pris och utestående aktier på samma ekonomiska basis.

* `close` i OHLC-tillägget är faktiskt ojusterat marknadspris. Det kan inte säkert multipliceras med ett eventuellt retroaktivt restaterat eller periodgenomsnittligt aktieantal.
* `adjusted_close` är totalavkastningsjusterat och dess adjustment factor påverkas även av kontantutdelningar. Det är därför inte ett market-cap-pris.
* Befintlig split-QA har 190 instrument med vendorhändelser. Bara 72 instrument-år visar aktieantalsförändring i linje med faktorn medan 204 inte gör det. Den tidigare QA:n visar dessutom att vendorens faktorlista blandar rena splittar med andra justeringshändelser. Den kan därför inte utan ny eventklassificering skapa en split-only prisbasis.
* Emissioner och buybacks mellan rapportdatum saknar komplett, verifierad effective-date-kedja i fryst data.

Slutsats: `historiskt pris × senast marknadskända number_Of_Shares` är PIT-observerbart som en **latest-reported-share market-cap proxy**, men inte verifierat som historiskt market cap. Det får inte användas under det namnet eller utan separat QA/frysning.

### Value-mått

| Mått | Numerator finns PIT? | Kräver EV? | Databeslut |
|---|---|---:|---|
| Earnings yield | ja | nej | BLOCKERAD: market cap eller splitjusterad EPS/prisbasis saknas |
| FCF yield | ja | nej | BLOCKERAD: market cap |
| Sales yield | ja | nej | BLOCKERAD: market cap |
| Book-to-market | ja | nej | BLOCKERAD: market cap |
| Dividend yield | dividend/share finns | nej | BLOCKERAD: per-share/prisbasis inte verifierad |
| EBITDA/EV | EBITDA finns | ja | BLOCKERAD: market capdelen i EV |
| EV/EBITDA | EBITDA finns | ja | BLOCKERAD: market capdelen i EV |

`net_Debt` finns PIT på samma 26 907 panelrader och är den godkända nettoskuldskomponenten. EV kan därför definieras som godkänt market cap + nettoskuld när market cap väl finns; att separat gissa debt minus cash förbättrar inte läget. För banker/finansiella bolag krävs dessutom ekonomisk användbarhetsregel innan EV-multiplar kan godkännas.

### Survivorship

K2 är **NOT SURVIVORSHIP SAFE**. Ingen av de 68 terminalekonomiska enheterna har användbar R12-rad i den historiska panelmatchningen; den tidigare sammanfattningen 67/68 saknar fundamenta kvarstår på källnivå. Ett framtida matched-population-test kan vara diagnostiskt, men måste jämföra H0 och value på exakt samma fundamentapopulation och får inte beskrivas som robust universum-alpha.

### Ren väg till ett senare preregistrerbart test

Innan K2 kan öppnas behövs ett separat immutable dataextension som:

1. verifierar shares outstanding och dess effective dates, skilt från EPS-weighted-average,
2. bygger eller hämtar split-only prisbasis och bevisar dess samstämmighet med aktiebasen,
3. fångar emissioner/buybacks från deras faktiska effective/market-known dates,
4. valutakonverterar pris för DKK/EUR-instrument mot rapporternas SEK-totaler,
5. fryser market cap och därefter EV före targetkoppling,
6. preregistrerar endast coverage-matchad diagnostik med märkningen `NOT SURVIVORSHIP SAFE`.

Inga K1- eller K2-experiment har körts i denna audit.
