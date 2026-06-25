# ML Momentum/Trend Trading System

## Struktur
```
momentum_ml/
├── README.md
├── requirements.txt
├── config.py                  # Alla parametrar
├── data/
│   └── data_loader.py         # Hämta & cacha veckodata
├── features/
│   └── feature_engineering.py # Alla tekniska features
├── models/
│   ├── lgbm_model.py          # LightGBM bas-modell
│   ├── lstm_model.py          # LSTM sekvensmodell
│   └── ensemble.py            # Ensemble + positionssizing
├── backtest/
│   ├── backtester.py          # Walk-forward backtest (kostnader, impact, DD-guard, korrelations-/sektorfilter)
│   ├── bootstrap.py           # Block bootstrap + Probabilistic/Deflated Sharpe Ratio
│   ├── drift_monitor.py       # Rullande AUC/hit-rate mot realiserade utfall
│   └── regime.py              # Bull/bear/sidledes-klassificering + prestanda-breakdown
└── main.py                    # Kör hela pipeline
```

## Snabbstart
```bash
pip install -r requirements.txt
python main.py --tickers AAPL MSFT NVDA TSLA --start 2010-01-01
```

## Flöde
1. `data_loader.py`  → hämtar OHLCV veckodata via yfinance
2. `feature_engineering.py` → bygger ~40 features
3. `lgbm_model.py`   → walk-forward CV, feature importance
4. `lstm_model.py`   → sekvensmodell på samma features
5. `ensemble.py`     → kombinerar, Kelly-sizing, alla outputs
6. `backtester.py`   → realistisk backtest med kostnader, drawdown-guard, korrelations- och sektorfilter
7. `bootstrap.py`    → block bootstrap-CI + Probabilistic/Deflated Sharpe Ratio på backtestresultatet
8. `regime.py`       → bryter ner backtestens avkastning per marknadsregim (bull/bear/sidledes)
9. `drift_monitor.py` → rullande AUC/hit-rate mot realiserade utfall, flaggar modell-drift

## Risk management
- **Drawdown-guard**: total exponering de-levereras linjärt när portföljens drawdown
  passerar `DRAWDOWN_GUARD_THRESHOLD`, ner till `DRAWDOWN_GUARD_FLOOR` vid 2x tröskeln.
- **Korrelationsfilter**: positioner med rullande avkastningskorrelation över
  `MAX_PAIRWISE_CORRELATION` slås ihop så att Kelly-budgeten inte satsas flera
  gånger på samma underliggande rörelse.
- **Sektorexponeringsgräns**: vikter skalas ner proportionellt inom en sektor
  om sektorns totalvikt överstiger `MAX_SECTOR_EXPOSURE`. Sektormappningen
  (`config.SECTOR_MAP`) är statisk för `DEFAULT_TICKERS` – lägg till nya
  tickers där om universet utökas.

## Robusthet
`bootstrap.py` kör en block bootstrap på backtestens veckoavkastningar och
skattar konfidensintervall (p5/p50/p95) för Sharpe, CAGR och Max Drawdown,
samt Probabilistic Sharpe Ratio (sannolikheten att den sanna Sharpe-kvoten
är positiv, givet skevhet/kurtosis i avkastningarna). Körs automatiskt
efter `print_statistics()` i `main.py`.

**Deflated Sharpe Ratio**: om fler än en strategi/parameteruppsättning
testats innan den slutgiltiga valdes, deflaterar `--n-trials N` PSR mot
`expected_max_sharpe(N)` (Bailey & López de Prado) i stället för mot 0,
så att konfidensen i resultatet sjunker i proportion till hur mycket
"data snooping" som skett.

## Marknadsregimer
`regime.py` klassificerar varje vecka som bull/bear/sidledes utifrån ett
SMA-trend-proxy på ett likaviktat indexsnitt över universumet, och
bryter ner strategins Sharpe/avg-return/win-rate per regim. Syftet är
att avgöra om edge:n håller över olika marknadsklimat eller är
koncentrerad till en specifik period (t.ex. en lång bull-trend) – måtten
är inte path-dependent CAGR/Max Drawdown eftersom regimperioderna är
diskontinuerliga i tid.

## Frusen holdout
`config.HOLDOUT_WEEKS` (default 104v) reserverar de sista veckorna av
historiken: LightGBM och LSTM tränas aldrig på den perioden. `main.py`
skriver ut separata statistikblock för "DEV" (tränad på) och "HOLDOUT"
(frusen, aldrig sedd) så att man kan se om resultaten i dev-perioden
generaliserar eller om de bara speglar overfitting på walk-forward-CV:n.

## Modell-drift
`drift_monitor.py` jämför `prob_up`/`pred_signal` mot de realiserade
`target_signal`/`target_return`-kolumnerna (samma definition som
modellen tränades mot) i ett rullande fönster (`DRIFT_WINDOW_WEEKS`) och
flaggar när rullande AUC faller under `DRIFT_AUC_FLOOR`. Mest relevant
vid upprepad/live-körning – i en ren historisk backtest visar den om
edge:n hållit konsekvent över tid eller koncentrerats till en period.

## Likviditet & marknadsimpact
`backtester.py` begränsar varje enskild orderflöde till
`LIQUIDITY_MAX_ADV_FRACTION` av tickerns genomsnittliga dollarvolym
(`LIQUIDITY_LOOKBACK_WEEKS`, strikt historisk för att undvika lookahead),
och lägger på en sqrt-marknadsimpact-term (`MARKET_IMPACT_COEF * sqrt(trade
/ ADV)`, tak `MARKET_IMPACT_MAX`) ovanpå courtage/slippage. Detta gör
kostnaderna mer realistiska för positioner som är stora relativt
tickerns handelsvolym.

## Datakvalitet / corporate actions
`data_loader.py` flaggar (men korrigerar inte automatiskt) veckoavkastningar
över `SUSPICIOUS_JUMP_THRESHOLD` i magnitud – sådana hopp kan vara legitima
nyheter eller artefakter av ojusterade splits/utdelningar och bör
granskas manuellt innan modellen tränas på dem.

## Kända begränsningar
- **Survivorship bias**: `yfinance` saknar avnoterade/uppköpta bolag, vilket
  gör att backtestresultat tenderar att överskatta verklig avkastning. Innan
  resultat tas på allvar för riktigt kapital bör en point-in-time-korrekt
  källa (Polygon.io, Norgate Data) ersätta `data_loader.py`.
