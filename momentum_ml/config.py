"""
config.py – Alla parametrar för momentum ML-systemet.
Ändra här; rör inte modellkoden.
"""

# ── Data ─────────────────────────────────────────────────────────────────────
DEFAULT_TICKERS = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "META", "JPM"]
START_DATE      = "2010-01-01"
END_DATE        = None          # None = idag
INTERVAL        = "1wk"        # veckodata

# ── Feature-fönster (veckor) ─────────────────────────────────────────────────
MOMENTUM_WINDOWS   = [4, 8, 13, 26, 52]
VOLATILITY_WINDOWS = [4, 13, 26]
VOLUME_WINDOWS     = [4, 13]
EMA_PAIRS          = [(8, 21), (13, 34), (21, 55)]
ADX_PERIOD         = 14

# ── Targets ──────────────────────────────────────────────────────────────────
FORWARD_WEEKS      = 4          # Förutsägningshorisont
RETURN_THRESHOLD   = 0.05       # >5% = positiv klass

# ── Walk-forward backtest ────────────────────────────────────────────────────
TRAIN_WINDOW_WEEKS = 260        # ~5 år träning
VAL_WINDOW_WEEKS   = 52         # ~1 år validering
TEST_STEP_WEEKS    = 13         # Rulla 1 kvartal åt gången

# ── LightGBM ─────────────────────────────────────────────────────────────────
LGBM_PARAMS = {
    "objective":        "binary",
    "metric":           ["binary_logloss", "auc"],
    "learning_rate":    0.05,
    "num_leaves":       63,
    "min_child_samples":50,
    "subsample":        0.8,
    "colsample_bytree": 0.8,
    "reg_alpha":        0.1,
    "reg_lambda":       1.0,
    "n_estimators":     1000,
    "early_stopping_rounds": 50,
    "verbose":          -1,
}

# ── LSTM ─────────────────────────────────────────────────────────────────────
LSTM_SEQUENCE_LEN  = 26        # 26 veckors historik per sample
LSTM_HIDDEN_SIZE   = 128
LSTM_NUM_LAYERS    = 2
LSTM_DROPOUT       = 0.2
LSTM_EPOCHS        = 100
LSTM_BATCH_SIZE    = 64
LSTM_LR            = 1e-3
LSTM_PATIENCE      = 15        # Early stopping

# ── Ensemble ─────────────────────────────────────────────────────────────────
ENSEMBLE_LGBM_WEIGHT = 0.6     # Startvikt; justeras av rolling Sharpe
ENSEMBLE_LSTM_WEIGHT = 0.4
ROLLING_SHARPE_WINDOW = 12     # Veckor för dynamisk viktning

# ── Positionssizing (Kelly) ───────────────────────────────────────────────────
KELLY_FRACTION     = 0.25      # Fractional Kelly (25%)
MAX_POSITION       = 0.20      # Max 20% per position
MIN_POSITION       = 0.01      # Min 1% (annars ej handel)
MAX_POSITIONS      = 10        # Max antal samtidiga positioner

# ── Backtest-kostnader ────────────────────────────────────────────────────────
COMMISSION         = 0.001     # 0.1% per trade
SLIPPAGE           = 0.001     # 0.1% slippage
INITIAL_CAPITAL    = 1_000_000 # 1 MSEK startkapital

# ── Risk management ───────────────────────────────────────────────────────────
DRAWDOWN_GUARD_THRESHOLD   = 0.15   # vid -15% drawdown, börja de-leverage
DRAWDOWN_GUARD_FLOOR       = 0.30   # min kvarvarande exponering vid 2x tröskeln (-30% DD)
MAX_PAIRWISE_CORRELATION   = 0.85   # över denna nivå räknas tickers som redundanta
CORRELATION_LOOKBACK_WEEKS = 26

# ── Robusthet (bootstrap) ─────────────────────────────────────────────────────
BOOTSTRAP_N_SIMS     = 1000
BOOTSTRAP_BLOCK_WEEKS = 4    # bevarar kort-sikt-autokorrelation vid resampling

# ── Sektorexponering ──────────────────────────────────────────────────────────
# OBS: statisk mappning för DEFAULT_TICKERS. Lägg till nya tickers här om
# universet utökas, annars hamnar de i "Okänd" och begränsas inte korrekt.
SECTOR_MAP = {
    "AAPL":  "Technology",
    "MSFT":  "Technology",
    "NVDA":  "Technology",
    "GOOGL": "Technology",
    "META":  "Technology",
    "TSLA":  "Consumer Discretionary",
    "AMZN":  "Consumer Discretionary",
    "JPM":   "Financials",
}
MAX_SECTOR_EXPOSURE = 0.40   # max 40% portföljvikt i en enskild sektor

# ── Modell-drift-monitoring ───────────────────────────────────────────────────
DRIFT_WINDOW_WEEKS = 26     # rullande fönster för realiserad prestanda
DRIFT_AUC_FLOOR    = 0.52   # under denna rullande AUC -> flagga
DRIFT_MIN_SAMPLES  = 20     # minsta antal observationer för att räkna AUC

# ── Likviditet & marknadsimpact ───────────────────────────────────────────────
LIQUIDITY_LOOKBACK_WEEKS   = 13     # fönster för genomsnittlig dollarvolym
LIQUIDITY_MAX_ADV_FRACTION = 0.10   # max andel av ADV som handlas per vecka
MARKET_IMPACT_COEF         = 0.10   # skala på sqrt(trade_value/ADV)-termen
MARKET_IMPACT_MAX          = 0.05   # tak för impact-kostnad per trade (5%)

# ── Corporate actions / datakvalitet ──────────────────────────────────────────
SUSPICIOUS_JUMP_THRESHOLD = 0.60    # flagga veckoavkastning över denna magnitud

# ── Marknadsregimer ───────────────────────────────────────────────────────────
REGIME_SMA_WEEKS = 26       # trend-proxy för bull/bear/sidledes-klassificering

# ── Frusen holdout ────────────────────────────────────────────────────────────
HOLDOUT_WEEKS = 104         # ~2 år som modellen aldrig tränas på

# ── Misc ─────────────────────────────────────────────────────────────────────
RANDOM_SEED        = 42
CACHE_DIR          = "cache"
RESULTS_DIR        = "results"
