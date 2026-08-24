# REP_MODEL_RACE_H0V3 — RESULTAT

Datum: 2026-08-19 · Preregistrering SHA256:
`8c301cf82a0c05f4dc869e757eb1be0320d204bbab934ae400c76e34ccd2555f`

48 modellfits (6 familjer × 2 fönster × 4 refits). 0 parametrar optimerade.
H0 V3 oförändrad. Preregistreringen oförändrad.

---

## A/B/C-ÖVERSIKT

| Modell | Stage A | Stage B | Stage C | 2014–2019 | 2020–2026 | Slutstatus |
|---|---|---|---|---|---|---|
| ExtraTrees | FAIL | NOT_TESTED | NOT_TESTED | **+0,76 pp** | −3,79 pp | PROMISING_BUT_NONREPLICATED |
| CatBoost | FAIL | NOT_TESTED | NOT_TESTED | −8,17 pp | +6,02 pp | PROMISING_BUT_NONREPLICATED |
| LightGBM | FAIL | NOT_TESTED | NOT_TESTED | −3,69 pp | +4,39 pp | PROMISING_BUT_NONREPLICATED |
| XGBoost | FAIL | NOT_TESTED | NOT_TESTED | −7,00 pp | **+11,88 pp** | PROMISING_BUT_NONREPLICATED |
| RandomForest | FAIL | NOT_TESTED | NOT_TESTED | −1,87 pp | +3,02 pp | PROMISING_BUT_NONREPLICATED |
| HistGradientBoosting | FAIL | NOT_TESTED | NOT_TESTED | −8,41 pp | +6,84 pp | PROMISING_BUT_NONREPLICATED |

**Samtliga sex byter tecken mellan fönstren. Ingen enda är konsistent.**

---

## BASLINJEVALET — EN TOLKNING JAG MÅSTE REDOVISA

Preregistreringen föreskriver *"Top-30, likavikt"* för modellportföljerna. H0 V3:s officiella
siffror kommer från dess frysta pipeline med **invers-vol-vikt, SMA200-grind,
bekräftelsemultiplikator och vikttak**. Att jämföra en likaviktad modellportfölj mot en
invers-vol-viktad H0 hade mätt *viktning*, inte *rankning* — och detta är ett
modellarkitekturrace.

Gate-baslinjen är därför **H0_V3_EW**: H0 V3:s exakta rankning körd genom samma likaviktade
harness som modellerna. Samma val gjordes i det gamla H1419-racet.

| | 2014–2019 | 2020–2026 |
|---|---|---|
| H0 V3 officiell (fryst pipeline) | **26,61 %** | **12,99 %** |
| H0_V3_EW (gate-baslinje) | 28,48 % | **1,57 %** |

Skillnaden i fönster 2 är **11,4 pp**. Invers-vol-viktningen och SMA-grinden bär alltså
merparten av H0 V3:s fönster-2-resultat — inte rankningen. Det är ett fynd i sig, och det ändrar
ingen dom.

---

## STAGE A — STANDALONE, ALLA SEX

Utvärdering: 49 paneler (2016-04-20 →) i fönster 1, 43 paneler (2023-04-20 →) i fönster 2.
Walk-forward med årlig omträning, purge 8 v + embargo 4 v.

### Fönster 1, 2014–2019 · H0_V3_EW = 28,48 %, MaxDD −20,08 %, Sharpe 1,643, turnover 6,83

| Modell | CAGR | Excess | KI | t | MaxDD | Sharpe | Turnover | Mean IC | **Top-30 IC** |
|---|---|---|---|---|---|---|---|---|---|
| **ExtraTrees** | **29,24 %** | +0,76 pp | [−3,8, +2,9] | +0,39 | −21,7 % | 1,66 | 7,8 | 0,0846 | **+0,0241** |
| RandomForest | 26,61 % | −1,87 pp | [−5,4, +0,9] | −0,65 | −26,1 % | 1,42 | 9,1 | 0,0632 | −0,0401 |
| LightGBM | 24,79 % | −3,69 pp | [−8,8, +0,2] | −0,83 | −22,7 % | 1,34 | 12,5 | 0,0604 | −0,0108 |
| XGBoost | 21,48 % | −7,00 pp | [−11,3, −3,8] | −1,50 | −22,1 % | 1,17 | 12,2 | 0,0541 | −0,0524 |
| CatBoost | 20,31 % | −8,17 pp | [−13,4, −2,9] | −1,90 | −21,4 % | 1,12 | 10,0 | 0,0682 | −0,0320 |
| HistGradBoost | 20,07 % | −8,41 pp | [−12,1, −3,2] | −2,15 | −25,3 % | 1,03 | 12,4 | 0,0621 | −0,0965 |

### Fönster 2, 2020–2026 · H0_V3_EW = 1,57 %, MaxDD −14,40 %, Sharpe −0,055, turnover 7,10

| Modell | CAGR | Excess | KI | t | MaxDD | Sharpe | Turnover | Mean IC | **Top-30 IC** |
|---|---|---|---|---|---|---|---|---|---|
| **XGBoost** | **13,45 %** | +11,88 pp | [−4,1, +38,0] | +1,33 | −22,7 % | 0,50 | 13,3 | 0,0557 | −0,0688 |
| HistGradBoost | 8,41 % | +6,84 pp | [−12,5, +28,2] | +0,99 | −23,4 % | 0,26 | 12,1 | 0,0521 | −0,1059 |
| CatBoost | 7,59 % | +6,02 pp | [−8,7, +20,7] | +0,92 | −21,3 % | 0,22 | 13,8 | 0,0559 | −0,0492 |
| LightGBM | 5,96 % | +4,39 pp | [−10,2, +17,4] | +0,64 | −25,3 % | 0,14 | 14,1 | 0,0536 | −0,0852 |
| RandomForest | 4,59 % | +3,02 pp | [−8,2, +15,9] | +0,49 | −22,4 % | 0,09 | 12,6 | 0,0491 | −0,0730 |
| ExtraTrees | −2,22 % | −3,79 pp | [−15,7, +0,4] | −0,35 | −25,4 % | −0,22 | 13,0 | 0,0415 | −0,0619 |

### De åtta kraven — mekaniskt tillämpade

| Krav | Uppfyllt av |
|---|---|
| 1. Excess > 0 i båda fönstren | **0 av 6** |
| 2. Över placebobandet 2,4 pp i minst ett, positiv i båda | **0 av 6** |
| 3. Mean IC > 0 i båda | 6 av 6 |
| 4. **Top-30 IC > 0 i båda** | **0 av 6** |
| 5. Ej koncentrationsfragil | 6 av 6 |
| 6. MaxDD inte >5 pp sämre | 3 av 6 |
| 7. Turnover ≤ 2× | 6 av 6 |
| 8. Positiv excess kvar vid 40 bp | **0 av 6** |

**STAGE A PASS: 0. FAIL: 6.**

---

## STAGE B — INTE KÖRD, OCH VARFÖR DET INTE ÄR SAMMA SAK SOM ETT NEJ

Informationsgrinden är **oberoende av Stage A**: mean IC > 0 **och** top-30 IC > 0 i båda fönstren.
En modell som faller Stage A hade gått vidare ändå om grinden passerats.

**Ingen passerade.** Mean IC är positiv överallt (0,041–0,085), men top-30 IC är negativ i minst
ett fönster för samtliga sex. Endast ExtraTrees har positiv top-30 IC någonstans — **+0,0241 i
fönster 1** — och den vänder till **−0,0619 i fönster 2**.

Samtliga sex: **NOT_TESTED_BY_SEQUENTIAL_GATE.** Ingen får märkas
`NO_INCREMENTAL_INFORMATION` — frågan är otestad, inte besvarad.

Stage C: **0 kvalificerade, 0 körda.** ExtraTrees fick ingen särbehandling; de historiska
+9,97 pp användes aldrig som tröskel, parameterval eller riktningsförväntan.

---

## DET AVGÖRANDE MÅTTET

Modellerna rangordnar **hela tvärsnittet** bättre än slumpen — mean IC 0,04–0,08 i båda
fönstren, för alla sex. Men de fallerar **inuti den investerbara toppen**: top-30 IC är negativ
i 11 av 12 modell-fönster-kombinationer.

Det är exakt samma mönster som H1419-racet och spår D visade. Skillnaden är att det nu är
bekräftat på PIT-korrekt grund, mot rätt baslinje, i två oberoende fönster. Den gamla domen var
inte identifierad; den nya är det.

---

## MODELLDIVERSITET — MEKANISMEN BAKOM DEN GAMLA EVIDENSEN

| Fönster | Modell | Rank corr mot H0 | **Top-30 överlapp** | Disagreement |
|---|---|---|---|---|
| 2014–2019 | ExtraTrees | **0,951** | **0,892** | 0,108 |
| 2014–2019 | CatBoost | 0,788 | 0,737 | 0,263 |
| 2014–2019 | HistGradBoost | 0,583 | 0,475 | 0,525 |
| 2020–2026 | ExtraTrees | 0,351 | **0,000** | **1,000** |
| 2020–2026 | HistGradBoost | 0,416 | 0,275 | 0,725 |
| 2020–2026 | XGBoost | 0,421 | 0,264 | 0,736 |

Detta förklarar den historiska ExtraTrees-evidensen. I fönster 1 väljer ExtraTrees **89 % samma
namn som H0** — den är i praktiken en variant av H0, och dess +0,76 pp är marginalen från de
återstående 11 %. I fönster 2 är överlappet **exakt noll** — modellen väljer en helt disjunkt
portfölj — och den är den enda som underpresterar.

Komplementaritet som bara uppstår när modellen nästan sammanfaller med basmodellen är inte
komplementaritet.

ML×ML-rankkorrelation: median 0,76 (fönster 1) och 0,79 (fönster 2). Familjerna är till stor del
versioner av samma signal.

---

## MULTIPLICITET

Sekventiell stege A→B→C som primär kontroll, tvåfönsterkravet som gate.

Holm-Bonferroni över sex familjer: **inget justerat p-värde understiger 0,05 i något fönster.**
Lägsta är 0,8076 (HistGradientBoosting, fönster 1). Rått, osäkerhet och multiplicitetsjusterad
evidens pekar åt samma håll: ingen familj kan utses till vinnare.

---

## RESERVATIONER

**XGBoost.** Högst CAGR i fönster 2 (13,45 %) och högst excess (+11,88 pp), men faller Stage A på
fönster 1 (−7,00 pp) och på top-30 IC i båda. Kapacitetskonfounden (300 träd mot LightGBMs 80) är
därför **inte material för domen**. Ytterligare: XGBoost kördes från
`momentum_prod_work/.research-libs` (3.4.0) eftersom paketet inte finns i den reproducerbara
venv:en — samma skäl som gjorde att den exkluderades ur H1419-racet. **Ingen installation gjordes.**

**VBG-B-kontamineringen.** Samtliga fyra berörda paneler (2020-03-26, 2020-04-23, 2020-05-21,
2020-06-18) ligger **före** fönster 2:s första utvärderingspanel 2023-04-20. **Noll kontaminerade
paneler i utvärderingsfönstret.** De ingår i träningsmålen men utgör 4 av 43 träningspaneler för
ett namn av ~330. **Inte material för domen.**

**F1 kördes inte** — preregistreringen: *"F1 körs ENDAST om minst en familj passerar STAGE A eller
STAGE B på F0."* Noll passerade. F1 stryks enligt kontraktet.

---

## EKONOMI

| Arkitektur | 2014–2019 | 2020–2026 | ≥ 20 % i båda |
|---|---|---|---|
| H0 V3 officiell | 26,61 % | 12,99 % | **NEJ** |
| H0_V3_EW | 28,48 % | 1,57 % | NEJ |
| Bästa standalone | ExtraTrees 29,24 % | XGBoost 13,45 % | NEJ |
| Bästa overlay | ej testad | ej testad | — |
| Bästa ensemble | ej testad | ej testad | — |

Ingen arkitektur når 20 % robust över båda fönstren. 20 % är ambitionsnivå, inte acceptansgräns,
och har inte påverkat någon dom.

---

## ARKITEKTURDOM

**H0_V3_REMAINS_GLOBAL_CHAMPION**

Preregistreringens champion-gate: *"default: A. Om ingen familj passerar något steg är utfallet A,
inte E — H0 V3 står kvar som identifierad global champion och racet har då gett ett positivt
besked om H0 V3."*

E används när någon familj passerar delvis men ingen uppfyller robusthetskraven. Här passerade
ingen familj något steg — inte ens informationsgrinden.

---

## REPRODUCERBARHET

Två oberoende fullständiga körningar av hela Stage A: **0 avvikelser**. Ingen icke-determinism.
Samtliga familjer seedade (20260819), enkeltrådiga. Fröet byttes inte.

Prediktioner per modell och fönster sparade i `results/predictions/` för oberoende reproduktion.

---

## ARTEFAKTER

`research_k/rep_model_race_h0v3/results/` — `stage_a_results.json` `cc94dcd2a59b5f51…` ·
`stage_b_results.json` · `stage_c_results.json` · `model_diagnostics.json` ·
`multiplicity_results.json` · `architecture_verdict.json` `0e0ba8f37de7c4c8…` ·
`reproducibility_manifest.json` · `execution_manifest.json` · `predictions/` (12 filer)
Kod: `tools/rep_model_race_h0v3_kor.py`
