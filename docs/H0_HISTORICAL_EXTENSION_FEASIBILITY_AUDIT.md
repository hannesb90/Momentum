# H0 Historical Extension Feasibility Audit

## Beslut

**SURVIVORSHIP-BLOCKERAT** med nu tillgänglig lokal data.

Det finns gott om äldre prisrader, men inte ett tillräckligt komplett historiskt universum av avnoterade värdepapper. H0 har inte körts och inga frysta artefakter har ändrats.

## Lokal data

### EODHD Stockholm-arkivet

Det aktiva immutable RAW-arkivet innehåller 5 119 filer och passerar byte-för-byte-verifiering mot `validated/external_dependencies_manifest.json`.

| Del | Katalog | Common Stock | Med ISIN | Tidigaste EOD |
|---|---:|---:|---:|---:|
| Aktiv | 1 010 | 945 | 770 | 1987-01-02 |
| Delisted | 694 | 669 | 323 | 1990-04-03 |

EOD-filerna innehåller open/high/low/close/adjusted_close/volume. Separata split- och dividendfiler finns per kod. **422 Common Stock-serier** (261 i active-katalogen och 161 i delisted-katalogen) löper över mitten av 2010.

Detta ser först lovande ut men är missvisande: **ingen delisted-serie slutar före 2013-07-23**. Det lokala Skatteverket-registret känner samtidigt 124 avnoteringar 2010–2013, varav 115 saknar prisserie.

För Nasdaq Stockholms huvudlista är priscoverage för kända avnoteringar:

| År | Coverage |
|---|---:|
| 2010 | 3/12 |
| 2011 | 2/9 |
| 2012 | 3/6 |
| 2013 | 0/5 |
| 2014 | 4/7 |
| 2015 | 5/8 |
| 2016 | 3/7 |
| 2017 | 4/4 |
| 2018 | 6/11 |
| 2019 | 7/8 |

En 2010–2019-körning från detta arkiv skulle därför systematiskt känna till överlevarna bättre än bolagen som försvann.

### Börsdata

573 lokala `max20`-prisfiler börjar som tidigast 2006-07-31 och 199 serier löper över mitten av 2010. **Noll** serier slutar före 2020. Instrumentcachen är en nutida lista och leverantören tar bort avnoterade instrument. Börsdata kan cross-validera överlevare men kan inte skapa det äldre PIT-universumet.

### Skatteverket och legacy

Skatteverket ger värdefull evidens om notering, avnotering, namnbyte, organisationsnummer och ibland marknadsplats/sista betalt. Det är inte en komplett säkerhetsmaster eller prisdatabas och källan varnar själv för att bolag normalt inte följs efter avnotering.

Legacy/Yahoo/processed signals är forskningsutsatta, bygger huvudsakligen på nutida tickerlistor och saknar immutable RAW-/identitetsbevis. De får inte användas som prisryggrad.

## Corporate actions, identitet och terminaler

EODHD:s struktur är tekniskt användbar: både justerad/ojusterad OHLC och separata splitar finns. Men V2:s tidigare QA har hittat både korrekta splitjusteringar och EODHD-splitposter som i praktiken motsvarar andra kapitalhändelser. Hela 2008–2019-lagret behöver därför ny split-/continuity-QA; filernas existens räcker inte.

Identitet är svagast för avnoterade: endast 323/694 katalogposter har ISIN och EODHD:s symbol-change-history stöder enligt leverantören endast USA. Sverige kräver därför en separat daterad ISIN/order-book/entity-kedja från Nasdaq/FinBas/primärkällor. Ticker får aldrig ensam koppla historiska instrument.

Sista prisdatum får inte automatiskt bli terminalevent. Varje terminal måste få verifierad typ och datum; uppköp, merger/successor, konkurs och fortsatt handel på annan lista måste skiljas. För V4-ekvivalens behövs även en ekonomiskt försvarbar slutvärdering.

## Universumregel

H0 behöver inte historisk Large/Mid/Small-indexmembership om ett bättre PIT-universum kan definieras före testet:

> Alla ordinära aktier som vid T var upptagna till handel på Nasdaq Stockholm Main Market, med daterad ISIN/order-book-identitet och observerbar handel, följt av samma preregistrerade PIT-investerbarhetsregler.

Detta är ekonomiskt närmare H0 än dagens-universe-backfill och undviker att rekonstruera storlekssegment. Men EODHD-koden `ST` räcker inte som marknadsplatsbevis; arkivet blandar instrumenttyper och handelsplatser. Daterad Nasdaq-reference/listing-data krävs.

## Möjliga källor

1. **FinBas** är den starkaste identifierade kandidaten. Swedish House of Finance beskriver daglig EOD, corporate actions och fundamentals för svenska börser, MTF:er och OTC sedan 1912. Åtkomst är dock begränsad till SSE och svensk akademi via SWAMID; ingen lokal licens hittades. [FinBas](https://www.houseoffinance.se/data-center/finbas/)
2. **Nasdaq Nordic HistoricalView + historiska reference/EOD-filer** kan ge officiell venue-, ISIN-, order-book- och handelsinformation. Nasdaq uppger att äldre filer kan beställas via Market Data Sales. Detta är en kommersiell dataförfrågan och behöver kompletteras med corporate-action/adjustment-data. [HistoricalView](https://www.nasdaq.com/solutions/data/nasdaq-nordic-baltic-historicalview), [Reference Data](https://www.nasdaq.com/solutions/data/nasdaq-nordic-reference-data-files), [End of Day](https://www.nasdaq.com/solutions/data/nasdaq-nordic-end-of-day-reports)
3. **EODHD refresh/support-probe** är billigast att prova först. Leverantören dokumenterar EOD för bolag avnoterade före 2018, men rekommenderar att specifik coverage verifieras med support. Den lokala Stockholm-snapshoten motsäger fullständighetsantagandet och får inte godkännas utan att de namngivna luckorna faktiskt levereras. [EODHD delisted documentation](https://eodhd.com/financial-apis/delisted-stock-companies-data-2)
4. Nasdaqs publika list-change-arkiv hjälper från 2019 och äldre annual reports/notices kan ge enskilda listningar och avnoteringar, men är inte ensamt en komplett daglig pris- och corporate-action-källa. [Nasdaq corporate actions/list changes](https://www.nasdaq.com/european-market-activity/news/corporate-actions)

## Möjlig historikvinst

- Om immutable RAW börjar senast cirka 2008-07 kan H0 få full 18m-lookback redan 2010 och cirka **10 extra år/65 extra 8v-rebalanseringar**.
- Om källan börjar 2010 blir första fulla H0-beslut omkring mitten av 2011: cirka **8,5 år/55 rebalanseringar**.
- Lokala deldata 2014–2019 skulle teoretiskt ge cirka **39 rebalanseringar**, men är inte inferensdugliga på grund av luckorna bland avnoterade.
- Med dagens godkända krav är den försvarbara utökningen före 2020: **noll år**.

## Historisk oberoendestatus

2010–2019 är **RESEARCH EXPOSED**, inte HISTORICALLY UNSEEN. Legacy innehåller 157 Python-skript som explicit refererar till start 2010-01-01, varav 97 tuning- och 32 diagnostikskript. Exakt ren V2-H0 har inte körts på ett korrekt rekonstruerat 2010-talsuniversum, så ett framtida test är fortfarande värdefullt—men perioden får inte kallas oberoende holdback eller untouched forward.

## Krav före ett framtida låst test

1. Immutable RAW från minst cirka 2008-07.
2. Daterad Nasdaq Main Market-security master med ISIN/order-book och in-/utträden.
3. Daglig OHLCV samt explicit adjustment factor eller oberoende QA-godkänd total-return close.
4. Full coverage-matris mot oberoende listnings-/avnoteringsantal per år.
5. Daterade identitetskedjor för ticker-/namn-/aktieslagsbyte, merger och redomiciliering.
6. Verifierad terminaltabell och V4-ekvivalent post-decision execution.
7. Immutable manifest och adversarial future-/survivor-ablation.
8. Därefter separat preregistrering av **exakt H0**, utan alternativa horisonter, Top-N, vikt eller rebalancefas.

## Slutsats

Svensk prisdata kan rent tekniskt förlängas långt före 2010, men den lokala datan kan inte förlänga ett survivorship-försvarbart H0-test före 2020. Terminala bolag kan inkluderas först efter ny dataleverans; corporate actions och identitet är hanterbara men kräver ett nytt separat QA-lager. FinBas eller officiell Nasdaq-historik är de mest försvarbara vägarna.

2010–2019 kan därför bli ett hårt historiskt robustness-test, men **inte med nuvarande filer och inte som untouched holdback**.
