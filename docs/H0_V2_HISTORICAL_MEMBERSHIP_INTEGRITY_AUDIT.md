# H0 V2 — HISTORICAL UNIVERSE / MEMBERSHIP INTEGRITY AUDIT

Datum 2026-08-18 · **Audit. H0 V2 är oförändrad. Noll forskningstester körda.**
Artefakter: `research_k/h0_membership_audit/` med SHA256-manifest.

**Dom: `H0_V2_MEMBERSHIP_CONTAMINATED_MATERIAL`** (klassificering C).

---

## 1. Pre-flight och H0 V2:s frysningskedja

Gate **PASS**. H0 V2:s kedja verifierad: preregistreringshash `23cd3cde…` matchar,
**samtliga 7 låsta indatafiler OK**, resultatartefakten refererar rätt prereg-hash
med `las_verifierat: true`, CAGR 0,2999 / MaxDD −0,1463.

**Frysningen är alltså intakt.** Det som granskas här är inte frysningen utan vad
som ligger inuti den.

---

## 2–4. Vad H0 V2 faktiskt gör — spårat i kod, inte i dokumentation

`tools/h1419_motor.py`, rad 65:

```python
rows = [{"kod": k, "m12": ..., "m18": ...} for k in SERIE if handlas(k, dt)]
```

och `handlas()`, rad 42–47:

```python
def handlas(k, dt):
    i = _idx(k, dt)
    if i is None:
        return False
    ds, _ = SERIE[k]
    return int((np.datetime64(dt) - ds[i]) / np.timedelta64(1, "D")) <= 30
```

**Eligibility = "det finns ett pris inom 30 dagar före panelen". Ingenting annat.**

Svar på de ställda frågorna, med kodbelägg:

| | Fråga | Svar |
|---|---|---|
| A | Hur bestäms eligible vid panel t? | `handlas()` — enbart prisnärvaro |
| B | Finns explicit `listing_date`? | **Nej.** Prisfilen har fälten `d` och `adj`, inget annat |
| C | Finns explicit `delisting_date`? | **Nej** i motorns eligibility |
| D | Används ett senare universum bakåt? | **Ja.** 222 av 290 rader har basis `DAGENS_MAIN_MARKET_ISIN_BAKATPROJICERAD` |
| E | Kan pris före Nasdaq-listing skapa eligibility? | **Ja** — det är precis mekanismen |
| F | Kan instrument komma in före faktisk Main Market-listing? | **Ja**, bekräftat empiriskt |
| G | Kan instrument utanför STO Main Market komma in? | **Ja** — NOKIA, 79 observationer |
| H | Ticker-/ISIN-byte? | Hanteras inte; ISIN är bakåtprojicerad |
| I | Relisting/code reuse? | Hanteras inte |
| J | Byte av handelsplats? | Hanteras inte |

### Medlemskapsfilen är dekoration

`membership_h1419_v2.json` är **låst indata i preregistreringen och hashad** — vilket
ger intrycket att medlemskap kontrolleras. Sökning över hela `tools/`:

* `h1419_forregistrering_v2.py` — **hashar** filen som låst indata
* `k1_material_validation.py` — mitt eget granskningsskript

**H0-motorn läser den aldrig.** Och även om den gjorde det: `member_from` är satt för
**0 av 290 rader**, `membership_verified` är `False` för samtliga.

---

## 5–6. Klassificering av varje panelobservation

Nasdaq-månadsserien används här **enbart** för presence/listing/delisting/identitet.
**Ingen segmentinformation ingår i denna audit.**

### Top-30-platser

| | 2014-2019 | 2020-2026 |
|---|---:|---:|
| VALID_MEMBER | 1 840 | 1 846 |
| **PRE_LISTING** | **520** | **112** |
| **NOT_STO_MAIN_MARKET** | **10** | 0 |
| CODE_REUSE_AMBIGUITY | 0 | 22 |
| **Kontaminerade totalt** | **530 av 2 370 = 22,4 %** | **112 av 1 980 = 5,7 %** |

### Giltigt medlemskap per panel

| | mean | median | **min** | p10 | p25 |
|---|---:|---:|---:|---:|---:|
| 2014-2019 | 77,6 % | 80,0 % | **60,0 %** | 66,7 % | 70,0 % |
| 2020-2026 | 93,2 % | 93,3 % | **76,7 %** | 86,7 % | 90,0 % |

---

## 7. Positiva kontroller

| Ticker | H0 rankar från | Nasdaq första observation | Top-30-obs | Klassificering |
|---|---|---|---:|---|
| **STAR-B** | 2014-01 | **2017-10** | 41 | 50 PRE_LISTING, 95 VALID |
| **HTRO** | 2014-01 | **2015-12** | 59 | 27 PRE_LISTING, 118 VALID |
| **STEF-B** | 2014-01 | **2018-04** | 18 | 57 PRE_LISTING, 88 VALID |
| **NOKIA** | 2014-01 | **finns inte** | 10 | 79 NOT_STO_MAIN_MARKET |

STEF-B rankas alltså **fyra år** innan bolaget fanns på Nasdaq Stockholm Main
Market, och tog 18 topp-30-platser under den tiden. NOKIA förekommer aldrig i STO
Main Market-segmentet men tog 10 topp-30-platser.

---

## 8. Root cause

**Nivå B — membership construction.** Reproducerbar kedja:

| Steg | Artefakt | Fynd |
|---|---|---|
| Source universe | `prices_h1419_universum_v2.json` | 290 tickers; fält per prisrad är **endast** `d` och `adj` |
| Membership | `membership_h1419_v2.json` | `member_from` satt för **0 av 290**; `membership_verified: False` |
| Consumer | `tools/h1419_motor.py` | rad 65 använder `handlas()` — ingen medlemskapskontroll |
| Läses aldrig | grep över `tools/` | endast hashare och granskningsskript läser membership |
| Downstream | `h1419_exakt_h0_RESULTAT_V2.json` | beräknat på det prisbaserade universumet |

**Mekanismen:** prisfilen innehåller kurshistorik som sträcker sig före
instrumentets faktiska Main Market-notering — typiskt First North-perioden. Eftersom
eligibility bara kräver ett färskt pris blir instrumentet rankbart **innan det var
investerbart**.

---

## 9. Når det faktisk ranking och portfölj?

**Ja, fullt ut.** I H0 V2 byggs rankningen direkt av de eligible, så en kontaminerad
rad når alltid rankningen.

| | 2014-2019 | 2020-2026 |
|---|---:|---:|
| CONTAMINATED_SOURCE_ROWS | 4 806 | 1 264 |
| CONTAMINATED_ELIGIBLE_ROWS | 4 806 | 1 264 |
| CONTAMINATED_RANKED_ROWS | 4 806 | 1 264 |
| **CONTAMINATED_TOP30_ROWS** | **530** | **112** |
| **CONTAMINATED_PORTFOLIO_EXPOSURES** | **530** | **112** |

---

## 10–11. Counterfactual — AUDIT ONLY

`H0_V2_MEMBERSHIP_CORRECTED_AUDIT_ONLY`. Samma signal, parametrar, rebalansdatum,
viktning och kostnader. **Enda ändringen är eligibility.** Ingen parameter retunad,
ingen size-information använd. **Detta är inte V3 och ersätter inte H0 V2.**

Båda armarna körs i samma harness så att differensen isolerar enbart eligibility;
absoluta nivåer skiljer sig därför från den frysta motorns egna tal.

| 2014-2019 | CAGR | Vol | MaxDD | Sharpe |
|---|---:|---:|---:|---:|
| Fryst eligibility | +31,56 % | 17,22 % | −19,73 % | 1,703 |
| PIT-medlemskap | +28,92 % | 16,80 % | −20,13 % | 1,587 |
| **Δ** | **−2,64 pp** | −0,42 pp | −0,40 pp | −0,116 |

| 2020-2026 | CAGR | Vol | MaxDD | Sharpe |
|---|---:|---:|---:|---:|
| Fryst eligibility | +7,20 % | 21,71 % | −33,50 % | 0,228 |
| PIT-medlemskap | +6,79 % | 21,03 % | −30,59 % | 0,216 |
| **Δ** | **−0,41 pp** | −0,68 pp | **+2,91 pp** | −0,012 |

### Portföljpåverkan

| | 2014-2019 | 2020-2026 |
|---|---:|---:|
| **Paneler där Top-30 ändras** | **79 av 79 (100 %)** | 51 av 66 (77 %) |
| Medelantal ändrade namn | **13,29 av 30** | 3,42 av 30 |
| Max ändrade namn | **24 av 30** | 14 av 30 |
| Jaccard-överlapp | **0,645** | 0,896 |
| Avkastningskorrelation | 0,960 | 0,993 |

**Varje enskild panel i det tidiga fönstret får en annan portfölj**, och i snitt
skiljer sig 13 av 30 innehav. Det är inte en marginell justering.

---

## 12. Hederlighetskontroll

Korrigeringen **sänker** CAGR i båda fönstren. Domen bygger inte på riktningen.

Enda frågan är om H0 V2:s historiska investerbara universum var PIT-korrekt. **Det
var det inte** — och det hade varit ett data- och provenancefel även om
korrigeringen höjt avkastningen.

---

## 13–14. Dom och konsekvens

### **C — `H0_V2_MEMBERSHIP_CONTAMINATED_MATERIAL`**

H0 V2 är **oförändrad**. Dess frysningskedja är fortsatt verifierad — artefakten är
vad den är. Men dess status skiljs nu:

> **`FROZEN_BUT_MEMBERSHIP_CONTAMINATED`**
> Ett historiskt fryst experiment, **inte** en fortsatt giltig champion.

Inskrivet i `freeze_chains.json` och `research_registry.json` med
`previous_claim` / `contradicting_evidence` / `resulting_status` bevarade.

### Förslag: H0 V3 PIT MEMBERSHIP RECONSTRUCTION — **körs inte här**

V3 ska använda **samma H0-signal, samma parametrar, samma modellarkitektur**, och
enbart byta ut eligibility mot Nasdaq PIT Main Market-medlemskap med korrekt
delisting och identitetskontinuitet.

**V3 är en datakorrigering, inte en modellförbättring.** Ingen parameteroptimering.
Preregistrering krävs innan körning.

---

## 15. Konsekvens för size-spåret

**Size-replikationen är blockerad** tills H0 V3 är byggd och validerad.

Att applicera en korrekt PIT-size på ett kandidatuniversum där 22,4 % av
topp-30-platserna i det tidiga fönstret inte var investerbara skulle producera ett
svar som inte går att tolka — oavsett hur bra size-datan är.

PIT Size Foundation förblir **VALID**. `nasdaq_market_cap_segment_pit` förblir
`ALLOWED_FOR_POPULATION_STRATIFICATION_ONLY`. Inga size-resultat återupprättas.

---

```
REPOSITORY INTEGRITY:              PASS
H0 V2 FREEZE PROVENANCE:           VERIFIERAD (prereg 23cd3cde…, 7/7 indata OK)
NASDAQ PIT MEMBERSHIP SOURCE:      201 månader 2009-08…2026-07, 707 instrument
                                   (endast STO + Stock; ingen segmentanvändning)
H0 PANEL OBSERVATIONS:             45 189 rankade (21 896 + 23 293)
VALID MEMBERSHIP (top-30):         1 840 / 2 370 · 1 846 / 1 980
PRE-LISTING (top-30):              520 · 112
POST-DELISTING (top-30):           0 · 0
NOT STO MAIN MARKET (top-30):      10 · 0
IDENTITY / CODE REUSE (top-30):    0 · 22
UNRESOLVED:                        0 · 0
MIN PANEL VALID MEMBERSHIP:        60,0 % (2014-2019) · 76,7 % (2020-2026)
CONTAMINATED SOURCE ROWS:          4 806 · 1 264
CONTAMINATED ELIGIBLE ROWS:        4 806 · 1 264
CONTAMINATED RANKED ROWS:          4 806 · 1 264
CONTAMINATED TOP30 ROWS:           530 · 112
CONTAMINATED PORTFOLIO EXPOSURES:  530 · 112
COUNTERFACTUAL AUDIT RUN:          YES

H0 V2 CAGR:                        +31,56 % (14-19) · +7,20 % (20-26)
AUDIT-ONLY CAGR:                   +28,92 % (14-19) · +6,79 % (20-26)
H0 V2 MAXDD:                       −19,73 % · −33,50 %
AUDIT-ONLY MAXDD:                  −20,13 % · −30,59 %
TOP30 PANELS CHANGED:              79 av 79 · 51 av 66
MEAN TOP30 CONSTITUENTS CHANGED:   13,29 · 3,42

FINAL MEMBERSHIP VERDICT:          H0_V2_MEMBERSHIP_CONTAMINATED_MATERIAL
H0 V2 STATUS:                      FROZEN_BUT_MEMBERSHIP_CONTAMINATED (oförändrad artefakt)
PIT SIZE FOUNDATION:               VALID
SIZE REPLICATION LICENSED:         NO
H0 V3 PREREGISTRATION REQUIRED:    YES
RESEARCH TESTS EXECUTED:           0
```
