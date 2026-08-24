"""Reusable frozen-H0 V3 policy adapter.

Base OFF reproduces the verified H0 V3 panel engine. A hook may change one
documented selection decision; all rank, cadence, SMA, sizing, turnover and
cost semantics remain frozen.
"""
from pathlib import Path
import sys
import numpy as np
ROOT=Path('/home/hannesb/momentum_v2');sys.path.insert(0,str(ROOT/'tools'))
import rebalance_cadence_4w_vs_8w_audit as H
N=30; COST=.002
class ReentryScoreImprovement:
    threshold=.10
    def __init__(self): self.exit_score={};self.blocked=0;self.reentries=0
    def ordinary(self, raw, previous_pre, previous_final, scores, date):
        out=[]; old=set(previous_final)
        for k in raw:
            if k in old or k not in self.exit_score or scores[k] >= self.exit_score[k]+self.threshold: out.append(k)
            else:self.blocked+=1
            if len(out)==N:break
        return out
    def after(self, previous_final, final, scores):
        for k in set(previous_final)-set(final): self.exit_score[k]=scores.get(k,self.exit_score.get(k,float('inf')))
        self.reentries += sum(k in self.exit_score and k not in previous_final for k in final)
class Top3WinnerProtection2Window:
    """Stateful, PIT ordinary-selection hook for the preregistered Top3 policy.

    ``completed`` contains only intervals whose right endpoint preceded the
    current ordinary decision.  The class deliberately has no access to the
    current or future interval return stream.
    """
    def __init__(self):
        self.episodes = {}
        self.completed = []
        self.events = []
        self.decisions = []

    @staticmethod
    def _finite(x):
        return x is not None and np.isfinite(x)

    def ordinary(self, raw, previous_pre, previous_final, scores, date):
        """Apply deterministic protection only at an ordinary decision.

        ``raw`` is the already frozen score/ticker ordered eligible ranking.
        A protected incumbent replaces the lowest-ranked *unprotected* fresh
        entrant.  This preserves the pre-SMA cardinality exactly.
        """
        baseline = list(raw[:N])
        decision = {'date': str(date), 'completed_window_count': len(self.completed),
                    'baseline': baseline, 'protected': [], 'displaced': [],
                    'final_pre_sma': baseline}
        # Cold start: fewer than two fully closed intervals means no decision.
        if len(self.completed) < 2:
            self.decisions.append(decision)
            return baseline
        a,b=self.completed[-1],self.completed[-2]
        incumbents = list(previous_final)
        eligible=set(raw); candidates=[]
        for k in incumbents:
            ep=self.episodes.get(k)
            if (not ep or k not in a['security'] or k not in b['security'] or
                    not self._finite(a['security'][k]) or not self._finite(b['security'][k]) or
                    not self._finite(a['mean']) or not self._finite(b['mean'])):
                continue
            epret=ep['cum']-1
            if a['security'][k]>a['mean'] and b['security'][k]>b['mean']:candidates.append((epret,k))
        top={k for _,k in sorted([(self.episodes[k]['cum']-1,k) for k in incumbents if k in self.episodes],key=lambda x:(-x[0],x[1]))[:3]}
        protected = [k for _, k in sorted(candidates, key=lambda x:(-x[0],x[1]))
                     if k in top and k in eligible and k not in baseline]
        # A previous holding is eligible only if it is in the frozen raw ranking.
        # Remove tail entrants, never an already protected name, and pair in
        # deterministic protection priority order.
        removable = [k for k in reversed(baseline) if k not in protected]
        protected = protected[:len(removable)]
        displaced = removable[:len(protected)]
        replace = dict(zip(displaced, protected))
        sel = [replace.get(k, k) for k in baseline]
        decision.update({'protected': protected, 'displaced': displaced,
                         'final_pre_sma': sel})
        self.decisions.append(decision)
        self.events += [{'date':date,'ticker':k,'displaced':d} for k,d in zip(protected,displaced)]
        return sel
    def after(self, previous_final, final, scores, security_returns=None, date=None):
        if security_returns is not None:
            sec={k:float(v) for k,v in security_returns.items()
                 if k in previous_final and self._finite(v)}
            self.completed.append({'security':sec,'mean':float(np.mean(list(sec.values()))) if sec else float('nan'),
                                   'end_date':str(date)})
            for k in previous_final:
                if k not in self.episodes:self.episodes[k]={'cum':1.}
                # Missing returns never manufacture a performance observation.
                if k in sec:self.episodes[k]['cum']*=1+sec[k]
        for k in final:
            if k not in self.episodes:self.episodes[k]={'cum':1.}
        for k in set(self.episodes)-set(final):del self.episodes[k]
def run_window(tag, hook=None):
    c=H.run_window(tag)['internal_context']; rk,ret,P=c['rankings'],c['returns'],c['panels']; sma,vol,confirmed=c['sma_fn'],c['vol_fn'],c['confirmed_fn']
    prev_pre=[];prev_final=[];rows=[]
    for i,dt in enumerate(P):
        raw=[r['kod'] for r in rk[dt]];scores={r['kod']:r['score'] for r in rk[dt]}
        if i%2==0 or not prev_pre:
            sel0=hook.ordinary(raw,prev_pre,prev_final,scores,dt) if hook else raw[:N]
            typ='ORDINARY_PANEL'
        else:
            eligible=set(raw);sel0=[k for k in prev_pre if k in eligible]
            sel0 += [k for k in raw if k not in set(sel0)][:max(0,N-len(sel0))];typ='INTERMEDIATE_PANEL'
        turn=0. if not prev_pre else 1-len(set(sel0)&set(prev_pre))/max(1,len(sel0))
        sel=[k for k in sel0 if sma(k,dt)];n=len(sel)
        if n:
            iv=1/(np.maximum(np.array([vol(k,dt) for k in sel]),.05)**1.5);w=iv/iv.sum()*(n/N);w=w*np.array([1 if confirmed(k,dt) else .75 for k in sel]);w=np.clip(w,.01,.06);w=w/w.sum()*(n/N);weights=dict(zip(sel,map(float,w)));gross=float(sum(weights[k]*ret.get((k,dt),0.) for k in sel))
        else:weights={};gross=0.
        cost=COST*turn;net=gross-cost
        rows.append({'date':dt,'panel_index':i,'panel_type':typ,'selected_pre_sma':sel0,'holdings':sel,'weights':weights,'gross':gross,'turnover':turn,'cost':cost,'net':net})
        if hook:
            sr={k:ret.get((k,dt),0.) for k in prev_final}
            try:hook.after(prev_final,sel,scores,security_returns=sr,date=dt)
            except TypeError:hook.after(prev_final,sel,scores)
        prev_pre=sel0;prev_final=sel
    return rows,hook
