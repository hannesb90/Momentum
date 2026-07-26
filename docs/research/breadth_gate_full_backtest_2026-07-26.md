# pct_positive_trend som styrsignal: fullständigt backtest - negativt resultat

Date: 2026-07-26

Uppföljning på `dispersion_proxy_analysis_2026-07-26.md`, som hittade att
`pct_positive_trend` (marknadsbredd, andel bolag med `roc_13w > 0`) var
den enda kandidatproxyn robust på BÅDA målen (test-IC, topp-decil-edge)
och - till skillnad från `val_auc_best` - beräkningsbar VECKOVIS utan
omträning. Den här körningen testar om det håller som en riktig,
veckovis position-styrande regel. Skript: `tune_breadth_gate.py`. Samma
full-universum-data (174 tickers) och riktiga `MomentumLGBM`/`ensemble.py`/
`MomentumBacktester`-infrastruktur som `abstention_gate`-backtestet.

## Tre varianter

1. **baseline** - ingen ändring.
2. **hard_threshold_30pct** - jämviktad exponering varje vecka där
   `pct_positive_trend < 30%` (samma nedre gräns som variant 3, för
   rättvis jämförelse).
3. **soft_bands** - kontinuerlig blandning modell/jämvikt: >70% breadd →
   100% modell, 50-70% → 75% modell, 30-50% → 50% modell, <30% → ren
   jämvikt.

`pct_positive_trend` beräknas VECKOVIS direkt ur `roc_13w` över hela
universumet - ingen framåtblick, ingen modell behövs.

## Tidsandel per band (hela historiken)

| Band | Andel av veckorna |
|---|---:|
| <30% | 21,9% |
| 30-50% | 44,3% |
| 50-70% | 29,6% |
| **>70%** | **4,2%** |

Marknaden ligger i "full modellvikt"-bandet (>70% breadd) bara 4,2% av
tiden - `soft_bands`-varianten späder alltså ut modellens övertygelse
NÄSTAN HELA TIDEN, inte bara i sällsynta krisveckor.

## Resultat

| Variant | Dev CAGR | Dev Sharpe | Dev MaxDD | Holdout CAGR | Holdout Sharpe | Turnover/år |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 9,4% | 1,57 | -8,9% | -0,3% | -0,03 | 5,84× |
| Hård tröskel (30%) | 8,2% | 1,41 | -8,5% | -0,2% | -0,02 | 6,04× |
| Mjuka band | **6,6%** | **1,36** | -8,0% | +0,2% | 0,06 | 4,85× |

**Dev-perioden försämras MONOTONT och tydligt** (CAGR 9,4%→8,2%→6,6%,
Sharpe 1,57→1,41→1,36) ju mer aggressivt breddregeln tillämpas. Holdout
förbättras bara marginellt (till +0,2% CAGR, 0,06 Sharpe - i praktiken
fortfarande platt, inte ett verkligt lyft jämförbart med
`val_auc_best`-gatets +0,77 Sharpe-siffra i föregående dokument). Hård
tröskel ökar dessutom turnover något (5,84×→6,04×/år) - en veckovis
brusig signal som korsar tröskeln fram och tillbaka skapar extra churn,
i stället för att minska den.

## Per marknadsregim (baseline vs de två varianterna)

| Regim | Baseline | Mjuka band | Hård tröskel |
|---|---:|---:|---:|
| Bear | -0,176% | -0,176% (oförändrat) | **-0,189%** (sämre) |
| Bull | +0,234% | **+0,199%** (sämre) | +0,229% (sämre) |
| Sidledes | +0,086% | **+0,066%** (sämre) | +0,066% (sämre) |

**Samtliga tre regimer blir lika bra eller SÄMRE under båda
breddvarianterna - aldrig bättre.** Exakt motsatt mönster mot
`val_auc_best`-gatets per-regim-resultat (som visade små men konsekventa
FÖRBÄTTRINGAR i alla tre regimer).

## Varför funkade den robusta korrelationen inte som veckoregel?

Den starka, robusta korrelationen i `dispersion_proxy_analysis.md`
mättes på PER-SPLIT-nivå (ett breddvärde per 13-veckorsperiod mot hela
periodens genomsnittliga edge) - ett lågfrekvent regimmått. Att applicera
SAMMA tröskelvärden på VECKOVIS data är en helt annan, mycket brusigare
signal: 44% av alla veckor hamnar i det "medelmåttiga" 30-50%-bandet, och
bara 4,2% når det översta "full vikt"-bandet. Bandgränserna (70/50/30),
kalibrerade mot per-split-kvintilernas medelvärden, motsvarar inte alls
samma andelar i veckodataens fördelning - resultatet blir att modellens
konviktion späds ut nästan HELA tiden i stället för selektivt under
genuint svaga perioder. En robust periodnivå-korrelation generaliserar
alltså INTE automatiskt till en veckovis handelsregel - upplösnings-
mismatchen mellan mätning och tillämpning är i sig en viktig lärdom.

## Slutsats

**Negativt resultat - `pct_positive_trend` som veckovis styrsignal
försämrar strategin, både i dev (tydligt) och tvärs alla tre
marknadsregimer, med bara en marginell (och sannolikt brusdriven)
förbättring i holdout.** Detta trots att samma mått var den mest robusta
kandidaten i periodnivå-analysen - ett konkret exempel på att en
korrelation som håller på en given tidsupplösning inte fritt kan
överföras till en annan utan egen validering.

**Rekommendation:** koda INTE in breddregeln i `ensemble.py`. Om
marknadsbredd ska undersökas vidare, testa den på SAMMA upplösning
(13-veckorsperioder, inte enskilda veckor) den faktiskt validerades på,
eller kalibrera nya bandgränser direkt mot veckodataens egen fördelning
i stället för att återanvända per-split-kvintilernas gränsvärden.
Ingen av de två testade styrsignalerna (`val_auc_best`, `pct_positive_
trend`) har hittills klarat ett fullständigt backtest tillräckligt
robust för produktion.

Rådata: `results/breadth_gate_backtest.csv`,
`results/breadth_gate_per_regime.csv` (genererade av
`tune_breadth_gate.py`, ej incheckade).
