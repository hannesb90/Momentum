"""Bygger canonical artefakter ur de RAW-manader som finns pa disk.
Ren databehandling. Inga tester, ingen payoff, ingen modell."""
from __future__ import annotations
import hashlib, json, pathlib, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from parse_monthly import parse, sto_stock, _las_xls, _las_xlsx, detektera_epok

V2 = pathlib.Path("/home/hannesb/momentum_v2")
D = V2 / "research_k/nasdaq_segment_foundation"
NOW = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
sha = lambda p: hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
PARSER = {m: sha(V2 / f"tools/nasdaq_segment/{m}") for m in ("ole2.py", "biff8.py", "parse_monthly.py")}

filer = sorted(V2.glob("raw/nasdaq_segment/monthly/*/[0-9]*.xls*"))
print(f"RAW-manader pa disk: {len(filer)}")

raw_manifest, schema, snapshots = [], [], []
for f in filer:
    r = parse(f)
    man = r["snapshot_month"] or f.stem
    ark = _las_xlsx(f) if f.suffix == ".xlsx" else _las_xls(f)
    rader = ark["Instrument Trading Details"]
    epok, h = detektera_epok(rader)
    hdr = {str(x).replace("\n", " ").strip(): i for i, x in enumerate(rader[h]) if str(x).strip()}
    s = sto_stock(r["rows"])
    raw_manifest.append({"report_month": man, "file": str(f.relative_to(V2)),
                         "file_type": f.suffix.lstrip("."), "byte_size": f.stat().st_size,
                         "sha256": sha(f), "retrieved_at": NOW,
                         "source": "api.news.eu.nasdaq.com -> attachment.news.eu.nasdaq.com"})
    schema.append({"report_month": man, "sheet_name": "Instrument Trading Details",
                   "header_row": h, "file_format": f.suffix.lstrip("."),
                   "parser_success": True, "raw_rows": r["n_rows"],
                   "sto_stock_cap_rows": len(s),
                   "kolumnpositioner": {k: hdr.get(k) for k in
                       ("ISIN", "Instrument  Type", "Segment", "Curr- ency",
                        "Loca- tion", "Issuer Country", "Delisted")},
                   "kolumnnamn": sorted(hdr)})
    for x in s:
        snapshots.append({"report_month": man, **{k: x[k] for k in
            ("instrument", "company_code", "orderbook_code", "isin", "instrument_type",
             "segment", "location", "delisted")},
            "raw_sha256": r["sha256"], "parser_sha256": PARSER["parse_monthly.py"]})

# ---- schema-drift
alla_kol = {}
for s in schema:
    for k, v in s["kolumnpositioner"].items():
        alla_kol.setdefault(k, {})[s["report_month"]] = v
drift = {k: v for k, v in alla_kol.items() if len(set(v.values())) > 1}
namndrift = {}
for s in schema:
    for k in s["kolumnnamn"]:
        namndrift.setdefault(k, set()).add(s["report_month"])
unika_per_manad = {s["report_month"]: set(s["kolumnnamn"]) for s in schema}
tillagda, borttagna = {}, {}
mm = sorted(unika_per_manad)
for a, b in zip(mm, mm[1:]):
    tillagda[f"{a}->{b}"] = sorted(unika_per_manad[b] - unika_per_manad[a])
    borttagna[f"{a}->{b}"] = sorted(unika_per_manad[a] - unika_per_manad[b])

json.dump({"schema": "NASDAQ_RAW_MANIFEST_V1", "created_utc": NOW,
           "parser_sha256": PARSER, "n_manader": len(raw_manifest),
           "filer": raw_manifest}, open(D / "raw_manifest.json", "w"),
          ensure_ascii=False, indent=1)
json.dump({"schema": "NASDAQ_SCHEMA_AUDIT_V1", "created_utc": NOW,
  "manader": schema, "positionsdrift": drift,
  "kolumner_tillagda": {k: v for k, v in tillagda.items() if v},
  "kolumner_borttagna": {k: v for k, v in borttagna.items() if v},
  "KRITISKT": "Kolumnen 'Issuer Country' infogas pa position 15 i den moderna epoken och "
    "knuffar 'Delisted' fran 15 till 16. En POSITIONSBASERAD parser hade last landskod som "
    "avnoteringsdatum. Namnbaserad mappning kravs.",
  "segmentvarden": sorted({x["segment"] for x in snapshots}),
  "locationvarden_i_urval": ["STO"],
  "instrumenttypvarden": sorted({x["instrument_type"] for x in snapshots if x["instrument_type"]})},
  open(D / "schema_audit.json", "w"), ensure_ascii=False, indent=1)
json.dump({"schema": "MONTHLY_SIZE_SNAPSHOTS_V1", "created_utc": NOW,
  "filter": "location=STO AND instrument_type=Stock AND segment in {Large,Mid,Small} Cap",
  "n_rader": len(snapshots), "manader": sorted({x["report_month"] for x in snapshots}),
  "rader": snapshots}, open(D / "monthly_size_snapshots.json", "w"),
  ensure_ascii=False, indent=1)

print(f"  raw_manifest: {len(raw_manifest)} filer")
print(f"  schema_audit: positionsdrift = {drift}")
for k, v in tillagda.items():
    if v: print(f"    tillagda {k}: {v}")
print(f"  monthly_size_snapshots: {len(snapshots)} instrumentrader")
for s in schema:
    print(f"    {s['report_month']}  headerrad {s['header_row']}  {s['file_format']:4s}  "
          f"STO-cap {s['sto_stock_cap_rows']}")
