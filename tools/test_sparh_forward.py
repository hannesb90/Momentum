#!/usr/bin/env python3
from __future__ import annotations
import datetime as dt,hashlib,importlib.util,json,shutil,tempfile
from pathlib import Path

SOURCE=Path(__file__).with_name('sparh_forward.py')
spec=importlib.util.spec_from_file_location('sparh_forward',SOURCE);h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,sort_keys=True,indent=2)+'\n')
def fixture(base:Path,future_noise=False):
 root=base/'repo';hh=root/'trackh';(root/'tools').mkdir(parents=True);shutil.copyfile(SOURCE,root/'tools/sparh_forward.py');(hh/'journal').mkdir(parents=True);(hh/'journal/INDEX.jsonl').write_text('')
 (root/'freeze.json').write_text('{}\n');fh=digest(root/'freeze.json');dump(hh/'H0_LOCK.json',{'freeze_manifest_path':'freeze.json','freeze_manifest_sha256':fh,'locked_files':[]})
 panel='2026-09-04';inbox=hh/'inbox'/panel
 universe=[{'kod':f'K{i:02d}','investable':True,'membership_verified':i%3==0,'membership_basis':'fixture','known_at':panel+'T16:00:00+02:00'} for i in range(35)]
 prices={}
 start=dt.date(2024,1,1);end=dt.date.fromisoformat(panel)
 for i,u in enumerate(universe):
  rows=[];d=start
  while d<=end:
   rows.append({'d':d.isoformat(),'adj':100+i+(d-start).days*(i+1)/1000});d+=dt.timedelta(days=1)
  prices[u['kod']]=rows
 dump(inbox/'prices_snapshot.json',prices);dump(inbox/'universe_snapshot.json',universe)
 files=[{'role':'prices','path':'prices_snapshot.json','sha256':digest(inbox/'prices_snapshot.json')},{'role':'universe','path':'universe_snapshot.json','sha256':digest(inbox/'universe_snapshot.json')}]
 dump(inbox/'input_manifest.json',{'panel_date':panel,'decision_timestamp':panel+'T18:00:00+02:00','data_as_of_timestamp':panel+'T17:59:00+02:00','next_scheduled_trading_date':'2026-09-07','files':files,'upstream_manifests':[]})
 if future_noise:dump(root/'unreferenced_future_targets.json',{'K00':-1,'K01':99})
 return root
def setroot(root):h.ROOT=root;h.H=root/'trackh';h.LOCK=h.H/'H0_LOCK.json';h.INDEX=h.H/'journal/INDEX.jsonl';h.verify_v4_freeze=lambda p:43;h.verify_abc=lambda:13
def main():
 assert h.scheduled(dt.date(2026,9,4)) and h.phase(dt.date(2026,9,4))
 assert h.scheduled(dt.date(2026,10,2)) and not h.phase(dt.date(2026,10,2))
 with tempfile.TemporaryDirectory() as td:
  a=fixture(Path(td)/'a');setroot(a);h.seal('2026-09-04');h.verify()
  rank_a=digest(a/'trackh/sealed/2026-09-04/prediction/ranking_champion.json');hold_a=digest(a/'trackh/sealed/2026-09-04/prediction/planned_holdings.json')
  try:h.seal('2026-09-04');raise AssertionError('overwrite accepted')
  except SystemExit:pass
  b=fixture(Path(td)/'b',True);setroot(b);h.seal('2026-09-04');h.verify()
  assert rank_a==digest(b/'trackh/sealed/2026-09-04/prediction/ranking_champion.json')
  assert hold_a==digest(b/'trackh/sealed/2026-09-04/prediction/planned_holdings.json')
  badexec=Path(td)/'bad_execution.json';dump(badexec,{'execution_rule':'FIRST_OBSERVED_CLOSE_STRICTLY_AFTER_DECISION','trades':[{'kod':'K00','execution_price_date':'2026-09-08','execution_price':100}]})
  try:h.immutable_event('execution','2026-09-04',badexec);raise AssertionError('late execution accepted')
  except AssertionError as e:
   if str(e)=='late execution accepted':raise
  p=b/'trackh/sealed/2026-09-04/prediction/ranking_champion.json';p.chmod(0o644);p.write_text('[]\n')
  try:h.verify();raise AssertionError('tamper accepted')
  except SystemExit:pass
  c=fixture(Path(td)/'c');setroot(c);ip=c/'trackh/inbox/2026-09-04/prices_snapshot.json';prices=json.loads(ip.read_text());prices['K00'].append({'d':'2026-09-05','adj':1});dump(ip,prices);im=c/'trackh/inbox/2026-09-04/input_manifest.json';m=json.loads(im.read_text());m['files'][0]['sha256']=digest(ip);dump(im,m)
  try:h.seal('2026-09-04');raise AssertionError('future price accepted')
  except AssertionError as e:
   if str(e)=='future price accepted':raise
  d=fixture(Path(td)/'d');setroot(d);up=d/'trackh/inbox/2026-09-04/universe_snapshot.json';u=json.loads(up.read_text());u[0]['target_fwd52w']=1;dump(up,u);im=d/'trackh/inbox/2026-09-04/input_manifest.json';m=json.loads(im.read_text());m['files'][1]['sha256']=digest(up);dump(im,m)
  try:h.seal('2026-09-04');raise AssertionError('target field accepted')
  except AssertionError as e:
   if str(e)=='target field accepted':raise
 print(json.dumps({'status':'PASS','tests':['calendar_phase','no_overwrite','future_unreferenced_ablation_byte_identical','future_price_rejected','target_field_rejected','execution_must_equal_preregistered_first_date','manifest_tamper_fail_fast']}))
if __name__=='__main__':main()
