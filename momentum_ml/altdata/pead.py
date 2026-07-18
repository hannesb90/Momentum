"""
altdata/pead.py – Token-fri PEAD (Post-Earnings-Announcement Drift).

PEAD är en av de mest robusta anomalierna i litteraturen: aktier fortsätter att
driva i samma riktning som marknadens REAKTION på en rapport, i veckor efteråt.
Marknaden underreagerar på rapporter.

Vi har inga analytikerestimat (skulle kräva betaltjänst), så vi kan inte räkna
en klassisk SUE (standardized unexpected earnings). I stället används den
väldokumenterade token-fria proxyn: RAPPORTVECKANS ABNORMALA AVKASTNING (aktiens
avkastning minus marknadens den veckan) som mått på "surprise" (Chan–Jegadeesh–
Lakonishok 1996). Positiv reaktion → förväntad fortsatt drift upp, och tvärtom.

Rena, testbara funktioner. Rapportdatumen hämtas separat via MFN-flödet (körs på
Pi:n; molnet når inte MFN). is_report/extract_report_dates arbetar på MFN-poster,
compute_pead_panel på en veckopris-panel + datum-map – båda enhetstestbara utan
nätverk.
"""
import re
from typing import Dict, List, Iterable, Optional
import numpy as np
import pandas as pd

# Rubrik-nyckelord för svenska/engelska periodrapporter. Håll brett men undvik
# rena PM ("inbjudan till presentation av delårsrapport" fångas också, men den
# publiceras normalt samma vecka som rapporten så datumet blir rätt).
_REPORT_PATTERNS = [
    r"delårsrapport", r"bokslutskommuniké", r"kvartalsrapport", r"årsredovisning",
    r"halvårsrapport", r"niomånadersrapport", r"tremånadersrapport",
    r"\bq[1-4]\b", r"interim report", r"year-end report", r"quarterly report",
    r"half-year report", r"annual report",
]
_REPORT_RE = re.compile("|".join(_REPORT_PATTERNS), re.IGNORECASE)


def is_report(item: dict) -> bool:
    """True om en MFN-post är en periodrapport (via properties.type eller rubrik)."""
    if str(item.get("type", "")).lower() == "report":
        return True
    return bool(_REPORT_RE.search(str(item.get("title", ""))))


def extract_report_dates(items: Iterable[dict]) -> Dict[str, List[pd.Timestamp]]:
    """
    MFN-poster → {ticker: sorterad lista av rapportdatum}. En post kan bära flera
    tickers (author.tickers); datumet tas från 'published'. Dubbletter (samma
    ticker+datum, t.ex. inbjudan + rapport) slås ihop.
    """
    out: Dict[str, set] = {}
    for it in items:
        if not is_report(it):
            continue
        ts = pd.to_datetime(it.get("published"), errors="coerce")
        if pd.isna(ts):
            continue
        ts = ts.normalize()
        tickers = it.get("tickers") or []
        if isinstance(tickers, str):
            tickers = [tickers]
        for t in tickers:
            out.setdefault(str(t), set()).add(ts)
    return {t: sorted(dates) for t, dates in out.items()}


def compute_pead_panel(
    price_panel: pd.DataFrame,
    report_dates: Dict[str, List[pd.Timestamp]],
    drift_weeks: int = 8,
    market: Optional[pd.Series] = None,
) -> pd.DataFrame:
    """
    Bygger en PEAD-signalpanel (samma form som price_panel: veckoindex × tickers).

    För varje ticker och vecka t:
      - hitta senaste rapport inom de senaste `drift_weeks` veckorna,
      - abnormal reaktion = aktiens avkastning rapportveckan − marknadens samma vecka,
      - signal = abnormal_reaktion × linjär avklingning (1 vid rapportveckan → 0
        efter drift_weeks). Ingen färsk rapport → 0.

    Kausalt: signalen vid t bygger bara på rapporter t.o.m. t och reaktionen som
    redan realiserats. `market` default = likaviktad panel-avkastning.
    """
    px = price_panel.sort_index()
    rets = px.pct_change()
    if market is None:
        market = rets.mean(axis=1)     # likaviktad marknadsproxy
    abn = rets.sub(market, axis=0)     # abnormal avkastning per vecka

    weeks = px.index
    signal = pd.DataFrame(0.0, index=weeks, columns=px.columns)

    for ticker, dates in report_dates.items():
        if ticker not in px.columns or not dates:
            continue
        col_abn = abn[ticker]
        # Mappa varje rapportdatum till veckobaren (första veckan >= datum).
        for d in dates:
            pos = weeks.searchsorted(pd.Timestamp(d).normalize(), side="left")
            if pos >= len(weeks):
                continue
            ann_week = weeks[pos]
            reaction = col_abn.get(ann_week, np.nan)
            if pd.isna(reaction):
                continue
            # Lägg ut den avklingande driftsignalen över drift_weeks efter rapporten.
            for k in range(drift_weeks):
                wi = pos + k
                if wi >= len(weeks):
                    break
                decay = 1.0 - k / drift_weeks
                w = weeks[wi]
                # Senaste rapporten vinner om två överlappar (skriv, inte addera).
                signal.iat[wi, signal.columns.get_loc(ticker)] = reaction * decay

    return signal
