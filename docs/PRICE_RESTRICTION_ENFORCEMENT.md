# PRICE_RESTRICTION ENFORCEMENT

Datum: 2026-08-19 · Status: **PRICE_RESTRICTIONS_ENFORCED**

Inga forskningstester körda. Ingen champion ändrad. Inga gamla frysta filer överskrivna.

---

## 1. CANONICAL PRICE_RESTRICTION_REGISTRY

`validated/prices_adjustment_repair_v4/PRICE_RESTRICTION_REGISTRY.json`
SHA256 `a5ab339ef462f6139bd5a5ef7947271e…` · version V1 · **102 poster i 61 instrument**

| Restriktionstyp | Poster |
|---|---|
| EXTERNALLY_UNVERIFIED_CORPORATE_ACTION | 71 |
| ADJUSTED_SERIES_UNVERIFIED | 23 |
| SERIES_SPLIT_BOUNDARY | 4 |
| RAW_CLOSE_INVALID | 3 |
| IDENTITY_UNVERIFIED | 1 |

Varje post bär `instrument_id`, `ticker`, `isin`, `valid_from`, `valid_to`,
`restriction_type`, `blocked_fields`, `allowed_fields`, `blocked_operation`,
`research_eligible`, `reason`, `evidence_id`, `source_defect_class`, `severity`,
`provenance` och `registry_version`.

### Den konservativa regeln — och varför den inte är maximal

För de 23 materiella faktorskiftena valdes **boundary-spärr, inte helspärr**:

> Ett overifierat permanent faktorskifte ogiltigförklarar **övergången**, inte segmenten.
> Båda sidor är internt konsistenta — det är bara skalan mellan dem som är osäker.

Att spärra hela instrumenthistoriken vore mer restriktivt men inte mer korrekt: det skulle
kasta data som bevisligen är giltig. Det som *måste* förhindras är att en beräkning länkar
över skiftet. Därför gäller: ingen rullande beräkning får korsa `boundary_date`, och
kumulativ avkastning får inte länkas över den. Samma mekanism används för SERIES_SPLIT och
för persistenta covidfall — en enda spärrmodell för fyra defektklasser.

---

## 2. GATE OCH LOADERS

`tools/revalidation_price_gate.py` — enda sanktionerade vägen in.

```
price input -> restriction registry -> eligibility mask -> research input
```

`PriceGate()` verifierar vid instansiering: prisfilens SHA256, registrets SHA256,
registerversion mot manifest, och att registret pekar på samma prisversion. Avvikelse ger
`PriceGateIntegrityError` — **ingen fallback till gammal prisfil**.

Tre åtkomstvägar: `series()` (vägrar för instrument med boundary), `window()` (vägrar vid
korsning), `eligible()` / `eligible_universe()` (boundary-medveten maskning).

Varje avvisning loggas med instrument, datumintervall, fält, restriktionstyp och
`evidence_id`. **Ingen tyst filtrering.** Felmeddelandet är hårt och namnger allt:

```
HARD FAIL — fonstret korsar en oavstamd boundary.
  instrument     : NEWA-B
  datumintervall : 2020-01-02 .. 2020-12-30
  falt           : adj
  boundary       : 2020-05-14
  restriction    : ADJUSTED_SERIES_UNVERIFIED
  evidence_id    : price_defect_registry_v3.json#NEWA-B@2020-05-14
```

**Loader-status, ärligt redovisad:** 109 skript rör prislagret, 94 med direkt filaccess.
De är **inte** omskrivna. Att ändra dem vore en forskningslogikändring, vilket detta
uppdrag inte får göra — och de är redan körda, med domar som ska stå orörda. Gaten är
obligatorisk för **ny** revalidation; kravet är dokumenterat i
`loader_integration_report.json`.

---

## 3. RAW CLOSE

FLERIE, IMMNOV och SAS: fältet `close` blockerat, `adj` tillåtet. Ingen implicit fallback —
ett försök att läsa `close` är ett fel, inte en tyst omdirigering.

De tre raw-close-beroende skripten (`research_v_portfolio_risk_architecture`,
`research_x_orthogonal_improvements`, `research_z_model_risk_audit`, alla med mönstret
`c = np.array([r.get("close", r["adj"]) for r in rs])`) är **BLOCKED endast för dessa tre
instrument** och får köra på övriga 417.

En kompatibel väg finns dokumenterad — byta till `r["adj"]`, som är verifierat oskadad i
alla tre. Men om nominell prisnivå är metodologiskt nödvändig är bytet inte neutralt.
Forskningslogiken är oförändrad.

---

## 4. SERIES_SPLIT — automatisk återinträdeslogik

| Instrument | Boundary | Behållet segment | Eligible före | Eligible efter +1 år |
|---|---|---|---|---|
| BETS-B | 2022-05-13 | efter | nej | **ja** |
| MOMENT | 2021-02-19 | efter | nej | **ja** |
| ATORX | 2025-01-24 | före | **ja** | nej (segmentet borttaget) |
| QLINEA | 2025-01-13 | före | **ja** | nej (segmentet borttaget) |

`eligible()` blir automatiskt True igen så snart hela lookbacken ligger på en sida av
boundaryn — och False när det behållna segmentet saknar data i fönstret. Verifierat i
enforcement-testerna.

---

## 5. DE 71 COVIDFALLEN

Klassade `EXTERNALLY_UNVERIFIED_CORPORATE_ACTION`. **Ingen gissad RESCALE.**
Persistenta skiften (>20 dagar, >2 %) spärrar boundary crossing; icke-persistenta eller
små får användas fritt. Segmenten före och efter är giltiga var för sig.

---

## 6. ENFORCEMENT-TESTER — 29/29 PASS

Negativa (ska ge hårt fel): läsa blockerat adjusted segment · FLERIE/IMMNOV/SAS raw close ·
korsa SERIES_SPLIT (ATORX, BETS-B) · rullande momentum över blockerad boundary (SWED-A) ·
hela serien för instrument med boundary · fel price-SHA · gammalt register (V0) · utan
register · utan manifest · okänt instrument. **Alla PASS.**

Positiva (ska passera): SAS giltiga corporate action · BEIJ-B efter reparerad period ·
orestricerat instrument (VOLV-B, hela serien) · NEWA-B segment helt före respektive efter
boundary · **SSAB-A hela serien** (reparerad, alltså ingen boundary) · FLERIE adjusted ·
ATORX behållet segment. **Alla PASS.** Plus åtta `eligible()`-fall. 8 avvisningar loggade.

Två av mina egna första testfall var felskrivna — jag antog att SSAB-A fortfarande var
spärrad (den är reparerad) och att ATORX behöll sitt senare segment (det behöll det
tidigare). Testerna rättades; gaten var korrekt hela tiden.

---

## 7. STATISK PÅVERKAN PÅ REVALIDERINGSKANDIDATERNA

Inga tester körda. Räknat statiskt över alla 803.

| Påverkan | Antal |
|---|---|
| UNAFFECTED — annan datalinje (legacy) | 487 |
| PARTIALLY_REDUCED_SAMPLE | 189 |
| UNAFFECTED — ingen prisinput | 124 |
| RAW_CLOSE_DEPENDENT | 3 |
| **HELT BLOCKERADE** | **0** |

| Prioritet | Raw-close | Delvis | Opåverkad (pris) | Opåverkad (linje) |
|---|---|---|---|---|
| P0 | 0 | **60** | 0 | 0 |
| P1 | 0 | 42 | 12 | 4 |
| P2 | 0 | 27 | 16 | 101 |
| P3 | 3 | 46 | 49 | 31 |

Samtliga 60 P0-kandidater får reducerat urval i vissa fönster — ingen blockeras helt.

### Restriktionernas faktiska kostnad

| Datum | Med full 252d-lookback | Exkluderade av **restriktion** | Eligible |
|---|---|---|---|
| 2021-06-01 | 343 | **13** | 330 (96,2 %) |
| 2022-06-01 | 347 | 5 | 342 (98,6 %) |
| 2023-06-01 | 363 | 1 | 362 (99,7 %) |
| 2024-06-01 | 357 | 3 | 354 (99,2 %) |
| 2025-06-01 | 352 | 3 | 349 (99,1 %) |
| 2026-06-01 | 348 | 3 | 345 (99,1 %) |

Restriktionerna kostar som mest **13 instrument** i ett enskilt fönster — covidfönstret
2021. Därefter 1–5. Skillnaden mot totala universumet beror i huvudsak på **datatillgång**
(nyligen noterade instrument saknar full lookback), inte på restriktioner. Den distinktionen
är viktig: det ser ut som 84,5 % täckning 2026, men 99,1 % av dem som *har* full lookback
är eligible.

---

## 8. SLUTSIFFROR

| | |
|---|---|
| Restricerade instrument | **61** |
| Blockerade adjusted spans (boundaries) | **98** i 38 instrument, 48 unika datum, 2020-03-18 … 2026-05-07 |
| Raw-close-invalid spans | **3** (hela serien per instrument) |
| SERIES_SPLIT boundaries | **4** |
| Covid external-verification spans | **71** |
| Revalideringstester helt blockerade | **0** |
| Delvis påverkade | **192** (189 + 3 raw-close) |
| Opåverkade | **611** |
| Enforcement-gates | **29/29 PASS** |

Prisversion `bb88b8cf4817b058…` · register `a5ab339ef462f613…` · gate-manifest
`88caa5a97bfbba4c…` · identity mapping `NASDAQ_MM_IDENTITY_HISTORY_V1 + eodhd catalogue 2026-08`

---

## KVARSTÅENDE SVAGHET

Gaten är tvingande för allt som går genom den, men **de 94 befintliga skripten med direkt
filaccess är inte omskrivna**. Ingen teknisk spärr hindrar en framtida körning av dem från
att läsa prisfilen förbi gaten. Att stänga det kräver antingen omskrivning av
forskningslogik — utanför detta uppdrags mandat — eller att den gamla prisfilen görs
oläsbar, vilket skulle bryta reproducerbarheten för redan körda tester.

Det är en governanceåtgärd, inte en teknisk: **ny revalidation ska köras genom
`PriceGate`, och kravet är dokumenterat i `loader_integration_report.json`.**

---

Leveranser i `validated/prices_adjustment_repair_v4/`: `PRICE_RESTRICTION_REGISTRY.json` ·
`REVALIDATION_PRICE_GATE_MANIFEST.json` · `loader_integration_report.json` ·
`raw_close_restriction_report.json` · `series_split_eligibility_report.json` ·
`enforcement_test_results.json` · `static_candidate_impact.json`
Kod: `tools/revalidation_price_gate.py` · `tools/test_price_gate_enforcement.py`
