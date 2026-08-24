# Universumkälla och verifiering av kategori 1

Datum: 2026-08-07. Legacy lästes READ-ONLY. Allt nedan ligger under `momentum_v2/`.
Verktyg: `tools/verify_universe_mapping.py`, `tools/verify_rawstore.py`.
Artefakter: `docs/probes/{swagger_v1.json, instruments_live.json, universe_mapping.json,
rawstore_verification.json, eodhd_delisted_serier.json}`.

---

## Steg 1 — Kan Börsdata ge avnoterade eller historiska instrument? **Nej.**

Fem oberoende kontroller, alla med samma svar.

**1. Det auktoritativa schemat.** `https://apidoc.borsdata.se/swagger/v1/swagger.json`
(`apiservice`-värden ger 403/404 för schemat) listar **33 endpoints**. Ingen av dem gäller
avnoterade instrument. I hela schemat förekommer orden `delist`, `deleted`, `inactive`,
`removed` och `historic` **noll gånger**. Modellen `InstrumentV1` har fälten
`insId, name, urlName, instrument, isin, ticker, yahoo, sectorId, marketId, branchId,
countryId, listingDate, stockPriceCurrency, reportCurrency` — `listingDate` finns,
men **inget avnoteringsfält**.

**2. Odokumenterade endpoints.** `/instruments/delisted`, `/instruments/inactive`,
`/instruments/historical`, `/instruments/all` → samtliga **404**.

**3. Filterparametrar ignoreras tyst.** `/instruments?includeDelisted=true` och
`/instruments?active=false` returnerar båda **200 med exakt 1 715 instrument**, dvs.
samma som utan parameter. Okända parametrar tystas ned — ett negativt svar från API:t
kan alltså inte skiljas från "parametern finns inte".

**4. `/instruments/updated` avslöjar en större id-rymd — men utan data.**
Endpointen returnerar 700 id, varav **22 saknas i `/instruments`**:
`86, 167, 400, 404, 460, 531, 545, 553, 961, 962, 994, 1541, 1648, 1749, 1895, 1924,
2081, 2312, 2502, 2515, 2533, 2566`. Hämtning av `/instruments/{id}/stockprices` och
`/reports/year` för dessa ger **HTTP 200 med noll rader**. Id:t finns kvar som skal;
datan är borta.

**5. Ögonblicksbilder över tid bevisar borttagningen.** En äldre instrumentcache i legacy
innehåller 1 718 instrument. Tre av dem finns inte i dagens lista:

| insId | ticker | namn | noterad |
|---|---|---|---|
| 404 | HELIO | Heliospectra | 2014-06-18 |
| 2502 | MNDRK | MindArk | 2023-01-27 |
| 2515 | MVE | MatvareExpressen | 2023-09-29 |

Exakt dessa tre återfinns bland de 22 id:na ovan. **Börsdata tar bort avnoterade
instrument ur listan och slutar servera deras data.**

**Följd för v2:** Börsdata kan inte ge ett survivorship-fritt universum, oavsett hur
hämtningen läggs upp. Dessutom: **våra egna ögonblicksbilder av `/instruments` är den
enda vägen att i efterhand rekonstruera avnoteringshistorik från Börsdata.** V2 måste
därför snapshotta `/instruments` regelbundet och versionera det — annars förloras
informationen löpande.

---

## Steg 2 — EODHD-arkivet blir universum- och prisryggrad

`cache/eodhd_archive/ST/` (legacy, läses read-only):

| | antal | Common Stock | ETF | FUND | med ISIN |
|---|---|---|---|---|---|
| active | 1 010 | 945 | 27 | 38 | 770 (76 %) |
| delisted | **694** | 669 | 25 | – | 323 (47 %) |

Manifestet för `delisted/` rapporterar `eod_ok 694, div_ok 694, splits_ok 694, errors []`,
uppdaterat 2026-07-26. Kurs-, utdelnings- och splitserier ligger **separat**, vilket är
precis vad v2 behöver för att göra justeringar explicita.

### Begränsning som måste avgöra panelens startdatum

Avnoteringsdatum härlett ur sista handelsdag per instrument:

| år | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| antal | 2 | 9 | 20 | 14 | 25 | 15 | 9 | 42 | 46 | 126 | 92 | 103 | 92 | 99 |

Tidigaste sista handelsdag i hela arkivet är **2013-07-23**. **Noll** instrument har sista
handelsdag före 2013.

Det betyder två saker:
1. **Bolag som avnoterades 2010–2013 finns inte i arkivet alls.** En panel som börjar 2010
   är survivorship-biased oavsett källa.
2. Nivåerna 2013–2019 (2–25 per år) är svårförenliga med hur många avnoteringar
   Stockholmsbörsen faktiskt har per år. Täckningen är sannolikt ofullständig även
   2013–2019, medan 2020–2026 (42–126 per år) ser rimlig ut.

**Rekommendation:** sätt `dataset_v1.0`:s survivorship-säkra period till **2020-01-01 och
framåt**, och märk 2013–2019 som "delvis täckt" respektive före 2013 som "ej täckt".
Det är en kortare historik än dagens panel, men det är den period där universumet faktiskt
går att försvara. Alternativet — att behålla 2010 och dokumentera biasen — motsäger
direktivet att inte acceptera survivorship bias.

---

## Steg 3 — Instrumentmappning EODHD ↔ Börsdata

### ISIN är enda tillförlitliga nyckel

| grupp | n | med ISIN | ISIN-träff | endast tickerträff | ingen träff |
|---|---|---|---|---|---|
| aktiva, alla typer | 1 010 | 770 | 691 | 180 | 139 |
| aktiva Common Stock | 945 | 737 | 691 | 180 | **74 (7,8 %)** |
| avnoterade, alla | 694 | 323 | 50 | 39 | 605 |
| avnoterade Common Stock | 669 | 320 | **50** | 39 | **580 (87 %)** |

### Tickerbyten: 248 av 268 är formatskillnader, inte byten

EODHD skriver `ABSL-B`, Börsdata `ABSLB`. Efter normalisering till enbart versaler och
siffror återstår **20 verkliga kodskillnader**, av två slag:

- **Korsnoteringar** där Börsdata bär marknadssuffix: `NDA-SE` ↔ `NDA FI`/`NDA DK`,
  `SAMPO-SEK` ↔ `SAMPO`/`SAMPO DKK`, `BOOZT` ↔ `BOOZT DKK`, `NOKIA` ↔ `NOKIA SEK`,
  `BETCO` ↔ `BETCO DKK`, `SSAB-A` ↔ `SSABAH` (Helsingfors). Måste hanteras genom att
  filtrera på marknad, inte genom att matcha ticker.
- **Verkliga namn-/tickerbyten** där EODHD behållit det gamla och Börsdata har det nya:
  `CMOTEC-B` → `NEEMS B` (Scandinavian ChemoTech → Neems Hill), `FPIP` → `LASER`
  (FormPipe → Lasernet Group), `LADYLU` → `EMB`, `MAHA-A` → `KEOC`, `NYF` → `ALTRA`
  (Nyfosa → Altra Fastigheter). **Tickermatchning hade missat eller felkopplat dessa.**

13 Börsdata-ISIN pekar på flera instrument (korsnoteringar), 2 i EODHD.

### Tickermatchning är direkt farlig för avnoterade

56 avnoterade instrument matchar ett Börsdata-instrument **enbart via ticker**, med annan
eller saknad ISIN — dvs. tickern har återanvänts av ett annat bolag. **Regel för v2:
avnoterade instrument får aldrig kopplas via ticker, bara via ISIN.**

### Corporate actions

| källa | splitar |
|---|---|
| Börsdata `StockSplits` (legacy-cache, från 2000) | 429 |
| EODHD, aktiva | 953 |
| EODHD, avnoterade | **480** |

EODHD har splithistorik även för avnoterade bolag. Börsdata har det inte — instrumenten
är borttagna.

### Konsekvens som måste sägas rakt ut

En survivorship-säker **pris- och universumryggrad** ger inte automatiskt ett
survivorship-säkert **fundamentaldataset**. Av 669 avnoterade Common Stock har bara **50**
en äkta ISIN-träff i Börsdata. För resten finns ingen fundamentaldata att hämta någonstans
— den är raderad hos leverantören.

Det lämnar tre vägar, och valet är ditt:

| väg | innebörd |
|---|---|
| **A. Prisbaserade features enbart** för survivorship-säkra tester; fundamenta används först när frågan uttryckligen gäller överlevande bolag | ärligt, men featureutrymmet krymper kraftigt |
| **B. Fundamenta som villkorad feature** med explicit `har_fundamenta`-flagga, och alla resultat redovisade både med och utan | behåller fundamenta men kräver dubbel redovisning i varje test |
| **C. Annan fundamentalleverantör** med point-in-time-historik för avnoterade (t.ex. Refinitiv/Compustat-motsvarighet) | löser problemet i grunden, men är en inköpsfråga |

---

## Steg 5 — Hashverifiering av kategori 1: **underkänd**

`cache/researchdb_v1/raw/` (2 085 hämtningar).

**Intern konsistens är perfekt:**

| kontroll | utfall |
|---|---|
| http_status | 200 för samtliga 2 085 |
| `ok=False` | 0 |
| filer som saknas på disk | 0 |
| filer som inte går att läsa | 0 |
| `meta.sha256` ≠ manifestets sha256 | 0 |
| `n_rows` ≠ faktiskt radantal | 0 |
| json-filer på disk utan manifestrad | 0 |
| manifestrader utan fil | 0 |

**Men hashen går inte att verifiera.** `rawstore.py` beräknar
`sha256(r.text)` — leverantörens råa svarskropp — men sparar
`json.dumps({"meta": …, "payload": json.loads(body)})`. **Rå-bytesen kastas.**
Ett stickprov på 60 filer testades mot fyra serialiseringar
(`ensure_ascii=False`, default, kompakt `(',',':')`, kompakt + `ensure_ascii=False`):
**59 av 60 kunde inte återskapas av någon av dem.**

Manifestets sha256 refererar alltså till bytes som inte längre existerar. Det som går att
kontrollera är självkonsistens (filens egen `meta.sha256` mot manifestraden), inte
äkthet mot leverantören.

**Kravet "RAW-data ska sparas oförändrad" är inte uppfyllt i legacyns lager.**

**Dessutom ofullständigt:** 678 av 1 715 instrument har rapporthämtning —
**täckningsgap 1 037 instrument (60,5 %)**. Prisendpointen i lagret
(`instruments_stockprices`) innehåller bara senaste kurs, inte historik.

### Omklassificering

`cache/researchdb_v1/raw/` flyttas från **kategori 1 till kategori 3 (hämtas om)**.
Skälet är inte att datan tros vara fel, utan att den inte kan bevisas vara rätt — och en
omhämtning är billig: 2 085 anrop med 0,15 s strypning är ~6 minuter, och hela
instrumentlistan ~3× det.

Kvar i kategori 1 är då **enbart `cache/eodhd_archive/ST/`**, som fortfarande behöver sin
egen manifest- och integritetskontroll innan migrering.

---

## Öppna beslut

1. **Startdatum för `dataset_v1.0`** — rekommendation 2020-01-01 (se steg 2).
2. **Fundamentaaxeln för avnoterade bolag** — väg A, B eller C ovan.

Ingen modellträning, inget backtest och ingen featureoptimering körs innan dessa är
avgjorda och datalagret är byggt.
