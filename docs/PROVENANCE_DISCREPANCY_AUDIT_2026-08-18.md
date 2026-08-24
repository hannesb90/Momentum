# PROVENANCE-DISKREPANSAUDIT MOT DEN NYA FORSKNINGSSTATUSEN

Datum 2026-08-18 · Utförd enligt `AGENTS_RESEARCH_HANDOFF.md` pre-flight punkt 3
**Inga tester körda. Inga frysta komponenter ändrade. Ingen size-hypotes berörd.**

Samtliga åtta auktoritativa dokument lästa. Därefter verifierade jag dem mot
faktiska filer, hashar och skript, enligt instruktionen att inte acceptera något
påstående utan kontroll. **Tre diskrepanser hittades. Två av dem är
säkerhetskritiska.**

---

## Del A — Repo-statusen bekräftad

Följande stämmer och accepteras:

| | |
|---|---|
| G-HET-1, G-SIZE-HET-1 | `NOT_IDENTIFIED` — verifierat: båda är riktiga beräkningar (615/632 rader, läser priser och paneler) men betingade på odaterad `market_list` |
| G-HIER-1, G-HIER-2 | `NON_COMPUTED_CLAIM` — verifierat: `g_hier_2_analysis.py` läser 0 prisfiler, importerar sklearn rad 39 utan att anropa den, och har 25 hårdkodade resultatfält |
| Population Passport | **inte fryst** — bekräftat, saknas i FREEZE_REGISTRY |
| G-PATH-1/2, H-ORIGIN-1, G-PROP-1 | `CLOSED_NEGATIVE` — står kvar |
| Öppna kandidater | **0** |
| K1 sektormanifest | hash **verifierad: matchar filen** |

---

## Del B — DISKREPANS 1 (säkerhetskritisk): governanceregistret licensierar den kontaminerade variabeln

`DATA_GOVERNANCE_REGISTRY.md` och `research_k/data_governance_registry.json` anger
för `list_segment (Large/Mid/Small Cap)`:

```json
"source":          "Avanza Stockholm Market List PIT Archive",
"date_fields":     ["panel_date"],
"pit_semantics":   "Expanding PIT list membership; delisted tickers assigned Terminal list",
"terminal_handling":"Assigned Terminal/Avnoterad category",
"qa_status":       "PASSED_100_PERCENT_QA",
"model_usage_permission": "ALLOWED_FOR_POPULATION_STRATIFICATION_ONLY"
```

Verifierat mot den faktiska källan
`research_k/avanza_sector_recovery_probe/qa_identity_sector_evidence.json`:

| Påstående i registret | Faktiskt förhållande |
|---|---|
| "PIT Archive" | En enda skrapning, `AVANZA_SECTOR_RECOVERY_20260809_V2` |
| `date_fields: ["panel_date"]` | **Fältet finns inte.** Filens fält är `instrument_id, terminal, expected_isin, expected_name, identity_method, identity_confidence, avanza_orderbook_id, avanza_isin, avanza_name, avanza_ticker, market_place, market_list, avanza_sector_path_raw, avanza_sector_objects_raw, source_url, retrieved_at, query_evidence, borsdata_sector_id_current, borsdata_branch_id_current` |
| "Expanding PIT list membership" | **Ett** `market_list`-värde per instrument, 420 poster |
| "delisted tickers assigned Terminal list" | Kommer ur `terminal_events.json` = avnoterade **någon gång**; tilldelas i samtliga paneler, även år före händelsen |
| `PASSED_100_PERCENT_QA` | Ingen QA av tidsdimensionen kan ha utförts — den finns inte |

Registret kan representera en tidsdimension: raden intill, `canonical_sector`,
anger korrekt `date_fields: ["valid_from", "valid_to"]`, och den filen har dem.
För `list_segment` påstås en tidsdimension som inte existerar.

**Detta motsäger direkt fyra andra auktoritativa utsagor** — `CURRENT_RESEARCH_STATE`
§3, `INVALIDATED_AND_SUPERSEDED_RESULTS` punkt 2, `RESEARCH_INDEX` raderna
T-G-HET-01/T-G-SIZE-HET-01, samt den stående instruktionen att `market_list` inte
får användas som historisk PIT-size och att `terminal_events` inte får användas
som feature före faktisk händelsetidpunkt.

**Konsekvens om den lämnas:** en agent som följer pre-flight-protokollet läser
governanceregistret, ser `ALLOWED_FOR_POPULATION_STRATIFICATION_ONLY` med
`PASSED_100_PERCENT_QA`, och återinför exakt den variabel som ogiltigförklarade
G-HET-1 och G-SIZE-HET-1. Registret är den enda platsen där en variabel får
godkännas, så felet är operativt aktivt.

---

## Del C — DISKREPANS 2 (säkerhetskritisk): tre av fyra frysningshashar verifierar inte

`FREEZE_REGISTRY.md` inleds: *"Endast komponenter med 100 % verifierad,
reproducerbar beräkning och PIT-giltighet finns i detta register."*

| Komponent | Hash i registret | Faktisk `sha256sum` | Utfall |
|---|---|---|---|
| H0 Core (`tools/h1419_kor_exakt_h0.py`) | `e27863ef…4e7687` | `c94fd568c0764bd1fede73c25e8f6441b9a16eb4b57c5310adb08c3cfc474690` | **MISMATCH** |
| Hysteres (`tools/hysteres_kop_och_agande.py`) | `c94812a1…726581` | `fef90f15b25f6ee491807c4f30e0564a839b8ca2c17b434554c8d759222ada87` | **MISMATCH** |
| G97-P (`tools/g97p_hogvolsvans.py`) | `74191a27…192039` | `a8a96ab3504295a938c6769b8b7ed2efdd3512952d549517b0b36d23b0e44ec6` | **MISMATCH** |
| K1 manifest | `816cb6b3…523041` | `816cb6b38a2130728bd282e8352c74ccf119f374b8747717c0b0603fa5523041` | **MATCH** |

Kan mismatchen förklaras av senare redigering?

* **Hysteres: nej.** Filens mtime är `2026-08-15 18:54`, låsdatum `2026-08-16`.
  Filen är oförändrad sedan före sin egen frysning och hashen stämmer ändå inte.
  Den kan alltså aldrig ha beräknats ur filen.
* **H0:** mtime `2026-08-15 21:04`, låsdatum `2026-08-15` — en redigering samma
  dag efter låsningen är möjlig. Men då var frysningen inte upprätthållen.
* **G97-P:** mtime `2026-08-17 15:43`, låsdatum `2026-08-16` — filen ändrades
  **efter** sin frysning. Registrets hash `74191a274190823901b81628f73b6109312529837190
  01b92837192038192039` är 64 hex-tecken men motsvarar ingen version av filen.

Oavsett vilken förklaring som gäller per rad håller inte registrets egen utsaga om
100 % verifiering. **K1 är den enda komponent vars frysning faktiskt verifierar.**

---

## Del D — DISKREPANS 3: frysta komponenters beskrivningar matchar inte koden

### D.1 G97-P beskrivs som fel regel

`FREEZE_REGISTRY.md` och `RESEARCH_INDEX.md` anger båda
*"Exkluderar 97.5:e percentilen volatilitetssvans"* respektive
*"Beräknad 97.5:e percentil vol-exkludering"*.

`tools/g97p_hogvolsvans.py` säger något annat:

```
rad  3:  SEX namn är låst (6/30 = 20 % = den högsta ...)
rad 11:  3. De SEX med högst vol_52w exkluderas.
rad 47:  K = 6                      # LÅST
rad 188: "regel": "exkludera de sex hogsta vol_52w i topp-30, ersatt med rank 31-36"
```

Regeln är **de sex högsta `vol_52w` inom Top-30, ersatta med rank 31–36** — den
högsta femtedelen av en trettiogruppe, inte en 97,5:e percentil av något. Två
auktoritativa dokument beskriver en fryst regel felaktigt.

### D.2 H0 tillskrivs STACK_H:s resultat

`CURRENT_RESEARCH_STATE.md` §1: *"H0 Core Momentum Engine … (CAGR 13,56 %,
MaxDD −24,32 %). Fil `tools/h1419_kor_exakt_h0.py`."*

`tools/stack_h_motor.py` rad 17 och 169, ordagrant:

```
Registrerat utfall att reproducera på 2020-2026:
    Net CAGR 13,56 %, Vol 17,02 %, MaxDD -24,32 %, omsättning 24,0 %
```

Det är **SHADOW_INTEGRATED_STACK_H** — ERC invvol^1.5 + FR-overlay + hysteres
rank 35 + NTZ 0,005 + SMA200 — alltså en annan modellfamilj än ren H0, och ett
**2020-2026**-tal. Den angivna filen `h1419_kor_exakt_h0.py` kör **2014-2019**
och kan inte producera det.

Två fel i samma rad: fel modell och fel fönster. Detta är samma kategori av
misstag som den permanenta regeln *"kolla alltid vilken modellversion en loggpost
kördes mot innan den citeras"* finns för.

---

## Del E — Var den stoppade planen står

Planen i `SIZE_PASSPORT_FREEZE_AUDIT_OCH_ARKITEKTUR.md` Del 3.6, mot ny status:

| Fas | Innehåll | Min status | Repo-status nu | Utfall |
|---|---|---|---|---|
| **0** | Shadow-logg av A-vs-B-par ur fryst logik | KAN STARTAS | ingen motsvarighet; `OPEN: 0` | **VILANDE — se nedan** |
| **0b** | Daterad storleksklassificering, `valid_from`/`valid_to` | DATAUPPDRAG | förutsättning enligt §5 | **oförändrat datauppdrag** |
| **1** | G-HIER-1 på riktigt | spärrad | `NON_COMPUTED_CLAIM`, inga öppna kandidater | **SPÄRRAD** |
| **2** | G-HIER-2 på riktigt | spärrad | `NON_COMPUTED_CLAIM` | **SPÄRRAD** |
| **3** | G-HIER-3 decision policy | spärrad | kräver 2 | **SPÄRRAD** |
| **4** | Size-conditional G97-P audit | spärrad | kräver PIT-size | **SPÄRRAD** |
| **5** | 2×2 faktoriell champion | spärrad | kräver 3 och 4 | **SPÄRRAD** |

Min tidigare bedömning och repots oberoende revision sammanfaller på varje punkt.
Ingen fas 1–5 får köras.

### Fas 0 stoppas också — och det avviker från min egen tidigare plan

Jag klassade fas 0 som startbar eftersom den inte rör size, inte ändrar H0 och
bara loggar. Mot den nya statusen stoppar jag den ändå:

`CURRENT_RESEARCH_STATE.md` §5 anger **noll öppna kandidater** och att projektet
**först** kräver PIT-korrekt storleksklassificering *och* reproducerbara dynamiska
beräkningar innan nya hierarki- eller beslutsmodeller får prövas. Shadow-loggens
enda konsument är fas 1–3. Att bygga infrastruktur vars mottagare är spärrad, i
ett repo som just fått tre komponenter ogiltigförklarade för bristande
provenance, är fel prioritering — och de tre diskrepanserna ovan måste åtgärdas
först.

Fas 0 förblir korrekt designad och kan återupptas när Del B–D är stängda.

---

## Del F — Vad som faktiskt är licensierat att göra nu

`OPEN: 0`. Det finns ingen forskningsuppgift att köra. Det enda licensierade
arbetet är det som pre-flight-protokollets punkt 3 föreskriver: verifiera
provenance och sätta korrekt status. Det är utfört, och det gav tre fynd.

**Rekommenderade åtgärder, i ordning:**

1. **`list_segment` ska sättas till förbjuden** i båda governanceregistren, med
   `date_fields: []` och `qa_status: FAILED_PIT_HISTORY_GATE`. Detta är den enda
   åtgärd som är brådskande, eftersom raden aktivt licensierar den kontaminerade
   variabeln.
2. **Frysningshasharna ska räknas om ur filerna** och de gamla behållas som
   `claimed_hash` intill `verified_hash`, så att fyndet inte raderas av
   korrigeringen.
3. **G97-P:s beskrivning rättas** till "de sex högsta `vol_52w` i Top-30, ersatta
   med rank 31–36".
4. **H0:s prestandarad rättas** — 13,56 %/−24,32 % tillhör STACK_H 2020-2026 och
   ska inte stå på H0.

Punkt 1 utförs härmed, eftersom den motsvarar en uttrycklig stående instruktion
och en kvarlämnad rad kan orsaka faktisk skada. Punkt 2–4 rör auktoritativa
dokument från en oberoende revision och lämnas som förslag för beslut, inte
ensidig ändring.
