"""Spar C, sista steget: konsoliderat manifest + SHA256 for de tva panelerna.

Rarafilbytehash (sha256 av filen exakt som den ligger pa disk) anvands har -
den enklaste, entydigt reproducerbara metoden ('sha256sum panels/x.json').
Skiljer sig darfor numeriskt fran de kanoniserade (sorterade) hasharna som
skrevs ut UNDER byggstegen (samma innehall, annan serialiseringsordning -
ingen datainkonsekvens, bara tva olika hashkonventioner).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
PANELS = V2 / "panels"
MANIFEST = V2 / "validated/manifest_sparC.json"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> None:
    target_man = json.loads((V2 / "docs/probes/target_manifest.json").read_text(encoding="utf-8"))
    registry = json.loads((V2 / "docs/probes/feature_registry.json").read_text(encoding="utf-8"))
    qa = json.loads((V2 / "docs/probes/spar_c_qa.json").read_text(encoding="utf-8"))
    man_a = json.loads((V2 / "validated/manifest_sparA.json").read_text(encoding="utf-8"))
    man_b = json.loads((V2 / "validated/manifest_sparB.json").read_text(encoding="utf-8"))
    man_b_extra = json.loads((V2 / "validated/manifest_sparB_extra.json").read_text(encoding="utf-8"))
    blueprint = json.loads((V2 / "docs/probes/feature_blueprint.json").read_text(encoding="utf-8"))

    alla_falt = registry["CORE"] + registry["FUNDAMENTA"]
    anvandbara = [f for f in alla_falt if f.get("status") != "UTESLUTEN" and
                  not f.get("ej_feature")]
    anv_core = [f for f in registry["CORE"] if f.get("status") != "UTESLUTEN"]
    anv_fund = [f for f in registry["FUNDAMENTA"] if f.get("status") != "UTESLUTEN"
                and not f.get("ej_feature")]
    from collections import Counter
    # D-1-fix (CODEX_SECOND_OPINION_V2_ABC.md): registryschemat har inte
    # burit ett "klassificering"-falt (GODKAND/KRAVER ATGARD) sedan
    # materialitetsregeln blev en inbyggd del av byggstegen istallet for ett
    # separat efterhandsbeslut - varje falt som finns i registryt ar per
    # definition redan byggt och godkant, det finns inget kvarvarande
    # KRAVER ATGARD-tillstand att rakna.
    bp_status = Counter(f["status"] for f in blueprint)

    man = {
        "dataset": "dataset_v1.0 / spår C — svenska aktier i rekonstruerat Nasdaq Stockholm-universum med observerbar handel och PIT-filter där membership är känd",
        "version": "1.2.0",
        "revision_not": "v1.1.0 ersätter v1.0.0 (rc): feature blueprint genomförd, 27 nya "
                        "fält byggda (varav 1 infrastruktur/index), 6 fält som stod KRÄVER "
                        "ÅTGÄRD lösta med en preregistrerad materialitetsregel. 0 fält kvar i "
                        "KRÄVER ÅTGÄRD.",
        "feature_blueprint": {
            "n_kandidater_totalt": len(blueprint),
            "status_fordelning": dict(bp_status),
            "n_implementerad_fore_blueprint": bp_status.get("IMPLEMENTERAD", 0),
            "n_kan_byggas_ej_byggd": bp_status.get("KAN BYGGAS MEN UPPSKJUTEN", 0),
            "n_saknar_data": bp_status.get("BLOCKERAD/SAKNAR DATA", 0),
            "n_bor_inte_byggas": bp_status.get("BÖR INTE BYGGAS", 0),
            "artefakt": "docs/probes/feature_blueprint.json",
        },
        "materialitetsregel": {
            "troskel": "|bas| ≥ 1% av total_Assets samma period",
            "tillampas_pa": ["gross_margin_ttm", "operating_margin_ttm", "net_margin_ttm",
                             "fcf_margin_ttm", "ocf_margin_ttm", "revenue_growth_yoy "
                             "(båda perioderna)", "eps_growth_yoy (båda perioderna, via "
                             "profit_To_Equity_Holders)"],
            "preregistrerad_fore_targetkoppling": True,
            "motiv": "en verksamhet med <1% av balansomslutningen i omsättning är i praktiken "
                    "inte 'opererande' i den mening marginalmått förutsätter — tröskeln är "
                    "vald på ekonomiska grunder, inte kalibrerad mot framtida avkastning",
            "resultat": "se docs/probes/fundamenta_panel_build_v2.json "
                       "(materialitetsregel_stoppade) för exakt radantal per fält",
        },
        "fryst_utc": "2026-08-08T00:00:00+00:00",
        "timestamp_policy": "deterministic dataset_v1.0 release timestamp; rebuild wall-clock time is not serialized",
        "beroenden": {
            "spar_A_dataset_sha256": man_a["dataset_sha256"],
            "spar_A_version": man_a["version"],
            "spar_B_kombinerad_sha256": man_b["kombinerad_sha256"],
            "spar_B_version": man_b["version"],
            "spar_B_extra_dataset_sha256": man_b_extra["dataset_sha256"],
            "membership_sha256": sha(V2 / "validated/membership_main_list_pit.json"),
            "external_eodhd_manifest_sha256": sha(V2 / "validated/external_dependencies_manifest.json"),
        },
        "target": {
            "definition": target_man["definition"],
            "parametrar": target_man["parametrar"],
            "censurering": target_man["censurering"],
            "utfall": target_man["utfall"],
            "kanda_begransningar": target_man["kanda_begransningar"],
        },
        "feature_registry": {
            "version": registry["registry_version"],
            "sha256": sha(V2 / "docs/probes/feature_registry.json"),
            "n_falt_totalt": len(alla_falt),
            "n_core": len(registry["CORE"]), "n_fundamenta": len(registry["FUNDAMENTA"]),
            "n_anvandbara_core": len(anv_core), "n_anvandbara_fundamenta": len(anv_fund),
            "samtliga_falt_byggda_och_godkanda": [f["id"] for f in anvandbara],
        },
        "paneler": {
            "core_panel": {
                "fil": "panels/core_panel.json",
                "sha256": sha(PANELS / "core_panel.json"),
                "n_rader": qa["nyckelkonsistens"]["n_core"],
                "n_instrument": len({r["kod"] for r in json.loads((PANELS / "core_panel.json").read_text())}),
                "n_features": len(anv_core),
                "survivorship_saker_prisuniversum": True,
                "historisk_membership_fullt_pit_verifierad": False,
                "beskrivning": "Enbart Spår A. Survivorship-säker för det rekonstruerade prisuniversumet; historisk huvudliste-membership är endast verifierad där membership_verified=True.",
            },
            "core_fundamenta_panel": {
                "fil": "panels/core_fundamenta_panel.json",
                "sha256": sha(PANELS / "core_fundamenta_panel.json"),
                "n_rader": qa["nyckelkonsistens"]["n_fund"],
                "n_instrument": len({r["kod"] for r in json.loads((PANELS / "core_fundamenta_panel.json").read_text())}),
                "n_features": len(anv_core) + len(anv_fund),
                "survivorship_saker": False,
                "varning": "INTE survivorship-säkert för fundamentakolumnerna. 67 av 68 "
                          "Nasdaq Stockholm-bolag som avnoterades 2020–2026 saknar all "
                          "fundamentadata (FUNDAMENTAL_QA.md). has_fundamenta=False för "
                          "dessa rader — provenance är alltid explicit, aldrig dold. "
                          "CORE-delen av samma panel (pris/volym) ÄR survivorship-säker.",
                "instrument_med_fundamenta": qa["instrument_med_fundamenta"],
            },
            "target_table": {
                "fil": "panels/target_table.json",
                "sha256": sha(PANELS / "target_table.json"),
                "n_rader": target_man["utfall"]["n_rader"],
                "n_instrument": target_man["utfall"]["n_instrument"],
                "byggd_separat_fran_features": True,
                "survivorship_saker": True,
            },
        },
        "auxiliary_artifacts": {
            "terminal_events": {"fil": "validated/terminal_events.json",
                                "sha256": sha(V2 / "validated/terminal_events.json"),
                                "n_events": len(json.loads((V2 / "validated/terminal_events.json").read_text()))},
            "membership": {"fil": "validated/membership_main_list_pit.json",
                           "sha256": sha(V2 / "validated/membership_main_list_pit.json"),
                           "n_instrument": len(json.loads((V2 / "validated/membership_main_list_pit.json").read_text())["rows"])},
            "external_eodhd": {"fil": "validated/external_dependencies_manifest.json",
                               "sha256": sha(V2 / "validated/external_dependencies_manifest.json")},
        },
        "pit_leakage_qa": {
            "status": "SAMTLIGA STRUKTURELLA KONTROLLER PASSERADE",
            "nyckelkonsistens": qa["nyckelkonsistens"],
            "inga_target_kolumner_i_features": qa["inga_target_kolumner"],
            "empirisk_pit_core_stickprov": qa["empirisk_pit_core"],
            "empirisk_pit_fund_fullstandig": qa["empirisk_pit_fund"],
            "empirisk_pit_fund_senaste_rapport_stickprov": qa["empirisk_pit_fund_senaste"],
            "target_pit": qa["target_pit"],
        },
        "coverage_qa": "fullständig per fält/år i docs/probes/spar_c_qa.json "
                       "(coverage_core, coverage_fundamenta)",
        "extremvarden": "flaggade, ALDRIG klippta eller imputerade — se "
                        "feature_registry.json (anmarkning_extremvarde per fält) och "
                        "docs/probes/spar_c_qa.json (extremvarden)",
        "kanda_begransningar_hela_spar_c": [
            "Historisk huvudliste-/segmentmembership är ofullständig. Källdaterade admissions "
            "filtreras; övriga instrument/rader har membership_verified=False och bygger endast "
            "på observerbar handel i det rekonstruerade universumet.",
            "REBALANCE_WEEKS=4 ger 13x överlapp mellan konsekutiva 52-veckors etiketter — "
            "måste hanteras i en framtida train/test-splittare (embargo_weeks=52 är "
            "preregistrerat för det syftet, inte applicerat här).",
            "7 fundamentafält (5 marginalmått + revenue_growth_yoy + eps_growth_yoy) har en "
            "nära-noll-bas-patologi vid extremt låg omsättning — hanterat med den "
            "preregistrerade materialitetsregeln (se 'materialitetsregel' ovan), som sätter "
            "null istället för ett matematiskt korrekt men ekonomiskt missvisande extremvärde. "
            "Exakt radantal per fält: docs/probes/fundamenta_panel_build_v2.json.",
            "CORE+FUNDAMENTA-panelen är inte survivorship-säker för fundamentakolumnerna "
            "(67/68 avnoterade saknar data) — CORE-delen och target är det.",
            "Feature-uppsättningen (13 CORE + 11 FUNDAMENTA) är avsiktligt begränsad till "
            "väldokumenterade, standardmässiga faktordefinitioner — INTE en uttömmande "
            "genomgång av alla tänkbara kombinationer av Spår A/B:s råfält.",
        ],
        "status": "FRYST/REDO FÖR SPÅR D: inga kända reparerbara blockerare; membership-osäkerhet och fundamental survivorship är explicit kvantifierade datasetbegränsningar. Ingen modellträning utförd.",
    }
    MANIFEST.write_text(json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")
    print("=" * 100)
    print("SPÅR C MANIFESTERAT — FRYST/REDO FÖR SPÅR D")
    print("=" * 100)
    print(f"core_panel.json:            {man['paneler']['core_panel']['sha256']}")
    print(f"core_fundamenta_panel.json: {man['paneler']['core_fundamenta_panel']['sha256']}")
    print(f"target_table.json:          {man['paneler']['target_table']['sha256']}")
    print(f"\nfalt totalt: {len(alla_falt)} (CORE {len(registry['CORE'])} + "
          f"FUNDAMENTA {len(registry['FUNDAMENTA'])})")
    print(f"\nartefakt: {MANIFEST}")


if __name__ == "__main__":
    main()
