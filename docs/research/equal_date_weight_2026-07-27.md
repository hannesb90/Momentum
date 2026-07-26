# Lika sample-vikt per datum - första genuint positiva holdout-resultatet

Date: 2026-07-27

Punkt 2/6 i användarens ursprungliga uppföljningslista (senare omprioriterad
till punkt 3): datum med fler noterade bolag får automatiskt större vikt i
förlustfunktionen eftersom `fit_walk_forward` tränar radvis utan sample
weights. Testat: samma binära klassificeringsobjective, samma features,
samma 31 walk-forward-splits, samma kalibreringsmetodik
(`CALIBRATION_VAL_FRACTION`-uppdelning) - enda skillnaden är
`lgb.Dataset(..., weight=1/n_tickers_den_veckan)` så varje datum bidrar
lika mycket TOTALT till förlusten. Skript: `tune_equal_date_weight.py`.

## Rangordningsmått (median över 31 splits, innan portföljfilter)

| Mått | Baseline | Lika datumvikt |
|---|---:|---:|
| Rank IC | 0,038 | 0,032 (något sämre) |
| Topp-decil-edge | 0,0024 | **0,0078** (~3x bättre) |
| NDCG@10 | 0,245 | 0,253 (något bättre) |
| Unika score-värden | 11 | 9 (något sämre) |
| Rankstabilitet (turnover) | 81,3% | 86,6% (något sämre) |

Blandad bild på de råa måtten - något bättre topp-decil-edge, i övrigt
ungefär oförändrat eller marginellt sämre.

## Fullständigt backtest (topp-10 likaviktat)

| Variant | Dev CAGR | Dev Sharpe | Dev MaxDD | Holdout CAGR | Holdout Sharpe |
|---|---:|---:|---:|---:|---:|
| Baseline | +7,6% | 1,17 | -7,5% | +2,5% | 0,43 |
| **Lika datumvikt** | +6,1% | 0,98 | -8,1% | **+7,7%** | **1,14** |

**Detta är det första resultatet i hela forsknings-tråden (val_auc-gate,
breadth-gate, objective-jämförelse) där en metodändring ger en tydlig,
stor förbättring i den RIKTIGA holdout-perioden** - CAGR mer än tredubblas
(2,5%→7,7%), Sharpe mer än fördubblas (0,43→1,14). Priset är en
försämring i dev-perioden (CAGR 7,6%→6,1%, Sharpe 1,17→0,98, MaxDD
-7,5%→-8,1%) - inte en gratislunch, ett genuint avvägningsbeslut.

## Försiktighetsflagga (samma disciplin som resten av sessionen)

Precis som `val_auc_best`-gatets holdout-hopp visade sig vara EN splits
tröskelpassage, är detta resultat baserat på EN enda holdout-period
(104 veckor, helt extrapolerad från sista splittens modell). Ett enda
lyckat/misslyckat path är ett tunt underlag - resultatet bör inte
adopteras baserat på denna ensamma siffra utan vidare kontroll (t.ex. om
mönstret håller på en annan feature-/datasnapshot, eller genom att
undersöka VILKA enskilda veckor inom holdouten som gör skillnaden).
Mekanismen är dock rimlig: att inte låta datum med råkat många noterade
bolag dominera förlustfunktionen är en genuint sund invändning mot
nuvarande upplägg, till skillnad från flera av de tidigare testade
idéerna (breadth-gate) som byggde på en förhoppning som inte höll.

## Slutsats

Mest lovande resultatet hittills i uppföljningsserien. Inte tillräckligt
ensamt för att motivera en produktionsändring (samma bar som resten av
sessionen: kräver robusthet över mer än en observation), men värt en
snabb sanity-check (t.ex. vilka specifika holdout-veckor som drev
skillnaden) innan det läggs åt sidan eller drivs vidare.

Rådata: `results/equal_date_weight_per_split.csv`, `_summary.csv`,
`_stability.csv`, `_backtest.csv` (ej incheckade).
