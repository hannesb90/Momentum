# LightGBM native NaN-hantering i stället för fillna(0) - negativt

Date: 2026-07-27

Punkt 5 i uppföljningslistan: koden kör genomgående `fillna(0)` innan
data går in i LightGBM, vilket gör "saknad data" och "verkligt värde
noll" identiska. Testat: samma binära klassificeringsobjective, samma
features/splits/kalibrering, enda skillnaden är att rå NaN skickas till
LightGBM (`use_missing=True` som default - modellen lär sig per
split-nod åt vilket håll saknade värden ska gå). Skript:
`tune_nan_native.py`.

Features med störst NaN-andel i datan (relevant kontext - dessa är de
features fillna(0)-bytet påverkar mest):

| Feature | NaN-andel |
|---|---:|
| div_growth_yoy | 93,2% |
| eps_growth_yoy | 90,9% |
| rev_growth_yoy | 47,6% |
| report_reaction_abn | 42,9% |
| resid_mom | 19,1% |

De fundamentala tillväxtfeaturesen (utdelnings-/vinst-/omsättnings-
tillväxt) saknas för de allra flesta rader - rimligt givet att de bara
blir kända efter bolagets FÖRSTA rapport i MFN-cachen, och `fillna(0)`
tolkar "okänd tillväxt" som "0% tillväxt" för 90 %+ av observationerna
på just dessa två features.

## Rangordningsmått (median över 31 splits, innan portföljfilter)

| Mått | Baseline (fillna(0)) | Nativ NaN |
|---|---:|---:|
| Rank IC | 0,038 | 0,040 (marginellt bättre) |
| Topp-decil-edge | 0,0024 | 0,0019 (marginellt sämre) |
| Unika score-värden | 11 | 10 (oförändrat) |
| Rankstabilitet (turnover) | 81,3% | 87,4% (sämre) |

I praktiken oförändrat på de råa måtten - ingen tydlig vinst eller
förlust.

## Fullständigt backtest

| Variant | Dev CAGR | Dev Sharpe | Dev MaxDD | Holdout CAGR | Holdout Sharpe |
|---|---:|---:|---:|---:|---:|
| Baseline | +7,6% | 1,17 | -7,5% | +2,5% | 0,43 |
| Nativ NaN | 6,4% | 0,96 | -8,3% | **1,4%** | **0,24** |

**Rakt igenom sämre** - till skillnad från de två föregående
experimenten (lika datumvikt, icke-överlappande labels) förbättras INTE
holdout här. Både dev och holdout försämras måttligt.

## Slutsats

Negativt resultat - inför INTE nativ NaN-hantering baserat på detta.
Hypotesen att fillna(0) döljer meningsfull information (särskilt för de
mycket NaN-täta fundamenta-featuresen) höll inte i praktiken - LightGBMs
inlärda missing-split-riktning tillförde inget mätbart värde här, och
bryter dessutom det "dev sämre/holdout bättre"-mönster de två senaste
experimenten visade (vilket i sig är informativt: det mönstret var alltså
INTE en generell effekt av "vilken ändring som helst som stör
baseline-modellen", utan specifikt kopplat till lika-datumvikt/reducerat
label-överlapp).

Rådata: `results/nan_native_per_split.csv`, `_summary.csv`,
`_stability.csv`, `_backtest.csv` (ej incheckade).
