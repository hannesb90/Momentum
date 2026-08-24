#!/usr/bin/env python3
"""Build K1 sector-classification freeze. Never reads targets or returns."""
from pathlib import Path
import csv, hashlib, json, datetime

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'research_k'/'sector_classification_v1'
AV=ROOT/'research_k/avanza_sector_recovery_probe/qa_identity_sector_evidence.json'
TE=ROOT/'validated/terminal_events.json'
PX=ROOT/'validated/prices/prices_validated.json'

RAW='''KLOV-PREF|Klövern Pref|Fastigheter|Kommersiella fastigheter|Hög
LEO|LeoVegas|Sällanköpsvaror|Online betting/casino|Hög
MAG|Magnolia Bostad|Fastigheter|Bostadsutveckling|Hög
MIC-SDB|Millicom|Kommunikation|Telekom|Hög
MULQ|MultiQ|Teknologi|Digital signage/displaylösningar|Hög
NET-B|NetEnt|Sällanköpsvaror/Teknologi|Programvara för onlinecasino|Hög*
NOBINA|Nobina|Industri|Kollektivtrafik/persontransport|Hög
NORVA|Norva24|Industri|Infrastrukturservice|Hög
NPAPER|Nordic Paper|Material|Papper & massa|Hög
NWG|Nordic Waterproofing|Industri|Byggprodukter/tätskikt|Hög
OP|Oscar Properties|Fastigheter|Fastighetsutveckling/förvaltning|Hög
OPUS|Opus Group|Industri|Fordonsinspektion|Hög
OX2|OX2|Energi/Utilities|Förnybar energiutveckling|Medel*
PENG-B|Projektengagemang|Industri|Teknikkonsult|Hög
PROB|Probi|Hälsovård|Probiotika/bioteknik|Hög
RECI-B|Recipharm|Hälsovård|Läkemedel/CDMO|Hög
RESURS|Resurs Holding|Finans|Konsumentkrediter/bank|Hög
RIZZO-B|Rizzo Group|Sällanköpsvaror|Detaljhandel skor/accessoarer|Hög
SAS|SAS|Industri|Flygbolag|Hög
SEMC|Semcon|Industri|Teknikkonsult|Hög
SMF|SEMAFO|Material|Guldgruvor|Hög
SPOR|Sportamore|Sällanköpsvaror|E-handel sport|Hög
SRNKE-B|Serneke|Industri|Bygg & entreprenad|Hög
SSM|SSM Holding|Fastigheter|Bostadsutveckling|Hög
STRAX|Strax|Teknologi|Mobilaccessoarer/distribution|Medel*
SWMA|Swedish Match|Dagligvaror|Tobak/nikotin|Hög
SWOL-B|Swedol|Industri|Handel/distribution yrkesprodukter|Medel*
TETY|Tethys Oil|Energi|Olja & gas|Hög
TRENT|Trention|Finans|Investment-/finansieringsbolag|Hög
VNE-SDB|Veoneer|Sällanköpsvaror|Fordonskomponenter/ADAS|Hög
ZETA|ZetaDisplay|Teknologi/Kommunikation|Digital signage|EJ ANGIVEN
ENG|Internationella Engelska Skolan|Sällanköpsvaror|Utbildning|Hög
ETX|Etrion|Energi|Solenergi / kraftproduktion|Hög
FEEL|Feelgood|Hälsovård|Företagshälsovård|Hög
FNOX|Fortnox|Teknologi|Affärssystem / SaaS|Hög
GHP|GHP Specialty Care|Hälsovård|Specialistvård|Hög
GUNN|Gunnebo|Industri|Säkerhetslösningar|Hög
HANDI|Handicare|Hälsovård|Medicinteknik / hjälpmedel|Hög
HEM-B|Hembla|Fastigheter|Bostadsfastigheter|Hög
HEMF|Hemfosa Fastigheter|Fastigheter|Samhälls-/kommersiella fastigheter|Hög
HIQ|HiQ|Teknologi|IT-/teknikkonsult|Hög
HLDX|Haldex|Industri|Fordonskomponenter|Hög
IAR-B|I.A.R Systems|Teknologi|Embedded-mjukvara / utvecklingsverktyg|Hög
ICA|ICA Gruppen|Dagligvaror|Dagligvaruhandel|Hög
IRRAS|IRRAS|Hälsovård|Medicinteknik|Hög
JOSE|Josemaria Resources|Material|Gruvprospektering / koppar-guld|Hög
KLED|Kungsleden|Fastigheter|Kommersiella fastigheter|Hög
ATVEXA-B|Atvexa|Sällanköpsvaror|Utbildning / skolor|Hög
BFG|Byggfakta Group|Teknologi|Bygginformation / data & mjukvara|Hög
BIOT|Biotage|Hälsovård|Life-scienceverktyg / laboratorieutrustning|Hög
BRG-B|Bergs Timber|Material|Trävaror / skogsprodukter|Hög
CALTX|Calliditas Therapeutics|Hälsovård|Bioteknik / läkemedel|Hög
CARY|Cary Group|Sällanköpsvaror|Fordonsservice / bilglas|Hög
CCOR-B|Concordia Maritime|Industri|Sjöfart / tankrederi|Hög
COIC|Concentric|Industri|Fordons-/industrikomponenter|Hög
COLL|Collector|Finans|Bank / konsument- och företagsfinansiering|Hög
CPAC-SPAC|Creaspac|Finans|SPAC / investmentbolag|Hög*
CS|CoinShares|Finans|Digitala tillgångar / kapitalförvaltning|Hög
DORO|Doro|Teknologi|Telekom-/konsumentelektronik|Hög*
EDGE|Edgeware|Teknologi|Videodistribution / streamingteknik|Hög
ELOS-B|Elos Medtech|Hälsovård|Medicinteknik / kontraktstillverkning|Hög
ENDO|Endomines|Material|Guldgruvor / mineralutvinning|Hög
ABLI|Abliva|Hälsovård|Bioteknik / läkemedelsutveckling|Hög
ADAPT|Adapteo|Industri|Modulbyggnader / flexibla lokaler|Hög
AGRO|Agromino|Dagligvaror|Jordbruk / lantbruksproduktion|Hög
AM1S|Ahlstrom-Munksjö|Material|Fiberbaserade specialmaterial / papper|Hög
ARISE|Arise|Energi|Vindkraft / förnybar energi|Hög
ATRE|A3 Allmänna IT- och Telekomaktiebolaget|Kommunikation|Telekom / bredband / IT-tjänster|Hög'''

SECTOR={'Fastigheter':'Fastigheter','Sällanköpsvaror':'Konsumentvaror & Tjänster','Sällanköpsvaror/Teknologi':'Konsumentvaror & Tjänster','Kommunikation':'Teknologi','Teknologi/Kommunikation':'Teknologi','Teknologi':'Teknologi','Industri':'Industri','Material':'Råmaterial','Energi/Utilities':'Energi','Energi':'Energi','Hälsovård':'Hälsovård','Finans':'Finans','Dagligvaror':'Konsumentvaror & Tjänster'}
MANUAL_ONLY={'ADAPT','AGRO','COLL','ENDO','ETX','JOSE','MIC-SDB','SMF','TETY'}
PRIMARY={'KLOV-PREF','ADAPT','COLL','ENDO'}

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,x): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')

def main():
 av=json.load(open(AV)); te=json.load(open(TE)); prices=json.load(open(PX))
 dates={k:[r.get('d') or r.get('date') for r in rs if r.get('d') or r.get('date')] for k,rs in prices.items()}
 rows=[]; manual=[]
 candidates=[]
 for line in RAW.splitlines():
  t,n,s,i,c=line.split('|'); candidates.append({'ticker':t,'company_name':n,'candidate_sector':s,'candidate_industry':i,'classification_method':'MANUAL_EXPERT_CLASSIFICATION','confidence':c,'valid_from':min(dates.get(t,['2020-01-01'])),'valid_to':te[t]['event_date'],'source_evidence':'USER_PROVIDED_CANDIDATE; QA_REQUIRED','QA_status':'MANUAL_EXPERT_CLASSIFICATION','notes':'Candidate input; never PIT_VERIFIED by manual label alone.'})
 assert len(candidates)==68 and set(x['ticker'] for x in candidates)==set(te)
 dump(OUT/'inputs/manual_terminal_candidates.json',candidates)
 paths=sorted({tuple(x['avanza_sector_path_raw']) for x in av if x.get('avanza_sector_path_raw')})
 dump(OUT/'taxonomy/avanza_canonical_taxonomy.json',[{'canonical_industry':p[0],'canonical_group':p[1] if len(p)>2 else None,'canonical_sector':p[-1],'raw_path':list(p)} for p in paths])
 # Current instruments: exact Avanza identity and sector; historical use is explicitly stable-entity support, not PIT financial data.
 for x in av:
  if x.get('terminal'): continue
  p=x.get('avanza_sector_path_raw') or []
  rows.append({'instrument_id':x['instrument_id'],'isin':x['expected_isin'],'company_name':x['expected_name'],'terminal':False,'canonical_sector':p[-1] if p else 'UNKNOWN','canonical_industry':p[0] if p else 'UNKNOWN','valid_from':min(dates.get(x['instrument_id'],['2020-01-01'])),'valid_to':None,'qa_status':'STABLE_CLASSIFICATION_SUPPORTED' if p else 'UNRESOLVED','identity_status':x['identity_method'],'evidence':[x.get('source_url'),'three V1/Borsdata snapshots; see K1 provenance audit'],'limitations':['historical sector changes not fully observable between snapshots']})
 by={x['ticker']:x for x in candidates}; ae={x['instrument_id']:x for x in av}
 cross=[]
 for t in sorted(te):
  c=by[t]; a=ae[t]; sec=SECTOR[c['candidate_sector']]
  # Exact Avanza leaf where recovered; otherwise conservative semantic industry label within locked broad taxonomy.
  p=a.get('avanza_sector_path_raw') or []
  ind=p[0] if p and p[-1]==sec else 'UNKNOWN'
  status='SOURCE_VERIFIED' if t in PRIMARY else ('MANUAL_EXPERT_CLASSIFICATION' if t in MANUAL_ONLY else 'STABLE_CLASSIFICATION_SUPPORTED')
  ev=[]
  if a.get('source_url'): ev.append(a['source_url'])
  if t not in MANUAL_ONLY: ev.append('trackj/validated_mfn_events_v1/validated_mfn_events.jsonl (exact ISIN contemporaneous issuer events)')
  if t=='KLOV-PREF': ev += ['https://view.news.eu.nasdaq.com/view?id=be51019e28103754e27ce7659d5103d9b&lang=en','https://www.corem.se/en/investor-relations/offer-for-klovern/','https://kelly.corem.se/app/uploads/2021/03/klovern__arsredovsning_2020.pdf']
  if t=='ADAPT': ev.append('https://www.goldmansachs.com/disclosures/sweden/announcements/docs/Offer-document-WSIP-Bidco-23-June-2021.pdf')
  if t=='COLL': ev.append('https://docs.norionbank.se/globalassets/4-investor-relations/4.1-finansiell-information/4.1.3-aktien/4.1.3.4-fusioner--nyemissoner/collector-bank-fusionsprospekt-20-april-2022.pdf')
  if t=='ENDO': ev.append('https://ipo.endomines.com/wp-content/uploads/2022/11/Prospectus.pdf')
  note=''
  if t=='KLOV-PREF': note='Klövern AB preference share SE0006593927 through 2021-07-20; Corem Kelly is renamed post-offer issuer and is not back-classified.'
  if ind=='UNKNOWN': note=(note+' Industry unresolved: no exact Avanza canonical leaf can be defended.').strip()
  row={'instrument_id':t,'isin':a['expected_isin'],'company_name':c['company_name'],'terminal':True,'canonical_sector':sec,'canonical_industry':ind,'valid_from':min(dates.get(t,['2020-01-01'])),'valid_to':te[t]['event_date'],'qa_status':status,'identity_status':a['identity_method'],'candidate_confidence':c['confidence'],'evidence':ev,'limitations':['manual semantic crosswalk to locked Avanza taxonomy'],'notes':note}
  rows.append(row); cross.append({'instrument_id':t,'candidate_sector':c['candidate_sector'],'candidate_industry':c['candidate_industry'],'canonical_sector':sec,'canonical_industry':ind,'rule':'manual semantic crosswalk; no target/return information'})
 dump(OUT/'taxonomy/terminal_crosswalk.json',cross)
 dump(OUT/'validated/sector_classification_intervals.json',sorted(rows,key=lambda x:x['instrument_id']))
 from collections import Counter
 cnt=Counter(x['qa_status'] for x in rows)
 rowmap={x['instrument_id']:x for x in rows}; panel=json.load(open(ROOT/'panels/core_panel.json')); yearly={}
 for p in panel:
  y=p['panel_date'][:4]; r=rowmap[p['kod']]; z=yearly.setdefault(y,{'rows':0,'sector_labeled':0,'industry_labeled':0,'verified_or_stable':0,'terminal_rows':0})
  z['rows']+=1; z['sector_labeled']+=r['canonical_sector']!='UNKNOWN'; z['industry_labeled']+=r['canonical_industry']!='UNKNOWN'; z['verified_or_stable']+=r['qa_status'] in {'SOURCE_VERIFIED','STABLE_CLASSIFICATION_SUPPORTED'}; z['terminal_rows']+=r['terminal']
 terminal_year=Counter(v['event_date'][:4] for v in te.values())
 cov={'total':len(rows),'current':sum(not x['terminal'] for x in rows),'terminal':sum(x['terminal'] for x in rows),'sector_labeled':sum(x['canonical_sector']!='UNKNOWN' for x in rows),'industry_labeled':sum(x['canonical_industry']!='UNKNOWN' for x in rows),'qa_status':dict(cnt),'verified_or_stable':sum(x['qa_status'] in {'SOURCE_VERIFIED','STABLE_CLASSIFICATION_SUPPORTED'} for x in rows),'manual_or_weaker':sum(x['qa_status'] not in {'SOURCE_VERIFIED','STABLE_CLASSIFICATION_SUPPORTED'} for x in rows),'terminal_sector_labeled':sum(x['terminal'] and x['canonical_sector']!='UNKNOWN' for x in rows),'terminal_verified_or_stable':sum(x['terminal'] and x['qa_status'] in {'SOURCE_VERIFIED','STABLE_CLASSIFICATION_SUPPORTED'} for x in rows),'by_panel_year':yearly,'terminal_events_by_year':dict(sorted(terminal_year.items())),'warning':'Label coverage is not QA-verified coverage.'}
 dump(OUT/'qa/coverage.json',cov)
 dump(OUT/'qa/k1_usability.json',{'sector_momentum':'DATA REDO MED BEGRÄNSNING','sector_relative_momentum':'DATA REDO MED BEGRÄNSNING','sector_breadth':'DATA REDO MED BEGRÄNSNING','industry_relative_momentum':'DELVIS TESTBAR','sector_diversification_tie_break':'DATA REDO MED BEGRÄNSNING','mandatory_sensitivity':'Report all results both including all labels and excluding MANUAL_EXPERT_CLASSIFICATION; no hidden terminal exclusion.'})
 dump(OUT/'preregistration_pending/sector_diversification_hypothesis.json',{'status':'DOCUMENTED_NOT_TESTED','hypothesis':'H0 retains alpha ranking; among practically equivalent H0 scores prefer candidate increasing sector diversification.','outcomes':['sector concentration','effective number of sectors','drawdown','common factor exposure','CAGR/IC non-inferiority'],'forbidden_now':['tie threshold','sector penalty','target','IC','backtest']})
 # Manifest all artifacts plus immutable input hashes; write last.
 inputs=[AV,TE,PX,ROOT/'panels/core_panel.json',ROOT/'trackj/validated_mfn_events_v1/validated_mfn_events.jsonl']
 arts=sorted(p for p in OUT.rglob('*') if p.is_file() and p.name not in {'manifest.json','manifest.sha256'})
 arts += [ROOT/'docs/K1_TERMINAL_SECTOR_QA_FREEZE.md',ROOT/'tools/spark_freeze_sector_classification.py',ROOT/'tools/verify_spark_sector_freeze.py']
 manifest={'version_id':'K1_SECTOR_CLASSIFICATION_V1_IMMUTABLE_2026-08-09','created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'classification/provenance only; no target, IC, alpha or backtest','inputs':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size} for p in inputs],'artifacts':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size} for p in arts]}
 dump(OUT/'manifest.json',manifest); (OUT/'manifest.sha256').write_text(sha(OUT/'manifest.json')+'  manifest.json\n')
 print(json.dumps({'manifest_sha256':sha(OUT/'manifest.json'),'coverage':cov},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
