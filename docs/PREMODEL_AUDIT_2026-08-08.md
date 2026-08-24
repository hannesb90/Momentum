# Oberoende pre-model audit av Spår A, B och C — dataset_v1.0

Datum: 2026-08-08. **Allt modellarbete stoppat.** Denna audit har gjorts oberoende, med
uttrycklig avsikt att falsifiera tidigare påståenden, inte bekräfta dem. **Ett verkligt,
allvarligt fel hittades. Ingen hash har ändrats, inget spår har öppnats om. Rapporten
STANNAR HÄR, som instruerat, i väntan på beslut om hur felet ska åtgärdas.**

Verktyg (nyskrivna för denna audit, inte återanvändning av tidigare QA-kod):
oberoende hashjämförelser, en fristående ombyggnad av `target_table.json` och
`core_panel.json` i en isolerad katalog, två ablationstester (fysiskt borttagen
framtidsdata, inte bara filter), samt en fullständig genomgång av Skatteverket→
EODHD/Börsdata-identitetskedjan för samtliga instrument med tvetydig mappning.

---

## SLUTSATSER (svar på de 8 punkterna)

1. **Är A reproducerbart och buggrent?** Reproducerbart: ja, verifierat. **Buggrent: NEJ.**
   Ett bekräftat, allvarligt fel i R2-truncation (§1) påverkar minst 7 instrument.
2. **Är B reproducerbart och buggrent?** **JA** till båda, med en mindre reservation
   (§1.5): B:s fundamenta för de 7 buggiga instrumenten FINNS och är korrekta i sig — de
   är bara osynliga i C på grund av A:s fel.
3. **Är C reproducerbart och buggrent?** Reproducerbart: ja (strukturell PIT/läckage-QA
   om körs, se §1.6). **Buggrent: NEJ** — C ärver A:s fel fullt ut, och förvärrar det genom
   att även kassera redan hämtad, giltig fundamentadata för samma instrument (§1.5).
4. **Är B:s fundamentainventering komplett?** **NEJ.** Börsdatas KPI-system (234 nyckeltal,
   aldrig tidigare inventerat) exponerar minst tre kategorier data som helt saknas i de
   22 godkända råfälten: **EBITDA, Capex, och — mest väsentligt — faktiska
   återköpsbelopp (Återköp Mkr)**, se DEL 2.
5. **Vilka relevanta råfält har missats?** EBITDA (KPI 54), Capex (KPI 64), färdigberäknad
   ROIC (KPI 37), Nettoskuld/EBITDA (KPI 42), samt — head route möjliggör en indirekt men
   verklig **skatteproxy** ur redan godkända fält (`profit_Before_Tax −
   profit_To_Equity_Holders`), se DEL 2.
6. **Vilka nya featuremöjligheter skapar detta?** Riktig EBITDA-marginal, riktig
   EV/EBITDA-liknande värdering, en skattejusterad ROIC (löser den tidigare dokumenterade
   bristen i `roic_proxy_ttm`), samt en genuin `shareholder_yield` (utdelning + återköp) —
   den familjemedlem som tidigare klassades SAKNAR DATA i C:s blueprint är **inte längre
   korrekt klassad**.
7. **Behöver C öppnas igen?** **JA, oundvikligt** — dels för att rätta A:s fel (vilket
   rippling påverkar C:s paneler), dels för att bygga de nya fundamentafälten DEL 2 avslöjat.
8. **Är dataset_v1.0 redo för Spår D?** **NEJ.** Se sammanfattande tabell nedan.

| komponent | reproducerbart | buggrent | redo för Spår D |
|---|---|---|---|
| Spår A (priser) | ✅ | ❌ (7 instrument, R2-fel) | Nej |
| Spår B (fundamenta) | ✅ | ✅ (med reservation) | Delvis — completeness-gap |
| Spår C (paneler) | ✅ (struktur) | ❌ (ärver A:s fel) | Nej |

---

# DEL 1 — BUGG-/REPRODUCERBARHETSAUDIT

## 1. HUVUDFYND: 7 instrument felaktigt trunkerade i Spår A — BUGG, hög allvarlighetsgrad

### 1.1 Upptäckt

En systematisk kontroll korsreferererade **varje** instrument vars prisserie slutar före
datasetets globala slutdatum (2026-07-24) mot Börsdatas **aktuella** lista över levande
Nasdaq Stockholm-instrument (`marketId` 1/2/3). Om ett "avnoterat" instruments ISIN
fortfarande är levande hos Börsdata **idag**, är trunkeringen bevisligen fel — Börsdata har
redan visats radera avnoterade bolag ur sitt register (`UNIVERSUM_OCH_KALLBESLUT.md`), så
ett kvarvarande ISIN är ett direkt motbevis mot en påstådd avnotering.

**14 instrument** klarade inte detta test. Av dessa var **3 redan kända och dokumenterade**
(FLERIE/MQ/ORRON — R7/R8-segmentering i `PRIS_QA_KLASSIFICERING.md`) och **2 redan
dokumenterade som "inte en äkta död"** (BESQAB, CCC). **7 var HELT ONYA fynd:**

| kod | bolag | trunkerad vid | förlorad handelshistorik | orsak (falsk avnotering) |
|---|---|---|---|---|
| **SBB-B** | Samhällsbyggnadsbolaget i Norden | 2021-04-21 | **5 år** | "Avnotering av **preferensaktien** från First North" — fel aktieslag |
| **KINV-A** | Kinnevik AB | 2025-03-17 | 1 år | Millicom (historiskt närstående, annat bolag) SDB-avnotering felaktigt tillskriven Kinnevik |
| **HUFV-A** | Hufvudstaden AB | 2020-01-30 | **6 år** | "**C-aktierna** är avnoterade" — fel aktieslag |
| **SAGA-B** | Sagax AB | 2021-04-01 | 5 år | "**Preferensaktierna** avnoterades" — fel aktieslag |
| **VEFAB** | VEF AB | 2021-07-02 | 5 år | "**SDB** avnoterade från First North" — fel instrumenttyp (depåbevis, inte stamaktien) |
| **FPAR-A** | Fast Partner AB | 2022-03-23 | 4 år | "**Preferensaktien** avnoterad" — fel aktieslag |
| **SFAST** | Stenhus Fastigheter i Norden | 2022-08-31 | 3 år | Halmslätten Fastighets AB (annat bolag/ISIN-sammanblandning) |

Samtliga 7 verifierade **levande idag** genom att deras ISIN återfinns i Börsdatas
`instruments_live.json` med `marketId` 1/2/3.

### 1.2 Rotorsak

`instrument_master.py` extraherar `avnoterad_datum` från Skatteverkets aktiehistorik-sidor
genom att leta efter ordet "avnoterad" i sidans händelsetabell. **Skatteverkets sidor
beskriver ibland FLERA värdepapper för samma bolag på en och samma sida** —
stamaktien, preferensaktien, C-aktien, ett depåbevis (SDB) — och när **en annan klass**
avnoteras skrivs det på **samma sida** som stamaktiens historik. Parsern skiljer inte på
"detta värdepapper avnoterat" och "ett släktat värdepapper på samma sida avnoterat".

En sekundär, förstärkande brist: kopplingen `kod2post[kod] = r` /
`avnoterad[kod] = r["avnoterad_datum"]` i både `instrument_master.py` och (identiskt)
`build_validated_prices.py` **skriver över** vid varje ny matchande post, utan
tie-breaking-logik. När flera Skatteverket-poster (namnbyten, aktieslag, släktade bolag)
mappar till samma EODHD-kod avgörs resultatet av **godtycklig array-ordning**, inte av en
avsiktlig regel. I flera av dessa 7 fall var det FAKTISKT den korrekta posten som "vann"
(t.ex. IAR-B, GUNN — kontrollerade separat, **inga fel** där) — men det är tur, inte
garanti. Se §1.3 för hur detta upptäcktes.

### 1.3 Falsifieringsmetod

Jag försökte aktivt motbevisa varje "avnoterad"-post genom att:
1. Identifiera ALLA instrument vars serie slutar för tidigt (14 kandidater).
2. För varje kandidat: läsa den FULLA `avnoterad_orsak`-texten, inte bara datumet.
3. Leta efter ord som avslöjar fel aktieslag: **"preferensaktie", "C-aktie", "SDB"** —
   samtliga 5 av de 7 nya fallen innehåller ett sådant ord explicit i den egna
   `avnoterad_orsak`-texten som redan låg lagrad i `instrument_master.json`. Felet var
   **synligt i den befintliga datan hela tiden** — det krävde bara att någon läste
   `avnoterad_orsak`-fältet kritiskt i stället för att bara konsumera `avnoterad_datum`.

### 1.4 Kvarstående, okvantifierad risk

Testet ovan (`ISIN fortfarande levande idag`) fångar bara de **grövsta** felen — där
bolaget är levande **just nu**. Samma rotorsak (fel aktieslag/närstående bolag på samma
Skatteverket-sida) kan i princip ha gett **subtilt fel** trunkeringsdatum även för bolag
som **faktiskt är döda** (avnoteringen är riktig, men datumet kan vara några veckor eller
månader förskjutet eftersom det kom från fel akties egen händelse). **Detta är inte
kvantifierat** i denna audit — det kräver en fullständig genomgång av samtliga ~90
avnoteringsposter i `instrument_master.json` med `avnoterad_orsak`-texten läst manuellt
eller mönstermatchad mot orden "preferensaktie/C-aktie/D-aktie/SDB/depåbevis", inte bara de
14 som redan flaggats via livstestet.

### 1.5 Konsekvens för Spår B och C

Kontrollerat explicit: samtliga 7 buggiga instrument **matchades korrekt och fick sin
fundamentadata hämtad live** i Spår B:s Track A (`raw/borsdata/_matchning.json` bekräftar
`SBB-B insId=438`, `KINV-A insId=1618`, osv. — matchningen sker via ISIN mot dagens levande
Börsdata-lista, en **annan, opåverkad** kodväg än A:s avnoterad-baserade trunkering).
**Spår B:s data för dessa bolag är alltså korrekt och fullständig 2021–2026.**

Men i Spår C är den **osynlig**: `core_panel.json` genererar rader för ett instrument bara
inom dess **prisseries** datumintervall (styrt av Spår A). Eftersom SBB-B:s prisserie
felaktigt slutar 2021-04-21 finns **inga panelrader alls** för SBB-B efter det datumet —
varken pris-, fundamenta- eller targetrader — trots att både priser (hos EODHD) och
fundamenta (redan hämtat i Spår B) finns tillgängliga. **Bugg-effekten är alltså inte
begränsad till priser: den kasserar tyst redan validerad fundamentadata för samma sju bolag,
inklusive Kinneviks och SBB:s dramatiska 2022–2023-period** — exakt den sortens
händelserika, informativa marknadsdata en riskmedveten modell mest skulle vilja lära av.

### 1.6 Övriga strukturella kontroller — GODKÄNDA

| kontroll | metod | utfall |
|---|---|---|
| Determinism, `target_table.json` | fristående ombyggnad i isolerad katalog, hashjämförelse | **bit-identisk** (`8a0b44e7…`) |
| Reproducerbarhet, Spår B:s kanoniserade hashar | omräknad exakt samma serialisering | **reproduceras** för alla tre tabeller (år/kvartal/R12) |
| `manifest_sparC.json` panel-hashar mot filer på disk | `sha256sum`-jämförelse | **matchar exakt** för alla tre paneler |
| Legacy-import/tysta globala defaults | grep av samtliga `tools/*.py` | **inga** kod-/config-importer från legacy; endast dokumenterade read-only `Path`-konstanter |
| CORE rör aldrig Spår B | grep efter "fundament"/"R12" i `spar_c_features_core_v2.py` | **bekräftat, 0 träffar** |
| `has_fundamenta` sätts alltid | kodgranskning | **bekräftat**, båda grenarna (finns/finns ej) sätter flaggan |
| Datum/tidszon | sökning efter `T00:00:00`-suffix i VALIDATED och paneler | **0 träffar**, rena `YYYY-MM-DD` genomgående |
| Rebalance = 4v | unika steg mellan samtliga panel_date | **exakt 28 dagar, inga undantag** |
| Target = 52v | oberoende omräkning, 20 slumpade rader | **0 avvikelser** |
| PIT/läckage, CORE | **ablationstest**: framtidsdata fysiskt borttagen, features omräknade oberoende | **0 avvikelser av 15 stickprov** |
| PIT/läckage, FUNDAMENTA | **ablationstest**: rapporter efter panel_date fysiskt borttagna | **0 avvikelser av 15 stickprov** |
| Inga target-/framtidsfält i features | kolumnnamnsgranskning + strukturell separation | **bekräftat** |
| Determinism, `core_panel.json` | fristående ombyggnad, 404 instrument, isolerad katalog | **bit-identisk** (`8515697d…`) |

### 1.7 Övriga fynd, RISK (låg allvarlighetsgrad, inte blockerande)

| fynd | omfattning | bedömning |
|---|---|---|
| **Utdragna handelsuppehåll ger inaktuella "aktuella" priser** — NEOBO (371 dagars lucka, SBB/Amasten/Neobo-omstrukturering), RIZZO-B | 19/28 539 rader (0,07 %), 2 instrument | äkta marknadshändelse, inte läckage — men en modell kan feltolka den frusna kortsiktiga volatiliteten som informativ. Ej åtgärdat. |
| **EODHD:s rådata är några dagar–månader efter** för enstaka tickers (NYF −10d, FPIP/MAHA-A −7d, KDEV −3 mån) | 4 instrument | källdata-eftersläpning, inte ett fel i vår pipeline — kan inte hämtas fräschare än arkivet tillåter |
| `fcf_yield_ttm` saknar materialitetsgrind mot börsvärde | redan dokumenterat i `feature_registry.json` | ej ny upptäckt, bekräftad kvarstående begränsning |
| ISIN-dubbletter inom universumet (12 st) | endast identitetskedjan, inte panelen (dict-nycklade, ingen dubblettrad) | inget dataintegritetsproblem i sig, men VAR grundorsaken till §1:s fynd |

---

# DEL 2 — FUNDAMENTAL BLUEPRINT / COMPLETENESS-AUDIT AV SPÅR B

## 2.1 Metod

Startade om helt från Börsdatas **rådata-metadata**, inte de 22 godkända fälten. Två
endpoints granskade:

- `/v1/instruments/reports/metadata` — redan känd, **37 fält** (rapportradata).
- **`/v1/instruments/kpis/metadata` — ALDRIG tidigare hämtad eller granskad.** 1 nytt
  API-anrop (read-only, sparat verbatim + sha256 i `raw/borsdata/metadata/`).
  **234 nyckeltal.**

Utöver detta: kontrollerade om finansbolag (SEB testad) har ett annat radschema än
standardbolag — **nej, exakt samma 37 fält**, men flera fält är **strukturellt
noll/odefinierade** för banker (`current_Assets=0`, `current_Liabilities=0`, `net_Debt=0`
eftersom klassisk kort-/långfristig balansräkningsindelning och nettoskuld-begreppet inte
är meningsfullt för en bank). Det är korrekt `null`-hantering i vår pipeline, inte ett fel
— men det betyder att `current_ratio` och `net_debt_to_equity` i praktiken är
**bransch-specifikt meningslösa/urblekta för finanssektorn**, inte tidigare dokumenterat.

## 2.2 Checklistan, fält för fält

| begärd post | finns i de 37 rapportfälten? | finns i KPI-systemet (234)? | bedömning |
|---|---|---|---|
| Revenue/net sales | ✅ `revenues`, `net_Sales` | ✅ KPI 53 | GODKÄND (redan i Spår B) |
| Gross profit | ✅ `gross_Income` | ✅ KPI 135 | GODKÄND |
| **EBITDA** | ❌ | ✅ **KPI 54** (MCURR) | **SAKNAS I SPÅR B — bör läggas till** |
| EBIT/operating income | ✅ `operating_Income` | ✅ KPI 55 | GODKÄND |
| Net income | ✅ `profit_To_Equity_Holders` | ✅ KPI 56 | GODKÄND |
| EPS | ✅ `earnings_Per_Share` | ✅ KPI 6 | GODKÄND |
| Assets | ✅ `total_Assets` | ✅ KPI 57 | GODKÄND |
| Equity | ✅ `total_Equity` | ✅ KPI 58 | GODKÄND |
| Cash | ✅ `cash_And_Equivalents` | ✅ KPI 130 | GODKÄND |
| Total/net debt | ✅ `net_Debt` | ✅ KPI 41/60 | GODKÄND (endast netto, ingen brutto-/kort-lång-uppdelning någonstans) |
| Short/long debt (separat) | ❌ | ❌ | **SAKNAS ÖVERALLT** — Börsdata exponerar bara nettoskuld, aldrig komponenter |
| Interest expense/income | ❌ | ~ delvis (KPI 278, endast fastighetssektor) | **SAKNAS** som generellt fält |
| Tax | ❌ direkt | ❌ direkt, men **derivarbar** ur `profit_Before_Tax − profit_To_Equity_Holders` | KRÄVER ÅTGÄRD → se §2.4 |
| Operating cash flow | ✅ `cash_Flow_From_Operating_Activities` | ✅ KPI 62 | GODKÄND |
| FCF | ✅ `free_Cash_Flow` | ✅ KPI 63 | GODKÄND |
| **Capex** | ❌ direkt | ✅ **KPI 64** (MCURR, direkt fält — inte bara OCF−FCF-derivering) | **SAKNAS I SPÅR B — bör läggas till** |
| Working capital-komponenter | ❌ | endast aggregat (KPI 93, Rörelsekapital-%) | **SAKNAS**, ingen komponentnivå någonstans |
| Receivables | ❌ | ❌ | **SAKNAS helt** i alla Börsdata-endpoints vi hittat |
| Inventory | ❌ | ❌ | **SAKNAS helt** |
| Payables | ❌ | ❌ | **SAKNAS helt** |
| Goodwill (separat från övriga immateriella) | ❌ endast `intangible_Assets` (aggregat) | ❌ samma aggregat (KPI 126) | **SAKNAS separat**, bara den sammanslagna posten finns |
| Shares outstanding | ✅ `number_Of_Shares` | ✅ KPI 61 | GODKÄND |
| Dilution/emissions | ❌ direkt (endast härledbar via `shares_growth_yoy`) | ❌ direkt | delvis täckt, ingen ren "nyemission"-post |
| **Buybacks** | ❌ | ✅ **KPI 213–215** ("Återköp Mkr" 1 mån/3 mån/1 år) | **SAKNAS I SPÅR B — DIREKT MOTSVARIGHET TILL DET TIDIGARE DOKUMENTERADE GAPET, bör läggas till** |
| Dividends | ✅ `dividend` | ✅ KPI 7 | GODKÄND |
| ROIC (färdigberäknad) | ❌ | ✅ **KPI 37** | Börsdata har redan en egen ROIC — vår `roic_proxy_ttm` behöver INTE vara en approximation |
| Net Debt/EBITDA | ❌ | ✅ KPI 42 | ny, användbar leverage/kvalitetskvot |

## 2.3 Sammanfattning: 3 tydliga, konkreta luckor

1. **EBITDA** (KPI 54) — direkt fält, ingen anledning att fortsätta sakna det.
2. **Capex** (KPI 64) — direkt fält, förbättrar `roic_proxy_ttm`, möjliggör `capex_intensity`
   (capex/revenue) och en riktig FCF-härledning i stället för att bara ta `free_Cash_Flow`
   som given.
3. **Återköp (Återköp Mkr, KPI 213–215)** — **löser explicit det tidigare dokumenterade
   SAKNAR DATA-beslutet för `shareholder_yield`** i `feature_blueprint.json`. Det beslutet
   var **fel** — inte för att resonemanget var ologiskt, utan för att sökningen bara
   omfattade rapportfälten (37), aldrig KPI-systemet (234).

## 2.4 Ny featuremöjlighet: skattejusterad ROIC

`profit_Before_Tax − profit_To_Equity_Holders` ger en implicit skatt+minoritetspost.
Stickprov (10 slumpade R12-rader) gav 20–27 % för de flesta bolag — konsekvent med svensk
bolagsskatt (20,6 %) plus viss minoritetsandelseffekt, med enstaka instabila utfall nära
noll-resultat (samma nära-noll-bas-mönster som redan hanteras via materialitetsregeln för
andra kvoter). Detta betyder att `roic_proxy_ttm`:s tidigare dokumenterade begränsning
("FÖRE-skatt-approximation, ingen skattefältvariabel tillgänglig") **inte längre är sann i
sak** — en skattejusterad variant är byggbar ur redan godkända fält, utan någon ny
datahämtning.

## 2.5 Vad som fortfarande INTE finns, bekräftat efter denna bredare sökning

Working capital-komponenter (kundfordringar/lager/leverantörsskulder), goodwill separat
från övriga immateriella tillgångar, brutto-/kort-/långfristig skulduppdelning, och en
generell räntekostnadspost saknas **även i det 234-punkters KPI-systemet** — det är alltså
inte bara en fråga om att vi tittat på fel endpoint tidigare. Dessa dimensioner är
**genuint otillgängliga** hos Börsdata för detta universum, inte ett tidigare
sökningsmisstag. `working_capital_efficiency`, `receivables_days`, `goodwill_exposure` och
`interest_coverage` (generellt, ej fastighetssektor-specifikt) kvarstår som **SAKNAR DATA**.

---

## 3. Vad som INTE gjorts i denna audit (ärligt redovisat)

- §1.4:s okvantifierade risk (subtilt fel trunkeringsdatum för redan döda bolag) är
  **inte genomsökt** — bara de 14 grövsta (levande-idag-testade) fallen är kända med
  säkerhet.
- Ingen ny data har hämtats för EBITDA/Capex/återköp — bara bekräftat att de **finns** och
  är hämtningsbara.

---

## 4. STOPP — inget har ändrats

**Ingen hash i `validated/` eller `panels/` har rörts.** Denna rapport är en revision, inte
en åtgärd. Nästa steg (rätta §1:s bugg i `instrument_master.py`/`build_validated_prices.py`,
genomsöka §1.4:s okvantifierade risk fullständigt, och hämta EBITDA/Capex/återköp från
KPI-systemet för att bygga om Spår B och C) kräver ett nytt, explicit uppdrag — de
påbörjas inte här.
