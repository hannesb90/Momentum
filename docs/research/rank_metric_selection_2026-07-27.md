# Rank IC/NDCG@10 som early-stopping-metrik i stället för AUC - ingen robust vinst

Date: 2026-07-27

Punkt 8 i uppföljningslistan: modellvalet (early stopping, dvs. vilken
boosting-iteration som blir "bäst") styrs idag av AUC på
valideringsfönstret. AUC mäter binär klassificeringskvalitet mot
`target_signal` - men det som faktiskt avgör portföljresultatet är
rangordningskvalitet mot den KONTINUERLIGA framtida avkastningen
(`target_return`). Spearman-korrelation mellan en predikterad sannolikhet
och en BINÄR label är dock matematiskt bara en omskalad AUC
(Mann-Whitney U) - att testa "Rank IC mot target_signal" hade alltså inte
varit ett giltigt test av något nytt. Testat i stället: två custom
`feval`-metriker mot `target_return` direkt, medelvärde PER
valideringsdatum (tvärsnitt inom varje vecka, inte poolat över tid):

  - `rank_ic_selection` – medel-Spearman (pred vs `target_return`) per datum.
  - `ndcg10_selection`  – medel-NDCG@10 per datum, relevans = ordinal
    decil (0-9) av `target_return` inom datumet (samma decil-konstruktion
    som `tune_objective_comparison.py` använder för LambdaRank).

Objectivet (binär klassificering, samma loss/gradienter/features/data som
produktionen) är OFÖRÄNDRAT i alla tre varianter - bara vilken metrik som
styr var early stopping stannar. `metric="None"` stängde av LightGBM:s
inbyggda AUC-spårning helt, så stoppunkten styrs uteslutande av
feval-måttet. Kalibreringen (isotonic mot `target_signal`) är identisk i
alla varianter. Skript: `tune_rank_metric_selection.py`.

## Rangordningsmått (median över 31 splits, innan portföljfilter)

| Mått | Baseline (AUC) | Rank IC-selection | NDCG@10-selection |
|---|---:|---:|---:|
| Rank IC | 0,038 | 0,022 (sämre) | 0,022 (sämre) |
| Topp-decil-edge | 0,0024 | 0,0024 (oförändrat) | 0,0114 (bättre) |
| NDCG@10 | 0,245 | 0,245 (oförändrat) | 0,233 (marginellt sämre) |
| Unika score-värden | 11 | 12 | 8 |
| Rankstabilitet (turnover) | 81,3% | 81,6% | 82,6% |

Kontraintuitivt: att styra early stopping mot Rank IC gjorde INTE Rank IC
bättre på testfönstret (0,038→0,022). Trolig förklaring: `val_d_stop`
(delen av valideringsfönstret som avgör stoppunkten, efter
`CALIBRATION_VAL_FRACTION`-uppdelningen) innehåller färre oberoende
tvärsnitt än hela valideringsfönstret AUC mäts på - ett per-datum-medelvärde
av Spearman-korrelation över få veckor är en brusigare stoppsignal än AUC
poolat över alla observationer, vilket tycks leda till en sämre vald
iteration snarare än en bättre.

## Fullständigt backtest

| Variant | Dev CAGR | Dev Sharpe | Dev MaxDD | Holdout CAGR | Holdout Sharpe |
|---|---:|---:|---:|---:|---:|
| Baseline (AUC) | +7,6% | 1,17 | -7,5% | +2,5% | 0,43 |
| Rank IC-selection | +7,2% | 1,07 | -7,5% | +2,5% | 0,44 |
| NDCG@10-selection | +6,3% | 0,96 | -6,7% | +2,5% | 0,44 |

Holdout är i praktiken IDENTISK mellan alla tre varianter (CAGR +2,5% på
decimalen, Sharpe 0,43 vs 0,44 - inom brus för en enda 104-veckors period).
Dev-perioden är flat-till-sämre för båda de nya varianterna, tydligast för
NDCG@10-selection (Sharpe 1,17→0,96). Ingen av varianterna visar det
"dev sämre/holdout bättre"-mönster som lika-datumvikt och
icke-överlappande-labels gjorde - här är det snarare "ingen skillnad där
det räknas (holdout), lätt sämre där det går att mäta tydligast (dev)".

## Slutsats

Ingen robust vinst - inför INTE Rank IC eller NDCG@10 som
early-stopping-kriterium. Hypotesen att AUC-styrd modellselektion var
strukturellt fel för portföljmålet höll inte i praktiken: en brusigare
per-datum-rangordningsmetrik på ett redan litet stop-fönster tycks kosta
mer i stabilitet än den vinner i målmatchning. AUC behålls som
selektionskriterium.

Rådata: `results/rank_metric_selection_per_split.csv`, `_summary.csv`,
`_stability.csv`, `_backtest.csv` (ej incheckade).
