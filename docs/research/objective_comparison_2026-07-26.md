# Objective-jämförelse: klassificering vs regression vs LambdaRank

Date: 2026-07-26 (avslutad 2026-07-27)

Samma features, samma 31 walk-forward-splits, tre LightGBM-objectives.
Skript: `tune_objective_comparison.py`. Klassificerings- och
regressionsmodellerna återanvänder de REDAN tränade `cls_models`/
`reg_models` från samma körning som `abstention_gate`/`breadth_gate`-
forskningen (`fit_walk_forward` tränar alltid båda); LambdaRank tränades
nytt per split (query-grupp = ett veckodatum, relevans = ordinal decil
0-9 av `target_return` inom det datumet, early-stoppad mot NDCG@10 på
valideringsfönstret - samma tålamodsbudget som de andra två).

## Rangordningsmått (innan portföljfilter, median över 31 splits)

| Objective | Rank IC | Topp-decil-edge | NDCG@10 | Unika score-värden | Största platå |
|---|---:|---:|---:|---:|---:|
| binary_classification (baseline) | 0,038 | 0,0024 | 0,245 | **11** | **48,8%** |
| regression | **0,066** | 0,0220 | 0,300 | 46 | 16,9% |
| lambdarank | -0,0001 | **0,0217** | **0,309** | **1009** | **1,8%** |

Score-upplösningen kvantifierar direkt det tidigare fyndet
(isotonic-platån): baseline har en median på bara **11 unika
kalibrerade sannolikhetsvärden** över ett helt testfönster, med nästan
halva observationerna (48,8%) i den enskilt största platån. LambdaRank
löser det problemet helt (1009 unika värden, 1,8% platå) och regression
ligger mitt emellan.

Både regression och LambdaRank slår baseline tydligt på topp-decil-edge
(~9x högre) och NDCG@10. LambdaRanks rena rank-IC är dock ~0 (ingen
linjär/monoton korrelation över HELA rangordningen) - den optimerar
uttryckligen bara ordningen i TOPPEN (NDCG@10, topp-decil), inte hela
listan, vilket är precis vad den är designad att göra.

## Rankstabilitet (andel av topp-10 utbytt per rebalansering)

| Objective | Turnover |
|---|---:|
| binary_classification | 81,3% |
| lambdarank | 75,0% |
| regression | 72,9% |

Baseline har MEST churn - regression är stabilast.

## Fullständigt backtest (topp-10 likaviktat, för att isolera
## rangordningskvaliteten från sizing-skillnader)

| Objective | Dev CAGR | Dev Sharpe | Dev MaxDD | Holdout CAGR | Holdout Sharpe |
|---|---:|---:|---:|---:|---:|
| binary_classification | +7,6% | **1,17** | **-7,5%** | **+2,5%** | **+0,43** |
| regression | **+12,3%** | 0,92 | -13,8% | -1,8% | -0,20 |
| lambdarank | +8,0% | 1,13 | -9,1% | -1,5% | -0,17 |

## Den centrala spänningen

**De objectives som ser bättre ut på RÅ rangordningskvalitet (regression,
LambdaRank - bättre IC/edge/NDCG/upplösning, mindre churn) presterar
SÄMRE i det faktiska, aldrig sedda holdout-backtestet.** Baseline
(klassificering), trots klart sämst råa rangordningsmått (11 unika
score-värden!), är den ENDA av de tre som är positiv i holdout (+2,5%
CAGR, +0,43 Sharpe) - regression och LambdaRank förlorar båda pengar där
(-1,8% resp. -1,5% CAGR).

Detta är exakt den typen av observation som ligger bakom punkt 3 i
uppföljningslistan ("valideringsmåttet optimerar inte portföljmålet") -
men resultatet visar den OMVÄNDA risken: att förbättra de mått som
LIKNAR portföljmålet mer (rank-IC, NDCG, topp-decil-edge) garanterar inte
bättre verklig, framåtblicksfri prestanda. Möjliga förklaringar (ingen
bekräftad ännu):

- Regression/LambdaRank kan överanpassa mer till dev-periodens
  brus - deras bättre in-sample-rangordning må inte generalisera.
  Isotonic-kalibreringen i klassificeringsvägen må fungera som en
  ofrivillig regulariserare mot just detta, trots att den (per
  rank-gap-granskningen tidigare i sessionen) samtidigt döljer verklig
  finrangordning.
- Ett enda holdout-fönster (104 veckor) är ett mycket tunt underlag -
  kan vara periodspecifik tur för klassificeringen snarare än en
  generell sanning.
- Topp-10-likaviktad sizing (vald för att isolera rangordningskvalitet)
  må missgynna regression/LambdaRanks scoreprofil jämfört med hur de
  skulle presterat med en skräddarsydd sizing-regel.

## Slutsats och nästa steg

Ingen av de tre objectiven är ett uppenbart, färdigt svar. LambdaRank/
regression löser det kvantifierade score-upplösningsproblemet
övertygande men det översätts INTE automatiskt till bättre verklig
prestanda i den här första, enkla backtest-uppställningen - samma typ av
lärdom som `breadth_gate`-forskningen gav (en stark korrelation på ett
mått garanterar inte en bättre regel i praktiken).

Användarens prioriterade uppföljningslista (efter LambdaRank, redan
testad här):
2. Samma classifier med lika total sample-vikt per datum
3. Kontrolltest med reducerat label-överlapp
4. Behåll NaN i stället för `fillna(0)`
5. Gör sektor kategorisk i stället för ordinal
6. Modellval styrt av Rank IC/NDCG i stället för enbart AUC

Ingen kodändring i produktionspipelinen ännu - forskningen fortsätter.

Rådata: `results/objective_comparison_per_split.csv`,
`_summary.csv`, `_stability.csv`, `_backtest.csv` (genererade av
`tune_objective_comparison.py`, ej incheckade).
