# REVALIDATION EXECUTION ENFORCEMENT

Datum: 2026-08-19 · Status: **REVALIDATION_EXECUTION_ENFORCEMENT_READY**

Inga forskningstester körda. Ingen champion ändrad. Inga historiska domar ändrade.
**Inga legacy-skript modifierade.**

---

## 1. CENTRAL RUNNER

`tools/revalidation_runner.py` · sha `85aeacb0e0f0eabb…`

Preflight verifierar innan en enda rad exekveras: gate-manifest, restriktionsregister,
kanonisk prisfil, PriceGate-implementation, sandbox-implementation, prisfilens SHA mot
manifest, registrets SHA mot manifest, registerversion, och universum-/datafrysning.
Saknas något — eller avviker en hash — körs ingenting.

Fundamenta/PIT-manifest är explicit markerat `EJ_TILLGANGLIGT` i varje manifest och
kopplas in när den frysningen är klar.

---

## 2. LEGACY-SKRIPTEN ÄR ORÖRDA

321 skript i `tools/`. **7 skapade i detta arbete** (gate, sandbox, runner,
acceptansgrind, två testsviter, repair_v2). Inga imports, sökvägar, loaders,
forskningslogik eller parametrar ändrade i något befintligt skript.

Hash-baslinje för samtliga 321 ligger i `LEGACY_SCRIPT_HASHES.json`.

Enforcement sker i **miljön runt** skripten, inte i dem.

---

## 3. ISOLERING VIA SÖKVÄGSAVLYSSNING

`tools/revalidation_sandbox.py` installeras i barnprocessen innan målskriptet importeras.
Hookar `builtins.open`, `io.open`, `gzip.open`, `pathlib.Path.open/read_text/read_bytes`,
`os.open` och `pandas.read_csv/json/parquet/pickle/table`.

Avlyssningen verkar på **absolut sökväg vid öppningstillfället**. Hur sökvägen skrevs i
koden — absolut, relativ, via `glob`, via `pathlib` — spelar ingen roll.

Tre klasser:

| Klass | Beteende |
|---|---|
| **REDIRECTED** | `validated/prices/prices_validated.json` → den gatade vyn. Varje omdirigering loggas. |
| **FORBIDDEN** | v1.1, v2_0, repair_v2, repair_v3, `.bak_`, `_SUPERSEDED_`, EODHD-råarkivet, legacy-cache. **HARD FAIL.** |
| **UNGATED_REQUIRES_DECLARATION** | `validated/prices_h1419/` — se §5. |

Originalfilerna är orörda och fullt läsbara i `HISTORICAL_REPRODUCTION`.

---

## 4. PRICEGATE APPLICERAS ÄVEN PÅ DIREKTLÄSANDE SKRIPT

Ett legacy-skript kan inte anropa `PriceGate` — det vet inte att den finns. Därför
**materialiseras** restriktionerna i den gatade vyn innan skriptet startar:

- **Boundary-restriktioner** → endast det längsta giltiga segmentet exponeras. Ett skript
  som beräknar 12-månaders momentum *kan inte* korsa en spärr, eftersom data på andra
  sidan inte finns i vyn.
- **RAW_CLOSE_INVALID** → instrumentet utesluts **helt** om körningen deklarerat
  `--price-fields adj,close`. Behålls om bara `adj` deklarerats. Ingen tyst fallback från
  `close` till `adj`.

Vyn är deterministisk och cachad på `(prisfil-SHA, register-SHA, deklarerade fält)`.
Varje utesluten observation räknas och skrivs i manifestet: **8 688 observationer** i
adj-läget, med instrument och skäl per post.

---

## 5. DET HÅL SOM HITTADES OCH STÄNGDES

`validated/prices_h1419/` — 2014–2019-ryggraden — var varken omdirigerad eller förbjuden,
och läses av **20 skript** inklusive kärnmotorn `h1419_motor.py` och `h0_v3_kor.py`.
Den har **inget restriktionsregister** och kan därför inte gatas.

Att tyst tillåta den vore precis det hål uppdraget skulle stänga. Att förbjuda den vore
att göra det andra forskningsfönstret oanvändbart. Lösningen:

**Förbjuden som standard.** Kan släppas in med explicit `--allow-ungated prices_h1419`,
vilket stämplar manifestet och nedgraderar acceptansgrindens svar från `VALID` till
**`VALID_WITH_UNGATED_INPUT`**. Ett sådant resultat är därmed permanent skiljbart i
ledgern. Det kan aldrig ske tyst.

---

## 6. TVÅ LÄGEN

| | REVALIDATION | HISTORICAL_REPRODUCTION |
|---|---|---|
| Körväg | endast central runner | runner, explicit läge |
| Data | kanonisk frysning | legacy-data |
| Gamla sökvägar | **oåtkomliga** | tillåtna |
| PriceGate / register | obligatoriskt | ej tillämpligt |
| Exekveringsmanifest | obligatoriskt | skapas, men märkt |
| Resultatklass | forskningsresultat | `HISTORICAL_REPRODUCTION_ONLY` |

Acceptansgrinden avvisar `HISTORICAL_REPRODUCTION` som ny revalidation — verifierat i test.

---

## 7. EXEKVERINGSMANIFEST OCH ACCEPTANSGRIND

Varje körning skriver ett immutabelt manifest med run_id, test_id, test_family,
script_path, script_sha256, timestamp, execution_mode, code provenance, price_file,
price_sha256, restriction_registry + sha + version, PriceGate-sha, sandbox-sha,
universe manifest + sha, identity mapping hash, fundamentals/PIT-status, effective sample
dates, excluded observations, restricted instruments, gate status och exit status.

`tools/validate_revalidation_run.py` returnerar `VALID`, `VALID_WITH_UNGATED_INPUT` eller
**`REVALIDATION_RESULT_INVALID`**. Den kontrollerar mode, samtliga hashar mot *levande*
filer (inte bara mot manifestet), gate-status, exit-status, förbjudna sökvägar i
åtkomstloggen, att restriktionsregistret faktiskt applicerats, och manifestets
fullständighet. Ett ogiltigt resultat får inte föras in i ledger, champion eller
preregistrerade resultat.

---

## 8. BYPASS-TESTER — 23/23 PASS

Negativa (ska ge HARD FAIL i REVALIDATION): absolut legacy-path · relativ path ·
`Path.read_text` · `Path.read_bytes` · `gzip.open` mot råarkivet · legacy-cache ·
`os.open` · `pandas.read_json` · glob följt av open · superseded fundamenta ·
**ogatat h1419 utan deklaration** · okänt exekveringsläge · okänt ogatat lager ·
manipulerad price-SHA · körning utan exekveringsmanifest ·
`HISTORICAL_REPRODUCTION` som revalidation. **Alla PASS.**

Positiva: legacy-sökvägen omdirigeras till maskad vy · raw-close-körning utesluter
FLERIE/IMMNOV/SAS · boundary kan inte korsas (NEWA-B) · deklarerat ogatat lager ger
`VALID_WITH_UNGATED_INPUT` · **HISTORICAL_REPRODUCTION accepterar legacy-skript
oförändrat** · acceptansgrind på giltig körning. **Alla PASS.**

---

## 9. INVENTERING AV DIREKTLÄSANDE SKRIPT

121 skript med hårdkodad prissökväg (fler än de 94 tidigare räknade — den siffran
missade `prices_h1419`- och råarkivsläsarna).

| Enforcement | Skript |
|---|---|
| REDIRECTED_TO_GATED_VIEW | **82** |
| UNGATED_REQUIRES_DECLARATION | 20 |
| FORBIDDEN_HARD_FAIL | 17 |
| NO_PRICE_PATH | 2 |
| **Interceptbara** | **121/121** |

Läsmetoder i beståndet: `json.loads` 111 · `read_text` 111 · `open` 29 · `json.load` 24 ·
`gzip.open` 21 — samtliga täckta av hookarna. Ingen script-rewrite.

*Rättelse:* en tidigare räkning angav 12 icke-interceptbara. Det var ett artefakt av att
regexen fångade docstring-text som sökvägar. Avlyssningen sker vid öppningstillfället och
är universell.

---

## 10. CANDIDATE MAP

Åtta metadatafält tillagda per kandidat: `required_execution_mode`, `runner_compatible`,
`price_gate_required`, `price_enforcement_status`, `requires_ungated_declaration`,
`raw_close_dependency`, `restricted_window_impact`, `expected_eligible_fraction`.
Endast metadata — ingen dom ändrad.

**P0: 60 kandidater.** Runnerns preflight PASS, samtliga 60 skript existerar.
15 kräver PriceGate, **5 kräver `--allow-ungated prices_h1419`**, 0 är raw-close-beroende.
41 rör inte prislagret alls.

---

## SLUTRAPPORT

| | |
|---|---|
| Legacy-skript totalt (`tools/`) | **321** |
| Skapade i detta arbete | 7 |
| Direktläsande prisskript | **121** |
| Enforceable via runner | **121/121** |
| Ej enforceable | **0** |
| Negativa bypass-tester | **23/23 PASS** |
| PriceGate-tester (tidigare) | 29/29 PASS |
| Historisk reproduktion fortfarande möjlig | **JA** — verifierat i test |
| Script-hashar oförändrade | **JA** |
| P0-kandidater runner-ready | **JA — 60/60** |

Prisfil `bb88b8cf4817b058…` · register `a5ab339ef462f613…` · runner `85aeacb0e0f0eabb…` ·
sandbox `87f23bad75dda456…` · gate `b99efe030d45411c…`

---

## VAD SOM ÄR ÄRLIGT ATT SÄGA OM RÄCKVIDDEN

Enforcement är fullständig **för allt som körs genom runnern**. Den är inte en
operativsystemsspärr: en framtida användare som kör `python tools/nagot.py` direkt från
skalet går förbi alltihop. Det är samma klass av risk som förut, med en skillnad — nu
finns en körväg som är komplett, testad och som gör varje kringgående synligt genom att
resultatet saknar exekveringsmanifest och därmed avvisas av acceptansgrinden.

Med andra ord: **kringgåendet går fortfarande att göra, men resultatet går inte att
använda.** Det är den starkaste garantin som kan ges utan att modifiera legacy-koden
eller göra gamla data oläsbara — båda uttryckligen förbjudna i detta uppdrag.

Kvar att koppla in när underlaget finns: fundamenta-/PIT-frysning, och ett
restriktionsregister för `prices_h1419` så att det ogatade lagret kan gatas i stället för
att deklareras.

---

Kod: `tools/revalidation_runner.py` · `tools/revalidation_sandbox.py` ·
`tools/validate_revalidation_run.py` · `tools/test_revalidation_bypass.py`
Artefakter: `research_k/revalidation_runs/` — `ENFORCEMENT_MANIFEST.json` ·
`BYPASS_TEST_RESULTS.json` · `DIRECT_ACCESS_INVENTORY.json` ·
`LEGACY_SCRIPT_HASHES.json` · `P0_RUNNER_READINESS.json`
