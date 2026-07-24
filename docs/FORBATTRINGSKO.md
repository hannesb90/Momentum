# Förbättringskö – förslag från extern granskning

Löpande, avbockningsbar checklista över alla förbättringsförslag som samlats
in från extern AI-granskning av modellkoden. Varje punkt får en status när
den testats – resultatet skrivs alltid till `docs/UTVECKLINGSLOGG.md` (den
ärliga, permanenta loggen); den här filen är bara en KÖ/checklista, inte
facit.

Status: `[ ]` ej testad · `[x]` testad, se loggreferens · `🔄` pågår just nu
· `⛔` ej tillämplig/redundant/motbevisad (motiverat inline)

## Del B – exekvering/produktion/säkerhet (#51, 2026-07-25)

Ny granskningsvinkel: signal→exekvering-timing, backtest-realism, API-
säkerhet, filintegritet. Fyra P0-fynd, se #51 i loggen för fullständig
motivering:

- `[x]` **P0-1: samma-bar signal/exekvering** (features + `_get_price`
  använder samma datums close) → ℹ️ **Dokumenterad, medveten begränsning**
  – target_return delar samma antagande (internt konsistent), men båda
  förutsätter idealiserad market-on-close-exekvering. Kräver target-
  redefinition + omträning för en riktig fix – EGEN PLANERAD SESSION,
  gör INTE detta oplanerat (skulle göra alla #1-#50 icke-jämförbara).
- `[x]` **P0-2: obegränsad forward-fill** → ✅ **Adopterat**
  (`MAX_PRICE_FFILL_WEEKS=8`).
- `[x]` **P0-2/P1-11-interaktion: osäljbar/nollvärderad position vid
  dataglapp** → ✅ **Adopterat** (`_get_price` faller tillbaka på senast
  kända pris för värdering/exekvering, upptäckt och fixad SAMMA session
  som P0-2 – utan detta hade P0-2 introducerat en NY regression).
- `[x]` **P0-3: API utan auth + CORS=\*, aktiv Cloudflare-tunnel** →
  🟡 **Bekräftat avsiktligt** (användarens egen fjärråtkomst) – INGEN
  autentisering/CORS-ändring utan att fråga igen explicit.
- `[ ]` **P0-4: icke-atomiska fil-/statesskrivningar** (`main.py`,
  `portfolio.py`, `api/main.py`) – samma temp-fil+`os.replace()`-mönster
  som redan finns för LGBM-checkpoints, inte utbrett till CSV/JSON-
  skrivningarna. Ej gjort.

**P1 (produktionsdrift, ej prioriterat idag – rör live-appen, inte
"slår modellen index"-spåret):** samtidiga state-skrivningar utan lås
(portfolio.py/api), `/api/health` kollar bara att processen lever (inte
data-/modell-färskhet), global felhanterare maskerar programfel som 503,
pickle-cacher laddas utan integritetsverifiering, datafreshness mäts mot
datasetets EGET senaste datum (inte verklig "nu" – kan dölja ett helt
leverantörsfel), exekveringskostnad använder samma dags ADV (bör laggas
en bar), köp som inte ryms i kassan hoppas över i stället för att skalas
proportionellt, rebalanseringens ordning kan göra resultatet beroende av
radordning (permutationstest saknas), fail-open vid trasig makro-/
regimdata (ska vara fail-safe/konservativ, inte full exponering).

**P2 (robusthet/realism, lägre prioritet):** fraktionella aktier utan
heltalsavrundning, saknar schema-/versionsmigrering för JSON/CSV-state,
API saknar storleks-/resursgränser (rate limits, request-body-limits),
resultatpublicering saknar ett sammanhållet atomiskt snapshot/manifest
(kan blanda gammal+ny pipelineversion), inga rådata-vintages/revisions-
spår (yfinance kan revidera historik i efterhand utan spårbarhet), saknar
full frontend-/API-integrationstestning.

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

## Fas 1 – korrigera tydliga kopplingsproblem — ✅ KLAR (2026-07-25)

1. `[x]` **[SAKNAS, KRITISK] Låt `pred_return` påverka positionsSTORLEKEN**
   (isolerat, oförändrat urval) → **#50, 🟡 Neutralt/marginellt positivt**
   (första icke-negativa resultatet idag – holdout oförändrat, helperiod
   marginellt bättre. För litet utslag för säker slutsats, kandidat för
   vidare validering, ingen SAAB-räddning sker eftersom urvalet är orört).
2. `[x]` **[DELVIS, KRITISK] Ranka inte topp-N enbart på `prob_up`** →
   **#49, ❌ Avvisat** (fjärde bekräftelsen av SAAB-mönstret, se varningsruta).
3. `[x]` **[SAKNAS, HÖG] Validera att regressionen tillför ekonomiskt värde**
   → **Implementerat** (`_fold_diagnostics` beräknar nu Spearman-IC +
   topp-botten-decilspread för `pred_return` vs faktisk `target_return` per
   fold, `models/lgbm_model.py`). Ablation klassificering-utan-regression
   ej gjord (lägre prioritet, kräver egen omträningskörning).
4. `[x]` **[SAKNAS, HÖG] Separera early stopping och kalibrering** →
   **Implementerat**: valideringsfönstret delas kronologiskt (60/40, se
   `CALIBRATION_VAL_FRACTION`), tidigare del → early stopping, senare del
   (närmast testfönstret) → isotonic-kalibrering. Fallback till hela
   fönstret om delningen ger för lite kalibreringsdata.
5. `[x]` **[SAKNAS, HÖG] Spara test_start/test_end per walk-forward-modell**
   → **Implementerat**: `split_ends` sparas parallellt med `split_starts`
   (checkpoint + instans, bakåtkompatibelt). `predict()` varnar nu en gång
   per instans vid extrapolering långt bortom sista kända testfönster.
6. `[x]` **[SAKNAS, HÖG] Separera historisk prediktion från live-prediktion**
   → **Implementerat, lättviktigt**: `predict(strict=True)` kastar
   `ValueError` om något datum ligger utanför tränade testfönster, i
   stället för en full `predict_walk_forward()`/`predict_serving()`-
   uppdelning (mindre riskabel ändring, alla befintliga anrop opåverkade
   med default `strict=False`). Uppföljning: inför `strict=True` i
   backtest-/tune-skript som ALDRIG ska extrapolera – ej gjort ännu.
7. `[x]` **[SAKNAS, HÖG] Gör LightGBM-träningen reproducerbar** → **Redan
   implementerat** (kodgranskningens påstående var föråldrat) –
   `config.LGBM_PARAMS` har redan `seed`/`bagging_seed`/
   `feature_fraction_seed`/`data_random_seed`/`deterministic=True`/
   `force_row_wise=True` med `RANDOM_SEED=42`. Korrigerade en föråldrad
   kodkommentar som hävdade motsatsen.

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
11. `[x]` **[TEST KRÄVS, HÖG] Validera inverse-vol-sizing mot conviction** →
    **#52, ℹ️ Bekräftat rimligt** (3-vägs-jämförelse: `inverse_vol` ger bäst
    holdout-CAGR OCH lägst MaxDD av `inverse_vol`/`pred_return`-tilt/
    `conviction`; conviction köper högre helperiod-CAGR mot sämre risk och
    sämre holdout – ingen ändring motiverad).
12. `[x]` **[TEST KRÄVS, MEDEL/HÖG] Kontrollera dubbla riskjusteringar** →
    **Redan besvarat** (tidigare session, "Etablerade sanningar" #2 i
    loggen): risklagren (#14 inverse-vol, #15 vol-target-overlay, #17
    momentum-kvalitetsgrind) redan ablerade stegvis – "gör kurvan snyggare
    men skapar ingen ny alfa". Ingen ny körning behövs.
13. `[x]` **[DELVIS, HÖG] Validera 13-veckors rebalansering mot signalens
    verkliga halveringstid** → **Redan gjort idag** (#41: både ett
    REBALANCE_WEEKS-svep 4/8/13/17/26v OCH kalender-vs-event-läge, 13v
    robust bäst på båda). Kvarstår ändå otestat: om EN fast hållperiod
    passar ALLA signaler lika bra (staggered portfolios, per-signal-IC
    vecka 1-20) – smalare uppföljningsfråga, lägre prioritet.

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
- `[x]` Featurelista/ordning validerad vid `predict()` → **Implementerat**
  (`feature_cols_` sparas vid träning, jämförs mot aktuell `FEATURE_COLS`,
  kastar tydligt fel vid mismatch). Datatyp-validering ej gjord.
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
