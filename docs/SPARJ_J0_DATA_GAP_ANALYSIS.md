# Spår J — J0 datagapanalys och J1 OHLC-QA

Status: **STOPPUNKT 1 SLUTFÖRD**  
Datum: 2026-08-09  
Target läst: nej  
Modell/backtest/IC kört: nej  
H0/H1/H2 ändrade: nej

## Research I

Research I är formellt **SLUTFÖRT**. Samtliga 46 poster klassade `REPLIKERA NU` är behandlade, kvarvarande poster är 0 och ingen Batch 4 får skapas. Maskinläsbar stängning finns i `research_i/RESEARCH_I_COMPLETE.json`.

## Sammanfattning

| Familj | J0-klass | Slutsats vid stoppunkt 1 |
|---|---|---|
| ATR / high-low | DATA REDAN TILLGÄNGLIG — QA FRYST | Låst EODHD RAW innehåller O/H/L/C/adjusted close/volume. Ett separat OHLC-tillägg har validerats och frysts; inga ATR/ADX-features har byggts. |
| Report / Attention / PEAD | DELVIS BYGGBAR | Lokal MFN-cache har riktiga publiceringstider och strukturerade ISIN/tickers, men är legacy-normaliserad och inte en reproducerbar verbatim RAW-snapshot. Ny råsnapshot/metod behövs före byggstart. |
| Dividend-gap | DATA SAKNAS / EJ PIT-FÖRSVARBAR | Ex-date och belopp finns, men announcement timestamp saknas för merparten. Ex-date får inte användas som proxy för när marknaden fick informationen. |
| Insider-gap | DELVIS BYGGBAR | Lokal FI-cache visar att källan är relevant, men den är parsad, datumgranulär, sannolikt trunkerad i delar och saknar korrigerings-/RAW-evidens. Ny officiell råinsamling/metod krävs. |

## J1 — separat OHLC-tillägg

Källa: den redan manifesterade immutable EODHD-snapshoten under `/home/hannesb/momentum_prod_work/momentum_ml/cache/eodhd_archive/ST`. Spår A öppnades eller ändrades inte; dess låsta instrument och datum användes endast som tillåten scope och som kontrollsumma för close, adjusted close och volume.

Resultat:

* 581 115 av 581 115 förväntade rader validerade.
* 420 instrument, varav 352 aktiva och 68 terminalinstrument.
* Terminaltäckning: 68/68 (100 %).
* Period: 2020-01-02–2026-07-24.
* Inga saknade OHLCV-fält, icke-positiva priser, negativa volymer, OHLC-identitetsbrott eller avvikelser mot Spår A:s råvärden.
* 74 dagsrader har high/low > 2 och sparas som explicita extrema observationer, inte som automatiska fel.
* 99 stora hopp i `adjusted_close/close` har identifierats för corporate-action-granskning. De är diagnostik och har inte använts för en feature.
* O/H/L/C/volume är vendor-observerade ojusterade värden. `adjusted_open/high/low` är en explicit mekanisk skalning med samma dags `adjusted_close/close`; detta är normalisering, inte en ATR-definition.

Manifest: `trackj/ohlc_v1/manifest.json`  
Manifest SHA256: `a6ab714dee0f6747f6a13376af11c3303ac8db99a74386df9cf7df8977b93c98`  
Aggregate SHA256: `b8bf830703db948eb3dd7b8b13f12e487726f0025e0053492e75789392a62458`

## Report / Attention / PEAD

Ekonomisk hypotes: verkligt tidsstämplad rapportpublicering, initial marknadsreaktion/uppmärksamhet och efterföljande drift kan bära information som är distinkt från lång momentum.

Behov: publiceringstid med tidszon, rapporttyp, stabil ISIN/issuer-identitet, pre/post-pris och volym. Earnings surprise kräver verklig konsensusdata och får inte skapas som prisproxy.

Lokalt finns en MFN-cache med 1 057 JSON-filer, 206 565 poster, 180 857 unika item-id:n och 38 272 textklassade rapportliknande events. 206 071 poster har strukturerad ISIN och 206 183 strukturerad ticker. Publiceringstider täcker 1996-12-11–2026-07-24. Cache finns för 378 V2-instrument, men endast 30 terminalinstrument; 29 av dem har rapportliknande event.

Risker: cacheurvalet gjordes historiskt via query/namn, samma item förekommer i flera filer, ursprungliga HTTP-bytes och requestmanifest saknas och eventklassificeringen är ännu inte QA-godkänd. `report_Date` i V2 är endast ett datumfält och är inte exakt publiceringstid.

Beslut: bygg inte eventpanel ännu. Nästa metodbeslut är om MFN kan hämtas om som verbatim, append-only RAW med requestparametrar och full ISIN-baserad historisk/terminal scope.

## Dividend-gap

Ekonomisk hypotes: en offentligt annonserad förändring i jämförbar utdelning kombinerad med svag initial reaktion kan följas av drift.

EODHD:s låsta dividendfiler innehåller 2 067 events sedan 2020 för 281 instrument, inklusive 31 terminalinstrument. Ex-date finns för alla, men `declarationDate` finns endast för 466 (22,5 %), `paymentDate` för 619 och `recordDate` för 2. Börsdata-cachen innehåller 12 751 events sedan 2020 och fält för ex-date, betalt belopp, typ, frekvens och valuta, men ingen announcement timestamp.

Risker: ex-date och payment date är framtida händelsefakta och visar inte när utdelningsförändringen blev publik. Ordinary/special, korrigeringar, splitjustering och jämförbar föregående utdelning kräver ytterligare QA.

Beslut: fortsatt **DATA SAKNAS / EJ PIT-FÖRSVARBAR**. Ingen bakåtkonstruktion av announcement date tillåts.

## Insider-gap

Ekonomisk hypotes: offentliggjorda diskretionära insiderköp/-försäljningar plus initial prisreaktion kan följas av drift. PIT-tid är offentliggörandet hos FI, inte transaktionsdagen.

Lokalt finns 719 parsade FI-filer med 14 310 rader från 2016-08-19–2026-07-24 och 652 unika ISIN. ISIN mappar till 217 V2-instrument men bara 3 terminalinstrument. 474 filer är tomma, 115 har exakt 80 rader och det finns 922 exakta dubblettrader.

Risker: endast datum, inte publiceringsklockslag; inga fält för rättelser/makuleringar; ingen original-HTML/API-snapshot eller request/pagineringsmanifest; 80-radersutfallen innebär konkret trunkeringsrisk; terminaltäckningen är mycket låg.

Beslut: **DELVIS BYGGBAR**, men endast efter nytt beslut om officiell FI-insamling som sparar verbatim RAW, paginering, mottagningstid och korrigeringshistorik.

Officiell kandidat: FI:s publika insynsregister och dess exportfunktion. FI anger att MAR-registret är sökbart från 3 juli 2016, att publicering sker automatiskt när anmälan kommer in samt att reviderade poster kan ha status `Reviderad`/`Historik`. Den officiella exporten är därför en bättre råkälla än den lokala issuer-query-cachen, men exakt exportformat, tidsgranularitet och möjligheten att bevara revisionskedjan måste beslutas innan hämtning.

## Identitet och survivorship

Ny data ska mappas `ISIN → orgnr → explicit verifierad mapping`. Ticker eller fuzzy namn får inte automatiskt skapa datapunkter. OHLC-tillägget följer Spår A:s explicit lösta EODHD-koder och omfattar alla 68 terminalinstrument. MFN:s och FI:s nuvarande terminaltäckning är däremot otillräcklig och får inte beskrivas med en enda aggregerad coverage-siffra.

## Rekommenderad byggordning

1. OHLC är färdig som dataartefakt; senare ATR/ADX-forskning kräver separat preregistrerad featuredefinition.
2. MFN report-events: besluta om och genomför reproducerbar verbatim råsnapshot med ISIN-baserad scope.
3. FI insider: besluta om officiell endpoint/export, full paginering, klocktidsregel och korrigeringshantering.
4. Dividend: fortsätt endast om en källa med faktisk announcement timestamp och tillräcklig historisk/terminal täckning identifieras.

## Stopp

Ingen extern data har hämtats, ingen event-/featurepanel har byggts för MFN, dividend eller insider, och ingen target, IC eller backtest har lästs eller körts. Fortsättning kräver nya käll- och metodbeslut enligt ovan.
