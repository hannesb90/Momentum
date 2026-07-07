"""
altdata/case_tracker.py – Har investeringscaset förändrats?

Visionens kärnfråga. Jämför per bolag de AI-extraherade signalerna (sentiment-
cachen: guidance, ledningston, materialitet, risk_flags, catalyst) i det
SENASTE 90-dagarsfönstret mot FÖREGÅENDE 90 dagar:

  förbättrat  – guidance upp / tonläge upp / nya katalysatorer
  försämrat   – guidance ned / tonläge ned / nya riskflaggor / emission
  oförändrat  – ingen väsentlig skillnad (eller för få datapunkter)

Ingen åsikt, ingen ny AI-körning – ren aggregering av redan extraherade,
cachade features (ett dokument analyseras EN gång; detta läser bara resultatet).
Output: results/case_changes.csv – konsumeras av appen/säljvakten som kontext.

    python -m altdata.case_tracker build   # → case_changes.csv
    python -m altdata.case_tracker show    # förändrade case först
"""
import csv
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

WINDOW_DAYS = 90
MIN_DOCS = 2          # per fönster för att våga säga något alls


def _load_joined() -> dict:
    """{ticker: [(datum, features)]} – MFN-dokument joinade med sentiment-cachen."""
    sdir = Path(config.anchor(config.SENTIMENT_CACHE_DIR))
    mdir = Path(config.anchor(config.MFN_CACHE_DIR))
    scores = {}
    for f in sdir.glob("*.json"):
        if f.name.startswith("_"):
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            scores[d.get("id") or f.stem] = d
        except Exception:  # noqa: BLE001
            pass
    out = {}
    for f in mdir.glob("*.json"):
        if f.name.startswith("_"):
            continue
        try:
            items = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(items, list):
            continue
        for it in items:
            sc = scores.get(it.get("id"))
            if not sc:
                continue
            try:
                dt = datetime.fromisoformat(str(it.get("published"))[:19])
            except ValueError:
                continue
            out.setdefault(f.stem.upper(), []).append((dt, sc))
    return out


def _agg(docs: list) -> dict:
    """Aggregera ett fönsters features (materialitets-viktat där det är rimligt)."""
    if not docs:
        return {}
    w = [max(int(s.get("materiality") or 0), 1) for _, s in docs]
    tot = sum(w) or 1
    def wavg(key):
        return sum(wi * int(s.get(key) or 0) for wi, (_, s) in zip(w, docs)) / tot
    flags = [fl for _, s in docs for fl in (s.get("risk_flags") or [])]
    cats = [s.get("catalyst") for _, s in docs if s.get("catalyst")]
    return {"n": len(docs), "sentiment": wavg("sentiment"), "guidance": wavg("guidance"),
            "tone": wavg("ceo_tone"), "risk_flags": flags, "catalysts": cats,
            "capital": sum(1 for _, s in docs if s.get("category") == "capital")}


def compute(now: datetime = None) -> list:
    now = now or datetime.now()
    cut1 = now - timedelta(days=WINDOW_DAYS)
    cut2 = now - timedelta(days=2 * WINDOW_DAYS)
    rows = []
    for tk, docs in _load_joined().items():
        cur = _agg([d for d in docs if d[0] >= cut1])
        prev = _agg([d for d in docs if cut2 <= d[0] < cut1])
        if not cur or cur["n"] < MIN_DOCS or not prev or prev["n"] < MIN_DOCS:
            continue
        reasons, score = [], 0.0
        dg = cur["guidance"] - prev["guidance"]
        if abs(dg) >= 0.3:
            score += dg
            reasons.append(f"guidance {'upp' if dg > 0 else 'ned'} ({dg:+.1f})")
        dt_ = cur["tone"] - prev["tone"]
        if abs(dt_) >= 0.5:
            score += 0.5 * dt_
            reasons.append(f"ledningston {'upp' if dt_ > 0 else 'ned'} ({dt_:+.1f})")
        new_flags = sorted(set(cur["risk_flags"]) - set(prev["risk_flags"]))
        if new_flags:
            score -= 0.5 * len(new_flags)
            reasons.append("nya risker: " + ", ".join(new_flags[:3]))
        if cur["capital"] > prev["capital"]:
            score -= 0.7
            reasons.append("kapitalanskaffning/emission")
        if cur["catalysts"]:
            score += 0.3
            reasons.append("katalysator: " + str(cur["catalysts"][0])[:40])
        status = "förbättrat" if score >= 0.4 else ("försämrat" if score <= -0.4 else "oförändrat")
        rows.append({"ticker": tk, "status": status, "score": round(score, 2),
                     "docs_90d": cur["n"], "docs_prev": prev["n"],
                     "reasons": " · ".join(reasons) or "ingen väsentlig skillnad"})
    rows.sort(key=lambda r: r["score"])
    return rows


def build():
    rows = compute()
    if not rows:
        print("För få bolag med scorade PM i båda fönstren – kör sentiment-pipelinen först.")
        return
    out = Path(config.anchor(config.RESULTS_DIR)) / "case_changes.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    ch = [r for r in rows if r["status"] != "oförändrat"]
    print(f"case_changes.csv: {len(rows)} bolag · {len(ch)} förändrade case → {out}")


def show():
    for r in compute():
        if r["status"] != "oförändrat":
            mark = "▲" if r["status"] == "förbättrat" else "▼"
            print(f"{mark} {r['ticker']:<14} {r['status']:<11} {r['score']:>+5.1f}  {r['reasons']}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    {"build": build, "show": show}.get(cmd, lambda: print(__doc__))()


if __name__ == "__main__":
    main()
