"""
tune_leverage_holding_period.py – Uppföljning på #131 (backtest_bear_hedge.py/
backtest_bull_hedge.py): den regim-styrda ackumuleringssimuleringen håller
hedge-positionen tills regimen vänder (i snitt ~8v för bear, ~13v för bull i
den mätningen, inte en fast period) - svarar därför INTE direkt på "vid
vilken innehavstid slutar hävstången löna sig?". Detta skript isolerar just
den frågan: för varje möjlig innehavsperiod N (1/2/5/10/13/26/52 veckor),
mät den hävstångade ETF:ens FAKTISKA avkastning över alla överlappande
N-veckorsfönster i historiken, jämfört med den NAIVA förväntan
(hävstång × underliggande index avkastning över samma fönster) - gapet
mellan dem ÄR den dagliga ombalanserings-decayen, som väntas växa med både
innehavstid och volatilitet under perioden (kvadratisk/variansdriven, inte
linjär - se #131/backtest_bear_hedge.py:s docstring).

Underliggande jämförelseindex: XACT-OMXS30.ST (produkterna är uttryckligen
byggda mot OMXS30, INTE XACT-SVERIGE.ST som #131 använde som bred
regimklassificerings-proxy - olika index, viktigt att inte blanda ihop här).

    /opt/momentum/venv/bin/python3 tune_leverage_holding_period.py
"""
import sys
sys.path.insert(0, '.')
import config
import numpy as np
import pandas as pd
from data.data_loader import fetch_weekly_data

UNDERLYING = "XACT-OMXS30.ST"
PRODUCTS = [
    ("XACT-BULL.ST",   "Bull +1,5x", 1.5),
    ("XACT-BULL-2.ST", "Bull +2x",   2.0),
    ("XACT-BEAR.ST",   "Bear -1,5x", -1.5),
    ("XACT-BEAR-2.ST", "Bear -2x",   -2.0),
]
HOLDING_WEEKS = [1, 2, 5, 10, 13, 26, 52]


def main():
    tickers = [UNDERLYING] + [t for t, _, _ in PRODUCTS]
    print(f"[leverage_holding] hämtar: {', '.join(tickers)}")
    prices = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    missing = [t for t in tickers if t not in prices]
    if missing:
        print(f"[leverage_holding] saknar prisdata för: {missing}")
        return

    closes = pd.DataFrame({t: prices[t]["Close"] for t in tickers}).dropna()
    print(f"[leverage_holding] {len(closes)} gemensamma veckor: "
          f"{closes.index.min().date()} -> {closes.index.max().date()}")

    rows = []
    for N in HOLDING_WEEKS:
        idx_ret = closes[UNDERLYING].shift(-N) / closes[UNDERLYING] - 1.0
        idx_vol = closes[UNDERLYING].pct_change().rolling(N).std() * np.sqrt(52)
        for ticker, label, lev in PRODUCTS:
            actual_ret = closes[ticker].shift(-N) / closes[ticker] - 1.0
            naive_expected = lev * idx_ret
            decay_gap = (actual_ret - naive_expected).dropna()
            vol_during = idx_vol.reindex(decay_gap.index)
            rows.append({
                "innehav_v": N, "produkt": label,
                "n_fonster": len(decay_gap),
                "snitt_faktisk_avk": actual_ret.reindex(decay_gap.index).mean(),
                "snitt_naiv_forvantan": naive_expected.reindex(decay_gap.index).mean(),
                "snitt_decay_gap": decay_gap.mean(),
                "median_decay_gap": decay_gap.median(),
                "andel_negativ_gap": (decay_gap < 0).mean(),
                "snitt_annualiserad_vol_under_fonstret": vol_during.mean(),
            })

    df = pd.DataFrame(rows)
    print("\n" + "=" * 100)
    print("Decay-gap (faktisk avkastning - hävstång×index-avkastning) per innehavstid")
    print("=" * 100)
    for produkt in [p[1] for p in PRODUCTS]:
        sub = df[df["produkt"] == produkt].set_index("innehav_v")
        print(f"\n  {produkt}:")
        print(sub[["n_fonster", "snitt_faktisk_avk", "snitt_naiv_forvantan",
                    "snitt_decay_gap", "median_decay_gap", "andel_negativ_gap",
                    "snitt_annualiserad_vol_under_fonstret"]]
              .to_string(float_format=lambda x: f"{x:+.4f}" if abs(x) < 10 else f"{x:.0f}"))

    print("\n[leverage_holding] Tolkning: 'snitt_decay_gap' negativt/växande med N (och med "
          "volatiliteten under fönstret) = decayen äter upp mer av den nominella hävstången "
          "ju längre du håller och ju skakigare perioden är. Positivt gap vid en viss N "
          "betyder att hävstången FAKTISKT slog den naiva multipeln under just de fönstren "
          "(kan hända i jämna trender - se #131/backtest_bull_hedge.py:s docstring).")
    print("\n[leverage_holding] Klart.")


if __name__ == "__main__":
    main()
