# Ta bort tidig_entry-featuregruppen - reproducerar INTE den tidigare vinsten

Date: 2026-07-27

Punkt 2 i användarens omprioriterade uppföljningslista. `config.py`
dokumenterar sedan tidigare (`tune_ablation.py`, LOGO-metodik) att
"tidig_entry"-gruppen (`donchian_pos`, `breakout_nw`, `roc_accel_4w`,
`pullback`) var AKTIVT SKADLIG på holdouten (-5,1% → +1,5% vid borttag),
men `config.DROP_FEATURES` är fortfarande tom - fyndet blev aldrig
adopterat. Testat här med samma full-pipeline-metodik som resten av
sessionens forskning (topp-10-likaviktat backtest, CAGR/Sharpe/MaxDD
dev+holdout) - INTE identisk metodik med den ursprungliga LOGO-ablationen
(som mätte capture-spread på en LGBM-only-modell). Skript:
`tune_drop_tidig_entry.py`. 52→48 features.

## Rangordningsmått (median över 31 splits, innan portföljfilter)

| Mått | Baseline (52 features) | Utan tidig_entry (48 features) |
|---|---:|---:|
| Rank IC | 0,038 | 0,020 (sämre) |
| Topp-decil-edge | 0,0024 | 0,0040 (något bättre) |
| Unika score-värden | 11 | 11 (oförändrat) |
| Rankstabilitet (turnover) | 81,3% | 85,5% (sämre) |

## Fullständigt backtest

| Variant | Dev CAGR | Dev Sharpe | Dev MaxDD | Holdout CAGR | Holdout Sharpe |
|---|---:|---:|---:|---:|---:|
| Baseline | +7,6% | 1,17 | -7,5% | +2,5% | 0,43 |
| Utan tidig_entry | **+5,7%** | **0,85** | **-11,9%** | +3,0% | 0,49 |

**Reproducerar INTE den tidigare dokumenterade holdout-vinsten.**
Dev-perioden försämras tydligt (CAGR 7,6%→5,7%, Sharpe 1,17→0,85, MaxDD
nästan fördubblad till -11,9%), medan holdout bara förbättras marginellt
(2,5%→3,0% CAGR) - inom brusnivå, inte en tydlig vinst.

## Varför skiljer sig resultatet från den tidigare ablationen?

Troligen metodologisk, inte en motsägelse i sak: den ursprungliga
LOGO-ablationen (`tune_ablation.py`) mätte OOS capture-spread på en
LGBM-only-modell med sin egen holdout-uppdelning, inte samma
topp-10-likaviktade CAGR/Sharpe-backtest som används genomgående i den
här sessionens forskning. Olika mätmetod, olika (eller uppdaterad)
datasnapshot sedan ablationen ursprungligen kördes, och olika
sizing-skala kan alla bidra till skillnaden. Detta upphäver inte
nödvändigtvis den ursprungliga LOGO-ablationens slutsats i sitt eget
sammanhang - men visar att fyndet INTE generaliserar till den fulla
portföljbacktesten som används här.

## Slutsats

Negativt/neutralt resultat i den här testuppställningen - inför INTE
`config.DROP_FEATURES` baserat på detta. Om frågan ska drivas vidare bör
den första ablationen (`tune_ablation.py`) köras om på samma
full-universum-data och med samma CAGR/Sharpe-metodik som resten av
sessionen, för en verkligt jämförbar omprövning.

Rådata: `results/drop_tidig_entry_per_split.csv`, `_summary.csv`,
`_stability.csv`, `_backtest.csv` (ej incheckade).
