# P0 EXECUTION CLOSEOUT

Datum: 2026-08-19 · Status: **P0_RESEARCH_QUEUE_FULLY_GATED**

Inga forskningstester körda. Ingen champion ändrad. Inga historiska domar ändrade.
**Inga legacy-skript modifierade** — 321 hashar mot baslinjen, 0 ändrade.

---

## B1 — `prima_storbolag`

### H1419 kompletterat med volym

`tools/build_h1419_volume.py` → `validated/h1419_volume_v1/`. Befintligt H1419 orört.

| | |
|---|---|
| Instrument | **290 / 290** |
| Förväntade rader | 519 829 |
| **Matchade rader** | **519 829 (100 %)** |
| Saknade i arkivet | **0** |
| Dubbla datum | **0** |
| Identitetsavvikelser | **0** |

Regler: samma instrumentidentitet, samma datum, samma handelskalender, `volume`/`close`
från exakt den EODHD-källa legacy-skriptet läser. Ingen forward fill, ingen interpolation,
ingen modern backfill, inga observationer utanför ursprungligt H1419-universum.

### Gating tillämpad

`prices_h1419_gated_with_volume.json` — 290 instrument, **501 502 rader**, fälten
`adj + d + close + v`. Radmängden är **identisk** med prisvyns. Volymlagrets 18 327 rader
utanför gatade segment är korrekt uteslutna: en observation blir inte eligible bara för
att volym finns.

### ADV-paritet — exakt legacy-definition

Median av `close × volume` över de 20 föregående raderna, minst 20 rader, nollor
exkluderade. Ingen signal-, ranking- eller backtestkod körd.

| Fönster | Jämförbara | Identiska | Avvikande |
|---|---|---|---|
| 2020-2026 | 1 957 | **1 925 (98,4 %)** | 32 |
| **2014-2019** | 1 431 | **1 382 (96,6 %)** | 49 |

**Samtliga 49 avvikelser i 2014-2019 förklarade — 0 oförklarade.** 37 tillhör
restriktionsregistret; de återstående 12 är instrument där H1419:s egen QA uteslöt rader
vid bygget, verifierat rad för rad: NOMI 322 uteslutna, AQ/HEXA-B/INVE-A/SGG 71,
ELUX-B/RROS 68, ASP 12.

### Benchmarken gatades också

`index_serie()` läser XACT-SVERIGE ur råarkivet för tracking error. Den gatades separat:
5 498 rader, 0 dubbletter, sorterad. Faktorskanningen gav 5 skiften — samtliga i juni över
fem olika år med kvoter 1,0543–1,0959, alltså ETF:ens årliga utdelning. Samma årskadensregel
som applicerats på aktielagren. **0 oförklarade skiften, inga restriktioner.**

### Adaptern

`tools/revalidation_adapters.py` · sha `267855a5ba6e10b5…` · patchar `adv` och `index_serie`
i en redan importerad modul. **Oförändrat:** signal, parametrar, ranking, filter,
universumlogik, resultatlogik. Originalskriptet är byte-identiskt, sha `7710f76cc46767d5…`.

Rå-åtkomst-QA med sandboxen aktiv och full förbudslista: 6/6 ADV-anrop lyckades,
`index_serie` returnerade korrekt, **0 nekade sökvägar**. Ingen alfakod exekverad.

**`prima_storbolag`: BLOCKED → FULLY_GATED via ADAPTER_ACCEPTED.**

---

## B2 — `tidig_detektion_och_utdelning`

`tools/revalidation_wrapper_tidig_detektion.py` · sha `e73a0f50f564c9b5…`
Originalet orört, sha `b7d29fb8afbc36ae…`.

Wrappern anropar `del1_detektion` och `del2_rotera` med exakt samma argument, i samma
ordning, och skriver forskningsnyttolasten separat. `del3_utdelning()` utelämnas.

### Programsemantisk ekvivalens — 6/6 PASS

Ingen forskningskod exekverad; jämförelsen sker på AST-nivå.

| Kontroll | Utfall |
|---|---|
| Samma antal forskningssatser | **PASS** — 3 mot 3 |
| Varje forskningssats identisk (AST) | **PASS** — 0 avvikande |
| Wrappern anropar aldrig `del3_utdelning` | **PASS** — 30 anrop, inget till del3 |
| Originalskriptet oförändrat | **PASS** |
| Identiska nyttolastnycklar | **PASS** — `detektion`, `rotation` |
| Samma funktionsanrop med samma argument | **PASS** — 4 mot 4 |

Två av mina första kontroller föll: importsatser räknades som forskningssatser, och
del3-kontrollen matchade docstring-text i stället för anrop. Båda var fel i testet, inte i
wrappern; rättade och gröna.

### DATA_QA-läget

`del3_utdelning()` förblir `DATA_QA_INTRINSIC_RAW_ACCESS` och körs i ett eget läge med
eget `run_id` och eget manifest. Reglerna är definierade i
`DATA_QA_MANIFEST_DEFINITION.json`: får läsa rådata, får **aldrig** producera ett
forskningsresultat, dess utdata får aldrig vara input till ett forskningstest, och
acceptansgrinden avvisar det som revalidation. Dess resultat krävs aldrig för att ett
forskningsresultat ska accepteras.

**`tidig_detektion_och_utdelning`: PARTIALLY_BLOCKED → FULLY_GATED via WRAPPER_ACCEPTED.**

---

## SLUTLIG P0-PREFLIGHT

Runner preflight **PASS**. Dry-run av samtliga genuina P0. Ingen alfa- eller backtestkod
exekverad.

| | Antal |
|---|---|
| Ursprungliga P0 | 60 |
| DATA_BUILD_FOUNDATION | 2 |
| DATA_QA-only | 6 |
| **Genuina RESEARCH_TEST** | **52** |
| **FULLY_GATED** | **52** |
| **BLOCKED** | **0** |
| **UNGATED** | **0** |
| Adapter krävs | 1 (`prima_storbolag`) |
| Wrapper krävs | 1 (`tidig_detektion_och_utdelning`) |
| Datamässigt begränsade | 2 |

De två datamässigt begränsade — `lonsamhetstilt_mot_stack_h` och
`spar_c_features_fundamenta` — är **exekveringsmässigt fullt gatade**. Deras begränsning är
att fundamentalurvalet har delisted coverage 1/68. Det är en datatäckningsfråga för
`DELISTED_FUNDAMENTALS_RECOVERY`, inte en exekveringsblockering, och statusen är
oförändrad enligt instruktion.

---

## ENFORCEMENT OFÖRSVAGAD

| | |
|---|---|
| Bypass-svit | **29/29 PASS** |
| PriceGate-svit | **29/29 PASS** |
| `UNGATED` | `{}` |
| Freeze-manifest | 17/17 komponenter, 0 avvikande hash |
| Legacy-skript ändrade | **0 av 321** |

Adaptern och wrappern försvagar ingenting: båda konsumerar **enbart** gatade källor, och
råarkivet är fortsatt förbjudet i REVALIDATION-mode. Adaptern ersätter datakällan, inte
forskningslogiken; wrappern anropar befintliga funktioner, den skriver inte om dem.

---

## SLUTRAPPORT

| | |
|---|---|
| H1419 volume coverage | **519 829 / 519 829 rader, 290/290 instrument, 0 saknade** |
| H1419 volume parity | **96,6 % identisk ADV, 0 oförklarade avvikelser** |
| `prima_storbolag` | **FULLY_GATED** via adapter `267855a5ba6e10b5…` |
| `tidig_detektion_och_utdelning` | **FULLY_GATED** via wrapper `e73a0f50f564c9b5…`, ekvivalens 6/6 |
| Genuine P0 count | **52** |
| FULLY_GATED | **52** |
| BLOCKED | **0** |
| UNGATED | **0** |
| Legacy script hashes unchanged | **JA** — 0 av 321 ändrade |
| Enforcement/bypass QA | **PASS** — 29/29 + 29/29 |

---

Leveranser: `validated/h1419_volume_v1/` · `validated/prices_h1419_gated/prices_h1419_gated_with_volume.json` ·
`validated/prices_h1419_gated/H1419_ADV_PARITY_REPORT.json` · `validated/benchmark_gated/` ·
`research_k/p0_closeout/{P0_FINAL_PREFLIGHT,WRAPPER_EQUIVALENCE,ADAPTER_RAW_ACCESS_QA,DATA_QA_MANIFEST_DEFINITION}.json` ·
`research_inventory/revalidation_candidate_map_v5.json`
Kod: `tools/build_h1419_volume.py` · `tools/revalidation_adapters.py` ·
`tools/revalidation_wrapper_tidig_detektion.py` · `tools/test_wrapper_semantic_equivalence.py`
