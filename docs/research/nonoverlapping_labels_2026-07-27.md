# Icke-överlappande labels - sämre in-sample, bättre holdout (samma mönster igen)

Date: 2026-07-27

Punkt 4 i uppföljningslistan: 13-veckors framtidsavkastning beräknas
varje vecka, så två intilliggande träningsrader för samma ticker delar
12 av 13 veckors framtidsdata - inte forward leakage (embargot är
korrekt), men den effektiva oberoende stickprovsstorleken är mycket
mindre än radantalet antyder. Testat: träna bara på var 13:e
(=`FORWARD_WEEKS`) datum i stället för varje vecka - varje kvarvarande
rad har då ett helt icke-överlappande 13-veckorsfönster. Validering och
testfönster oförändrade (full veckovis upplösning). Skript:
`tune_nonoverlapping_labels.py`.

**Metodologisk reservation (gäller hela resultatet nedan):** detta
minskar tränings-radantalet till **7,7%** av originalet (65 062 av
848 486 rader) - inte en ren isolering av "överlapp", utan konflaterat
med "drastiskt mindre träningsdata". Ett genuint rent test hade krävt
mer kalenderhistorik för att kompensera, vilket inte var görbart inom
samma dev-fönster.

## Rangordningsmått (median över 31 splits, innan portföljfilter)

| Mått | Baseline | Icke-överlappande |
|---|---:|---:|
| Rank IC | 0,038 | **-0,019** (blir negativ) |
| Topp-decil-edge | 0,0024 | 0,0002 (mycket sämre) |
| NDCG@10 | 0,245 | 0,227 (sämre) |
| Unika score-värden | 11 | 7 (sämre) |
| Rankstabilitet (turnover) | 81,3% | 92,6% (mycket sämre) |

**Alla råa mått är sämre** - till skillnad från lika-datumvikt-testet
(som hade blandade råa mått men en tydlig backtest-vinst) är detta
resultat entydigt negativt på in-sample-rangordningskvalitet.

## Fullständigt backtest

| Variant | Dev CAGR | Dev Sharpe | Dev MaxDD | Holdout CAGR | Holdout Sharpe |
|---|---:|---:|---:|---:|---:|
| Baseline | +7,6% | 1,17 | -7,5% | +2,5% | 0,43 |
| Icke-överlappande | 5,4% | 0,85 | -8,4% | **+5,7%** | **0,93** |

Trots att ALLA råa rangordningsmått är sämre, är holdout ändå bättre
(CAGR 2,5%→5,7%, Sharpe 0,43→0,93) - samma RIKTNING som
lika-datumvikt-resultatet (dev sämre, holdout bättre), men här mest
sannolikt en "mindre data att överanpassa till"-effekt snarare än ett
genuint "överlapp var problemet"-fynd, givet hur kraftigt
radreduktionen var och att de råa måtten konsekvent försämrades.

## Ett återkommande mönster värt att notera

Det här är NU DEN ANDRA sessionens experiment (efter lika datumvikt) där
en förändring som försämrar dev-perioden ändå förbättrar den riktiga
holdout-perioden. Ett enda holdout-fönster (104 veckor) är fortfarande
ett tunt underlag för att dra en stark slutsats av någotdera resultatet
för sig, men mönstret UPPREPAT över två oberoende metodändringar (olika
mekanismer: samplingsvikt kontra radurval) är svagt suggestivt att
nuvarande modell är något överanpassad till dev-periodens
egenheter - värt en riktig undersökning (t.ex. lärkurvor: hur känsligt
är dev/holdout-gapet för regulariseringsstyrka i allmänhet, inte bara
just dessa två specifika ingrepp).

## Slutsats

Inför INTE detta specifika ingrepp (för kraftig databeskärning, oklart om
vinsten beror på minskat överlapp eller bara mindre data). Men det
förstärker en växande hypotes: modellen må vara systematiskt överanpassad
till dev-perioden på ett sätt som skadar generalisering till holdout -
värt att undersöka direkt (regulariseringsstyrka, tränings­fönsterlängd)
snarare än via fler punktvisa ingrepp.

Rådata: `results/nonoverlap_per_split.csv`, `_summary.csv`,
`_stability.csv`, `_backtest.csv` (ej incheckade).
