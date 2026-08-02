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
from backtest import pipeline_diagnostics as _diag


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
        lgbm_weight: Optional[float] = None,
        lstm_weight: Optional[float] = None,
    ):
        self.lgbm_w = config.ENSEMBLE_LGBM_WEIGHT if lgbm_weight is None else lgbm_weight
        self.lstm_w = config.ENSEMBLE_LSTM_WEIGHT if lstm_weight is None else lstm_weight
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
        # prob_raw (LGBM:s okalibrerade poäng) följer med som finordnings-/tie-
        # break-signal – LSTM saknar motsvarighet, så den blandas inte.
        if "prob_raw" in lg.columns:
            combined["prob_raw"] = lg["prob_raw"]
        # Kalibrering (rättad 2026-07-29, se tune_rank_calibration.py): LGBM-benet
        # är sedan LambdaRank-migreringen INTE längre isotoniskt kalibrerat -
        # prob_up är en ren rankscore-normalisering, bara LSTM-benet är det
        # fortfarande (models/lstm_model.py). prob_up_calibrated blandar LSTM:s
        # äkta kalibrerade sannolikhet med LGBM:s empiriska decil-vinstfrekvens
        # (lgbm_model.py:s decile_win_rates_) istället för dess råa rankscore -
        # det är DENNA kolumn Kelly-sizing (kelly_position_size) ska använda,
        # inte prob_up. prob_up självt lämnas orört: det används för rangordning/
        # topp-N-urval, där bara den RELATIVA ordningen spelar roll (validerad
        # Spearman=0.879 mot faktisk vinstfrekvens) - den absoluta skalans fel
        # påverkar inte det.
        if "prob_up_calibrated" in lg.columns:
            combined["prob_up_calibrated"] = w_lg * lg["prob_up_calibrated"] + w_ls * ls["prob_up"]
        else:
            combined["prob_up_calibrated"] = combined["prob_up"]
        # pred_signal nedan (>0.5) skrivs ändå ÖVER i build_full_output av den
        # alltid-investerade topp-N-logiken, så 0.5-tröskeln är inte aktiv.
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

    BUGG (fixad, verkligt fall: kodgranskning 2026-07-23): np.clip SANERAR
    INTE NaN – np.clip(nan, 0.01, 0.99) returnerar nan, som sedan flödar
    oförändrat genom hela uträkningen till slutresultatet. Ett NaN prob_up
    (t.ex. ett kalibreringsfel eller en saknad rad i ensemble.combine())
    gav därför en NaN position_size rakt in i backtesterns portföljvikter,
    helt tyst. Explicit NaN/Inf-koll krävs FÖRE clip, den kan inte göra
    jobbet själv.
    """
    if not np.isfinite(prob_up):
        return 0.0
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
    n: Optional[int] = None,
    max_position: Optional[float] = None,
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
    n = config.MAX_POSITIONS if n is None else n
    max_position = config.MAX_POSITION if max_position is None else max_position
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
    apply_entry_policy: bool = False,
    record_diagnostics: bool = True,
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

            kelly_prob = row["prob_up_calibrated"] if "prob_up_calibrated" in row.index else row["prob_up"]
            raw_kelly = kelly_position_size(kelly_prob, row["pred_return"], vol)
            # Behörig kandidat = modellen förväntar inte en nedgång (förv.avk över
            # selektivitetsgolvet, default 0.0). INGEN absolut prob_up-tröskel –
            # vi rankar RELATIVT och håller de N starkaste (oavsett absolut nivå),
            # så portföljen alltid fylls. Kontanter uppstår bara när i stort sett
            # inget bolag har positiv förväntan (bred nedgång) + via marknadsfiltret.
            eligible = row["pred_return"] > config.MIN_EXPECTED_RETURN
            # Fonder/ETF:er (cap_tier="Fond": XACT-index, tyska iShares/
            # Xtrackers-sektor-ETF:er) laddas medvetet in för sektor-momentum-
            # signaler (se load_sweden_universe()) men är INGA portfölj-
            # kandidater - upptäckt 2026-07-24 att de läckte in som faktiska
            # köpsignaler (t.ex. XACT-SVERIGE.ST/XACT-OMXS30.ST rekommenderade
            # som "småbolagsköp"). config.CAP_TIER_MAP saknar okänd ticker →
            # get() default "" (inte "Fond") → utesluter aldrig av misstag.
            if config.CAP_TIER_MAP.get(ticker, "") == "Fond":
                eligible = False

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

            entry_action = "normal"
            entry_overextended = False
            entry_fundamental_override = False
            entry_peak_roc13_13w = np.nan
            new_entry_allowed = True
            if apply_entry_policy:
                from models.entry_policy import decide_entry
                try:
                    decision = decide_entry(
                        getattr(config, "ACTIVE_SEGMENT", "large"),
                        feat_df.loc[:date],
                        bool(eligible),
                    )
                    new_entry_allowed = decision.eligible
                    entry_action = decision.action
                    entry_overextended = decision.overextended
                    entry_fundamental_override = decision.fundamental_override
                    entry_peak_roc13_13w = decision.peak_roc13_13w
                except Exception as exc:
                    # Fail open for availability, but expose the fallback.
                    entry_action = f"policy_fallback:{type(exc).__name__}"

            rows.append({
                "Date":          date,
                "ticker":        ticker,
                "prob_up":       row["prob_up"],
                # rå (okalibrerad) poäng: tie-break när isotonic-platån gör
                # prob_up identisk för nästan alla bolag. Saknas (gammal pkl)
                # → faller tillbaka på prob_up (samma beteende som förut).
                "prob_raw":      float(row.get("prob_raw", row["prob_up"])),
                "pred_return":   row["pred_return"],
                "ta_score":      ta_score,
                "raw_kelly":     raw_kelly,
                "vol":           float(vol) if vol and vol > 0 else 0.20,
                "mom":           float(mom) if mom is not None and not pd.isna(mom) else 0.0,
                "eligible":      int(eligible),
                "entry_action":  entry_action,
                "entry_overextended": int(entry_overextended),
                "entry_fundamental_override": int(entry_fundamental_override),
                "entry_peak_roc13_13w": entry_peak_roc13_13w,
                "new_entry_allowed": int(new_entry_allowed),
            })

    df = pd.DataFrame(rows).set_index("Date").sort_index()
    # Buggfix 2026-07-30 (UTVECKLINGSLOGG #132): MomentumLGBM.predict()s egen
    # tvärsnittella min-max-normalisering av prob_up är verkningslös när den
    # anropas per ticker (VARJE anropare i kodbasen, inklusive main.py, gör
    # det) - varje datum-grupp innehåller då bara EN rad, så x.max()==x.min()
    # är trivialt sant och 0.5-fallbacken triggas alltid (verifierat: prob_up
    # var identiskt 0,5 för samtliga rader, i produktion såväl som i alla
    # tune_*.py-skript). Räknas om HÄR i stället, där df redan är ett RIKTIGT
    # tvärsnitt (alla tickers per datum, efter rows-konkateneringen ovan) -
    # samma plats/logik som model_order_rank redan använder korrekt.
    #
    # VILLKORLIGT per datum (inte en ovillkorlig överskrivning): bara om den
    # inkommande prob_up redan är DEGENERERAD (alla tickers knutna till samma
    # värde den dagen - exakt buggens signatur) räknas den om från prob_raw.
    # Om prob_up redan varierar meningsfullt (t.ex. en framtida genuint
    # LSTM-blandad prob_up, som bär information prob_raw INTE gör - se
    # ensemble.combine()) lämnas den ORÖRD - annars skulle en riktig
    # ensembleblandning tystas ned till en ren LGBM-rangordning. Bekräftat
    # med test_ensemble.py::test_neutral_short_signal_preserves_prob_then_raw_order,
    # som injicerar en avsiktligt icke-degenererad prob_up och förväntar att
    # den (inte prob_raw) styr urvalet.
    degenerate = df.groupby(level=0)["prob_up"].transform("nunique") <= 1
    if degenerate.any():
        recomputed = df.loc[degenerate].groupby(level=0)["prob_raw"].transform(
            lambda x: (x - x.min()) / (x.max() - x.min() + 1e-9) if x.max() > x.min() else 0.5
        )
        df.loc[degenerate, "prob_up"] = recomputed
    short_active = (
        bool(getattr(config, "SHORT_SIGNAL_ENABLED", False))
        and getattr(config, "ACTIVE_SEGMENT", "large") == "large"
    )
    if short_active:
        try:
            from altdata.fi_blankning import attach_features
            df = attach_features(df)
        except Exception as exc:
            print(f"  [WARN] FI-blankningssignal kunde inte läsas: {exc}")
    for col in ("short_pct", "short_delta_4w", "short_delta_8w", "short_delta_13w"):
        if col not in df:
            df[col] = np.nan
    # Exakt percentil av den BEFINTLIGA lexikografiska grundordningen:
    # prob_up först, prob_raw endast tie-break. Att bara ranka prob_raw här
    # skulle göra råpoängen primär även för helt oblan­kade namn och därmed
    # förändra basmodellen när den nya signalen är neutral.
    ordered = (df.assign(_row=np.arange(len(df)))
               .sort_values(["Date", "prob_up", "prob_raw"],
                            ascending=[True, True, True]))
    ordered["_base_order_rank"] = (
        ordered.groupby(level="Date").cumcount().add(1)
        / ordered.groupby(level="Date")["ticker"].transform("size")
    )
    base_order_rank = ordered.set_index("_row")["_base_order_rank"].reindex(
        np.arange(len(df))
    ).to_numpy()
    df["model_order_rank"] = base_order_rank
    # Kort EMA över modellens fulla lexikografiska ordning (prob_up först,
    # prob_raw bara tie-break) kan dämpa enveckorsbrus utan att råpoängen blir
    # primär. Span=1 är en exakt no-op. Vi exporterar
    # challenger-ranken även när den inte styr urvalet så A/B-resultatet går att
    # granska i efterhand.
    ema_span = max(int(getattr(config, "RANK_EMA_SPAN", 1)), 1)
    ordered_time = (
        df.reset_index()
        .assign(_row=np.arange(len(df)))
        .sort_values(["ticker", "Date", "_row"])
    )
    ordered_time["rank_ema_score"] = (
        ordered_time.groupby("ticker", sort=False)["model_order_rank"]
        .transform(lambda s: s.ewm(span=ema_span, adjust=False).mean())
    )
    ema_score = ordered_time.set_index("_row")["rank_ema_score"].reindex(
        np.arange(len(df))
    ).to_numpy()
    df["rank_ema_score"] = ema_score
    df["rank_ema_rank"] = df.groupby(level="Date")["rank_ema_score"].rank(
        method="first", pct=True
    )
    df["short_entry_penalty"] = 0.0
    df["short_adjusted_rank"] = df["model_order_rank"]
    if short_active:
        pct = df["short_pct"].clip(
            lower=0.0, upper=float(getattr(config, "SHORT_ENTRY_MAX_PCT", 10.0))
        ).fillna(0.0)
        df["short_entry_penalty"] = (
            pct * float(getattr(config, "SHORT_ENTRY_PENALTY_PER_PCT", 0.03))
        )
        df["short_adjusted_rank"] -= df["short_entry_penalty"]
    short_entry_active = short_active and bool(
        getattr(config, "SHORT_ENTRY_ENABLED", False)
    )
    if ema_span > 1:
        df["selection_rank"] = df["rank_ema_rank"]
        if short_entry_active:
            df["selection_rank"] -= df["short_entry_penalty"]
    else:
        df["selection_rank"] = (
            df["short_adjusted_rank"] if short_entry_active else df["model_order_rank"]
        )

    # Alltid-investerad topp-N (tvärsnitts-momentum): bland behöriga kandidater,
    # ranka efter prob_up (conviction, alltid definierad) och håll de N starkaste
    # – oavsett absolut nivå. Vikta efter Kelly-conviction; om den är degenererad
    # (alla ~0, dvs svag edge) faller vi tillbaka på likavikt så portföljen ändå
    # fylls. Normaliserat till ~100%. Marknadsfilter/sektor-/korrelationsspärrar
    # i backtestern drar ner exponeringen i kris.
    gate = bool(getattr(config, "MOMENTUM_GATE_ENABLED", False))
    df["selection_eligible"] = df["eligible"].astype(int)
    if gate:
        df.loc[df["mom"] <= float(getattr(config, "MOMENTUM_GATE_MIN", 0.0)),
               "selection_eligible"] = 0

    def _size_date(group: pd.DataFrame) -> pd.Series:
        cand = group[group["selection_eligible"] == 1]
        # Momentum-kvalitetsgrind (#17 i UTVECKLINGSLOGG.md, adopterad per
        # segment; #62 validerade den strikt mot alternativ - se loggen):
        # håll bara namn med POSITIVT 12-1-momentum över MOMENTUM_GATE_MIN.
        # KORRIGERAT 2026-07-25 (extern kodgranskning): denna kommentar sa
        # tidigare felaktigt "abs. 12-1" (absolutvärde) - koden nedan har
        # ALDRIG använt abs(), bara ett strikt POSITIVT tröskelvillkor
        # (mom > MOMENTUM_GATE_MIN, inte abs(mom) > MOMENTUM_GATE_MIN).
        # Kommentaren var missvisande; koden (som styr beteendet) är och
        # har varit oförändrad. Annars tvingar alltid-investerad topp-N in
        # ~100% i N namn även när få trendar → de få vinnarna späds ut av
        # "minst dåliga" namn. Med grinden får portföljen hålla FÄRRE än N
        # och bygga kontanter när momentum är ont om (jfr kap-viktning som
        # låter vinnaren bli stor och struntar i resten). Ingen skillnad
        # görs mellan NYA kandidater och REDAN ÄGDA innehav - grinden
        # omprövas tillståndslöst varje vecka för alla (#63 testade att
        # låta ägda innehav slippa omprövningen - ingen förbättring).
        if cand.empty:
            return pd.Series(0.0, index=group.index)
        # Sortera på kalibrerad prob FÖRST (oförändrat där den skiljer), med rå
        # poäng som TIE-BREAK: på isotonic-platån (nästan alla exakt 34,4%) var
        # urvalet annars godtycklig radordning – nu avgör modellens finordning.
        sort_cols = ["selection_rank", "prob_up", "prob_raw"]
        top = (cand.sort_values(sort_cols, ascending=False)
               .head(config.MAX_POSITIONS))
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
            # TA score är ett explicit storleks-overlay. Tidigare multiplicerade
            # det bara raw_kelly och blev därför en tyst no-op i det adopterade
            # inverse-vol-läget.
            if ta_filter == "score":
                inv = inv * top["ta_score"].clip(lower=0.0, upper=1.0)
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
    # prob_rank: tvärsnitts-percentil av rå poäng per datum (0–1). Det ÄRLIGA
    # talet att visa i appen – kalibrerad prob_up är en isotonic-trappa som vid
    # svag signal står på exakt basfrekvensen (34,4%) i åratal och ser trasig ut,
    # medan percentilen alltid varierar och betyder något: "hur stark är aktien
    # relativt universumet just nu?" (det är också så urvalet faktiskt fungerar).
    df["prob_rank"] = df.groupby(level="Date")["prob_raw"].rank(pct=True)

    # Eligible-mask-tratt (#5/#9 i pipeline-granskningen): universum ->
    # eligible (förv.avk-golv) -> efter momentumgrind -> slutligt urval, per
    # historiskt datum. Loggas HÄR, sist möjliga plats innan eligible/
    # selection_eligible/position_size skrivs bort nedan - en gradvis
    # krympande n_final/n_eligible-kvot över tid avslöjar tyst
    # överfiltrering utan att någon enskild körning ser fel ut.
    # record_diagnostics=False för serveringsmodellens build_full_output-
    # anrop (main.py STEG 5.6) - annars loggas samma holdout-datum två
    # gånger (mät- OCH serveringsmodellen), vilket skulle dubblera/
    # motsäga varandra i eligible_funnel_history.csv:s tidsserie.
    if record_diagnostics:
        funnel = df.groupby(level="Date").agg(
            n_scored=("ticker", "size"),
            n_eligible=("eligible", "sum"),
            n_after_gate=("selection_eligible", "sum"),
            n_final=("position_size", lambda s: int((s > 0).sum())),
        )
        for date, row in funnel.iterrows():
            _diag.record_eligible_funnel(
                date, row["n_scored"], row["n_eligible"], row["n_after_gate"], row["n_final"])

    df = df.drop(columns=["raw_kelly", "vol", "mom", "eligible"])
    return df
