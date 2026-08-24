#!/usr/bin/env python3
import json
from pathlib import Path
R=Path(__file__).resolve().parents[1];src=(R/'tools/spari_batch3.py').read_text();pre=json.loads((R/'research_i/batch3_preregistration.json').read_text());matrix=json.loads((R/'research_i/LEGACY_V2_COVERAGE_MATRIX_PRE_BATCH3.json').read_text())
assert len(matrix['rows'])==46 and len(matrix['remaining_tests'])==2
assert pre['number_of_batch3_tests']==2 and pre['parameter_search'] is False
assert 'target_fwd52w' not in src
assert "THRESH=.85" in src and "has_fundamenta==True" in src
assert 'H1' not in [x['id'] for x in pre['tests']] and 'H2' not in [x['id'] for x in pre['tests']]
print(json.dumps({'status':'PASS','matrix_rows':46,'tests':2,'parameter_search':False,'target_free_selection':True}))
