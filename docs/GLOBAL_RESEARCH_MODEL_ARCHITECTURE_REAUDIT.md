# GLOBAL RESEARCH RESET AUDIT

Datum: 2026-08-19 · Status: **AUDIT KLAR — INGA TESTER KÖRDA, INGA MODELLER TRÄNADE**

H0 V3 är oförändrad och förblir **fryst PIT-korrekt referensbenchmark** — inte en
arkitektonisk begränsning och inte automatiskt slutlig champion.

---

## GENOMSÖKT

1 334 py-filer i `momentum_v2`, `momentum_prod_work` och `momentum_exports_2026-08-02`
(exklusive venv, node_modules, site-packages, .git). Plus 212 markdown, 114
preregistreringar, 45 frysfiler, 803 katalogiserade tester, `spard/`, `sparg/`,
`research_i/`, `research_k/`, `panels/`, `validated/`, `trackh/`, `trackj/`, samt
prod_works 793 git-commits.

Verifiering skedde mot **CODE → INPUT → RESULT → REPORT** där kedjan fanns. Textpåståenden
utan beräkning klassas `NON_COMPUTED_CLAIM`.

---

## FYND 1 — DEN GLOBALA MODELLNIVÅN ÄR INTE IDENTIFIERAD

Två modellrace finns, och **båda vilar på icke-PIT-verifierat medlemskap**.

### Race A — H1419 sexmodellsracet (`h0_validator_model_race_1419.py`)

Preregistrerat, prisbaserade features, fasta hyperparametrar, tränat 2014-2016,
dev 2017, final 2018-19. Modellerna testas som **exit-/entry-validatorer på H0**, inte
som fristående rankare.

| Modell | IC 2017 | IC 2018-19 | exit Δ 2017 | exit Δ 2018-19 | entry Δ 2017 | entry Δ 2018-19 | Båda positiva |
|---|---|---|---|---|---|---|---|
| **ExtraTrees** | 0,0827 | 0,1172 | **+0,0164** | **+0,0110** | **+0,0131** | **+0,0167** | **JA / JA** |
| **CatBoost** | 0,0941 | 0,1115 | **+0,0117** | **+0,0126** | **+0,0305** | **+0,0042** | **JA / JA** |
| RandomForest | 0,0709 | 0,1133 | −0,0073 | +0,0386 | −0,0006 | +0,0370 | nej — teckenbyte |
| HistGradBoost | 0,0619 | 0,0850 | −0,0350 | +0,0183 | +0,0273 | +0,0222 | nej / ja |
| **LightGBM** | 0,0616 | 0,0983 | −0,0448 | +0,0283 | −0,0222 | **+0,0426** | nej — teckenbyte |
| Ridge | 0,0275 | 0,0774 | −0,0392 | −0,0019 | −0,0276 | −0,0093 | nej / nej |

Inget t-värde överstiger 2,05. 2017 års bootstrapintervall är degenererade (13 paneler).
Universum: H1419 V2, medlemskap **ej** PIT-verifierat. Baslinje: fryst H0, **inte H0 V3**.

### Race B — spår D (`spard_neutral_race.py`), OOS 2024-2025

| Familj | mean IC | median IC | **top-30 IC** | CAGR | excess | Sharpe | leave-top3 |
|---|---|---|---|---|---|---|---|
| **momentum_52w** | **0,1327** | **0,1647** | −0,0434 | 0,1511 | 0,0109 | 0,102 | 0,0470 |
| catboost | 0,0893 | 0,0836 | −0,1167 | **0,4224** | 0,2822 | **1,528** | 0,2303 |
| xgboost | 0,0950 | 0,1053 | −0,1869 | 0,3835 | 0,2433 | 1,402 | 0,2268 |
| lightgbm | 0,0716 | 0,0781 | −0,2140 | 0,4075 | 0,2673 | 1,383 | 0,2210 |
| ridge | −0,0024 | −0,0107 | −0,0841 | 0,1994 | 0,0592 | 0,362 | 0,0353 |
| elasticnet | −0,0237 | −0,0244 | −0,1003 | 0,1734 | 0,0331 | 0,236 | 0,0134 |

Verdikt: **C) SVAG/INGEN MODELLSIGNAL**, ingen familj vald.

Jag verifierade förkastningskriteriet mot de faktiska talen. Det håller: **samtliga sex
familjer, inklusive momentumbaslinjen, är koncentrationsfragila** enligt den
preregistrerade regeln. Leave-top-3-out tar bort 64–70 % av trädfamiljernas
överavkastning och gör den negativ för momentum, ridge och elasticnet. Regeln tillämpades
symmetriskt och korrekt.

**Men:** `panels/core_panel.json` — racets indata — bär
`"membership_verified": false, "membership_basis": "HISTORICAL_MEMBERSHIP_UNKNOWN"`.
Hela racet kördes på en population vars historiska medlemskap var okänt.

### Mönstret som förenar båda racen

Bred IC är positiv för trädfamiljerna, men **top-30 IC är negativ för alla sex**. Modellerna
rangordnar hela tvärsnittet bättre än slumpen men fallerar *inuti* den investerbara toppen.
Det är samma sak som projektet redan konstaterat i annat sammanhang: IC ≠ handelsbar spread.

---

## FYND 2 — LIGHTGBM BLEV ALDRIG FALSIFIERAD

Frågan var: föll modellfamiljen, eller föll en implementation på bristfällig datagrund?

**Svaret är det senare.** LightGBM har testats tre gånger:

1. **H1419-racet:** byter tecken i båda rollerna (exit −0,0448 → +0,0283, entry −0,0222 →
   +0,0426). Dess starkaste enskilda tal — entry +0,0426, t = 2,05 — är hela tabellens högsta.
2. **Spår D:** CAGR 40,75 %, Sharpe 1,383, positiv OOS median IC. Förkastad på en
   fragilitetsregel som *också* förkastade momentumbaslinjen.
3. **Legacy prod (LambdaRank):** domen finns bara i prosa, ingen avstämbar artefakt.

Ingen av de tre kördes på PIT-verifierat medlemskap. Ingen kördes mot H0 V3. Ingen
uppfyllde tvåfönsterkriteriet.

`REJECTION_STILL_IDENTIFIED: NEJ.` Samma gäller CatBoost, XGBoost och ExtraTrees.

**XGBoost är ett särfall:** explicit exkluderat ur H1419-racet med motiveringen *"Not
installed in the reproducible /opt/momentum/venv environment"*. Det har alltså aldrig
testats i validator- eller overlayrollen.

De enda förkastanden som **står** oberoende av universumfrågan är **Ridge** och
**ElasticNet** — båda negativa i båda delperioderna och med negativ OOS mean IC.

---

## FYND 3 — DET STARKASTE KOMPLEMENTARITETSFYNDET

ExtraTrees som **overlay** på H0: H0 genererar Top-30, ET omordnar endast dessa och tar Top-20.

| Period | H0 Top-30 | ET Top-20 | Δ CAGR |
|---|---|---|---|
| 2017 | 35,72 % | 38,88 % | +3,16 pp |
| 2018 | −0,01 % | −1,75 % | **−1,74 pp** |
| 2019 | 34,89 % | 47,42 % | +12,53 pp |
| 2018–19 | 16,14 % | 20,35 % | +4,21 pp |
| 2017–19 | 22,33 % | 24,51 % | +2,18 pp |

Mot **H0 Top-20** (rätt jämförelse vid samma N): **+10,42 pp** (2017) och **+9,97 pp** (2018-19).

Dokumenterad dom: **PERIOD-DEPENDENT VALUE**, inte Economic Value Confirmed. Skälen är
redovisade och håller: turnover +40 % (7,75 mot 5,53), MaxDD försämras 2017 och 2018,
2017 års överavkastning kommer till 78 % från den största procenten positiva dagsdifferenser,
och **mekanismen är instabil** — 2017 års drivande features är H0/rank/momentum medan
2018-19 års är marknadsregimfeatures.

Beslutslagret kvalificerar inte som live decision layer; enda försvarbara är en shadow
second opinion utan handelsåtgärd.

Detta är exakt fallet som prompten pekar på: **en modell som inte kan köra standalone i sin
design men som tillför mätbart värde betingat på H0.** Ett gammalt negativt
standalone-resultat får inte användas mot ensemblevärdet.

---

## FYND 4 — L4 EXISTERAR INTE

Av 803 tester:

| Nivå | Antal |
|---|---|
| L0 DATA/ELIGIBILITY | 182 |
| L1 GLOBAL SIGNAL | 139 |
| L2 GLOBAL MODEL | 171 |
| L3 CONDITIONAL | 129 |
| **L4 HIERARCHICAL/INTERACTION** | **0** |
| L5 PORTFOLIO/DECISION | 90 |
| L6 RISK/EXECUTION | 92 |

Inget hierarkiskt interaktionstest har någonsin körts. G-HIER-1 och G-HIER-2 skulle ha
varit det men är `NON_COMPUTED_CLAIM` — hårdkodade dictar utan beräkning. 36 tester kördes
globalt trots att deras ekonomiska hypotes rimligen är betingad.

---

## OMBEDÖMNING AV ALL GAMMAL FORSKNING

Gamla domar är **oförändrade**. Klassificeringen beskriver bara informativitet för det nya
programmet.

| Klass | Antal |
|---|---|
| VALID_FOR_OLD_SYSTEM_ONLY | 372 |
| INSUFFICIENT_PROVENANCE | 240 |
| OLD_UNIVERSE_SENSITIVE | 142 |
| VALID_AND_STILL_INFORMATIVE | 22 |
| DATA_BLOCKED_BUT_NOW_RESOLVED | 13 |
| STILL_DATA_BLOCKED | 10 |
| NON_COMPUTED_CLAIM | 3 |
| INVALID | 1 |

Beroendematrisen mot de tolv förändrade datadimensionerna: **183 av 803 domar är
fortfarande identifierade, 620 är det inte.** Den dominerande mekanismen är
PIT-medlemskapet — i 2014-2019 ändrades varenda panels Top-30 med i snitt 13,29 av 30 namn.

Ny data är inte i sig skäl för omtest. Kravet är en **identifierbar mekanism**, och den
finns dokumenterad per test.

---

## SIGNALFAMILJER: 22

2 VALID_AND_STILL_INFORMATIVE · 7 OLD_UNIVERSE_SENSITIVE · 3 REQUIRES_CLEAN_REPLICATION ·
4 STILL_DATA_BLOCKED · 2 DATA_BLOCKED_BUT_NOW_RESOLVED · 2 NOT_FAIRLY_TESTED ·
1 VALID_FOR_OLD_SYSTEM_ONLY · 1 INSUFFICIENT_PROVENANCE.

Nyupplåsta: **likviditet** (faktisk turnover, spread, antal avslut ersätter pris × volym)
och **size** (201 månaders PIT-segment med 366 övergångar ersätter en odaterad
2026-ögonblicksbild).

---

## VARFÖR STANDARDORDNINGEN ÄR FEL

Den föreslagna ordningen H0 → Size → Sektor → Träd är **inte motiverad av artefakterna**.

L2 — den globala modellarkitekturen — är inte identifierad. Fyra av sex modellförkastanden
vilar på icke-PIT-verifierat medlemskap. Att bygga betingade lager ovanpå en oidentifierad
global arkitektur ärver hela osäkerheten och gör varje conditional-resultat otolkbart.

Om exempelvis **H0 V3 + ExtraTrees** visar sig vara den bäst identifierade globala
arkitekturen, ska conditional research utgå från *den*, inte från H0 ensam.

---

## REKOMMENDERAD FORSKNINGSORDNING

| Fas | Syfte | Stop/Go |
|---|---|---|
| **PHASE_0** | Datagrund — **redan klar** | passerad |
| **PHASE_1** | Vilka globala signaler överlever PIT-korrekt population | GO om någon slår placebobandet i båda fönstren |
| **PHASE_2** | **Avgör global modellarkitektur** — den enskilt viktigaste luckan | GO om någon familj har positiv IC och positiv Δ mot H0 V3 i båda fönstren |
| **PHASE_3** | Komplementaritet: overlay och ensemble | GO om ensemblen slår båda komponenterna i båda fönstren |
| **PHASE_4** | Lås global champion-arkitektur (governanceakt) | hashad och tidsstämplad |
| **PHASE_5** | Betingad heterogenitet — ICB R1–R5, size, G-HET, likviditet | GO endast om **minst två** dimensioner visar reproducerbar heterogenitet |
| **PHASE_6** | Hierarkisk modell / interaktion | GO om interaktionen slår den additiva modellen |
| **PHASE_7** | Portfölj och beslut | |
| **PHASE_8** | Risk och exekvering med faktisk likviditetsdata | |

Ridge och ElasticNet återkörs **inte** — deras förkastande är identifierat.
Hyperparametrar återanvänds ordagrant ur de gamla preregistreringarna; ingen sökning.

---

## PRESTANDAKRITERIER

20 % CAGR är projektets **ekonomiska ambitionsnivå**, aldrig ett acceptanskriterium.
Framtida jämförelser ska minst omfatta CAGR efter kostnader, överavkastning, Sharpe/excess
Sharpe, MaxDD, turnover, kostnadskänslighet, temporal stabilitet, **båda oberoende
fönstren**, preregistrerad bootstrap-osäkerhet, koncentration, delisted-exponering,
robusthet och inkrementellt värde mot benchmark.

En modell med hög historisk CAGR men svag OOS-evidens ska inte föredras framför en robustare.

---

## LEVERANSER

| Artefakt | SHA256 |
|---|---|
| `model_family_inventory.json` | `d778f1f1fd58adc6…` |
| `model_combination_inventory.json` | `2eb2d877b5d6dd8a…` |
| `research_test_inventory.json` | `6032f492cbe48751…` |
| `signal_family_inventory.json` | `94168856341bac62…` |
| `data_dependency_matrix.json` | `4e9c4fe0645adc5f…` |
| `old_verdict_reassessment.json` | `3514510a3490bb01…` |
| `replication_candidates.json` | `ac9698325586cbb6…` |
| `model_family_replication_matrix.json` | `36d5f071cc12981c…` |
| `hierarchical_test_dependency_graph.json` | `15af29487210b63f…` |
| `recommended_research_sequence.json` | `1fb0f8f7825b30da…` |
