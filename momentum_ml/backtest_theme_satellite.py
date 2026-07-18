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
from backtest.accumulation import (  # noqa: E402
    normalize_weekly_panel, simulate_accumulation, simulate_rotating_accumulation,
)

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
    raw_panel = er._panel(theme_tickers + extra)
    # er._panel() gör bara ffill(limit=1) på en rå multi-ticker-join - täcker INTE att
    # olika tickers veckostaplar kan vara ankrade på olika veckodagar (samma rotbugg
    # som fixades i backtest/accumulation.py:_weekly_closes(), se normalize_weekly_panel()
    # för varför den annars smyger in en TYST snedvridning av rel_mom:s .shift(w)-fönster,
    # inte bara av vecko-/år-räkningen).
    panel = normalize_weekly_panel(raw_panel)
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

    core_prices = {CORE_TICKER: panel[[CORE_TICKER]].rename(columns={CORE_TICKER: "Close"})}

    # Två separata körningar, var och en på sitt EGET maximala fönster - de
    # kan starta olika (temauniversumet innehåller ETF:er äldre än ACWI
    # självt, t.ex. INRG.L sedan 2009 mot ACWI:s 2011). `start=` klipper bara
    # FRAMÅT, den kan aldrig trolla fram data en ticker inte har - att skicka
    # in den ENA sidans startdatum till den ANDRA (förra körningen) är därför
    # ett no-op om den andra redan börjar SENARE, vilket gav en tyst orättvis
    # jämförelse (temat fick extra år kärnan aldrig testades mot). Rätt fix:
    # räkna ut det SENASTE av de två egna starterna och klipp BÅDA dit.
    r_theme_own = simulate_rotating_accumulation(have_theme, rel, panel, risk_on=regime, fallback_ticker=CORE_TICKER)
    if r_theme_own is None:
        print("[backtest_theme_satellite] < 3 år gemensam historik för tema-universumet - kan inte testa.")
        return
    r_core_own = simulate_accumulation({CORE_TICKER: 1.0}, core_prices)
    if r_core_own is None:
        print("[backtest_theme_satellite] kärnan saknar tillräcklig egen historik - kan inte jämföra.")
        return

    print("  EGET FÖNSTER (respektive strategis maximala tillgängliga historik):\n")
    _print_result(f"Endast {CORE_NAME} (100% kärna hela tiden)", r_core_own)
    _print_result("Tema-satellit (100% i rotationens #1-tema varje månad, aldrig sälj)", r_theme_own)

    matched_start = max(r_theme_own["start"], r_core_own["start"])
    r_core = simulate_accumulation({CORE_TICKER: 1.0}, core_prices, start=matched_start)
    if r_core is None:
        print(f"\n[backtest_theme_satellite] för kort efter klippning till {matched_start} - "
              "ingen matchad jämförelse möjlig.")
        return

    # Tre säljvarianter på SAMMA fönster: ingen säljregel alls (gamla beteendet),
    # appens EGEN konfigurerade säljvakts-tröskel (config.TAKEPROFIT_GAIN, 50%),
    # och en snävare 90%-tröskel. Sålt kapital slussas in i SAMMA "var ska
    # nästa krona in"-beslut som nästa månads vanliga insättning - kan alltså
    # gå tillbaka till ett tema om rotationen fortfarande gynnar ett, ingen
    # särbehandlad genväg rakt till kärnan (se simulate_rotating_accumulation()s
    # docstring för hela mekaniken).
    app_tp = float(getattr(config, "TAKEPROFIT_GAIN", 0.50))
    variants = [("Ingen säljregel (rent köp-och-behåll)", None),
                (f"Säljvakt vid +{app_tp:.0%} (appens EGEN config.TAKEPROFIT_GAIN)", app_tp),
                ("Säljvakt vid +90%", 0.90)]

    print(f"\n  MATCHAT FÖNSTER (klippt till senaste av de två egna starterna): "
          f"{r_core['start']} → {r_core['end']} ({r_core['years']} år)\n")
    _print_result(f"Endast {CORE_NAME} (100% kärna hela tiden)", r_core)

    results = []
    for label, tp in variants:
        r = simulate_rotating_accumulation(have_theme, rel, panel, risk_on=regime,
                                            fallback_ticker=CORE_TICKER, start=matched_start,
                                            take_profit_gain=tp)
        if r is None:
            print(f"  Tema-satellit – {label:<55} HOPPAD (för kort)")
            continue
        results.append((label, r))
        _print_result(f"Tema-satellit – {label}", r)
        if r.get("take_profits"):
            hits = ", ".join(f"{t} ({n}×)" for t, n in r["take_profits"].items())
            print(f"    → sålde vid tröskeln: {hits}")

    base = results[0][1] if results else None
    if base:
        print("\n  Insättningar per tema-ETF, ingen säljregel (hur koncentrerat 'rider vinnarna' faktiskt blev):")
        total_months = sum(base["picks"].values())
        for t, n in base["picks"].items():
            name = next((nm for tk, _, nm in uni if tk == t), t)
            print(f"    {t:<10} {name:<45} {n:>3} månader ({n / total_months:.0%})")

    print("\n(100% i endera - INTE next_buy()s faktiska blandning av kärna/Sverige/tema samtidigt - "
          "det här isolerar TEMA-MEKANIKENS egen merit, oberoende av hur stor andel av insättningen "
          "som faktiskt går dit i skarpt läge. NAV-CAGR/Sharpe/MaxDD är insättnings-neutrala. "
          "Säljvakten kollas mot en VIKTAD SNITTKOSTNAD per ticker, inte senaste köpet - en position "
          "som köpts flera månader i rad drar upp sin egen tröskel i takt med priset, se "
          "simulate_rotating_accumulation()s docstring.)")


if __name__ == "__main__":
    main()
