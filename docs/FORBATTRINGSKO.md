# Förbättringskö – förslag från extern granskning (2026-07-24)

Löpande, avbockningsbar checklista över alla förbättringsförslag som samlats
in (mestadels från en extern AI-granskning av modellkoden) sedan #44:s
SAAB/`liquidity_rank`-fynd. Varje punkt får en status när den testats –
resultatet skrivs alltid till `docs/UTVECKLINGSLOGG.md` (den ärliga,
permanenta loggen); den här filen är bara en KÖ/checklista, inte facit.

Status-nycklar: `[ ]` ej testad · `[x]` testad, se loggreferens · `🔄` pågår
just nu · `⛔` ej tillämplig/redundant (motiverat nedan)

---

## Pågår just nu

- 🔄 **Åldersviktade sample weights** (exponentiell decay, half-life 104v/2 år)
  – mjukare variant av #43 (som avvisade en hård 130v-fönsteravskärning).
  Testskript: `age_weight_test.py`. Väntar på resultat.

## Kö – näst i tur (prioritetsordning)

1. `[ ]` **Kombinerad rankningsscore** `score = prob_up × max(pred_return, 0)`
   för topp-N-urvalet i `ensemble.py` – i stället för att klassificering och
   regression används separat. Högst prioriterat: matchar #45:s fynd att
   urvalet EFTER prediktionen är flaskhalsen, inte feature engineering.
2. `[ ]` **Regressionsobjective: Huber eller Quantile** i stället för RMSE –
   billigt, välspecificerat, kompletterar punkt 1 (RMSE drar extrema
   uppgångar mot medelvärdet).
3. `[ ]` **Avkastningsviktade sample weights** (magnitud, inte ålder) – vikta
   upp observationer med stor FAKTISK framtida avkastning. Separat hypotes
   från det pågående ålders-testet, kan kombineras senare.
4. `[ ]` **Diagnostik (ingen omträning): dämpar tvärsnittsnormalisering
   extremvinnare?** – jämför råa `roc_13w`-extremvärden mot normaliserade
   `mom_12_1`/`resid_mom`-percentiler för kända extremvinnare (SAAB, NOKIA).
   Billig förstudie innan ev. omträning.
5. `[ ]` **Tak på volatilitetsnämnaren i `resid_mom`** – viss SHAP-evidens
   (konsekvent negativt bidrag på SAAB/NOKIA, växande över tid), men mindre
   magnitud än `liquidity_rank`. Lägre prioritet än 1–4.

## Testade idag – se `docs/UTVECKLINGSLOGG.md` för fullständig motivering

- `[x]` Kort träningsfönster (130v i stället för 260v) → **#43, ❌ Avvisat**
  (sämre på alla mått).
- `[x]` SHAP-diagnos: varför litar modellen inte på SAAB? → **#44, ℹ️ Diagnos**
  (`liquidity_rank` dominerande bov).
- `[x]` IntegratedBacktester / härdighets-bonus (Stage 1) mot dagens baslinje
  → **#45, ❌ Avvisat** (verkar EFTER `pred_signal`-grinden, kan aldrig
  rädda ett uteslutet bolag; empiriskt negativt mot dagens baslinje).
- `[x]` Native NaN-hantering i stället för `fillna(0)` → **#46, ❌ Avvisat**
  (fick SAAB köpt 11/104v men holdout blev sämre i aggregat).
- `[x]` Tak/winsorisering på `liquidity_rank` (CAP=0,90) → **#47, ❌ Avvisat**
  (samma mönster som #46 – SAAB köpt 10/104v, holdout ändå sämre. **Viktig
  metaobservation: två oberoende metoder fick båda SAAB köpt och båda
  gjorde holdout sämre** – SAAB generaliserar inte till en systematisk fix).

## Bevisat overifierade/lågt prioriterade för DETTA problem

SHAP-kontroll på SAAB:s FAKTISKA smäll-vecka (2022-02-28, +25%/1v, volym 4x)
visade att dessa features hade SHAP-bidrag ≈ **0.00000** även då – ingen
hävstång att hämta oavsett hur de justeras, om inte modellens lärda
featureviktning ändras i grunden:

- `⛔` Volymkatalysator för utbrott (pris + volym>3x) – SHAP=0 vid SAAB:s
  faktiska utbrott.
- `⛔` Klippning av `bb_position`/`ret_1w` ("anti-whipsaw") – samma skäl.
- `⛔` Kortsiktigt momentum aktiverat vid volymstöd (OBV) – samma skäl.
- `⛔` Dynamisk reducering av `MOM_SKIP_WEEKS` vid volymdriven nyhetschock –
  samma familj, samma brist på hävstång.
- `⛔` Monotona restriktioner som tvingar en utbrottssignal alltid positiv –
  riskabelt utöver att vara overifierat: #42 visade att momentum→avkastning-
  sambandet INTE är stabilt över regimer, ett tvingat samband kan förvärra.
- `⛔` PEAD-override (låt stark `report_reaction_abn` överstyra svag
  historisk tillväxt) – featuren fick redan ett stort positivt SHAP-bidrag
  naturligt (NOKIA +0,016) utan någon override. Ingen evidens för behov.

## Diagnostik/hygien – ej akut, ingen specifik evidens pekar dit idag

- `[ ]` IC (Spearman-rankkorrelation) per fold, sparad i `fold_diagnostics_`.
- `[ ]` Precision/Recall/F1 utöver dagens `hit_rate`.
- `[ ]` Kalibrering per sannolikhetsintervall (reliability-bins per fold).
- `[ ]` Winsorisera extrema regressionsmål.
- `[ ]` Antal köpsignaler per fold (upptäck degenererat "köp allt/inget").
- `[ ]` Feature distribution drift train/val/test (generaliserar #42:s fynd
  till alla features, inte bara `mom_12_1`).
- `[ ]` `best_iteration` per fold sparad.
- `[ ]` Automatiska sanity checks före träning (NaN i labels, oändligheter,
  konstanta features, dubbletter, tillräckligt många +/- labels).
- `[ ]` Maskinläsbar diagnostik (CSV/Parquet i stället för bara utskrift).
- `[ ]` Enhetstest: `predict()` väljer verkligen rätt split-modell per datum
  (resten av walk-forward-invarianterna är redan testade,
  `tests/test_walk_forward.py`).
- `[ ]` Reproducerbarhet: seeds (`feature_fraction_seed`, `bagging_seed`,
  `data_random_seed`, `deterministic=True`).
- `[ ]` Varning när modellen predikterar långt efter sista walk-forward-split
  (kopplar till #29 serveringsmodellen).
- `[ ]` Minska checkpoint-filstorlek (spara modeller separat).
- `[ ]` Ensemble-diversitet (korrelation mellan walk-forward-foldens
  modeller).
- `[ ]` Permutation importance på testfolds (SHAP redan använt manuellt idag,
  #44).
- `[ ]` Prediktionsosäkerhet via fold-modellernas inbördes oenighet.

## Redan byggt – ingen ny insats behövs

- `⛔` Kalibreringsvalidering (Brier score, ECE) – redan `backtest/
  calibration_check.py` (Stage 0).
- `⛔` Feature-stabilitet/fold-metrics – `feature_importance_history_` är
  redan en DataFrame med per-period-uppdelning.
- `⛔` SHAP över gain-importance – redan använt manuellt idag (#44),
  identifierade `liquidity_rank`.

## Ej tillämpligt på den här arkitekturen

- `⛔` Optimera beslutströskeln mot 0.5 – `pred_signal` sätts av topp-N-
  urval (`ensemble.py:417`), inte av en fri `prob_up`-tröskel. Ingenting
  att optimera här.

## Större arkitekturfråga – inte ett snabbtest, egen framtida session

- `[ ]` Optimera modellen direkt mot portfölj-Sharpe/CAGR/Information Ratio
  i stället för rad-för-rad klassificerings-/regressionsfel
  ("learning-to-rank"-nivå, inte en parameterjustering).
- `[ ]` Granska hela kedjan modell → ensemble → ranking → portföljkonstruktion
  systematiskt (delvis redan gjort via #45, men en fullständig, strukturerad
  genomgång är större än dagens enskilda test).
