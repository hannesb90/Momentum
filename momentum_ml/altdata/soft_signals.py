"""
altdata/soft_signals.py – TOKEN-FRI "mjuka värden"-modell: destillerar
LLM-kvalitetsbedömningen (quality_screener) till en LOKAL modell som körs
helt utan AI/tokens, på hela universumet, varje natt.

PROBLEMET: de mjuka värdena (vallgrav, ledning, skalbarhet, säljmomentum...)
kommer idag från en LLM som läser rapporttexterna – det kostar tokens och
täcker bara de bolag screenern körts på. Resten av universumet står utan
mjuk bedömning.

LÖSNINGEN – DESTILLATION (lärare→elev):
  1. FEATURES (token-fria): kurerade svenska/engelska nyckelords-lexikon per
     mjuk dimension (vallgrav, global skalbarhet, säljmomentum, lönsamhets-
     bana, ton, varningsflaggor) räknas i bolagets senaste 12 månaders
     MFN-texter, normaliserat per 1000 ord. Plus meta-drag (PM-frekvens,
     rapportlängd, order-PM-andel). Plus HÅRDA nyckeltals-drag (tillväxt,
     marginal, vinsttecken ur samma fundamentals-CSV:er som value_screener –
     LLM-läraren läser ju siffrorna i rapporten, så eleven måste också få se
     dem) och TREND-drag (senaste halvårets ton/säljmomentum mot halvåret
     före – accelererar eller avtar bolagets egen kommunikation?).
  2. LABELS: de LLM-betyg som REDAN finns (quality_screener-cachen,
     composite 0-5) – redan betalda tokens, återanvänds som facit.
  3. MODELL: LightGBM-regressor (samma bibliotek som huvudpipelinen redan
     kräver) tränas features→composite. 5-fold CV rapporteras ÄRLIGT mot
     en alltid-medelvärdet-baseline – slår modellen inte baselinen (eller
     är etiketterna < MIN_LABELS) används i stället en ren lexikon-komposit,
     tydligt märkt i utdata ("lexikon", inte "destillerad").
  4. RÖDA FLAGGOR är alltid REGELBASERADE (going concern, vinstvarning,
     nyemission, kontrollbalansräkning...) – de ska aldrig bero på en modell.

    python -m altdata.soft_signals train           # destillera (kräver LLM-labels)
    python -m altdata.soft_signals score large     # poängsätt HELA segmentet, token-fritt
    python -m altdata.soft_signals explain AAK.ST  # visa features/flaggor för ett bolag

Skriver <results_dir>/soft_signals.csv. portfolio._load_scores använder
soft_score som KVALITETS-FALLBACK enbart där LLM-betyg saknas (LLM:en vinner
alltid när den finns) – märkt i why-etiketten så det aldrig kan förväxlas.

ÄRLIGA BEGRÄNSNINGAR:
  · Eleven kan aldrig bli bättre än läraren – och läraren (LLM på PM-text)
    är själv en heuristik, inte bevisad edge.
  · Lexikonen är kurerade, inte inlärda – ett bolag som beskriver samma sak
    med ovanliga ord missas. Utöka listorna när misses upptäcks.
  · PM-text är bolagets EGEN marknadsföring – tonen är systematiskt positiv.
    Percentil-ranken (relativt ANDRA bolags PM) neutraliserar det delvis.
"""
import sys
import csv
import json
import re
import datetime as dt
from pathlib import Path
from typing import Dict, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

# ── Lexikon per mjuk dimension (svenska + engelska, ordstams-regex) ──────────
# Kurerade mot quality_screenerns taxonomi (moat/global/scalable/sales/mgmt/
# profit_path). Räknas per 1000 ord → jämförbart mellan pratiga och tysta bolag.
_LEXICON: Dict[str, str] = {
    "moat": (r"marknadsledande|marknadsledare|ledande\s+(?:position|aktör|leverantör)"
             r"|återkommande\s+intäkter|prenumeration|abonnemang|saas|licensintäkter"
             r"|ramavtal|fleråri\w+\s+avtal|långsiktig\w*\s+avtal|inträdesbarriär"
             r"|prissättningskraft|prishöjning\w*|patent|proprietär|market.?leading|recurring\s+revenue"),
    "global_scale": (r"internationell\w*|expansion|nya\s+marknader|lanser\w+\s+i"
                     r"|globalt?|skalbar\w*|distributörsavtal|partneravtal|återförsäljare"
                     r"|nordamerika|usa|tyskland|europa|asien|utanför\s+sverige|international\s+expansion"),
    "sales_momentum": (r"orderingång\w*|rekordorder|genombrottsorder|ny\s+order|ordervärde"
                       r"|avtal\s+värt|kontrakt\s+värt|orderbok\w*|ökad\s+försäljning"
                       r"|rekordkvartal|rekordomsättning|order\s+intake|record\s+quarter"),
    "profit_path": (r"lönsam\w*|positivt\s+kassaflöde|break.?even|svarta\s+siffror"
                    r"|förbättrad\w*\s+marginal\w*|marginalförbättring|kostnadskontroll"
                    r"|skalfördelar|bruttomarginal\w*\s+(?:ökade|förbättrades|stärktes)|profitab\w+"),
    "guidance_up": (r"höjer\s+(?:prognos|utsikter|mål)|uppgraderar|över\s+förväntan"
                    r"|starkare\s+än\s+väntat|upprepar\s+(?:prognos|mål)|raises\s+(?:guidance|outlook)"),
    "tone_pos": (r"rekord\w*|stark\w*|förbättr\w*|ökad\s+efterfrågan|välfylld\w*|milstolpe"
                 r"|framgångsri\w+|överträff\w*|accelerer\w*"),
    "tone_neg": (r"svag\w*|utmanande|motvind|osäkerhet|förlust\w*|minskad\s+efterfrågan"
                 r"|prispress|försening\w*|lägre\s+än\s+väntat|besparingsprogram|varsel"),
}
# RÖDA FLAGGOR – regelbaserade, ALDRIG modellberoende. Var och en är en
# dokumenterad, allvarlig händelse (inte ton) → listas med namn i utdata.
# PRECISION FÖRE TÄCKNING: en flagga eskalerar säljvakten och sänker mjuk-
# poängen hårt, så en falsk träff på standard-boilerplate är mycket värre än
# en missad ovanlig formulering. Varje mönster är verifierat mot vanliga
# godartade fraser (se test_soft_signals): "av- och nedskrivningar" (D&A-raden
# i VARJE resultaträkning), "VD lämnar sina kommentarer", "nyemission för att
# finansiera förvärvet" (offensiv, inte nöd) får INTE flagga.
_RED_FLAGS: Dict[str, str] = {
    "going_concern": r"going\s+concern|väsentlig\w*\s+osäkerhet\w*\s+(?:om|kring|avseende)\s+fortsatt\s+drift|fortsatt\s+drift\s+är\s+osäker",
    "kontrollbalansräkning": r"kontrollbalansräkning",
    # företrädesemission/nyemission är ETT ord; "riktad emission" två.
    "nyemission_nöd": r"(?:nyemission|företrädesemission|riktad\s+(?:ny)?emission)\s+för\s+att\s+(?:säkra|stärka|finansiera\s+(?:fortsatt|löpande))|likviditetsbrist|behov\s+av\s+ytterligare\s+finansiering",
    "vinstvarning": r"vinstvarning|sänker\s+(?:prognos|utsikter|sina?\s+mål)|profit\s+warning|lowers\s+(?:guidance|outlook)",
    "revisor": r"revisor\w*\s+(?:anmärkning|reservation|avstyrk\w*)|oren\s+revisionsberättelse",
    # "lämnar" kräver post/tjänst/bolag-objekt ("VD lämnar sina kommentarer" är
    # standard-PM-språk); "avgår som VD" fångar omvänd ordföljd.
    "ledningsavhopp": (r"(?:vd|verkställande\s+direktör\w*|cfo|finanschef\w*)\s+"
                       r"(?:avgår|entledigas|har\s+avgått|lämnar\s+(?:sin\s+(?:post|tjänst|roll)|bolaget|sitt\s+uppdrag))"
                       r"|avgår\s+som\s+(?:vd|verkställande\s+direktör|cfo|finanschef)"),
    # Bara ny-annonserade nedskrivningar av substans (goodwill/belopp) – INTE
    # resultaträkningens stående "av- och nedskrivningar"-rad.
    "nedskrivning": (r"nedskrivning\w*\s+av\s+goodwill|goodwillnedskrivning|nedskrivningsbehov"
                     r"|(?:gör|redovisar|beslutat\s+om)\s+(?:en\s+)?nedskrivning"
                     r"|impairment\s+(?:charge|loss|of\s+goodwill)"),
}
_LEX_RE = {k: re.compile(v, re.I) for k, v in _LEXICON.items()}
_FLAG_RE = {k: re.compile(v, re.I) for k, v in _RED_FLAGS.items()}

_FEATURE_ORDER = (list(_LEXICON.keys())
                  + ["tone_score", "n_pm_12m", "n_reports_12m", "avg_pm_len", "red_flag_count"]
                  # Hårda + trend-drag (se _hard_features/_trend_features). Saknat
                  # värde = NaN, ALDRIG 0.0 – LightGBM hanterar missing nativt,
                  # medan 0.0 hade betytt "noll tillväxt"/"oförändrad ton" (fejk-
                  # signal för bolag vi bara saknar data om).
                  + ["hard_rev_growth", "hard_margin", "hard_np_pos",
                     "hard_growth_share", "hard_n_reports",
                     "tone_trend", "sales_trend"])
_MODEL_PATH = "cache/soft_model.txt"
_META_PATH = "cache/soft_model_meta.json"
MIN_LABELS = 20          # färre LLM-facit än så → lexikon-läge (ingen låtsas-ML)


def _model_file() -> Path:
    return Path(config.anchor(_MODEL_PATH))


def _meta_file() -> Path:
    return Path(config.anchor(_META_PATH))


def _company_text(ticker: str, months: int = 12) -> Tuple[str, int, int]:
    """(sammanslagen PM-text senaste `months`, antal PM, antal rapport-PM)."""
    from altdata.mfn_fundamentals import is_report_pm
    p = Path(config.MFN_CACHE_DIR) / f"{ticker}.json"
    if not p.exists():
        return "", 0, 0
    try:
        items = json.loads(p.read_text(encoding="utf-8")).get("items", [])
    except Exception:  # noqa: BLE001
        return "", 0, 0
    cutoff = (dt.date.today() - dt.timedelta(days=months * 30)).isoformat()
    texts, n_pm, n_rep = [], 0, 0
    for it in items:
        if str(it.get("published") or "")[:10] < cutoff:
            continue
        n_pm += 1
        if is_report_pm(it):
            n_rep += 1
        texts.append(str(it.get("title") or "") + "\n" + str(it.get("text") or ""))
    return "\n\n".join(texts), n_pm, n_rep


_MIN_WORDS = 300         # mindre 12-månaders-text än så → för tunt för en mjuk bedömning
_RATE_CAP = 10.0         # winsorisering av lexikon-frekvenser (träffar per 1000 ord)


def extract_features(ticker: str) -> Optional[Dict[str, float]]:
    """Token-fria drag för ETT bolag. None om MFN-texten saknas ELLER är för
    tunn (< _MIN_WORDS ord på 12 månader) – hellre ärligt obedömd än en
    "mjuk poäng" byggd på en enda mening.

    Frekvenserna winsoriseras vid _RATE_CAP: utan taket exploderade per-1000-
    ord-talen för korta texter (EN kort bullish PM gav moat ≈ 79/1k mot ~1-3
    för normala bolag) och förvred både ML-features och lexikon-kompositen –
    upptäckt i granskning, inte hypotetiskt."""
    text, n_pm, n_rep = _company_text(ticker)
    if not text:
        return None
    n_words = len(text.split())
    if n_words < _MIN_WORDS:
        return None
    feats = _text_features(text)
    feats["n_pm_12m"] = float(n_pm)
    feats["n_reports_12m"] = float(n_rep)
    feats["avg_pm_len"] = n_words / max(n_pm, 1)
    return feats


def _text_features(text: str) -> Dict[str, float]:
    """Lexikon-drag för EN godtycklig text (winsoriserade per-1000-ord-
    frekvenser + ton + flaggor). Delas av 12-månaders-bedömningen
    (extract_features), korskontrollen och den bakåtblickande utfalls-
    modellen (per enskild rapport-text)."""
    n_words = max(len(text.split()), 1)
    per_k = 1000.0 / n_words
    feats: Dict[str, float] = {}
    for k, rx in _LEX_RE.items():
        feats[k] = min(len(rx.findall(text)) * per_k, _RATE_CAP)
    pos, neg = feats.get("tone_pos", 0.0), feats.get("tone_neg", 0.0)
    feats["tone_score"] = (pos - neg) / (pos + neg + 0.5)
    flags = [name for name, rx in _FLAG_RE.items() if rx.search(text)]
    feats["red_flag_count"] = float(len(flags))
    feats["_flags"] = flags          # metadata, inte modell-input (prefix _)
    return feats


def _lexicon_score(feats: Dict[str, float]) -> float:
    """Ren lexikon-komposit 0-5 – fallback när ML-destillation inte är
    försvarbar (för få labels eller sämre än baseline i CV). Viktningen är
    kurerad, inte inlärd: positiva dimensioner lyfter, ton justerar,
    röda flaggor sänker HÅRT (en going concern ska aldrig döljas av bra ton)."""
    core = (feats.get("moat", 0) + feats.get("global_scale", 0)
            + feats.get("sales_momentum", 0) + feats.get("profit_path", 0)
            + 2.0 * feats.get("guidance_up", 0))
    base = 2.5 + min(core, 5.0) * 0.35 + feats.get("tone_score", 0.0) * 0.75
    base -= 1.2 * feats.get("red_flag_count", 0.0)
    return round(max(0.0, min(5.0, base)), 2)


# ── Hårda + trend-drag (destillations-features utöver lexikonen) ─────────────
_GROWTH_CAP = 3.0        # winsorisering av YoY-tillväxt (+300 % räcker som "extremt")
_TREND_MIN_WORDS = 150   # tunnare halvårsfönster än så → trend obedömbar (NaN)


def _hard_features(rows: list) -> Dict[str, float]:
    """Hårda nyckeltals-drag ur samma fundamentals-CSV:er som value_screener
    läser (rows = bolagets rader sorterade på published, ur _fund_rows).
    LLM-läraren LÄSER siffrorna i rapporttexten när den sätter sitt betyg –
    en elev som bara ser nyckelords-frekvenser kan därför aldrig komma nära.
    Alla drag är enhets-oberoende kvoter/tecken av SAMMA rads fält (ingen
    Mkr/tkr-skalning behövs, samma princip som crosscheck). Saknat = NaN."""
    nan = float("nan")
    out = {"hard_rev_growth": nan, "hard_margin": nan, "hard_np_pos": nan,
           "hard_growth_share": nan, "hard_n_reports": float(len(rows))}
    if not rows:
        return out
    latest = rows[-1]
    rev, prior = _fnum(latest.get("revenue")), _fnum(latest.get("revenue_prior"))
    npf = _fnum(latest.get("net_profit"))
    if rev is not None and prior not in (None, 0.0):
        out["hard_rev_growth"] = max(-1.0, min((rev - prior) / abs(prior), _GROWTH_CAP))
    if npf is not None and rev not in (None, 0.0):
        out["hard_margin"] = max(-1.0, min(npf / abs(rev), 1.0))
    if npf is not None:
        out["hard_np_pos"] = 1.0 if npf > 0 else 0.0
    grew = []
    for r in rows[-4:]:
        rv, pv = _fnum(r.get("revenue")), _fnum(r.get("revenue_prior"))
        if rv is not None and pv not in (None, 0.0):
            grew.append(rv > pv)
    if grew:
        out["hard_growth_share"] = sum(grew) / len(grew)
    return out


def _window_text(ticker: str, start_days: int, end_days: int) -> str:
    """Sammanslagen PM-text i fönstret [idag-start_days, idag-end_days)."""
    p = Path(config.MFN_CACHE_DIR) / f"{ticker}.json"
    if not p.exists():
        return ""
    try:
        items = json.loads(p.read_text(encoding="utf-8")).get("items", [])
    except Exception:  # noqa: BLE001
        return ""
    lo = (dt.date.today() - dt.timedelta(days=start_days)).isoformat()
    hi = (dt.date.today() - dt.timedelta(days=end_days)).isoformat()
    return "\n\n".join(str(it.get("title") or "") + "\n" + str(it.get("text") or "")
                       for it in items if lo <= str(it.get("published") or "")[:10] < hi)


def _trend_features(ticker: str) -> Dict[str, float]:
    """Riktningen i bolagets egen kommunikation: senaste halvåret mot halvåret
    före. En statisk 12-månaders-frekvens kan inte skilja ett bolag vars ton
    är på väg upp från ett vars ton är på väg ned – trenden kan. För tunna
    fönster = NaN (ärligt obedömbart), inte 0 (fejk-stabilitet)."""
    nan = float("nan")
    recent, prior = _window_text(ticker, 183, 0), _window_text(ticker, 365, 183)
    if len(recent.split()) < _TREND_MIN_WORDS or len(prior.split()) < _TREND_MIN_WORDS:
        return {"tone_trend": nan, "sales_trend": nan}
    fr, fp = _text_features(recent), _text_features(prior)
    return {"tone_trend": fr["tone_score"] - fp["tone_score"],
            "sales_trend": fr["sales_momentum"] - fp["sales_momentum"]}


def _enrich(ticker: str, feats: Dict[str, float], fund_map: Dict[str, list]) -> Dict[str, float]:
    """Lägg hårda + trend-drag ovanpå text-dragen (in-place, returnerar feats)."""
    feats.update(_hard_features(fund_map.get(ticker) or []))
    feats.update(_trend_features(ticker))
    return feats


_OUTCOME_FEATURES = list(_LEXICON.keys()) + ["tone_score", "red_flag_count"]
_OUTCOME_MODEL_PATH = "cache/soft_outcome_model.txt"
_OUTCOME_META_PATH = "cache/soft_outcome_meta.json"
MIN_PAIRS = 150          # färre historiska (rapport → nästa rapport)-par → ingen utfallsmodell


def _outcome_model_file() -> Path:
    return Path(config.anchor(_OUTCOME_MODEL_PATH))


def _outcome_meta_file() -> Path:
    return Path(config.anchor(_OUTCOME_META_PATH))


def _fund_rows(segment: str) -> Dict[str, list]:
    """{ticker: [fundamentals-rader sorterade på published]} ur samma CSV:er
    som value_screener läser – ger de HÅRDA facit-siffrorna per rapport."""
    import pandas as pd
    seg = config.SEGMENTS.get(segment) or config.SEGMENTS[config.DEFAULT_SEGMENT]
    rd = Path(config.anchor(seg["results_dir"]))
    frames = []
    for fname in ("fundamentals_from_mfn.csv", "fundamentals_from_pdf.csv"):
        p = rd / fname
        if p.exists():
            try:
                frames.append(pd.read_csv(p))
            except Exception:  # noqa: BLE001
                pass
    if not frames:
        return {}
    df = pd.concat(frames, ignore_index=True)
    if "ticker" not in df.columns:
        return {}
    df = df.dropna(subset=["ticker"]).sort_values("published")
    return {t: g.to_dict("records") for t, g in df.groupby("ticker")}


def _report_texts(ticker: str) -> Dict[str, str]:
    """{pm_id: rapporttext} ur MFN-cachen – kopplar mjuk text till hård rad."""
    from altdata.mfn_fundamentals import is_report_pm
    p = Path(config.MFN_CACHE_DIR) / f"{ticker}.json"
    if not p.exists():
        return {}
    try:
        items = json.loads(p.read_text(encoding="utf-8")).get("items", [])
    except Exception:  # noqa: BLE001
        return {}
    return {str(it.get("id")): (str(it.get("title") or "") + "\n" + str(it.get("text") or ""))
            for it in items if is_report_pm(it) and it.get("text")}


def _latest_report_text(ticker: str) -> Optional[str]:
    """Texten för bolagets SENASTE rapport-PM (per published-datum – pm-id:n
    är godtyckliga strängar och får ALDRIG användas för kronologi)."""
    from altdata.mfn_fundamentals import is_report_pm
    p = Path(config.MFN_CACHE_DIR) / f"{ticker}.json"
    if not p.exists():
        return None
    try:
        items = json.loads(p.read_text(encoding="utf-8")).get("items", [])
    except Exception:  # noqa: BLE001
        return None
    reps = [it for it in items if is_report_pm(it) and it.get("text")]
    if not reps:
        return None
    latest = max(reps, key=lambda it: str(it.get("published") or ""))
    return str(latest.get("title") or "") + "\n" + str(latest.get("text") or "")


def _fnum(v):
    try:
        f = float(v)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def crosscheck(feats: Dict[str, float], latest_row: dict):
    """KORSKONTROLL mjukt-mot-hårt ("walk the talk"): håller bolagets PRAT
    (lexikon-anspråk i texten) när det möter bolagets SIFFROR (extraherade
    hårda fält ur samma rapportflöde)?

    Returnerar (walk_score, flagga): walk_score i [0,1] = andel anspråk som
    bekräftas av siffrorna (None om inga bedömbara anspråk – tyst bolag är
    inte lögnaktigt bolag). Flaggan "prat_utan_täckning" sätts när minst två
    anspråk kan prövas och högst en tredjedel håller – den rider sedan på
    samma röda-flagg-bana som going concern m.fl. (säljvakt + poängavdrag).
    Kvoterna är enhets-oberoende (tecken/kvot av samma rads fält)."""
    if not latest_row:
        return None, None
    rev, rev_prior = _fnum(latest_row.get("revenue")), _fnum(latest_row.get("revenue_prior"))
    npf = _fnum(latest_row.get("net_profit"))
    rev_growth = ((rev - rev_prior) / abs(rev_prior)
                  if (rev is not None and rev_prior not in (None, 0.0)) else None)
    confirms = contradicts = 0
    # Anspråk 1: säljmomentum-språk ("rekordorder", "ökad försäljning"...)
    if feats.get("sales_momentum", 0) >= 1.0 and rev_growth is not None:
        confirms, contradicts = (confirms + 1, contradicts) if rev_growth > 0 else (confirms, contradicts + 1)
    # Anspråk 2: lönsamhets-språk ("förbättrad marginal", "positivt kassaflöde"...)
    if feats.get("profit_path", 0) >= 1.0 and npf is not None:
        confirms, contradicts = (confirms + 1, contradicts) if npf > 0 else (confirms, contradicts + 1)
    # Anspråk 3: starkt positiv ton överlag
    if feats.get("tone_score", 0) >= 0.3 and (rev_growth is not None or npf is not None):
        ok = (rev_growth is not None and rev_growth > 0) or (npf is not None and npf > 0)
        confirms, contradicts = (confirms + 1, contradicts) if ok else (confirms, contradicts + 1)
    total = confirms + contradicts
    if total == 0:
        return None, None
    walk = round(confirms / total, 2)
    flag = "prat_utan_täckning" if (total >= 2 and walk <= 0.34) else None
    return walk, flag


def validate() -> None:
    """BAKÅTBLICKANDE VALIDERING: förutsäger de mjuka dragen i rapport N det
    HÅRDA utfallet i rapport N+1 (intäkterna växer YoY)? Bygger (text_N →
    utfall_N+1)-par ur hela historiken, rapporterar per-dimension-diagnostik
    ärligt, och tränar en utfallsmodell BARA om den slår majoritets-baselinen
    i 5-fold CV. Sparad modell blandas in i soft_score av score()
    (config.SOFT_OUTCOME_BLEND) – då lär sig modellen av FACIT, inte bara av
    LLM-lärarens åsikt."""
    import numpy as np
    X_rows, y = [], []
    for seg_name in config.SEGMENTS:
        for t, rows in _fund_rows(seg_name).items():
            texts = _report_texts(t)
            for i in range(len(rows) - 1):
                nxt = rows[i + 1]
                rev, prior = _fnum(nxt.get("revenue")), _fnum(nxt.get("revenue_prior"))
                if rev is None or prior in (None, 0.0):
                    continue
                txt = texts.get(str(rows[i].get("pm_id")))
                if not txt or len(txt.split()) < 60:
                    continue
                f = _text_features(txt)
                X_rows.append([f.get(k, 0.0) for k in _OUTCOME_FEATURES])
                y.append(1 if rev > prior else 0)
    n = len(y)
    print(f"[soft_signals validate] {n} historiska (rapport → nästa rapport)-par")
    if n == 0:
        return
    X, y = np.array(X_rows), np.array(y)
    base = max(y.mean(), 1 - y.mean())
    print(f"  basnivå (majoritetsklass): {base:.1%} – tillväxt nästa rapport i {y.mean():.1%} av paren")
    # Ärlig per-dimension-diagnostik: medelvärde i tillväxt- vs krymp-gruppen.
    for j, name in enumerate(_OUTCOME_FEATURES):
        up, dn = X[y == 1, j].mean(), X[y == 0, j].mean()
        mark = "→" if abs(up - dn) < 0.05 else ("↑" if up > dn else "↓")
        print(f"    {name:<16} tillväxt {up:6.2f}  krymper {dn:6.2f}  {mark}")
    if n < MIN_PAIRS:
        print(f"  Under {MIN_PAIRS} par – ingen utfallsmodell tränas (diagnostiken ovan gäller ändå).")
        _outcome_model_file().unlink(missing_ok=True)
        _outcome_meta_file().unlink(missing_ok=True)
        return
    import lightgbm as lgb
    from sklearn.model_selection import KFold
    params = dict(objective="binary", metric="binary_logloss", verbosity=-1,
                  num_leaves=7, min_data_in_leaf=max(5, n // 20),
                  learning_rate=0.06, feature_fraction=0.8, seed=42)
    accs = []
    for tr, te in KFold(5, shuffle=True, random_state=42).split(X):
        m = lgb.train(params, lgb.Dataset(X[tr], y[tr]), num_boost_round=150)
        accs.append(float(((m.predict(X[te]) >= 0.5).astype(int) == y[te]).mean()))
    cv_acc = float(np.mean(accs))
    print(f"  CV-träffsäkerhet {cv_acc:.1%} vs baseline {base:.1%}")
    if cv_acc <= base:
        print("  Slår inte baselinen – ingen modell sparas (mjuk text har då inget mätbart "
              "prediktivt värde på nästa rapports hårda utfall – ärligt konstaterat).")
        _outcome_model_file().unlink(missing_ok=True)
        _outcome_meta_file().unlink(missing_ok=True)
        return
    booster = lgb.train(params, lgb.Dataset(X, y), num_boost_round=150)
    _outcome_model_file().parent.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(_outcome_model_file()))
    _outcome_meta_file().write_text(json.dumps({
        "features": _OUTCOME_FEATURES, "n_pairs": n,
        "cv_acc": round(cv_acc, 4), "baseline": round(base, 4),
        "trained": dt.date.today().isoformat()}, ensure_ascii=False), encoding="utf-8")
    print(f"  Utfallsmodell sparad → {_outcome_model_file()} (blandas in av score, "
          f"vikt {getattr(config, 'SOFT_OUTCOME_BLEND', 0.30)})")


def _load_outcome_model():
    if not (_outcome_model_file().exists() and _outcome_meta_file().exists()):
        return None, None
    try:
        import lightgbm as lgb
        meta = json.loads(_outcome_meta_file().read_text(encoding="utf-8"))
        if meta.get("features") != _OUTCOME_FEATURES:
            return None, None
        return lgb.Booster(model_file=str(_outcome_model_file())), meta
    except Exception:  # noqa: BLE001
        return None, None


def _load_labels() -> Dict[str, float]:
    """{ticker: LLM-composite} ur quality_screener-cachen (redan betalda
    tokens – återanvänds som destillations-facit)."""
    out = {}
    qdir = Path(config.QUALITY_CACHE_DIR)
    if not qdir.exists():
        return out
    for p in qdir.glob("*.json"):
        if p.name.startswith("_"):
            continue                      # _quant.json/_marketcaps.json = inte labels
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        comp = d.get("composite")
        if isinstance(comp, (int, float)) and comp > 0:
            out[p.stem] = float(comp)
    return out


def _matrix(feats_by_ticker: Dict[str, dict]):
    import numpy as np
    # Saknad feature = NaN (LightGBM:s nativa missing-hantering), inte 0.0 –
    # se kommentaren vid _FEATURE_ORDER. Lexikon-/meta-dragen finns alltid;
    # det är hård-/trend-dragen som kan saknas för enskilda bolag.
    X = np.array([[feats_by_ticker[t].get(f, float("nan")) for f in _FEATURE_ORDER]
                  for t in feats_by_ticker], dtype=float)
    return X, list(feats_by_ticker.keys())


def _fund_rows_all_segments() -> Dict[str, list]:
    """Fundamentals-rader över BÅDA segmenten (train/explain är segment-
    agnostiska – labels kommer ur en gemensam quality-cache)."""
    fund_all: Dict[str, list] = {}
    for seg_name in config.SEGMENTS:
        for t, rows in _fund_rows(seg_name).items():
            fund_all.setdefault(t, rows)
    return fund_all


# Litet, ärligt svep – varje kandidat utvärderas i SAMMA 5-fold-CV och
# vinnaren väljs på CV-MAE (inte på träningsdata). Fler kandidater än så
# vore överanpassning av själva svepet på några hundra labels.
_PARAM_GRID = (
    dict(num_leaves=7,  learning_rate=0.08, feature_fraction=0.8),
    dict(num_leaves=7,  learning_rate=0.05, feature_fraction=0.6),
    dict(num_leaves=15, learning_rate=0.05, feature_fraction=0.8),
    dict(num_leaves=31, learning_rate=0.08, feature_fraction=0.9),
)


# quality_screener (LLM-läraren) täcker AVSIKTLIGT bara microcap ex medtech
# (config.QUALITY_MARKET_CAP) - Large/Mid Cap och Health Care har därför
# NOLL facit-underlag. score() applicerar modellen på HELA segmentets
# universum (inkl. Large/Mid/Health Care) - utan en spärr extrapolerar
# modellen tyst utanför allt den någonsin sett. MIN_CATEGORY_LABELS = hur
# många etiketter en sektor/cap-nivå minst behöver för att LITAS på;
# under det används lexikon-läge för just de raderna (se score()).
MIN_CATEGORY_LABELS = 5


def train() -> None:
    """Destillera: träna LightGBM på (token-fria features → LLM-composite).
    Sveper _PARAM_GRID i 5-fold CV, rapporterar CV-MAE mot alltid-medel-
    baselinen OCH Spearman-rankkorrelation (portföljen använder poängen för
    RANGORDNING – rank-IC är därför det mått som faktiskt betyder något),
    och vägrar spara en modell som inte slår baselinen. Spårar även VILKA
    sektorer/cap-nivåer facit-urvalet faktiskt täcker (se MIN_CATEGORY_LABELS
    ovan) - score() faller tillbaka på lexikon för kategorier utanför det,
    istället för att tyst extrapolera en modell som aldrig sett exemplet."""
    import numpy as np
    from collections import Counter
    from data.data_loader import load_sweden_universe
    labels = _load_labels()
    print(f"[soft_signals train] {len(labels)} LLM-betygsatta bolag som facit")
    if len(labels) < MIN_LABELS:
        print(f"  För få labels (< {MIN_LABELS}) för försvarbar ML – score kör lexikon-läge.")
        _model_file().unlink(missing_ok=True)
        _meta_file().unlink(missing_ok=True)
        return

    fund_all = _fund_rows_all_segments()
    feats = {}
    for t in labels:
        f = extract_features(t)
        if f:
            feats[t] = _enrich(t, f, fund_all)
    if len(feats) < MIN_LABELS:
        print(f"  Bara {len(feats)} av dem har MFN-text – för få. Lexikon-läge gäller.")
        _model_file().unlink(missing_ok=True)
        return
    X, tickers = _matrix(feats)
    y = np.array([labels[t] for t in tickers])

    # Facit-täckning per sektor/cap-nivå (över HELA universumet, inte ett
    # enskilt segment - facit-bolagen kan i princip höra till vilket segment
    # som helst även om quality_screener idag bara körs mot microcap).
    _, sector_map, cap_map, _ = load_sweden_universe(min_market_cap=None)
    sec_counts = Counter(sector_map.get(t, "okänd") for t in tickers)
    cap_counts = Counter(cap_map.get(t, "okänd") for t in tickers)
    covered_sectors = sorted(s for s, n in sec_counts.items() if n >= MIN_CATEGORY_LABELS)
    covered_caps = sorted(c for c, n in cap_counts.items() if n >= MIN_CATEGORY_LABELS)
    uncovered_sec = sorted(s for s, n in sec_counts.items() if 0 < n < MIN_CATEGORY_LABELS)
    print(f"  Facit-täckning: sektorer {covered_sectors}")
    print(f"                  cap-nivåer {covered_caps}")
    if uncovered_sec:
        print(f"  [tunt facit, <{MIN_CATEGORY_LABELS} etiketter] {uncovered_sec} - "
              f"körs i lexikon-läge av score() tills fler LLM-betyg finns")

    import lightgbm as lgb
    from scipy.stats import spearmanr
    from sklearn.model_selection import KFold
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    base_mae = float(np.mean([np.mean(np.abs(y[tr].mean() - y[te]))
                              for tr, te in kf.split(X)]))
    best = None   # (cv_mae, params, oof_preds)
    for g in _PARAM_GRID:
        params = dict(objective="regression", metric="mae", verbosity=-1,
                      min_data_in_leaf=max(3, len(y) // 10), seed=42, **g)
        oof = np.full_like(y, np.nan, dtype=float)
        for tr, te in kf.split(X):
            m = lgb.train(params, lgb.Dataset(X[tr], y[tr]), num_boost_round=200)
            oof[te] = m.predict(X[te])
        cv_mae = float(np.mean(np.abs(oof - y)))
        marker = ""
        if best is None or cv_mae < best[0]:
            best, marker = (cv_mae, params, oof), "  ← bäst hittills"
        print(f"    leaves={g['num_leaves']:<3} lr={g['learning_rate']:<5} "
              f"ff={g['feature_fraction']}  CV-MAE {cv_mae:.3f}{marker}")
    cv_mae, params, oof = best
    rho = spearmanr(oof, y).statistic
    rank_ic = float(rho) if rho == rho else 0.0   # NaN-vakt (konstanta prediktioner)
    print(f"  Bästa: CV-MAE {cv_mae:.3f} vs baseline (alltid medel) {base_mae:.3f}, "
          f"rank-IC (Spearman) {rank_ic:+.3f} på {len(y)} bolag, "
          f"composite-spann {y.min():.1f}-{y.max():.1f}")
    if cv_mae >= base_mae:
        print("  Modellen slår INTE baselinen – sparas inte (ärligt > låtsas-ML). "
              "score kör lexikon-läge tills fler LLM-labels finns.")
        _model_file().unlink(missing_ok=True)
        _meta_file().unlink(missing_ok=True)
        return
    booster = lgb.train(params, lgb.Dataset(X, y), num_boost_round=200)
    imp = sorted(zip(_FEATURE_ORDER, booster.feature_importance("gain")),
                 key=lambda kv: kv[1], reverse=True)
    total_gain = sum(v for _, v in imp) or 1.0
    print("  Viktigaste drag (andel av total gain): "
          + ", ".join(f"{k} {v / total_gain:.0%}" for k, v in imp[:6]))
    _model_file().parent.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(_model_file()))
    _meta_file().write_text(json.dumps({
        "features": _FEATURE_ORDER, "n_labels": len(y),
        "cv_mae": round(cv_mae, 4), "baseline_mae": round(base_mae, 4),
        "rank_ic": round(rank_ic, 4),
        "covered_sectors": covered_sectors, "covered_caps": covered_caps,
        "params": {k: v for k, v in params.items() if k in
                   ("num_leaves", "learning_rate", "feature_fraction", "min_data_in_leaf")},
        "trained": dt.date.today().isoformat(),
    }, ensure_ascii=False), encoding="utf-8")
    print(f"  Modell sparad → {_model_file()}  (används av 'score')")


def _load_model():
    if not _model_file().exists() or not _meta_file().exists():
        return None, None
    try:
        import lightgbm as lgb
        meta = json.loads(_meta_file().read_text(encoding="utf-8"))
        if meta.get("features") != _FEATURE_ORDER:
            return None, None            # feature-listan har ändrats → träna om
        return lgb.Booster(model_file=str(_model_file())), meta
    except Exception:  # noqa: BLE001
        return None, None


def score(segment: Optional[str] = None) -> None:
    """Poängsätt HELA segmentet token-fritt → results*/soft_signals.csv."""
    import numpy as np
    from data.data_loader import load_sweden_universe
    seg_name = segment or config.DEFAULT_SEGMENT
    seg_cfg = config.SEGMENTS.get(seg_name, config.SEGMENTS[config.DEFAULT_SEGMENT])
    tickers, sector_map, cap_map, name_map = load_sweden_universe(min_market_cap=seg_cfg["market_cap"])

    booster, meta = _load_model()
    mode = "destillerad ML" if booster is not None else "lexikon"
    labels = _load_labels()

    # Hårda rader: både korskontrollen och hård-/trend-dragen läser dem –
    # måste därför laddas INNAN feature-bygget (samma segment).
    hard_rows = _fund_rows(seg_name)

    rows = []
    feats_all: Dict[str, dict] = {}
    for t in tickers:
        if cap_map.get(t) == "Fond" or sector_map.get(t) == "Fond":
            continue
        f = extract_features(t)
        if f:
            feats_all[t] = _enrich(t, f, hard_rows)
    if not feats_all:
        print("[soft_signals] ingen MFN-text för segmentet – kör mfn_fetch först.")
        return

    # Facit-täckning (sparad av train(), se MIN_CATEGORY_LABELS): bolag vars
    # sektor ELLER cap-nivå saknar tillräckligt LLM-facit får INTE en ML-
    # extrapolerad poäng - de faller på lexikon-läge radvis, samma "hellre
    # ärligt obedömt än låtsad poäng"-princip som resten av modulen. Saknad
    # nyckel i äldre meta (innan detta fanns) = ingen spärr (bakåtkompatibelt).
    covered_sectors = set(meta.get("covered_sectors", [])) if meta else set()
    covered_caps = set(meta.get("covered_caps", [])) if meta else set()
    has_coverage_guard = bool(meta and "covered_sectors" in meta)

    def _in_coverage(t: str) -> bool:
        if not has_coverage_guard:
            return True
        return sector_map.get(t) in covered_sectors and cap_map.get(t) in covered_caps

    if booster is not None:
        ml_tickers = {t: f for t, f in feats_all.items() if _in_coverage(t)}
        pred_by_t = {t: _lexicon_score(f) for t, f in feats_all.items()}   # lexikon-golv för alla
        if ml_tickers:
            X, order = _matrix(ml_tickers)
            preds = np.clip(booster.predict(X), 0.0, 5.0)
            pred_by_t.update({t: float(p) for t, p in zip(order, preds)})
        n_out = len(feats_all) - len(ml_tickers)
        if n_out:
            print(f"  [facit-spärr] {n_out} bolag utanför ML:s facit-täckning "
                  f"(sektor/cap-nivå) – körs i lexikon-läge istället för extrapolerad ML.")
    else:
        pred_by_t = {t: _lexicon_score(f) for t, f in feats_all.items()}

    # Bakåtvaliderad utfallsmodell (validate): blandas in med konfigurerbar
    # vikt – lärarens åsikt (LLM-destillat/lexikon) + facitets historik.
    out_booster, out_meta = _load_outcome_model()
    blend_w = float(getattr(config, "SOFT_OUTCOME_BLEND", 0.30))
    if out_booster is not None and blend_w > 0:
        mode += "+utfall"

    for t, f in feats_all.items():
        base_score = pred_by_t[t]
        outcome_prob = None
        if out_booster is not None and blend_w > 0:
            latest_txt = _latest_report_text(t)
            if latest_txt:
                rf = _text_features(latest_txt)
                Xo = np.array([[rf.get(k, 0.0) for k in _OUTCOME_FEATURES]])
                outcome_prob = float(out_booster.predict(Xo)[0])
                base_score = (1 - blend_w) * base_score + blend_w * (outcome_prob * 5.0)
        # Korskontroll mjukt-mot-hårt: pratet prövas mot senaste hårda raden.
        rows_t = hard_rows.get(t) or []
        walk, walk_flag = crosscheck(f, rows_t[-1] if rows_t else None)
        flags = list(f.get("_flags", []))
        if walk_flag:
            flags.append(walk_flag)
        row_mode = mode if _in_coverage(t) else mode.replace("destillerad ML", "lexikon (utanför facit)")
        rows.append({
            "ticker": t, "name": name_map.get(t, t),
            "soft_score": round(base_score, 2),
            "mode": ("LLM" if t in labels else row_mode),   # facit-bolag märks som LLM-täckta
            "llm_composite": labels.get(t, ""),
            "outcome_prob": ("" if outcome_prob is None else round(outcome_prob, 3)),
            "walk_score": ("" if walk is None else walk),
            "tone_score": round(f["tone_score"], 3),
            "red_flag_count": len(flags),
            "red_flags": ";".join(flags),
            **{k: round(f[k], 3) for k in _LEXICON},
        })
    rows.sort(key=lambda r: r["soft_score"], reverse=True)
    out = Path(config.anchor(seg_cfg["results_dir"])) / "soft_signals.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    n_flag = sum(1 for r in rows if r["red_flag_count"])
    # Den globala `mode`-variabeln beskriver bara vilken modell som FINNS
    # (destillerad ML vs lexikon) - inte vad varje enskild rad faktiskt fick.
    # Facit-spärren kan tysta ner ML:n till 0 verkliga ML-rader för ett helt
    # segment (t.ex. "large" när facit bara täcker Small/Micro/Nano Cap) - då
    # vore "(destillerad ML)" i sammanfattningen direkt missvisande. Räkna
    # den faktiska fördelningen istället för att lita på den globala flaggan.
    from collections import Counter
    mode_counts = Counter(r["mode"] for r in rows)
    mode_breakdown = ", ".join(f"{n} {m}" for m, n in mode_counts.most_common())
    print(f"[soft_signals] {len(rows)} bolag poängsatta ({mode_breakdown}"
          + (f", CV-MAE {meta['cv_mae']} vs baseline {meta['baseline_mae']}" if meta else "")
          + f") → {out}")
    print(f"  {n_flag} bolag med röda flaggor. TOPP 10 (soft_score, token-fritt):")
    for r in rows[:10]:
        print(f"   {r['soft_score']:>4}  {r['ticker']:<12} {str(r['name'])[:24]:<24} "
              f"ton {r['tone_score']:+.2f}"
              + (f"  ⚑ {r['red_flags']}" if r["red_flags"] else ""))


def explain(ticker: str) -> None:
    f = extract_features((ticker or "").upper())
    if not f:
        print(f"Ingen MFN-text för {ticker}.")
        return
    f = _enrich((ticker or "").upper(), f, _fund_rows_all_segments())
    print(f"=== {ticker.upper()} – token-fria mjuk-drag (per 1000 ord) ===")
    for k in _LEXICON:
        print(f"  {k:<16} {f[k]:.2f}")
    print(f"  tone_score       {f['tone_score']:+.3f}")
    print(f"  PM 12m           {f['n_pm_12m']:.0f} (varav {f['n_reports_12m']:.0f} rapporter)")

    def _fmt(v):
        return "saknas" if v != v else f"{v:+.3f}"
    print(f"  hård tillväxt    {_fmt(f['hard_rev_growth'])}   marginal {_fmt(f['hard_margin'])}"
          f"   vinst>0 {_fmt(f['hard_np_pos'])}")
    print(f"  ton-trend 6m     {_fmt(f['tone_trend'])}   sälj-trend 6m {_fmt(f['sales_trend'])}")
    print(f"  röda flaggor     {f.get('_flags') or 'inga'}")
    print(f"  lexikon-score    {_lexicon_score(f)}/5")
    booster, _ = _load_model()
    if booster is not None:
        import numpy as np
        X, _ = _matrix({ticker.upper(): f})
        print(f"  ML-score         {float(np.clip(booster.predict(X)[0], 0, 5)):.2f}/5 (destillerad)")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "score"
    if cmd == "train":
        train()
    elif cmd == "validate":
        validate()
    elif cmd == "score":
        score(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "explain" and len(sys.argv) > 2:
        explain(sys.argv[2])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
