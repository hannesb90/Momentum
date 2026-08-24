# H0 Historical Universe Recovery — Nasdaq Stockholm 2010–2019

Datum: 2026-08-09  
Status: **SURVIVORSHIP-BLOCKERAT**  
Metodstatus: **HISTORICAL ROBUSTNESS — RESEARCH EXPOSED**

Ingen H0, target, IC, avkastning eller alternativ universumdefinition har körts. H0/V4 och alla tidigare frysningar är orörda.

## Slutsats

Nej — med de data som faktiskt finns lokalt kan vi ännu inte rekonstruera ett tillräckligt komplett och survivorship-försvarbart Nasdaq Stockholm Main Market-universum för 2010–2019.

Problemet är inte att en möjlig datakälla saknas i världen. Officiell Nasdaq-data som principiellt kan lösa venue- och identitetsfrågan finns. Problemet är att dessa historiska filer inte finns i projektet som immutable RAW och att nuvarande prisarkiv saknar en materiell del av de avnoterade Main Market-instrumenten. Därför har inget slutligt historical-universe-lager frysts.

Preregistreringen låstes före rekonstruktionsresultatet i [H0_HISTORICAL_UNIVERSE_2010_2019_PREREGISTRATION.json](/home/hannesb/momentum_v2/research_k/H0_HISTORICAL_UNIVERSE_2010_2019_PREREGISTRATION.json), SHA256 `fd4a41ec6b4ac62671d4b9d8faefee9ddc5614f1469dcad64596e281b867a03c`.

## Canonical universe och ordinary equity

Universumdefinitionen är låst till alla ordinära aktier som vid beslutstid T var upptagna till handel på Nasdaq Stockholm Main Market, med daterad instrumentidentitet och observerbar handel.

Inkluderas deterministiskt: ordinära A/B/C-aktieslag; SDB endast när depåbeviset representerar ordinärt eget kapital och själva SDB-linjen var upptagen på Main Market; utländska eller parallellnoterade bolag endast för den kvalificerade Stockholm-linjen.

Exkluderas: preferensaktier, ETF/ETP/fonder, certifikat, warranter, teckningsrätter, units, BTA, obligationer samt SPAC före slutförd business combination. Ticker är ett tidsbundet alias, aldrig persistent identitet.

## Befintliga källor

| Källa | Faktiskt innehåll | Användbarhet | Avgörande begränsning |
|---|---:|---|---|
| Skatteverket Aktiehistorik | 1 639 parsade bolag; 930 nya verbatim-sidor | Daterade noteringar, avnoteringar, namnbyten och ibland explicit venue | Inte ett komplett säkerhetsregister; ISIN/orderbook-ID saknas ofta |
| Legacy PIT-intervall | 749 intervall / 744 tickers | Kandidatintervall och källlänkar | Endast 10 intervall slutar före 2020; tickercentrerat och ofullständigt |
| EODHD ST archive | 1 010 aktiva + 694 delistade katalogposter | Priser, splits, utdelningar och discovery | `ST` blandar venue och instrumenttyper; bara 320/669 delistade Common Stock har ISIN |
| Börsdata pris-cache | 573 serier; tidigast 2006-07-31 | Historik för kvarvarande instrument | Ingen serie slutar före 2020; dagens instrumentlista är survivor/current |
| Tidigare Nasdaq segmentbevis | Ett fåtal daterade segmentbyten | Kan styrka Main Market för enskilda bolag | Segmentändringar är inte ett komplett membership-register |

EODHD:s `ST` innehåller dessutom 38 aktiva fonder, 27 aktiva ETF:er och 25 delistade ETF:er. Koden får därför inte användas som venue- eller ordinary-equity-bevis.

## Officiell Nasdaq-data

Den officiella vägen är reell men ännu inte införskaffad/frysen:

- [Nasdaq Nordic Reference Data Files](https://www.nasdaq.com/solutions/data/nasdaq-nordic-reference-data-files) innehåller börsspecifika equity listing details, inklusive ISIN och ticker. Den normala leveransen omfattar ett begränsat aktuellt fönster; projektet saknar 2010–2019-filerna.
- [Nasdaq Nordic and Baltic HistoricalView](https://www.nasdaq.com/solutions/data/nasdaq-nordic-baltic-historicalview) erbjuder historiska dagliga handelsfiler. Nasdaq anger att äldre filer kan begäras från Market Data Sales.
- Officiella övervakningsrapporter kan ge individuella listing/delisting-händelser med uttrycklig Main Market/First North-status. Exempelvis skiljer [Nasdaqs halvårsrapport 2019](https://www.nasdaq.com/docs/2019_Half-Yearly_Surveillance_Report.pdf) uttryckligen marknaderna åt. En komplett uppsättning för samtliga halvår 2010–2019 finns dock inte lokalt.
- [FinBas](https://www.houseoffinance.se/data-center/finbas/) är en möjlig lång svensk akademisk marknadsdatakälla. Ingen verifierad åtkomst eller immutable snapshot fanns i denna audit.

En offentlig årsrapport för 2010 ger en viktig kontrollsumma — 14 nya Main Market-noteringar och 15 avnoteringar — men aggregat kan inte ersätta instrumentvisa daterade identitetsintervall.

## Venue- och identitets-QA

Godtagbar evidensordning är:

1. daterad Nasdaq reference/listing-fil eller notice,
2. annan samtida primärkälla med uttrycklig venue och datum,
3. flera oberoende daterade källor som stödjer samma intervall.

EODHD `ST`, dagens Börsdata `marketId`, ticker eller fuzzy namn räcker aldrig ensamt. Endast 320 av EODHD:s 669 delistade Common Stock-poster har ISIN. Tidigare QA har dessutom dokumenterat tickeråteranvändning och kodkonflikter. Merger, relisting, ISIN-byte och aktieslagsbyte måste därför lösas med daterade kedjor, inte `last one wins`.

## Terminal- och pristäckning

Detta är den blockerande observationen:

| År | Identifierade Main Market-avnoteringar | Med EODHD-prisserie | Coverage |
|---:|---:|---:|---:|
| 2010 | 12 | 3 | 25 % |
| 2011 | 9 | 2 | 22 % |
| 2012 | 6 | 3 | 50 % |
| 2013 | 5 | 0 | 0 % |
| 2014 | 7 | 4 | 57 % |
| 2015 | 8 | 5 | 63 % |
| 2016 | 7 | 3 | 43 % |
| 2017 | 4 | 4 | 100 % |
| 2018 | 11 | 6 | 55 % |
| 2019 | 8 | 7 | 88 % |
| **Totalt** | **77** | **37** | **48,1 %** |

För 2010–2013 är täckningen endast **8/32 (25 %)**. Ingen delistad EODHD-serie slutar före 2013-07-23. Detta kan inte avhjälpas genom att använda dagens bolag: det vore exakt den survivor-only-backfill som testet ska undvika.

Skatteverket kan identifiera många av de saknade terminalerna och deras venue, men en terminalpost utan historisk pris- och corporate-actionkedja kan inte värderas ekonomiskt i H0. Börsdata-cachen innehåller 199 serier som når mitten av 2010 men noll serier som slutar före 2020; den bekräftar därmed inte terminaltäckning.

## Möjlig extra H0-historik — endast kalenderberäkning

Den frysta 8-veckorsfasen är förankrad i 2024-01-26 och stegas med 56 kalenderdagar.

- Om komplett prisdata börjar senast cirka 2008-08-12 blir första fas-kompatibla beslut 2010-02-12 och sista före 2020 blir 2019-12-06: **65 potentiella extra rebalanseringar**.
- Om prisdata först börjar 2010-01-01 ger 18 månaders lookback första fas-kompatibla beslut 2011-07-01: **56 potentiella extra rebalanseringar** till 2019-12-06.

Detta är en kalender-/feasibilityberäkning. Ingen ranking eller avkastning har beräknats.

## Acceptansgrindar

| Krav | Status |
|---|---|
| Daterad och PIT-försvarbar venue | **FAIL** för hela decenniet |
| Deterministisk ordinary-equity-definition | **PASS**, låst i preregistreringen |
| Stabil identitetskedja | **FAIL** för hela decenniet |
| Materiell terminaltäckning | **FAIL** — 37/77 prisatta |
| Priskoppling utan dagens-universe-bias | **FAIL** |

## Vad som krävs före ett framtida H0-test

1. Beställ/få åtkomst till immutable Nasdaq equity reference/security-master-filer för relevanta datum 2008–2019, eller en likvärdig auktoritativ licensierad källa.
2. Skaffa survivorship-kompletta priser och corporate actions för samtliga kvalificerade intervall, inklusive delistade linjer.
3. Bygg daterade ISIN/orderbook/share-class/entity-kedjor och venueintervall.
4. Stäm av instrumentvisa listings/delistings och årliga kontrollsummor mot officiella Nasdaq-notices.
5. Frys mottagna RAW-bytes, normalisering, exclusions, terminalmapping och slutuniversum med fail-fast-manifest.

Först därefter får ett separat protokoll preregistrera körningen av exakt oförändrad H0. Perioden ska även då märkas **HISTORICAL ROBUSTNESS — RESEARCH EXPOSED**, aldrig untouched OOS eller holdback.

Maskinläsbar evidens finns i [H0_HISTORICAL_UNIVERSE_RECOVERY_2010_2019_AUDIT.json](/home/hannesb/momentum_v2/research_k/H0_HISTORICAL_UNIVERSE_RECOVERY_2010_2019_AUDIT.json).
