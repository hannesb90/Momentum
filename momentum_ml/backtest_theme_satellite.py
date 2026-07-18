"""
backtest_theme_satellite.py – testar next_buy()s TEMA-SATELLIT-motivering
("Rotationen slog aldrig index netto → minsta hinken, aldrig kärnersättning",
portfolio.py:next_buy() rad ~2257) mot den FAKTISKA mekaniken, inte en
näraliggande.

Den motiveringen citerar etf_rotation.py:s backtest() - en strategi som
SÄLJER/roterar bort en ETF när den faller ur topp-K var 4:e vecka. Men
next_buy()s riktiga tema-satellit (_candidates()["theme"], se portfolio.py)
gör något annat: plockar den högst rankade tema-ETF:en VARJE månad och
lägger HELA den månadens insättning där - säljer ALDRIG en tidigare köpt
position även om den tappar rank. Två olika strategier, bara en av dem
faktiskt testad tidigare.

Samma "bara påfyllnad, aldrig sälj"-disciplin som backtest_core_allocation.py
(se backtest/accumulation.py:simulate_rotating_accumulation), men med en
ROTERANDE kandidat i stället för fasta målvikter - portföljen ackumulerar
över åren vilka "månadens vinnare" än råkade vara.

Kräver nätåtkomst till Yahoo Finance - körs på Pi:n:

    python backtest_theme_satellite.py

Återanvänder etf_rotation.py:s EGNA _panel()/_scores()/_regime() rakt av
(inte en omskriven variant) - garanterar att rel_mom/risk-on-flaggan här är
IDENTISK med vad som faktiskt driver produktionens theme_pick, inte en
subtilt annorlunda tolkning.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
import etf_rotation as er  # noqa: E402
from backtest.accumulation import simulate_accumulation, simulate_rotating_accumulation  # noqa: E402

CORE_TICKER, CORE_NAME = getattr(config, "PORTFOLIO_CORE_ETF", ("IUSQ.DE", "iShares MSCI ACWI"))


def _fmt_pct(x):
    return f"{x:+.1%}" if x is not None else "  n/a"


def _print_result(label, r):
    s = r["nav_stats"]
    print(f"  {label}")
    print(f"    fönster {r['start']} → {r['end']} ({r['years']} år) · "
          f"NAV-CAGR {s['CAGR']} · Sharpe {s['Sharpe']} · MaxDD {s['Max Drawdown']} · "
          f"slutvärde {r['end_value']:,.0f} av {r['total_contributed']:,.0f} insatt "
          f"({_fmt_pct(r['gain_over_contributed'])})".replace(",", " "))


def main():
    uni = er._load_universe()
    kinds = er._kinds()
    theme_tickers = [t for t, _, _ in uni if kinds.get(t) == "theme"]
    if not theme_tickers:
        print("[backtest_theme_satellite] inga theme-taggade tickers i data/rotation_universe.csv.")
        return
    print(f"[backtest_theme_satellite] {len(theme_tickers)} tema-ETF:er i rotationsuniversumet: "
          f"{', '.join(theme_tickers)}")

    extra = [x for x in (config.ETF_ROT_DEFENSIVE, config.ETF_ROT_REGIME_TICKER, CORE_TICKER) if x]
    panel = er._panel(theme_tickers + extra)
    have_theme = [t for t in theme_tickers if t in panel.columns]
    if len(have_theme) < 2:
        print(f"[backtest_theme_satellite] för få tema-ETF:er med prisdata ({len(have_theme)}).")
        return
    if CORE_TICKER not in panel.columns:
        print(f"[backtest_theme_satellite] ingen prisdata för kärnan ({CORE_TICKER}) - kan inte jämföra.")
        return

    rel, _absm = er._scores(panel, have_theme)   # SAMMA formel som produktionens rel_mom
    regime = er._regime(panel)   # None om ETF_ROT_REGIME_ENABLED=False, annars kausal bool-serie

    print(f"\n===== TEMA-SATELLIT: rider rotationens månadsvinnare, aldrig sälj "
          f"(samma disciplin som next_buy()) =====")
    print(f"Regim-gate: {'PÅ (' + config.ETF_ROT_REGIME_TICKER + ' vs ' + str(config.ETF_ROT_REGIME_MA) + 'v MA)' if regime is not None else 'AV'}"
          f" · Månadsinsättning: {config.NEXT_BUY_DEFAULT_AMOUNT:,.0f} · "
          f"kostnad/köp: {config.ETF_ROT_COST_ONEWAY:.2%}\n".replace(",", " "))

    r_theme = simulate_rotating_accumulation(
        have_theme, rel, panel, risk_on=regime, fallback_ticker=CORE_TICKER,
    )
    if r_theme is None:
        print("[backtest_theme_satellite] < 3 år gemensam historik för tema-universumet - kan inte testa.")
        return

    r_core = simulate_accumulation({CORE_TICKER: 1.0}, {CORE_TICKER: panel[[CORE_TICKER]].rename(
        columns={CORE_TICKER: "Close"})}, start=r_theme["start"])
    if r_core is None:
        print("[backtest_theme_satellite] kärnan saknar data i tema-fönstret - kan inte jämföra.")
        return

    print(f"  MATCHAT FÖNSTER: {r_theme['start']} → {r_theme['end']} ({r_theme['years']} år)\n")
    _print_result(f"Endast {CORE_NAME} (100% kärna hela tiden)", r_core)
    _print_result("Tema-satellit (100% i rotationens #1-tema varje månad, aldrig sälj)", r_theme)

    print("\n  Insättningar per tema-ETF (hur koncentrerat 'rider vinnarna' faktiskt blev):")
    total_months = sum(r_theme["picks"].values())
    for t, n in r_theme["picks"].items():
        name = next((nm for tk, _, nm in uni if tk == t), t)
        print(f"    {t:<10} {name:<45} {n:>3} månader ({n / total_months:.0%})")

    print("\n(100% i endera - INTE next_buy()s faktiska blandning av kärna/Sverige/tema samtidigt - "
          "det här isolerar TEMA-MEKANIKENS egen merit, oberoende av hur stor andel av insättningen "
          "som faktiskt går dit i skarpt läge. NAV-CAGR/Sharpe/MaxDD är insättnings-neutrala.)")


if __name__ == "__main__":
    main()
