"""RUNWAY-MÄTNINGEN: BÄR KÖPBANDET ELLER GAPET?

Hypotesen bakom "köp kring rank 20, äg tills 30": ett namn köpt på rank 20 har
nitton platser att klättra och tio att falla, medan ett köpt på rank 5 har fyra
upp och tjugofem ner. Om det är förklaringen ska avkastningen delas asymmetriskt
— mer tjänat på vägen upp, mindre återlämnat på vägen ner.

Mäts på UNIVERSUMSNIVÅ, inte i en portfölj: varje namn som kommer in i ett
rankband följs som ett hypotetiskt innehav tills ranken passerar H. Ingen
portföljväg, ingen viktning, inga transaktionskostnader — bara namnens egna
banor. Spells överlappar inte: ett nytt räknas först när det förra stängts.

Per hypotetiskt innehav mäts:
  ret_upp    avkastning från inträde till panelen med bästa rank
  ret_ner    avkastning från bästa rank till utgång
  ret_total  hela innehavet
  paneler upp / ner

DEN AVGÖRANDE KONTROLLEN: samma mätning för flera GAP (H − köpbandets nedre
kant). Om effekten sitter i gapet ska band 1-10 med H=20 likna band 15-25 med
H=35. Om den sitter i bandet ska den följa bandet oavsett gap.

"Klättrade platser" rapporteras inte som huvudmått — det är mekaniskt begränsat
av inträdesranken och kan inte jämföras mellan band.

DIAGNOSTISKT. Kör: /opt/momentum/venv/bin/python tools/runway_matning.py
"""
from __future__ import annotations
import importlib.util, json, math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/runway_matning_results.json"

spec = importlib.util.spec_from_file_location("h2h", V2 / "tools/research_all_6_models_head_to_head.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


def main():
    core_df, prices, terminal = m.load_data()
    returns_map, all_dates = m.execution_engine(core_df, prices, terminal)
    vol_map, price_series = m.compute_vols(prices, window=60)
    rankings = m.derive_h0_scores(core_df, prices)
    eval_dates = sorted(rankings.keys())
    rank_map = {(r["kod"], dt): i + 1 for dt in eval_dates for i, r in enumerate(rankings[dt])}
    print(f"{len(eval_dates)} paneler, {eval_dates[0]} — {eval_dates[-1]}")

    sma_cache = {}
    def sma_ok(k, dt):
        key = (k, dt)
        if key not in sma_cache:
            v = True
            if k in price_series:
                ds, adj = price_series[k]
                i = next((j for j in range(len(ds) - 1, -1, -1) if ds[j] <= dt), None)
                if i is not None and i >= 200:
                    v = adj[i] >= float(np.mean(adj[i - 200:i]))
            sma_cache[key] = v
        return sma_cache[key]

    def spells_for(lo, hi, H):
        """Hypotetiska innehav: in när rank hamnar i [lo,hi], ut när rank > H."""
        upptagen = defaultdict(lambda: -1)   # kod -> panelindex då förra spell stängde
        ut = []
        for pi, dt in enumerate(eval_dates):
            for r in rankings[dt][lo - 1:hi]:
                k = r["kod"]
                if pi <= upptagen[k] or not sma_ok(k, dt):
                    continue
                # följ framåt tills rank > H
                banor, ranks = [], []
                j = pi
                while j < len(eval_dates):
                    rj = rank_map.get((k, eval_dates[j]))
                    if rj is None or rj > H:
                        break
                    ranks.append(rj)
                    banor.append(float(returns_map.get((k, eval_dates[j]), 0.0)))
                    j += 1
                if not ranks:
                    continue
                upptagen[k] = j - 1
                b = int(np.argmin(ranks))          # index för bästa rank
                upp = float(np.prod([1 + x for x in banor[: b + 1]]) - 1) if b >= 0 else 0.0
                ner = float(np.prod([1 + x for x in banor[b + 1:]]) - 1) if b + 1 < len(banor) else 0.0
                tot = float(np.prod([1 + x for x in banor]) - 1)
                ut.append({"kod": k, "start": pi, "intradesrank": ranks[0], "bastarank": ranks[b],
                           "utgangsrank": rank_map.get((k, eval_dates[j])) if j < len(eval_dates) else None,
                           "paneler": len(ranks), "paneler_upp": b + 1, "paneler_ner": len(ranks) - b - 1,
                           "ret_upp": upp, "ret_ner": ner, "ret_total": tot,
                           "nadde_topp5": min(ranks) <= 5, "nadde_topp10": min(ranks) <= 10})
        return ut

    def sam(v, nyckel):
        a = np.array([x[nyckel] for x in v], dtype=float)
        if len(a) < 3:
            return None
        return {"n": len(a), "medel": round(float(a.mean()), 4), "median": round(float(np.median(a)), 4),
                "t": round(float(a.mean() / (a.std(ddof=1) / math.sqrt(len(a)))), 2)}

    out = {
        "version": "RUNWAY_MATNING_V1",
        "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "DIAGNOSTISKT — ingen fryst fil ändrad, ingen försegling bruten",
        "metod": "hypotetiska innehav på universumsnivå, ingen viktning, inga kostnader, "
                 "icke-överlappande spells per namn",
        "n_paneler": len(eval_dates), "per_band_h30": {}, "gapkontroll": {},
    }

    # ---- Del 1: samma H=30 för alla band (som i portföljtestet) ----
    print("\nDEL 1 — samma utgång H=30 för alla köpband:")
    print(f"  {'band':<8} {'n':>4} {'paneler':>8} {'upp/ner':>9} {'ret_upp':>9} {'ret_ner':>9} "
          f"{'ret_tot':>9} {'median_tot':>11} {'topp5':>7}")
    for lo, hi in [(1, 5), (6, 10), (11, 15), (16, 20), (21, 25), (26, 30)]:
        sp = spells_for(lo, hi, 30)
        if len(sp) < 10:
            continue
        d = {"n": len(sp),
             "paneler": sam(sp, "paneler"), "paneler_upp": sam(sp, "paneler_upp"),
             "paneler_ner": sam(sp, "paneler_ner"),
             "ret_upp": sam(sp, "ret_upp"), "ret_ner": sam(sp, "ret_ner"),
             "ret_total": sam(sp, "ret_total"),
             "andel_nadde_topp5": round(float(np.mean([s["nadde_topp5"] for s in sp])), 3),
             "andel_positiva": round(float(np.mean([1.0 if s["ret_total"] > 0 else 0.0 for s in sp])), 3)}
        out["per_band_h30"][f"{lo}-{hi}"] = d
        print(f"  {lo}-{hi:<5} {d['n']:>4} {d['paneler']['medel']:>8.1f} "
              f"{d['paneler_upp']['medel']:>4.1f}/{d['paneler_ner']['medel']:<4.1f} "
              f"{d['ret_upp']['medel']:>9.2%} {d['ret_ner']['medel']:>9.2%} "
              f"{d['ret_total']['medel']:>9.2%} {d['ret_total']['median']:>11.2%} "
              f"{d['andel_nadde_topp5']:>7.0%}")

    # ---- Del 2: gapkontrollen ----
    print("\nDEL 2 — gapkontroll: H satt så att fallutrymmet är lika stort:")
    print(f"  {'band':<8} {'gap':>4} {'H':>3} {'n':>4} {'ret_upp':>9} {'ret_ner':>9} {'ret_tot':>9} "
          f"{'median':>9} {'paneler':>8}")
    for gap in (5, 10, 15, 20):
        for lo, hi in [(1, 10), (11, 20), (15, 25), (21, 30)]:
            H = hi + gap
            sp = spells_for(lo, hi, H)
            if len(sp) < 10:
                continue
            d = {"H": H, "n": len(sp), "ret_upp": sam(sp, "ret_upp"), "ret_ner": sam(sp, "ret_ner"),
                 "ret_total": sam(sp, "ret_total"), "paneler": sam(sp, "paneler")}
            out["gapkontroll"][f"band{lo}-{hi}_gap{gap}"] = d
            print(f"  {lo}-{hi:<5} {gap:>4} {H:>3} {d['n']:>4} {d['ret_upp']['medel']:>9.2%} "
                  f"{d['ret_ner']['medel']:>9.2%} {d['ret_total']['medel']:>9.2%} "
                  f"{d['ret_total']['median']:>9.2%} {d['paneler']['medel']:>8.1f}")

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"\nSkrivet: {OUT}")


if __name__ == "__main__":
    main()
