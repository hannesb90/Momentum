# Spår D — neutralt modellrace på fryst dataset_v1.0

## Beslut

**C) SVAG/INGEN MODELLSIGNAL.** Den rena CORE-basen innehåller en tydlig enkel
12-månaders momentumstruktur, men det neutrala ML-racet visar inte robust marginalnytta
över denna baseline. Ingen A/B/C-/targetfil ändrades och ingen dataintegritetsbugg hittades.

Ingen modellfamilj klarade den förregistrerade kombinationen positiv OOS-IC,
icke-degenererade scores och tickerrobusthet. Därför valdes **0 modeller** och
CORE+FUNDAMENTA-challengern kördes inte. Urvalsregeln lättades inte efter resultatet.

## Förregistrerad tidsdesign

| Fönster | Roll | Train | Eval | Train obs/datum | Eval obs/datum |
|---|---|---|---|---:|---:|
| 2023 | validation | 2020-01-03–2021-12-31 | 2023-01-27–2023-12-29 | 8 881 / 27 | 4 511 / 13 |
| 2024 | OOS | 2020-01-03–2022-12-30 | 2024-01-26–2024-12-27 | 13 422 / 40 | 4 408 / 13 |
| 2025 | OOS | 2020-01-03–2023-12-29 | 2025-01-24–2025-07-11 | 17 933 / 53 | 2 373 / 7 |

Embargo är exakt 52 veckor. Samtliga fem familjer använder samma 29 CORE-features,
target, observationsuniversum, paneldatum och kostnads-/portföljlogik. Ingen random CV,
early stopping, tuning, feature selection eller resultatanpassning användes.

## Primärt resultat

OOS avser 2024–2025-07, 6 781 observationer och 20 paneldatum.

| Modell | Mean IC52 | Median IC52 | Positiva datum | Mean top-30 IC52 | 2024 mean IC | 2025 mean IC |
|---|---:|---:|---:|---:|---:|---:|
| 12m momentum | **0,133** | **0,165** | **95 %** | -0,043 | 0,120 | 0,157 |
| XGBoost | 0,095 | 0,105 | 85 % | -0,187 | 0,085 | 0,113 |
| CatBoost | 0,089 | 0,084 | 100 % | -0,117 | 0,082 | 0,104 |
| LightGBM | 0,072 | 0,078 | 75 % | -0,214 | 0,043 | 0,124 |
| Ridge | -0,002 | -0,011 | 45 % | -0,084 | 0,015 | -0,034 |
| ElasticNet | -0,024 | -0,024 | 35 % | -0,100 | -0,008 | -0,053 |

Valideringen 2023 stödjer samma försiktiga slutsats: XGBoost/LightGBM/CatBoost hade
mean IC 0,034/0,028/0,010, medan 12m momentum hade 0,095. Ridge och ElasticNet var
negativa (-0,164/-0,169).

Trädmodellerna fångar alltså en bred rangsignal, men ingen slår den enkla
momentumbaslinjen på primär OOS-IC. Än viktigare: samtliga ML-modellers top-30-IC är
negativ. ML förbättrar inte rangordningen där portföljen faktiskt koncentreras.

## Sekundär portfölj

Top-30 är lika viktad, ombalanseras var fjärde vecka och belastas med 20 bp per
one-way turnover. Benchmark är samma observerbara universum lika viktat. CAGR är
sekundärt och avgör inte vinnaren.

| Modell | CAGR | Excess mot 14,0 % benchmark | Sharpe | MaxDD | Turnover |
|---|---:|---:|---:|---:|---:|
| CatBoost | 42,2 % | 28,2 % | 1,53 | -9,5 % | 42,2 % |
| LightGBM | 40,7 % | 26,7 % | 1,38 | -8,9 % | 39,8 % |
| XGBoost | 38,4 % | 24,3 % | 1,40 | -10,9 % | 40,8 % |
| Ridge | 19,9 % | 5,9 % | 0,36 | -18,8 % | 26,0 % |
| ElasticNet | 17,3 % | 3,3 % | 0,24 | -20,7 % | 22,5 % |
| 12m momentum | 15,1 % | 1,1 % | 0,10 | -14,7 % | 32,3 % |

Dessa attraktiva träd-CAGR-värden godkänns inte som robust alpha. När de tre största
tickerbidragen lämnas ute faller excessavkastningen med 70 % för LightGBM, 64 % för
XGBoost och 68 % för CatBoost — över den preregistrerade 50 %-gränsen.
Topptickers är i respektive modell XBRANE/PREC/STRAX, XBRANE/QLINEA/STRAX och
XBRANE/ISOFOL/STRAX. Full contribution per ticker, bästa/sämsta ticker,
leave-one-ticker-out och periodbidrag finns i `core_metrics.json`.

Sektorkoncentrationen är också synlig: sectorId 4 står för 33,2 %/29,0 %/30,7 % av
LightGBM/XGBoost/CatBoost-valen. Sektor-ID används endast för efterhands-QA, aldrig som feature.

## Scorekvalitet

- Ridge, ElasticNet och CatBoost: inga ties; minst 337 distinkta OOS-scores per datum.
- LightGBM: minst 272 distinkta scores; maximal tieandel 20,5 %.
- XGBoost: minst 226 distinkta scores; maximal tieandel 33,9 %.
- Ingen modell har noll/konstant scorevarians. Median rankstabilitet mellan intilliggande
  datum är 0,69–0,92. Den tidigare typen av degenererad sen ranking återkom inte.

## FUNDAMENTA challenger

Inte körd. Detta är ett resultat av den låsta urvalsregeln, inte ett bortfall:
ingen CORE-familj kvalificerade. Fundamental-survivorship 67/68 kvarstår därmed en
framtida begränsning, men påverkade inte detta race eftersom endast CORE användes.

## Frysta artefakter

- Preregistrering: `spard/core_race_preregistration.json`
- Splits: `split_manifest.json`
- Predictions/scores: `core_predictions.json`
- Metrics, portfolios och robusthet: `core_metrics.json`
- CORE-lock: `CORE_LOCK.json`
- Urval: `selection.json`
- Miljö/versioner: `environment.json`
- Full fillista/SHA256: `manifest.json`

Kärnhashar:

- predictions: `8a923a81112c1a8fd251f1f4ed1023a95284a241dd3d50eb3a946acef0c8eac7`
- metrics: `772e313d50a661f8fc6681b7c93ccf18212ca8f56d40c274d246385519d3238a`
- splits: `df577a35fe74c2e1cc2469c4e7cca764b56bff2847a17241f471bb22ae512c1e`

Två fulla resultatrundor gav identiska predictions, scores, metrics och locks.
Icke-deterministiska pickle-bytes från tredjepartsbibliotek lagras avsiktligt inte;
reproduktion sker från låst kod, konfiguration, miljö och inputs.

## Backlog — inte byggt nu

- Macro/Regime-lager
- räntor och yield curve
- SEK/valuta
- kredit/risk sentiment
- VIX
- råvaror
- marknadsregim
- sektorinteraktioner
- alpha-lager
- exitstrategier
- eventuell senare hyperparametertuning

Varje framtida lager ska testas som separat marginalbidrag ovanpå denna låsta CORE-benchmark.
Det neutrala resultatet får inte repareras i efterhand.
