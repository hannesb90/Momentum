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
     rapportlängd, order-PM-andel).
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
from typing import Dict, List, Optional, Tuple

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
_RED_FLAGS: Dict[str, str] = {
    "going_concern": r"going\s+concern|väsentlig\w*\s+osäkerhet\w*\s+(?:om|kring|avseende)\s+fortsatt\s+drift|fortsatt\s+drift\s+är\s+osäker",
    "kontrollbalansräkning": r"kontrollbalansräkning",
    "nyemission_nöd": r"(?:företrädes|riktad)?\s*nyemission\s+för\s+att\s+(?:säkra|stärka|finansiera\s+(?:fortsatt|löpande))|likviditetsbrist|behov\s+av\s+ytterligare\s+finansiering",
    "vinstvarning": r"vinstvarning|sänker\s+(?:prognos|utsikter|sina?\s+mål)|profit\s+warning|lowers\s+(?:guidance|outlook)",
    "revisor": r"revisor\w*\s+(?:anmärkning|reservation|avstyrk\w*)|oren\s+revisionsberättelse",
    "ledningsavhopp": r"(?:vd|verkställande\s+direktör\w*|cfo|finanschef\w*)\s+(?:avgår|lämnar|entledigas|har\s+avgått)(?:\s+med\s+omedelbar\s+verkan)?",
    "nedskrivning": r"nedskrivning\w*\s+(?:av|om|på)|impairment",
}
_LEX_RE = {k: re.compile(v, re.I) for k, v in _LEXICON.items()}
_FLAG_RE = {k: re.compile(v, re.I) for k, v in _RED_FLAGS.items()}

_FEATURE_ORDER = (list(_LEXICON.keys())
                  + ["tone_score", "n_pm_12m", "n_reports_12m", "avg_pm_len", "red_flag_count"])
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


def extract_features(ticker: str) -> Optional[Dict[str, float]]:
    """Token-fria drag för ETT bolag. None om ingen MFN-text finns."""
    text, n_pm, n_rep = _company_text(ticker)
    if not text:
        return None
    n_words = max(len(text.split()), 1)
    per_k = 1000.0 / n_words
    feats: Dict[str, float] = {}
    for k, rx in _LEX_RE.items():
        feats[k] = len(rx.findall(text)) * per_k
    pos, neg = feats.get("tone_pos", 0.0), feats.get("tone_neg", 0.0)
    feats["tone_score"] = (pos - neg) / (pos + neg + 0.5)
    feats["n_pm_12m"] = float(n_pm)
    feats["n_reports_12m"] = float(n_rep)
    feats["avg_pm_len"] = n_words / max(n_pm, 1)
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
    X = np.array([[feats_by_ticker[t].get(f, 0.0) for f in _FEATURE_ORDER]
                  for t in feats_by_ticker], dtype=float)
    return X, list(feats_by_ticker.keys())


def train() -> None:
    """Destillera: träna LightGBM på (token-fria features → LLM-composite).
    Rapporterar 5-fold CV-MAE mot alltid-medel-baselinen och vägrar spara en
    modell som inte slår den (då används lexikon-läget vid score)."""
    import numpy as np
    labels = _load_labels()
    print(f"[soft_signals train] {len(labels)} LLM-betygsatta bolag som facit")
    if len(labels) < MIN_LABELS:
        print(f"  För få labels (< {MIN_LABELS}) för försvarbar ML – score kör lexikon-läge.")
        _model_file().unlink(missing_ok=True)
        _meta_file().unlink(missing_ok=True)
        return

    feats = {}
    for t in labels:
        f = extract_features(t)
        if f:
            feats[t] = f
    if len(feats) < MIN_LABELS:
        print(f"  Bara {len(feats)} av dem har MFN-text – för få. Lexikon-läge gäller.")
        _model_file().unlink(missing_ok=True)
        return
    X, tickers = _matrix(feats)
    y = np.array([labels[t] for t in tickers])

    import lightgbm as lgb
    from sklearn.model_selection import KFold
    params = dict(objective="regression", metric="mae", verbosity=-1,
                  num_leaves=7, min_data_in_leaf=max(3, len(y) // 10),
                  learning_rate=0.08, feature_fraction=0.8, seed=42)
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    maes, base_maes = [], []
    for tr, te in kf.split(X):
        m = lgb.train(params, lgb.Dataset(X[tr], y[tr]), num_boost_round=200)
        pred = m.predict(X[te])
        maes.append(float(np.mean(np.abs(pred - y[te]))))
        base_maes.append(float(np.mean(np.abs(y[tr].mean() - y[te]))))
    cv_mae, base_mae = float(np.mean(maes)), float(np.mean(base_maes))
    print(f"  CV-MAE {cv_mae:.3f} vs baseline (alltid medel) {base_mae:.3f} "
          f"på {len(y)} bolag, composite-spann {y.min():.1f}-{y.max():.1f}")
    if cv_mae >= base_mae:
        print("  Modellen slår INTE baselinen – sparas inte (ärligt > låtsas-ML). "
              "score kör lexikon-läge tills fler LLM-labels finns.")
        _model_file().unlink(missing_ok=True)
        _meta_file().unlink(missing_ok=True)
        return
    booster = lgb.train(params, lgb.Dataset(X, y), num_boost_round=200)
    _model_file().parent.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(_model_file()))
    _meta_file().write_text(json.dumps({
        "features": _FEATURE_ORDER, "n_labels": len(y),
        "cv_mae": round(cv_mae, 4), "baseline_mae": round(base_mae, 4),
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

    rows = []
    feats_all: Dict[str, dict] = {}
    for t in tickers:
        if cap_map.get(t) == "Fond" or sector_map.get(t) == "Fond":
            continue
        f = extract_features(t)
        if f:
            feats_all[t] = f
    if not feats_all:
        print("[soft_signals] ingen MFN-text för segmentet – kör mfn_fetch först.")
        return

    if booster is not None:
        X, order = _matrix(feats_all)
        preds = np.clip(booster.predict(X), 0.0, 5.0)
        pred_by_t = {t: float(p) for t, p in zip(order, preds)}
    else:
        pred_by_t = {t: _lexicon_score(f) for t, f in feats_all.items()}

    for t, f in feats_all.items():
        rows.append({
            "ticker": t, "name": name_map.get(t, t),
            "soft_score": round(pred_by_t[t], 2),
            "mode": ("LLM" if t in labels else mode),   # facit-bolag märks som LLM-täckta
            "llm_composite": labels.get(t, ""),
            "tone_score": round(f["tone_score"], 3),
            "red_flag_count": int(f["red_flag_count"]),
            "red_flags": ";".join(f.get("_flags", [])),
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
    print(f"[soft_signals] {len(rows)} bolag poängsatta ({mode}"
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
    print(f"=== {ticker.upper()} – token-fria mjuk-drag (per 1000 ord) ===")
    for k in _LEXICON:
        print(f"  {k:<16} {f[k]:.2f}")
    print(f"  tone_score       {f['tone_score']:+.3f}")
    print(f"  PM 12m           {f['n_pm_12m']:.0f} (varav {f['n_reports_12m']:.0f} rapporter)")
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
    elif cmd == "score":
        score(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "explain" and len(sys.argv) > 2:
        explain(sys.argv[2])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
