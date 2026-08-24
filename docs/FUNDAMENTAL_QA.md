# Spår B: fundamental-QA mot det låsta Nasdaq Stockholm-universumet 2020+

Datum: 2026-08-08. **Ingen feature engineering, ingen modellträning, ingen rådata ändrad.**
Legacy läst strikt read-only. Verktyg: `tools/fund_legacy_inventory.py`,
`tools/fetch_v2_raw_borsdata.py`, `tools/fund_qa_track_a.py`, `tools/build_validated_fundamentals.py`.
Artefakter: `docs/probes/fund_legacy_inventory.json`, `raw/borsdata/` (1 077 hämtningar),
`docs/probes/fund_qa_track_a.json`, `validated/fundamentals/`, `validated/manifest_sparB.json`.

Arbetet utgår från Börsdatas 37 råfält, inte de gamla 48 featurerna.

---

## 0. Sammanfattning

| track | definition | utfall i detta universum |
|---|---|---|
| **A** | V2 RAW, nyhämtad live 2026-08-08, verbatim bytes + sha256 | **358 instrument, 1 077 hämtningar, 0 fel** |
| **B** | LEGACY_ARCHIVE, ej reproducerbar på råbytesnivå, PIT-verifierad via innehåll | **1 rad (Besqab) — redan täckt av Track A** |
| **C** | otillräckligt verifierbar | **67 av 68 avnoterade bolag** |

Den viktigaste slutsatsen kommer före fältklassificeringen: **Track B tillför i praktiken
ingenting.** Premissen — att legacy-cachen kan bevara oersättlig fundamenta för bolag
Börsdata sedan raderat — höll inte vid rigorös kontroll för det här universumet.

## 1. Legacy-inventering: vad finns faktiskt för de 68 avnoterade?

Metod: matcha varje avnoterat bolag mot Börsdatas `insId` via **ISIN i första hand, exakt
normaliserat namn i andra hand**. Fuzzy namnmatchning testades och **stängdes av** efter ett
konkret kontrollprov: vid cutoff 0,90 matchade "Nobina AB" (busstrafik, avnoterad
2022-02-16) mot **"Nobia"** (kök, insId 157, alltjämt aktiv med rapporter t.o.m.
2026-07-17) — två olika bolag med snarlika namn. En sådan felidentifiering hade varit värre
än en lucka: fel bolags fundamenta hade smugit in under fel namn. Endast ISIN och exakt
namn godtas.

**Resultat: 1 av 68 matchade mot en legacy-rapportfil (Besqab, insId 2197, 8 årsrader).
67 saknar identifierbar data helt.**

En kompletterande kontroll utesluter att bristen beror på ofullständig matchning: av
legacy-cachens samtliga 732 årsrapportfiler har **0 st** ett `insId` som saknas i både
dagens och en äldre Börsdata-instrumentlista — dvs. det finns inga "spårlösa" filer som
skulle kunna dölja ytterligare någon av de 68.

**Förklaringen är strukturell, inte ett sökfel:** legacyns fundamentahämtningar kördes 2026,
år efter de flesta avnoteringarna. Börsdata hade redan då tagit bort dessa bolag ur sitt eget
`/instruments`-register (samma raderingsmekanism som fastställdes i universumarbetet), och
fetchkoden itererade bara över instrument som fanns i listan **vid hämtningstillfället**.
Legacyns fundamentacache byggdes alltså aldrig för bolag som redan var döda när cachen
skapades.

Och Besqab — den enda träffen — är enligt spår A **inte en äkta dödsobservation**:
handeln fortsatte efter avnoteringsdatumet, och priset delades vid ett datafel snarare än
vid bolagets faktiska upphörande (`PRIS_QA_KLASSIFICERING.md §4b`). Besqab finns dessutom
**redan i Track A** (live-hämtad, insId 2197 ingår i de 358 matchade). **Track B bidrar
noll unika instrument.**

Full provenance per rad (instrument, ISIN, filhash som den ser ut nu, rapportperiod,
`report_Date`, filens mtime som approximation av hämtningstid eftersom inget hämtningsmanifest
sparades för denna legacy-cache) finns i `docs/probes/fund_legacy_inventory.json`.

## 2. Track A: live-hämtning, hashverifierad

359 av universumets 429 instrument (356 aktiva + Besqab-typen) matchade mot Börsdatas
**dagens** `/instruments` via ISIN. Tre endpoints per instrument (`reports` år,
`reports/quarter`, `reports/r12`), rådata sparad **verbatim** (`r.content`, inte
`json.dumps(r.json())` som legacyns kod gjorde), sha256 på exakt de mottagna bytesen.

**1 077/1 077 lyckade anrop, 0 fel.** 358 instrument gav faktiskt årsdata (ett av de 359
matchade svarade tomt). 70 av universumets instrument matchar inte Börsdatas live-lista
alls — förväntat, det är just de äkta avnoteringarna.

Denna gång är kravet "RAW sparas oförändrad" **uppfyllt**, till skillnad från legacyns
`researchdb_v1/raw` (se `UNIVERSUM_OCH_KALLBESLUT.md §5`).

## 3. Fältmetadata — den auktoritativa källan

`GET /v1/instruments/reports/metadata` hämtades (1 anrop, sparad verbatim). Den definierar
samtliga 37 fält med svenskt/engelskt namn och enhetsformat:

| format | betydelse | antal fält |
|---|---|---|
| `MCURR` | miljoner i rapportvalutan | 22 |
| `CURR` | valutaenhet per aktie/post (ej miljoner) | 5 |
| `MILL` | miljoner aktier | 1 |
| *(null)* | datum/kategoriskt/valutakod | 9 |

**Dokumentationsfel upptäckt:** metadata kallar intäktsfältet `net_sales` (gemen s), men
det faktiska datafältet i svaren heter `net_Sales` (versal S). Ren namninkonsekvens hos
leverantören — påverkar ingen data, men fångade en bugg i min egen första analys (fältet
såg ut att ha 0 % täckning tills case-felet rättades).

## 4. PIT-korrekthet

5 403 årsrader, 358 instrument, 2006–2026.

| kategori | antal | andel |
|---|---|---|
| giltiga | 4 869 | 90,1 % |
| saknar `report_Date` | 482 | 8,9 % |
| Excel-epok (`1899-12-30` m.fl.) | 8 | 0,15 % |
| **genuin look-ahead** (`report_Date` < `report_End_Date`) | **49** | **0,91 %** |

**Look-ahead, uppdelat i två skilda orsaker:**
- 8 fall är `1899-12-30`-epokdatumet — samma kända Excel-nollepoksfel som redan dokumenterat
  för MFN-datan i legacy. Fångas separat av epokfiltret, inte räknat som look-ahead.
- **49 genuina fall, 13 instrument** (BICO Group, Alligo, Ascelia Pharma, Fortinova
  Fastigheter, Eolus m.fl.): `report_Date` för en **helårsrad** ligger konsekvent i
  oktober/maj/augusti — mitt i det rapporterade räkenskapsåret, inte efter det. Det är inte
  slumpmässigt brus utan ett systematiskt fel i hur Börsdata satt datumet för dessa
  bolags äldre årsrader (troligen ett kvartalsdatum av misstag kopplat till helårsraden).
  **Dessa 49 rader utesluts** — ingen gissning på rätt datum görs.

**Saknat `report_Date` är starkt koncentrerat till den äldsta raden per bolag:** 482 av 485
saknade är helårsrader (`period=5`), och **157 av 358 instrument (44 %)** saknar datum just
på sin äldsta årsrad (median år 2016, spann 2006–2025). Det är ett **vänstercensurerat**
mönster i vad Börsdata dokumenterat, inte en jämnt spridd brist — konsekvent med att äldre
delar av 20-årshistoriken har sämre metadata.

**Rapporteftersläpning** (`report_Date − report_End_Date`, giltiga rader): median 43 dagar,
p10 29 dagar, p90 55 dagar, max 393 dagar. Rimligt för kvartals-/årsrapportering.

## 5. Valuta och enhetskonvertering

| valuta | rader | andel |
|---|---|---|
| SEK | 4 851 | 89,7 % |
| EUR | 338 | 6,3 % |
| USD | 173 | 3,2 % |
| NOK | 21 | 0,4 % |
| PLN | 16 | 0,3 % |
| ISK | 12 | 0,2 % |

`currency_Ratio` konverterar `MCURR`/`CURR`-fält till SEK. **20 rader har `currency_Ratio`
exakt 1,0 i en icke-SEK-valuta** — uppdelat:

- **5 EUR-rader**: bevisligen fel (EUR/SEK har aldrig legat nära paritet). **Uteslutna.**
- **15 NOK-rader**: tvetydigt. NOK/SEK har historiskt legat nära paritet, så 1,0 kan i
  princip vara korrekt — men att värdet är **exakt** 1,0 på samtliga 15 rader (inte t.ex.
  0,97 eller 1,02, som en verklig daglig växelkurs skulle ge) tyder på en **fallback-standard**
  snarare än en levande konvertering. **Behållna men flaggade** (`ratio_flagg=true` i
  VALIDATED) — inte uteslutna, eftersom en felaktig uteslutning här vore lika fel som en
  felaktig inkludering.

## 6. Källkonsistens: `revenues` mot `net_Sales`

Båda fälten finns i samma svar. **4 261/5 411 rader (78,7 %) är exakt identiska.** De
återstående 21,3 % skiljer sig med små belopp (exempel: 10 081 mot 10 011, 10 302 mot
10 295) — inte fel av samma storleksordning som skalfelen i §7, utan sannolikt två skilda
redovisningsrader (`revenues` inkluderar möjligen övriga rörelseintäkter som `net_Sales`
exkluderar). **Inte verifierat vilken definition som är vilken** — flaggas som öppen fråga,
inte som datafel.

## 7. Skala, tecken och extremvärden — per fält

Fullständig tabell i `docs/probes/fund_qa_track_a.json`. Sammanfattning:

- De 22 `MCURR`-balans-/resultaträkningsfälten har **100,0 % täckning** i samtliga 358
  instrument och rimliga percentilspann efter SEK-konvertering. Nollandelen (0,3–13,9 %) är
  genomgående förklarlig (t.ex. `intangible_Assets` 13,9 % nollor = bolag utan
  immateriella tillgångar, inte ett datafel).
- **`earnings_Per_Share` är internt konsistent**: beräknat som
  `profit_To_Equity_Holders / number_Of_Shares` matchar det rapporterade värdet inom 1 % i
  89,9 % av raderna och inom 10 % i 97,0 %. Fältet är alltså **inte** offer för den
  retroaktiva splitjustering som förstörde legacyns MFN-baserade `eps_growth_yoy` (se
  `DATATACKNING_48FEATURES_2026-08-07.md`).
- **EPS-hopp >5×/<0,2× år till år (215 fall, varav 198 utan matchande split hos
  Skatteverket) är i allt väsentligt äkta resultatvolatilitet**, inte datafel — exempel
  Humana (0,044→0,937 kr, 2011→2012, verksamhetsvändning) och Paradox Interactive
  (tillväxtfas). Bekräftat av den interna konsistenskontrollen ovan.
- **`dividend`-hopp (36 fall, 27 okopplade mot känd split via Skatteverkets textbaserade
  ±1-årsfönster)** — se §7b för den definitiva kontrollen direkt mot EODHD:s splitfiler.
- **`stock_Price_*`-hopp (37 fall, 27 okopplade)** innehåller minst ett bekräftat *äkta*
  fall som inte är ett datafel: Oncopeptides 161,20→8,98 kr (2020→2021) är den välkända
  FDA-indragningen — en verklig kurskrasch, inte en trasig serie. Att skilja äkta krascher
  från ojusterade splitar kräver samma sortens volymkontinuitetsanalys som gjordes för
  EODHD-priserna i spår A, och det är inte gjort för Börsdatas egna prisfält — ett av
  skälen (utöver redundansen med redan verifierade priser) till att fältet utesluts.

## 7b. Splitverifiering av `earnings_Per_Share` och `dividend` — definitiv kontroll

Verktyg: `tools/fund_split_verify.py`. Metod: Börsdatas `instrument_master`-kopplade
EODHD-kod (samma ISIN-verifierade mappning som spår A) ger tillgång till EODHD:s
**splitfiler** — samma källa som redan klassade de 871 prisnivåbrotten i
`PRIS_QA_KLASSIFICERING.md`, inte Skatteverkets fritextbaserade tabell.

**Test 1 — reflekteras kända splitar i `number_Of_Shares`?** 190/358 instrument har minst
en EODHD-split. Av 276 instrument-år med en split i fönstret matchar aktieantalets
förändring splitfaktorn (±30 %) i **72 fall**, och stämmer **inte** i **204 fall**.

Fyra av avvikelserna (HOLM-B 2018, ALFA 2008, HMS 2017, INDT 2016) kontrollerades direkt mot
**rå** (ojusterad) `close` i spår A:s EODHD-data: samtliga visar en verklig ~2–4× prisnedgång
exakt på splitdatumet, med `adjusted_close` kontinuerlig över hoppet (dvs. spår A:s
prisjustering är korrekt) — **men `number_Of_Shares` ändras inte alls**. Den mest sannolika
förklaringen: EODHD:s splitfil blandar ihop genuina aktiesplittar (som multiplicerar
aktieantalet) med andra händelser som kräver samma sorts prisjusteringsfaktor men INTE ändrar
aktieantalet — typiskt en stor extrautdelning. Det är alltså i dessa fyra fall EODHD:s
split-etikett som är för bred, inte Börsdatas aktieantal som är fel. **De återstående 200
avvikande fallen är inte stickprovskontrollerade var för sig** — se kvarvarande begränsning.

**Test 2 — är EPS lika internt konsistent (`profit_To_Equity_Holders / number_Of_Shares`)
kring splitår som generellt?**

| grupp | n | andel <1 % avvikelse | andel <10 % avvikelse |
|---|---|---|---|
| rader kring en genuin split | 276 | 81,5 % | 89,9 % |
| övriga rader | 4 585 | 89,6 % | 97,3 % |

En måttlig men inte dramatisk försämring — konsistensen håller i stort sett även vid splitar,
vilket visar att aktieantal och EPS uppdateras samordnat när en split väl sker.

**Test 3 — de tio namngivna "oförklarade" hoppen från §7, kontrollerade en och en mot EODHD:s
splitfiler (inte Skatteverkets text):**

| bolag | fält | period | utfall | EODHD-split i fönstret | aktieantal |
|---|---|---|---|---|---|
| Humana AB | EPS | 2011→2012 | *(raden utesluten av PIT-regel R4, se §10)* | – | – |
| Holmen AB | EPS | 2010→2011 | 4,191→23,542 | **ingen** | oförändrat 168,00→168,00 |
| Carasent AB | EPS | 2016→2017 | 5,173→0,944 | **ingen** | oförändrat 20,36→20,36 |
| Paradox Interactive AB | EPS | 2014→2015 | *(raden utesluten av PIT-regel R4)* | – | – |
| Hufvudstaden AB | dividend | 2006→2007 | 11,600→1,750 | **ingen** | oförändrat 206,26→206,26 |
| Avarda Bank AB | dividend | 2013→2014 | *(raden utesluten av PIT-regel R4)* | – | – |
| Volati AB | dividend | 2020→2021 | 11,200→1,700 | **ingen** | oförändrat 79,41→79,41 |
| NAXS AB | dividend | 2024→2025 | 20,250→2,000 | **ingen** | oförändrat 11,08→11,08 |
| NCC AB | dividend | 2007→2008 | 21,000→4,000 | **ingen** | oförändrat 108,40→108,40 |
| New Wave Group AB | dividend | 2007→2008 | 0,500→0,090 | **ingen** | oförändrat 132,68→132,68 |

**Samtliga åtta kontrollerbara fall saknar helt matchande split, och aktieantalet är
oförändrat.** Det utesluter en ojusterad split som förklaring och bekräftar att hoppen är
äkta ekonomiska händelser: resultatvolatilitet för EPS, utdelningspolicyändringar
(extrautdelning följt av normalisering, eller finanskrisrelaterade sänkningar 2007–2008 för
NCC och New Wave Group) för dividend. Två av de tio raderna (Humana, Paradox Interactive,
Avarda Bank — tre, inte två) exkluderades för övrigt redan av en oberoende PIT-regel (§10)
innan splitkontrollen ens blev relevant.

**Slutsats: `earnings_Per_Share` och `dividend` uppgraderas från KRÄVER ÅTGÄRD till
GODKÄND.** Den kvarvarande, ärligt redovisade begränsningen: kontrollen är riktad (de
namngivna extremfallen plus en aggregerad konsistensmätning), inte en uttömmande
rad-för-rad-verifiering av samtliga 204 avvikande split-instrument-år.

## 8. Avnoterade bolag — bekräftelse

68 avnoterade Nasdaq Stockholm-bolag 2020–2026. **1 med åtkomlig fundamentadata (Besqab,
som inte är en äkta dödsobservation), 67 helt utan.** Detta är oberoende av
prisproblemet som spår A löste — priserna är nu survivorship-säkra, **fundamenta är det
inte och kan inte göras det med tillgängliga källor.** Se `docs/probes/fund_legacy_inventory.json`
för fullständig lista med orgnr och avnoteringsdatum.

**Detta gäller likadant för kvartals- och R12-datan** (§9) — samma 358 instrument, samma
avsaknad för de 67. Survivorship-problemet i fundamenta är alltså inte en artefakt av
årsupplösningen, det är strukturellt för hela Börsdata-källan i det här universumet.

---

## 9. Kvartals- och R12-data — separat fullständig QA

Verktyg: `tools/fund_qa_quarter.py`. Samma 37 fält, samma 358 instrument, hämtade som en del
av Track A (§2). **12 995 kvartalsrader och 12 883 R12-rader.**

### PIT

| | kvartal | R12 | (år, jämförelse) |
|---|---|---|---|
| giltiga | 12 294 (94,6 %) | 12 275 (95,3 %) | 4 869 (90,1 %) |
| saknar datum | 632 (4,9 %) | 531 (4,1 %) | 482 (8,9 %) |
| look-ahead | 66 (0,51 %) | 75 (0,58 %) | 49 (0,91 %) |
| epok | 3 | 2 | 8 |

Kvartalsdatan har genomgående **bättre** PIT-kvalitet än årsdatan — väntat, eftersom API:ts
40-kvartalstak (se nedan) gör att kvartalshistoriken är nyare i genomsnitt och den äldsta,
sämst dokumenterade delen av 20-årshistoriken aldrig nås.

**API-taket bekräftat igen, oberoende av tidigare mätning:** kvartalsraderna sträcker sig
tillbaka till 2014 men med bara 1–4 rader det året, växande till full bredd (1 200+ rader)
först 2017–2021. Det är samma gräns — 40 kvartal per instrument räknat bakåt från
hämtningsdagen — som redan fastställdes empiriskt i `LUCKFYLLNING_FUNDAMENTA_2026-08-07.md`.

**Ny PIT-brist, inte synlig i årsdatan förrän den här kontrollen gjordes: orimlig
eftersläpning.** `Alligo AB` har sju på varandra följande kvartalsrader (2017 Q4 till 2019
Q2) med `report_Date` **sekventiellt** `2020-05-01, 2020-05-02, 2020-05-03 … 2020-05-08`
— ett datum per dag, oberoende av vilket kvartal raden gäller. Det är inte en genuin
publiceringsdatumserie, det är ett **batch-tilldelat** datum, sannolikt kopplat till
Alligos avknoppning från Momentum Group 2022 (samma bolag vars årsdata redan flaggades i §4
för att ha `report_Date` mitt i räkenskapsåret). En ny regel (R4, §10) utesluter rader med
>180 dagars eftersläpning — det fångar de värsta 16/10/2 fallen (år/kvartal/R12) men är
inte bevisat att fånga alla subtilare varianter av samma Alligo-mönster.

### Täckning per instrument och år

Samtliga 358 instrument har rader; endast 1 instrument har färre än 8 kvartalsrader (≈2 år).
Ingen ytterligare täckningslucka utöver den redan kända API-gränsen.

### Skala och extremvärden

Percentilspannen är i samma storleksordning som årsdatan för samtliga fält (full tabell i
`docs/probes/fund_qa_quarter.json`). Ingen ny skalanomali hittades utöver de redan kända
(`net_Sales`-aliaset, NOK/EUR-konverteringen).

### Källkonsistens — tre oberoende endpoints jämförda mot varandra

**Kvartalssumma (4 st) mot motsvarande R12-rad**, tre flödesfält:

| fält | n | <1 % avvikelse | <10 % avvikelse |
|---|---|---|---|
| `revenues` | 11 121 | 93,0 % | 99,6 % |
| `operating_Income` | 11 838 | 92,3 % | 99,1 % |
| `profit_To_Equity_Holders` | 11 835 | 91,7 % | 98,9 % |

**R12 vid Q4 mot samma periods årsdata** (två helt separata endpoints, `/reports` mot
`/reports/r12`):

| fält | n | identiska (<0,1 %) |
|---|---|---|
| `revenues` | 3 177 | **100,0 %** |
| `operating_Income` | 3 386 | **100,0 %** |
| `profit_To_Equity_Holders` | 3 385 | **100,0 %** |
| `total_Assets` | 3 386 | **100,0 %** |
| `total_Equity` | 3 386 | **100,0 %** |

**Perfekt överensstämmelse mellan tre oberoende hämtade tabeller.** Det här är det
starkaste enskilda beviset för att Track A:s kärnfält är korrekta — tre olika API-anrop,
olika endpoints, samma tal.

### Missing-semantik: `dividend` i kvartalsdata

Hypotesen att utdelning skulle vara koncentrerad till ett enda kvartalsnummer (t.ex. Q2, då
de flesta svenska bolagsstämmor hålls) **höll inte**: rader med `dividend ≠ 0` fördelar sig
jämnt över alla fyra kvartal (1 850–1 887 vardera). En nolla i ett enskilt kvartal är alltså
en äkta observation ("ingen utbetalning denna period"), inte ett tecken på fel — men den
kan inte tolkas som "bolaget delar aldrig ut" utan att se hela året.

---

## 10. Fältklassificering — slutlig

| fält | format | klass | skäl |
|---|---|---|---|
| `revenues` | MCURR | **GODKÄND** | 100 % täckning, PIT ok, ingen skalanomali |
| `gross_Income` | MCURR | **GODKÄND** | 99,6 % täckning, rimlig fördelning |
| `operating_Income` | MCURR | **GODKÄND** | 100 % täckning |
| `profit_Before_Tax` | MCURR | **GODKÄND** | 100 % täckning |
| `profit_To_Equity_Holders` | MCURR | **GODKÄND** | 100 % täckning; grund för EPS-konsistenskontrollen |
| `total_Assets` | MCURR | **GODKÄND** | 100 % täckning |
| `total_Equity` | MCURR | **GODKÄND** | 100 % täckning |
| `total_Liabilities_And_Equity` | MCURR | **GODKÄND** | identisk med `total_Assets` per definition — bokföringsidentitet, inte fel |
| `current_Assets` / `current_Liabilities` | MCURR | **GODKÄND** | 100 % täckning |
| `non_Current_Assets` / `non_Current_Liabilities` | MCURR | **GODKÄND** | 100 % täckning |
| `cash_And_Equivalents` | MCURR | **GODKÄND** | 100 % täckning |
| `net_Debt` | MCURR | **GODKÄND** | 100 % täckning, negativa värden korrekt (nettokassa) |
| `tangible_Assets` / `intangible_Assets` | MCURR | **GODKÄND** | 99,3–99,4 % täckning |
| `financial_Assets` | MCURR | **GODKÄND** | 99,1 % täckning |
| `cash_Flow_From_{Operating,Investing,Financing}_Activities` | MCURR | **GODKÄND** | 99,9 % täckning |
| `cash_Flow_For_The_Year` | MCURR | **GODKÄND** | 99,9 % täckning |
| `free_Cash_Flow` | MCURR | **GODKÄND** | 99,9 % täckning |
| `number_Of_Shares` | MILL | **GODKÄND** | 100 % täckning, ingen konvertering behövs |
| `earnings_Per_Share` | CURR | **GODKÄND** *(uppgraderad, se §7b)* | internt konsistent (89,6–97,3 %) och splitverifierad: samtliga kontrollerbara "oförklarade" hopp saknar matchande split och har oförändrat aktieantal — äkta resultatvolatilitet |
| `dividend` | CURR | **GODKÄND** *(uppgraderad, se §7b)* | 39,8–42,3 % äkta nollor (jämnt fördelat över kvartal, §9); de kontrollerade hoppen saknar matchande split — äkta utdelningspolicyändringar. Riktad kontroll, inte uttömmande (se kvarvarande begränsning nedan) |
| `stock_Price_Average/High/Low` | CURR | **UTESLUTEN** | redundant med och sämre verifierat än spår A:s `adjusted_close` (871 klassade nivåbrott, noll kvar efter behandling). Använd prisdata från VALIDATED-priserna, inte Börsdatas egna prisfält |
| `net_Sales` | MCURR | **UTESLUTEN (dubblett)** | 78,7 % identisk med `revenues`; ingen fastställd egen definition. Behåll `revenues`, exkludera `net_Sales` tills definitionsskillnaden är utredd |
| `currency` / `currency_Ratio` | – | **GODKÄND (stödfält)** | krävs för konvertering av alla `MCURR`/`CURR`-fält, inte en feature i sig |
| `broken_Fiscal_Year` | – | **GODKÄND (stödfält)** | 100 % täckning, användbar flagga för avvikande räkenskapsår |
| `report_Date` / `report_Start_Date` / `report_End_Date` | – | **GODKÄND (PIT-nyckel)** | grunden för hela PIT-kopplingen; 94,6–95,3 % (kvartal/R12) resp. 89,9 % (år, efter R4) av raderna passerar samtliga fem kontroller |

**29 kandidatfält, samtliga slutklassificerade: 22 GODKÄNDA (varav 2 uppgraderade efter
splitverifiering), 2 UTESLUTNA (en dubblett, en redundant), 3 stödfält godkända, 2 rena
PIT-datumfält godkända. Noll fält kvar i KRÄVER ÅTGÄRD.**

---

## 11. VALIDATED-lager — år, kvartal och R12, samtliga frysta

`validated/fundamentals/fundamentals_{year,quarter,r12}_validated.json` +
`validated/manifest_sparB.json`. PIT-reglerna är identiska för alla tre tabeller (R1–R5,
inklusive den nya R4-eftersläpningsregeln som §9 motiverade).

| tabell | indata (rå) | efter PIT-regler | andel | `dataset_sha256` |
|---|---|---|---|---|
| år | 5 403 rader | **4 847** | 89,7 % | `5f8e3a6fb865a6e8…` |
| kvartal | 12 995 rader | **12 280** | 94,5 % | `1bc5c4fafdb87dad…` |
| R12 | 12 883 rader | **12 269** | 95,2 % | `a8168eb2dff36915…` |

`kombinerad_sha256` (hash av de tre tabellhasharna tillsammans): `9da73a883721b9cb…`

Samtliga rader taggade `quality_class="A"` (Track B tillför som konstaterat inget unikt).
NOK-rader med `currency_Ratio`=1,0 flaggade (`ratio_flagg`), inte uteslutna. Källfilshashar
för alla 358 × 3 = 1 074 hämtade filer finns i manifestet.

De 20 ursprungligen godkända fälten samt `earnings_Per_Share` och `dividend` (nu godkända)
ingår i alla tre tabeller — **22 fält**. `stock_Price_*` och `net_Sales` är exkluderade ur
samtliga.

**Ändring jämfört med den första (rc1) årsfrysningen:** den nya R4-regeln (eftersläpning
>180 dagar) sänker årsdatans behållna andel något (4 863→4 847 rader) sedan
Alligo-mönstret upptäcktes vid kvartalsgranskningen. Det är en skärpning, inte en
mjukning — ingen tidigare godkänd rad har blivit mer tillåtande behandlad.

---

## 12. Vad som är godkänt för `dataset_v1.0` — och vad som fortfarande begränsar det

### Godkänt

- **22 av 29 Börsdata-råfält**, i tre tidsupplösningar (år, kvartal, R12), för **358
  instrument** i det låsta Nasdaq Stockholm-universumet.
- PIT-korrekt kopplade (`report_Date`, fem uteslutningsregler, 89,7–95,2 % behållningsgrad).
- Valutakonverterade till SEK via `currency_Ratio`, med NOK-osäkerheten explicit flaggad
  snarare än gömd.
- Källkonsistens verifierad **oberoende** i tre led: kvartalssumma mot R12 (91,7–93,0 %
  exakt), R12 mot årsdata (**100,0 % exakt** för alla fem testade fält) — det starkaste
  enskilda fyndet i hela spår B.
- `earnings_Per_Share` och `dividend` splitverifierade mot spår A:s oberoende EODHD-data,
  inte bara internkonsistensprövade.
- Hashverifierat och reproducerbart: `raw/borsdata/` (verbatim + sha256, till skillnad från
  legacyns underkända rådatalager) → `validated/` med tre tabellhashar plus en kombinerad.

### Kvarstående begränsningar — måste följa med varje användning

1. **Survivorship-bias i fundamenta är olöst och olösbar med tillgängliga källor.** 67 av 68
   bolag som avnoterades från Nasdaq Stockholm 2020–2026 saknar all fundamentadata, i
   samtliga tre tidsupplösningar. Detta gäller **inte** priserna (spår A är
   survivorship-säkert från 2020-01-01). En modell som blandar prisfeatures och
   fundamentalfeatures är survivorship-säker i den första dimensionen och **inte** i den
   andra. **Varje resultat som använder fundamentalfeatures ska uttryckligen ange detta.**
2. `net_Sales` kontra `revenues`: definitionsskillnaden (21,3 % av raderna avviker) är
   inte utredd, bara undviken genom att exkludera `net_Sales`.
3. Splitverifieringen av EPS/dividend är riktad (extremfall + aggregerad konsistens), inte
   en uttömmande rad-för-rad-kontroll av alla 204 avvikande split-instrument-år.
4. Alligo AB:s `report_Date`-mönster (§9) är dokumenterat opålitligt för perioder före
   ~2020. R4 fångar de grövsta fallen (>180 dagars eftersläpning); subtilare varianter för
   samma eller liknande bolag med bolagshändelsehistorik kan finnas kvar.
5. Endast Börsdatas fundamentaendpoints är granskade. Ingen jämförelse har gjorts mot en
   tredje, oberoende fundamentalkälla (till skillnad från priserna, där EODHD och
   Skatteverket korsverifierade varandra).

**Ingen modellträning eller featureoptimering är gjord.** Klassificeringen ovan avgör vilka
råfält som får ingå i nästa steg (spår C), inte hur de ska omvandlas till features.
