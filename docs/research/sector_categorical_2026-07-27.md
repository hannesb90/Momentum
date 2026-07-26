# Sektor som nativ LightGBM-kategori - negativt, avstår

Date: 2026-07-27

Punkt 6 i uppföljningslistan: `sector_code` kodas idag ORDINALT
(`features/feature_engineering.py::_category_code`, index i
`config.SECTOR_CATEGORIES`-listan). LightGBM behandlar den då som en
vanlig numerisk feature med en riktning (sektor 5 antas ligga "mellan"
sektor 2 och 8), trots att listans ordning är godtycklig - bara den
ordning sektorerna råkade läggas till i config.py, ingen verklig gradient
(t.ex. "cyklisk" -> "defensiv"). Testat: LightGBM:s nativa kategoriska
hantering (`categorical_feature=[...]` till `lgb.Dataset`), som vid varje
split söker den bästa GRUPPERINGEN av kategorier på träningsdata i stället
för att anta någon ordning. Identisk binär klassificeringsobjective,
features, splits och kalibrering i övrigt. Skript: `tune_sector_categorical.py`.

11 distinkta `sector_code`-värden förekommer i data (av 14 möjliga i
`config.SECTOR_CATEGORIES` - inte alla kategorier är representerade i
det aktuella universumet).

`cap_tier_code` testades INTE - den listan (Mega -> Nano Cap) har en
genuin ordning, så ordinal kodning är rimlig där; det är bara sektor som
saknar en meningsfull inbördes ordning.

## Rangordningsmått (median över 31 splits, innan portföljfilter)

| Mått | Baseline (ordinal) | Kategorisk sektor |
|---|---:|---:|
| Rank IC | 0,038 | **0,011** (mer än halverad) |
| Topp-decil-edge | 0,0024 | 0,0123 (högre - se reservation nedan) |
| Unika score-värden | 11 | 10 |
| Rankstabilitet (turnover) | 81,3% | 82,9% (marginellt sämre) |

Topp-decil-edgen är motsägelsefullt HÖGRE trots kraftigt sämre Rank IC -
ett tecken på att den kategoriska varianten producerar en mer instabil,
mer utspridd fördelning av rå scorer (t.ex. några enstaka splittar med
extrema utslag drar upp medelvärdet av edge-måttet) snarare än en
genuint bättre rangordning över hela linjen. Fullbacktesten nedan, som
väger in HELA perioden i stället för medianer/medelvärden av enskilda
mått, ger den tydligaste bilden och den är entydigt negativ.

## Fullständigt backtest

| Variant | Dev CAGR | Dev Sharpe | Dev MaxDD | Holdout CAGR | Holdout Sharpe |
|---|---:|---:|---:|---:|---:|
| Baseline | +7,6% | 1,17 | -7,5% | +2,5% | 0,43 |
| Kategorisk sektor | +6,9% | 1,00 | **-12,4%** | **-2,0%** | **-0,30** |

Rakt igenom sämre: lägre dev-Sharpe, betydligt djupare dev-drawdown
(-12,4% mot -7,5%), och holdout blir negativ (både CAGR och Sharpe byter
tecken). Till skillnad från de "dev sämre/holdout bättre"-mönstren i
lika-datumvikt/icke-överlappande-labels-experimenten är detta samstämmigt
negativt i BÅDA perioderna - inget tecken på att det bara är en
regulariseringseffekt som råkar gynna holdout.

## Slutsats

Negativt resultat - inför INTE kategorisk sektor-kodning. Med bara 11
representerade kategorier och en trädmodell som redan kan hitta
godtyckliga uppdelningar längs den ordinala axeln (ett träd behöver inte
faktiskt tro att sektor 5 ligger "mellan" 2 och 8 - det kan splitta
`sector_code <= 4.5` lika lätt som en explicit kategorisk gruppering)
tycks den nativa kategoriska sökningen mest introducera extra
frihetsgrader som modellen överanpassar mot i stället för att fånga upp
verklig sektorstruktur. Nuvarande ordinal-kodning behålls.

Rådata: `results/sector_categorical_per_split.csv`, `_summary.csv`,
`_stability.csv`, `_backtest.csv` (ej incheckade).
