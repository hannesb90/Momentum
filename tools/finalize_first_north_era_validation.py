"""Finalize locally fetched First North era files; transport failures remain explicit."""
import hashlib,json,pathlib,sys,zipfile,xml.etree.ElementTree as ET
V=pathlib.Path('/home/hannesb/momentum_v2');D=V/'research_k/nasdaq_historical_master/first_north/alternative_discovery';R=D/'sample_raw';sys.path.insert(0,str(V/'tools/nasdaq_segment'));from ole2 import OLE2
import biff8
NS='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}';RNS='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
def compact(x):return ' '.join(str(x or '').split()).lower()
def header(p):
 if p.suffix=='.xlsx':
  z=zipfile.ZipFile(p);ss=[]
  if 'xl/sharedStrings.xml' in z.namelist():
   for si in ET.fromstring(z.read('xl/sharedStrings.xml')).iter(f'{NS}si'):ss.append(''.join(t.text or '' for t in si.iter(f'{NS}t')))
  wb=ET.fromstring(z.read('xl/workbook.xml'));rels={r.get('Id'):r.get('Target') for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))};sn=[];hh=[]
  for s in wb.iter(f'{NS}sheet'):
   sn.append(s.get('name'))
   if s.get('name')=='Instrument Trading Details':
    t=rels[s.get(RNS+'id')];t=t if t.startswith('xl/') else 'xl/'+t
    for row in ET.fromstring(z.read(t)).iter(f'{NS}row'):
     q=[]
     for c in row.iter(f'{NS}c'):
      v=c.find(f'{NS}v');q.append(ss[int(v.text)] if c.get('t')=='s' and v is not None else(v.text if v is not None else ''))
     if 'isin' in {compact(x) for x in q}:hh=q;break
  return sn,hh
 sn=[];hh=[]
 for b in biff8.parse(OLE2(p.read_bytes()).read('Workbook')):
  sn.append(b['name'])
  if b['name']=='Instrument Trading Details':
   c=b['cells']
   for r in range(min(max((x for x,_ in c),default=0)+1,30)):
    q=[c.get((r,k),'') for k in range(max((x for _,x in c),default=0)+1)]
    if 'isin' in {compact(x) for x in q}:hh=q;break
 return sn,hh
meta={'2026-03':('NASDAQ_VIEW','https://view.news.eu.nasdaq.com/view?id=bcc90c76404e448b9c373f6f4cb78be3e&lang=en'),'2024-09':('NASDAQ_VIEW','https://view.news.eu.nasdaq.com/view?id=b07f405d62ce82d99236f5ffb3325fc65&lang=en'),'2018-07':('GLOBENEWSWIRE_ESR','https://www.globenewswire.com/news-release/2018/08/02/1546022/0/en/Equity-Trading-by-Company-First-North-July-2018.html'),'2012-10':('GLOBENEWSWIRE_ESR','https://www.globenewswire.com/news-release/2012/11/08/503563/0/en/Equity-Trading-by-Company-First-North-October-2012.html'),'2010-01':('NASDAQ_VIEW','https://view.news.eu.nasdaq.com/view?id=bad786badca523163ffd53c8bcdf6371a&lang=en')}
out=[]
for m,(source,pub) in meta.items():
 ps=list(R.glob(m+'.*'))
 if not ps:out.append({'month':m,'publication_url':pub,'discovery_source':source,'status':'TRANSPORT_FAILURE','reason':'publication and filename verified; attachment retrieval did not complete, not SOURCE_MISSING'});continue
 p=ps[0];sn,hh=header(p); hs={compact(x) for x in hh}; modern='first north trading details' in {compact(x) for x in sn}; legacy=('instrument trading details' in {compact(x) for x in sn})
 ok=(modern or legacy) and 'issuer code' in hs and 'location' not in hs and 'company code' not in hs
 out.append({'month':m,'publication_url':pub,'discovery_source':source,'local_path':str(p.relative_to(V)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'status':'PASS' if ok else 'FAIL','parser_profile':'FIRST_NORTH_MODERN_V1' if modern else ('FIRST_NORTH_LEGACY_V1' if legacy else 'UNRECOGNIZED'),'sheets':sn,'required_fields_present':{'issuer_code':'issuer code' in hs,'location_absent':'location' not in hs,'company_code_absent':'company code' not in hs}})
D.joinpath('era_sample_final.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False,indent=2))
