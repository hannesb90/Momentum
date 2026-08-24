"""H1419 VOLUME V1 — kompletterar H1419 med volym och ra close ur EODHD-arkivet.

H1419-lagret har bara falten ['adj','d']. prima_storbolag berakar ADV = median av
close x volume over 20 foregaende rader, vilket darfor inte gar att reproducera ur
gatad data for 2014-2019.

Detta skript hamtar volym och ra close fran EXAKT samma rakalla som H1419 byggdes ur,
for EXAKT samma instrument x datum. Inga nya observationer, ingen forward fill, ingen
interpolation, ingen modern backfill.

Las:   validated/prices_h1419/prices_h1419_universum_v2.json  (RORS EJ)
       momentum_prod_work/momentum_ml/cache/eodhd_archive/ST   (READ-ONLY)
Skriv: validated/h1419_volume_v1/
"""
from __future__ import annotations
import gzip, hashlib, json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
EOD = Path("/home/hannesb/momentum_prod_work/momentum_ml/cache/eodhd_archive/ST")
SRC = V2 / "validated/prices_h1419/prices_h1419_universum_v2.json"
OUT = V2 / "validated/h1419_volume_v1"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    kat = {}
    for g in ("active", "delisted"):
        for x in json.loads((EOD / f"{g}_catalogue.json").read_text()):
            kat.setdefault(x["Code"], g)
    H = json.loads(SRC.read_text())
    vol, st = {}, Counter()
    rapport = []
    for kod, rader in sorted(H.items()):
        p = EOD / kat.get(kod, "active") / "eod" / f"{kod}.json.gz"
        if not p.exists():
            st["instrument_utan_arkiv"] += 1
            rapport.append({"kod": kod, "status": "ARKIV_SAKNAS", "h1419_rader": len(rader)})
            continue
        with gzip.open(p, "rt", encoding="utf-8") as f:
            raw = json.load(f)
        idx = {r["date"]: r for r in raw}
        dubbletter = len(raw) - len(idx)
        ut, saknade = [], 0
        for r in rader:
            a = idx.get(r["d"])
            if a is None:
                saknade += 1
                continue                      # ingen fill — raden utelamnas
            c, v = a.get("close"), a.get("volume")
            if c is None or v is None:
                saknade += 1
                continue
            ut.append({"d": r["d"], "close": c, "v": v})
        if ut:
            vol[kod] = ut
        st["instrument"] += 1
        st["rader_forvantade"] += len(rader)
        st["rader_matchade"] += len(ut)
        st["rader_saknade_i_arkivet"] += saknade
        st["dubbla_datum_i_arkivet"] += dubbletter
        rapport.append({"kod": kod, "status": "OK", "h1419_rader": len(rader),
                        "matchade": len(ut), "saknade": saknade,
                        "arkiv_dubbletter": dubbletter,
                        "spann": [ut[0]["d"], ut[-1]["d"]] if ut else None})
    dst = OUT / "h1419_volume.json"
    dst.write_text(json.dumps(vol, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    man = {"version": "H1419_VOLUME_V1",
           "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
           "source_h1419": str(SRC.relative_to(V2)), "source_h1419_sha256": sha(SRC),
           "source_raw_archive": str(EOD),
           "output": str(dst.relative_to(V2)), "output_sha256": sha(dst),
           "regler": ["samma instrumentidentitet (orderbook_code) som H1419",
                      "samma datum — endast (instrument, datum) som redan finns i H1419",
                      "samma handelskalender — inga nya handelsdagar tillfors",
                      "volymdefinition = EODHD 'volume', ra close = EODHD 'close' (identisk med "
                      "legacy prima_storbolag adv())",
                      "INGEN forward fill", "INGEN interpolation", "INGEN modern backfill",
                      "inga observationer utanfor ursprungligt H1419-universum"],
           "utfall": dict(st), "per_instrument": rapport}
    (OUT / "H1419_VOLUME_MANIFEST.json").write_text(json.dumps(man, ensure_ascii=False, indent=1))
    print(f"instrument {st['instrument']}  forvantade {st['rader_forvantade']:,}  "
          f"matchade {st['rader_matchade']:,}  saknade {st['rader_saknade_i_arkivet']:,}")
    print(f"dubbla datum i arkivet: {st['dubbla_datum_i_arkivet']}  "
          f"instrument utan arkiv: {st['instrument_utan_arkiv']}")
    print(f"sha256 {man['output_sha256']}")


if __name__ == "__main__":
    main()
