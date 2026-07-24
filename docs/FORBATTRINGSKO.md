# Förbättringskö – förslag från extern granskning

Löpande, avbockningsbar checklista över alla förbättringsförslag som samlats
in från extern AI-granskning av modellkoden. Varje punkt får en status när
den testats – resultatet skrivs alltid till `docs/UTVECKLINGSLOGG.md` (den
ärliga, permanenta loggen); den här filen är bara en KÖ/checklista, inte
facit.

Status: `[ ]` ej testad · `[x]` testad, se loggreferens · `🔄` pågår just nu
· `⛔` ej tillämplig/redundant/motbevisad (motiverat inline)

**2026-07-25: fil omstrukturerad** runt en mycket mer genomarbetad,
kodverifierad 40-punktsgranskning (statuskoder [SAKNAS]/[DELVIS]/
[IMPLEMENTERAT]/[TEST KRÄVS] + prioritet + rekommenderad fasordning). De två
mest kritiska sakpåståendena är verifierade direkt mot koden:

1. **`kelly_position_size()` (`models/ensemble.py:92-138`) tar emot
   `pred_return` som parameter men använder den ALDRIG i beräkningen** –
   `p`/`q`/`b` kommer bara från `prob_up`/`win_loss_ratio`. Koden har redan
   en kommentar som medger detta.
2. **`config.py:266: SIZING_MODE = "inverse_vol"`** – bekräftad
   produktionsdefault. Idag: VILKA N bolag väljs på `prob_up`, HUR MYCKET av
   varje bestäms av `1/volatilitet`. `pred_return` påverkar varken rankning
   eller storlek, bara en binär grind (`pred_return > MIN_EXPECTED_RETURN`).

## ⚠️ Robust bevisad slutsats (tre oberoende SAAB-räddningstest, 2026-07-24)

Native NaN (#46), `liquidity_rank`-cap (#47) och åldersviktning (#48) fick
ALLA SAAB köpt i holdout (11, 10 resp. 27/104 veckor) – och ALLA gjorde
holdout SÄMRE, inte bättre. **"Få modellen att köpa SAAB" är inte längre en
hypotes att jaga.** Punkter nedan som är RIKTADE SAAB-räddningar (t.ex.
volymkatalysator/klippning, se avsnittet längst ner) är nedprioriterade av
det skälet. Dagens 40-punktsgranskning är däremot inte SAAB-fokuserad –
den riktar in sig på arkitekturen (ranking/sizing/kalibrering/attribution)
och ska bedömas på egna meriter.

---

## ⚠️ Nu fyra oberoende bekräftelser av samma mönster (2026-07-25)

Native NaN (#46), `liquidity_rank`-cap (#47), åldersviktning (#48) OCH nu
även **kombinerad rankningsscore (#49)** fick alla SAAB köpt mer i holdout
– och alla gav sämre/oförändrad holdout-prestanda (MaxDD t.o.m. SÄMST av
alla fyra för #49). Fyra helt olika sorters fix (feature/sample-weight/
rankningsformel) ger samma signatur. Nästa punkt (sizing via Kelly) är
en genuint annan mekanism men bör testas med rimlig skepsis, inte
förväntan om att den ensam löser indexgapet.

## Fas 1 – korrigera tydliga kopplingsproblem (rekommenderad startordning)

1. `[x]` **[SAKNAS, KRITISK] Låt `pred_return` påverka positionsSTORLEKEN**
   (isolerat, oförändrat urval) → **#50, 🟡 Neutralt/marginellt positivt**
   (första icke-negativa resultatet idag – holdout oförändrat, helperiod
   marginellt bättre. För litet utslag för säker slutsats, kandidat för
   vidare validering, ingen SAAB-räddning sker eftersom urvalet är orört).
2. `[x]` **[DELVIS, KRITISK] Ranka inte topp-N enbart på `prob_up`** →
   **#49, ❌ Avvisat** (fjärde bekräftelsen av SAAB-mönstret, se varningsruta).
3. `[ ]` **[SAKNAS, HÖG] Validera att regressionen tillför ekonomiskt värde**
   – logga Spearman-IC per fold för `pred_return`, avkastning per decil,
   ablera klassificering-utan-regression mot kombinerad modell.
4. `[ ]` **[SAKNAS, HÖG] Separera early stopping och kalibrering** – samma
   valideringsfönster används idag för båda; inför train→val→calibration→test
   eller cross-fitted calibration.
5. `[ ]` **[SAKNAS, HÖG] Spara test_start/test_end per walk-forward-modell**
   – `_select_model_idx()` verifierar idag bara att ett datum ligger EFTER
   ett split-startdatum, inte att det ligger INOM rätt testfönster.
6. `[ ]` **[SAKNAS, HÖG] Separera historisk prediktion från live-prediktion**
   – `predict_walk_forward()` (strikt OOS-kontroll) vs `predict_serving()`
   (senaste produktionsmodellen), aldrig blandade.
7. `[ ]` **[SAKNAS, HÖG] Gör LightGBM-träningen reproducerbar** – seeds
   (`feature_fraction_seed`, `bagging_seed`, `data_random_seed`,
   `deterministic=True`), logga bibliotoksversioner + manifest (datahash,
   kodhash, parametrar, featureordning).

## Fas 2 – fastställ var indexgapet uppstår

8. `[ ]` **[DELVIS→KRITISK] Full benchmark-relativ attribution** – fyra
   kontrafaktiska portföljer (fullinvesterad likaviktad topp-N / modellens
   vikter / utan overlays / faktisk strategi) för att isolera VAR alfat
   försvinner: universum, sektor, urval, ranking, sizing, exit, kostnader.
9. `[ ]` **[SAKNAS, KRITISK] Kontrafaktisk "varför vann/förlorade vi mot
   index"-analys per kvartal** – för varje stor indexdrivare: valbar? vilken
   rank? vald? vikt? när såld? Detta är den mest direkta vägen till svaret,
   utan att fastna i enstaka exempel (samma lärdom som SAAB/#40 idag).
10. `[ ]` **[SAKNAS, HÖG] Mät universumseffekten separat** – för varje
    period: största indexbidragsgivare, fanns de i råuniversumet, klarade de
    likviditetsfilter, vilken rank/vikt fick de. Delar underprestation i
    "ej valbar" vs "felrankad".
11. `[ ]` **[TEST KRÄVS, HÖG] Validera inverse-vol-sizing mot conviction** –
    jämför `inverse_vol`/`equal_weight`/`conviction`/riskjusterad score på
    Sharpe OCH excess CAGR.
12. `[ ]` **[TEST KRÄVS, MEDEL/HÖG] Kontrollera dubbla riskjusteringar** –
    volskalad momentum-feature + prob_up-urval + inverse-vol-sizing +
    marknadsfilter/sektor-/korrelationsspärrar kan tillsammans dämpa
    uppmarknadsfångst mer än avsett. Stegvis ablation av varje lager.
13. `[ ]` **[DELVIS, HÖG] Validera 13-veckors rebalansering mot signalens
    verkliga halveringstid** – REBALANCE_WEEKS=FORWARD_WEEKS är redan
    bekräftat robust (#41), men om EN fast hållperiod passar ALLA signaler
    är otestat.

## Fas 3 – statistisk robusthet

14. `[ ]` **[DELVIS, KRITISK] Point-in-time-universum med avnoterade bolag**
    – `data_loader.py` dokumenterar redan survivorship bias öppet (yfinance
    ger bara dagens överlevande). Backtesten är forskningsindikativ, inte
    kapitalbevis, tills detta åtgärdas.
15. `[ ]` **[SAKNAS, MEDEL/HÖG] Label-uniqueness/tidsvikter + block-bootstrap**
    – 13v-targets överlappar kraftigt inom segment; nuvarande osäkerhetsmått
    kan vara optimistiska.
16. `[ ]` **[TEST KRÄVS, KRITISK] Undvik upprepad holdout-granskning** – för
    logg över varje experiment som tittat på holdout (många `tune_*.py`-
    skript idag), inför en sista orörd testperiod, rapportera Deflated Sharpe.
17. `[ ]` **[DELVIS, HÖG] Experimentregistry + bredare testsvit** – gemensam
    experimentkonfiguration, samma metrik-/kostnadsdefinition överallt.

## Diagnostik/hygien – lägre prioritet, ingen akut evidens

- `[ ]` IC (Spearman) per fold i `fold_diagnostics_`.
- `[ ]` Precision/Recall/F1 utöver dagens `hit_rate`.
- `[ ]` Kalibrering per sannolikhetsintervall (reliability-bins).
- `[ ]` Winsorisera/ranktransformera extrema regressionsmål.
- `[ ]` Modellera nedsiderisk separat (P(return < -X%) eller negativ kvantil).
- `[ ]` Omkalibrera den FÄRDIGA ensemblen (LGBM+LSTM), inte bara var för sig.
- `[ ]` Validera fasta ensemblevikter (0,6/0,4) via ablation.
- `[ ]` Antal köpsignaler per fold (upptäck degenererat "köp allt/inget").
- `[ ]` Feature distribution drift train/val/test (generaliserar #42).
- `[ ]` `best_iteration` per fold sparad.
- `[ ]` Automatiska sanity checks före träning (NaN/oändligheter/konstanta
  features/dubbletter/tillräckligt många +/- labels).
- `[ ]` Vikta varje handelsdatum lika i träningsförlusten (`1/antal bolag`
  samma datum, motverkar att universumsstorlek dominerar förlusten).
- `[ ]` Maskinläsbar diagnostik (CSV/Parquet i stället för utskrift).
- `[ ]` Rätt ekonomisk målfunktion vid hyperparameterval (separat dev-
  portföljmått, inte bara early-stopping-loss).
- `[ ]` Enhetstest: `predict()` väljer rätt split-modell per datum (övriga
  walk-forward-invarianter redan testade, `tests/test_walk_forward.py`).
- `[ ]` Varning vid prediktion långt efter sista walk-forward-split (kopplar
  till #29 serveringsmodellen).
- `[ ]` Minska checkpoint-filstorlek (spara modeller separat).
- `[ ]` Ensemble-/fold-diversitet + prediktionsosäkerhet via oenighet.
- `[ ]` Permutation importance på testfolds (SHAP redan använt manuellt, #44).
- `[ ]` Featurelista/ordning/datatyp validerad vid modelladdning (utöver
  checkpointens hash).
- `[ ]` Mät effekten av `MIN_HISTORY_WEEKS` (78v) på nynoteringar.
- `[ ]` Verifiera kostnadsmodellen mot verkliga fills, per likviditetssegment.
- `[ ]` Validera `ASYMMETRIC_EXIT` separat innan ev. aktivering (redan av).

## Redan byggt – ingen ny insats behövs (dubbelräkna inte)

- Purged walk-forward + embargo train/val/test.
- Cross-sectional target (XS_TARGET, topp-tertil per datum).
- Prognoshorisont = rebalansering = 13v.
- Optimerbar köptröskel på dev, holdout utanför sökningen.
- Alltid-investerad relativ topp-N-design.
- `prob_raw` som tie-break på isotonic-platåer.
- Benchmarkrapport (alfa/beta).
- Transaktionskostnader: courtage, slippage, spread, marknadsimpact.
- Driftmonitor (rullande AUC/hit rate) – `⛔` men bör KOMPLETTERAS med
  feature-drift, pred_return-IC-drift, kalibreringsdrift, ekonomisk drift.
- Point-in-time merge-logik för flera datakällor.
- Misstänkta prishopp/corporate actions loggas.
- Feature-cache + walk-forward-checkpoint kod-/databundna.
- Survivorship bias dokumenterad öppet i koden.
- Kalibreringsvalidering (Brier/ECE) – `backtest/calibration_check.py`.
- Feature-stabilitet per period – `feature_importance_history_`.
- SHAP över gain-importance – använt manuellt idag (#44).

## Ej tillämpligt på arkitekturen

- Optimera beslutströskeln mot 0.5 – `pred_signal` sätts av topp-N-urval
  (`ensemble.py:417`), ingen fri `prob_up`-tröskel att optimera.

## Bevisat overifierade/lågprioriterade SAAB-räddningsförsök (se varningsruta)

SHAP-kontroll på SAAB:s FAKTISKA smäll-vecka (2022-02-28, +25%/1v, volym 4x)
visade SHAP-bidrag ≈ **0.00000** även då – ingen hävstång att hämta:

- Volymkatalysator för utbrott, klippning av `bb_position`/`ret_1w`,
  kortsiktigt momentum vid volymstöd, dynamisk `MOM_SKIP_WEEKS`-reducering –
  alla targetar features modellen knappt använder vid dessa värden.
- Monotona restriktioner som tvingar en utbrottssignal alltid positiv –
  riskabelt: #42 visade momentum→avkastning-sambandet INTE är stabilt över
  regimer.
- PEAD-override (`report_reaction_abn`) – fick redan stort positivt SHAP-
  bidrag naturligt (NOKIA +0,016), ingen evidens för behov av override.

## Testat idag – se `docs/UTVECKLINGSLOGG.md` för fullständig motivering

- Kort träningsfönster (130v) → **#43, ❌ Avvisat**.
- SHAP-diagnos SAAB → **#44, ℹ️ Diagnos** (`liquidity_rank` dominerande bov).
- IntegratedBacktester/härdighetsbonus → **#45, ❌ Avvisat** (verkar EFTER
  `pred_signal`-grinden).
- Native NaN-hantering → **#46, ❌ Avvisat**.
- `liquidity_rank`-cap → **#47, ❌ Avvisat**.
- Åldersviktade sample weights → **#48, ❌ Avvisat**.
- Kombinerad rankningsscore (`prob_up × max(pred_return,0)`) → **#49, ❌ Avvisat**.
- `pred_return`/vol-sizing, isolerat (oförändrat urval) → **#50, 🟡 Neutralt/marginellt positivt**.

## Större arkitekturfråga – inte ett snabbtest

- `[ ]` Optimera modellen direkt mot portfölj-Sharpe/CAGR/IR i stället för
  rad-för-rad-fel ("learning-to-rank"-nivå).
