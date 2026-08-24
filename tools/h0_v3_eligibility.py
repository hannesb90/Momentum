"""H0 V3 PIT eligibility-panel + QA. Delas av V3-korningen. Ingen size-anvandning."""
from __future__ import annotations
import json, pathlib
from collections import Counter, defaultdict
V2=pathlib.Path("/home/hannesb/momentum_v2")
SRC=V2/"research_k/nasdaq_segment_foundation/monthly_size_snapshots.json"
REUSE=V2/"research_k/nasdaq_segment_foundation/code_reuse_audit.json"
_snap=json.load(open(SRC))["rader"]
MANADER=sorted({x["report_month"] for x in _snap})
# Segment anvands ENBART som Main Market-markor, aldrig som feature.
_kod_m={(x["orderbook_code"].upper(),x["report_month"]) for x in _snap}
_isin_m={(x["isin"],x["report_month"]) for x in _snap}
_isin2kod={}
for x in _snap: _isin2kod.setdefault(x["isin"], x["orderbook_code"].upper())
_pres=defaultdict(set)
for x in _snap: _pres[x["orderbook_code"].upper()].add(x["report_month"])
_REUSE={r["orderbook_code"].upper() for r in json.load(open(REUSE))["flaggade"]
        if r["klass"]=="CONFIRMED_CODE_REUSE"}

def _norm(k): return k.replace("-"," ").upper()

def kallmanad(dt):
    """Senaste rapportmanad STRIKT FORE beslutsdatumets manad."""
    pm=dt[:7]
    k=[m for m in MANADER if m < pm]
    return k[-1] if k else None

def medlem(kod, isin, dt):
    """Returnerar (eligible, orsak, kallmanad)."""
    m=kallmanad(dt)
    if m is None: return False,"INGEN_RAPPORTMANAD_FORE_BESLUT",None
    nk=_norm(kod)
    if nk in _REUSE: return False,"CONFIRMED_CODE_REUSE_EJ_SAMMANFOGAD",m
    if (nk,m) in _kod_m: return True,"MEMBER_VIA_ORDERBOOK",m
    k2=_isin2kod.get(isin) if isin else None
    if k2:
        if k2 in _REUSE: return False,"CONFIRMED_CODE_REUSE_EJ_SAMMANFOGAD",m
        if (k2,m) in _kod_m: return True,"MEMBER_VIA_ISIN_KEDJA",m
    if isin and (isin,m) in _isin_m: return True,"MEMBER_VIA_ISIN_DIREKT",m
    kk = nk if nk in _pres else (k2 if k2 in _pres else None)
    if kk is None: return False,"UNRESOLVED_IDENTITY_ELLER_EJ_MAIN_MARKET",m
    if m < min(_pres[kk]): return False,"PRE_LISTING",m
    if m > max(_pres[kk]): return False,"POST_DELISTING",m
    return False,"UNRESOLVED_MEMBERSHIP",m
