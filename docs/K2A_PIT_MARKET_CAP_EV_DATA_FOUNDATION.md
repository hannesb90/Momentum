# K2A — PIT market cap / EV data foundation

## Slutbeslut

- PIT market cap: **BLOCKERAD**.
- PIT EV: **BLOCKERAD**.
- Value-within-momentum: **FORTSATT BLOCKERAD**.

Ingen target, IC, alpha, ranking eller backtestning har lästs eller körts. Eftersom market-cap-gaten föll byggdes inget numeriskt market-cap- eller EV-lager.

## `number_Of_Shares`

Börsdatas offentliga material visar “Antal Aktier” som rapportdata och säger att punkterna i historikdiagrammet kommer från rapporter, men definierar inte fältet som periodslutets utestående aktier. OpenAPI beskriver det endast som ett numeriskt rapportfält. [Börsdata – historisk rapportdata](https://borsdata.se/info/bolagssida/aktiekurs-nyckeltalsutveckling), [officiell API-dokumentation](https://github.com/Borsdata-Sweden/API).

Empirin visar:

- `profit_To_Equity_Holders / number_Of_Shares ≈ earnings_Per_Share` på 12 263 R12-rader.
- Median relativ avvikelse är 0,0015%, p95 0,927%; 95,16% ligger inom 1% och 98,72% inom 10%.
- Enheten är därmed empiriskt **miljoner aktier**, eftersom rapportbeloppen är MSEK.
- Detta identifierar fältet som EPS-denominator eller närliggande rapportperiodmått. Det bevisar inte period-end shares outstanding.
- Runt 273 rapportpar med vendorhändelser följde endast 72 share-count-förändringar splitfaktorn inom ±30%; 201 gjorde det inte. HMS, Holmen, AQ och flera andra behåller i praktiken samma rapporterade aktieantal över tydliga splitfaktorer, förenligt med retroaktiv splitrestatement. EPS-konsistensen är samtidigt stark.

Det går därför inte att avgöra från Börsdatafältet om en observation är basic/diluted weighted average, period-end outstanding, totalt emitterat eller retroaktivt restaterat. Emissioner, återköp, indragningar och aktieslag saknar dessutom en fullständig effective-date-kedja.

## Två tider

`report_end_date` är ekonomiskt periodslut. `report_date` är den försvarbara tidpunkt då observationen tidigast blir marknadskänd i V2. Ett framtida lager måste alltid använda senaste `report_date <= panel_date`; periodslutet får aldrig vara availability timestamp.

Panelens rapportstaleness är 0–437 dagar, median 45 dagar. Staleness får inte interpoleras eller döljas.

## Pris- och splitbasis

Ojusterad `close` är faktiskt handlat pris, men kan inte multipliceras med ett okänt periodvägt eller retroaktivt splitrestaterat aktieantal. `adjusted_close` är totalavkastningsjusterat och påverkas även av utdelningar; det är därför inte ett ekonomiskt market-cap-pris.

En produkt av `close × latest reported number_Of_Shares` är tekniskt beräkningsbar, men den är endast en **latest-reported-share market-cap proxy**. Den är inte godkänd och får inte kallas historiskt market cap.

## Aktieslag

`number_Of_Shares` är rapportdata på bolagsnivå medan V2-priset avser ett instrument/aktieslag. För bolag med flera noterade eller onoterade klasser kan totalbolagets aktier inte multipliceras med varje klasspris eller med ett godtyckligt representativt klasspris. Den generella regeln är därför att sådana observationer förblir `UNRESOLVED` tills klassvisa utestående aktier och priser kan summeras utan dubbelräkning.

## Oberoende market-cap sanity QA

Ingen historisk market-cap-jämförelse genomfördes. Det är ett avsiktligt fail-fast: en jämförelse av en odefinierad proxy mot publicerade market caps skulle inte verifiera denominatorns PIT- eller splitsemantik. Sanity-steget får börja först efter att utestående aktier och effective dates har verifierats oberoende.

## EV

`net_Debt` är den redan QA-godkända PIT-komponenten och finns på 26 907 panelrader. Ett ekonomiskt EV kan definieras som godkänt market cap plus nettoskuld. Eftersom market cap är blockerad är EV blockerad. Ingen pseudo-EV från osäkra skuld-/kassakomponenter byggs. Banker och finansbolag behöver dessutom en separat ekonomisk användbarhetsregel.

## Value-featureinventering

Följande har PIT-numerator men blockerad denominator:

- Earnings yield: vinst till aktieägare / market cap.
- FCF yield: FCF / market cap.
- Sales yield: omsättning / market cap.
- Book-to-market: eget kapital / market cap.
- Dividend yield: utdelning per aktie / kompatibelt ojusterat pris.
- EBITDA/EV, EBIT/EV och FCF/EV: respektive flöde / EV.

Inget av måtten är godkänt för signalbygge ännu. Missing ska senare vara `NULL`, aldrig ekonomisk nolla.

## Coverage och survivorship

- Panelrader: 30 073.
- Fundamentatäckning: 26 907 rader, 89,47%.
- Instrument: 345/420.
- Terminalinstrument med användbar panelmatchad fundamenta: 0/68.
- Årscoverage ökar från 80,53% år 2020 till 97,99% år 2026.

Detta är **NOT SURVIVORSHIP SAFE**. Hög radcoverage bland överlevare ändrar inte att terminalpopulationen saknas. Även efter en framtida market-cap-lösning får K2 därför endast preregistreras som matched-population diagnostic.

## Vad som krävs för att öppna K2

1. Historiska utestående aktier, inte EPS-weighted-average, med explicit effective date.
2. Klassvis aktiefördelning och generell regel för noterade/onoterade aktieslag.
3. Komplett kedja för split, emission, återköp och indragning.
4. Ojusterat historiskt pris på kompatibel splitbasis.
5. Valutamatchning mellan pris och rapporttotaler.
6. Oberoende jämförelse mot dokumenterade historiska market caps.
7. Immutable freeze före targetkoppling.

## Svar på huvudfrågan

**Nej.** Med nuvarande frysta V2-data kan vi inte utan look-ahead och på bevisat kompatibel splitbasis veta exakt vad marknaden värderade bolaget till vid varje beslutstidpunkt. Vi kan observera ett rapportpublicerat EPS-aktieantal och ett historiskt pris, men inte bevisa att deras ekonomiska baser är kompatibla. K2-value-testet får därför inte preregistreras ännu.
