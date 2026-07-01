"""
etf_thesis.py – Kausalt "världsträd" för TREND-IDÉER (D-spårets hypotes-lager).

Givet vad som är hett NU (från etf_rotation-signalen) + drivkrafter (krig, ränta,
politik) traverserar det ett kausalt kartträd (data/sector_causal_graph.json) och
föreslår plausibla NÄSTA sektorer med resonemangskedjan – t.ex. AI → datacenter →
kraft → kärnkraft/uran.

ÄRLIGHET (viktigt): detta är EJ backtestbart och EJ en signal. LLM:en har
look-ahead (tränad t.o.m. 2026 – den 'vet' redan gårdagens trender), så grafen är
en IDÉGENERATOR att bedöma själv, inte ett bevisat edge. Bekräfta alltid mot den
mekaniska rotationssignalen (etf_rotation.py), som faktiskt är testbar.

    python etf_thesis.py next                 # nästa-trend-idéer från dagens heta ETF:er
    python etf_thesis.py next ai_capex        # ...från en drivkraft (krig, ränta, ai_capex...)
    python etf_thesis.py next Semiconductors  # ...från en sektor
    python etf_thesis.py graph                # visa hela trädet
    python etf_thesis.py expand 50            # LLM: generera 50 nya kanter (KOSTAR krediter)
"""
import sys
import csv
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config

_GRAPH = Path(__file__).parent / "data" / "sector_causal_graph.json"
_UNIVERSE = Path(__file__).parent / "data" / "rotation_universe.csv"
_DECAY = 0.55   # bidrag krymper per extra hopp i kedjan


def _load_graph() -> dict:
    return json.loads(_GRAPH.read_text(encoding="utf-8"))


def _group_to_etf() -> dict:
    """grupp-etikett → första ETF-ticker (så en sektor-nod blir handelsbar)."""
    m = {}
    if _UNIVERSE.exists():
        with open(_UNIVERSE, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                m.setdefault(row.get("group"), row["ticker"])
    return m


def _adjacency(edges):
    adj = {}
    for e in edges:
        adj.setdefault(e["from"], []).append(e)
    return adj


def _hot_sectors():
    """Dagens heta sektorer = grupperna för de ETF:er rotationssignalen HÅLLER."""
    sig = Path("results/etf_rotation.csv")
    if not sig.exists():
        return []
    etf_group = {}
    with open(_UNIVERSE, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            etf_group[row["ticker"]] = row.get("group")
    out = []
    with open(sig, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("hold") in ("1", "1.0", "True", "true"):
                g = etf_group.get(row.get("etf"))
                if g:
                    out.append(g)
    return out


def next_trends(seeds=None):
    g = _load_graph()
    adj = _adjacency(g["edges"])
    g2etf = _group_to_etf()
    drivers = g.get("drivers", {})

    if not seeds:
        seeds = _hot_sectors()
        src = "dagens heta ETF:er (rotationssignalen)"
    else:
        src = "angivet: " + ", ".join(seeds)
    seeds = [s for s in seeds if s in adj or s in drivers or s in g2etf]
    if not seeds:
        print("[next] inga giltiga frö-noder. Ange sektor/drivkraft, eller kör "
              "'etf_rotation.py signal' först så vi kan läsa dagens heta sektorer.")
        print("  Drivkrafter:", ", ".join(drivers))
        return

    score, best_chain, headwind = {}, {}, {}
    seed_set = set(seeds)

    def walk(node, hop, contrib, chain):
        if hop > 2:
            return
        for e in adj.get(node, []):
            to, conf, sign = e["to"], float(e["conf"]), e["sign"]
            c = contrib * conf * (_DECAY ** (hop - 1))
            newchain = chain + [f"  →({e['why']})  {to}"]
            if sign == "-":
                headwind[to] = max(headwind.get(to, 0.0), c)
            else:
                if to not in seed_set and c > score.get(to, 0.0):
                    score[to] = c
                    best_chain[to] = newchain
                elif to not in seed_set:
                    score[to] = score.get(to, 0.0) + c * 0.3   # extra vägar → liten bonus
                walk(to, hop + 1, c, newchain)

    for s in seeds:
        label = f"[{drivers[s]}]" if s in drivers else s
        walk(s, 1, 1.0, [label])

    ranked = sorted(score.items(), key=lambda kv: kv[1], reverse=True)
    print(f"\n  NÄSTA-TREND-IDÉER  (från {src})")
    print("  ⚠ hypoteser, inte signaler – LLM-look-ahead, ej backtestbart. Bedöm själv.\n")
    if not ranked:
        print("  (inga utgående kausalkedjor från fröna – prova en annan sektor/drivkraft)")
    for node, sc in ranked[:10]:
        etf = g2etf.get(node, "—")
        hw = "  ⚠motvind" if node in headwind and headwind[node] > sc else ""
        print(f"   {sc:>4.2f}  {node:<22} {etf:<9}{hw}")
        print(f"         {''.join(best_chain[node])}")
    if headwind:
        strong = [n for n, v in headwind.items() if v > score.get(n, 0)]
        if strong:
            print(f"\n  Motvind (drivkrafterna talar EMOT just nu): {', '.join(strong[:8])}")
    print("\n  Nästa steg: kolla om idéerna redan syns i rotationens 'flöde' (kapital in) "
          "– en idé som ÄN INTE är het men börjar klättra är den intressanta.")


def show_graph():
    g = _load_graph()
    print("\n  DRIVKRAFTER (makro/geopolitik/ränta):")
    for k, v in g.get("drivers", {}).items():
        print(f"   {k:<18} {v}")
    print(f"\n  KAUSALKANTER ({len(g['edges'])} st):")
    for e in sorted(g["edges"], key=lambda e: (e["from"], -float(e["conf"]))):
        print(f"   {e['from']:<20} {e['sign']} {e['to']:<22} "
              f"(conf {e['conf']}, +{e['lag_m']}m)  {e['why']}")


def expand(n=50):
    """LLM genererar n NYA kausalkanter → mot 1000+ punkter. KOSTAR krediter.
    Hård ram i prompten: strukturella ekonomiska mekanismer, inte kursmönster."""
    from altdata.sentiment import _client
    g = _load_graph()
    sectors = sorted({e["from"] for e in g["edges"]} | {e["to"] for e in g["edges"]})
    drivers = list(g.get("drivers", {}))
    existing = {(e["from"], e["to"]) for e in g["edges"]}
    model = getattr(config, "THESIS_MODEL", config.QUALITY_MODEL)
    system = (
        "Du bygger en KAUSAL graf över makro/sektor-samband för idégenerering (ej "
        "prediktion). Basera kanter på DURABLA ekonomiska mekanismer (utbud/efterfrågan, "
        "kapitalcykler, politik), ALDRIG på nyliga kursrörelser. Undvik efterhandskonstruktion. "
        "Svara ENDAST med en JSON-array av objekt: {from,to,sign('+'/'-'),lag_m(int),conf(0-1),why}. "
        "'from' och 'to' ska vara en av dessa noder:\n"
        f"DRIVKRAFTER: {drivers}\nSEKTORER: {sectors}\n"
        "Ge nya, icke-triviala kanter (2:a/3:e ordningens kaskader värdesätts, "
        "t.ex. AI→kraft→kärnkraft→koppar)."
    )
    msg = _client().messages.create(
        model=model, max_tokens=4000, system=system,
        messages=[{"role": "user", "content": f"Generera {n} NYA kausalkanter (ej dubbletter)."}],
    )
    txt = "".join(getattr(b, "text", "") for b in msg.content)
    import re
    m = re.search(r"\[.*\]", txt, re.S)
    if not m:
        print("[expand] kunde inte tolka LLM-svaret som JSON-array.")
        return
    try:
        new = json.loads(m.group(0))
    except Exception as e:  # noqa: BLE001
        print(f"[expand] JSON-fel: {e}")
        return
    added = 0
    for e in new:
        if not isinstance(e, dict) or "from" not in e or "to" not in e:
            continue
        if (e["from"], e["to"]) in existing:
            continue
        e.setdefault("sign", "+"); e.setdefault("lag_m", 3); e.setdefault("conf", 0.4)
        e.setdefault("why", "")
        g["edges"].append(e)
        existing.add((e["from"], e["to"]))
        added += 1
    _GRAPH.write_text(json.dumps(g, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[expand] +{added} nya kanter (totalt {len(g['edges'])}). "
          "OBS: hypoteser för idégenerering, inte validerade samband.")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "next"
    if cmd == "next":
        next_trends(sys.argv[2:] or None)
    elif cmd == "graph":
        show_graph()
    elif cmd == "expand":
        expand(int(sys.argv[2]) if len(sys.argv) > 2 else 50)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
