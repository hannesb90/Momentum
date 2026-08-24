# H0 V3 — PIT MEMBERSHIP RECONSTRUCTION

Datum 2026-08-18 · **Datakorrigering, inte modellförbättring** · Noll forskningstester
Artefakter: `research_k/h0_v3/` med SHA256-manifest

**Dom: `H0_V3_PIT_MEMBERSHIP_VALIDATED`**

---

## 0. Pre-flight

Gate **PASS**. H0 V2:s frysningskedja verifierad: prereg `23cd3cde…`, samtliga 7 låsta
indatafiler OK, resultatet refererar rätt hash.

### Membership-input — identifierad och hashad

| | |
|---|---|
| **Artefakt** | `research_k/nasdaq_segment_foundation/monthly_size_snapshots.json` |
| **SHA256** | `5ed725424f9ea9b5cee53b9245f4ecd66c3bbaa3507ee18e0a8397e9921c1e60` |
| Innehåll | 70 939 rader, 201 månader 2009-08…2026-07 |
| Filter i källan | `Location = STO` och `Instrument Type = Stock` |
| Foundation | `PIT_SIZE_FOUNDATION_VALID`, 14 av 14 |

**Segmentets roll:** segment används **enbart** som markör för Main Market-listan.
Segmentvärdet Large/Mid/Small läses aldrig och används aldrig som feature.

**Verifierat ej använda:** Avanza `market_list`, `sweden_universe.csv` / `CAP_TIER_MAP`,
`membership_h1419_v2.json` som medlemskapskälla, dagens Nasdaq-lista bakåtprojicerad,
`terminal_events.json` som eligibility-feature.

---

## 1. Preregistrering låst före resultat

`research_k/h0_v3/h0_v3_preregistration.json`
SHA256 `9fc4a4ae80051bdeedcadbe86983193b5704ec832e95462ed5e6bcc52d8c18c6`
Status `LOCKED_BEFORE_ANY_V3_RESULT`, låst 2026-08-18T19:54:51Z — **före** varje V3-körning.

Låser A–H som oförändrade från V2 och definierar den enda tillåtna ändringen:

> `eligible(i,t) = TRUE` endast om officiell Nasdaq PIT-data visar att instrument *i*
> tillhörde Nasdaq Stockholm Main Market vid beslutstidpunkt *t*.
> **Prisexistens får aldrig ersätta membership.**

---

## 2. Temporal semantik — låst före körning

| Fall | Regel |
|---|---|
| Beslutsregel | månad `M` = senaste rapportmånad med `M < YYYY-MM(t)`. Aldrig samma månad, aldrig senare |
| Listing intramonth | eligible först från den panel vars beslutsregel pekar på en månad där instrumentet förekommer |
| Delisting intramonth | eligible så länge instrumentet förekommer i den använda månaden; avnoteringsdatum används **aldrig** för att exkludera i förväg |
| Saknad månad | ej eligible. Ingen interpolation |
| ISIN-byte | Orderbook Code bär kontinuiteten (159 av 707 instrument har flera ISIN) |
| Confirmed code reuse | **sammanfogas aldrig** — kan inte ärva medlemskap över sitt gap |
| Aktieslag | instrumentnivå bevaras, A/B/C/SDB slås aldrig ihop |

---

## 3. Eligibility-panel — QA

| | 2014-2019 | 2020-2026 |
|---|---:|---:|
| H0-kandidater | 21 896 | 23 293 |
| **Eligible** | 18 825 = **86,0 %** | 22 014 = **94,5 %** |
| PRE_LISTING | 2 980 | 1 107 |
| POST_DELISTING | 12 | 0 |
| Confirmed code reuse, ej sammanfogad | 0 | 132 |
| **Unresolved** | **79 = 0,36 %** | **40 = 0,17 %** |

Unresolved är **ej materiell** — körningen fick fortsätta. Ingen membership gissades.

---

## 4. V2 reproducerad före V3

`tools/h1419_kor_exakt_h0_v2.py` kördes oförändrad: **bitidentiskt resultat utom
`run_utc`.** Låset verifierat, samtliga sex indatafiler oförändrade.

---

## 5. V3 — en minimal diff

`tools/h0_v3_kor.py` är ett derivat av den frysta V2-körningen. **AST-baserad jämförelse
av exekverbara rader** (kommentarer och docstrings borttagna):

| | |
|---|---:|
| Exekverbara rader V2 → V3 | 202 → 212 |
| Tillagda | **12** — 10 funktionella, 2 bokföring |
| Borttagna | 2 — båda bokföring |
| **Parametrar ändrade** | **0** |

De 10 funktionella raderna är: en import, en ISIN-identitetsmap, och eligibility-kontrollen:

```python
_elig, _orsak, _m = _pit_medlem(k, _ISIN.get(k), dt)
if not _elig:
    continue
```

De 2 bokföringsraderna är utdatasökväg och versionsträng.

---

## 6. V1 / V2 / V3

| | CAGR | Vol | MaxDD | Sharpe | Benchmark | Δ mot benchmark | KI | t |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| **V1** | 27,39 % | 14,09 % | −12,09 % | 1,785 | 18,77 % | +8,62 pp | [+3,30, +15,19] | 2,46 |
| **V2** | 29,99 % | 15,00 % | −14,63 % | 1,850 | 17,84 % | +12,15 pp | [+4,25, +23,74] | 3,27 |
| **V3** | **26,61 %** | 14,11 % | **−13,08 %** | 1,727 | 18,70 % | **+7,91 pp** | [+4,34, +13,78] | **2,40** |

* **V1 → V2**: universumreparation — 44 bolag som avnoterades 2020-2026 saknades.
* **V2 → V3**: **enbart** PIT membership correction.

**V2 → V3: ΔCAGR −3,38 pp, ΔMaxDD +1,55 pp** (drawdown förbättras).
V3:s primära utfall är fortfarande **STÖD** med t 2,40 och 100 % positiva bootstraps.

Benchmarken ändras också (17,84 → 18,70 %) eftersom det likaviktade universumet nu är
det PIT-korrekta Main Market-universumet. Det är väntat och korrekt.

> **V3:s legitimitet avgörs av PIT-korrektheten, inte av att CAGR faller.** Hade
> korrigeringen höjt avkastningen vore slutsatsen densamma.

---

## 7. Portföljdifferens V2 → V3

| | |
|---|---:|
| **Paneler som ändras** | **79 av 79 (100 %)** |
| Medelantal utbytta Top-30-namn | **6,71** |
| Median | 6,0 |
| Max | 12 |
| **Jaccard-likhet** | **0,643** |

Exkluderade V2-innehav per orsak: **520 PRE_LISTING**, **10 UNRESOLVED / ej Main Market**.

Konkreta exempel, panel 2014-01-01:

| Ticker | Orsak | Nasdaq första observation |
|---|---|---|
| SGG | PRE_LISTING | **2023-06** |
| STAR-B | PRE_LISTING | 2017-10 |
| VNV | PRE_LISTING | 2020-06 |
| MCAP | PRE_LISTING | 2016-02 |

SGG rankades alltså i H0 V2 nio och ett halvt år innan bolaget fanns på Main Market.

*Not: membership-auditen rapporterade 13,29 som "medelantal ändrade namn". Det talet var
symmetrisk differens (båda riktningarna); 6,71 här är antalet utbytta namn. 13,29 / 2 ≈ 6,6
— samma sak.*

---

## 8. Negativa kontroller — 8 av 8 PASS

| # | Krav | Utfall |
|---:|---|---|
| 1 | kan ej välja före första verifierade membership | PASS |
| 2 | kan ej behålla efter verifierad exit | PASS |
| 3 | terminal status ej bakåt | PASS — `terminal_events.json` läses inte |
| 4 | ingen 2026-segmentetikett bakåt | PASS — segmentvärdet läses aldrig |
| 5 | prisexistens ej membership | PASS — `handlas()` **och** `medlem()` krävs |
| 6 | ingen framtida Nasdaq-månad vid beslut *t* | PASS — 79 paneler kontrollerade |
| 7 | confirmed code reuse ej sammanfogad | PASS |
| 8 | H0-parametrar oförändrade | PASS — AST-verifierat |

**Injicerat test:** `kallmanad` ändrad från `<` till `<=` så att samma månad blir synlig
→ kontroll 6 **detekterar läckaget**. Gaten passerar inte tomt.

### Två egna testfel, rättade och redovisade

1. Kontroll 8:s första version var en nyckelordsdetektor som gav **falsk positiv** på
   docstringordet *"viktning, kostnader"* och substrängen `N =` i `_ISIN = {`. Ersatt med
   AST-baserad jämförelse.
2. Det första negativa testet av inputmanifestet var en **no-op** — jag bytte första
   tecknet från `0` till `0` på en hash som redan började med `0`. Med en riktig
   manipulation ger gaten 2 blockerare.

---

## 9–10. Dom och frysning

### **A — `H0_V3_PIT_MEMBERSHIP_VALIDATED`**

Ny frysningskedja `H0_V3` skapad. **V1 och V2 är oförändrade och överskrivs inte.**

| Version | Status |
|---|---|
| **V1** | `SUPERSEDED_BY_V2` — survivorship-defekt |
| **V2** | `FROZEN_BUT_MEMBERSHIP_CONTAMINATED` — historiskt fryst experiment, bevaras oförändrad |
| **V3** | `FROZEN` — **PIT-korrekt H0-baslinje för framtida forskning** |

Preregistreringen är fryst före resultat och fick därför **inte** kompletteras i efterhand.
De låsta indata redovisas i ett separat `h0_v3_input_manifest.json` (8 poster: V2:s sju
ärvda filer plus membership-datasetet), som integrity-gaten verifierar med samma stringens.

---

```
REPOSITORY INTEGRITY:            PASS
V2 REPRODUCED:                   JA — bitidentiskt utom run_utc
V3 PREREGISTERED BEFORE RETURNS: JA — låst 2026-08-18T19:54:51Z, sha 9fc4a4ae…
NASDAQ PIT MEMBERSHIP INPUT:     research_k/nasdaq_segment_foundation/monthly_size_snapshots.json
MEMBERSHIP INPUT SHA256:         5ed725424f9ea9b5cee53b9245f4ecd66c3bbaa3507ee18e0a8397e9921c1e60
V2 SIGNAL/PARAMETERS UNCHANGED:  JA — AST-verifierat, 0 parameterändringar
V3 MEMBERSHIP QA:                unresolved 0,36 % / 0,17 % — ej materiell
2014-2019 ELIGIBILITY COVERAGE:  86,0 % (18 825 / 21 896)
2020-2026 ELIGIBILITY COVERAGE:  94,5 % (22 014 / 23 293)
UNRESOLVED MEMBERSHIP:           79 / 40
V2 CONTAMINATED TOP30:           530 (2014-2019) · 112 (2020-2026)
V3 INVALID TOP30:                0
V2 CAGR / MAXDD:                 29,99 % / −14,63 %
V3 CAGR / MAXDD:                 26,61 % / −13,08 %
V2→V3 ΔCAGR / ΔMAXDD:            −3,38 pp / +1,55 pp
PANELS CHANGED:                  79 av 79
MEAN TOP30 NAMES CHANGED:        6,71 (median 6, max 12, Jaccard 0,643)
NEGATIVE LEAKAGE TESTS:          8 av 8 PASS + injicerat test detekterar läckage
FINAL H0 V3 VERDICT:             H0_V3_PIT_MEMBERSHIP_VALIDATED
H0 V1 STATUS:                    SUPERSEDED_BY_V2 (oförändrad)
H0 V2 STATUS:                    FROZEN_BUT_MEMBERSHIP_CONTAMINATED (oförändrad)
H0 V3 STATUS:                    FROZEN — PIT-korrekt baslinje för framtida forskning
FREEZE CREATED:                  JA — H0_V3-kedja med inputmanifest, gate PASS
RESEARCH TESTS EXECUTED:         0
NEXT ALLOWED TASK:               NASDAQ HISTORICAL MASTER FIELD INVENTORY
                                 (ej påbörjad, separat uppdrag)
```

Size-forskning, sektor-, hierarki-, hold/replace- och feature-mining förblir **ej
licensierade**. Size-replikationen kräver egen preregistrering.
