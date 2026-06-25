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
│   └── backtester.py          # Walk-forward backtest
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
6. `backtester.py`   → realistisk backtest med kostnader
