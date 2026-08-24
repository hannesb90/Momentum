# NASDAQ HISTORICAL MASTER — P0 MAIN MARKET MONTHLY MASTER + P1 HISTORICAL ICB

Datum 2026-08-18 · **Data foundation. Noll forskningstester. Inga frysta komponenter ändrade.**
27 artefakter med SHA256 · full provenance till RAW

---

## Pre-flight

Gate **PASS**. `H0_V3` = `FROZEN`, provenance verifierad (prereg, implementation och resultat
hashmatchar). H0 V3, signaler, parametrar och forskningsresultat är orörda.

---

## DEL A+B — Monthly master med publiceringslagg

**73 958 rader, 201 månader (2009-08 … 2026-07), population `Location = STO` och
`Instrument Type = Stock`.** Header-mappning är namnbaserad, aldrig positionsbaserad.

Varje rad bär: `observation_month · period_end · source_publication_date · known_from ·
known_from_rule · valid_from · valid_to · source_file · raw_sha256`.

| | |
|---|---:|
| Rader utan publiceringsdatum | **0** |
| `known_from` = faktiskt `release_time` från Nasdaqs nyhets-API | 201 / 201 |
| **Look-ahead-överträdelser** | **0** |

**Ingen konservativ approximationsregel behövdes** — alla 201 månader har verkligt
publiceringsdatum. Regeln är: filen för månad *M* publiceras i *M+1*, och `known_from`
är den faktiska publiceringstidpunkten. Alla månadsvariabler är `PIT_SAFE_WITH_LAG`.

---

## DEL C — Identitet

**763 orderbook-koder · 160 med ISIN-byte · 3 `CONFIRMED_CODE_REUSE`**

`instrument_identity_history.json` ger per kod: `first_seen · last_seen · months_present ·
isin_intervals (med valid_from/valid_to) · names · company_codes · delistings ·
code_reuse_flag · canonical_instrument_id · får_sammanfogas`.

De 3 bekräftade reuse-fallen får `canonical_instrument_id = <kod>#REUSE` och
`får_sammanfogas: false`. **Ingen automatisk hopkoppling.**

`issuer_mapping.json` är ett **separat lager**. Flera aktieslag förblir separata
instrument; ingen instrumenthistorik kastas.

---

## DEL D — Market cap validation

Nasdaqs egen definition, ordagrant ur filen:

> *"Market Capitalization. Calculated as the No of Shares Listed × Reference Price at the
> last trading day of month"*

Empirisk reproduktion av `market_cap / (no_of_shares_listed × latest_paid)`:

| | |
|---|---:|
| n | 60 887 |
| **median** | **1,000000** |
| p1 / p99 | 1,0000 / 1,0000 |
| **Andel inom 0,1 %** | **96,88 %** |
| Avvikande observationer | 1 897 (3,1 %) — **ej korrigerade**, dokumenterade |

| | |
|---|---|
| Valuta | SEK för samtliga 73 687 STO-observationer |
| Nivå | instrument (flera aktieslag har egna värden) |
| Tidpunkt | sista handelsdagen i månaden |
| Coverage | **99,63 %** |
| Senare avnoterade | **98,54 %** |
| Överlevare | 99,99 % |
| **Survivorship-gap** | **1,45 pp** |

**`T-MCAP-01`: de tidigare blockeringsskälen är empiriskt lösta för månadsupplösning.**
Skälen var *"unadjusted snapshot without daily PIT history"* och *"missing historical
market cap array for delisted issuers"*. Båda faller för en månadsserie som täcker
avnoterade till 98,54 %. **Daglig upplösning är fortfarande inte löst.**
Forskningsstatus är **inte** ändrad.

---

## DEL E — Liquidity foundation

Alla tre tidigare `SEMANTICS_UNRESOLVED`-fält är nu **`SEMANTICS_VERIFIED`** ur Nasdaqs
egen dokumentation inne i filerna:

| Fält | Bevis |
|---|---|
| **`avg_closing_spread`** | Enheten är **decimalbråk där 0,01 = 1 %**. Bevisad via Nasdaqs likviditetsgruppsdefinitioner: *"A-Group: … Spread < 1%"*, *"C-Group: … Spread > 5%"*. Observerad median 0,0058, p99 0,0914 — konsistent |
| **`vwap`** | *"Turnover / Volume during the period, taking into account trades that have updated the average daily price (trades that are executed in continuous trading and within the current spread). Adjusted for Corporate Actions."* |
| **`turnover_velocity`** | *"Turnover during period / Average Market Cap during period × 250 / Number of listed days"* |

| Fält | Coverage | Period |
|---|---:|---|
| total_turnover / traded_shares / trades | 99,9 % | 2009-08 → 2026-07 |
| traded_days / listed_days | 99,6 % | full |
| turnover_velocity | 99,5 % | full |
| avg_closing_spread | 96,6 % | full |
| vwap / high_paid / low_paid | 83,7 % | full |
| otc_turnover / otc_trades | 30,1 % | 2009-08 → **2023-02** |

Instrumentbladets not i moderna filer: *"OTC figures are not included in this report"* —
konsistent med att OTC-kolumnerna upphör 2023-02.

---

## DEL F — P1 Historical ICB

**756 instrument.** Intervall: `industry` 939 · `supersector` 1 217 · `sector` 366 ·
`sub_industry` 380.

| Nivå | Instrument som byter värde | Andel |
|---|---:|---:|
| `supersector` | **398** | **52,6 %** |
| `industry` | **176** | **23,3 %** |
| `sub_industry` | 17 | 2,2 % |
| `sector` | 3 | 0,4 % |

Taxonomiregimer: `sector + sub_industry` (2009-08 … 2012-01) → `indsutry(sic) + supersector`
(2012-02 … 2013-05) → `industry + supersector` (2013-06 … 2026-07).

QA-fall: AAK `Consumer Goods → Consumer Staples` · AXFO `Consumer Discretionary → Consumer
Services → Consumer Staples` · ALIV SDB · BEIA B. **Ingen bakåtprojektion.**

### Jämförelse mot K1 — governance consequence

| | K1 | Nasdaq |
|---|---:|---:|
| Instrument | 420 | 756 |
| **Med mer än ett intervall** | **0** | **176 (industry)** |
| **Coverage 2014-2019** | **0,0 %** | **99,5 %** |

**K1:s historiska representation är otillräcklig** — den kan strukturellt inte uttrycka
sektorbyten och har noll täckning i det tidiga fönstret.

> **Detta kräver ett explicit beslut. K1:s status och freeze är inte ändrade här.**

---

## DEL G — Temporal & survivorship QA

| | |
|---|---|
| Månader | 201 |
| **Saknade månader** | **3** — `2010-09`, `2011-08`, `2013-03` (alla utanför båda forskningsfönstren) |
| Duplicate instrument-month | **0** |
| Överlappande identitetsintervall | **0** |
| Instrumentluckor | 15 `EXPECTED_ABSENCE`, **1 `UNEXPLAINED_GAP`** |
| ISIN-transitioner | 160 |
| Segmentintervall | 1 133 |
| Delistings | 190 |
| Confirmed code reuse | 3 |
| **Ingen interpolation** | bekräftat |

---

## DEL H — Canonical output

```
RAW                     raw/nasdaq_segment/monthly/  (201 filer, hashade)
  ↓
normalized/
    instrument_monthly_master.json      73 958 rader, PIT-stämplade
    instrument_identity_history.json    763 koder, ISIN-intervall
    issuer_mapping.json                 separat lager
    segment_intervals.json              1 133
    taxonomy_intervals.json             industry/supersector/sector/sub_industry
  ↓
QA: market_cap_validation · liquidity_foundation · historical_icb_foundation
    temporal_survivorship_qa · pit_publication_qa · data_consequence_audit
```

**Data dictionary: 28 variabler**, var och en med `source_field · source_sheet ·
semantic_definition · unit · frequency · observation_time · known_from_rule · PIT_status ·
coverage · first/last_available · QA_status · allowed_use`.

Tilldelade `allowed_use`:
* `ALLOWED_FOR_POPULATION_STRATIFICATION` — identitet, segment, taxonomi, delisting
* `ALLOWED_FOR_RESEARCH_AFTER_PREREGISTRATION` — market cap, shares, turnover-familjen,
  spread, VWAP, priser

> **Ingen variabel blir en alfafeature bara för att datan är korrekt.**
> `ALLOWED_FOR_RESEARCH_AFTER_PREREGISTRATION` betyder att **datan** är godkänd, inte hypotesen.

---

## DEL I — Data consequence audit

| Familj | Dataproblem löst? | Forskningsstatus |
|---|---|---|
| **T-MCAP-01** | JA för månadsupplösning, NEJ för daglig | OFÖRÄNDRAD |
| historisk size | JA | OFÖRÄNDRAD — G-HET/G-SIZE-HET förblir `NOT_IDENTIFIED`, G-HIER förblir `NON_COMPUTED_CLAIM` |
| historisk ICB | JA | OFÖRÄNDRAD — governance consequence kräver beslut |
| liquidity / tradability | JA — volym fanns inte alls före 2020 | OFÖRÄNDRAD |
| spread / friction | **DELVIS** — månadsspread finns; intraday och orderdjup saknas, så market impact och participation rate förblir blockerade | OFÖRÄNDRAD |
| dilution / share-count | JA | OFÖRÄNDRAD |

**Legitima kandidater för separat preregistrering** — ingen av dem licensierad:
PIT size heterogeneity replication (mot H0 V3) · historisk ICB som stratifiering ·
liquidity som eligibility- eller kostnadslager · spread i kostnadsmodellen ·
share-count-förändring som utspädningsmått.

---

## DEL J — First North P2-specifikation

Sample hämtat och hashat (2026-07). **Gemensamma fält:** Instrument, Orderbook Code, ISIN,
Instrument Type, Industry, Supersector, Round Lot, Currency, Delisted, No of Shares Listed,
Market Cap, Latest Paid, Issuer Country.

**Avvikelser:** saknar `Location` · `Issuer Code` i stället för `Company Code` ·
First North-nivåer (t.ex. `First North Premier`) i stället för Large/Mid/Small Cap.

**Återanvänds direkt:** `ole2.py`, `biff8.py`, bladval via r:id, namnbaserad headerdetektor,
Excel-serialdatum, identitets- och intervallbyggare, PIT-publiceringslagg.

**Återstående historik: EJ FASTSTÄLLD** — endast 4 månader nådda. P2 kräver paginerad
rå-JSON-discovery först.

---

```
REPOSITORY INTEGRITY:            PASS
NASDAQ RAW MONTHS:               201 (2009-08 … 2026-07)
MONTHS PARSED:                   201 / 201 = 100 %
MONTHLY MASTER ROWS:             73 958 (STO + Stock)
MARKET CAP FOUNDATION:           BYGGD — formel dokumenterad av Nasdaq, empiriskt verifierad
MARKET CAP COVERAGE:             99,63 % · avnoterade 98,54 % · överlevare 99,99 %
LISTED SHARES FOUNDATION:        BYGGD — 99,66 %, 201 månader
LIQUIDITY FOUNDATION:            BYGGD — turnover/shares/trades 99,9 %, velocity 99,5 %
AVG CLOSING SPREAD SEMANTICS:    SEMANTICS_VERIFIED — decimalbråk, 0,01 = 1 %
HISTORICAL ICB FOUNDATION:       BYGGD — 939 industry-intervall, 1 217 supersector
ICB TEMPORAL COVERAGE:           99,5 % (2014-2019) · 176/756 byter industry
IDENTITY HISTORY:                763 koder · 160 ISIN-byten · 3 confirmed reuse, ej sammanfogade
DELISTED COVERAGE:               98,54 % (market cap)
SURVIVOR COVERAGE:               99,99 % — gap 1,45 pp
PIT PUBLICATION-LAG QA:          201/201 med faktiskt release_time, 0 utan
LOOK-AHEAD VIOLATIONS:           0
T-MCAP-01 DATA BLOCKER:          EMPIRISKT LÖST för månadsupplösning (status ej ändrad)
K1 DATA CONSEQUENCE:             K1 otillräcklig historiskt — KRÄVER EXPLICIT BESLUT
FIRST NORTH P2 READY:            SPEC KLAR — historikdjup ej fastställt
DATA FOUNDATION VERDICT:         VALID
RESEARCH TESTS EXECUTED:         0
H0 V3 MODIFIED:                  NO
FROZEN COMPONENTS MODIFIED:      NONE
NEW RESEARCH PREREGISTERED:      NONE
NEXT ALLOWED TASK:               explicit beslut om K1 mot Nasdaq-taxonomin,
                                 alternativt P2 First North discovery
```
