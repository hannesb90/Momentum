"""
backtest_core_allocation.py – testar FRÅGAN next_buy()s kärn-motivering
("en enda global fond slog varje aktiv variant") ALDRIG faktiskt testade.

Den motiveringen (portfolio.py:next_buy(), rad ~2251) citerar aktie-holdout
och ETF-rotationens OOS-svep som bevis - men båda testar HELT andra frågor
(kan modellen plocka enskilda svenska aktier? slår TAKTISK ETF-rotation
index netto?). Ingen av dem testar:
  1. Bara påfyllnad, aldrig sälj (next_buy()s FAKTISKA kärn-mekanik) - se
     backtest/accumulation.py, som simulerar exakt den disciplinen.
  2. Rimlig exponeringsfördelning mellan flera fonder i stället för en enda.
  3. Olika regionindex mot varandra (Kina/Indien separat vs bred EM-korg,
     Europa vs bred World).

Det här skriptet fyller den luckan: samma månadsinsättning, samma
köp-och-behåll-disciplin, olika kärn-konstruktioner, jämförda på riktig
prisdata. Kräver nätåtkomst till Yahoo Finance - körs på Pi:n:

    python backtest_core_allocation.py

VIKTIGT om resultatet: World+EM-scenariot återskapar (i kapvikt) i princip
SAMMA exponering som dagens ACWI-ensamma kärna - om det scenariot inte
slår ren ACWI är det förväntat (samma innehav, bara uppdelat på två
fonder/emittenter i stället för en), inte ett tecken på att splitten är
fel. Den delen av frågan handlar om KONCENTRATIONSRISK (se "störst enskilt
innehav"-varningen i portfolio.compute()), inte om avkastning. EM/Europa/
Kina/Indien-scenarierna däremot är RIKTIGA regionsatsningar (bort från
kapvikt) - DE är det som faktiskt testas här mot en avkastnings-/risk-
måttstock, och ska INTE kallas "kärna" (evidensbackad) förrän de faktiskt
vunnit den jämförelsen.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
from data.data_loader import fetch_weekly_data  # noqa: E402
from backtest.accumulation import simulate_accumulation  # noqa: E402

# Xetra-noterade UCITS-ETF:er, alla i EUR (FX identisk för alla scenarier,
# se accumulation.py:s docstring för varför den då kan uteslutas ur jämförelsen).
IUSQ = "IUSQ.DE"   # iShares MSCI ACWI (dagens kärna, hela världen i en fond)
WORLD = "EUNL.DE"  # iShares Core MSCI World (utvecklade marknader, ex EM)
USA = "SXR8.DE"    # iShares Core S&P 500 (delmängd av World - se overlap-varning nedan)
EM = "IS3N.DE"     # iShares Core MSCI EM IMI
EUROPE = "EXSA.DE"  # iShares Core MSCI Europe (delmängd av World - se overlap-varning nedan)
CHINA = "XCS6.DE"  # Xtrackers MSCI China (bred Kina, inte "China Tech"/KWBE.DE-nischen)
INDIA = "QDV5.DE"  # iShares MSCI India (kortast historik i setet, lanserad 2018)

SCENARIOS = {
    "Endast ACWI (dagens kärna)": {IUSQ: 1.0},
    "World + EM, kapvikt ~88/12 (samma exponering som ACWI, 2 fonder)": {WORLD: 0.88, EM: 0.12},
    "EM + Europa, 50/50 (aktiv regionsatsning, INTE kapvikt)": {EM: 0.5, EUROPE: 0.5},
    "World + USA + EM + Europa, 25/25/25/25 (dagens Innehav-sida, se overlap-varning)": {
        WORLD: 0.25, USA: 0.25, EM: 0.25, EUROPE: 0.25,
    },
    "World + EM + Kina + Indien, 60/15/15/10 (granulär, illustrativ vikt - ej optimerad)": {
        WORLD: 0.60, EM: 0.15, CHINA: 0.15, INDIA: 0.10,
    },
}


def _fmt_pct(x):
    return f"{x:+.1%}" if x is not None else "  n/a"


def _diagnose_tickers(prices):
    """Per-ticker giltigt datumintervall + antal NaN-luckor DÄRINOM - separat
    från _weekly_closes()s STRIKTA gemensamma-fönster-krav (kräver att ALLA
    tickers i ett scenario har pris SAMMA vecka). En kort/gles enskild ticker
    (t.ex. tunt handlad på Yahoo) syns härifrån direkt, i stället för att bara
    tysta HOPPAS scenariot som använder den."""
    print("\n[diagnos] per-ticker giltigt intervall (förklarar ev. HOPPADE scenarier nedan):")
    for t in sorted(prices):
        c = prices[t]["Close"].dropna()
        if c.empty:
            print(f"    {t:<10} INGEN giltig prisdata")
            continue
        span_weeks = int((c.index.max() - c.index.min()).days / 7) + 1
        gaps = span_weeks - len(c)
        print(f"    {t:<10} {c.index.min().date()} → {c.index.max().date()} "
              f"({len(c)} veckor, {gaps} luckor inom intervallet)")


def main():
    tickers = sorted({t for w in SCENARIOS.values() for t in w})
    print(f"[backtest_core_allocation] hämtar veckodata för {len(tickers)} ETF:er: {', '.join(tickers)}")
    prices = fetch_weekly_data(tickers, start="2005-01-01", end=None, use_cache=True)
    missing = [t for t in tickers if t not in prices]
    if missing:
        print(f"[VARNING] ingen prisdata för: {', '.join(missing)} - scenarier som kräver dem hoppas över.")

    _diagnose_tickers(prices)

    print("\n===== KÄRN-ALLOKERING: bara påfyllnad, aldrig sälj (samma disciplin som next_buy()) =====")
    print(f"Månadsinsättning: {config.NEXT_BUY_DEFAULT_AMOUNT:,.0f} (instrumentens egen valuta, EUR) "
          f"· kostnad/köp: {config.ETF_ROT_COST_ONEWAY:.2%}\n".replace(",", " "))

    rows = []
    for label, weights in SCENARIOS.items():
        if any(t not in prices for t in weights):
            print(f"  {label:<70} HOPPAD (saknar prisdata)")
            continue
        r = simulate_accumulation(weights, prices)
        if r is None:
            print(f"  {label:<70} HOPPAD (< {156 // 52} år gemensam historik - se diagnosen ovan)")
            continue
        rows.append((label, r))
        s = r["nav_stats"]
        print(f"  {label}")
        print(f"    fönster {r['start']} → {r['end']} ({r['years']} år) · "
              f"NAV-CAGR {s['CAGR']} · Sharpe {s['Sharpe']} · MaxDD {s['Max Drawdown']} · "
              f"slutvärde {r['end_value']:,.0f} av {r['total_contributed']:,.0f} insatt "
              f"({_fmt_pct(r['gain_over_contributed'])})".replace(",", " "))

    if not rows:
        print("\n[backtest_core_allocation] inget scenario kunde köras - saknas prisdata helt?")
        return

    print("\n(NAV-CAGR/Sharpe/MaxDD är insättnings-NEUTRALA - jämförbara trots olika kapitalflöden. "
          "Slutvärde/insatt är den praktiska \"hur mycket pengar hade jag haft\"-siffran för EXAKT "
          "samma månadsinsättning i just den korgen. OBS olika scenarier kan ha olika fönster - "
          "kortast gemensam historik i korgen styr, se datumen ovan.)")

    # ── MATCHAT FÖNSTER: PARVIS mot Endast ACWI, inte ett globalt minimum ────
    # BUGG (fixad): förra versionen klippte ALLA scenarier till det kortaste
    # gemensamma fönstret bland dem (2018, styrt av Kina/Indien-scenariot) -
    # det kastade bort 2014-2018 helt i onödan för ACWI-vs-World+EM-paret, som
    # kunde delat ett mycket längre fönster (2014-2026) sinsemellan. Rätt sätt
    # att göra en rättvis jämförelse är PARVIS: klipp ACWI till VARJE scenarios
    # EGNA fönster för sig, inte till det snävaste gemensamma för alla på en gång.
    acwi_label = "Endast ACWI (dagens kärna)"
    acwi_weights = SCENARIOS[acwi_label]
    print("\n===== MATCHAT FÖNSTER (Endast ACWI parvis klippt till varje scenarios EGET fönster) =====")
    for label, r in rows:
        if label == acwi_label:
            continue
        r_acwi = simulate_accumulation(acwi_weights, prices, start=r["start"])
        if r_acwi is None:
            print(f"  {label:<70} HOPPAD (ACWI för kort efter klippning)")
            continue
        print(f"  vs. {label}  (fönster {r['start']} → {r['end']}, {r['years']} år)")
        for sub_label, rr in ((acwi_label, r_acwi), (label, r)):
            s = rr["nav_stats"]
            print(f"    {sub_label:<68} NAV-CAGR {s['CAGR']} · Sharpe {s['Sharpe']} · "
                  f"MaxDD {s['Max Drawdown']} · slutvärde {rr['end_value']:,.0f} av "
                  f"{rr['total_contributed']:,.0f} insatt "
                  f"({_fmt_pct(rr['gain_over_contributed'])})".replace(",", " "))


if __name__ == "__main__":
    main()
