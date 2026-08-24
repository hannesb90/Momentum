"""Hashverifiering och fullstandighetskontroll av legacyns radatalager.

Kategori 1-kalla: /home/hannesb/momentum_prod_work/momentum_ml/cache/researchdb_v1/raw/

Fristaende: ingen legacy-import, legacy lases READ-ONLY. Skriver bara under momentum_v2/.

Verifierar:
  1. Kan manifestets sha256 aterskapas ur den sparade filen? (rawstore hashade
     r.text men sparade json.dumps(payload) - provar flera serialiseringar)
  2. Sjalvkonsistens: meta.sha256 i filen == manifestets sha256
  3. n_rows i manifestet == faktiskt antal rader i payload
  4. Fullstandighet: filer utan manifestrad, manifestrader utan fil, HTTP-status,
     endpointtackning och instrumenttackning mot instrumentlistan
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

RAW = Path("/home/hannesb/momentum_prod_work/momentum_ml/cache/researchdb_v1/raw")
MANIFEST = RAW / "_manifest.jsonl"
V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "docs/probes/rawstore_verification.json"

SERIALISERINGAR = {
    "dumps(ensure_ascii=False)": lambda p: json.dumps(p, ensure_ascii=False),
    "dumps(default)": lambda p: json.dumps(p),
    "kompakt(',',':')": lambda p: json.dumps(p, separators=(",", ":")),
    "kompakt+ensure_ascii=False": lambda p: json.dumps(p, separators=(",", ":"),
                                                       ensure_ascii=False),
}


def main() -> None:
    rader = [json.loads(l) for l in MANIFEST.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"manifest: {len(rader)} rader")
    st = Counter(str(r.get("http_status")) for r in rader)
    print(f"  http_status: {dict(st)}")
    ej_ok = [r for r in rader if not r.get("ok")]
    print(f"  ok=False: {len(ej_ok)}")
    med_fil = [r for r in rader if r.get("ok") and r.get("file")]
    print(f"  rader med fil: {len(med_fil)}")

    rep: dict = {"manifest_rader": len(rader), "http_status": dict(st),
                 "ok_false": len(ej_ok), "rader_med_fil": len(med_fil),
                 "legacy_lases_readonly": True}

    # ---------- 1. hashåterspelning på ett stickprov ----------------
    print("\n" + "=" * 88)
    print("1. HASHÅTERSPELNING — kan manifestets sha256 återskapas ur filen?")
    print("=" * 88)
    prov = med_fil[:: max(1, len(med_fil) // 60)][:60]
    traff = Counter()
    for r in prov:
        p = RAW / r["file"]
        if not p.exists():
            traff["FIL SAKNAS"] += 1
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        pl = d.get("payload")
        matchade = False
        for namn, fn in SERIALISERINGAR.items():
            if hashlib.sha256(fn(pl).encode("utf-8")).hexdigest() == r.get("sha256"):
                traff[namn] += 1
                matchade = True
                break
        if not matchade:
            traff["INGEN SERIALISERING MATCHAR"] += 1
    print(f"  stickprov {len(prov)} filer:")
    for k, v in traff.most_common():
        print(f"    {k:34s} {v:>4d}")
    rep["hash_aterspelning"] = {"stickprov": len(prov), "utfall": dict(traff)}
    aterspelbar = traff.get("INGEN SERIALISERING MATCHAR", 0) == 0 and len(prov) > 0

    # ---------- 2-3. självkonsistens och radantal -------------------
    print("\n" + "=" * 88)
    print("2-3. SJÄLVKONSISTENS (meta.sha256 mot manifest) OCH RADANTAL")
    print("=" * 88)
    saknade_filer, sha_avvik, rad_avvik, trasiga = [], [], [], []
    for r in med_fil:
        p = RAW / r["file"]
        if not p.exists():
            saknade_filer.append(r["file"])
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            trasiga.append(r["file"])
            continue
        meta = d.get("meta") or {}
        if meta.get("sha256") != r.get("sha256"):
            sha_avvik.append(r["file"])
        pl = d.get("payload")
        n = (len(pl) if isinstance(pl, list)
             else sum(len(v) for v in pl.values() if isinstance(v, list))
             if isinstance(pl, dict) else 0)
        if n != r.get("n_rows"):
            rad_avvik.append((r["file"], r.get("n_rows"), n))
    print(f"  filer som saknas på disk:      {len(saknade_filer)}")
    print(f"  filer som inte går att läsa:   {len(trasiga)}")
    print(f"  meta.sha256 ≠ manifest.sha256: {len(sha_avvik)}")
    print(f"  n_rows ≠ faktiskt radantal:    {len(rad_avvik)}")
    for f, a, b in rad_avvik[:5]:
        print(f"      {f}: manifest {a}, faktiskt {b}")
    rep["sjalvkonsistens"] = {"saknade_filer": len(saknade_filer), "trasiga": len(trasiga),
                              "sha_avvikelser": len(sha_avvik), "radantal_avvikelser": len(rad_avvik),
                              "exempel_radantal": rad_avvik[:10]}

    # ---------- 4. fullständighet -----------------------------------
    print("\n" + "=" * 88)
    print("4. FULLSTÄNDIGHET")
    print("=" * 88)
    pa_disk = {str(p.relative_to(RAW)) for p in RAW.rglob("*.json") if p.name != "_manifest.jsonl"}
    i_manifest = {r["file"] for r in med_fil}
    print(f"  json-filer på disk: {len(pa_disk)} | i manifestet: {len(i_manifest)}")
    print(f"  på disk men EJ i manifestet: {len(pa_disk - i_manifest)}")
    print(f"  i manifestet men EJ på disk: {len(i_manifest - pa_disk)}")
    rep["fullstandighet"] = {"filer_pa_disk": len(pa_disk), "filer_i_manifest": len(i_manifest),
                             "oregistrerade": len(pa_disk - i_manifest),
                             "saknade": len(i_manifest - pa_disk)}

    ep = Counter(r.get("endpoint", "?") for r in rader)
    generiska = {k: v for k, v in ep.items() if not k.startswith("/instruments/")}
    print(f"  distinkta endpoints i manifestet: {len(ep)}")
    print("  icke-instrumentspecifika: " + ", ".join(f"{k}({v})" for k, v in
                                                     sorted(generiska.items())))

    inst_filer = list((RAW / "instruments").glob("*.json"))
    n_lista = 0
    if inst_filer:
        d = json.loads(inst_filer[0].read_text(encoding="utf-8"))
        pl = d.get("payload", d)
        n_lista = len(pl.get("instruments") or [])
    med_rapport = {r.get("instrument") for r in rader
                   if "reports" in str(r.get("endpoint", "")) and r.get("ok")}
    med_rapport.discard(None)
    med_rapport.discard("None")
    print(f"  instrument i listan: {n_lista} | instrument med rapporthämtning: {len(med_rapport)}")
    print(f"  TÄCKNINGSGAP: {n_lista - len(med_rapport)} instrument saknar rapporter "
          f"({100*(n_lista-len(med_rapport))/max(n_lista,1):.1f} %)")
    rep["fullstandighet"].update({
        "endpoints": len(ep), "instrument_i_listan": n_lista,
        "instrument_med_rapporter": len(med_rapport),
        "tackningsgap": n_lista - len(med_rapport)})

    # ---------- dom ---------------------------------------------------
    print("\n" + "=" * 88)
    print("DOM")
    print("=" * 88)
    if aterspelbar:
        print("  Hashen ÄR återspelbar ur den sparade filen → källan kan hashverifieras.")
    else:
        print("  Hashen är INTE återspelbar: rawstore hashade leverantörens råa svarskropp")
        print("  (r.text) men sparade en omserialiserad json.dumps(payload). Rå-bytesen")
        print("  finns inte kvar. Manifestets sha256 kan därför inte bekräftas mot filen —")
        print("  bara filens egen meta.sha256 kan jämföras med manifestraden (självkonsistens).")
        print("  → Kravet 'RAW sparas oförändrad' är INTE uppfyllt i legacyns lager.")
    rep["dom"] = {"hash_aterspelbar": bool(aterspelbar)}

    OUT.write_text(json.dumps(rep, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nartefakt: {OUT}")


if __name__ == "__main__":
    main()
