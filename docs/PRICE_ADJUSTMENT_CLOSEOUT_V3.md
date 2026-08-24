# PRICE_ADJUSTMENT_CLOSEOUT_V3

Datum: 2026-08-19 · Status: **PRICE_ADJUSTMENT_FOUNDATION_READY**

Inga forskningstester körda. Ingen champion ändrad. Inga gamla frysta filer
överskrivna — hash-verifierat.

---

## 1. DE 8 EXTREMA ADJUSTED-RETURN-FALLEN

Alla åtta diagnostiserade, **noll odiagnostiserade**. Nyckelobservationen: i sju av
åtta är justeringsfaktorn **oförändrad** — rå close hoppar, alltså inget justeringsfel.

| Instrument | Datum | Kvot | Faktor | Klass | Bevis | Åtgärd |
|---|---|---|---|---|---|---|
| ABLI | 2024-12-16 | 3,06 | oförändrad | VALID_EXTREME_CORPORATE_ACTION | volym 144 M mot 1–3 M (×50–100), nivån består i veckor | NO_ACTION |
| CANTA | 2025-07-15 | 3,55 | oförändrad | VALID_EXTREME_CORPORATE_ACTION | volym 74 M mot 0,5–1 M (×70) | NO_ACTION |
| OP | 2024-06-05 | 4,33 | oförändrad | VALID_EXTREME_CORPORATE_ACTION | volym 236 M mot ~1 M | NO_ACTION |
| OP | 2024-08-12 | 3,69 | oförändrad | VALID_EXTREME_CORPORATE_ACTION | volym 390 M mot ~1 M | NO_ACTION |
| **MOMENT** | 2021-02-19 | 7,13 | oförändrad | **SPURIOUS_ADJUSTMENT** | SKV `new_issue N 23:3, kurs 0,133` + Börsdata `N 6,8:1` på exakt datumet; kursen steg ×7,13 **utan** faktorändring — historiken restaterades aldrig. TERP ger 2,939, inte 7,131 | SERIES_SPLIT |
| **MORROW** | 2026-01-09 | 3,44 | oförändrad | **SERIES_BOUNDARY** | SKV: "Ny notering på Nasdaq Stockholm den 9 januari" | TRUNCATION |
| **SSM** | 2021-01-07 | 5,07 | oförändrad | **RAW_PRICE_ERROR** | rundresa 9,00 → 1,81 → 8,98 på fyra dagar; volym 24 238 på återhämtningen mot 1,8 M under felperioden | RAW_ROW_EXCLUSION |
| **ZETA** | 2021-10-08 | 3,38 | oförändrad | **RAW_PRICE_ERROR** | SKV bekräftar **27 kr** som sista betalkurs på avnoteringsdagen; mellanvärdena 6,30/8,22/8,01/7,99 är fel | RAW_ROW_EXCLUSION |

---

## 2. UTDELNINGENS TILLSTÅNDSMASKIN — 14 av 14 dubbelräkningar bevisade

Bland de 85 covidkandidaterna har 14 en **positiv** utdelningspost senare under 2020.
Mönstret är entydigt: faktorskifte vid det *ursprungligt planerade* ex-datumet i
mars–maj, och den faktiskt betalda utdelningen efter den uppskjutna stämman i juni–december.

Beviskravet var att den **faktiskt betalda** utdelningen har sin **egen** exakt avstämda
justering. Det håller i **14 av 14**:

| Instrument | Vårskifte | Kvot | Faktisk utdelning | Dess egen justering |
|---|---|---|---|---|
| NCC-B | 2020-04-02 | 1,2321 | 2020-11-13 (2,50) | 1,016036 EXAKT |
| WALL-B | 2020-04-29 | 1,2180 | 2020-10-01 (0,50) | 1,003669 EXAKT |
| WALL-B | 2020-10-29 | 1,1902 | 2020-10-01 (0,50) | 1,003669 EXAKT |
| LIFCO-B | 2020-04-27 | 1,0647 | 2020-06-25 (5,25) | 1,009032 EXAKT |
| SECU-B | 2020-05-08 | 1,0504 | 2020-12-10 (4,80) | 1,034470 STARK |
| SKA-B | 2020-03-27 | 1,0412 | 2020-10-23 (3,25) | 1,017882 EXAKT |
| RATO-B | 2020-04-02 | 1,0341 | 2020-10-23 (0,65) | 1,018791 EXAKT |
| MYCR | 2020-05-08 | 1,0247 | 2020-06-26 (2,00) | 1,011656 EXAKT |
| HUSQ-A | 2020-04-03 | 1,0162 | 2020-10-26 (2,25) | 1,023451 EXAKT |
| ARJO-B | 2020-04-28 | 1,0135 | 2020-06-30 (0,65) | 1,012344 EXAKT |
| MANG | 2020-04-03 | 1,0103 | 2020-07-01 (7,30) | 1,006805 EXAKT |
| GETI-B | 2020-04-23 | 1,0080 | 2020-06-29 (1,50) | 1,008569 EXAKT |
| BEIJ-B ×2 | 2020-04-17 / 10-02 | 1,3659 / 1,2344 | 2020-06-26 (1,75) | 1,006263 EXAKT |

**12 nya RESCALE** applicerade (BEIJ-B:s två var redan åtgärdade i V2). Övriga 71
kandidater: `INSUFFICIENT_EVIDENCE` — 35 utan 2020-post alls, 25 utan referensdata,
11 med nollpost på annat datum. Ingen extern data hämtad; de är märkta som krävande
extern verifiering.

---

## 3. DE 403 UNKNOWN SYSTEMATISERADE

405 kandidater i 104 instrument (99 stamaktier, 3 preferensaktier, 1 SDB, 1 unit).
Tre evidensbaserade regler flyttade dem:

| Metod | Kandidater |
|---|---|
| Kvartals-/regelbunden kadens (preferens- och D-aktier) | 131 |
| **Årlig utdelningskadens** (≥2 år, mars–juni, kvot 1,01–1,25) | 43 |
| Ren splitkvot (inom 0,2 % av n:1 eller 1:n) | 4 |
| **Kvar som UNKNOWN** | **213** |

Årskadensen träffade tolv instrument vars utdelningar helt saknas i Börsdatas kalender —
HAV-B 8 skiften över sex år i mars–juni, LAMM-B 5, INDU-A 4, NPAPER 4, NWG 4, SWEC-A 4.
Det är den svenska utdelningssäsongens signatur, inte defekter.

---

## 4. DE 241 UTAN BÖRSDATA-REFERENS

| Resolution | Kandidater |
|---|---|
| **RESOLVED_VIA_ISIN** | **126** |
| DELISTED_NO_BORSDATA_COVERAGE | 115 |

VESTUM (99 kandidater) och NYF (17) löstes via ISIN. De 115 kvarvarande tillhör
avnoterade instrument som Börsdata aldrig täckt — Swedish Match, LeoVegas, Kungsleden,
Concentric, Probi med flera. Identitetsmappningen är löst; referensdatan existerar inte.

---

## 5. RAW CLOSE-POLICY

Tre instrument har kvantiserad rå close:

| Instrument | Rader | Unika close | Min | Upplösningsfel |
|---|---|---|---|---|
| FLERIE | 787 | **4** (0,5 %) | 0,0001 | **50 %** |
| IMMNOV | 1 649 | 827 (50 %) | 0,0019 | 2,6 % |
| SAS | 1 164 | 979 (84 %) | 0,0026 | 1,9 % |

Den **justerade** serien är oskadad i alla tre. Motorerna `stack_h_motor.py` och
`h1419_motor.py` läser uteslutande `r["adj"]`, och 109 skript använder `adj`.

Men spårningen hittade **tre forskningsskript som faktiskt använder rå close** som
prisserie: `research_v_portfolio_risk_architecture`, `research_x_orthogonal_improvements`
och `research_z_model_risk_audit`, alla med mönstret
`c = np.array([r.get("close", r["adj"]) for r in rs])`.

**Dessa tre skript är BLOCKED för FLERIE, IMMNOV och SAS. Resten av projektet är inte
blockerat.** Tre andra rå-close-användare är legitima: turnover i kronor
(`g97p_confounder_audit`), adj-mot-close-jämförelse per konstruktion
(`tidig_detektion_och_utdelning`) och pris mot rapporterat resultat
(`spar_c_features_fundamenta_v2`).

---

## 6. SERIES_SPLIT-KOSTNADEN OMPRÖVAD

| Instrument | Förlorade rader | Förlorat intervall | Rekonstruktionsförsök |
|---|---|---|---|
| BETS-B | 596 | 2020-01-02 … 2022-05-12 | Korrekt multiplikator **är** härledbar: inlösen 1,97 kr ger 1,031315. **Men** brottdatumet 2022-05-13 ligger fem dagar före Skatteverkets ex-datum 2022-05-18. En omskalning förankrad i fel datum vore ett nytt fel — SERIES_SPLIT behålls tills avvikelsen är förklarad. |
| ATORX | 374 | 2025-01-24 … 2026-07-24 | TERP ej härledbar: unitstrukturen innehåller TO12 och TO13 vars värde inte ingår i formeln. |
| QLINEA | 383 | 2025-01-13 … 2026-07-24 | Samma unitproblematik. |
| MOMENT | 285 | 2020-01-02 … 2021-02-18 | TERP ur emissionsvillkoren ger 2,939 mot observerad 7,131; sannolikt kombinerad sammanläggning vars villkor saknas lokalt. |

Totalt **1 657 rader** offras (0,29 % av lagret). ATORX och QLINEA förlorar sin
*senare* period, BETS-B och MOMENT sin *tidigare*.

---

## 7. POST-CLOSEOUT FULL SCAN

| Klass | Antal | | Åtgärd | Antal |
|---|---|---|---|---|
| VALID_CORPORATE_ACTION | **1 899** | | NO_ACTION | 1 899 |
| RAW_PRICE_ERROR | 601 | | RAW_CLOSE_INVALID_DO_NOT_USE | 480 |
| UNKNOWN | 213 | | BLOCK | 382 |
| AMBIGUOUS_CORPORATE_ACTION | 39 | | RESCALE | **20** |
| SPURIOUS_ADJUSTMENT_FACTOR | 20 | | SERIES_SPLIT | 3 (+1 i v4) |
| TEMPORARY_SOURCE_ERROR | 12 | | | |
| IDENTITY_ERROR / SERIES_BOUNDARY | 1 | | | |

### Den avgörande separationen

**Olöst men IRRELEVANT för adjusted-close-forskning:** 601 RAW_PRICE_ERROR-kandidater
i tre instrument. Defekten sitter i rå close; den justerade serien är oskadad och R1
använder bara adjusted_close.

**Olöst OCH MATERIELLT:** **23 kandidater i 17 instrument** — permanenta faktorskiften
över 5 % utan förklaring, i instrument vars justerade serie används av forskning:
ACRI-B, KDEV, NEWA-B, CNCJO-B, GRNG, DORO, ENDO, PRFO, IMMU, ARION-SDB, SWED-A, PRIC-B,
BILL, ELAN-B, RESURS, B3, BILI-A. Dessa är registrerade som `ADJUSTED_SERIES_UNVERIFIED`.

Övriga 190 UNKNOWN är ≤5 % (storleksordningen för en normal utdelning) eller kortvariga.

---

## 8. QA-GATES

Kanonisk kandidat: `validated/prices_adjustment_repair_v4/prices_validated_adjustment_repair_v4.json`
SHA256 `bb88b8cf4817b05882699d3be3787132…` · **579 458 rader** · 420 serier ·
1 651 handelsdagar · 2020-01-02 … 2026-07-24

| Gate | Utfall |
|---|---|
| 19 krav-gates (borta/kvar per instrument) | **ALLA PASS** |
| Inga nya artificiella skarvar | **PASS — 0** |
| Genuina corporate actions bevarade | **PASS — SAS + 1 899** |
| Extrema adjusted-returns diagnostiserade | **PASS — 8 av 8, 0 odiagnostiserade** |
| Osorterade / dubbletter / ogiltiga värden | **0 / 0 / 0** |
| Ingen ±N-dagarsmaskering | **PASS** |
| Provenance per ändring | **PASS** |
| Gamla frysta filer orörda | **PASS** |

Kvarvarande |adj-avkastning| > 200 %: **4** — ABLI, CANTA, OP ×2, samtliga verifierade
marknadshändelser med NO_ACTION.

Versionskedja: v1.0 581 115 (orörd) → v2 579 762 → v3 579 762 → **v4 579 458**.

---

## 9. SLUTRAPPORT

| Fråga | Svar |
|---|---|
| **85 covidfall** | **14 lösta och reparerade** (12 nya + BEIJ-B ×2), **71 kvar** som INSUFFICIENT_EVIDENCE |
| **403 UNKNOWN** | **192 lösta**, **213 kvar** — varav endast **23 materiella** |
| **8 extremfall** | 4 VALID_EXTREME (NO_ACTION) · 1 SPURIOUS (SERIES_SPLIT) · 1 SERIES_BOUNDARY (truncation) · 2 RAW_PRICE_ERROR (radexklusion). **0 odiagnostiserade** |
| **Raw-close-invalid instrument** | **3** — FLERIE, IMMNOV, SAS |
| **Använder aktiv forskning rå close?** | **Ja, tre skript** — research_v, research_x, research_z. Blockerade för dessa tre instrument; övriga projektet fritt |
| **241 no-reference** | **126 lösta via ISIN**, 115 avnoterade utan Börsdata-täckning |
| **BETS-B / ATORX / QLINEA** | **Behåll SERIES_SPLIT.** BETS-B:s multiplikator är härledbar men datumavvikelsen på fem dagar är oförklarad; ATORX och QLINEA har ovärderbara teckningsoptioner |

### Kvarvarande blockerare som kan påverka framtida forskning

**23 materiella UNKNOWN i 17 instrument.** Permanenta faktorskiften över 5 % som varken
kan förklaras eller avfärdas med lokal data. De sitter i den justerade serien och kan
därför påverka avkastningsberäkningar för just dessa instrument. De är registrerade som
`ADJUSTED_SERIES_UNVERIFIED` så att forskning kan exkludera eller flagga dem — men de är
inte borttagna ur lagret.

Detta är den enda kvarvarande materiella risken. Enligt frysningskriteriet i uppdraget
räcker explicit blockering, och restriktionsregistret uppfyller det. Men det ska sägas
rakt ut: **blockeringen är en registerpost, inte en dataexkludering.** Den som kör
revalidering måste läsa registret.

---

Leveranser i `validated/prices_adjustment_repair_v4/`:
`prices_validated_adjustment_repair_v4.json` · `REPAIR_V4_MANIFEST.json` ·
`price_defect_registry_v3.json` · `dividend_state_machine.json` ·
`extreme_return_diagnostics.json` · `unknown_resolution_ledger.json` ·
`raw_close_restriction_registry.json` · `series_split_coverage_report.json` ·
`PRICE_FREEZE_CANDIDATE_MANIFEST.json`
