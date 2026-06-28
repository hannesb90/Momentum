"""
config.py – Alla parametrar för momentum ML-systemet.
Ändra här; rör inte modellkoden.
"""

# ── Data ─────────────────────────────────────────────────────────────────────
DEFAULT_TICKERS = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "META", "JPM"]
START_DATE      = "2010-01-01"
END_DATE        = None          # None = idag
INTERVAL        = "1wk"        # veckodata

# Minsta historik (veckor) för att en ticker ska tas med. Modellen tränas på
# POOLAD tvärsnittsdata, så en aktie behöver bara nog historik för sina egna
# features (~52v ROC + FORWARD_WEEKS label + buffert) – INTE en hel egen
# träningsperiod. Tidigare krävdes TRAIN_WINDOW_WEEKS+LSTM+FORWARD (=290v ≈
# 5,6 år), vilket uteslöt nästan alla små-/nyintroducerade bolag och kapade
# universumet till ~120. 78v ≈ 1,5 år släpper in dem. OBS: tickers med <36v
# får ingen LSTM-prediktion (men väl LGBM). Sänk inte under ~60v.
MIN_HISTORY_WEEKS = 78

# ── Feature-fönster (veckor) ─────────────────────────────────────────────────
MOMENTUM_WINDOWS   = [4, 8, 13, 26, 52]
VOLATILITY_WINDOWS = [4, 13, 26]
VOLUME_WINDOWS     = [4, 13]
EMA_PAIRS          = [(8, 21), (13, 34), (21, 55)]
ADX_PERIOD         = 14
DONCHIAN_WEEKS     = 20         # utbrottsfönster (pris bryter N-veckors high/low)

# Klassisk "12-1"-momentum: formation 52v, hoppa över senaste 4v (skip-month).
# Skip-fönstret är avgörande – på 1-4 veckors sikt dominerar REVERSAL (aktier som
# just stigit rekylerar), medan trenden 12→1 mån håller i sig (Jegadeesh-Titman).
MOM_FORMATION_WEEKS = 52
MOM_SKIP_WEEKS      = 4

# ── Targets ──────────────────────────────────────────────────────────────────
# Prognoshorisont. VIKTIGT: 4v låg i reversal-regimen – modellen lärde sig då att
# undvika just de aktier som trendar (t.ex. SAAB under försvarsrusningen fick
# aldrig prob_up över basnivån). Klassisk momentum håller 1-3 mån; 13v (≈kvartal)
# ligger i momentum-regimen. Styr även REBALANCE_WEEKS och EMBARGO_WEEKS nedan.
FORWARD_WEEKS      = 13         # Förutsägningshorisont (≈ kvartal, momentum-regim)
RETURN_THRESHOLD   = 0.05       # >5% = positiv klass (endast om XS_TARGET=False)

# Tvärsnitts-target (cross-sectional). Det gamla absoluta targetet ("går DENNA
# aktie upp >RETURN_THRESHOLD på 4v?") gör att positiv klass nästan försvinner i
# svaga perioder → prob_up kollapsar mot basfrekvensen för alla bolag (platt,
# AUC ~0.50, ingen rangordning). Topp-N behöver i stället en RELATIV fråga:
# "kommer aktien att SLÅ de andra bolagen?". Med XS_TARGET=True sätts positiv
# klass = aktier vars framåtavkastning ligger i toppen (>= XS_TARGET_QUANTILE) av
# universumets fördelning SAMMA vecka. Klassbalansen blir då ~konstant oavsett
# marknadsregim och prob_up får verklig tvärsnitts-dispersion = meningsfull edge
# att vikta på. (Jegadeesh-Titman-anda: relativ styrka, inte absolut nivå.)
XS_TARGET          = True
XS_TARGET_QUANTILE = 0.67       # topp-tertil = positiv klass

# Rebalanseringsfrekvens (veckor). Modellen förutsäger FORWARD_WEEKS framåt, så
# att rebalansera VARJE vecka på en 4-veckorssignal innebär att man ständigt
# reagerar på brus och churnar portföljen – på en koncentrerad topp-N-portfölj
# blir veckovis omsättning ~40%+/vecka, vilket äts upp av courtage/spread/impact
# (mätt: ~8–20 %-enheter/år kostnadsdrag). Vi håller därför innehaven en hel
# prognoshorisont och rebalanserar var FORWARD_WEEKS:e vecka. Marknadsfiltret
# kan ändå de-riska däremellan (se backtester.run).
REBALANCE_WEEKS    = FORWARD_WEEKS  # = 4

# Asymmetrisk exit: behåll de långsamma kvartals-INGÅNGARNA (rid vinnare), men
# tillåt en SNABB utgång mellan rebalanseringar om ett innehavs trend bryts
# (priset faller under sitt EXIT_SMA_WEEKS-glidande medel). "Sälj när bolaget är
# klart" gjort robust – vi kallar inte toppen, vi reagerar på bruten trend.
# Kapital som frigörs ligger i kontanter tills nästa schemalagda rebalans (då det
# roteras in i nästa topp-N-namn). Default AV: skyddar den bevisade baslinjen –
# slå på och A/B-testa (predict-only) innan den görs permanent. På syntetisk
# slumpdata över-exitade den (korsar SMA hela tiden); på riktiga trender utlöses
# den långt mer sällan, men måste mätas på riktig holdout först.
ASYMMETRIC_EXIT    = False
EXIT_SMA_WEEKS     = 20

# Delisting-detektor: om en ticker saknar ny kurs i mer än så här många veckor
# (relativt universumets senaste datum) tolkas bolaget som avnoterat och tas bort
# – ska inte visas som aktuell signal eller störa beräkningarna. Se
# data_loader.filter_active_universe.
STALE_MAX_WEEKS    = 4

# ── Walk-forward backtest ────────────────────────────────────────────────────
TRAIN_WINDOW_WEEKS = 260        # ~5 år träning
VAL_WINDOW_WEEKS   = 52         # ~1 år validering
TEST_STEP_WEEKS    = 13         # Rulla 1 kvartal åt gången
# Purge/embargo mot dataläckage: targets är FORWARD_WEEKS framåtavkastning, så
# de sista veckornas labels i ett fönster överlappar nästa fönsters features.
# Vi rensar (purgar) de sista EMBARGO_WEEKS observationerna ur varje segment
# innan nästa börjar. Se walk_forward_splits och López de Prado (purged CV).
EMBARGO_WEEKS      = FORWARD_WEEKS  # = 4, en hel label-horisont

# ── Resursbegränsningar (för svagare hårdvara, t.ex. Raspberry Pi) ───────────
# Antal CPU-trådar att avsätta för LightGBM/PyTorch-träning. Lämna minst en
# kärna ledig åt API-servern om de körs på samma maskin samtidigt.
# Sätts via env-variabeln MOMENTUM_TRAINING_THREADS (se deploy/), annars
# None = låt biblioteken välja själva (default, använder alla kärnor).
import os as _os
_env_threads = _os.environ.get("MOMENTUM_TRAINING_THREADS")
NUM_TRAINING_THREADS = int(_env_threads) if _env_threads else None

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
    "num_threads":      NUM_TRAINING_THREADS or 0,  # 0 = LightGBM väljer själv
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

# ── Köptröskel (data-driven) ─────────────────────────────────────────────────
# pred_signal = 1 om prob_up > BUY_THRESHOLD. Istället för en hårdkodad 0.5
# kan tröskeln sökas fram på dev-perioden (in-sample) och valideras på den
# frusna holdouten – se backtest/threshold_opt.py och flaggan
# --optimize-threshold (default på). Detta löser "nästan alltid i kontanter"-
# problemet: en välkalibrerad P(>5% på 4v) passerar sällan 0.5, så portföljen
# blir sällan investerad. Låt datan välja nivån istället för att gissa.
BUY_THRESHOLD = 0.5   # legacy: används ej i alltid-investerad topp-N-design
# Selektivitetsgolv: en aktie är kandidat till portföljen bara om dess
# förväntade avkastning (över FORWARD_WEEKS) överstiger detta. Default 0.0 =
# håll vilket bolag som helst med icke-negativ förväntan → "alltid investerad"
# (topp-N fyller portföljen). HÖJ för färre/starkare innehav och mer kontanter
# i svaga perioder (t.ex. 0.015 för att kräva marginal över round-trip-kostnad).
MIN_EXPECTED_RETURN = 0.0
# Kandidatrutnät som söks igenom. Varje testad nivå är ett "trial" som
# deflaterar Deflated Sharpe Ratio (multipeltestning) – se --n-trials.
BUY_THRESHOLD_GRID = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]
# Mål som maximeras vid sökningen: 'sharpe' (default, riskjusterat),
# 'cagr' (rå avkastning – överanpassar lättare) eller 'calmar' (CAGR/|maxDD|).
THRESHOLD_OBJECTIVE = "sharpe"

# ── Positionssizing (Kelly) ───────────────────────────────────────────────────
KELLY_FRACTION     = 0.25      # Fractional Kelly (25%)
MAX_POSITION       = 0.20      # Max 20% per position
MIN_POSITION       = 0.01      # Min 1% (annars ej handel)
MAX_POSITIONS      = 10        # Max antal samtidiga positioner
# Conviction-tilt vs likavikt (krympning). prob_up mäter P(+5% på 4v) och är
# naturligt <0.5 för nästan alla bolag, så absolut Kelly blir 0 för de flesta
# och portföljen kollapsar till de få namn som råkar ha hög prob_up – inte en
# diversifierad topp-N. Vi krymper därför conviction-vikten mot likavikt:
# vikt_i = (1-blend)*likavikt + blend*kelly_normaliserad. 0.0 = ren likavikt,
# 1.0 = ren conviction. Likavikt är notoriskt svårslaget och krympning minskar
# estimeringsbrus (Ledoit-Wolf-anda) – varje vald aktie får alltid en
# meningsfull vikt så vi håller N diversifierade innehav.
CONVICTION_BLEND   = 0.5

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

# Bolagsnamn per ticker. Fylls från sweden_universe.csv m.fl. i main.py
# (config.NAME_MAP.update(...)) så signals.csv kan exportera ett namn-fält –
# frontend visar namn + ticker i listor/aktievyn och kan söka på bolagsnamn.
NAME_MAP: dict = {}

# Kanoniska kategorilistor för sektor/cap-tier som modell-features
# (features/feature_engineering.py: sector_code, cap_tier_code). Fast
# ordning krävs eftersom träning och prediktion körs i separata processer
# (se main.py) – koderna måste vara identiska mellan de körningarna.
# "Okänd"/"Unknown" sist fångar allt som inte matchar (t.ex. om universet
# utökas till nya marknader senare).
SECTOR_CATEGORIES = [
    "Communication Services", "Consumer Discretionary", "Consumer Staples",
    "Energy", "Financials", "Health Care", "Industrials",
    "Information Technology", "Technology", "Materials", "Real Estate",
    "Utilities", "Fond", "Okänd",
]
CAP_TIER_CATEGORIES = [
    "Mega Cap", "Large Cap", "Mid Cap", "Small Cap", "Micro Cap", "Nano Cap",
    "Fond", "Okänd",
]

# ── Modell-drift-monitoring ───────────────────────────────────────────────────
DRIFT_WINDOW_WEEKS = 26     # rullande fönster för realiserad prestanda
DRIFT_AUC_FLOOR    = 0.52   # under denna rullande AUC -> flagga
DRIFT_MIN_SAMPLES  = 20     # minsta antal observationer för att räkna AUC

# ── Likviditet & marknadsimpact ───────────────────────────────────────────────
LIQUIDITY_LOOKBACK_WEEKS   = 13     # fönster för genomsnittlig dollarvolym
LIQUIDITY_MAX_ADV_FRACTION = 0.10   # max andel av ADV som handlas per vecka
MARKET_IMPACT_COEF         = 0.10   # skala på sqrt(trade_value/ADV)-termen
MARKET_IMPACT_MAX          = 0.05   # tak för impact-kostnad per trade (5%)

# Likviditetsberoende halv-spread (bid/ask). Fast courtage+slippage (0.1%+0.1%)
# är rimligt för Large Cap men optimistiskt för tunt handlade små-/microbolag
# där spreaden lätt är 1-3%. Vi lägger på en halv-spread som växer när en
# akties omsättning (ADV) ligger under en referensnivå, klippt till ett tak.
# Detta gör att den utökade småbolagsavkastningen inte blir illusorisk.
SPREAD_ADV_REF = 5_000_000   # ADV (lokal valuta/vecka) där spreaden är "normal"
SPREAD_MIN     = 0.0005      # 0.05% halv-spread för mycket likvida bolag
SPREAD_MAX     = 0.020       # 2% tak för de tunnaste namnen

# ── Universumfilter (förfilter innan feature engineering/träning) ────────────
# Tunt handlade bolag drar ner datakvalitet och ökar beräkningstid utan att
# tillföra mycket – filtreras bort innan resten av pipelinen körs. Tröskeln
# är i lokal valuta (t.ex. SEK för .ST-tickers, USD för US-tickers).
UNIVERSE_MIN_AVG_TURNOVER       = 100_000     # min genomsnittlig omsättning/vecka
UNIVERSE_LIQUIDITY_LOOKBACK_WEEKS = 26         # fönster för det måttet

# ── Index-benchmark (visuell jämförelse i appen) ──────────────────────────────
# OMXS30 = vad en bred publik faktiskt köper passivt (kap-viktat, 30 största).
# Vi använder XACT-OMXS30-ETF:en (finns i universumet) som kursproxy och visar
# den som en linje mot strategins portfölj. OBS: detta är en ANNAN, oftast mildare
# ribba än vårt likaviktade köp-och-behåll-benchmark (som alfa/beta räknas mot).
INDEX_BENCHMARK_TICKER = "XACT-OMXS30.ST"
INDEX_BENCHMARK_LABEL  = "OMXS30 (XACT)"

# ── Corporate actions / datakvalitet ──────────────────────────────────────────
SUSPICIOUS_JUMP_THRESHOLD = 0.60    # flagga veckoavkastning över denna magnitud

# ── Teknisk-analys-filter (valbart, slås på med --ta-filter gate|score) ───────
# Ett bekräftelselager ovanpå modellens köpsignaler, byggt på TA-features som
# redan beräknas i feature_engineering.py (ingen extra datahämtning). Två lägen:
#   gate  – hård grind: köpsignalen nollas om villkoren inte uppfylls
#   score – mjuk viktning: position_size skalas med andelen uppfyllda villkor
# Stränghet (--ta-strictness) väljer vilka villkor som krävs:
#   loose    – bara pris > SMA52
#   moderate – trend (ADX) + riktning upp + pris > SMA52   (default)
#   strict   – alla ovan + nära 52v-högsta + ej överköpt
TA_FILTER_STRICTNESS = "moderate"
TA_FILTER_ADX_MIN    = 20.0   # minsta ADX för att räkna trenden som "riktig"
TA_FILTER_HIGH52_MIN = 0.90   # high52_ratio: hur nära 52v-högsta (1.0 = vid högsta)
TA_FILTER_BB_MAX     = 1.0    # bb_position-tak: över detta = för överköpt

# ── Marknadsregimer ───────────────────────────────────────────────────────────
REGIME_SMA_WEEKS = 26       # trend-proxy för bull/bear/sidledes-klassificering

# ── Marknadsfilter (long-only exponerings-overlay) ────────────────────────────
# Long-only momentum bär full marknadsrisk. I stället för att blanka (som vi
# medvetet INTE gör) drar vi ner portföljens bruttoexponering mot kontanter när
# den breda marknaden är svag, och kör fullt i stark trend. Detta är klassisk
# trendfilter-/dual-momentum-logik (Faber; Antonacci) och sänker både beta och
# björnmarknads-drawdowns utan blankning. Faktorn multipliceras på målvikterna;
# resten hamnar i kontanter automatiskt. Använder samma bull/bear/sidledes-
# klassificering som regim-fliken (backtest/regime.py).
MARKET_FILTER_EXPOSURE = {"bull": 1.0, "sideways": 0.6, "bear": 0.25}

# ── Frusen holdout ────────────────────────────────────────────────────────────
HOLDOUT_WEEKS = 104         # ~2 år som modellen aldrig tränas på

# ── Misc ─────────────────────────────────────────────────────────────────────
RANDOM_SEED        = 42
CACHE_DIR          = "cache"
RESULTS_DIR        = "results"

# ── Segment (separata modeller per storleksklass) ─────────────────────────────
# Två SEPARATA modeller, en per storleksgrupp, så att tvärsnitts-rangordningen
# sker inom jämförbara bolag (en stabil storbolagstrend drunknar annars i
# småbolagens större kast – uppmätt: SAAB föll från prob_up 1.0 till 0.35 när
# universumet blandades). Varje segment tränas/backtestas för sig och skrivs till
# egen results-mapp; frontend togglar mellan dem som två identiska vyer.
# market_cap = nivåer som tas med, results_dir = var output hamnar.
# max_positions/conviction_blend per segment (sizing-svep 2026-06, tune_sizing.py):
#   large – fler innehav/högre conviction försämrade (alfa -1.7% -> -3.2%); 10
#           namn @ blend 0.5 var optimum (= globala default). Redan maxad skörd.
#   small – fler innehav (20) diversierar småbolagens högre idiosynkratiska risk
#           och lyfter alfan från -0.6% till ~+0.6-1.0% (in-sample). OBS: holdout
#           fortfarande negativ + survivorship-flattrad → ej pålitlig än.
SEGMENTS = {
    "large": {"label": "Storbolag", "market_cap": ["Large Cap", "Mid Cap"], "results_dir": "results",
              "max_positions": 10, "conviction_blend": 0.5},
    "small": {"label": "Småbolag",  "market_cap": ["Small Cap"],            "results_dir": "results/small",
              "max_positions": 20, "conviction_blend": 0.5},
}
DEFAULT_SEGMENT = "large"
