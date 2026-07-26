"""
features/feature_engineering.py – Bygger ~40 tekniska features per ticker.

Feature-kategorier:
  1. Momentum / ROC
  2. Trend (EMA-kors, ADX)
  3. Volatilitet (ATR, realized vol, vol-ratio)
  4. Volym (OBV, vol-ratio, A/D)
  5. Pris-nivå (52v high/low ratio, BB-position)
  6. Cross-sectional (relativ styrka, percentilrank)
  7. Targets (framåtblickande, läcker ej in i träning)
"""

import hashlib
import numpy as np
import pandas as pd
from typing import Dict, Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from backtest import pipeline_diagnostics as _diag


# ─────────────────────────────────────────────────────────────────────────────
# Hjälpfunktioner
# ─────────────────────────────────────────────────────────────────────────────

def _roc(series: pd.Series, n: int) -> pd.Series:
    """Rate of Change: (p_t / p_{t-n}) - 1"""
    return series.pct_change(n)


def _ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()


def _wilder(series: pd.Series, n: int) -> pd.Series:
    """
    Wilders utjämning (RMA) = EMA med alpha = 1/n. Detta är den smoothing
    Welles Wilder definierade för ATR/ADX/DI – INTE ett enkelt rullande medel.
    Ett `.rolling(n).mean()` ger en annan (snabbare, fönsterbegränsad) serie som
    inte matchar standard-ADX i litteratur/andra verktyg. ewm(alpha=1/n) ger den
    rekursiva Wilder-serien.
    """
    return series.ewm(alpha=1.0 / n, adjust=False).mean()


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int) -> pd.Series:
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low  - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    return _wilder(tr, n)


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14):
    """Returnerar (ADX, +DI, -DI) med Wilders smoothing (standarddefinitionen)."""
    up   = high.diff()
    down = -low.diff()
    plus_dm  = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)

    atr_n = _atr(high, low, close, n)   # Wilder-utjämnad TR
    plus_di  = 100 * _wilder(pd.Series(plus_dm,  index=close.index), n) / atr_n
    minus_di = 100 * _wilder(pd.Series(minus_dm, index=close.index), n) / atr_n

    dx  = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di)).fillna(0)
    adx = _wilder(dx, n)
    return adx, plus_di, minus_di


def _obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


def _ad_line(high: pd.Series, low: pd.Series,
             close: pd.Series, volume: pd.Series) -> pd.Series:
    clv = ((close - low) - (high - close)) / (high - low).replace(0, np.nan)
    return (clv * volume).cumsum()


# ─────────────────────────────────────────────────────────────────────────────
# Huvud-funktion: features per ticker
# ─────────────────────────────────────────────────────────────────────────────

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Input:  DataFrame med kolumner [Open, High, Low, Close, Volume]
    Output: DataFrame med alla features + targets (NaN i början, ej framåtläckage)
    """
    feat = pd.DataFrame(index=df.index)
    o, h, l, c, v = df["Open"], df["High"], df["Low"], df["Close"], df["Volume"]

    # ── 1. Momentum / ROC ────────────────────────────────────────────────────
    for w in config.MOMENTUM_WINDOWS:
        feat[f"roc_{w}w"] = _roc(c, w)

    # Klassisk "12-1" momentum: avkastning från ~12 mån sedan till ~1 mån sedan
    # (hoppar över senaste MOM_SKIP_WEEKS för att undvika kortsiktig reversal).
    # Det mest evidensbackade momentum-måttet (Jegadeesh-Titman) – skip-fönstret
    # är nyckeln till att fånga uthålliga trender i stället för spikar som rekylerar.
    feat["mom_12_1"] = c.shift(config.MOM_SKIP_WEEKS) / c.shift(config.MOM_FORMATION_WEEKS) - 1

    # Skew och kurtosis av veckoavkastning (13v)
    wr = c.pct_change()
    feat["ret_skew_13w"]  = wr.rolling(13).skew()
    feat["ret_kurt_13w"]  = wr.rolling(13).kurt()

    # ── Edge-tillägg: reversal + vol-skalat momentum ─────────────────────────
    # 1-veckas reversal: veckoavkastning har NEGATIV autokorrelation på 1v-horisont
    # (kortsiktig rekyl efter en spik). Låter modellen lära sig "stark trend + svag
    # senaste vecka = bättre/billigare entry". Används också som råvara till
    # residual-momentum i add_cross_sectional.
    feat["ret_1w"] = wr
    # Vol-skalat (t-statistik-) momentum: avkastning PER ENHET RISK är en starkare
    # tvärsnitts-rankningssignal än rå avkastning (jämför äpplen med äpplen mellan
    # lugna large-caps och stökiga small-caps). 26v-momentum delat på annualiserad
    # 26v-vol – en dimensionslös t-stat-liknande kvot.
    feat["mom_tstat_26w"] = (c / c.shift(26) - 1) / (wr.rolling(26).std() * np.sqrt(52) + 1e-9)

    # ── 2. Trend (EMA-kors, ADX) ─────────────────────────────────────────────
    for fast, slow in config.EMA_PAIRS:
        ema_f = _ema(c, fast)
        ema_s = _ema(c, slow)
        feat[f"ema_cross_{fast}_{slow}"] = (ema_f - ema_s) / c   # normaliserat avstånd
        feat[f"ema_slope_{fast}w"]       = ema_f.pct_change(4)    # lutning

    adx, plus_di, minus_di = _adx(h, l, c, config.ADX_PERIOD)
    feat["adx"]       = adx
    feat["di_diff"]   = (plus_di - minus_di) / 100               # +DI - -DI normaliserat
    feat["adx_trend"] = (plus_di > minus_di).astype(int)         # 1=upptrend

    # ── 3. Volatilitet ────────────────────────────────────────────────────────
    for w in config.VOLATILITY_WINDOWS:
        feat[f"rvol_{w}w"] = wr.rolling(w).std() * np.sqrt(52)   # annualiserad

    feat["atr_norm"] = _atr(h, l, c, 14) / c                     # ATR% av pris
    feat["vol_ratio"] = feat["rvol_4w"] / feat["rvol_26w"]       # kort/lång vol

    # Bollinger Band position
    sma20 = c.rolling(20).mean()
    std20 = c.rolling(20).std()
    feat["bb_position"] = (c - sma20) / (2 * std20)              # -1..+1

    # ── 4. Volym ─────────────────────────────────────────────────────────────
    for w in config.VOLUME_WINDOWS:
        feat[f"vol_ratio_{w}w"] = v / v.rolling(w).mean()        # relativ volym

    obv = _obv(c, v)
    feat["obv_roc_4w"]  = _roc(obv, 4)
    feat["obv_roc_13w"] = _roc(obv, 13)

    ad = _ad_line(h, l, c, v)
    feat["ad_roc_4w"] = _roc(ad, 4)

    # Dollarvolym, absolut nivå – grund för cross-sectional likviditetsrank
    # (add_cross_sectional). Modellen ser idag ingen skillnad mellan en
    # djupt likvid large-cap och en tunn micro-cap förutom via
    # vol_ratio_*w (relativ mot egen historik) – det säger inget om hur
    # likvid aktien är i absoluta termer jämfört med resten av universumet.
    feat["dollar_vol_13w"] = (c * v).rolling(13).mean()

    # ── 5. Pris-nivå ─────────────────────────────────────────────────────────
    feat["high52_ratio"] = c / h.rolling(52).max()               # nära 52v-high?
    feat["low52_ratio"]  = c / l.rolling(52).min()               # över 52v-low?
    feat["price_vs_sma52"] = c / c.rolling(52).mean() - 1

    # ── 5b. Tidiga entry-signaler (utbrott, acceleration, pullback) ──────────
    # De övriga momentum-måtten (roc_*, high52_ratio) belönar redan etablerade
    # trender och fångar därför rörelsen sent. Här läggs signaler som tänder
    # nära BÖRJAN av en rörelse, så modellen kan lära sig att gå in tidigare.
    dwin   = config.DONCHIAN_WEEKS
    high_d = h.rolling(dwin).max()
    low_d  = l.rolling(dwin).min()
    rng_d  = (high_d - low_d).replace(0, np.nan)
    # Position i N-veckors pris-kanal: 0 = vid kanalbotten, 1 = vid kanaltopp.
    feat["donchian_pos"] = (c - low_d) / rng_d
    # Utbrott: pris bryter över föregående N-veckors högsta (nytt högsta = ny trend).
    feat["breakout_nw"]  = (c > high_d.shift(1)).astype(int)
    # Acceleration ("momentum av momentum"): ökar takten? Fångar inflektionen,
    # inte bara nivån – positivt innan ROC hunnit bli högt.
    feat["roc_accel_4w"] = feat["roc_4w"] - feat["roc_4w"].shift(4)
    # Pullback i upptrend: längre trend upp (pris > SMA52) men kortsiktigt
    # nedtryckt (låg Bollinger-position) = köp dippen, tidigare/billigare entry.
    feat["pullback"] = ((feat["price_vs_sma52"] > 0) & (feat["bb_position"] < -0.5)).astype(int)

    # ── 6. Targets (LÄCKER EJ – shift bakåt) ─────────────────────────────────
    fwd = config.FORWARD_WEEKS
    fwd_ret = c.shift(-fwd) / c - 1                               # framåtavkastning

    feat["target_return"]   = fwd_ret                             # regression
    feat["target_signal"]   = (fwd_ret > config.RETURN_THRESHOLD).astype(int)  # klassifikation
    feat["target_prob_pos"] = np.nan                              # fylls av modellen

    # Vissa kvoter (volym=0, flat pris -> std=0, OBV/AD-linje som korsar noll)
    # kan ge inf istället för NaN - normalisera så nedströms NaN-hantering
    # (dropna/fillna) täcker även dessa fall.
    feat = feat.replace([np.inf, -np.inf], np.nan)

    # ── Rensa bort rader med för många NaN ───────────────────────────────────
    # (behåll rader som har tillräckligt med historik för alla features)
    min_valid = 0.70
    thresh = int(len(feat.columns) * min_valid)
    feat = feat.dropna(thresh=thresh)

    return feat


# ─────────────────────────────────────────────────────────────────────────────
# Cross-sectional features (kräver hela universum)
# ─────────────────────────────────────────────────────────────────────────────

def add_cross_sectional(all_features: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """
    Lägger till cross-sectional features:
      - rs_4w, rs_13w, rs_26w : relativ styrka vs universum (mean)
      - rank_4w, rank_26w     : percentilrank i universum
    """
    # Samla ROC per datum
    roc_4  = pd.DataFrame({t: f["roc_4w"]  for t, f in all_features.items()})
    roc_13 = pd.DataFrame({t: f["roc_13w"] for t, f in all_features.items()})
    roc_26 = pd.DataFrame({t: f["roc_26w"] for t, f in all_features.items()})
    dvol   = pd.DataFrame({t: f["dollar_vol_13w"] for t, f in all_features.items()})

    universe_mean_4  = roc_4.mean(axis=1)
    universe_mean_26 = roc_26.mean(axis=1)
    dvol_rank = dvol.rank(axis=1, pct=True)   # 0=tunnast, 1=mest likvid i universumet just det datumet
    rank_13   = roc_13.rank(axis=1, pct=True) # percentilrank på 13v-momentum, per datum

    # ── Residual-momentum (Blitz-Huij-Martens) ───────────────────────────────
    # Rå momentum bär stor marknads-/beta-exponering: högmomentum-korgen är ofta
    # bara "hög beta i en uppgång", vilket kraschar hårt i sättningar (momentum-
    # crashes). Residual-momentum tar bort marknadsdelen: regressera varje akties
    # veckoavkastning mot marknaden (universums-medel) via rullande 52v-beta, och
    # ranka momentum på RESIDUALEN. Ger en jämnare, mindre crash-benägen signal.
    # Allt kausalt: beta och residual-summan använder bara data t.o.m. datum t,
    # och momentum-fönstret hoppar över senaste 4v (shift(4)) som vanligt momentum.
    rets = pd.DataFrame({t: f["ret_1w"] for t, f in all_features.items()})
    mkt  = rets.mean(axis=1)                                  # likaviktad marknadsproxy
    mkt_var = mkt.rolling(52).var()
    resid_mom = {}
    for ticker in all_features:
        r = rets[ticker]
        beta = r.rolling(52).cov(mkt) / (mkt_var + 1e-9)
        resid = r - beta * mkt                                # marknads-neutraliserad avkastning
        # 48v residual-momentum (hoppar senaste 4v), skalat på residualens vol.
        # BUGFIX: aritmetisk summa av veckovisa residual-avkastningar är bara en
        # förstaordnings-approximation av 48 veckors FAKTISK kumulativ avkastning -
        # kan avvika markant från riktig compounding när residualerna är stora.
        # Geometrisk kedjning (produkt av (1+r), minus 1) är den korrekta 48-veckors
        # kumulativa residualavkastningen. OBS: modellen är tränad på DEN GAMLA
        # (arimetisk summa) skalan - kräver omträning innan denna variant faktiskt
        # syns i signalerna (samma disciplin som config.DROP_FEATURES-kommentaren).
        num = (1.0 + resid).shift(4).rolling(48).apply(np.prod, raw=True) - 1.0
        den = resid.rolling(52).std() * np.sqrt(52) + 1e-9
        resid_mom[ticker] = num / den

    for ticker, feat in all_features.items():
        feat["rs_4w"]   = feat["roc_4w"]  - universe_mean_4
        feat["rs_13w"]  = feat["roc_13w"] - roc_13.mean(axis=1)
        feat["rs_26w"]  = feat["roc_26w"] - universe_mean_26
        feat["rank_4w"] = roc_4.rank(axis=1, pct=True)[ticker]
        feat["rank_26w"]= roc_26.rank(axis=1, pct=True)[ticker]
        feat["liquidity_rank"] = dvol_rank[ticker]
        # Rank-rotation: hur aktiens relativa rank ändrats senaste 4v (per-aktie-
        # analog till sektorns "Kapital in"). Positivt = klättrar i universumet,
        # dvs. relativ styrka tilltar – ofta ett tidigt rotations-tecken.
        feat["rank_change_4w"] = rank_13[ticker] - rank_13[ticker].shift(4)
        feat["resid_mom"] = resid_mom[ticker].reindex(feat.index)

    # ── Tvärsnitts-target (relativ rangordning) ──────────────────────────────
    # Sätt klassificerings-targetet RELATIVT: positiv klass = aktier vars
    # framåtavkastning (target_return) ligger i toppen av universumet samma vecka.
    # Detta ersätter det absoluta ">RETURN_THRESHOLD"-targetet (se config.XS_TARGET).
    # Ingen lookahead utöver den befintliga forward-fönstret: rankningen för
    # datum t använder bara avkastningar som realiseras i t:s forward-fönster,
    # rankade mot samtidiga bolag.
    if getattr(config, "XS_TARGET", False):
        fwd_ret = pd.DataFrame({t: f["target_return"] for t, f in all_features.items()})
        # percentilrank per datum (rad). min_periods via count: rankas bara när
        # tillräckligt många bolag har en realiserad avkastning den veckan.
        pr = fwd_ret.rank(axis=1, pct=True)
        valid = fwd_ret.notna().sum(axis=1) >= 5      # kräv minst 5 bolag för en meningsfull rank
        q = float(config.XS_TARGET_QUANTILE)
        for ticker, feat in all_features.items():
            sig = (pr[ticker] >= q).astype(float)
            # ogiltigt (saknad avkastning eller för få bolag) -> NaN, droppas i to_model_df
            sig[fwd_ret[ticker].isna() | ~valid] = np.nan
            feat["target_signal"] = sig.reindex(feat.index)

    return all_features


# ── Persistent per-ticker features-cache (2026-07-22) ───────────────────────
# build_all_features byggde tidigare om HELA feature-matrisen (2010->idag,
# ~500 bolag) från grunden VARJE NATT, trots att build_features() är en REN
# funktion av en enda tickers prisserie - historiska rader ändras aldrig
# (bortsett från sällsynta Yahoo-revideringar, som cachen nedan ändå fångar
# korrekt via datahashen). Den enda cachen som fanns innan (main.py:s
# _load_feature_cache) var bara giltig INOM en enda körning och raderades
# explicit när den var klar - noll nytta natt till natt.
#
# MEDVETET REN MEMOISERING, INTE INKREMENTELL UPPDATERING: cachen lagras per
# ticker, nyckel = hash(prisdata) + hash(feature-kod+config). Ändras EN rad i
# prisserien (ny vecka, eller en Yahoo-revidering av gammal data) blir hela
# hashen annorlunda och HELA den tickerns features byggs om från grunden -
# aldrig en delvis/splitsad uppdatering. Det gör cachen trivial att resonera
# om korrekthet för (samma indata → samma cachade utdata, garanterat av att
# build_features är en ren funktion) i utbyte mot att inte vara maximalt
# snål - ett enskilt ändrat bolag kostar en full ombyggnad av DEN tickern,
# inte bara den nya veckan. Given att flertalet bolag har OFÖRÄNDRAD
# veckodata natt till natt (ny bar bara en gång/vecka) täcker det ändå
# merparten av besparingen.
#
# KORREKTHETS-SÄKRING: kod-hashen omfattar HELA feature_engineering.py +
# HELA config.py:s källkod - INTE bara en manuellt underhållen versions-
# sträng. Varje ändring i endera filen (nya features, ändrade fönster,
# bugfixar) ogiltigförklarar AUTOMATISKT alla cachade rader nästa körning,
# utan att någon behöver komma ihåg att bumpa ett versionsnummer. Medvetet
# överinvaliderande (en helt orelaterad config-ändring tvingar också en
# ombyggnad) snarare än att riskera en tyst, felaktig cache-träff i en
# modell som handlar riktiga pengar.
_FEATURE_SRC_HASH: Optional[str] = None


def _feature_code_hash() -> str:
    """KRITISK LÄRDOM (2026-07-24, #31): käll-TEXT-hashen ensam räcker inte.
    Ett skript som muterar config.FORWARD_WEEKS i runtime (horisonttester)
    fick cache-TRÄFF på features vars target_return var byggd med det GAMLA
    värdet - tyst fel horisont i träningen, och omvänt förgiftades
    produktionscachen när ett sådant skript byggde om. Nyckeln inkluderar
    därför numera de RUNTIME-värden som påverkar den cachade artefaktens
    innehåll (target-horisonten + target-definitionen), utöver källtexten."""
    global _FEATURE_SRC_HASH
    if _FEATURE_SRC_HASH is None:
        src = Path(__file__).read_text() + Path(config.__file__).read_text()
        _FEATURE_SRC_HASH = hashlib.sha1(src.encode()).hexdigest()[:16]
    runtime = (f"|fwd={config.FORWARD_WEEKS}|xs={getattr(config, 'XS_TARGET', False)}"
               f"|q={getattr(config, 'XS_TARGET_QUANTILE', None)}"
               f"|thr={getattr(config, 'RETURN_THRESHOLD', None)}")
    return hashlib.sha1((_FEATURE_SRC_HASH + runtime).encode()).hexdigest()[:16]


def _price_data_hash(df: pd.DataFrame) -> str:
    h = pd.util.hash_pandas_object(df, index=True).values
    return hashlib.sha1(h.tobytes()).hexdigest()[:16]


def _per_ticker_cache_dir() -> Path:
    p = Path(config.anchor("cache/features_by_ticker"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def build_all_features(data: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """
    Kör feature engineering för alla tickers + cross-sectional.
    """
    print("[Features] Bygger features...")
    code_hash = _feature_code_hash()
    cache_dir = _per_ticker_cache_dir()
    all_feat = {}
    n_cached = 0
    for ticker, df in data.items():
        try:
            data_hash = _price_data_hash(df)
            cache_path = cache_dir / f"{ticker}.pkl"
            feat = None
            if cache_path.exists():
                try:
                    saved = pd.read_pickle(cache_path)
                    if saved.get("code_hash") == code_hash and saved.get("data_hash") == data_hash:
                        feat = saved["features"]
                except Exception:  # noqa: BLE001 - korrupt/ofullständig cache, bygg om
                    feat = None
            if feat is not None:
                n_cached += 1
            else:
                feat = build_features(df)
                try:
                    pd.to_pickle(
                        {"code_hash": code_hash, "data_hash": data_hash, "features": feat},
                        cache_path,
                    )
                except Exception as e:  # noqa: BLE001 - cachen är en optimering, aldrig kritisk
                    print(f"  [WARN] Kunde inte skriva features-cache för {ticker} (icke-kritiskt): {e}")
            all_feat[ticker] = feat
        except Exception as e:
            print(f"  [WARN] {ticker}: feature error: {e}")

    all_feat = add_cross_sectional(all_feat)

    # Nedkonvertera float64 -> float32 för hela dicten (halverar RAM). Gäller
    # även prediktionsprocessen som håller hela universumet i minnet samtidigt.
    for feat in all_feat.values():
        float_cols = feat.select_dtypes(include=["float64"]).columns
        if len(float_cols):
            feat[float_cols] = feat[float_cols].astype("float32")

    print(f"[Features] Klar. {len(all_feat)} tickers ({n_cached} från cache), "
          f"{next(iter(all_feat.values())).shape[1]} features.")
    _diag.record_universe_stage("build_all_features", list(all_feat.keys()))
    return all_feat


def _category_code(value: Optional[str], categories: list) -> int:
    """
    Ordinal kod för en kategori utifrån en fast lista (se config.py
    SECTOR_CATEGORIES/CAP_TIER_CATEGORIES). Fast lista krävs eftersom
    träning och prediktion körs i separata processer (main.py) – koderna
    måste vara identiska mellan körningarna. Okänt/saknat värde får sista
    kategorins kod ("Okänd").
    """
    if value in categories:
        return categories.index(value)
    return len(categories) - 1


def attach_categorical_features(
    all_features: Dict[str, pd.DataFrame],
    sector_map: Optional[Dict[str, str]] = None,
    cap_tier_map: Optional[Dict[str, str]] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Lägger till sector_code/cap_tier_code (ordinal-kodade, fast lista i
    config.py) på varje tickers feature-DataFrame, INNAN to_model_df
    respektive prediktion – main.py använder samma all_features-dict för
    både träning (via to_model_df) och live-prediktion (direkt iteration),
    så kolumnerna måste finnas här för att båda vägarna ska se samma
    FEATURE_COLS. Saknas mappningarna sätts allt till "Okänd"-koden
    (bakåtkompatibelt, t.ex. för ad-hoc --tickers-körningar).
    """
    for ticker, feat in all_features.items():
        sector = (sector_map or {}).get(ticker)
        cap_tier = (cap_tier_map or {}).get(ticker)
        feat["sector_code"]   = _category_code(sector, config.SECTOR_CATEGORIES)
        feat["cap_tier_code"] = _category_code(cap_tier, config.CAP_TIER_CATEGORIES)
    return all_features


def _load_fundamentals_growth(
    segment: Optional[str] = None,
    prices: Optional[Dict[str, pd.DataFrame]] = None,
) -> pd.DataFrame:
    """
    Läser results*/fundamentals_from_mfn.csv + fundamentals_from_pdf.csv
    (byggda av altdata/mfn_fundamentals.py resp. altdata/mfn_pdf.py) och
    räknar ut YoY-tillväxt per rapport. _prior-kolumnen är enligt svensk
    IR-konvention SAMMA PERIOD FÖREGÅENDE ÅR (t.ex. Q1 2024:s revenue_prior
    = Q1 2023:s revenue) – tillväxten går alltså att räkna direkt ur en
    enskild rapportrad, ingen historisk hopslagning mot en tidigare rapport
    krävs.

    report_reaction_abn (kräver prices): rapportveckans ABNORMALA avkastning
    (aktiens avkastning minus en likaviktad marknadsproxy den veckan) – samma
    token-fria mått som altdata/pead.py använder som surprise-proxy. Ensam
    (rev_growth_yoy/eps_growth_yoy) berättar bara att förbättringen var
    verklig; kombinerat med denna kan modellen lära sig SKILJA mellan "redan
    prisat" (stark reaktion) och "marknaden missade det" (dämpad reaktion
    trots verklig förbättring) – validerat i tune_earnings_reaction_gap.py:
    IC 0.093/Q5-Q1 5.2% på 26v-holdouten för just den kombinationen, mot
    IC≈0 för tillväxten ensam på samma fönster. prices=None (t.ex. äldre
    anropare som inte skickar in prispanelen) ger NaN, som all annan saknad
    fundamentaldata.

    SAMMA rapport (pm_id) kan finnas i BÅDA CSV:erna med komplementära fält
    sedan PDF-backfillen blev nyckelfälts-medveten (mfn_pdf._KEY_FIELDS) –
    raderna slås ihop fältvis per pm_id (text-raden vinner där båda har
    värde), annars skulle merge_asof-källan få dubbla rader per rapport och
    slumpmässigt kunna välja pdf-raden utan revenue_prior → NaN-tillväxt
    trots känd data.

    ANDRA STEGET – altdata/avanza.py (fundamentals_from_avanza.csv, samma
    delade mekanism som value_screener._load_fundamentals, se altdata/
    fund_merge.fill_from_avanza): Avanza FYLLER bara NaN-celler i text-rader
    med samma (ticker, årsbärande period), eller läggs till som egna rader
    för perioder text-källorna helt saknar – text-rader slås ALDRIG ihop med
    varandra och behåller sina egna published-stämplar (kritiskt just HÄR:
    merge_asof:en nedströms är point-in-time, en hopblandad published-stämpel
    är en lookahead-läcka). Avanza saknar eps_prior helt (bara revenue_prior
    beräknas i avanza._build_rows), så eps_growth_yoy förblir NaN för rader
    som bara har Avanza-data – ärligt obedömbart, ingen gissning.

    Saknas filerna (inte genererade ännu, eller körs i en miljö utan
    altdata-pipelinen) returneras en tom DataFrame – growth-featuresen blir
    då bara NaN för alla tickers i stället för en krasch.
    """
    seg = config.SEGMENTS.get(segment) if segment else None
    seg = seg or config.SEGMENTS[config.DEFAULT_SEGMENT]
    results_dir = Path(config.anchor(seg["results_dir"]))

    frames = []
    for fname in ("fundamentals_from_mfn.csv", "fundamentals_from_pdf.csv"):
        p = results_dir / fname
        if p.exists():
            try:
                frames.append(pd.read_csv(p))
            except Exception:  # noqa: BLE001
                pass
    cols = ["ticker", "published", "rev_growth_yoy", "eps_growth_yoy", "report_reaction_abn", "div_growth_yoy"]

    if frames:
        text_df = pd.concat(frames, ignore_index=True)
        # Fältvis pm_id-sammanslagning (se docstring) – groupby().first() tar
        # första icke-NaN per kolumn; mfn-CSV:n läses först → text-raden vinner.
        if "pm_id" in text_df.columns:
            has_id = text_df["pm_id"].notna()
            merged = text_df[has_id].groupby("pm_id", as_index=False, sort=False).first()
            text_df = pd.concat([merged, text_df[~has_id]], ignore_index=True)
    else:
        text_df = pd.DataFrame()

    avanza_p = results_dir / "fundamentals_from_avanza.csv"
    avanza_df = pd.DataFrame()
    if avanza_p.exists():
        try:
            avanza_df = pd.read_csv(avanza_p)
        except Exception:  # noqa: BLE001
            pass

    from altdata.fund_merge import fill_from_avanza
    df = fill_from_avanza(text_df, avanza_df)
    if df.empty or "ticker" not in df.columns or "published" not in df.columns:
        return pd.DataFrame(columns=cols)

    df["published"] = pd.to_datetime(df["published"], errors="coerce", utc=True).dt.tz_localize(None)
    df = df.dropna(subset=["ticker", "published"])

    def _growth(value_col: str, prior_col: str) -> pd.Series:
        if value_col not in df.columns or prior_col not in df.columns:
            return pd.Series(np.nan, index=df.index)
        val, prior = df[value_col], df[prior_col]
        g = (val - prior) / prior.abs()
        g[(prior == 0) | prior.isna() | val.isna()] = np.nan
        return g

    df["rev_growth_yoy"] = _growth("revenue", "revenue_prior")
    # EPS: olika bolag rapporterar olika varianter (eps/eps_basic/eps_diluted)
    # – ta det som faktiskt finns, prioritetsordning eps > eps_basic > eps_diluted.
    eps_g = _growth("eps", "eps_prior")
    for value_col, prior_col in (("eps_basic", "eps_basic_prior"), ("eps_diluted", "eps_diluted_prior")):
        eps_g = eps_g.where(eps_g.notna(), _growth(value_col, prior_col))
    df["eps_growth_yoy"] = eps_g

    # Utdelningstillväxt YoY (validerad i tune_dividend_gap.py: holdout 26v
    # IC=0.059/Q5-Q1=+5.3% kombinerat med report_reaction_abn, konsekvent
    # med hela-perioden IC=0.191/+11.5% - klart över husets tröskel, till
    # skillnad från 8v-horisonten som INTE höll på holdout). dividend/
    # dividend_prior lagras som NEGATIVA tal (kassautflöde, samma konvention
    # som capex) - tillväxt räknas därför på abs(), INTE med _growth() ovan
    # (som hade gett fel tecken: en högre utdelning gör värdet MER negativt).
    if {"dividend", "dividend_prior"}.issubset(df.columns):
        div, div_prior = df["dividend"], df["dividend_prior"]
        div_g = (div.abs() - div_prior.abs()) / div_prior.abs()
        div_g[(div_prior == 0) | div_prior.isna() | div.isna()] = np.nan
        df["div_growth_yoy"] = div_g
    else:
        df["div_growth_yoy"] = np.nan

    # Rapportveckans abnormala avkastning (surprise-proxy, se docstring ovan).
    # Kräver prisdata – utan den (äldre anropare) blir kolumnen NaN, samma
    # ärliga "obedömbart"-hantering som resten av modulen.
    px = pd.DataFrame({t: d["Close"] for t, d in prices.items() if "Close" in d}).sort_index() if prices else pd.DataFrame()
    if not px.empty:
        rets = px.pct_change()
        market = rets.mean(axis=1)          # likaviktad marknadsproxy, samma som pead.py
        abn = rets.sub(market, axis=0)
        weeks = px.index

        def _reaction(t, published):
            if t not in abn.columns:
                return np.nan
            pos = weeks.searchsorted(published, side="left")
            return abn.iat[pos, abn.columns.get_loc(t)] if pos < len(weeks) else np.nan

        df["report_reaction_abn"] = [_reaction(t, p) for t, p in zip(df["ticker"], df["published"])]
    else:
        df["report_reaction_abn"] = np.nan

    before = df[cols]
    out = before.dropna(subset=["rev_growth_yoy", "eps_growth_yoy", "div_growth_yoy"], how="all")
    _diag.record_nan("load_fundamentals_growth:dropna_all_growth_nan", before, out,
                      cols=["rev_growth_yoy", "eps_growth_yoy", "div_growth_yoy", "report_reaction_abn"])
    return out.sort_values(["ticker", "published"])


# Tak/saknat-sentinel för days_since_report: allt äldre än ett år är "gammalt"
# – ingen extra information i 400 vs 700 dagar, och saknad rapporthistorik
# kodas som exakt detta värde (se attach_fundamentals_features).
_DAYS_SINCE_CAP = 365


def attach_fundamentals_features(
    all_features: Dict[str, pd.DataFrame],
    segment: Optional[str] = None,
    prices: Optional[Dict[str, pd.DataFrame]] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Kopplar in tillväxt-features (rev_growth_yoy, eps_growth_yoy,
    report_reaction_abn, div_growth_yoy) från MFN-rapporternas hårddata, samma mönster som
    attach_categorical_features() för sector/cap_tier – anropas EFTER
    build_all_features(), FÖRE to_model_df(), så samma all_features-dict
    används av både träning och live-prediktion.

    POINT-IN-TIME-KRITISKT: en given vecka får bara känna till rapporter
    som FAKTISKT var publicerade senast den veckan (backward as-of-join på
    'published', pd.merge_asof direction='backward') – annars läcker
    framtida rapportsiffror in i backtestet. 'published' är MFN:s faktiska
    publiceringstidsstämpel (inte räkenskapsårets slutdatum), så ingen
    extra säkerhetsmarginal behövs (till skillnad från den äldre, årsvisa
    results/fundamentals.csv i tune_fundamentals.py, som bara har
    räkenskapsår och därför måste GISSA ett publiceringsdatum).

    prices (samma dict som backtester.py/main.py redan håller i minnet,
    ticker → OHLCV-DataFrame): krävs för report_reaction_abn (rapportveckans
    abnormala avkastning, se _load_fundamentals_growth). Utan den blir bara
    den kolumnen NaN – rev_growth_yoy/eps_growth_yoy/days_since_report
    påverkas inte.

    Saknar en ticker helt rapportdata (inga träffar, eller filerna saknas)
    blir kolumnerna NaN genom hela historiken – konsekvent med hur alla
    andra FEATURE_COLS hanterar saknade värden (fillna(0) sker centralt i
    models/lgbm_model.py/lstm_model.py vid X-uppbyggnad, inte här).
    """
    fund = _load_fundamentals_growth(segment, prices=prices)
    by_ticker = ({tk: g.drop(columns="ticker") for tk, g in fund.groupby("ticker")}
                 if len(fund) else {})
    _alignment_totals = {"n": 0, "non_monday_dates": 0, "future_published_rows": 0}

    # days_since_report: dagar sedan senast kända rapport (PEAD-driftens
    # tidsaxel – den mest evidensbackade rapportsignalen). Köp-vaktens
    # blackout/färsk-logik använder redan detta, men den TRÄNADE modellen
    # såg det aldrig – nu blir det en riktig feature som modellen själv får
    # lära sig tröskla (färsk rapport → drift; gammal → ingen information).
    # SAKNAT värde kodas som _DAYS_SINCE_CAP (max-stale), INTE NaN: den
    # centrala fillna(0)-hanteringen i modellerna hade annars gjort "okänd
    # rapporthistorik" till "rapporterade idag" – motsatt betydelse.
    for ticker, feat in all_features.items():
        g = by_ticker.get(ticker)
        if g is None or g.empty:
            feat["rev_growth_yoy"] = np.nan
            feat["eps_growth_yoy"] = np.nan
            feat["report_reaction_abn"] = np.nan
            feat["div_growth_yoy"] = np.nan
            feat["days_since_report"] = float(_DAYS_SINCE_CAP)
            continue
        left = feat.index.to_frame(index=False, name="Date").sort_values("Date")
        g = g.sort_values("published")
        # pandas 2.x kan ge OLIKA datetime64-upplösningar (s/ms/us/ns) beroende
        # på källa: prisindexet ('Date', ur yfinance ELLER, sedan Avanza blev
        # prisdatakälla för NGM/Spotlight, altdata.avanza.fetch_chart_ohlcv:s
        # pd.to_datetime(ts, unit='ms')) kontra 'published' (ur pd.to_datetime
        # på MFN-textsträngar, vars upplösning pandas härleder ur strängens
        # egen precision). merge_asof KRÄVER numera identisk upplösning på
        # båda nycklarna (MergeError annars) – normalisera uttryckligen till
        # 'us' hellre än att lita på att källorna råkar matcha.
        left["Date"] = left["Date"].astype("datetime64[us]")
        g["published"] = g["published"].astype("datetime64[us]")
        joined = pd.merge_asof(left, g,
                                left_on="Date", right_on="published", direction="backward")
        joined = joined.set_index("Date")
        check = _diag.assert_date_alignment(joined)
        for key in _alignment_totals:
            _alignment_totals[key] += check[key]
        feat["rev_growth_yoy"] = joined["rev_growth_yoy"].reindex(feat.index)
        feat["eps_growth_yoy"] = joined["eps_growth_yoy"].reindex(feat.index)
        feat["report_reaction_abn"] = joined["report_reaction_abn"].reindex(feat.index)
        feat["div_growth_yoy"] = joined["div_growth_yoy"].reindex(feat.index)
        days = (joined.index.to_series() - joined["published"]).dt.days
        feat["days_since_report"] = (days.clip(upper=_DAYS_SINCE_CAP)
                                     .fillna(_DAYS_SINCE_CAP)
                                     .reindex(feat.index)
                                     .fillna(_DAYS_SINCE_CAP)
                                     .astype(float))
    if _alignment_totals["n"]:
        _diag.record_date_alignment("fundamentals_merge_asof", _alignment_totals)
    return all_features


def to_model_df(all_features: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Slår ihop alla tickers till ett long-format df med 'ticker'-kolumn.
    Droppar rader där target är NaN (sista FORWARD_WEEKS veckorna).

    Minne: float64-features dominerar RAM-användningen på hela Sverige-
    universumet (~656 tickers). Vi nedkonverterar därför float-kolumner till
    float32 PER ticker innan concat – det halverar topp-minnet utan att påverka
    modellen (LightGBM/precisionen klarar float32 gott). Viktigt för att hela
    universumet ska få plats i RAM på en 2GB-Pi.
    """
    frames = []
    for ticker, feat in all_features.items():
        tmp = feat.copy()
        float_cols = tmp.select_dtypes(include=["float64"]).columns
        if len(float_cols):
            tmp[float_cols] = tmp[float_cols].astype("float32")
        tmp["ticker"] = ticker
        frames.append(tmp)
    df = pd.concat(frames).sort_index()
    del frames
    before = df
    df = df.dropna(subset=["target_return", "target_signal"])
    _diag.record_nan("to_model_df:dropna_target", before, df,
                      cols=["target_return", "target_signal"])
    return df


FEATURE_COLS = [
    # Momentum
    *[f"roc_{w}w" for w in config.MOMENTUM_WINDOWS],
    "mom_12_1",
    "ret_skew_13w", "ret_kurt_13w",
    "ret_1w", "mom_tstat_26w",
    # Trend
    *[f"ema_cross_{f}_{s}" for f, s in config.EMA_PAIRS],
    *[f"ema_slope_{f}w" for f, _ in config.EMA_PAIRS],
    "adx", "di_diff", "adx_trend",
    # Volatilitet
    *[f"rvol_{w}w" for w in config.VOLATILITY_WINDOWS],
    "atr_norm", "vol_ratio", "bb_position",
    # Volym
    *[f"vol_ratio_{w}w" for w in config.VOLUME_WINDOWS],
    "obv_roc_4w", "obv_roc_13w", "ad_roc_4w",
    # Pris-nivå
    "high52_ratio", "low52_ratio", "price_vs_sma52",
    # Tidiga entry-signaler (utbrott, acceleration, pullback)
    "donchian_pos", "breakout_nw", "roc_accel_4w", "pullback",
    # Cross-sectional
    "rs_4w", "rs_13w", "rs_26w", "rank_4w", "rank_26w", "liquidity_rank",
    "rank_change_4w", "resid_mom",
    # Klassificering (ordinal-kodad, fast lista i config.py)
    "sector_code", "cap_tier_code",
    # Fundamenta (YoY-tillväxt ur MFN-rapporternas hårddata, point-in-time
    # as-of-kopplad – se attach_fundamentals_features()). NaN tills bolagets
    # första kända rapport, fillna(0) sker centralt i models/lgbm_model.py.
    "rev_growth_yoy", "eps_growth_yoy",
    # Rapportveckans abnormala avkastning (surprise-proxy, samma mått som
    # altdata/pead.py). Kombinerat med tillväxten ovan kan modellen skilja
    # "redan prisat" (stark reaktion) från "marknaden missade det" (dämpad
    # reaktion trots verklig förbättring) – validerat i
    # tune_earnings_reaction_gap.py, IC 0.093/Q5-Q1 +5.2% på 26v-holdouten
    # för just den kombinationen, mot IC≈0 för tillväxten ensam. fillna(0) =
    # neutral (ingen abnorm rörelse), en rimlig default till skillnad från
    # days_since_report nedan.
    "report_reaction_abn",
    # Utdelningstillväxt YoY (abs()-baserad, se _load_fundamentals_growth -
    # dividend/dividend_prior lagras som negativa kassautflödestal). Delar
    # report_reaction_abn ovan som reaktionsaxel - modellen lär sig samma typ
    # av gap som för rev/eps-tillväxten. Validerad i tune_dividend_gap.py:
    # holdout 26v IC=0.059/Q5-Q1=+5.3% (konsekvent med hela-perioden
    # 0.191/+11.5%), 8v höll INTE på holdout - bara 26v-relationen är
    # validerad. fillna(0) = neutral (ingen utdelningsförändring).
    "div_growth_yoy",
    # PEAD-tidsaxeln: dagar sedan senast kända rapport (takad vid 365; saknat
    # = 365, ALDRIG NaN – fillna(0) hade betytt "rapporterade idag").
    "days_since_report",
]

# Ablation: släpp namngivna features ur modellens INDATA genom HELA pipelinen
# (LGBM + LSTM + ensemble + main), så en ablations-vinnare kan re-valideras med
# fulla pipelinen, inte bara LGBM. Featuresen BERÄKNAS fortfarande (kolumnerna
# finns) – de matas bara inte till modellen. Default tom = full modell.
# Exempel (re-validera "utan tidig_entry"): sätt i config.py
#   DROP_FEATURES = ["donchian_pos", "breakout_nw", "roc_accel_4w", "pullback"]
# OBS: håll DROP_FEATURES tom när du kör tune_ablation.py (den styr urvalet själv).
_dropped = set(getattr(config, "DROP_FEATURES", []) or [])
if _dropped:
    FEATURE_COLS = [c for c in FEATURE_COLS if c not in _dropped]
