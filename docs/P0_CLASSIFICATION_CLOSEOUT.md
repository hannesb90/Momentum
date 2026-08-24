# P0 CLASSIFICATION CLOSEOUT

Datum: 2026-08-19 · Status: **P0_RESEARCH_QUEUE_BLOCKED**

Inga forskningstester körda. Ingen champion ändrad. Inga historiska domar ändrade.
Inga legacy-skript modifierade — hash-verifierat.

---

## 1. DE TVÅ H1419-SKRIPTEN → DATA_BUILD_FOUNDATION

Båda analyserade på utdata och beräkningsinnehåll:

| | `h1419_steg2_universum` | `h1419_universum_v2` |
|---|---|---|
| Utdata | `prices_h1419_universum.json`, membership, QA | `prices_h1419_universum_v2.json`, `membership_h1419_v2.json`, QA |
| CAGR / Sharpe / IC / spearman / alpha | **inga** | **inga** |
| Dom eller hypotesprövning | **ingen** | **ingen** |
| Råarkivsåtkomst | bygger lagret **ur** arkivet | d:o |

De transformerar och QA:ar datagrunden. Att de läser EODHD-arkivet är inte ett kringgående
— arkivet **är** deras indata.

**Klassificerade `DATA_BUILD_FOUNDATION`.** Borttagna ur forskningskön, kvar i inventoryn
med bevarad provenance och oförändrad historisk status. Att runnern blockerar dem i
REVALIDATION-mode är korrekt: ett databygge hör aldrig hemma i en revalidation.

---

## 2. `tidig_detektion_och_utdelning` — semantisk separation verifierad

Skriptet har tre block. Råarkivet rörs på exakt tre rader, alla inuti `del3_utdelning()`.

| Block | Datakälla | Karaktär |
|---|---|---|
| `del1_detektion(S.F26 / S.F19)` | motordata (gatad) | forskning |
| `del2_rotera(S.F26 / S.F19, tilt)` + `S.kor` + `S.boot` | motordata (gatad) | forskning — producerar `delta_cagr`, KI |
| `del3_utdelning()` | **EODHD-råarkiv** (`eod` + `div`) | data-QA |

**Separationen är verifierad, inte antagen:**

- `del3_utdelning()` tar **inga argument** — den kan inte ta emot forskningsdata.
- Dess returvärde skrivs enbart till `ut["utdelning"]` och läses aldrig av del 1 eller 2.
- Forskningsdelarna beräknas i `main()` **före** `del3` anropas.
- **Noll dataflöde** från rå-QA in i alfaresultatet.

Del 3 klassificeras `DATA_QA_INTRINSIC_RAW_ACCESS`: dess syfte är att verifiera att
`adjusted_close` bär utdelningen genom att jämföra `ret(adj)` mot `(close + utdelning)/close`.
Det **kräver** rå close och rå utdelningsbelopp. Ingen gatad källa kan ersätta det.

### Men kopplingen är exekveringsmässig

Semantiskt separerbar — exekveringsmässigt kopplad. `del3` körs i samma process och kastar
hårt fel **innan** `OUT.write_text()`, så forskningsresultatet skrivs aldrig. Att dela
skriptet i två kräver kodändring, vilket detta uppdrag inte får göra.

→ `RESEARCH_WITH_DATA_QA_COMPONENT`, `gating_status: PARTIALLY_BLOCKED`.
Alfainnehållet är fullt gatat; exekveringen kräver separat mandat.

---

## 3. `prima_storbolag` — adaptern kan inte accepteras

### Varför den läser råarkivet

`adv(k, dt)` beräknar **median** av `close × volume` över de 20 raderna före `dt`, med
minst 20 föregående rader och nollor exkluderade. (Docstringen säger "medelvärde"; koden
säger `np.median`. Koden är auktoritativ.)

### Dataparitetstest — endast input, ingen alfakod

| Fönster | Jämförbara | Identiska | Avvikande |
|---|---|---|---|
| **2020-2026** | 1 957 | **1 925 (98,4 %)** | 32 i 10 instrument |
| **2014-2019** | **0** | — | — |

Samtliga 32 avvikelser är förklarade: fem avnoterade där den gatade vyn trunkerar
(HIQ 2020-11-06, SMF 2020-06-24, FEEL 2021-08-06, ZETA 2021-10-08, COLL 2022-08-11) och
tre registrerade restriktioner (SSM, FLERIE, ATORX). Det är precis de spärrade och
defekta observationer som paritetskriteriet tillåter.

### Det som fäller adaptern

Skriptet kör **båda** fönstren (rad 173: `sim(S.F26, ...)`, `sim(S.F19, ...)`).

Den gatade H1419-vyn har fälten `['adj', 'd']`. **Noll av 290 instrument har volym.**
ADV kan därför inte beräknas alls för 2014-2019 ur gatad data.

Dataparitet kan inte visas för det fönstret → **ingen adapter accepteras**.

`adapter_status: ADAPTER_NOT_POSSIBLE`, `gating_status: BLOCKED`.
Originalskriptet är oförändrat, sha `7710f76cc46767d5…`.

**Konkret åtgärd:** lägg till volymfält i H1419-lagret. Det är ett databygge och kräver
separat mandat. Då blir adaptern möjlig för båda fönstren.

---

## 4. ENFORCEMENT ÄR INTE FÖRSVAGAD

Ingen ändring gjord i runnern för att göra dessa skript gröna.
`UNGATED = {}` · ingen silent fallback · ingen direktåtkomst till råarkiv · ingen
PriceGate-bypass · inget undantag från freeze-manifestet. Hård fail kvarstår.

Freeze-manifest: 17 komponenter, **0 avvikande hash**. Runner preflight: **PASS**.

---

## 5–6. FAKTISK P0-KÖ EFTER KLASSIFICERING

| | Antal |
|---|---|
| Ursprungliga P0 | **60** |
| DATA_BUILD_FOUNDATION | **2** |
| DATA_QA-only | **6** |
| **Genuina RESEARCH_TEST** | **52** |

Av de 52 genuina:

| | Antal | |
|---|---|---|
| FULLY_GATED | **48** | |
| PARTIALLY_BLOCKED | 3 | `tidig_detektion_och_utdelning`, `lonsamhetstilt_mot_stack_h`, `spar_c_features_fundamenta` |
| BLOCKED | 1 | `prima_storbolag` |
| ADAPTER_REQUIRED | 1 | `prima_storbolag` — ej möjlig |
| **UNGATED** | **0** | |

### Exekverbarhet — den distinktion som avgör

Två av de tre PARTIALLY_BLOCKED **kan köras**. `lonsamhetstilt_mot_stack_h` och
`spar_c_features_fundamenta` läser inga förbjudna sökvägar; deras begränsning är att
fundamentalurvalet är survivorship-begränsat (1 av 68 avnoterade har data). De är körbara
med deklarerad begränsning.

| | Antal |
|---|---|
| **Kan exekveras via runner** | **50 av 52** |
| varav med deklarerad begränsning | 2 |
| **HARD FAIL vid exekvering** | **2** — `tidig_detektion_och_utdelning`, `prima_storbolag` |

---

## 7–8. SLUTTABELL

| Skript | execution_role | Rå-åtkomst, skäl | Forskningsrelevant | Fully gated | Adapter | Slutlig disposition |
|---|---|---|---|---|---|---|
| `h1419_steg2_universum` | DATA_BUILD_FOUNDATION | bygger lagret ur arkivet | **NEJ** | N/A | N/A | **Bort ur research queue**, kvar i inventory |
| `h1419_universum_v2` | DATA_BUILD_FOUNDATION | d:o | **NEJ** | N/A | N/A | **Bort ur research queue**, kvar i inventory |
| `tidig_detektion_och_utdelning` | RESEARCH_WITH_DATA_QA_COMPONENT | del 3 verifierar att `adj` bär utdelning — kräver rå close + utdelningsbelopp | **JA** | NEJ | ej krävd för forskningsdelarna | **Kvar, PARTIALLY_BLOCKED** — kräver mandat att dela skriptet |
| `prima_storbolag` | RESEARCH_TEST | ADV = median(close × volume) ur arkivet | **JA** | NEJ | **ADAPTER_NOT_POSSIBLE** | **Kvar, BLOCKED** — kräver volym i H1419 |

---

## SLUTSTATUS

| READY-krav | Utfall |
|---|---|
| DATA_BUILD bortklassade från research queue | **JA** — 2 st |
| DATA_QA-only räknas inte som alfa-revalidation | **JA** — 6 st |
| **Alla genuina P0-researchtester kan köras via runner** | **NEJ — 50 av 52** |
| 0 ungated research input | **JA** |
| Inga legacy-skript modifierade | **JA** — hash-verifierat |
| Freeze/hash/enforcement fortsatt PASS | **JA** — 17/17, preflight PASS |

Sex av sju krav uppfyllda. Det sjunde faller på två skript.

### Konkreta återstående blockerare

**B1 — `prima_storbolag` kan inte köras.** ADV kräver volym; den gatade H1419-vyn har
ingen. Åtgärd: lägg till volymfält i H1419-lagret (databygge, separat mandat). Paritet
för 2020-2026 är redan visad till 98,4 % med samtliga avvikelser förklarade, så adaptern
blir accepterbar så snart 2014-2019 kan mätas.

**B2 — `tidig_detektion_och_utdelning` kan inte köras hel.** Forskningsdelarna är fullt
gatade och semantiskt oberoende av rå-QA-delen — det är verifierat, inte antaget. Men
del 3 avbryter processen innan resultatet skrivs. Åtgärd: mandat att dela skriptet i en
forskningsdel och en QA-del. Ingen datagrundsändring behövs.

Ingen av dem är ett fel i datagrunden. Båda är konsekvenser av att enforcement är verklig.

---

Leveranser: `research_k/p0_closeout/P0_CLASSIFICATION_CLOSEOUT.json` ·
`research_inventory/revalidation_candidate_map_v4.json` ·
uppdaterad `research_k/revalidation_runs/DIRECT_ACCESS_INVENTORY.json`
