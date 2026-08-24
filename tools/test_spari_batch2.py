#!/usr/bin/env python3
import ast,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
src=(R/'tools/spari_batch2.py').read_text();tree=ast.parse(src)
assert 'target_fwd52w' not in src and 'target_table' not in src
pre=json.loads((R/'research_i/batch2_preregistration.json').read_text())
assert len(pre['executable_tests_in_order'])==5
assert all(x.get('label')=='LEGACY_REPLICATION_PARAMETER' for x in pre['executable_tests_in_order'])
assert {x['id'] for x in pre['not_executable']} >= {'streak_persistence','rank_exit','ATR'}
assert 'common_execution' in src and "d>boundary" in src.replace(' ','')
print(json.dumps({'status':'PASS','target_free':True,'strict_post_trigger_execution':True,'preregistered_variants':5}))
