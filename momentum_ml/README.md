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
│   ├── backtester.py          # Walk-forward backtest (kostnader, DD-guard, korrelations-/sektorfilter)
│   ├── bootstrap.py           # Block bootstrap + Probabilistic Sharpe Ratio
│   └── drift_monitor.py       # Rullande AUC/hit-rate mot realiserade utfall
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
7. `bootstrap.py`    → block bootstrap-CI + Probabilistic Sharpe Ratio på backtestresultatet
8. `drift_monitor.py` → rullande AUC/hit-rate mot realiserade utfall, flaggar modell-drift

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

## Modell-drift
`drift_monitor.py` jämför `prob_up`/`pred_signal` mot de realiserade
`target_signal`/`target_return`-kolumnerna (samma definition som
modellen tränades mot) i ett rullande fönster (`DRIFT_WINDOW_WEEKS`) och
flaggar när rullande AUC faller under `DRIFT_AUC_FLOOR`. Mest relevant
vid upprepad/live-körning – i en ren historisk backtest visar den om
edge:n hållit konsekvent över tid eller koncentrerats till en period.

## Kända begränsningar
- **Survivorship bias**: `yfinance` saknar avnoterade/uppköpta bolag, vilket
  gör att backtestresultat tenderar att överskatta verklig avkastning. Innan
  resultat tas på allvar för riktigt kapital bör en point-in-time-korrekt
  källa (Polygon.io, Norgate Data) ersätta `data_loader.py`.
