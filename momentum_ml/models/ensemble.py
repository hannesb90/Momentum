"""
models/ensemble.py – Kombinerar LGBM + LSTM, Kelly-positionssizing.

Output per ticker per vecka:
  - prob_up      : ensemble sannolikhet
  - pred_signal  : Köp(1)/Sälj(0)
  - pred_return  : förväntad avkastning
  - position_size: Kelly-baserad storlek [0..MAX_POSITION]
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from models.ta_filter import ta_confirmation


# ─────────────────────────────────────────────────────────────────────────────
# Ensemble
# ─────────────────────────────────────────────────────────────────────────────

class MomentumEnsemble:
    """
    Kombinerar LGBM + LSTM med FASTA prior-vikter (LGBM 0.6 / LSTM 0.4).

    OBS: dynamisk rolling-Sharpe-viktning är INTE implementerad. Tidigare fanns en
    `update_weights`-stub (en no-op `pass`) + `config.ROLLING_SHARPE_WINDOW` som
    antydde att vikterna justerades löpande – det gjorde de aldrig. Vi tog bort
    det döda löftet hellre än att skeppa ovaliderad dynamik. Att låta vikterna
    variera med rullande Sharpe ÄR en möjlig framtida A/B, men den ändrar
    rangordningen och måste då valideras på holdouten (inte gratis).
    """

    def __init__(
        self,
        lgbm_weight: float = config.ENSEMBLE_LGBM_WEIGHT,
        lstm_weight:  float = config.ENSEMBLE_LSTM_WEIGHT,
    ):
        self.lgbm_w = lgbm_weight
        self.lstm_w  = lstm_weight
        self._history: list = []   # (date, lgbm_ret, lstm_ret, actual_ret)

    # ── Kombinera prediktioner ────────────────────────────────────────────────

    def combine(
        self,
        lgbm_preds: pd.DataFrame,
        lstm_preds: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """
        Slår ihop LGBM och (valfritt) LSTM-prediktioner.
        Gemensamma index (datum) används.
        """
        if lstm_preds is None or lstm_preds.empty:
            return lgbm_preds.copy()

        # Gemensamma datum
        idx = lgbm_preds.index.intersection(lstm_preds.index)
        lg  = lgbm_preds.loc[idx]
        ls  = lstm_preds.loc[idx]

        w_lg = self.lgbm_w / (self.lgbm_w + self.lstm_w)
        w_ls = self.lstm_w  / (self.lgbm_w + self.lstm_w)

        combined = pd.DataFrame(index=idx)
        combined["prob_up"]     = w_lg * lg["prob_up"]    + w_ls * ls["prob_up"]
        combined["pred_return"] = w_lg * lg["pred_return"] + w_ls * ls["pred_return"]
        # OBS kalibrering: LGBM:s prob_up är isotoniskt kalibrerad, LSTM:s är inte,
        # och MEDELVÄRDET av två sannolikheter är i allmänhet INTE kalibrerat. Den
        # blandade prob_up används därför främst för (a) RANGORDNING till topp-N –
        # robust mot monoton miss-kalibrering – och (b) som visat tal i appen (där
        # den är ungefärlig). pred_signal nedan (>0.5) skrivs ändå ÖVER i
        # build_full_output av den alltid-investerade topp-N-logiken, så själva
        # 0.5-tröskeln är inte aktiv. Att omkalibrera blandningen (eller kalibrera
        # LSTM före blandning) förbättrar mest det VISADE talet, inte rangordningen.
        combined["pred_signal"] = (combined["prob_up"] > 0.5).astype(int)
        return combined


# ─────────────────────────────────────────────────────────────────────────────
# Positionssizing – Kelly
# ─────────────────────────────────────────────────────────────────────────────

def kelly_position_size(
    prob_up:    float,
    pred_return: float,
    volatility:  float,
    win_loss_ratio: float = 1.5,
) -> float:
    """
    Fractional Kelly:
      f* = (p * b - q) / b  ×  KELLY_FRACTION
    
    Där:
      p = prob_up
      q = 1 - p
      b = win_loss_ratio (förväntad vinst / förlust)
    
    Skalas sedan med volatilitetsinvers för volatilitets-targeting.

    OBS: `win_loss_ratio` är en FAST prior (1.5), inte estimerad från modellens
    egen historiska vinst/förlust-kvot per prob_up-nivå – Kelly-storleken är
    därmed delvis schablon. Latent betydelse just nu: med config.SIZING_MODE=
    "inverse_vol" (adopterad) används `raw_kelly` INTE för viktningen (1/vol
    styr), så win_loss_ratio påverkar inte live-signalen. Den blir relevant först
    om conviction-läget återanvänds – estimera den då från data.
    """
    p = np.clip(prob_up, 0.01, 0.99)
    q = 1 - p
    b = max(win_loss_ratio, 0.1)

    kelly = (p * b - q) / b
    kelly = max(kelly, 0.0)                          # aldrig negativt (long-only)
    kelly *= config.KELLY_FRACTION                    # fractional Kelly

    # Volatilitetsskala: target 15% annualiserad vol
    if volatility > 0:
        vol_scale = 0.15 / max(volatility, 0.05)
        kelly *= vol_scale

    return float(np.clip(kelly, 0.0, config.MAX_POSITION))


def _apply_portfolio_constraints(weights: Dict[str, float]) -> Dict[str, float]:
    """
    Gemensam regeltillämpning för portföljvikter:
      - kasta bort vikter under MIN_POSITION
      - begränsa till MAX_POSITIONS (störst vikt vinner)
      - normalisera om total > 1
    """
    weights = {t: w for t, w in weights.items() if w >= config.MIN_POSITION}

    if len(weights) > config.MAX_POSITIONS:
        top = sorted(weights.items(), key=lambda x: x[1], reverse=True)[:config.MAX_POSITIONS]
        weights = dict(top)

    total = sum(weights.values())
    if total > 1.0:
        weights = {t: w / total for t, w in weights.items()}

    return weights


def _topn_invested_weights(
    raw: Dict[str, float],
    n: int = config.MAX_POSITIONS,
    max_position: float = config.MAX_POSITION,
) -> Dict[str, float]:
    """
    Alltid-investerad topp-N-allokering (tvärsnitts-momentum).

    I stället för en absolut tröskel som lämnar kapitalet i kontanter när få
    namn kvalar in, håller vi alltid de N starkaste kandidaterna och fyller
    ~100% av portföljen. `raw` är conviction per ticker (Kelly utifrån prob_up
    + volatilitet); vi tar topp-N, viktar PROPORTIONELLT mot conviction och
    normaliserar till summa 1.0 (fullinvesterad). Varje innehav kapas vid
    max_position och överskottet fördelas om. Kontanter uppstår sedan bara via
    marknadsfiltret (kris) och sektor-/korrelationsspärrarna i backtestern, inte
    för att "inget kvalade in".
    """
    if not raw:
        return {}
    top = dict(sorted(raw.items(), key=lambda kv: kv[1], reverse=True)[:n])
    total = sum(top.values())
    if total <= 0:
        return {}
    w = {t: v / total for t, v in top.items()}   # conviction-vikt, fullinvesterad

    # Kapa per innehav vid max_position och fördela om överskottet proportionellt.
    for _ in range(5):
        over = {t: v for t, v in w.items() if v > max_position + 1e-9}
        if not over:
            break
        excess = sum(v - max_position for v in over.values())
        for t in over:
            w[t] = max_position
        under = {t: v for t, v in w.items() if v < max_position - 1e-9}
        under_sum = sum(under.values())
        if under_sum <= 0:
            break
        for t in under:
            w[t] += excess * (w[t] / under_sum)
    return w


def build_portfolio_weights(
    signals: pd.DataFrame,
    feature_df: pd.DataFrame,   # behövs för volatilitet
    date: pd.Timestamp,
) -> Dict[str, float]:
    """
    Bygger portföljvikter för ett givet datum.

    signals: DataFrame med kolumner [ticker, prob_up, pred_return, pred_signal]
    Returnerar {ticker: weight}
    """
    long_signals = signals[signals["pred_signal"] == 1].copy()

    if long_signals.empty:
        return {}

    weights: Dict[str, float] = {}

    for _, row in long_signals.iterrows():
        ticker = row["ticker"]
        prob   = row["prob_up"]
        ret    = row["pred_return"]

        # Hämta volatilitet om tillgänglig
        try:
            vol = feature_df.loc[feature_df["ticker"] == ticker].loc[:date, "rvol_13w"].iloc[-1]
        except Exception:
            vol = 0.20   # default 20% annualiserad vol

        weights[ticker] = kelly_position_size(prob, ret, vol)

    return _apply_portfolio_constraints(weights)


# ─────────────────────────────────────────────────────────────────────────────
# Full output per datum/ticker
# ─────────────────────────────────────────────────────────────────────────────

def build_full_output(
    lgbm_preds_by_ticker: Dict[str, pd.DataFrame],
    lstm_preds_by_ticker: Optional[Dict[str, pd.DataFrame]],
    feature_dfs: Dict[str, pd.DataFrame],
    ensemble: MomentumEnsemble,
    ta_filter: Optional[str] = None,
    ta_strictness: str = config.TA_FILTER_STRICTNESS,
    buy_threshold: Optional[float] = None,
) -> pd.DataFrame:
    """
    Returnerar ett long-format DataFrame med alla outputs:
      Date, ticker, prob_up, pred_signal, pred_return, ta_score, position_size

    position_size tillämpar MIN_POSITION/MAX_POSITIONS/normalisering per datum
    (samma regler som build_portfolio_weights), så flera tickers med
    samtidiga köpsignaler konkurrerar om portföljutrymmet korrekt.

    buy_threshold: köpsignal sätts om prob_up > buy_threshold. None =
    config.BUY_THRESHOLD. Tröskeln kan optimeras på dev-perioden (se
    backtest/threshold_opt.py) – därför härleds pred_signal här i stället för
    att förlita sig på ensemblens hårdkodade 0.5.

    ta_filter: None (av), "gate" (hård grind – nollar köpsignaler som TA inte
    bekräftar) eller "score" (mjuk viktning – skalar position_size med andelen
    uppfyllda TA-villkor). ta_strictness väljer villkorsuppsättning, se
    models/ta_filter.py. ta_score sparas alltid (1.0 när filtret är av) för
    transparens.
    """
    if ta_filter not in (None, "gate", "score"):
        raise ValueError(f"Okänt ta_filter: {ta_filter!r}. Välj None, 'gate' eller 'score'.")

    buy_threshold = config.BUY_THRESHOLD if buy_threshold is None else buy_threshold

    rows = []

    for ticker, lgbm_pred in lgbm_preds_by_ticker.items():
        lstm_pred = (lstm_preds_by_ticker or {}).get(ticker)
        combined  = ensemble.combine(lgbm_pred, lstm_pred)

        feat_df = feature_dfs.get(ticker, pd.DataFrame())

        for date, row in combined.iterrows():
            # Hämta volatilitet
            try:
                vol = feat_df.loc[:date, "rvol_13w"].iloc[-1]
            except Exception:
                vol = 0.20

            # Absolut momentum (12-1) för momentum-kvalitetsgrinden (se _size_date).
            try:
                mom = feat_df.loc[:date, "mom_12_1"].iloc[-1]
            except Exception:
                mom = None

            raw_kelly = kelly_position_size(row["prob_up"], row["pred_return"], vol)
            # Behörig kandidat = modellen förväntar inte en nedgång (förv.avk över
            # selektivitetsgolvet, default 0.0). INGEN absolut prob_up-tröskel –
            # vi rankar RELATIVT och håller de N starkaste (oavsett absolut nivå),
            # så portföljen alltid fylls. Kontanter uppstår bara när i stort sett
            # inget bolag har positiv förväntan (bred nedgång) + via marknadsfiltret.
            eligible = row["pred_return"] > config.MIN_EXPECTED_RETURN

            # ── Valbart TA-bekräftelsefilter (opt-in, ovanpå momentum) ────────
            ta_score = 1.0
            if ta_filter is not None and eligible:
                try:
                    ta_row = feat_df.loc[date]
                    if isinstance(ta_row, pd.DataFrame):   # om datumet är duplicerat
                        ta_row = ta_row.iloc[-1]
                    passed, score = ta_confirmation(ta_row, ta_strictness)
                except Exception:
                    passed, score = False, 0.0   # saknad TA-data = ingen bekräftelse

                if ta_filter == "gate":
                    ta_score = 1.0 if passed else 0.0
                    if not passed:
                        eligible = False          # hård grind: vetar kandidaten
                else:  # score: mjuk viktning av conviction
                    ta_score = score
                    raw_kelly *= score

            rows.append({
                "Date":          date,
                "ticker":        ticker,
                "prob_up":       row["prob_up"],
                "pred_return":   row["pred_return"],
                "ta_score":      ta_score,
                "raw_kelly":     raw_kelly,
                "vol":           float(vol) if vol and vol > 0 else 0.20,
                "mom":           float(mom) if mom is not None and not pd.isna(mom) else 0.0,
                "eligible":      int(eligible),
            })

    df = pd.DataFrame(rows).set_index("Date").sort_index()

    # Alltid-investerad topp-N (tvärsnitts-momentum): bland behöriga kandidater,
    # ranka efter prob_up (conviction, alltid definierad) och håll de N starkaste
    # – oavsett absolut nivå. Vikta efter Kelly-conviction; om den är degenererad
    # (alla ~0, dvs svag edge) faller vi tillbaka på likavikt så portföljen ändå
    # fylls. Normaliserat till ~100%. Marknadsfilter/sektor-/korrelationsspärrar
    # i backtestern drar ner exponeringen i kris.
    def _size_date(group: pd.DataFrame) -> pd.Series:
        cand = group[group["eligible"] == 1]
        # Momentum-kvalitetsgrind (experiment, default AV): håll bara namn med
        # GENUINT momentum (abs. 12-1 > MOMENTUM_GATE_MIN). Annars tvingar
        # alltid-investerad topp-N in ~100% i N namn även när få trendar → de få
        # vinnarna späds ut av "minst dåliga" namn. Med grinden får portföljen
        # hålla FÄRRE än N och bygga kontanter när momentum är ont om (jfr
        # kap-viktning som låter vinnaren bli stor och struntar i resten).
        gate = bool(getattr(config, "MOMENTUM_GATE_ENABLED", False))
        if gate and "mom" in cand.columns:
            cand = cand[cand["mom"] > float(getattr(config, "MOMENTUM_GATE_MIN", 0.0))]
        if cand.empty:
            return pd.Series(0.0, index=group.index)
        top = cand.sort_values("prob_up", ascending=False).head(config.MAX_POSITIONS)
        n = len(top)
        eq = 1.0 / n
        # Tilt KRYMPT mot likavikt så portföljen inte kollapsar till de få namn
        # vars absoluta vikt råkar vara störst. Varje valt namn får minst
        # (1-blend)*likavikt, så vi håller N diversifierade innehav. Urvalet (vilka
        # N) styrs alltid av prob_up ovan – SIZING_MODE styr bara fördelningen:
        #   conviction  – tilt ∝ Kelly-conviction (default).
        #   inverse_vol – tilt ∝ 1/volatilitet (risk-paritet, lika riskbidrag).
        mode = str(getattr(config, "SIZING_MODE", "conviction"))
        if mode == "inverse_vol":
            inv = (1.0 / top["vol"].clip(lower=0.05))
            isum = float(inv.sum())
            tilt = (inv / isum) if isum > 0 else pd.Series(eq, index=top.index)
        else:
            kelly = top["raw_kelly"].clip(lower=0.0)
            ksum = float(kelly.sum())
            tilt = (kelly / ksum) if ksum > 0 else pd.Series(eq, index=top.index)
        blend = float(getattr(config, "CONVICTION_BLEND", 0.5))
        raw = {t: (1.0 - blend) * eq + blend * float(tw)
               for t, tw in zip(top["ticker"], tilt)}
        if gate and str(getattr(config, "MOMENTUM_GATE_MODE", "cash")) == "concentrate":
            # Aggressivt: satsa ~100% i de FÅ namn som klarade grinden (som
            # kap-viktning – låt vinnarna bli stora). Högre per-namn-tak; med t.ex.
            # taket 0.5 och 2 namn blir det 50/50 = 100% investerat.
            cap = float(getattr(config, "MOMENTUM_GATE_CONCENTRATE_CAP", config.MAX_POSITION))
            sized = _topn_invested_weights(raw, n=len(raw), max_position=cap)
        elif gate:
            # Defensivt (kontant): investerad andel = k/N (k = antal namn som
            # klarade grinden). Färre momentumnamn → mindre investerat, resten
            # kontanter. Ingen omfördelning av kapat överskott upp mot 100%.
            N = max(int(config.MAX_POSITIONS), 1)
            total_target = len(top) / float(N)
            s = sum(raw.values()) or 1.0
            sized = {t: min((v / s) * total_target, config.MAX_POSITION)
                     for t, v in raw.items()}
        else:
            # Alltid-investerad baslinje: normalisera topp-N till ~100% (kapat
            # överskott omfördelas). n=len(raw): explicit (default fryses vid import).
            sized = _topn_invested_weights(raw, n=len(raw))
        return group["ticker"].map(sized).fillna(0.0)

    df["position_size"] = df.groupby(level="Date", group_keys=False).apply(_size_date)
    # pred_signal = "hålls i portföljen nu" (topp-N), inte en absolut tröskel.
    df["pred_signal"] = (df["position_size"] > 0).astype(int)
    df = df.drop(columns=["raw_kelly", "vol", "mom", "eligible"])
    return df
