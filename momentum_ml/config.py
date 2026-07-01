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

# Ablation: lista feature-namn som ska UTESLUTAS ur modellens indata genom hela
# pipelinen (se features/feature_engineering.py). Default tom = full modell.
# Ablationen (tune_ablation.py LOGO) visade att modellen är överbyggd – varje
# borttagen grupp höjde capture-spreaden, och "tidig_entry" var aktivt skadlig
# på holdouten (−5.1% → +1.5%). För att re-validera den borttagningen med FULLA
# pipelinen (LGBM+LSTM+tröskel), avkommentera och kör en omträning:
#   DROP_FEATURES = ["donchian_pos", "breakout_nw", "roc_accel_4w", "pullback"]
DROP_FEATURES: list = []

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

# Rebalanseringsläge:
#   "calendar" – rebalansera var REBALANCE_WEEKS:e vecka (bevisad baslinje).
#   "event"    – HÄNDELSESTYRD rotation: tekniken avgör hålltiden, inte kalendern.
#                Sälj ett innehav så snart trenden bryts (kurs < EXIT_SMA) ELLER det
#                faller ur behåll-zonen (topp KEEP_BAND_MULT×N i prob_up-rank); fyll
#                lediga platser samma vecka med nästa kvalificerade bolag. Stabila
#                vinnare rids orört (no-trade-band), så omsättningen hålls nere trots
#                veckovis utvärdering. Default calendar tills event A/B-testats.
REBALANCE_MODE     = "calendar"
KEEP_BAND_MULT     = 2.0    # håll ett innehav så länge det är inom topp 2N (hysteres)

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
# FASTA prior-vikter för LGBM/LSTM-blandningen. Dynamisk rolling-Sharpe-viktning
# är INTE implementerad (den gamla `ROLLING_SHARPE_WINDOW` + update_weights-stub
# var ett dött löfte och är borttagna). Se models/ensemble.py.
ENSEMBLE_LGBM_WEIGHT = 0.6
ENSEMBLE_LSTM_WEIGHT = 0.4

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

# Sizing-läge: hur vikten FÖRDELAS bland de N namn som rangordnats in (urvalet
# sker alltid på prob_up – tvärsnitts-edgen). A/B-bart i tune_sizing.py:
#   "conviction"  – tilt ∝ Kelly-conviction (default, bevisad baslinje).
#   "inverse_vol" – tilt ∝ 1/volatilitet (risk-paritet; lika riskbidrag per namn,
#                   dämpar att högvolatila namn dominerar – Sortino-hygien).
# Bägge krymps mot likavikt med CONVICTION_BLEND. Samma N, olika vikt → isolerar
# sizing-effekten rent. A/B 2026-06 (tune_sizing.py large): inverse_vol slog
# conviction på HELA rutnätet vid blend 0.5 – CAGR 14.0→14.3%, Sharpe 1.07→1.10,
# alfa −1.7→−1.4%, holdout 0.0→+0.7%. Adopterat.
SIZING_MODE = "inverse_vol"

# Momentum-kvalitetsgrind + villkorad kontant (experiment, default AV). Adresserar
# en konstruktionsmiss: alltid-investerad topp-N tvingar ~100% i N namn ÄVEN när
# bara några få har äkta momentum → de få vinnarna späds ut av "minst dåliga"
# namn (motsatsen till kap-viktning, som låter vinnaren bli stor). Med grinden på
# hålls bara namn med abs. 12-1-momentum > MOMENTUM_GATE_MIN, och investerad andel
# blir k/N (k = antal som klarar grinden) → kontanter byggs när momentum är ont om.
# Ändrar bara sizing (ej modellen) → A/B utan omträning via tune_gate.py. Behåll
# bara om holdout/alfa förbättras utan att kontant-draget äter mer än det räddar.
# ADOPTERAT 2026-06-28 (tune_gate.py large, tröskel-svep): grinden vid >10% slog
# baslinjen på VARJE mått och var en robust platå (5–10% alla bättre, topp vid 10%,
# faller vid 15% – inte en holdout-spik): CAGR 12.4→14.3%, Sharpe 1.12→1.25, alfa
# −3.3→−1.4%, MaxDD −19.9→−17.6%, holdout +1.3→+4.4%. (Fortfarande negativ alfa mot
# likavikt – en reell förbättring, inte ett index-slag.) OBS: validerat LGBM-only
# som inverse_vol/vol-target; nästa fulla träning bekräftar med LSTM.
# PER-SEGMENT: grinden hjälpte STOR men STJÄLPTE SMÅ på holdouten → den styrs nu
# av gate_enabled/gate_min i SEGMENTS (stor: på, små: av). Värdena här är bara
# fallback/default om man kör utan --segment.
MOMENTUM_GATE_ENABLED = True
MOMENTUM_GATE_MIN     = 0.10  # kräver >10% abs. 12-1-momentum för att hållas
# Vad gör vi när FÅ namn klarar grinden? Två filosofier (A/B i tune_gate.py):
#   "cash"        – defensivt: investerad andel = k/N, resten kontant (mindre risk
#                   när momentum är ont om).
#   "concentrate" – aggressivt: satsa ~100% i de få som trendar (som kap-viktning
#                   som låter vinnarna bli stora). Per-namn-taket höjs då till
#                   MOMENTUM_GATE_CONCENTRATE_CAP. OBS: hög koncentration = hög
#                   idiosynkratisk risk (en vinstvarning på ett namn slår hårt) –
#                   för en bred publik är "cash" det ansvarsfulla default-valet;
#                   låt Sharpe/MaxDD i svepet avgöra.
MOMENTUM_GATE_MODE            = "cash"
MOMENTUM_GATE_CONCENTRATE_CAP = 0.34   # per-namn-tak i concentrate (0.5 = tillåt 100% i 2 namn)

# ── Target-vol-overlay (Barroso & Santa-Clara, "Managing the risk of momentum") ─
# Skalar portföljens BRUTTOEXPONERING kontinuerligt mot en mål-volatilitet i
# stället för det grova bull/sideways/bear-marknadsfiltret: exp = min(target_vol /
# realiserad_vol, tak). Litteraturens mest robusta momentum-förbättring – sänker
# drawdowns/höjer Sharpe genom att dra ner inför turbulens. Long-only & ingen
# hävstång → taket är 1.0 (overlayn skalar bara NER mot kontanter, aldrig upp).
# OBS: realiserad vol mäts på portföljvärdet (efter ev. nedskalning) – en
# pragmatisk proxy med viss återkoppling; långt lookback dämpar oscillation.
# A/B 2026-06 (tune_voltarget.py large): mål 10% var bäst – Sharpe 1.07→1.16,
# Sortino 1.29→1.60, MaxDD −28.2→−20.6%, holdout 0.0→+0.7% (kostar CAGR
# 14.0→13.4%). Adopterat: för en bred publik är 7,6 pp mindre drawdown värt det.
VOL_TARGET_ENABLED        = True
VOL_TARGET_ANNUAL         = 0.10   # mål: 10% annualiserad portföljvol
VOL_TARGET_LOOKBACK_WEEKS = 13     # fönster för realiserad vol
VOL_TARGET_MAX_LEVERAGE   = 1.0    # tak (1.0 = ingen hävstång, bara de-risking)

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

# ── Orderläggning (limit för köpsignaler) ─────────────────────────────────────
# En köpsignal ska inte jagas hur högt som helst – gapar aktien upp innan du
# hinner köpa är edgen delvis borta. Varje aktuell köpsignal får därför en
# inköpsgräns = referenskurs × (1 + BUY_LIMIT_TOLERANCE). Lägg en LIMITORDER på
# den nivån; fyller priset inte ≤ gränsen avstår du (nästa rebalans fångar den
# annars). Litet tal eftersom edgen sitter på kvartalshorisont, inte intradag.
BUY_LIMIT_TOLERANCE = 0.015   # köp: max 1.5% över referenskurs
# Symmetrisk sälj-limit: dumpa inte ett innehav du vill ut ur in i ett tillfälligt
# gap-ned – lägg en sälj-LIMITORDER på minst referenskurs × (1 - SELL_LIMIT_TOLERANCE).
SELL_LIMIT_TOLERANCE = 0.015  # sälj: minst 1.5% under referenskurs

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

# ── Alt-data: MFN-pressmeddelanden + LLM-sentiment (validate-first) ────────────
# Hypotes: tvärsnittsmomentum på enbart pris har tappat sin edge i algo-eran
# (era_analysis.py visade att försprånget mot OMXS30 var uppvärmnings-artefakt).
# En durabel edge kräver alt-data som algon inte trivialt arbitrerar bort:
# TONEN i bolagens egna regulatoriska pressmeddelanden (PEAD-anda – marknaden
# under-reagerar på nyhetston och driften håller i sig veckor framåt).
#
# MFN.se (Modular Finance) distribuerar nordiska regulatoriska PM och har ett
# ARKIV med publiceringstidsstämpel → point-in-time text utan look-ahead, vilket
# är exakt vad en ärlig backtest kräver. Vi poängsätter varje PM med Claude
# (sentiment + materialitet) och testar OOS (2016+) om signalens capture-spread
# är positiv INNAN vi bygger in den i modellen. Engångskostnad ~hundralapp
# (Haiku 4.5 + Batch-API), löpande drift ~ören/vecka.
#
# OBS: körs på Pi:n (molncontainern når varken mfn.se eller Yahoo). MFN:s exakta
# endpoint/JSON-form ska verifieras med `mfn_fetch.py probe <query>` på Pi:n
# innan massiv hämtning – se altdata/README.md.
MFN_BASE_URL        = "https://mfn.se"
MFN_LANG            = "sv"          # hämta svenska PM (MFN har även "en")
MFN_REQUEST_PAUSE_S = 0.5          # paus mellan anrop (snäll mot MFN)
MFN_MAX_PAGES       = 20           # max feed-sidor per bolag (500 PM/sida; stoppar vid START_DATE)
MFN_MAX_BODY_CHARS  = 8000         # klipp PM-text innan LLM (håller token-kostnad nere)
MFN_CACHE_DIR       = "cache/mfn"   # rå-PM cachas här (JSON per ticker)

# LLM-sentiment (Anthropic). API-NYCKELN läses ur miljövariabeln ANTHROPIC_API_KEY
# – lägg ALDRIG nyckeln i koden/repot. Haiku räcker för klassificering; höj till
# Sonnet bara om A/B på ~200 PM visar att Haiku missar nyanser i svensk PM-text.
SENTIMENT_MODEL     = "claude-haiku-4-5"
SENTIMENT_USE_BATCH = True          # Batch-API = -50% för historisk massa-poängsättning
SENTIMENT_CACHE_DIR = "cache/sentiment"  # poäng cachas per PM-id (kör aldrig om samma PM)
SENTIMENT_MAX_TOKENS = 400

# Backtest av sentiment-signalen: aggregera ett innehavs PM-ton i ett bakåtfönster
# och mät framåtavkastning (capture-spread, mirror av capture_analysis.py).
# Kvalitativ fundamental sållning (quality_screener.py) – diskretionär tratt, EJ
# backtestbar. Läser bolagens MFN-rapporter/PM och låter Claude poängsätta en
# kvalitativ checklista (10-årings-test, global ambition, moat, ledning/skin-in-
# the-game, säljkultur, adresserbar marknad, IR). Sonnet för djupare omdöme än
# Haiku (klassificering vs bedömning). ~$0.02/bolag → hela microcap-universumet
# några dollar. Hård regel i prompten: bedöm ENBART det som står i texten.
QUALITY_MODEL          = "claude-sonnet-4-6"
QUALITY_CACHE_DIR      = "cache/quality"
QUALITY_MAX_CHARS      = 24000      # underlag/bolag (senaste rapport + några PM) – rymmer resultaträkningen
QUALITY_EXCLUDE_SECTORS = ["Health Care"]   # undvik medtech/pharma (binärt lotteri)
QUALITY_MARKET_CAP     = ["Small Cap", "Micro Cap", "Nano Cap"]   # tidiga, oupptäckta bolag

# ── Nasdaq Nordic (gratis, auktoritativt börsvärde – kompletterar Yahoo) ──────
# Yahoo saknar aktieantal/börsvärde för många microcaps → screenerns "okänd"-hink.
# Nasdaqs egen datafeed har det gratis. Vi hämtar hela Stockholmsbörsen i några
# anrop och fyller BARA de börsvärden Yahoo missade (Yahoo har företräde).
# XML-datafeed (reverse-engineerad, körs på Pi:n – molncontainern når den ej).
NASDAQ_ENDPOINT     = "http://www.nasdaqomxnordic.com/webproxy/DataFeedProxy.aspx"
NASDAQ_EXCHANGE     = "NMF"
# Stockholmsmarknader att svepa (Large/Mid/Small/First North). Verifiera/utöka
# via `probe` – varje id ger en delmängd. Kända start-id:n från publika klienter.
NASDAQ_MARKETS      = ["L:3303", "L:10214"]
# Vilka instrument-attribut som begärs (numeriska koder → namngivna XML-attribut).
NASDAQ_INST_FIELDS  = "0,87,1,2,5,37,4,20,21,23,24,33,34,97,129,98,72"
# Attributnamn i <inst>-svaret. SÄTTS KORREKT EFTER `probe` (då ser vi de riktiga
# namnen/värdena). Tomt mcap → räkna börsvärde som aktieantal × senaste kurs.
NASDAQ_ATTR_MCAP    = ""            # direkt börsvärde om feeden ger det
NASDAQ_ATTR_SHARES  = ""            # antal aktier
NASDAQ_ATTR_PRICE   = ""            # senaste kurs
NASDAQ_ATTR_SYMBOL  = "nm"         # kortnamn/symbol att matcha mot vår ticker
NASDAQ_ATTR_ISIN    = "isin"
NASDAQ_REQUEST_PAUSE_S = 0.5

SENTIMENT_LOOKBACK_DAYS = 7         # PM publicerade senaste veckan räknas in i veckans signal
SENTIMENT_OOS_START     = "2016"    # rent OOS-fönster (samma som era_analysis.py)
# Poängsätt bara PM från detta datum (en buffert före OOS-start). Vi backtestar
# enbart 2016+, så att betala för 2010-2015 års PM är bortkastat. Sänk vid behov.
SENTIMENT_SCORE_FROM    = "2015-09-01"

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
# index_ticker/index_label per segment: storbolag jämförs mot OMXS30, men SMÅBOLAG
# ska jämföras mot ett SMÅBOLAGSINDEX (XACT Svenska Småbolag, finns i universumet)
# – inte mot OMXS30 (storbolag). Båda ETF:erna återinvesterar utdelning och hämtas
# auto_adjust=True → totalavkastning på BÅDA sidor (rättvis jämförelse, se nedan).
SEGMENTS = {
    # gate_enabled/gate_min per segment: momentum-kvalitetsgrinden hjälpte STORBOLAG
    # på holdouten (#17: holdout +1.3→+4.4%) men STJÄLPTE SMÅBOLAG på holdouten
    # (−2.3→−3.8%, trots bättre helperiod – sannolikt småbolagsmomentum-reversal i
    # holdout-fönstret). Domaren = holdouten → grind PÅ för stor, AV för små.
    # Stor-segmentet = Large+Mid → jämför mot en BRED Stockholms-ribba, inte top-30
    # (OMXS30). XACT Sverige (totalavkastning, utdelnings­återinvesterande ETF) är
    # apples-to-apples. INTE OMXSPI rakt av – det är ett KURSINDEX (utan utdelning)
    # och vår portfölj är totalavkastning → orättvist smickrande. Verifiera att
    # XACT Sverige spårar den breda benchmarken (OMXSB-cap GI), inte OMXS30.
    "large": {"label": "Storbolag", "market_cap": ["Large Cap", "Mid Cap"], "results_dir": "results",
              "max_positions": 10, "conviction_blend": 0.5,
              "index_ticker": "XACT-SVERIGE.ST",  "index_label": "OMX Sthlm bred (XACT Sverige)",
              "gate_enabled": True,  "gate_min": 0.10},
    "small": {"label": "Småbolag",  "market_cap": ["Small Cap"],            "results_dir": "results/small",
              "max_positions": 20, "conviction_blend": 0.5,
              "index_ticker": "XACT-SMABOLAG.ST", "index_label": "Svenska Småbolag (XACT)",
              "gate_enabled": False, "gate_min": 0.10},
}
DEFAULT_SEGMENT = "large"
