"""
altdata/fund_merge.py – DELAD sammanslagning av text-extraherade fundamenta
(fundamentals_from_mfn/_pdf.csv, redan pm_id-mergade) med Avanza-datan
(fundamentals_from_avanza.csv). Används av BÅDE value_screener._load_
fundamentals och feature_engineering._load_fundamentals_growth – tidigare
duplicerade de logiken, och båda kopiorna bar på samma tre buggar
(upptäckta i granskning mot RIKTIG diagnose-data för AAK.ST):

  1. ÅRSLÖSA PERIODER SLOGS IHOP ÖVER ÅRSGRÄNSER: text-rader kan ha period
     'Q3'/'Helår' UTAN år (PM-titel utan årtal – verkliga exempel i AAK:s
     historik 2010–2017). En groupby på (ticker, period) slog ihop Q3 2010
     med Q3 2017 till EN kimär-rad med blandade fält från olika år.
  2. OLIKA PM FÖR SAMMA PERIOD KOLLAPSADE: bokslutskommunikén (feb) och
     årsredovisningen (apr) är båda 'Helår 2025' – mergen blandade deras
     fält och tidsstämplar, så ett fält publicerat i april kunde hamna
     under februaris published-datum: en ~2 månaders LOOKAHEAD-läcka in i
     feature_engineerings point-in-time-features.
  3. sort_values utan kind='stable' gjorde vilken text-rad som 'vann' inom
     en grupp icke-deterministiskt mellan körningar.

Designen här undviker alla tre: text-rader slås ALDRIG ihop med varandra
(rad-per-PM bevaras, published orörd per rad). Avanza-rader FYLLER bara
NaN-celler i text-rader med samma (ticker, period) – och bara för perioder
MED årtal, den enda entydiga nyckeln – eller läggs till som egna rader för
perioder text-källorna helt saknar. En redan populerad text-cell skrivs
aldrig över (samma prioritet som tidigare: narrativ/tabell-extraktionen är
verifierad mot fler skarpa exempel än Avanza-mappningen).
"""
import re

_YEAR_RE = re.compile(r"(?:19|20)\d{2}")

# Identitets-/metadatafält som ALDRIG fylls från Avanza in i en text-rad –
# text-raden behåller sin egen point-in-time-stämpel och proveniens.
_NO_FILL = ("ticker", "period", "pm_id", "published", "title")


def fill_from_avanza(text_df, avanza_df):
    """(text_df, avanza_df) -> en DataFrame. Endera får vara None/tom.
    text_df förväntas redan vara pm_id-mergad (mfn+pdf fältvis per PM)."""
    import pandas as pd

    t_empty = text_df is None or text_df.empty
    a_empty = avanza_df is None or avanza_df.empty
    if t_empty and a_empty:
        return pd.DataFrame()
    if a_empty:
        return text_df.reset_index(drop=True)
    if t_empty:
        return avanza_df.reset_index(drop=True)

    t = text_df.reset_index(drop=True).copy()
    a = avanza_df.reset_index(drop=True).copy()
    if "period" not in t.columns or "period" not in a.columns or "ticker" not in t.columns:
        # utan gemensam nyckel: bara lägg ihop (gamla pre-merge-beteendet)
        return pd.concat([t, a], ignore_index=True, sort=False)

    def _keyable(df):
        # Bara perioder MED årtal är en entydig join-nyckel ('Q3 2017');
        # en årslös 'Q3' är det INTE (se modulens docstring, bugg 1).
        return (df["ticker"].notna() & df["period"].notna()
                & df["period"].astype(str).str.contains(_YEAR_RE).fillna(False))

    t_ok = _keyable(t)
    a_ok = _keyable(a)

    a_keyed = a[a_ok].set_index(["ticker", "period"])
    if not a_keyed.empty:
        # skulle Avanza mot förmodan ge dubbletter per (ticker, period):
        # första raden vinner, deterministiskt
        a_keyed = a_keyed.groupby(level=[0, 1], sort=False).first()

    if t_ok.any() and not a_keyed.empty:
        t_keys = pd.MultiIndex.from_frame(t.loc[t_ok, ["ticker", "period"]])
        aligned = a_keyed.reindex(t_keys)
        for c in a_keyed.columns:
            if c in _NO_FILL:
                continue
            if c not in t.columns:
                # fält som BARA Avanza har (t.ex. equity när text-CSV:n helt
                # saknar kolumnen, eller roe_avanza) – läggs till som ny
                # kolumn så matchade perioder ändå kan få värdet. object-
                # dtype: kolumnen kan bära BÅDE tal och enhetssträngar (Mkr)
                t[c] = pd.Series(None, index=t.index, dtype="object")
            cur = t.loc[t_ok, c]
            t.loc[t_ok, c] = cur.where(cur.notna(), aligned[c].to_numpy())
        matched = set(t_keys)
    else:
        matched = set()

    keep_a = [not (ok and (tick, per) in matched)
              for ok, tick, per in zip(a_ok, a["ticker"], a["period"])]
    return pd.concat([t, a[keep_a]], ignore_index=True, sort=False)
