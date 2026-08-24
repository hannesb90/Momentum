"""VALIDATED-lager for priser + frysning av spar A.

Implementerar EXAKT de beslutade reglerna i docs/PRIS_QA_KLASSIFICERING.md §3:
  R1  endast adjusted_close anvands for avkastning; close bevaras men flaggas
  R2  serier trunkeras vid avnoteringsdagen (instrumentateranvandning)
  R3  ogiltiga varden UTESLUTS, aldrig interpoleras (golv 0.0001, platshallare 1e6)
  R4  justeringsproblem: +/-10 handelsdagar kring brottet utesluts
  R5  annan verifierad orsak: handelseveckan utesluts, dokumenterad per fall
  R6  ingen clipping, ingen winsorisering, ingen imputering

Legacy lases READ-ONLY. Utdata + manifest skrivs under momentum_v2/validated/.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

LEG = Path("/home/hannesb/momentum_prod_work/momentum_ml/cache")
EOD = LEG / "eodhd_archive/ST"
V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "validated/prices"
MANIFEST = V2 / "validated/manifest_sparA.json"

START = "2020-01-01"
FLOOR, PLACEHOLDER = 0.0001, 1000000.0

# Beslutade specialfall (docs/PRIS_QA_KLASSIFICERING.md §2)
SPECIAL = {
    "MQ":     {"regel": "R4", "datum": "2020-02-13", "fonster_dagar": 14,
               "orsak": "split-/justeringsproblem, adjusted_close bryter"},
    "ORRON":  {"regel": "R5", "datum": "2022-06-23", "fonster_dagar": 7,
               "orsak": "Aker BP-utskiftning fångas inte av adjusted_close"},
}


def las_gz(p: Path):
    if not p.exists():
        return []
    try:
        with gzip.open(p, "rt", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return []


def d(s: str) -> date:
    return date(int(s[:4]), int(s[5:7]), int(s[8:10]))


def main() -> None:  # noqa: C901
    # Refuse anonymous/mutable cache drift before reading a single source row.
    from build_external_dependencies_manifest import verify_external_source
    verify_external_source()
    OUT.mkdir(parents=True, exist_ok=True)
    master = json.loads((V2 / "docs/probes/instrument_master.json").read_text(encoding="utf-8"))
    inst = json.loads((V2 / "docs/probes/instruments_live.json").read_text(encoding="utf-8"))
    brott = json.loads((V2 / "docs/probes/price_qa_slutlig.json").read_text(encoding="utf-8"))["brott"]

    # ---------- universum ------------------------------------------
    ns_isin = {(i.get("isin") or "").upper() for i in inst if i.get("marketId") in (1, 2, 3)}
    kandidater_per_kod = {}
    for r in master:
        e = r.get("eodhd") or {}
        kod = e.get("code")
        if not kod:
            continue
        t = (r.get("avnoterad_orsak") or "").lower()
        ar = r.get("avnoterad_ar") or 0
        i_ns = (e.get("isin") or "").upper() in ns_isin
        avn_ns = ar >= 2020 and any(k in t for k in ("nasdaq stockholm", "nordiska listan"))
        if i_ns or avn_ns:
            kandidater_per_kod.setdefault(kod, []).append(r)

    # Flera historiksidor kan vara alias för samma EODHD-kod. Validera och
    # konsolidera gruppen explicit; iterationsordning/"last one wins" är förbjuden.
    kod2post, avnoterad, entity_resolution = {}, {}, {}
    for kod, kandidater in sorted(kandidater_per_kod.items()):
        isin = sorted({((r.get("eodhd") or {}).get("isin") or "").upper()
                       for r in kandidater if (r.get("eodhd") or {}).get("isin")})
        grupper = {(r.get("eodhd") or {}).get("grupp") for r in kandidater}
        datum = sorted({r["avnoterad_datum"][:10] for r in kandidater
                        if r.get("avnoterad_datum")})
        if len(isin) > 1 or len(grupper) > 1 or len(datum) > 1:
            raise RuntimeError(f"{kod}: olöst entity-konflikt isin={isin}, grupp={grupper}, datum={datum}")
        # Kanoniskt visningsnamn väljs mot leverantörens eget namn. Ekonomiska
        # attribut (ISIN, status, terminaldatum) är gruppvaliderade ovan.
        import difflib
        kanon = max(kandidater, key=lambda r: (
            difflib.SequenceMatcher(None, (r.get("namn") or "").lower(),
                                     ((r.get("eodhd") or {}).get("namn") or "").lower()).ratio(),
            r.get("slug") or ""))
        kod2post[kod] = kanon
        if datum:
            avnoterad[kod] = datum[0]
        entity_resolution[kod] = {
            "n_masterposter": len(kandidater), "isin": isin[0] if isin else None,
            "kanonisk_slug": kanon.get("slug"),
            "aliaser": [{"slug": r.get("slug"), "namn": r.get("namn"),
                         "forsta_notering": r.get("forsta_notering"),
                         "avnoterad_datum": r.get("avnoterad_datum")}
                        for r in kandidater]}
    print(f"universum: {len(kod2post)} instrument (Nasdaq Stockholm, inkl. avnoterade 2020+)")

    # ---------- härled regler ur klassificeringen -------------------
    # SPANN, inte punkter: punktvis radering skapar nya brott i pendlande serier.
    ATERANV = "instrumentåteranvändning"
    PROBLEM = {"leverantörs-/datafel", "split-/justeringsproblem",
               "annan verifierad orsak", "OKLASSIFICERAD"}
    trunk_vid, problemspann = {}, {}
    for b in brott:
        if b["code"] not in kod2post or b["datum_efter"] < START:
            continue
        if b["klass"] == ATERANV:
            # trunkera vid BROTTET, inte vid det formella avnoteringsdatumet:
            # handeln i det ursprungliga instrumentet upphör före avregistreringen
            f = trunk_vid.get(b["code"])
            trunk_vid[b["code"]] = min(f, b["datum_fore"]) if f else b["datum_fore"]
        elif b["klass"] in PROBLEM:
            lo, hi = problemspann.get(b["code"], (b["datum_fore"], b["datum_efter"]))
            problemspann[b["code"]] = (min(lo, b["datum_fore"]), max(hi, b["datum_efter"]))
    MARGINAL = 5      # kalenderdagar på vardera sidan om spannet
    for k, (lo, hi) in list(problemspann.items()):
        problemspann[k] = ((d(lo) - timedelta(days=MARGINAL)).isoformat(),
                           (d(hi) + timedelta(days=MARGINAL)).isoformat())

    kat = {}
    for g in ("active", "delisted"):
        for x in json.loads((EOD / f"{g}_catalogue.json").read_text(encoding="utf-8")):
            kat[x["Code"]] = g

    stat = Counter()
    serier, kallhashar = {}, {}
    for kod in sorted(kod2post):
        g = kat.get(kod)
        if not g:
            stat["utan_eodhd_serie"] += 1
            continue
        p = EOD / g / "eod" / f"{kod}.json.gz"
        rå = las_gz(p)
        if not rå:
            stat["tom_serie"] += 1
            continue
        kallhashar[kod] = hashlib.sha256(p.read_bytes()).hexdigest()
        # R2: trunkera vid avnotering ELLER vid instrumentåteranvändningsbrottet,
        #     det som infaller först
        gransar = [x for x in (avnoterad.get(kod), trunk_vid.get(kod)) if x]
        trunk = min(gransar) if gransar else None
        spann = problemspann.get(kod)
        rader = []
        for x in rå:
            dt = x.get("date")
            if not dt or dt < START:
                continue
            if trunk and dt > trunk:
                stat["R2_efter_avnotering_eller_aterانv" if False
                     else "R2_efter_trunkering"] += 1
                continue
            ac, cl = x.get("adjusted_close"), x.get("close")
            if ac is None or ac <= 0:
                stat["R3_saknad_adjclose"] += 1
                continue
            if abs(ac - FLOOR) < 1e-9 or (cl is not None and abs(cl - PLACEHOLDER) < 1e-6):
                stat["R3_golv_platshallare"] += 1
                continue
            if spann and spann[0] <= dt <= spann[1]:
                stat["R3R4R5_problemspann"] += 1
                continue
            # A-2 (CODEX_SECOND_OPINION_V2_ABC.md): "or 0" riskerade att kollapsa
            # saknad volym och genuin nollhandel till samma varde. Verifierat
            # empiriskt over HELA instrument_master-korpusen (3 322 934 rader,
            # samtliga instrument, bade aktiva och avnoterade): "volume" saknas
            # ALDRIG i EODHD-arkivet - alltid ett tal, ibland genuint 0 (134 225
            # rader, ~4%). "or 0" ar darfor ett no-op mot aktuell data (andrar
            # inget faktiskt varde), men tas bort for tydlighet och for att inte
            # tyst maskera ett framtida datakallsbyte dar volume KAN saknas.
            if cl is None or cl <= 0:
                stat["R3_saknad_close"] += 1
                continue
            rader.append({"d": dt, "adj": ac, "close": cl, "v": x.get("volume")})
        if len(rader) < 5:
            stat["for_kort_efter_regler"] += 1
            continue
        serier[kod] = rader
        stat["instrument_i_validated"] += 1

    # ---------- R7: slutning mot acceptanskriteriet -----------------
    # Regeln är sluten: kvarstående brott utvidgar det uteslutna spannet tills
    # kriteriet "noll nivåbrott" är uppfyllt. Inget värde skrivs om — spannet
    # utesluts, och exakt vilka spann som uteslöts registreras i manifestet.
    def brott_i(r):
        return [(i, r[i]["d"]) for i in range(1, len(r))
                if not (0.05 <= r[i]["adj"] / r[i - 1]["adj"] <= 20)]

    # R8: konvergerar inte fönsterbehandlingen inom MAX_VARV är serien inte
    # reparerbar på fönsternivå -> HELA instrumentet utesluts och registreras.
    MAX_VARV = 3
    utvidgade, uteslutna_instrument = {}, {}
    for varv in range(MAX_VARV + 1):
        kvarstar = {kod: brott_i(r) for kod, r in serier.items() if brott_i(r)}
        if not kvarstar:
            break
        if varv == MAX_VARV:
            # R8: serien DELAS vid de olösta brotten och det längsta sammanhängande
            # segmentet behålls. Att kasta hela instrumentet vore att kasta äkta
            # observationer (t.ex. MQ:s konkurs 2020) — segmentering bevarar dem.
            MIN_SEG = 60
            for kod, bl in kvarstar.items():
                idx = [b[0] for b in bl]
                gr = [0] + idx + [len(serier[kod])]
                segment = [serier[kod][gr[i]:gr[i + 1]] for i in range(len(gr) - 1)]
                basta = max(segment, key=len)
                uteslutna_instrument[kod] = {
                    "regel": "R8 segmentering",
                    "orsak": "olöst nivåbrott — serien delad, längsta segmentet behållet",
                    "brottdatum": [b[1] for b in bl][:10],
                    "n_rader_fore": len(serier[kod]), "n_rader_efter": len(basta),
                    "behallet_spann": [basta[0]["d"], basta[-1]["d"]] if basta else None,
                    "instrumentet_uteslutet": len(basta) < MIN_SEG}
                if len(basta) >= MIN_SEG:
                    serier[kod] = basta
                else:
                    del serier[kod]
            break
        for kod, bl in kvarstar.items():
            lo = min(b[1] for b in bl)
            hi = max(b[1] for b in bl)
            lo2 = (d(lo) - timedelta(days=7 * (varv + 1))).isoformat()
            hi2 = (d(hi) + timedelta(days=7 * (varv + 1))).isoformat()
            fore = len(serier[kod])
            serier[kod] = [x for x in serier[kod] if not (lo2 <= x["d"] <= hi2)]
            u = utvidgade.setdefault(kod, {"spann": [], "borttagna_rader": 0, "varv": 0})
            u["spann"] = [lo2, hi2]
            u["borttagna_rader"] += fore - len(serier[kod])
            u["varv"] = varv + 1
    serier = {k: v for k, v in serier.items() if len(v) >= 5}
    kvar = [(kod, r[i]["d"], round(r[i - 1]["adj"], 4), round(r[i]["adj"], 4),
             round(r[i]["adj"] / r[i - 1]["adj"], 5))
            for kod, r in serier.items() for i in range(1, len(r))
            if not (0.05 <= r[i]["adj"] / r[i - 1]["adj"] <= 20)]
    print(f"\nR7-slutning: {len(utvidgade)} instrument fick utvidgat uteslutet spann")
    for kod, u in sorted(utvidgade.items()):
        print(f"   {kod:10s} {u['spann'][0]} – {u['spann'][1]}  "
              f"({u['borttagna_rader']} rader, {u['varv']} varv)")
    print("\nREGELUTFALL")
    for k, v in sorted(stat.items()):
        print(f"  {k:34s} {v:>8d}")
    print(f"\nKONTROLL: nivåbrott kvar i VALIDATED: {len(kvar)}")
    for x in kvar:
        print(f"   {x[1]} {x[0]:10s} {x[2]} → {x[3]} ({x[4]}x)")

    # ---------- skriv + frys ---------------------------------------
    kanon = json.dumps({k: serier[k] for k in sorted(serier)}, sort_keys=True,
                       separators=(",", ":"), ensure_ascii=False)
    dataset_hash = hashlib.sha256(kanon.encode("utf-8")).hexdigest()
    (OUT / "prices_validated.json").write_text(kanon, encoding="utf-8")

    n_rader = sum(len(v) for v in serier.values())
    dat = sorted({r["d"] for v in serier.values() for r in v})
    man = {
        "dataset": "dataset_v1.0 / spår A — svenska aktier i rekonstruerat Nasdaq Stockholm-universum med observerbar handel; efterföljande PIT-filter där membership är känd",
        "version": "1.0.0-rc1",
        "fryst_utc": "2026-08-08T00:00:00+00:00",
        "timestamp_policy": "deterministic dataset_v1.0 release timestamp; rebuild wall-clock time is not serialized",
        "dataset_sha256": dataset_hash,
        "universum": {"marknadsplats": "Nasdaq Stockholm (OMX Large/Mid/Small Cap)",
                      "startdatum": START,
                      "n_instrument_definierade": len(kod2post),
                      "n_instrument_i_validated": len(serier)},
        "innehall": {"n_rader": n_rader, "forsta_datum": dat[0] if dat else None,
                     "sista_datum": dat[-1] if dat else None,
                     "falt": ["d (datum)", "adj (adjusted_close; totalavkastning)",
                              "close (ojusterad stängningskurs; pris×volym)", "v (volym)"]},
        "regler": {
            "R1": "adjusted_close används för avkastning; ojusterad close endast för pris×volym",
            "R2": "serier trunkeras vid avnoteringsdagen ur instrument_master",
            "R3": "ogiltiga värden utesluts (golv 0.0001, platshållare 1e6, klassade leverantörsfel)",
            "R4": "justeringsproblem: hela det klassade problemspannet ±5 dagar utesluts",
            "R5": "annan verifierad orsak: samma spannregel (ORRON 2022-06-23, Aker BP)",
            "R6": "ingen clipping, winsorisering eller imputering",
            "R7": "slutningsregel: kvarstående nivåbrott utvidgar spannet iterativt tills noll brott återstår; inget värde skrivs om",
            "R8": "konvergerar inte fönsterbehandlingen inom 3 varv DELAS serien vid brottet och längsta segmentet behålls; instrumentet utesluts bara om segmentet <60 rader"},
        "specialfall": SPECIAL,
        "R7_utvidgade_spann": utvidgade,
        "R8_segmenterade_instrument": uteslutna_instrument,
        "entity_resolution": entity_resolution,
        "regelutfall": dict(stat),
        "kvarvarande_nivabrott": kvar,
        "kallor": {
            "eodhd_arkiv": str(EOD),
            "n_kallfiler_hashade": len(kallhashar),
            "kallfil_sha256": kallhashar,
            "instrument_master": hashlib.sha256(
                (V2 / "docs/probes/instrument_master.json").read_bytes()).hexdigest(),
            "price_qa_slutlig": hashlib.sha256(
                (V2 / "docs/probes/price_qa_slutlig.json").read_bytes()).hexdigest()},
        "beroende_dokument": ["docs/PRIS_QA_KLASSIFICERING.md", "docs/UNIVERSUM_V1_LASNING.md"],
        "status": "SPÅR A FRYST; historisk membership-osäkerhet är kvantifierad datasetbegränsning, inte verifierad PIT-membership",
    }
    MANIFEST.write_text(json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\ninstrument {len(serier)} | rader {n_rader:,} | {dat[0]} – {dat[-1]}")
    print(f"dataset_sha256 {dataset_hash}")
    print(f"artefakter: {OUT/'prices_validated.json'}\n            {MANIFEST}")


if __name__ == "__main__":
    main()
