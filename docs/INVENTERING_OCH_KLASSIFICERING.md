# Inventering och klassificering av befintlig rådata och API-kod

Datum: 2026-08-07. Fas 1 av omstarten mot ett fristående `dataset_v1.0`.

**Inget har flyttats, kopierats eller migrerats.** Denna fil och katalogen
`/home/hannesb/momentum_v2/` innehåller enbart ny dokumentation. Legacy
(`/home/hannesb/momentum_prod_work/`) har inte ändrats — utom att den provisoriska
panelen från det avbrutna bygget satts i karantän som
`cache/researchdb_v1/_panel_v2_PROVISORISK_ANVAND_EJ/`.

**Läsanvisning:** kategori 1 betyder "inget omtolkningsarbete krävs, bara mekanisk
verifiering". Ingen källa är slutverifierad ännu — hashåterspelning och
fullständighetskontroll är *inte* körda. Varje post anger exakt vilken verifiering
som återstår.

---

## 0. Sammanfattning

| kategori | källor | volym |
|---|---|---|
| **1** – säker att migrera efter mekanisk verifiering | 2 | ~445 MB |
| **2** – kräver QA/korrigering | 5 | ~1,2 GB |
| **3** – ska hämtas om från API | 5 | ~570 MB (kasseras) |
| **4** – lämnas i legacy | 12+ | ~2,5 GB |

Den viktigaste enskilda slutsatsen: **ett korrekt uppbyggt rådatalager finns redan**
(`cache/researchdb_v1/raw/`, byggt 2026-08-06) med verbatim API-svar, sha256 per
hämtning, endpointpartitionering och append-only-manifest. Det uppfyller v2:s krav
på RAW-lagret *till formen*. Det är däremot **ofullständigt** (678 av 1 715 instrument,
ingen full prishistorik, inga avnoterade bolag) och dess egen validering flaggar redan
73 look-ahead-rader och 959 rader utan publiceringsdatum.

Näst viktigast: **prisdatan är det svagaste ledet.** Den enda källa som alls hanterar
avnoterade bolag är `cache/eodhd_archive/` — och den har aldrig använts av modellen.
Prisdatan som modellen faktiskt tränat på ligger i 18 md5-namngivna pickles utan
härkomstinformation.

---

## 1. KATEGORI 1 — säker att migrera efter mekanisk verifiering

### 1.1 `momentum_ml/cache/researchdb_v1/raw/` — Börsdata rådatalager
360 MB, 2 047 endpointkataloger, 2 085 hämtningar, byggt 2026-08-06.

| egenskap | status |
|---|---|
| verbatim API-svar | ja, `{meta, payload}`-kuvert, aldrig överskrivet |
| endpoint per katalog | ja (`instruments_<id>_reports_year` osv.) |
| tidsstämplad filnamnsrymd | ja (`<key>__<UTC>Z.json`) |
| checksumma | **sha256 på 2 085/2 085 hämtningar** |
| manifest | `_manifest.jsonl`, append-only, med `endpoint`, `params`, `http_status`, `instrument`, `n_rows`, `datasource` |

Innehåll: `instruments` (1 715 instrument), `sectors`, `markets`, `branches`, `countries`,
`translationmetadata`, `instruments_kpis_metadata`, `instruments_stocksplits`,
`instruments_stockprices` (**endast senaste kurs, inte historik**),
`holdings_{insider,buyback,shorts}`, samt `reports_{year,r12,quarter}` för **678** instrument.

**Återstående verifiering före migrering:**
1. Räkna om sha256 för varje fil och jämför mot manifestet (mekanisk, inget omdöme).
2. Bekräfta att `params` i manifestet motsvarar det som faktiskt efterfrågades
   (särskilt `maxYearCount`/`maxR12Count`/`maxQuarterCount`).
3. Dokumentera att `instruments_stockprices` **inte** är historik.
4. Notera täckningsgapet: 678 av 1 715 instrument har rapporter.

### 1.2 `momentum_ml/cache/eodhd_archive/ST/` — prisarkiv med avnoterade bolag
85 MB, 5 119 filer, uppdelat i `active/` (3 031 filer) och `delisted/` (2 083 filer),
vardera med `eod/`, `div/`, `splits/` (gzippade per ticker) och `manifest.json`,
plus `active_catalogue.json` (1 010 instrument) och `delisted_catalogue.json`.

Detta är **den enda källan i hela projektet som innehåller avnoterade bolag** och
därmed den enda som kan ge ett survivorship-fritt universum. Den innehåller dessutom
utdelnings- och splitserier separat från kurserna, vilket är exakt den uppdelning v2
behöver för att kunna göra justeringar explicita i stället för implicita.

Katalogen innehåller både `Type: FUND`, `Common Stock` m.m. — instrumenttypen måste
filtreras explicit i VALIDATED-steget, inte antas.

**Återstående verifiering:** manifestens fullständighet, att `adjusted_close` och `close`
är konsistenta med `splits`/`div`-serierna, samt licens-/avtalsfrågan för vidare
användning av EODHD-data.

---

## 2. KATEGORI 2 — kräver QA/korrigering

### 2.1 `cache/borsdata/reports_*_max20y.json` (732 filer) — årsrapporter, 20 år
Den djupaste fundamentalhistoriken som finns (2006–2025). **Kända defekter, mätta 2026-08-07:**
- 1 104 av 9 602 rader (11,5 %) saknar `report_Date` → kan inte PIT-dateras. Sämst 2014–2016 (75 % med datum).
- 8 rader med epokdatum (1899-12-30), 95 rader med `available_date` före rapportperiodens slut.
- **Per aktie-fälten är retroaktivt splitjusterade** till dagens aktieantal. ENRO.ST 2007 får
  `dividend` 1 025 100 och EPS 1 434 066 vid 900 utestående aktier. Det är inte ett enhetsfel —
  det är en dokumenterad egenskap som gör *nivåer* icke-PIT och *kvoter* giltiga utom över splitar.

### 2.2 `cache/borsdata/quarterly/reports_*_{quarter,r12}_max40.json` (1 464 filer)
Ligger på API:ts tak (40 kvartal, verifierat 2026-08-07 med `maxCount` 40/80/160/400 → alltid 40).
Räckvidden beror därför på *hämtningsdatum*, inte på bolaget: äldsta kvartal ≈ 2016.
Måste dokumenteras som ett rullande fönster, inte som "historik".

### 2.3 `cache/mfn/*.json` (1 062 filer, 972 MB) — MFN-pressmeddelanden
Leverantörspayload med `{ticker, query, schema, items}`. Rådatakaraktär, men **den härledda
extraktionen är svag**: `results/fundamentals_from_mfn.csv` har 3 805 rader men bara
**8 utdelningsvärden**, 1 793 av 2 010 intäktsrader saknar enhetsangivelse, och enheterna är
fritext (`MSEK`, `Mkr`, `mkr`, `miljoner kronor`, `Tkr`, `TSEK`). Rådatan kan migreras;
extraktionen måste byggas om från grunden.

### 2.4 `cache/fi_insyn/` (719 filer) och `cache/fi_blankning/` (2 filer)
Finansinspektionens insyns- respektive blankningsregister. Nyckelnamn är bolagsnamn
(`Yubico.json`, `Yubico_AB.json`) — **inte instrument-id**, vilket ger dubbletter och
kopplingsrisk mot tickerhistorik. Kräver namnnormalisering och PIT-datumkontroll.

### 2.5 `cache/aktiehistorik/` (735 filer, 69 MB)
Skrapad HTML plus `ticker_match.json` och `survival_facts.json`. Enda källan för
historisk noterings-/avnoteringsinformation vid sidan av EODHD. Kräver källgranskning
(skrapning, ingen API-garanti) innan något av det används för universumdefinition.

---

## 3. KATEGORI 3 — ska hämtas om från API

### 3.1 `cache/borsdata/reports_*_max20.json` (732 filer) — **defekt hämtning**
Hämtade med `maxCount` mot den *kombinerade* `/reports`-endpointen, som inte tar den
parametern. Resultat: 10 årsrader och 10 kvartalsrader per bolag i stället för avsedda 20/40.
Felet är dokumenterat i `altdata/borsdata.py`. Filerna är ersatta av 2.1/2.2 och ska inte migreras.

### 3.2 `cache/borsdata/stockprices_*_max20.json` (573 filer)
Daglig historik men med 10-årstak (äldsta 2016-03-22) och **endast aktiva instrument**.
Ger survivorship bias om den används som prisgrund.

### 3.3 `cache/*.pkl` i projektroten (18 filer, 260 MB) — yfinance/Avanza-cache
Filnamn är `md5(cache_key)[:8]` — **härkomsten går inte att läsa ur filen**. Ingen endpoint,
inget hämtningsdatum, ingen checksumma. Det är denna data modellen faktiskt tränat på, och
den har dokumenterad glitchhistorik (`results/backup_contaminated_prices_20260803/`,
`data/extreme_jump_evidence.csv`, `ret_1w` med maxvärde 266 = +26 500 %/vecka).
**Kan inte verifieras i efterhand och ska inte migreras.**

### 3.4 `cache/borsdata/dividend_calendar_*.json` (42 filer)
Batchade med instrumentlistor i filnamnet (`dividend_calendar_104_1075_1689_…json`).
Nyckelrymden är oanvändbar för reproducerbarhet. Hämtas om per instrument.

### 3.5 Aldrig hämtat: avnoterade instrument från Börsdata
Ingen av de tre Börsdata-cacherna innehåller avnoterade bolag. Instrumentlistan (1 715)
är dagens noterade. Utan detta går survivorship inte att åtgärda på Börsdata-sidan —
bara via EODHD-arkivet (1.2).

---

## 4. KATEGORI 4 — lämnas i legacy

| källa | omfattning | skäl |
|---|---|---|
| `results/` | 748 filer, 2,0 GB | härledd forskningsutdata: `signals.csv`, `_features_cache_*.pkl`, `fundamentals*.csv`, `niva3_*`, 305 CSV/262 JSON/114 loggar. Byggbar ur RAW, och flera bär kända defekter. |
| `cache/features_by_ticker/` | 620 filer, 118 MB | härlett featurelager |
| `cache/sentiment/` | 8 800 filer | LLM-poängsatta pressmeddelanden — modellutdata, inte primärkälla |
| `cache/quality/`, `cfo_inflection/`, `otto_band/`, `global_relval/`, `etf_composition/` | ~1 700 filer | härledda score-/researchlager |
| `cache/researchdb_v1/{ablation,ablation48,diag,dosrespons,earlystop,fund_ab,fund_qa,luckfyllning,modellalder,pit,r1,tackning,topp30,validation}` | 63 filer | forskningsartefakter (inkl. denna veckas körningar) |
| `cache/researchdb_v1/_panel_v2_PROVISORISK_ANVAND_EJ/` | 2 filer | karantän, får inte användas |
| `cache/borsapi/` | 34 filer | äldre, parallell Börsdata-klient |
| `cache/eodhd/`, `cache/sentiment_benchmark/` | tomma | – |
| `momentum_ml/altdata/*.py` | 35 moduler, ~700 KB | legacy-API-kod, se §5 |
| `momentum_ml/data/data_loader.py` | 24 KB | yfinance/Avanza-lager |
| `momentum_ml/data/*.csv`, `*.json` | 7 filer | universum/sektorkartor — **återskapas i v2 ur instrumentlistan**, ärvs inte |

---

## 5. API-kod: klassificering

| modul | kategori | kommentar |
|---|---|---|
| `researchdb/rawstore.py` | **referens (4)** | Enda koden som redan följer v2:s principer: verbatim, sha256, append-only-manifest, ingen transformering. **Ska läsas som förlaga och skrivas om i v2** — den importerar legacy `config` och får därför inte importeras. |
| `researchdb/fetch_all.py` | referens (4) | endpointtäckning, batchgränser (`MAX_INSTLIST = 50`, verifierad) |
| `altdata/pit_validation.py` | referens (4) | reglerna (saknat/epok/look-ahead) är sunda och dokumenterade; implementeras om i v2 |
| `altdata/borsdata.py` | referens (4) | innehåller den dokumenterade `maxCount`-buggen och globala defaults ur `config` |
| `altdata/borsdata_quarterly.py` | referens (4) | `MAXCOUNT = 40` ligger på API-taket — bekräftat |
| `altdata/fundamentals*.py`, `fund_merge.py` | 4 | härledningslager, ersätts av v2:s explicita RAW→VALIDATED→PIT-steg |
| `altdata/mfn_*.py` (4 moduler, 133 KB) | 4 | textextraktion; byggs om vid behov |
| `altdata/eodhd.py` | referens (4) | behövs för att förstå arkivets format |
| `data/data_loader.py` | 4 | yfinance/Avanza med implicita globala defaults |
| övriga 25 `altdata`-moduler | 4 | screeners, sentiment, tradingview, soft_signals m.m. — inte datalager |

---

## 6. Riskregistret från inventeringen

Punkterna du bad om att särskilt kontrollera, med den evidens som redan finns:

| kontrollpunkt | status i legacy | konsekvens för v2 |
|---|---|---|
| **enheter/skala** | MFN har fritextenheter, 1 793 rader utan enhet; Börsdata per aktie-fält i miljonklassen efter omvända splitar | enhet ska vara ett **obligatoriskt, typat fält** i VALIDATED, aldrig gissat |
| **datumdefinitioner** | tre olika datum i Börsdatas rapporter (`report_Start_Date`, `report_End_Date`, `report_Date`); 11,5 % saknar `report_Date` | PIT-lagret får bara använda `report_Date`; rader utan det utesluts, aldrig approximeras |
| **NaN/sentinel** | `days_since_report` sentinel 365 (68 % av dev), `attention_gap` `fillna(0)` som betyder motsatsen till saknat | sentinelvärden ska vara **egna kolumner** (`*_is_missing`), aldrig kodade i värdet |
| **dubletter** | v1-valideringen: 0 dubbletter i rapporter och priser; FI-registret har namnbaserade dubletter | dubbletthantering på (instrument_id, period, endpoint) |
| **extremvärden** | `rev_growth`/`rev_accel`/`ni_growth` kvar >1,2 miljoner även efter 1/99-vinsorisering | extremvärden ska flaggas i QA, inte klippas bort tyst |
| **split-/utdelningsjustering** | Börsdata per aktie retroaktivt justerat; v1-valideringen flaggar 117 möjliga ojusterade splitar i priser | justering ska vara ett **eget, explicit steg** med sparade justeringsfaktorer |
| **instrument-/tickerhistorik** | ticker används som nyckel genom hela legacy; namnbyten och tickerbyten spåras inte | v2 ska nyckla på `insId`/ISIN, aldrig på ticker |
| **avnoterade bolag** | endast i EODHD-arkivet; Börsdata-cachen har bara dagens 1 715 noterade | universum måste byggas ur en källa med avnoterade, annars är allt survivorship-biased |
| **look-ahead** | v1-valideringen flaggar 73 look-ahead-rader; 95 i årsrapporterna | look-ahead-kontroll ska vara ett hårt test som fäller bygget, inte en varning |

---

## 7. Föreslagen ordning för nästa steg

1. **Verifiera 1.1 och 1.2 mekaniskt** (hashåterspelning, manifestfullständighet). Först
   därefter får något kopieras in i v2.
2. **Bestäm universumkälla.** Utan avnoterade bolag är resten meningslöst. EODHD-arkivet är
   enda kandidaten; alternativet är att acceptera survivorship och dokumentera det.
3. **Bygg v2:s RAW-hämtare** (förlaga: `rawstore.py`, men egen kod) och hämta om det som är
   kategori 3 — inklusive full prishistorik och, om möjligt, avnoterade instrument.
4. **Datadictionary och endpointregister** skrivs innan VALIDATED-lagret, inte efter.
5. **VALIDATED → PIT → FEATURES** som separata, testbara steg med egen QA-rapport per steg.
6. Frys `dataset_v1.0` med hash och versionsnummer.

**Ingen modell, inget backtest och ingen featureoptimering körs innan steg 6 är klart.**
