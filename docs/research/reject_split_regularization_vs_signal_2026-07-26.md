# Underkända (1-träds) walk-forward-splits: regularisering eller saknad signal?

Date: 2026-07-26

## Bakgrund

Rank-gap-granskningen (pipeline_health.json) visade att flera olika bolag
fick bit-identisk rå LGBM-poäng. Spårat till: den split som styr dagens
signaler (`_select_model_idx`) hade `num_trees()==best_iteration()==
current_iteration()==1`. Fråga: beror det på att `reg_lambda`/`reg_alpha`/
`min_child_samples` är för hårt satta, eller på att momentum-signalen
genuint saknas i vissa 3-månadersfönster?

**Datakälla-caveat:** main.py raderar sin feature-cache efter varje
orkestrerad körning (numera undantaget vid underkänd split, se samma
sessions kod-PR). Den EXAKTA data som orsakade produktionens degenererade
splits gick inte att återskapa - analysen nedan kör om hela walk-forward-
kedjan mot den nyaste TILLGÄNGLIGA feature-cachen (`results/
_features_cache_4da9fd9c993cff11.pkl`, byggd 2026-07-26 05:37), inte en
bit-identisk reproduktion. Kvalitativt samma mönster som produktionens
~10/31 degenererade splits återfanns (3/31 här - färre, men samma
karaktär), så slutsatserna nedan bör generalisera även om exakta tal
skiljer sig från en given natts körning.

Skript: `tune_reject_split_diagnosis.py compare` / `grid`.

## Fas 1: jämförelse, degenererade vs friska splits (BASELINE-parametrar)

| Mått | Friska (n=28) | Degenererade (n=3) |
|---|---:|---:|
| Tränings-rader (median) | 31 057 | 37 079 |
| Positiv targetandel | 0,334 | 0,334 |
| Targetvarians/datum (median) | 0,0141 | 0,0234 |
| NaN-andel (medel över features) | 0,071 | 0,061 |
| Feature-drift train→val (medel \|z\|) | 0,092 | **0,201** |
| Bästa validerings-AUC (median) | 0,594 | **0,488** |
| Antal boosting-rundor FÖRSÖKTA | 63 | 51–59 |
| Unika score-värden (validering) | 1599 | 53 |

**Viktig korrigering av tidigare hypotes:** `eval_rounds_attempted` (51-59,
inte 1) bevisar att degenereringen är VANLIG tålamods-baserad early
stopping (runda 1 var bäst, ~50 rundor därefter förbättrade aldrig) - INTE
LightGBM:s interna "no further splits with positive gain"-terminering som
en tidigare, ej eval_history-verifierad hypotes antog. Boostingen försöker
faktiskt, den lyckas bara aldrig hitta något bättre än den första trädet.

De degenererade splittarnas bästa AUC (median 0,488, dvs vid eller under
slumpnivå 0,50) är den starkaste enskilda signalen: modellen hittar helt
enkelt ingen lärbar kant i de perioderna, oavsett hur många rundor den
provar. De visar dessutom dubbelt så hög feature-drift mellan tränings-
och valideringsfönstret som de friska - konsekvent med regimskiften där
träningsperiodens mönster inte överför sig till valideringsperioden.

## Fas 2: parametergrid (baseline / variant A / variant B) på samma splits

Kört på de 3 splits som var degenererade under BASELINE + 3 friska
kontrollsplits, TEST-fönstrets (aldrig sett av träning/early stopping)
AUC/rank-IC/score-upplösning:

| Variant | reg_lambda | reg_alpha | min_child_samples |
|---|---:|---:|---:|
| baseline | 1.0 | 0.1 | 50 |
| variant_A | 0.5 | 0.05 | 30 |
| variant_B | 0.0 | 0.0 | 20 |

**Degenererade splits (median över de 3):**

| Variant | num_trees | test_AUC | test_rank_IC | unika score |
|---|---:|---:|---:|---:|
| baseline | 1 | 0,520 | -0,037 | 39 |
| variant_A | 1 | 0,530 | -0,012 | 41 |
| variant_B | 1 | 0,536 | -0,002 | 40 |

**Friska kontrollsplits (median över de 3):**

| Variant | num_trees | test_AUC | test_rank_IC | unika score |
|---|---:|---:|---:|---:|
| baseline | 22 | 0,580 | 0,036 | 1252 |
| variant_A | 27 | 0,568 | 0,026 | 1318 |
| variant_B | 20 | 0,583 | 0,044 | 1209 |

## Slutsats

**`num_trees` stannar på exakt 1 för ALLA tre degenererade splits i ALLA
tre parametervarianter** - även vid variant B (`reg_lambda=0`,
`reg_alpha=0`, `min_child_samples=20`, den mest tillåtande uppsättningen)
växer inte ett enda extra träd. Test-AUC rör sig marginellt uppåt
(0,520→0,536) men förblir nära slumpnivå, långt under de friska splittarnas
~0,58. De friska kontrollsplittarna förbättras INTE heller konsekvent av
mindre regularisering (AUC pendlar 0,568-0,583 utan tydlig riktning) - dvs
regulariseringsförändringen är inte ett generellt "gratis lyft" för någon
grupp.

**Detta talar starkt för: signalen saknas genuint i de perioderna, inte
att regulariseringen är för hård.** Om regularisering vore boven skulle
variant B (nästan ingen regularisering alls) rimligen ha låtit trädet
växa förbi runda 1 - det gjorde den inte, i något av de tre fallen.

**Ett undantag värt att notera:** split 27 hade redan vid BASELINE en
faktisk användbar test-AUC (0,60) och rank-IC (0,15) TROTS `num_trees==1`
- ett enda träd råkade fånga en tillräckligt stark enskild split för att
ge verkligt värde. `num_trees<=1` är alltså inte ett ofelbart tecken på
"värdelös modell" i varje enskilt fall, bara på gruppnivå ett starkt
mönster - split 27 är en påminnelse om att den nya `active`-kritiska
flaggan (pipeline_diagnostics.py) fortfarande är rätt DEFAULT-agerande
(en enda tränings-runda ger sällan tillförlitlig generalisering), men att
en mer finkornig framtida signal (t.ex. testa AUC/rank-IC direkt, inte
bara trädantal) skulle kunna undvika att blockera de sällsynta fallen där
en enda-träds-modell ändå håller.

## Rekommendation

- Ändra INTE `config.LGBM_PARAMS`s regularisering globalt - grid-resultatet
  visar att det inte löser problemet och inte hjälper de friska splittarna
  konsekvent heller.
- Behåll den redan byggda kritiska/fallback-mekanismen
  (`pipeline_diagnostics.model_tree_health_report`, main.py STEG 3) som
  skydd när den AKTIVA splitten degenererar - det är rätt säkerhetsnät
  givet att grundorsaken är en genuint dålig period, inte ett
  konfigurationsfel som går att "fixa bort".
- Eventuell framtida uppföljning (INTE gjord här): komplettera
  `num_trees<=1`-kriteriet med ett direkt AUC/rank-IC-tröskelvärde, så en
  sällsynt men faktiskt användbar enda-träds-split (som #27) inte
  onödigtvis blockeras av den framtida fallback-logiken.

Rådata: `results/reject_split_comparison.csv`, `results/
reject_split_comparison_summary.csv`, `results/reject_split_grid.csv`
(genererade av `tune_reject_split_diagnosis.py`, inte incheckade -
resultatmapp gitignorad, se README).
