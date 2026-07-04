"""
tune_pead.py – Har den token-fria PEAD-signalen prediktiv kraft?

Mäter signalens INFORMATIONSKOEFFICIENT (IC) och kvintil-spread mot realiserad
framåtavkastning INNAN den bakas in som feature. Rätt vetenskaplig ordning: bevisa
att signalen har edge på egen hand först, addera den till modellen sen.

Läser MFN-cachen (cache/mfn/<ticker>.json) som redan producerats på Pi:n via
mfn_fetch.fetch_universe – ingen nätverksåtkomst behövs här. Saknas cachen, kör
först:

    /opt/momentum/venv/bin/python -c "from altdata import mfn_fetch; mfn_fetch.fetch_universe('large')"

Kör sen (från /opt/momentum/src/momentum_ml):

    /opt/momentum/venv/bin/python tune_pead.py
"""
import sys, json
from pathlib import Path
sys.path.insert(0, '.')
import numpy as np
import pandas as pd

import config
from data.data_loader import (
    fetch_weekly_data, filter_liquid_universe, filter_active_universe, load_sweden_universe,
)
from altdata.pead import extract_report_dates, compute_pead_panel

DRIFT_WEEKS = 8


def _load_mfn_items():
    """Läs alla cache/mfn/<ticker>.json → {ticker: [items]}."""
    cache_dir = Path(config.MFN_CACHE_DIR)
    if not cache_dir.exists():
        return {}
    items = {}
    for f in cache_dir.glob("*.json"):
        if f.name.startswith("_"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, list) and data:
            items[f.stem] = data
    return items


def main():
    seg = config.SEGMENTS["large"]
    tickers, sector_map, cap_tier_map, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)

    px = pd.DataFrame({t: d["Close"] for t, d in data.items() if "Close" in d}).sort_index()
    fw = config.FORWARD_WEEKS
    fwd_ret = px.shift(-fw) / px - 1

    # ── Rapportdatum från MFN-cachen ─────────────────────────────────────────
    mfn = _load_mfn_items()
    if not mfn:
        print(f"Ingen MFN-cache i {config.MFN_CACHE_DIR}. Kör fetch_universe först "
              "(se docstring överst).")
        return
    all_items = [it for items in mfn.values() for it in items]
    report_dates = extract_report_dates(all_items)
    # Faller author.tickers inte tillbaka på filnamnet? Komplettera med filnyckeln.
    for t, items in mfn.items():
        rd = extract_report_dates(items)
        for _, dates in rd.items():
            report_dates.setdefault(t, [])
            report_dates[t] = sorted(set(report_dates[t]) | set(dates))
    covered = [t for t in px.columns if report_dates.get(t)]
    n_reports = sum(len(report_dates[t]) for t in covered)
    print(f"\nMFN: {len(covered)}/{len(px.columns)} bolag med rapportdatum, "
          f"{n_reports} rapporter totalt.")
    if not covered:
        print("Inga rapportdatum matchade universum-tickers – kolla ticker-mappningen.")
        return

    # ── PEAD-panel + IC ──────────────────────────────────────────────────────
    pead = compute_pead_panel(px, report_dates, drift_weeks=DRIFT_WEEKS)

    all_dates = px.index
    holdout_start = all_dates[-config.HOLDOUT_WEEKS] if len(all_dates) > config.HOLDOUT_WEEKS else all_dates[0]

    def ic_and_spread(mask_dates):
        ics, spreads = [], []
        for d in mask_dates:
            s = pead.loc[d]
            r = fwd_ret.loc[d] if d in fwd_ret.index else None
            if r is None:
                continue
            act = s[s != 0]
            act = act[act.index.isin(r.dropna().index)]
            if len(act) < 5:
                continue
            rr = r[act.index]
            ic = act.rank().corr(rr.rank())            # Spearman
            if pd.notna(ic):
                ics.append(ic)
            # kvintil-spread: översta vs understa 20% av PEAD-signalen
            if len(act) >= 10:
                hi = rr[act >= act.quantile(0.8)].mean()
                lo = rr[act <= act.quantile(0.2)].mean()
                if pd.notna(hi) and pd.notna(lo):
                    spreads.append(hi - lo)
        return (np.mean(ics) if ics else float("nan"),
                np.std(ics) if ics else float("nan"),
                np.mean(spreads) if spreads else float("nan"),
                len(ics))

    full = ic_and_spread(all_dates)
    ho   = ic_and_spread(all_dates[all_dates >= holdout_start])

    print("\n" + "=" * 60)
    print(f"  PEAD token-fri signal · drift {DRIFT_WEEKS}v · mått mot {fw}v-avk")
    print("=" * 60)
    print(f"  {'period':<12}{'IC (snitt)':>12}{'IC std':>10}{'Q5-Q1':>12}{'n veckor':>10}")
    print("-" * 60)
    print(f"  {'hela':<12}{full[0]:>12.3f}{full[1]:>10.3f}{full[2]:>12.2%}{full[3]:>10}")
    print(f"  {'holdout':<12}{ho[0]:>12.3f}{ho[1]:>10.3f}{ho[2]:>12.2%}{ho[3]:>10}")
    print("-" * 60)
    # IC > ~0.03 med positiv spread = användbar edge i tvärsnitts-sammanhang.
    if pd.notna(ho[0]) and ho[0] > 0.03 and pd.notna(ho[2]) and ho[2] > 0:
        print("  → PEAD har prediktiv kraft på holdouten. Värt att lägga in som feature.")
    else:
        print("  → Svag/ingen PEAD-edge på holdouten. Lägg inte till den ännu.")


if __name__ == "__main__":
    main()
