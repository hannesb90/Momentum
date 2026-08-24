#!/usr/bin/env python3
"""Build the First North PIT foundation solely from the verified CNS raw store.

This intentionally has no discovery or download path.  A raw-manifest record is
the unit of work and each record must produce exactly one parser disposition.
"""
from __future__ import annotations

import csv
import argparse
import hashlib
import gzip
import io
import json
import re
import shutil
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

V = Path('/home/hannesb/momentum_v2')
# This tool is deliberately parser-only after the structural alignment repair.
# Venue/reference attribution and company-master work are downstream and must not
# be accidentally triggered by a successful raw/parser run.
OUT = V / 'research_k/nasdaq_historical_master/first_north_schema_repaired'
RAW_ROOT = V / 'raw/nasdaq_segment/first_north_cns_objects'
MANIFEST = V / 'research_k/nasdaq_historical_master/first_north_rebuilt/raw_manifest.json'
sys.path.insert(0, str(V / 'tools/nasdaq_segment'))
from ole2 import OLE2
import biff8

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
RNS = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'

COMMON = {'location', 'company code', 'issuer code', 'orderbook code'}
FIELDS = {
    'instrument': 'instrument', 'issuer code': 'issuer_code', 'company code': 'issuer_code',
    'orderbook code': 'ticker', 'isin': 'isin', 'instrument type': 'instrument_type',
    'segment': 'segment', 'industry': 'industry', 'supersector': 'supersector',
    'super sector': 'supersector', 'issuer country': 'issuer_country', 'currency': 'currency', 'curr- ency': 'currency', 'lp yes=y': 'lp_yes', 'lp yes': 'lp_yes', 'location': 'location',
    'delisted': 'delisted',
}

CANONICAL_FIELDS = ('instrument', 'issuer_code', 'ticker', 'orderbook_id',
                    'isin', 'instrument_type', 'segment', 'industry',
                    'supersector', 'currency', 'location', 'delisted')
CURRENCY_DOMAIN = {'SEK', 'EUR', 'DKK', 'ISK', 'NOK', 'GBP', 'USD'}
LP_DOMAIN = {'Y', 'N', 'YES', 'NO', ''}
ISIN_RE = re.compile(r'^[A-Z]{2}[A-Z0-9]{9}[0-9]$')

def utc(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
def norm(x): return re.sub(r'\s+', ' ', str(x or '')).strip()
def norm_header(x):
    """Normalize a header label without changing its physical coordinate.

    Excel wraps "Curr-\nency" into two visual lines.  The dash is a wrap
    artefact, not a field delimiter.  Header normalization is intentionally
    separate from data-cell normalization.
    """
    value = str(x or '').replace('\u00ad', '')
    value = re.sub(r'-\s+', '', value)
    return re.sub(r'\s+', ' ', value).strip().lower()
def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def colnum(ref):
    n = 0
    for ch in re.match(r'[A-Z]+', ref).group(0): n = n * 26 + ord(ch) - 64
    return n - 1
def csv_write(path, rows):
    rows = list(rows); keys = sorted({k for r in rows for k in r}) if rows else ['status']
    with Path(path).open('w', newline='', encoding='utf8') as f:
        w = csv.DictWriter(f, keys, extrasaction='ignore'); w.writeheader(); w.writerows(rows)
def json_gz_write(path, value):
    # mtime=0 makes byte-level replay stable for identical parser inputs.
    with gzip.GzipFile(filename=str(path), mode='wb', mtime=0) as raw:
        with io.TextIOWrapper(raw, encoding='utf8') as f: json.dump(value, f, ensure_ascii=False, separators=(',', ':'))
def json_gz_read(path):
    with gzip.open(path, 'rt', encoding='utf8') as f: return json.load(f)

def xlsx_sheets_rows(path):
    """Read xlsx while preserving Excel coordinates; never compact blank cells."""
    with zipfile.ZipFile(path) as z:
        strings = []
        if 'xl/sharedStrings.xml' in z.namelist():
            for si in ET.fromstring(z.read('xl/sharedStrings.xml')).iter(f'{NS}si'):
                strings.append(''.join(t.text or '' for t in si.iter(f'{NS}t')))
        wb = ET.fromstring(z.read('xl/workbook.xml'))
        rels = {r.get('Id'): r.get('Target') for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        out, meta = {}, {}
        for sheet in wb.iter(f'{NS}sheet'):
            target = rels[sheet.get(RNS + 'id')]
            target = target if target.startswith('xl/') else 'xl/' + target.lstrip('/')
            cells = {}
            for row in ET.fromstring(z.read(target)).iter(f'{NS}row'):
                for cell in row.iter(f'{NS}c'):
                    ref = cell.get('r'); v = cell.find(f'{NS}v')
                    if not ref: continue
                    value = '' if v is None else v.text or ''
                    if cell.get('t') == 's' and v is not None: value = strings[int(v.text)]
                    cells[(int(re.search(r'\d+', ref).group(0)) - 1, colnum(ref))] = value
            name = sheet.get('name')
            out[name] = sparse_rows(cells)
            root = ET.fromstring(z.read(target))
            merges = []
            for merge in root.iter(f'{NS}mergeCell'):
                if merge.get('ref'): merges.append(merge.get('ref'))
            meta[name] = {'merged_ranges': sorted(merges)}
        return out, meta

def sparse_rows(cells):
    if not cells: return []
    mr, mc = max(r for r, _ in cells), max(c for _, c in cells)
    return [[cells.get((r, c), '') for c in range(mc + 1)] for r in range(mr + 1)]

def xls_sheets_rows(path):
    return ({b['name']: sparse_rows(b['cells'])
             for b in biff8.parse(OLE2(Path(path).read_bytes()).read('Workbook'))},
            {})

def load_book(path):
    return xlsx_sheets_rows(path) if path.suffix.lower() == '.xlsx' else xls_sheets_rows(path)

def cell_text(book):
    return ' '.join(norm(v).lower() for rows in book.values() for row in rows for v in row if norm(v))

def classify(book, meta):
    """Positive content markers win; generic Nasdaq columns are deliberately neutral."""
    sheets = list(book)
    text = cell_text(book)
    fn = []
    mm = []
    if 'First North Trading Details' in sheets: fn.append('sheet:First North Trading Details')
    if 'Company Trading Overview' in sheets and 'first north' in text: fn.append('legacy_sheet+content:Company Trading Overview/First North')
    if re.search(r'\bfirst north\b', text): fn.append('content:First North')
    if re.search(r'\bmain market\b', text): mm.append('content:Main Market')
    if any('main market' in s.lower() for s in sheets): mm.append('sheet:Main Market')
    generic = sorted(h for rows in book.values() for row in rows[:25] for h in (norm(x).lower() for x in row) if h in COMMON)
    if mm and not fn: return 'MAIN_MARKET_QUARANTINE', fn, mm, generic, 'positive Main Market content with no positive First North marker'
    if fn and not mm:
        profile = 'FIRST_NORTH_MODERN_V1' if 'First North Trading Details' in sheets else 'FIRST_NORTH_LEGACY_V1'
        return profile, fn, mm, generic, 'positive First North workbook content; shared Nasdaq fields treated as neutral'
    if fn and mm: return 'AMBIGUOUS_QUARANTINE', fn, mm, generic, 'both market markers in workbook content'
    return 'AMBIGUOUS_QUARANTINE', fn, mm, generic, 'no positive market marker in workbook content'

def choose_data_sheet(book):
    if 'Instrument Trading Details' in book: return 'Instrument Trading Details'
    for name, rows in book.items():
        if any('isin' in [norm(v).lower() for v in row] for row in rows[:25]): return name
    return None

def header_sections(rows):
    """Return every physical header section on an instrument sheet.

    A modern workbook can contain several tables (Premier, cooperative
    instruments, then First North) on the same sheet.  The former parser
    selected the first header and incorrectly applied it to every later table.
    Each section below is a physical-header evidence object; it is not yet a
    data mapping.
    """
    found = []
    for i, row in enumerate(rows):
        h = [norm_header(x) for x in row]
        if 'isin' in h and ('issuer code' in h or 'company code' in h) and 'orderbook code' in h:
            found.append({'header_row': i, 'physical_header_grid': row[:],
                          'normalized_header_vector': h})
    for n, item in enumerate(found):
        item['data_start_row'] = item['header_row'] + 1
        item['data_end_row'] = found[n + 1]['header_row'] if n + 1 < len(found) else len(rows)
    return found

def header(rows):
    """Compatibility helper for callers that need only the first section."""
    sections = header_sections(rows)
    if not sections: return None, None
    return sections[0]['header_row'], sections[0]['normalized_header_vector']

def effective_width(row):
    for i in range(len(row) - 1, -1, -1):
        if norm(row[i]): return i + 1
    return 0

def field_positions_from_header(headers):
    positions = {}
    for index, label in enumerate(headers):
        key = FIELDS.get(label)
        if key and key not in positions: positions[key] = index
    # The Nasdaq Orderbook Code is the source identifier used at this parser
    # stage.  It is deliberately duplicated in the logical vector rather than
    # inferred later from ticker text.
    if 'ticker' in positions: positions['orderbook_id'] = positions['ticker']
    return positions

def mapping_evidence(headers, positions):
    evidence = {}
    for field in CANONICAL_FIELDS:
        if field in positions:
            i = positions[field]
            evidence[field] = {'physical_header_cells': [i],
                               'normalized_header': headers[i],
                               'data_column_index': i,
                               'mapping_method': 'SECTION_HEADER_EXACT_COORDINATE'}
        else:
            evidence[field] = {'physical_header_cells': [], 'normalized_header': None,
                               'data_column_index': None,
                               'mapping_method': 'SOURCE_FIELD_ABSENT'}
    return evidence

def row_is_candidate(row, positions):
    """Recognize a data row by its section-specific logical mapping only."""
    name = norm(row[positions['instrument']]) if 'instrument' in positions and positions['instrument'] < len(row) else ''
    ticker = norm(row[positions['ticker']]) if 'ticker' in positions and positions['ticker'] < len(row) else ''
    isin = norm(row[positions['isin']]) if 'isin' in positions and positions['isin'] < len(row) else ''
    typ = norm(row[positions['instrument_type']]) if 'instrument_type' in positions and positions['instrument_type'] < len(row) else ''
    return bool(ticker or isin or name) and typ.lower() in {'stock', 'share', 'shares'}

def structural_sentinels(row, positions):
    """Validate a selected mapping; never use values to shift a mapping."""
    errors = []
    def value(field):
        i = positions.get(field)
        return norm(row[i]) if i is not None and i < len(row) else ''
    currency, lp, isin, orderbook = value('currency').upper(), value('lp_yes').upper(), value('isin').upper(), value('orderbook_id')
    if currency in {'Y', 'N', 'YES', 'NO', 'TRUE', 'FALSE'}:
        errors.append('CURRENCY_BOOLEAN_DOMAIN_VIOLATION')
    elif currency and currency not in CURRENCY_DOMAIN:
        errors.append('CURRENCY_DOMAIN_VIOLATION:' + currency)
    if lp and lp not in LP_DOMAIN:
        errors.append('LP_YES_DOMAIN_VIOLATION:' + lp)
    if isin and not ISIN_RE.fullmatch(isin):
        errors.append('ISIN_STRUCTURAL_VIOLATION:' + isin)
    if orderbook and not re.fullmatch(r'[A-Za-z0-9 .\-_/]{1,64}', orderbook):
        errors.append('ORDERBOOK_ID_STRUCTURAL_VIOLATION:' + orderbook)
    return errors

def venue_from_source(location, currency, ticker):
    """Venue is an auditable source attribute, never a First-North default."""
    loc = norm(location).upper(); cur = norm(currency).upper(); code = norm(ticker).upper()
    if loc in {'HEL', 'HELSINKI', 'FINLAND'}: return 'NASDAQ_HELSINKI_FIRST_NORTH', 'LOCATION'
    if loc in {'STO', 'STOCKHOLM', 'SWEDEN'}: return 'NASDAQ_STOCKHOLM_FIRST_NORTH', 'LOCATION'
    if loc in {'CPH', 'COPENHAGEN', 'DENMARK'}: return 'NASDAQ_COPENHAGEN_FIRST_NORTH', 'LOCATION'
    if loc in {'ICE', 'ICELAND', 'REYKJAVIK'}: return 'NASDAQ_ICELAND_FIRST_NORTH', 'LOCATION'
    # Legacy files omit Location. The contemporaneous currency and Nordic
    # orderbook convention are explicit source cells and identify these pairs.
    if cur == 'EUR' and code.endswith('H'): return 'NASDAQ_HELSINKI_FIRST_NORTH', 'CURRENCY_AND_ORDERBOOK'
    if cur == 'SEK' and code.endswith('S'): return 'NASDAQ_STOCKHOLM_FIRST_NORTH', 'CURRENCY_AND_ORDERBOOK'
    return 'UNKNOWN_FIRST_NORTH_VENUE', 'INSUFFICIENT_SOURCE_EVIDENCE'

def schema_fingerprint(path, sheet, section, merged_ranges):
    positions = field_positions_from_header(section['normalized_header_vector'])
    # Core width is the rightmost canonical source cell needed for a complete
    # field mapping.  It is not the workbook's padded sparse-row length.
    core_width = max(positions.values(), default=-1) + 1
    fingerprint = {'file_type': path.suffix.lower().lstrip('.'), 'sheet_name': sheet,
                   'header_rows': [section['header_row']],
                   'merged_ranges_signature': hashlib.sha256('|'.join(merged_ranges).encode()).hexdigest(),
                   'normalized_header_structure': section['normalized_header_vector'],
                   'data_vector_width': core_width}
    serial = json.dumps(fingerprint, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return 'FN_SCHEMA_' + hashlib.sha256(serial.encode()).hexdigest()[:16], fingerprint, positions

def build_schema_registry(records):
    """Build an auditable registry from physical section structure only."""
    registry, assignments, workbook_evidence = {}, {}, {}
    for number, rec in enumerate(records, 1):
        path = (V / rec['local_path']).resolve()
        book, book_meta = load_book(path)
        sheet = choose_data_sheet(book)
        if not sheet: raise ValueError('DATA_SHEET_NOT_FOUND:' + rec['attachment_object_id'])
        sections = header_sections(book[sheet])
        if not sections: raise ValueError('HEADER_NOT_FOUND:' + rec['attachment_object_id'])
        section_ids = []
        for section in sections:
            schema_id, fingerprint, positions = schema_fingerprint(path, sheet, section, book_meta.get(sheet, {}).get('merged_ranges', []))
            section_ids.append(schema_id)
            if schema_id not in registry:
                registry[schema_id] = {'schema_id': schema_id, 'fingerprint': fingerprint, 'workbook_count': 0,
                                       'workbooks': [], 'first_observed': rec['report_month'], 'last_observed': rec['report_month'],
                                       'file_type': fingerprint['file_type'], 'sheet': sheet,
                                       'header_rows': fingerprint['header_rows'],
                                       'merged_ranges_signature': fingerprint['merged_ranges_signature'],
                                       'logical_field_vector': sorted(positions, key=positions.get),
                                       'expected_data_width': fingerprint['data_vector_width'],
                                       'field_to_data_index': positions,
                                       'mapping_evidence': mapping_evidence(section['normalized_header_vector'], positions),
                                       'validation_examples': []}
            item = registry[schema_id]
            item['workbooks'].append({'disclosure_id': rec['disclosure_id'], 'report_month': rec['report_month'],
                                      'sha256': rec['sha256'], 'header_row': section['header_row'],
                                      'data_start_row': section['data_start_row'], 'data_end_row': section['data_end_row']})
            item['first_observed'] = min(item['first_observed'], rec['report_month'])
            item['last_observed'] = max(item['last_observed'], rec['report_month'])
            if len(item['validation_examples']) < 3:
                item['validation_examples'].append({'disclosure_id': rec['disclosure_id'], 'report_month': rec['report_month'],
                                                    'header_row': section['header_row'], 'data_start_row': section['data_start_row']})
        # A workbook is assigned one deterministic composite schema bundle even
        # when it carries multiple independently headed tables.
        bundle = 'FN_WORKBOOK_SCHEMA_' + hashlib.sha256('|'.join(sorted(section_ids)).encode()).hexdigest()[:16]
        assignments[rec['attachment_object_id']] = {'workbook_schema_id': bundle, 'section_schema_ids': section_ids}
        workbook_evidence[rec['attachment_object_id']] = {'sheet': sheet, 'sections': sections, 'book_meta': book_meta}
        if number % 10 == 0:
            print(f'schema_registry {number}/{len(records)} profiles={len(registry)}', flush=True)
    for item in registry.values():
        item['workbook_count'] = len({x['disclosure_id'] for x in item['workbooks']})
        item['workbooks'].sort(key=lambda x: (x['report_month'], x['disclosure_id'], x['header_row']))
    return registry, assignments, workbook_evidence

def parse_observations(book, book_meta, meta, registry, assignment):
    sheet = choose_data_sheet(book)
    if not sheet: raise ValueError('DATA_SHEET_NOT_FOUND')
    rows = book[sheet]; sections = header_sections(rows)
    expected = assignment['section_schema_ids']
    if len(sections) != len(expected): raise ValueError('SCHEMA_SECTION_COUNT_MISMATCH')
    out, invariant_failures = [], []
    for section, schema_id in zip(sections, expected):
        profile = registry.get(schema_id)
        if not profile: raise ValueError('UNKNOWN_SCHEMA:' + schema_id)
        positions = profile['field_to_data_index']
        if section['normalized_header_vector'] != profile['fingerprint']['normalized_header_structure']:
            raise ValueError('SCHEMA_HEADER_FINGERPRINT_MISMATCH:' + schema_id)
        def val(row, key):
            index = positions.get(key)
            return norm(row[index]) if index is not None and index < len(row) else ''
        for physical_row, row in enumerate(rows[section['data_start_row']:section['data_end_row']], section['data_start_row']):
            if not row_is_candidate(row, positions): continue
            # The row must at least contain the profile's required core vector;
            # optional trailing market-statistics cells can be absent in source.
            if effective_width(row) < profile['expected_data_width']:
                invariant_failures.append({'schema_id': schema_id, 'physical_row': physical_row,
                                           'failure': 'FIELD_ALIGNMENT_INVARIANT_FAILURE:DATA_VECTOR_TOO_SHORT'})
                continue
            errors = structural_sentinels(row, positions)
            if errors:
                invariant_failures.append({'schema_id': schema_id, 'physical_row': physical_row,
                                           'failure': 'FIELD_ALIGNMENT_INVARIANT_FAILURE:' + '|'.join(errors)})
                continue
            ticker, isin, name, typ = val(row, 'ticker'), val(row, 'isin'), val(row, 'instrument'), val(row, 'instrument_type')
            currency = val(row, 'currency').upper()
            out.append({
                'report_month': meta['report_month'], 'known_from': (meta.get('release_time') or '')[:10],
                'market': 'FIRST_NORTH', 'issuer_name': name or None, 'issuer_code': val(row, 'issuer_code') or None,
                'ticker': ticker or None, 'orderbook_id': val(row, 'orderbook_id') or None,
                'isin': isin or None, 'instrument_type': typ, 'lp_yes': val(row, 'lp_yes').upper() or None,
                'location': val(row, 'location') or None, 'currency': currency or 'UNKNOWN',
                'currency_source': 'DIRECT_INSTRUMENT_ROW' if 'currency' in positions else 'SOURCE_FIELD_ABSENT',
                'segment': val(row, 'segment') or 'FIRST_NORTH_UNSPECIFIED',
                'industry': val(row, 'industry') or None, 'supersector': val(row, 'supersector') or None,
                'source_disclosure_id': meta.get('disclosure_id'), 'source_attachment_url': meta.get('attachment_url'),
                'source_raw_object': meta['local_path'], 'source_sha256': meta['sha256'], 'data_sheet': sheet,
                'schema_id': schema_id, 'physical_header_row': section['header_row'], 'physical_data_row': physical_row,
            })
    return out, invariant_failures

def month_next(month):
    y, m = map(int, month.split('-')); return f'{y+1:04d}-01' if m == 12 else f'{y:04d}-{m+1:02d}'

def intervals(rows):
    groups = defaultdict(list)
    for r in rows: groups[(r['ticker'] or '', r['isin'] or '', r['venue'])].append(r)
    result, identities = [], []
    for (ticker, isin, venue), rs in sorted(groups.items()):
        rs.sort(key=lambda r: r['report_month'])
        iid = f'FN:ISIN:{isin}' if isin else f'FN:ORDERBOOK:{venue}:{ticker}'
        identities.append({'canonical_instrument_id': iid, 'ticker': ticker, 'isin': isin,
                           'first_seen': rs[0]['report_month'], 'last_seen': rs[-1]['report_month'],
                           'months_present': len({r['report_month'] for r in rs}), 'market': 'FIRST_NORTH',
                           'venue': venue})
        for field in ('issuer_name', 'issuer_code', 'segment', 'industry', 'supersector', 'location', 'currency', 'venue'):
            cur = None
            for r in rs:
                if cur and cur['value'] == r[field] and r['report_month'] == month_next(cur['observation_to']):
                    cur['observation_to'] = r['report_month']
                else:
                    if cur: result.append(cur)
                    cur = {'canonical_instrument_id': iid, 'ticker': ticker, 'isin': isin, 'field': field,
                           'value': r[field], 'observation_from': r['report_month'], 'observation_to': r['report_month'],
                           'known_from': r['known_from'], 'market': 'FIRST_NORTH', 'venue': venue}
            if cur: result.append(cur)
    return identities, result

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path, default=OUT, help='separate parser-only output directory')
    args = ap.parse_args()
    if not MANIFEST.exists(): raise SystemExit(f'MISSING_RAW_MANIFEST:{MANIFEST}')
    out_dir = args.output.resolve(); out_dir.mkdir(parents=True, exist_ok=True)
    all_m = json.loads(MANIFEST.read_text())['files']
    if len(all_m) != 200: raise SystemExit(f'RAW_MANIFEST_RECORD_COUNT_NOT_200:{len(all_m)}')
    # Registry construction reads only immutable content-addressed raw objects.
    registry, assignments, _ = build_schema_registry(all_m)
    (out_dir / 'FIRST_NORTH_SCHEMA_REGISTRY.json').write_text(json.dumps({
        'schema_version': 'FIRST_NORTH_SCHEMA_REGISTRY_V1', 'registry': registry,
        'workbook_assignments': assignments}, ensure_ascii=False, indent=2, sort_keys=True))
    audit, parsed = [], []
    stages = {'RAW_COMPLETE': {'input': len(all_m), 'success': 0, 'skipped': 0, 'quarantined': 0, 'failed': 0, 'output': None}}
    dispositions = set()
    invariant_rows = []
    for number, rec in enumerate(all_m, 1):
        path = (V / rec['local_path']).resolve()
        base = {'report_month': rec.get('report_month'), 'disclosure_id': rec.get('disclosure_id'), 'publication_timestamp': rec.get('release_time'),
                'filename': rec.get('filename'), 'attachment_url': rec.get('attachment_url'), 'local_path': rec.get('local_path'),
                'sha256': rec.get('sha256'), 'attachment_object_id': rec.get('attachment_object_id'), 'cache_status': rec.get('cache_status'), 'provenance_verification': rec.get('provenance_verification')}
        if RAW_ROOT.resolve() not in path.parents or not path.exists() or digest(path) != rec['sha256']:
            audit.append({**base, 'final_classification': 'PARSE_FAILURE', 'classification_reason': 'content-addressed path or hash verification failed'})
            dispositions.add(rec['attachment_object_id']); continue
        stages['RAW_COMPLETE']['success'] += 1
        try:
            book, book_meta = load_book(path); classification, fn, mm, common, reason = classify(book, rec)
            evidence = {**base, 'sheet_names': '|'.join(book), 'first_north_markers': '|'.join(fn), 'main_market_markers': '|'.join(mm),
                        'common_neutral_fields': '|'.join(sorted(set(common))), 'workbook_schema_id': assignments[rec['attachment_object_id']]['workbook_schema_id'],
                        'section_schema_ids': '|'.join(assignments[rec['attachment_object_id']]['section_schema_ids']),
                        'final_classification': classification, 'classification_reason': reason}
            if not classification.startswith('FIRST_NORTH_'):
                audit.append(evidence); dispositions.add(rec['attachment_object_id']); continue
            obs, failures = parse_observations(book, book_meta, rec, registry, assignments[rec['attachment_object_id']])
            evidence['extracted_observations'] = len(obs); evidence['field_alignment_failures'] = len(failures)
            audit.append(evidence); parsed.extend(obs)
            invariant_rows.extend([{**base, **x} for x in failures]); dispositions.add(rec['attachment_object_id'])
        except Exception as exc:
            audit.append({**base, 'final_classification': 'PARSE_FAILURE', 'classification_reason': f'{type(exc).__name__}:{exc}'})
            dispositions.add(rec['attachment_object_id'])
        if number % 10 == 0:
            print(f'parser_stage {number}/{len(all_m)} observations={len(parsed)} dispositions={len(dispositions)}', flush=True)
    if len(dispositions) != len(all_m): raise RuntimeError('SILENT_DROP_INVARIANT_FAILED')
    classifications = Counter(a['final_classification'] for a in audit)
    stages['PARSE_COMPLETE'] = {'input': len(all_m), 'success': sum(n for k,n in classifications.items() if k.startswith('FIRST_NORTH_')), 'skipped': 0,
                                'quarantined': sum(n for k,n in classifications.items() if 'QUARANTINE' in k), 'failed': classifications['PARSE_FAILURE'], 'output': 'workbook_audit.csv'}
    csv_write(out_dir / 'workbook_audit.csv', audit)
    csv_write(out_dir / 'parser_dispositions.csv', [{'attachment_object_id': a['attachment_object_id'], 'disposition': a['final_classification']} for a in audit])
    csv_write(out_dir / 'field_alignment_failures.csv', invariant_rows)
    values = Counter(r['currency'] for r in parsed)
    invalid = {k:v for k,v in values.items() if k != 'UNKNOWN' and k not in CURRENCY_DOMAIN}
    stages['SCHEMA_ASSIGNED'] = {'input': len(all_m), 'success': len(assignments), 'skipped': 0, 'quarantined': 0, 'failed': len(all_m)-len(assignments), 'output': 'FIRST_NORTH_SCHEMA_REGISTRY.json'}
    stages['QA_COMPLETE'] = {'input': len(parsed), 'success': len(parsed) if not invariant_rows and not invalid else 0,
                             'skipped': 0, 'quarantined': 0, 'failed': len(invariant_rows)+len(invalid), 'output': 'schema_qa.json'}
    qa = {'raw_input': len(all_m), 'schema_assigned': len(assignments), 'parser_attempted': len(audit),
          'parsed': stages['PARSE_COMPLETE']['success'], 'quarantined': stages['PARSE_COMPLETE']['quarantined'],
          'failed': stages['PARSE_COMPLETE']['failed'], 'silent_drop': len(all_m)-len(dispositions),
          'field_alignment_invariant_failures': len(invariant_rows), 'currency_values': dict(sorted(values.items())),
          'invalid_currency_values': invalid, 'currency_schema_alignment': 'PASS' if not invariant_rows else 'FAIL',
          'currency_domain': 'PASS' if not invalid else 'FAIL',
          'raw_provenance': 'PASS' if stages['RAW_COMPLETE']['success']==len(all_m) else 'FAIL',
          'parser_schema_audit': 'PASS' if not invariant_rows and not invalid and stages['PARSE_COMPLETE']['failed']==0 and stages['PARSE_COMPLETE']['quarantined']==0 else 'FAIL',
          'company_master_integration_ready': 'NO'}
    json_gz_write(out_dir/'schema_repaired_observations.json.gz', {'rows':parsed})
    (out_dir/'schema_qa.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2,sort_keys=True))
    result = {'schema':'FIRST_NORTH_SCHEMA_REPAIR_V1','created_utc':utc(),'stages':stages,'classification':dict(classifications),'qa':qa,
              'parsed_observations':len(parsed),'main_market_mutated':False,'production_mutation_performed':False,
              'downstream_work_run':False}
    (out_dir/'STAGE_COUNTS.json').write_text(json.dumps({'created_utc':utc(),'stages':stages},indent=2))
    (out_dir/'FINAL_RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__ == '__main__': main()
