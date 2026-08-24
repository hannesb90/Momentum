import hashlib,json,pathlib,sys,urllib.request,html,zipfile,xml.etree.ElementTree as ET
from datetime import datetime,timezone
V=pathlib.Path('/home/hannesb/momentum_v2'); D=V/'research_k/nasdaq_historical_master/first_north/alternative_discovery'; R=D/'sample_raw'; R.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(V/'tools/nasdaq_segment'));from ole2 import OLE2
import biff8
S=[('2026-03','NASDAQ_VIEW','https://view.news.eu.nasdaq.com/view?id=bcc90c76404e448b9c373f6f4cb78be3e&lang=en','https://attachment.news.eu.nasdaq.com/a0c7525910acdc890928976edd6d3b3df','Equity Trading by Company and Instrument - First North 2603.xlsx'),('2024-09','NASDAQ_VIEW','https://view.news.eu.nasdaq.com/view?id=b07f405d62ce82d99236f5ffb3325fc65&lang=en','https://attachment.news.eu.nasdaq.com/adf114a70cdd329ee7daf22701d9ec6da','Equity Trading by Company and Instrument - First North 2409.xlsx'),('2018-07','GLOBENEWSWIRE_ESR','https://www.globenewswire.com/news-release/2018/08/02/1546022/0/en/Equity-Trading-by-Company-First-North-July-2018.html','https://www.globenewswire.com/Attachment/DownloadAttachment?articleid=1546022&fileId=555988&filename=Equity%20Trading%20by%20Company%20and%20Instrument%20-%20First%20North%201807.xls&filetype=3&islogo=0','Equity Trading by Company and Instrument - First North 1807.xls'),('2012-10','GLOBENEWSWIRE_ESR','https://www.globenewswire.com/news-release/2012/11/08/503563/0/en/Equity-Trading-by-Company-First-North-October-2012.html','https://www.globenewswire.com/Attachment/DownloadAttachment?articleid=503563&fileId=232796&filename=Equity%20Trading%20by%20Company%20and%20Instrument%20-%20First%20North%201210.xls&filetype=3&islogo=0','Equity Trading by Company and Instrument - First North 1210.xls'),('2010-01','NASDAQ_VIEW','https://view.news.eu.nasdaq.com/view?id=bad786badca523163ffd53c8bcdf6371a&lang=en','https://attachment.news.eu.nasdaq.com/a4b16bc9451a921c0a347af1bd2bfc327','Equity Trading by Company and Instrument - First North 1001.xls')]
NS='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}';RNS='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
def sheets_headers(p):
 if p.suffix=='.xlsx':
  z=zipfile.ZipFile(p);ss=[]
  if 'xl/sharedStrings.xml' in z.namelist():
   for si in ET.fromstring(z.read('xl/sharedStrings.xml')).iter(f'{NS}si'):ss.append(''.join(t.text or '' for t in si.iter(f'{NS}t')))
  wb=ET.fromstring(z.read('xl/workbook.xml'));rels={r.get('Id'):r.get('Target') for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}; names=[];hdr=[]
  for s in wb.iter(f'{NS}sheet'):
   names.append(s.get('name'));t=rels[s.get(RNS+'id')];t=t if t.startswith('xl/') else 'xl/'+t
   if s.get('name')=='Instrument Trading Details':
    for row in ET.fromstring(z.read(t)).iter(f'{NS}row'):
     x=[]
     for c in row.iter(f'{NS}c'):
      v=c.find(f'{NS}v');x.append(ss[int(v.text)] if c.get('t')=='s' and v is not None else (v.text if v is not None else ''))
     if any(str(q).strip().lower()=='isin' for q in x):hdr=x;break
  return names,hdr
 names=[];hdr=[]
 for b in biff8.parse(OLE2(p.read_bytes()).read('Workbook')):
  names.append(b['name'])
  if b['name']=='Instrument Trading Details':
   c=b['cells'];
   for r in range(min(30,max((a for a,_ in c),default=0)+1)):
    x=[c.get((r,k),'') for k in range(max((b for _,b in c),default=0)+1)]
    if any(str(q).strip().lower()=='isin' for q in x):hdr=x;break
 return names,hdr
out=[]
for month,src,pub,url,fn in S:
 ext='.xlsx' if fn.endswith('xlsx') else '.xls';p=R/(month+ext)
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=120) as f:p.write_bytes(f.read())
  sn,h=sheets_headers(p);hh={' '.join(str(x).split()).lower() for x in h};passed=('First North Trading Details' in sn and 'issuer code' in hh and 'location' not in hh and 'company code' not in hh)
  out.append({'month':month,'publication_url':pub,'attachment_url':url,'attachment_filename':fn,'discovery_source':src,'retrieval_timestamp':datetime.now(timezone.utc).isoformat(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'sheets':sn,'headers':h,'signature':'PASS' if passed else 'FAIL'})
 except Exception as e:
  out.append({'month':month,'publication_url':pub,'attachment_url':url,'attachment_filename':fn,'discovery_source':src,'signature':'FETCH_FAIL','error':type(e).__name__+': '+str(e)[:200]})
D.joinpath('era_sample.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False,indent=2))
