"""G67/G68 EFFICIENCY RATIO och G74/G75 DIRECTIONAL CONSISTENCY

Rena INFORMATIONSTESTER. Ingen portföljvariant, ingen tröskel, ingen grid.

Population: locked H0:s topp-30 vid varje beslutstidpunkt.
Locked H0 = 7,20 % (2020-2026) / 31,56 % (2014-2019) efter G29:s vikträttelse.

FÖRREGISTRERADE DEFINITIONSBESLUT — fattade före varje beräkning
  1. ER52 använder VECKOVISA prisinkrement, inte dagliga. Skälet är att
     featureregistrets övriga banmått (trend_consistency_52w, vol_52w,
     skew_52w) alla räknar veckor; en daglig nämnare skulle göra ER
     jämförbar med ingenting annat i programmet.
        ER52 = |P_T − P_{T−52v}| / summa|P_i − P_{i−1}|, veckovisa stängningar
  2. Veckogränser är ISO-veckor, identiska för samtliga aktier. Veckans
     observation är sista handelsdagen i ISO-veckan.
  3. Minst 45 av 52 veckoavkastningar måste finnas, annars saknas värdet.
  4. Ingen alternativ horisont beräknas. 52 veckor för båda måtten.

DET OGILTIGA TIDIGARE RESULTATET
  Spår F:s trend_consistency_52w vann preliminärt men ogiltigförklarades:
  blueprinten säger andel positiva VECKOR, aktiv C-kod räknade positiva
  HANDELSDAGAR (max avvikelse 0,282). Det resultatet används INTE här — varken
  för att välja definition, sätta tröskel, tolka riktning eller bekräfta
  hypotes. Måttet byggs från den oberoende veckorekonstruktionen nedan.

HUVUDFRÅGAN ÄR INKREMENTELL INFORMATION
  Ett samband mellan banmåttet och framtida avkastning räcker inte om det
  försvinner efter kontroll för aktuell H0-score/rank.

METODVARNING FRÅN H1 (permanent)
  H1 hade Top-30 IC +0,0348/+0,0528, positiv i båda fönstren, och gav ändå
  −5,48 pp CAGR i det tidiga fönstret. Ett positivt IC här får därför INTE
  beskrivas som en förbättring av H0.

Kör: /opt/momentum/venv/bin/python tools/g67_g74_banans_form.py
"""
from __future__ import annotations
import bisect, json, math, sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S
import h1419_motor as M

OUT = V2 / "research_k/g67_g74_results.json"
PANEL = V2 / "research_k/g67_g74_paneldata.jsonl"
N = 30
HOR = [(1, "4v"), (2, "8v"), (3, "12v"), (6, "24v")]
MIN_VECKOR = 45

_D, _V = {}, {}


def dagsserie(F, k):
    n = (id(F), k)
    if n not in _D:
        if F is S.F19:
            s = M.SERIE.get(k)
            _D[n] = None if s is None else \
                (s[0].astype("datetime64[D]").astype(str).tolist(), np.asarray(s[1]))
        else:
            s = S.PS26.get(k)
            _D[n] = None if s is None else (list(s[0]), np.asarray(s[1]))
    return _D[n]


def veckoserie(F, k):
    """Oberoende veckorekonstruktion: sista handelsdagen i varje ISO-vecka.
    Samma veckogränser för alla aktier. Byggs en gång per namn."""
    n = (id(F), k)
    if n in _V:
        return _V[n]
    s = dagsserie(F, k)
    if s is None:
        _V[n] = None
        return None
    ds, adj = s
    sista = {}
    for i, d in enumerate(ds):
        y, w, _ = date.fromisoformat(d).isocalendar()
        sista[(y, w)] = i           # senare index skriver över -> sista dagen i veckan
    nycklar = sorted(sista)
    idx = [sista[x] for x in nycklar]
    _V[n] = ([ds[i] for i in idx], adj[idx])
    return _V[n]


def banmatt(F, k, dt):
    """-> (ER52, positiv_veckoandel) med endast information till och med dt."""
    v = veckoserie(F, k)
    if v is None:
        return None, None
    wd, wp = v
    j = bisect.bisect_right(wd, dt)         # PIT: strikt till och med paneldatum
    if j < MIN_VECKOR + 1:
        return None, None
    fon = wp[max(0, j - 53):j]
    if len(fon) < MIN_VECKOR + 1:
        return None, None
    diff = np.diff(fon)
    total = float(np.sum(np.abs(diff)))
    er = float(abs(fon[-1] - fon[0]) / total) if total > 0 else None
    ret = fon[1:] / fon[:-1] - 1
    pwr = float(np.mean(ret > 0)) if len(ret) >= MIN_VECKOR else None
    return er, pwr


def spearman(x, y):
    if len(x) < 10:
        return None
    def rk(a):
        o = sorted(range(len(a)), key=lambda i: a[i])
        r = [0.0] * len(a); i = 0
        while i < len(o):
            j = i
            while j + 1 < len(o) and a[o[j + 1]] == a[o[i]]:
                j += 1
            m = (i + j) / 2 + 1
            for t in range(i, j + 1):
                r[o[t]] = m
            i = j + 1
        return np.array(r)
    a, b = rk(x), rk(y)
    if a.std() == 0 or b.std() == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def residual(mal, kontroll):
    """Rangbaserad ortogonalisering av mal mot en eller flera kontrollvariabler."""
    y = np.argsort(np.argsort(mal)).astype(float)
    X = np.column_stack([np.ones(len(y))] +
                        [np.argsort(np.argsort(c)).astype(float) for c in kontroll])
    try:
        beta = np.linalg.lstsq(X, y, rcond=None)[0]
    except Exception:
        return y
    return y - X @ beta


def framat(F, k, pi, h):
    dts, ret = F["eval_dates"], F["returns_map"]
    if pi + h > len(dts):
        return None
    p = 1.0
    for i in range(pi, pi + h):
        v = ret.get((k, dts[i]))
        if v is None:
            return None
        p *= (1 + v)
    return p - 1


def matt(F, namn, valj, extra_kontroll=None, etikett=""):
    """valj: 'er' | 'pwr'. extra_kontroll: 'pwr' | 'er' | None för dedupkontroll."""
    dts = F["eval_dates"]
    ic, ric, kv, tmb, mono = defaultdict(list), defaultdict(list), defaultdict(lambda: defaultdict(list)), defaultdict(list), defaultdict(list)
    n_obs = 0
    for pi, dt in enumerate(dts):
        raw = F["rankings"][dt]
        top = [r["kod"] for r in raw][:N]
        sc = {r["kod"]: r["score"] for r in raw}
        rows = []
        for k in top:
            er, pwr = banmatt(F, k, dt)
            v = er if valj == "er" else pwr
            ek = (pwr if extra_kontroll == "pwr" else er) if extra_kontroll else 0.0
            if v is not None and (extra_kontroll is None or ek is not None):
                rows.append((k, v, sc[k], ek))
        if len(rows) < 20:
            continue
        n_obs += len(rows)
        koder = [r[0] for r in rows]
        mv = np.array([r[1] for r in rows]); sv = np.array([r[2] for r in rows])
        kontroll = [sv] + ([np.array([r[3] for r in rows])] if extra_kontroll else [])
        res = residual(mv, kontroll)
        for h, e in HOR:
            fw = [framat(F, k, pi, h) for k in koder]
            m = [i for i, x in enumerate(fw) if x is not None]
            if len(m) < 20:
                continue
            y = [fw[i] for i in m]
            a = spearman([mv[i] for i in m], y)
            b = spearman([res[i] for i in m], y)
            if a is not None:
                ic[e].append(a)
            if b is not None:
                ric[e].append(b)
            ordn = sorted(m, key=lambda i: mv[i])
            q = max(3, len(ordn) // 5)
            for qi in range(5):
                seg = ordn[qi * q:(qi + 1) * q] if qi < 4 else ordn[4 * q:]
                if seg:
                    kv[e][qi].append(float(np.mean([fw[i] for i in seg])))
            tmb[e].append(float(np.mean([fw[i] for i in ordn[-q:]]) -
                                np.mean([fw[i] for i in ordn[:q]])))
    print(f"\n  {namn}{etikett}   observationer: {n_obs}, paneler: {len(ic['4v'])}")
    print(f"    {'horisont':<9}{'rank-IC':>10}{'t':>7}{'residual-IC':>13}{'t':>7}"
          f"{'topp−botten':>13}{'t':>7}  kvintiler Q1→Q5")
    ut = {}
    for h, e in HOR:
        if len(ic[e]) < 8:
            continue
        a1 = np.array(ic[e]); a2 = np.array(ric[e]); a3 = np.array(tmb[e])
        f_ = lambda x: float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x))))
        q = [float(np.mean(kv[e][i])) for i in range(5) if kv[e][i]]
        stig = all(q[i] <= q[i + 1] for i in range(len(q) - 1))
        fall = all(q[i] >= q[i + 1] for i in range(len(q) - 1))
        ut[e] = {"ic": round(float(a1.mean()), 4), "t_ic": round(f_(a1), 2),
                 "residual_ic": round(float(a2.mean()), 4), "t_residual": round(f_(a2), 2),
                 "topp_minus_botten": round(float(a3.mean()), 5), "t_tmb": round(f_(a3), 2),
                 "kvintiler": [round(x, 5) for x in q],
                 "monoton": "stigande" if stig else ("fallande" if fall else "ej monoton"),
                 "n_paneler": len(a1)}
        print(f"    {e:<9}{a1.mean():>+10.4f}{f_(a1):>7.2f}{a2.mean():>+13.4f}{f_(a2):>7.2f}"
              f"{a3.mean():>+13.2%}{f_(a3):>7.2f}  "
              f"{' '.join(f'{x:+.1%}' for x in q)}  {ut[e]['monoton']}")
    return ut


def dom(a, b):
    """a, b = resultat per fönster. Klassificering enligt förregistrering."""
    gem = [e for e in a if e in b]
    if not gem:
        return "NO INCREMENTAL SIGNAL"
    samma = [(a[e]["residual_ic"] > 0) == (b[e]["residual_ic"] > 0) for e in gem]
    sig = [abs(a[e]["t_residual"]) > 1.96 or abs(b[e]["t_residual"]) > 1.96 for e in gem]
    stark = [abs(a[e]["t_residual"]) > 1.96 and abs(b[e]["t_residual"]) > 1.96 for e in gem]
    mono = [a[e]["monoton"] != "ej monoton" or b[e]["monoton"] != "ej monoton" for e in gem]
    if all(samma) and any(stark) and any(mono):
        return "REPLICATED INCREMENTAL SIGNAL"
    if any(sig) and any(samma):
        return "PROMISING-BUT-UNSTABLE"
    return "NO INCREMENTAL SIGNAL"


def main():
    ut = {"version": "G67_G74_BANANS_FORM_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "locked_h0": {"2020_2026": 0.0720, "2014_2019": 0.3156},
          "forregistrerade_definitionsbeslut": [
              "ER52 pa VECKOVISA prisinkrement, ISO-veckor, sista handelsdag i veckan",
              "minst 45 av 52 veckoavkastningar kravs",
              "ingen alternativ horisont, 52 veckor for bada matten",
              "det ogiltiga Spar F-resultatet anvands inte for nagot andamal"],
          "metodvarning": "H1 hade Top-30 IC +0,0348/+0,0528 och gav anda -5,48 pp CAGR. "
                          "Ett positivt IC har ar INTE en forbattring av H0.",
          "steg1_ER52": {}, "steg2_PWR52": {}, "dedup": {}}

    print(f"{'='*78}\nSTEG 1 — G67/G68 EFFICIENCY RATIO 52v")
    for w_, F, namn in (("2020_2026", S.F26, "2020-2026"), ("2014_2019", S.F19, "2014-2019")):
        ut["steg1_ER52"][w_] = matt(F, namn, "er")
    d1 = dom(ut["steg1_ER52"]["2020_2026"], ut["steg1_ER52"]["2014_2019"])
    ut["dom_G67"] = d1
    print(f"\n  DOM G67/G68: {d1}")

    print(f"\n{'='*78}\nSTEG 2 — G74/G75 POSITIVE WEEK RATIO 52v")
    for w_, F, namn in (("2020_2026", S.F26, "2020-2026"), ("2014_2019", S.F19, "2014-2019")):
        ut["steg2_PWR52"][w_] = matt(F, namn, "pwr")
    d2 = dom(ut["steg2_PWR52"]["2020_2026"], ut["steg2_PWR52"]["2014_2019"])
    ut["dom_G74"] = d2
    print(f"\n  DOM G74/G75: {d2}")

    # ---- dedupliceringskontroll
    print(f"\n{'='*78}\nDEDUPLICERINGSKONTROLL — mäter de samma sak?")
    rader = []
    for w_, F, namn in (("2020_2026", S.F26, "2020-2026"), ("2014_2019", S.F19, "2014-2019")):
        par = []
        for pi, dt in enumerate(F["eval_dates"]):
            for k in [r["kod"] for r in F["rankings"][dt]][:N]:
                er, pwr = banmatt(F, k, dt)
                if er is not None and pwr is not None:
                    par.append((er, pwr))
                    rader.append({"fonster": namn, "dt": dt, "kod": k,
                                  "er52": round(er, 5), "pwr52": round(pwr, 5)})
        a = np.array([x[0] for x in par]); b = np.array([x[1] for x in par])
        pear = float(np.corrcoef(a, b)[0, 1])
        spe = spearman(list(a), list(b))
        ut["dedup"][w_] = {"n": len(par), "pearson": round(pear, 4),
                           "spearman": round(spe, 4) if spe else None}
        print(f"  {namn}: n={len(par)}  Pearson {pear:+.3f}  Spearman {spe:+.3f}")

    # ömsesidig kontroll endast om båda visar något
    if d1 != "NO INCREMENTAL SIGNAL" and d2 != "NO INCREMENTAL SIGNAL":
        print(f"\n  Ömsesidig kontroll (båda visade signal):")
        ut["dedup"]["omsesidig"] = {}
        for w_, F, namn in (("2020_2026", S.F26, "2020-2026"), ("2014_2019", S.F19, "2014-2019")):
            ut["dedup"]["omsesidig"].setdefault("ER_givet_PWR", {})[w_] = \
                matt(F, namn, "er", extra_kontroll="pwr", etikett="  [ER | H0 + PWR]")
            ut["dedup"]["omsesidig"].setdefault("PWR_givet_ER", {})[w_] = \
                matt(F, namn, "pwr", extra_kontroll="er", etikett="  [PWR | H0 + ER]")
    else:
        ut["dedup"]["omsesidig"] = ("EJ KÖRD — ömsesidig kontroll är endast meningsfull "
                                    "om båda måtten visar signal")
        print(f"\n  Ömsesidig kontroll EJ KÖRD: minst ett mått gav NO INCREMENTAL SIGNAL")

    with open(PANEL, "w") as f:
        for r in rader:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1, default=float))
    print(f"\n{'='*78}\nG67/G68: {d1}\nG74/G75: {d2}")
    print(f"\nSkrivet: {OUT}\nPaneldata: {PANEL} ({len(rader)} observationer)")


if __name__ == "__main__":
    main()
