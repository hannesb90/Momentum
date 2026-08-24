# NASDAQ HISTORICAL MASTER — FIELD INVENTORY, SOURCE MAPPING & EXTRACTION PLAN

Datum 2026-08-18 · **Datainventering. Noll forskningstester. H0 V3 orörd.**
Artefakter: `research_k/nasdaq_historical_master/` · 13 filer med SHA256

---

## 0. Pre-flight

Gate **PASS**. `H0_V3` = `FROZEN`, PIT-korrekt baslinje. `H0_CORE` (V2) kvarstår
`FROZEN_BUT_MEMBERSHIP_CONTAMINATED`. Ingenting av detta ändrat.

---

## 1. Inventering av alla 201 filer och alla blad

Samtliga 201 RAW-filer lästa, **alla fem blad i varje**, inte bara det parsern använder:

| Blad | Förekomst |
|---|---:|
| Contents | 201/201 |
| Main Market Trading Details | 201/201 |
| Company Trading | 201/201 |
| Company Trading per Exchange | 201/201 |
| **Instrument Trading Details** | 201/201 |

**256 unika normaliserade fältnamn · 213 schemavarianter** (blad × headerset).
Header-igenkänning är namnbaserad, aldrig positionsbaserad.

### Instrument Trading Details — 28 fält med full täckning

`instrument · company_code · orderbook_code · isin · instrument_type · segment ·
currency · location · delisted · round_lot · lg · plus · no_of_shares_listed ·
market_cap · latest_paid · listed_days · traded_days · total_turnover ·
total_no_of_traded_shares · total_no_of_trades · average_turnover ·
average_no_of_traded_shares · average_no_of_trades · average_trade_size ·
turnover_velocity · average_closing_spread · vwap · high_paid · low_paid`

Delvis täckning: `nc` 199 · `lp_yes_no` 194 (från 2010-03) · `super_sector` 173
(från 2012-02) · **`otc_turnover` / `otc_no_of_trades` 160 (2009-08 → 2023-02, upphör)** ·
`industry` 158 (från 2013-06) · `issuer_country` 20 (från 2024-12) ·
`sector` + `sub_industry` 28 (2009-08 → 2012-01).

Valideringsextraktion: **73 958 STO+Stock-rader** över 201 månader.

---

## 3–4. Semantik och PIT-status

### Publiceringsmodell — verifierad

Filen för månad *M* publiceras **första veckan i M+1** (2012-03 publicerad 2012-04-04;
2025-11 publicerad 2025-12-02).

> **Grundregel: inget fält är `PIT_SAFE`. Allt är `PIT_SAFE_WITH_LAG`.**
> Månadens handelsstatistik får aldrig användas vid månadens början.
> Beslutsregel: använd senaste månad *M* med *M* < beslutsmånaden.

### Market cap — semantiken är löst, inte gissad

```
market_cap / (no_of_shares_listed × latest_paid)
    n = 60 887    median 1,0000    p10 1,0000    p90 1,0000
```

**Market cap = noterade aktier × sista betalkurs, instrumentnivå, månadsslut, SEK.**
Samtliga 73 687 STO-observationer har `currency = SEK`.

Ekonomisk rimlighetskontroll mot segmentgränserna (2026-07, median):
Large 23,6 mdr SEK ≈ EUR 2 mdr · Mid 3,77 mdr ≈ EUR 330 m · Small 516 m ≈ EUR 45 m.
Konsistent med Large ≥ EUR 1 mdr, Mid 150 m–1 mdr, Small < 150 m.

### Fält markerade `SEMANTICS_UNRESOLVED`

| Fält | Varför |
|---|---|
| `vwap` | handelsmängden (on-exchange vs inkl. OTC) framgår inte av filens noter |
| `turnover_velocity` | formeln är inte dokumenterad i källan |
| `avg_closing_spread` | enheten (bp eller procent) är inte verifierad |

Dessa **antas inte**. De är flaggade tills källdokumentation verifierar dem.

---

## 5. Jämförelse mot Momentums befintliga data

| Fält | Klassificering | Skäl |
|---|---|---|
| **market_cap** | **NEW_DATA** | Börsdata market cap är `DATA_BLOCKED`. Här finns 201 månader, 99,63 %, SEK, inkl. avnoterade |
| **no_of_shares_listed** | **NASDAQ_BETTER_SOURCE** | Börsdatas `number_Of_Shares` är EPS-denominator med **0/68** täckning för avnoterade. Nasdaq ger faktiskt noterade aktier, 99,66 % |
| **turnover / traded_shares / trades** | **NEW_DATA** | Volym saknades **helt före 2020** (G149). Nasdaq har månadsdata från 2009-08 |
| **avg_closing_spread** | **NEW_DATA** | Batch 11 stängde hela friktionsfamiljen med skälet att ingen spreadserie finns. **Den finns** — 96,6 % över 201 månader |
| **otc_turnover / otc_trades** | **NEW_DATA** | Off-book-aktivitet, tidigare helt frånvarande. Upphör 2023-02 |
| **industry / supersector** | **NASDAQ_BETTER_SOURCE** | se nedan |
| **isin / orderbook / company_code** | **NASDAQ_BETTER_SOURCE** | enda källan med tidsberoende ISIN-identitet |
| vwap / high / low | NASDAQ_QA_SOURCE | prisdatan är redan daglig och finare |
| segment, membership, delisted | REDAN_CANONICAL | används redan av H0 V3 |
| currency / round_lot / lp / issuer_country | DUPLICATE_BUT_USEFUL | referensmetadata, billig att bevara |

**4 NEW_DATA · 3 NASDAQ_BETTER_SOURCE · 1 QA · 2 REDAN_CANONICAL · 1 DUPLICATE_BUT_USEFUL**

---

## 6. Market cap audit

| | |
|---|---|
| Täckning | **99,63 %** (73 687 / 73 958); per månad min 98,3 %, median 99,7 % |
| Historik | 2009-08 → 2026-07, **201 månader** |
| Valuta | SEK för samtliga STO-instrument |
| Nivå | **instrument**, inte issuer — flera aktieslag har egna värden |
| Avnoterade | market cap finns i avnoteringsmånaden för 16 instrument |
| Nollor/negativa | **0** |
| Instrument | 757 |

**`T-MCAP-01` blockeringsorsak: `DATA_BLOCK_REASON_POTENTIALLY_RESOLVED`.**
Blockeringen motiverades av att PIT-market cap saknade daglig historik och att
avnoterade saknades. Båda skälen bortfaller för en **månadsupplöst** serie.

> Forskningsstatus är **inte** ändrad i detta uppdrag. Endast dataevidensen rapporteras.

---

## 7. Liquidity foundation

| Fält | Täckning | Period |
|---|---:|---|
| total_turnover | 99,9 % | 2009-08 → 2026-07 |
| total_traded_shares | 99,9 % | 2009-08 → 2026-07 |
| total_trades | 99,9 % | 2009-08 → 2026-07 |
| traded_days / listed_days | 99,6 % | full |
| turnover_velocity | 99,5 % | full |
| avg_closing_spread | 96,6 % | full |
| vwap / high / low | 83,7 % | full |
| otc_turnover / otc_trades | 30,1 % | 2009-08 → **2023-02** |

En framtida canonical `nasdaq_liquidity_monthly` är **möjlig**. Ingen liquidity gate
byggs, ingen backtest körs.

---

## 8. ICB / sektor — genuint historisk

Detta är uppdragets näst viktigaste fynd.

| Fält | Instrument som byter värde över tid |
|---|---:|
| `supersector` | **398 av 756 = 52,6 %** |
| `industry` | **176 av 756 = 23,3 %** |
| `sub_industry` | 17 = 2,2 % |
| `sector` | 3 = 0,4 % |

Ett enda taxonomiskifte i tiden: **2012-01 → 2012-02**, från `Sector`/`Sub-Industry`
till `Industry`/`Supersector`.

Konkreta byten: AAK `Consumer Goods → Consumer Staples` · ALIV SDB
`Consumer Discretionary → Consumer Goods` · AXFO `Consumer Discretionary →
Consumer Services → Consumer Staples` · BEIA B `Basic Materials → Industrials`.

**Detta är verkliga månadssnapshots, inte bakåtprojektion.**

Jämför K1: **0 av 420 instrument har mer än ett intervall**, och täckningen i
2014-2019 är **0 %**. K1-status ändras **inte** automatiskt — men Nasdaq-serien är
empiriskt överlägsen på båda punkterna.

---

## 9. First North

**Finns.** `Equity Trading by Company and Instrument - First North YYMM.xlsx`, plus en
aggregatvariant `Total Equity Trading - First North YYMM.xlsx`.

Sample hämtat och inspekterat (2026-07, 1,04 MB, hashat). Samma femblads-workbook.
Header:

```
Instrument | Issuer Code | Orderbook Code | ISIN | Instrument Type | Industry |
Supersector | Round Lot | LP Yes=Y | Currency | Issuer Country | Delisted |
No of Shares Listed | Market Cap | Latest Paid
```

**Schemakompatibilitet: hög men inte direkt.** Main Market-parsern faller på att
`Location` saknas. Krävs: en First North-profil där Location defaultas,
segmentvokabulären utökas (`First North Premier` m.fl. i stället för Large/Mid/Small),
och `Issuer Code` mappas mot `Company Code`.

**Historikens djup är inte fastställt** — endast 4 månader (2026-04…2026-07) nåddes i
denna sökning. Kräver samma paginerade discovery som Main Market.

---

## 10–13. Övriga källor

**Reference Data:** ingen historisk referensdataserie identifierad. Men det behövs
sannolikt inte — **`No of Shares Listed` finns redan i Main Market-filerna** med
99,66 % täckning över 201 månader. Låg prioritet.

**Corporate Actions:** ingen strukturerad historisk eventserie. Träffarna är
procedurdokument och marknadsmodellnotiser. Split- och emissionsdetektion är däremot
**härledbar** ur månad-över-månad-förändringar i `no_of_shares_listed`.
Skatteverket, Börsdata och MFN förblir primära. Nasdaq = `QA_SOURCE`.

**Index history:** indexnivåer troligen tillgängliga men **ej verifierade**.
Historiska constituents och vikter är **inte** verifierade — att dagens constituents
visas är inget bevis för historik. En daterad OMXS30-medlemskapsfil finns i legacy
(50 rader). `Index Development`-bladet i First North-aggregatet är outforskat.

**Experimentella:** QuoteView `ACCOUNT_REQUIRED/PAID` — men `avg_closing_spread`
täcker redan spreadbehovet månadsvis från 2009 till en bråkdel av kostnaden.
Trading Activity Tracker och ITCH/HistoricalView: `PAID`. Domicile finns delvis
gratis som `Issuer Country` från 2024-12.

---

## 14–15. Datamodell och prioritering

```
nasdaq_historical/
    raw/            main_market/ (201, hashade)  first_north/ (sample)
    normalized/     instrument_monthly · membership_intervals · segment_intervals
                    icb_intervals · market_cap_monthly · liquidity_monthly
                    listed_shares_history · issuer_identity
    validated/      efter QA per lager
```

RAW bevaras verbatim med hash. Normalized ersätter aldrig RAW.

| Prio | Uppgift | Motiv |
|---|---|---|
| **P0** | Main Market monthly master extraction | RAW redan hämtat, parser finns, 4 NEW_DATA + 3 BETTER_SOURCE |
| **P1** | **Historisk ICB/sektor-intervallserie** | K1 kan inte representera sektorbyten alls; datan är redan extraherad |
| **P2** | First North monthly | utvidgar universumet; kräver parserprofil och djupare discovery |
| **P3** | Corporate-action QA via `no_of_shares_listed` | splitdetektion utan ny datakälla |
| **P4** | Index history | constituents och vikter ej verifierade |
| **P5** | QuoteView / flows | lågt värde relativt kostnad |

**Avvikelse från den föreslagna ordningen:** historisk ICB flyttas till **P1**, före
First North. Skälet är empiriskt — K1 har 0 av 420 instrument med mer än ett intervall
och 0 % täckning i 2014-2019, medan Nasdaq visar att 23,3 % faktiskt byter industry.
Datan är dessutom redan extraherad.

---

```
REPOSITORY INTEGRITY:              PASS

MAIN MARKET MONTHS AUDITED:        201 (2009-08 … 2026-07)
WORKBOOK SHEETS FOUND:             5 (samtliga i alla 201 filer)
UNIQUE RAW FIELDS:                 256 normaliserade
SCHEMA VARIANTS:                   213 (blad × headerset)

MARKET CAP
  AVAILABLE:                       JA
  HISTORY:                         2009-08 … 2026-07, 201 månader
  PIT STATUS:                      PIT_SAFE_WITH_LAG (publiceras i M+1)
  COVERAGE:                        99,63 %, per månad min 98,3 %
  CLASSIFICATION:                  NEW_DATA

LIQUIDITY
  TURNOVER:                        99,9 %
  TRADED SHARES:                   99,9 %
  TRADES:                          99,9 %
  VWAP:                            83,8 % (SEMANTICS_UNRESOLVED)
  OTC:                             30,1 %, upphör 2023-02
  PIT STATUS:                      PIT_SAFE_WITH_LAG
  CLASSIFICATION:                  NEW_DATA

ICB / SECTOR
  AVAILABLE:                       JA
  HISTORICAL CHANGES VERIFIED:     JA — 176/756 byter industry, 398/756 supersector
  PIT STATUS:                      PIT_SAFE_WITH_LAG
  CLASSIFICATION:                  NASDAQ_BETTER_SOURCE

FIRST NORTH
  AVAILABLE:                       JA
  HISTORY:                         EJ FASTSTÄLLD (4 månader nådda)
  SCHEMA COMPATIBILITY:            HÖG — saknar Location, annan segmentvokabulär
  NEXT ACTION:                     paginerad discovery före ingestion

REFERENCE DATA
  LISTED SHARES:                   JA — i Main Market-filerna, 99,66 %
  SHARE CAPITAL:                   ej separat fält
  HISTORY:                         201 månader
  PIT STATUS:                      PIT_SAFE_WITH_LAG

CORPORATE ACTIONS
  AVAILABLE:                       NEJ som serie
  USE CASE:                        QA_SOURCE — splitdetektion via no_of_shares_listed

INDEX HISTORY
  LEVELS:                          troligen, EJ VERIFIERAT
  CONSTITUENTS:                    EJ VERIFIERAT
  WEIGHTS:                         EJ VERIFIERAT

NEW_DATA FIELDS:                   market_cap · turnover-familjen · avg_closing_spread · otc
NASDAQ_BETTER_SOURCE FIELDS:       no_of_shares_listed · industry/supersector · isin-identitet
NASDAQ_QA_SOURCE FIELDS:           vwap · high_paid · low_paid
SEMANTICS_UNRESOLVED FIELDS:       vwap · turnover_velocity · avg_closing_spread

T-MCAP-01 BLOCKER POTENTIALLY RESOLVED:  JA (endast dataevidens, status ej ändrad)
LIQUIDITY FOUNDATION POSSIBLE:           JA
HISTORICAL ICB FOUNDATION POSSIBLE:      JA
FIRST NORTH MASTER POSSIBLE:             JA, efter discovery

NASDAQ HISTORICAL MASTER RECOMMENDATION: BYGG — P0 Main Market monthly master
NEXT IMPLEMENTATION STEP:                P0-extraktion till normalized/instrument_monthly
                                         med RAW-hash och available_from per rad

RESEARCH TESTS EXECUTED:           0
H0 V3 MODIFIED:                    NO
```
