# Avstående-regel: fullständigt walk-forward-backtest (CAGR/Sharpe/MaxDD)

Date: 2026-07-26

Uppföljning på `reject_split_followup_precursors_windows_regime_abstention_2026-07-26.md`
(som visade riktningen med enkla genomsnittsavkastningar). Detta är den
fulla, riktiga backtesten användaren efterfrågade innan mekanismen
eventuellt kodas in i `ensemble.py`: **hela** large-universumet (174
tickers efter fond-/likviditetsfilter, färsk data), en riktig
`MomentumLGBM.fit_walk_forward()`-körning (exakt produktionskoden), riktiga
`ensemble.py`-funktioner för positionsstorlek, och `MomentumBacktester` för
CAGR/Sharpe/MaxDD/turnover. Skript: `tune_abstention_gate.py`
(fetch/train/backtest).

**Inget kodat in i `ensemble.py`/live-signallogiken.** Detta är enbart en
valideringskörning, per instruktion.

## Design: ingen framåtblick

Varje historiskt datum tilldelas `val_auc_best` från den split
`MomentumLGBM._select_model_idx` FAKTISKT skulle valt för just det datumet
(samma sökordning `predict()` använder). En splits `val_auc_best`
beräknas under dess egen träning, på data som avslutas FÖRE dess eget
testfönster - mappningen date→val_auc_best kan därför aldrig läcka in
framtida information, per konstruktion (verifierat separat i föregående
uppföljningsdokument: samtliga 31 splits strikt kronologiska).

## Varianter testade

- **Hårda trösklar** 0,50 / 0,51 / 0,52 / 0,53 / 0,54, var och en med tre
  fallbacks: `equal_weight` (jämviktad över eligible-namn), `benchmark`
  (100% i XACT-OMXS30.ST), `cash` (0% investerat).
- **Mjuk viktning** (separat variant, ej del av tröskelsvepet): linjär
  blandning mellan normal topp-N-vikt (AUC≥0,54) och jämviktad exponering
  (AUC≤0,52).
- **Baseline**: ingen avstående alls (nuvarande produktionslogik).

## Resultat, dev (14 år) vs holdout (fryst, 2024-04-29→)

| Variant | Dev CAGR | Dev Sharpe | Holdout CAGR | Holdout Sharpe | Turnover/år |
|---|---:|---:|---:|---:|---:|
| Baseline (ingen avstående) | 9,4% | 1,57 | **-0,3%** | **-0,03** | 5,84× |
| Tröskel 0,52, jämviktad | 9,9% | 1,65 | -0,3% | -0,04 | 5,77× |
| Tröskel 0,53, jämviktad | 9,8% | 1,65 | **+2,3%** | **+0,77** | 5,04× |
| Tröskel 0,54, jämviktad | 9,9% | 1,67 | +2,3% | +0,77 | 4,69× |
| Mjuk viktning (0,52-0,54) | 9,6% | 1,64 | +1,3% | 0,45 | 5,10× |

(Fullständig tabell inkl. benchmark-/kontant-fallback:
`results/abstention_backtest_sweep.csv`, ej incheckad.)

## KRITISK nyans: holdout-effekten drivs av EN split, inte många

Hela den frusna holdout-perioden (2024-04-29 och framåt) serveras via
EXTRAPOLERING från den SISTA uppmätta splitten (split 31, testfönster
slutar 2023-12-04 - ingen av de 31 splittarna har ett testfönster INOM
holdout-perioden). Split 31:s `val_auc_best = 0,5243` - precis över
tröskeln 0,52 (ingen effekt) men under 0,53 (full effekt). **Hela
Sharpe-hoppet från -0,03 till +0,77 i holdout är alltså en enda splits
tröskelpassage, inte ett mönster som upprepar sig över flera oberoende
perioder.** Detta är exakt den typen av skör, fåtal-splittar-driven
effekt användaren bad mig kontrollera för - och den håller INTE testet.

## Vad som DÄREMOT är brett förankrat (men litet)

Vid tröskel 0,50-0,52 (10 av 31 splits berörda, ingen av dem i holdout):

- **Dev-effekten är i praktiken brusnivå** (9,4%→9,9% CAGR, 1,57→1,65
  Sharpe) - varken ett tydligt lyft eller en försämring.
- **Per-split** (tröskel 0,52, jämviktad): blandad bild. Tydliga
  förbättringar (split 10: -0,22%→+0,08% veckoavkastning, split 20:
  +0,06%→+0,35%, split 30: -0,16%→-0,05%) men också tydliga försämringar
  (split 7: +0,38%→+0,10%, split 27 - samma split som i föregående
  dokument visade genuin edge trots ett enda träd: +0,05%→+0,01%).
- **Per marknadsregim**: konsekvent, om än små, förbättringar i ALLA tre
  regimer (bear -0,176%→-0,171%, bull +0,234%→+0,250%, sideways
  +0,086%→+0,092% veckoavkastning) - ingen regim blir sämre. Det här är
  den mest robusta (flest oberoende observationer bakom sig), om än
  minst dramatiska, delen av resultatet.
- **Turnover sjunker något** med jämviktad avstående (5,0-5,8×/år mot
  5,8× baseline) - ett litet men konsekvent sekundärt plus.

`equal_weight` slår genomgående `benchmark` och `cash` som fallback-val -
`cash` tappar uppsidan när marknaden ändå går upp under en svag-signal-
period, `benchmark` presterar mittemellan.

## Slutsats

**Uppfyller INTE fullt ut kriteriet "robust förbättring över flera
trösklar, inte bara drivet av ett fåtal splittar."** Det dramatiska,
marknadsföringsbara resultatet (holdout Sharpe -0,03→+0,77) är en enda
splits tröskelpassage - skört, inte ett upprepat mönster. Det finns ett
bredare men modest stöd (konsekventa små positiva nudgar över regimer och
en majoritet av de berörda splittarna vid tröskel 0,50-0,52), men det är
för litet för att ensamt motivera en produktionsändring.

**Rekommendation:** koda INTE in avstående-mekanismen i `ensemble.py` änn
u. Behåll den redan implementerade `val_auc_best`-trend-signalen
(`pipeline_diagnostics.py::_val_auc_trend`, `declining_trend`-flaggan i
`pipeline_health.json`) som övervakning - den är fortfarande den bästa
framåtblicksfria tidiga varningssignalen, oavsett avstående-beslutet.
Samla mer data (fler splits, en framtida omträning där split 31:s
efterträdare får ett eget mätt testfönster i stället för extrapolering)
innan frågan omprövas.

Rådata: `results/abstention_backtest_sweep.csv`,
`results/abstention_per_split_breakdown.csv`,
`results/abstention_per_regime_breakdown.csv` (genererade av
`tune_abstention_gate.py`, ej incheckade - resultatmapp gitignorad).
