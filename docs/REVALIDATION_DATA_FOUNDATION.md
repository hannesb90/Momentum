# REVALIDATION DATA FOUNDATION

Datum: 2026-08-19 · Status: **REVALIDATION_DATA_FOUNDATION_READY**

Inga forskningstester körda. Ingen champion ändrad. Inga historiska domar ändrade.
Inga legacy-skript modifierade. Inga gamla frysta artefakter överskrivna.

---

## DEL A — H1419 ÄR GATAT

### A1 Inventering och ett avgörande strukturfynd

`validated/prices_h1419/` innehåller sju filer. Den som används,
`prices_h1419_universum_v2.json`: **290 instrument, 519 829 rader, 2012-07-02 …
2019-12-30**, 1 937 handelsdagar. Läses av 20 skript, däribland kärnmotorn
`h1419_motor.py` och `h0_v3_kor.py`. Fem P0-kandidater krävde det.

**Lagret har bara fälten `adj` och `d` — ingen rå close.**

Två konsekvenser. `RAW_CLOSE_INVALID` är per konstruktion omöjlig att bryta mot: det
finns inget close att läsa. Men faktordetektorn bygger på `close/adj` och kan därför
**inte köras mot lagret självt**.

### Kanonregistret var inte tillämpligt

Huvudregistrets 99 boundaries ligger 2020-03-09 … 2026-05-07. **Noll** faller i
H1419-fönstret. En översättning av registret hade gett ett falskt friskintyg.

Därför en **oberoende skanning** mot EODHD-råarkivet för exakt samma instrument och
fönster — den källa lagret byggdes ur:

| | |
|---|---|
| Faktorregimkandidater 2012-07 … 2019-12 | **2 383** i 246 instrument |
| VALID_CORPORATE_ACTION | 1 033 (varav 45 rena splitkvoter, 510 årskadens, 16 kvartalskadens) |
| UNKNOWN | 1 350 |
| **Materiella** (>5 %, permanenta) | **59 i 30 instrument** |

### A2–A3 Register och gatad vy

`PRICE_H1419_RESTRICTION_REGISTRY.json` — 59 poster med H1419-identitet, canonical
identitet, boundary, eligibility före/efter och mappningsförtroende: **53
EXACT_TICKER, 6 H1419_ONLY**. Ingen UNKNOWN passerar tyst.

`validated/prices_h1419_gated/prices_h1419_gated.json` — samma princip som huvudlagret:
endast längsta giltiga segment exponeras. **519 829 → 501 502 rader** (18 327 uteslutna),
290 instrument bevarade.

### A4 Ungated-behovet är borta

`prices_h1419_universum_v2.json` och `prices_h1419_universum.json` omdirigeras nu till
den gatade vyn. Mellanstegen `preliminar` och `klassificerad` är förbjudna.
`UNGATED = {}` — mekanismen finns kvar för framtida fall, men listan är tom.

**0 av 60 P0 kräver längre `--allow-ungated`.**

### A5 H1419-enforcement

Fyra nya negativa test (mellansteg via `open`, `pathlib`, `pandas`) och tre positiva
(omdirigering, boundary-spärr på NET-B 2016-05-04, relativ sökväg). Alla PASS.

---

## DEL B — FUNDAMENTALS/PIT

### B1 Inventering

| Tabell | Rader | Instrument | Periodspann | SHA256 |
|---|---|---|---|---|
| year | 4 847 | 345 | 2006-11-30 … 2026-04-30 | `7cead0b764c81e7d…` |
| quarter | 12 280 | 347 | 2014-12-31 … 2026-06-30 | `e7c6ec8a1096189a…` |
| r12 | 12 269 | 347 | 2014-06-30 … 2026-06-30 | `487f212237f9bdd4…` |

36 fält per rad, inklusive `report_date`, `currency`, `currency_ratio`, `ratio_flagg`.
PIT-regler R1–R5 är redan applicerade vid byggtillfället (5 403 → 4 847 årsrader:
482 utan datum, 49 look-ahead, 16 orimlig eftersläpning borttagna).

### B2 Valutareparationen verifierad

Kanonlagret är i **originalvaluta**; `currency_ratio` konverterar till SEK.

| Bolag | År | Valuta | ratio | Gammal | Ny | Kvot |
|---|---|---|---|---|---|---|
| **AZN** | 2024 | USD | 11,0250 | 6 572 607 | 596 155 | **11,025** |
| LUMI | 2024 | USD | 11,0217 | 415 771 | 37 723 | 11,022 |
| ORRON | 2024 | EUR | 11,4559 | 4 816 | 420 | 11,456 |
| ARP | 2024 | PLN | 2,6791 | 24 653 | 9 202 | 2,679 |
| ARION-SDB | 2024 | ISK | 0,0796 | 421 | 5 291 | 0,080 |

Kvoten är i varje fall **exakt** `currency_ratio` — dubbelkonverteringen är borta.
**`number_Of_Shares`: 0 av 4 691 ändrade** — korrekt undantaget.

Detta är också en forskningsrisk som nu är registrerad: 481 av 4 847 årsrader är
icke-SEK. Ett test som jämför AZN:s intäkter (596 155 MUSD) mot ett SEK-bolags utan att
applicera ratio jämför äpplen med päron.

### B3 no_future_report_leakage — PASS

`tools/fundamental_pit_gate.py`. Regel:

> `first_eligible_research_date` = första handelsdagen **strikt efter** `report_date`

Endast datum finns, inte klockslag. Regeln antar därför publicering efter börsstängning.
Ingen intradagsåtkomst inferreras, ingen backfill.

Över **29 396 rader**: 0 utan report_date, 0 look-ahead, 0 med eftersläpning över 180
dagar, 0 epokfel. Publiceringseftersläpning: median 43 dagar (år), 32 (kvartal), max 141.
23 kvartals-/R12-rader har report_date efter prisseriens slut och saknar därmed
eligibility-datum — korrekt oanvändbara.

Gaten kastar hårt fel dagen före eligibility och släpper igenom på eligibility-datumet —
verifierat.

### B4 Deterministiskt urval

De "20 respektive 41 duplicerade perioder" jag först mätte var ett artefakt: jag
grupperade på `kod`, och 9 instrument (156–339 rader, ~3 %) saknar ticker.

På den riktiga primärnyckeln `(insid, year, period)`: **0 dubbletter i alla tre
tabellerna**. Det finns ingen restatement-tvetydighet att lösa.

### B5 EPS, aktier och utdelning

**209 aktieantalshopp** över ±50 % utan matchande Börsdata-split → `SHARES_UNVERIFIED`.
153 rader har EPS som avviker mer än 10 % från `profit_To_Equity_Holders / number_Of_Shares`.
Manifestets egen splitverifiering: EPS-konsistens 97,3 % generellt, 89,9 % kring splittar,
och tio tidigare flaggade hopp har noll matchande split — bekräftat äkta händelser.

### B6 Delistade fundamentals

**1 av 68** avnoterade instrument har fundamentadata. 67 saknar den i alla källor —
oberoende bekräftat av `manifest_sparB` track_B.

Separationen är registrerad: ett rent pristest blockeras inte, men ett fundamentaltest
måste deklarera att dess urval är survivorship-begränsat.

### B7–B8 Register och gate

`FUNDAMENTAL_RESTRICTION_REGISTRY.json` — **233 poster**: 209 SHARES_UNVERIFIED,
13 CURRENCY_UNVERIFIED, 9 IDENTITY_UNVERIFIED, 1 DELISTED_FUNDAMENTALS_MISSING,
1 R12_CONSTRUCTION_UNVERIFIED.

Runnerns preflight kräver nu fundamentalregistret, identitetskartan och att alla tre
tabellernas SHA matchar registret. Manifestet bär `fundamental_registry_sha256`,
`fundamental_table_sha256` per tabell, `fundamental_pit_gate_sha256` och
`identity_map_sha256`.

---

## DEL C — KANONISK IDENTITET

`CANONICAL_IDENTITY_MAP.json` — **2 139 instrument**.

| Nivå | Definition |
|---|---|
| `issuer_id` | ekonomiskt bolag — Börsdata `insId`, löst via ISIN |
| `instrument_id` | aktieslag/listning — Nasdaq `orderbook_code`, annars EODHD `Code` |
| `isin` / `ticker` / `company_name` | **tidsbegränsade alias** med giltighetskedjor |

**Regel: ingen implicit namnmatchning i revalidation.** Namn får redovisas som alias men
aldrig användas som join-nyckel.

Mappningsförtroende: 483 EXACT_ISIN_AND_NASDAQ · 523 BORSDATA_ISIN_ONLY ·
280 NASDAQ_PIT_ONLY · 853 EODHD_CATALOGUE_ONLY.
**267 ISIN-byten i 160 instrument, 87 namnbyten i 76.** 0 dubbletter på `instrument_id`.

---

## DEL D — SLUTLIG FRYSNING

`research_k/REVALIDATION_DATA_FREEZE_MANIFEST.json` · **17 komponenter, status SEALED**
Kombinerad SHA256 `7613acac43c6bc4c51ae826cac4b8131…`

Varje komponent bär path, version, SHA256, radantal, datum- och instrumenttäckning,
provenance och begränsningar. Samtliga 17 existerar och hash-matchar.

---

## DEL E — FOUNDATION QA: 15/15 PASS

| Gate | Utfall |
|---|---|
| price/component hashes match | **PASS** — 17 komponenter, 0 avvikande |
| H1419 hash/registry match | **PASS** |
| no price boundary leakage | **PASS** — 0 korsbara boundaries i gatad vy |
| no raw-close-invalid use | **PASS** — fältblock aktivt för FLERIE, IMMNOV, SAS |
| no future membership leakage | **PASS** — 0 brott |
| **no future report leakage** | **PASS** — 0 look-ahead över 29 396 rader |
| PIT-gate hårt fel dagen före eligibility | **PASS** |
| PIT-gate släpper igenom på eligibility-datum | **PASS** |
| canonical identity deterministic | **PASS** — 2 139 instrument, 0 dubbletter |
| no survivorship-only implicit fundamental sample | **PASS** — explicit registrerat |
| no unverified currency conversion | **PASS** — AZN-regression exakt |
| no forbidden legacy path in REVALIDATION | **PASS** — 29/29 bypass-tester |
| all required restriction registries loaded | **PASS** |
| runner manifest complete | **PASS** — acceptansgrind VALID |
| deterministic rebuild | **PASS** — identisk SHA över två oberoende byggen |

Bypass-sviten är nu **29/29 PASS** (var 23 före H1419-testerna).

---

## DEL F — CANDIDATE MAP FINAL

| Klass | Antal | | Prioritet | Antal |
|---|---|---|---|---|
| UNAFFECTED | 412 | | P0 | **60** |
| DIRECTLY_AFFECTED | 213 | | P1 | 58 |
| STRUCTURALLY_AFFECTED | 83 | | P2 | 144 |
| POSSIBLY_AFFECTED | 89 | | P3 | 129 |
| UNKNOWN | 6 | | | |

| Readiness | Antal |
|---|---|
| FULLY_GATED | **300** |
| UNAFFECTED_OTHER_LINEAGE | 487 |
| PARTIALLY_BLOCKED | 16 |
| DATA_UNAVAILABLE | 0 |

Kräver fundamenta: **32** · kräver H1419: **24** · påverkas av delistade fundamentals: **13**.
Förväntad eligible sample fraction: 0,962 (huvudlagret), 0,965 (H1419), 1,0 (övriga).

### P0 — explicit readiness

**58 FULLY_GATED, 2 PARTIALLY_BLOCKED.** 0 kräver ungated input. 0 är raw-close-beroende.
5 kräver fundamenta, 7 kräver H1419.

De två partiellt blockerade — `lonsamhetstilt_mot_stack_h` och
`spar_c_features_fundamenta` — är fundamentaltester vars urval är survivorship-begränsat
(1 av 68 avnoterade har data). De är körbara; begränsningen måste deklareras.

---

## VAD SOM MÅSTE SÄGAS RAKT UT

**Fyra P0 skulle HARD FAIL i REVALIDATION-mode som de är skrivna**, eftersom de läser
förbjudna sökvägar:

- `h1419_steg2_universum` och `h1419_universum_v2` — **databyggen**, inte forskningstester.
  De *producerar* H1419-lagret. De hör hemma i databygge, aldrig i revalidation.
  Att de är blockerade är korrekt.
- `tidig_detektion_och_utdelning` — läser EODHD-råarkivet. Dess tredje del *är* en
  data-QA som verifierar att `adjusted_close` är totalavkastningsjusterad; råaccess är
  intrinsisk för syftet.
- `prima_storbolag` — beräknar ADV ur råarkivet. Volym finns i den gatade vyn (`v`), så
  det vore tekniskt möjligt att läsa därifrån — men skriptet gör det inte, och att skriva
  om det är förbjudet i detta uppdrag.

Det är alltså **två genuina forskningsskript** som inte kan revalideras som de står. Det
är inte ett fel i datagrunden utan en konsekvens av att enforcement är verklig: skript som
kringgår det validerade lagret blockeras, precis som avsett. Antingen klassas de som
data-QA, eller så krävs ett separat mandat att skriva om dem.

---

## SLUTSTATUS

| READY-krav | Utfall |
|---|---|
| 60/60 P0 utan ungated prisinput | **JA** — `UNGATED = {}`, 0 kräver deklaration |
| H1419 gatat | **JA** — 59 boundaries, 501 502 rader |
| no_future_report_leakage PASS | **JA** — 0 över 29 396 rader |
| Kanonisk identitet beslutad och maskinellt använd | **JA** — 2 139 instrument, tvingande i preflight |
| Fundamentala restriktioner enforceable | **JA** — 233 poster, SHA-verifierade i runnern |
| Slutligt freeze-manifest hash-verifierat | **JA** — 17/17 komponenter |
| Inga nya forskningsresultat producerade | **JA** |

---

Leveranser: `validated/prices_h1419_gated/` · `validated/fundamentals_gated/` ·
`research_k/canonical_identity/CANONICAL_IDENTITY_MAP.json` ·
`research_k/REVALIDATION_DATA_FREEZE_MANIFEST.json` ·
`research_k/FOUNDATION_QA_RESULTS.json` ·
`research_inventory/revalidation_candidate_map_v3.json`
Kod: `tools/fundamental_pit_gate.py` (ny) · uppdaterade `revalidation_runner.py`,
`validate_revalidation_run.py`, `test_revalidation_bypass.py`
