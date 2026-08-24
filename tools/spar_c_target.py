"""Spar C, steg 1: FORREGISTRERAT target, byggt separat fran features.

Anvander ENBART Spar A (validated/prices/prices_validated.json). Ingen
fundamentadata, inga legacy-defaults. Malet ar en 52-veckors framatblickande
totalavkastning, konsekvent med den redan uttalade fragan for modellracet
("Finns det ... en modell som robust kan rangordna svenska storbolag efter
2021?" - "52v-target" namndes explicit dar). Detta ar INTE ett tyst arv fran
legacy config - det ar en medveten, dokumenterad preregistrering for just
detta dataset, las nedan.

FORREGISTRERADE PARAMETRAR (lasta i denna fil - andring kraver ny version):
  TARGET_HORIZON_WEEKS = 52
      Motiv: matchar den uttryckligen efterfragade fragestallningen for
      modellracet. En kortare horisont vore lika forsvarbar men skulle vara
      ett NYTT beslut, inte en preregistrering av det som redan efterfragats.
  EMBARGO_WEEKS = 52
      Motiv: embargo >= horisont ar den minimala regeln for att en
      train/test-uppdelning inte ska lacka - ingen testrad far ha ett
      etikettfonster som overlappar en traningsrads etikettfonster.
      Embargot appliceras INTE i denna fil (ingen modellering sker i Spar C)
      - det skrivs bara in i manifestet for att en framtida splittare inte
      ska kunna falla tillbaka pa nagot annat vantevarde.
  REBALANCE_WEEKS = 4
      Motiv: panelens observationsfrekvens (en rad per instrument var 4:e
      vecka), inte portfoljens handelsfrekvens (ett separat, senare beslut).
      4 veckor halver overlappet mellan konsekutiva etiketter fran 52x
      (veckovis) till 13x - fortfarande starkt korrelerat, men panelen blir
      hanterbar och tathet racker for framtida CV-arbete. Dokumenterat
      explicit har eftersom instruktionen kraver att detta INTE far vara ett
      dolt globalt default.
  UNIVERSUM_FILTER: Nasdaq Stockholm (OMX Large/Mid/Small Cap) fran
      2020-01-01, PIT-dynamiskt per instruments faktiska prisserie i Spar A
      (IPO/avnotering trunkerar naturligt via VALIDATED-seriens start/slut).
      Marknadssegment (large/mid/small) ar INTE PIT-rekonstruerat historiskt -
      se kanda begransningar i manifestet.

Target = adj[T + 52v] / adj[T] - 1, dar adj ar Spar A:s redan
splitt-/utdelningsjusterade adjusted_close.

TERMINALHANTERING (C-2, CODEX_SECOND_OPINION_V2_ABC.md - fixad 2026-08-08):
Tidigare version satte target=null for ALL hoger-censurering (T+52v bortom
seriens slut), utan att skilja pa VARFOR serien slutar dar. Det ar fel: en
instrumentserie kan sluta antingen (a) for att HELA datamaterialet slutar dar
(dagens datauttag, 2026-07-24 - en genuint okand framtid for alla aktiva
instrument), eller (b) for att just DETTA instrument avnoterades/gick i
konkurs/kopptes upp FORE dess (en KAND handelse, inte en okand framtid).
Att blank-nulla (b) ar informativ censurering: de sista ~52 veckorna fore
varje avnotering forsvinner systematiskt ur trainingsurvalet, vilket kan
snedvrida uppmatt modellprestanda uppat (overlevnadsbias i sjalva
etiketten, inte bara i featurestacket).

Seriens sista datum används ALDRIG som proxy för ekonomisk terminalhändelse.
Endast explicit verifierade avnoteringar i instrument_master får skapa ett
separat terminalutfall. Eftersom ett kort terminalutfall inte är jämförbart
med den preregistrerade 52v-definitionen lämnas target_fwd52w null; utfallet,
eventtypen och den faktiska horisonten lagras i separata kolumner.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
PRICES = V2 / "validated/prices/prices_validated.json"
MEMBERSHIP = V2 / "validated/membership_main_list_pit.json"
OUT_DIR = V2 / "panels"
TARGET_MANIFEST = V2 / "docs/probes/target_manifest.json"
TARGET_TABLE = OUT_DIR / "target_table.json"

# ---------------------------------------------------------------- LÅSTA ----
TARGET_HORIZON_WEEKS = 52
EMBARGO_WEEKS = 52
REBALANCE_WEEKS = 4
UNIVERSUM_START = "2020-01-01"
TARGET_KÄLLA_FÄLT = "adj"          # adjusted_close, Spår A
MAX_PRICE_LAG_CALENDAR_DAYS = 8     # preregistrerad kalenderdagstolerans


def d(s: str) -> date:
    return date.fromisoformat(s[:10])


def veckogaller(första: date, sista: date, steg_veckor: int) -> list:
    """Panel-datum: varannan/var-N:e fredag fran forsta tillgangliga handelsdag."""
    # första fredag på/efter första
    off = (4 - första.weekday()) % 7          # fredag = weekday 4
    start = första + timedelta(days=off)
    ut, cur = [], start
    while cur <= sista:
        ut.append(cur)
        cur += timedelta(weeks=steg_veckor)
    return ut


def närmast_handelsdag(datum_lista: list, mål: date,
                       max_dagar: int = MAX_PRICE_LAG_CALENDAR_DAYS):
    """Senaste faktiska handelsdatum PÅ ELLER FÖRE mål (aldrig efter -> ingen läckage)."""
    bäst = None
    for x in datum_lista:
        dt = d(x)
        if dt <= mål:
            if bäst is None or dt > d(bäst):
                bäst = x
        else:
            break
    if bäst and (mål - d(bäst)).days <= max_dagar:
        return bäst
    return None


def main() -> None:  # noqa: C901
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    priser = json.loads(PRICES.read_text(encoding="utf-8"))
    membership = {r["kod"]: r for r in
                  json.loads(MEMBERSHIP.read_text(encoding="utf-8"))["rows"]}
    if set(priser) != set(membership):
        raise RuntimeError("membership ledger and target price universe differ")
    master = json.loads((V2 / "docs/probes/instrument_master.json").read_text(encoding="utf-8"))
    källhash = hashlib.sha256(PRICES.read_bytes()).hexdigest()

    man = {
        "steg": "Spår C — target (preregistrerad, byggd separat från features)",
        "fryst_utc": "2026-08-08T00:00:00+00:00",
        "timestamp_policy": "deterministic dataset_v1.0 release timestamp; rebuild wall-clock time is not serialized",
        "kalla": {"fil": "validated/prices/prices_validated.json",
                  "sha256": källhash, "fält": TARGET_KÄLLA_FÄLT},
        "parametrar": {
            "target_horizon_weeks": TARGET_HORIZON_WEEKS,
            "embargo_weeks": EMBARGO_WEEKS,
            "rebalance_weeks": REBALANCE_WEEKS,
            "universum_start": UNIVERSUM_START,
            "max_price_lag_calendar_days": MAX_PRICE_LAG_CALENDAR_DAYS,
            "universum_filter": "rekonstruerat svenskt Nasdaq Stockholm-universum med observerbar "
                                "handel; källdaterade admissions filtreras PIT, övrig historisk "
                                "membership är explicit okänd i membership_main_list_pit.json",
        },
        "definition": "target(instrument, T) = adj[T+52v] / adj[T] - 1, adj = Spår A "
                      "adjusted_close (redan split-/utdelningsjusterad, R1-R8 i "
                      "manifest_sparA.json)",
        "censurering": "target_fwd52w är null när full 52v-horisont saknas. Endast explicit "
                       "verifierade terminalhändelser i validated/terminal_events.json kan "
                       "skapa terminal_return; detta kortare utfall lagras separat och är "
                       "inte en del av det preregistrerade 52v-targetet.",
        "kanda_begransningar": [
            "Large/Mid/Small-segmentet inom huvudlistan särredovisas inte; V2:s investerbara "
            "universum omfattar alla tre och membership-ledgern styr inträde på huvudlistan.",
            "REBALANCE_WEEKS=4 ger 13x överlapp mellan konsekutiva 52-veckors etiketter — "
            "kvarvarande autokorrelation måste hanteras i en framtida train/test-splittare, "
            "inte i target-tabellen.",
        ],
    }
    TARGET_MANIFEST.write_text(json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")
    print("[target] preregistrering skriven:", TARGET_MANIFEST)
    print(json.dumps(man["parametrar"], indent=2, ensure_ascii=False))

    # ---------------- panel-datum (gemensam kalender) -------------------
    första_global = date.fromisoformat(UNIVERSUM_START)
    sista_global = max(d(rader[-1]["d"]) for rader in priser.values())
    panel_datum = veckogaller(första_global, sista_global, REBALANCE_WEEKS)
    print(f"[target] panel-kalender: {len(panel_datum)} datum, "
          f"{panel_datum[0]}–{panel_datum[-1]}, steg {REBALANCE_WEEKS}v")

    # Explicit verifierade terminalhändelser. Ett kort prisserieslut är aldrig
    # en terminalsignal. Dubblettposter för samma kod måste vara eniga.
    terminal_per_kod = {}
    for r in master:
        kod = (r.get("eodhd") or {}).get("code")
        if not kod or kod not in priser or not r.get("avnoterad_datum"):
            continue
        event = {"event_date": r["avnoterad_datum"][:10],
                 "event_type": "verifierad_avnotering",
                 "evidence": r.get("avnoterad_orsak"), "source_slug": r.get("slug")}
        if kod in terminal_per_kod and terminal_per_kod[kod]["event_date"] != event["event_date"]:
            raise RuntimeError(f"{kod}: motstridiga verifierade terminaldatum")
        terminal_per_kod[kod] = event
    (V2 / "validated/terminal_events.json").write_text(
        json.dumps(terminal_per_kod, indent=1, ensure_ascii=False), encoding="utf-8")

    n_rader = n_target_ok = n_censur_okand_framtid = n_terminal = n_utanfor_serie = 0
    tabell = {}
    for kod, rader in priser.items():
        datum_lista = [r["d"] for r in rader]
        adj_by_d = {r["d"]: r["adj"] for r in rader}
        mem = membership[kod]
        effective_from = mem.get("member_from") if mem.get("membership_verified") else mem["observation_window_from"]
        serie_start = max(d(datum_lista[0]), d(effective_from))
        serie_slut = d(datum_lista[-1])
        if mem.get("member_to"):
            serie_slut = min(serie_slut, d(mem["member_to"]))
        terminal = terminal_per_kod.get(kod)
        instrument_rader = []
        for pd_ in panel_datum:
            if pd_ < serie_start or pd_ > serie_slut:
                continue                                   # instrumentet existerar inte här
            t0 = närmast_handelsdag(datum_lista, pd_)
            if t0 is None:
                # CORE använder samma fasta stalenessgräns och ska därför
                # inte heller innehålla denna nyckel.
                continue
            mål = pd_ + timedelta(weeks=TARGET_HORIZON_WEEKS)
            a0 = adj_by_d.get(t0)
            terminal_return = terminal_horisont = terminal_typ = terminal_datum = None
            if mål > serie_slut:
                if terminal and a0 and a0 > 0 and d(terminal["event_date"]) >= d(t0):
                    t1_real = datum_lista[-1]
                    a1 = adj_by_d.get(t1_real)
                    terminal_return = (a1 / a0 - 1.0) if (a1 and a1 > 0) else None
                    terminal_horisont = (d(t1_real) - d(t0)).days
                    terminal_typ, terminal_datum = terminal["event_type"], terminal["event_date"]
                    n_terminal += terminal_return is not None
                # Canonical targetdefinition ändras inte: kortare terminalutfall
                # lagras separat och blandas aldrig in i target_fwd52w.
                tgt, typ, horisont_dagar = None, None, None
                n_censur_okand_framtid += 1
            else:
                t1 = närmast_handelsdag(datum_lista, mål)
                a1 = adj_by_d.get(t1) if t1 else None
                if a0 and a1 and a0 > 0:
                    tgt = a1 / a0 - 1.0
                    typ = "forward_52w"
                    horisont_dagar = (d(t1) - d(t0)).days
                    n_target_ok += 1
                else:
                    tgt, typ, horisont_dagar = None, None, None
                    n_utanfor_serie += 1
            instrument_rader.append({"panel_date": pd_.isoformat(), "price_date": t0,
                                     "membership_verified": bool(mem.get("membership_verified")),
                                     "target_fwd52w": tgt, "target_typ": typ,
                                     "realiserad_horisont_dagar": horisont_dagar,
                                     "terminal_return": terminal_return,
                                     "terminal_horisont_dagar": terminal_horisont,
                                     "terminal_event_type": terminal_typ,
                                     "terminal_event_date": terminal_datum})
            n_rader += 1
        if instrument_rader:
            tabell[kod] = instrument_rader

    TARGET_TABLE.write_text(json.dumps(tabell, ensure_ascii=False, separators=(",", ":")),
                            encoding="utf-8")
    tabellhash = hashlib.sha256(
        json.dumps({k: tabell[k] for k in sorted(tabell)}, sort_keys=True,
                   separators=(",", ":")).encode()).hexdigest()
    print(f"\n[target] {n_rader} rader, {len(tabell)} instrument")
    print(f"  target beräknad (52v framåt): {n_target_ok} ({100*n_target_ok/n_rader:.1f} %)")
    print(f"  separata verifierade terminalutfall: {n_terminal} "
          f"({100*n_terminal/n_rader:.1f} %; inte target_fwd52w)")
    print(f"  höger-censurerad (genuint okänd framtid): {n_censur_okand_framtid} "
          f"({100*n_censur_okand_framtid/n_rader:.1f} %)")
    print(f"  saknar prispunkt exakt vid target-datum: {n_utanfor_serie}")
    print(f"  target_table_sha256: {tabellhash}")

    man["utfall"] = {"n_rader": n_rader, "n_instrument": len(tabell),
                     "n_target_beraknad_52v_framat": n_target_ok,
                     "n_separata_verifierade_terminalutfall": n_terminal,
                     "n_censurerad_okand_framtid": n_censur_okand_framtid,
                     "n_saknar_prispunkt": n_utanfor_serie,
                     "target_table_sha256": tabellhash}
    TARGET_MANIFEST.write_text(json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
