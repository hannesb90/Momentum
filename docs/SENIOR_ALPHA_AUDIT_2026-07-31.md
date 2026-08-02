# Momentum – senior alpha- och isoleringsgranskning

Datum: 2026-07-31

## Beslut

Nuvarande Large-kontrakt är **52 veckor**. #31 förkastade 52v för den äldre
pre-LambdaRank-modellen, men efter LambdaRank-migreringen omprövades beslutet
i #124 med ett färskt 4/8/13/26/52v-svep. 52v vann både dev och holdout:
dev CAGR/Sharpe 14,8%/1,25 och holdout 12,9%/1,08, mot 13v:s
14,1%/1,14 respektive 5,5%/0,50. `results/stats.json:horizon_weeks=52`
matchar därmed den senare validerade arkitekturen.

Resultat #165–#172 behöver alltså inte ogiltigförklaras på grund av
horisonten. De omfattas fortfarande av den generella risken att samma holdout
har öppnats många gånger.

## Stängda integritetsfel

1. Large-kontraktet hålls på den efter LambdaRank validerade 52v-designen.
2. Walk-forward-embargo löstes tidigare vid modulimport. Segment kunde därför
   få ett annat purge-värde än sin runtime-konfiguration. Defaults löses nu
   vid anropstid.
3. LGBM-checkpointnyckeln ignorerade träningsdatan trots att den tog `df` som
   argument. Samma features men andra targets/horisonter kunde återuppta en
   gammal modell. Nyckeln inkluderar nu data, horizon och splitkontrakt.
4. Modellartefakter får nu ett träningskontrakt (horizon, embargo, featurelista).
   Inference stoppas vid mismatch. Äldre modeller kontrolleras mot `stats.json`.
5. Ensemble-, topp-N- och LSTM-defaults som beror på muterbar runtime-config
   löses nu vid anropstid.
6. A2:s oenighetsmått var matematiskt degenererat (std ≈1 per aktie).
   Standardisering sker nu per modell över tvärsnittet; gammalt resultat är
   ogiltigförklarat.
7. Fingerprint-testet är hermetiskt och gör inte längre nätverksanrop mot en
   föränderlig först-ticker.

## Alpha: prioriterad arbetsordning

### 1. Återställ en trovärdig baslinje

- Behåll Large 52v och verifiera det inbäddade kontraktet vid nästa omträning.
- Verifiera inbäddat modellkontrakt, pipeline fingerprint och stats-horizon.
- Rapportera nettoalfa mot XACT Sverige, inte bara CAGR/Sharpe.
- Frys den redan hårt använda holdouten. Nästa produktionsdom bör komma från
  paper/live eller en senare, ännu orörd period.

### 2. Billigast sannolika inkrementella edge

- **A3 sektorneutral residualmomentum:** solo-IC för residualmomentum är stark,
  men sektordelen är inte isolerad. Kör IC/Q5–Q1 per era och sektor först.
- **Korrelationsfilter med påfyllnad:** korrigerad mätning visar att 20% av
  relevanta ombalanseringar tappar en effektiv plats. Fyll med nästa okorrelerade
  kandidat och mät netto; detta är ett konkret portföljimplementeringsgap.
- **Re-entry 10 procentenheter:** starkaste positiva fyndet hittills, men
  replikera på Small eller ny period innan adoption.
- **A2 korrekt oenighet:** kör bara om korrekt mått visar monotont samband med
  framtida nedsida/IC på dev. Full backtest först därefter.

### 3. Ny alpha kräver ny information

Pris-only och PM-sentiment har i stort sett uttömts. Högst informationsvärde har:

- point-in-time analytikerrevideringar/SUE,
- PIT share issuance/shareholder yield och asset growth,
- verkligt survivorship-fritt universum,
- eventtidstämplade rapportdata.

Utan PIT-data bör inga historiska fundamentalresultat användas som alpha-bevis.

## Tester som inte bör prioriteras

- fler finjusteringar av ensemblevikten (LSTM-benet verkar viktigt, exakt vikt
  gav ingen robust skillnad),
- koncentrationstak 20/25% (band aldrig i den testade mekanismen),
- dynamiskt antal positioner,
- fler generella exits/stoppar (whipsaw och cash drag är redan tydligt),
- ekonomisk målfunktion vald på backtest-CAGR (valde tidigare overfit-varianter).

## Kvarstående metodrisker

- survivorship bias i Yahoo-universumet,
- upprepad diagnostisk användning av samma holdout,
- tuning-skript muterar global `config` och `FEATURE_COLS`; säkert som separata
  processer men inte som importerbara bibliotek. Nya experiment ska lägga
  mutationer i `main()`/context och aldrig vid modulimport,
- `tune_large_small_allocation.py` blandar sleeves genom veckovis återställning
  utan explicit sleeve-rebalanseringskostnad; resultatet är inte investerbart
  förrän kostnaden och PIT-samtidigheten modelleras.

## Verifiering

Efter ändringarna passerar hela regressionssviten. Kör alltid sviten före
omträning och kontrollera att `stats.json:horizon_weeks` matchar modellens
kontrakt.
