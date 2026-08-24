# PRICE_ADJUSTMENT_REPAIR_V2

Datum: 2026-08-19 · Status: **PRICE_ADJUSTMENT_FOUNDATION_BLOCKED**

Ersätter `RATTELSE_JUSTERINGSBROTT_V1`. Inga forskningstester körda, ingen champion
ändrad, inga gamla frysta filer överskrivna (hash-verifierat).

---

## 1. GENERELL FAKTORREGIM-DETEKTOR

`adjustment_factor = close / adjusted_close`. Kandidat = varje faktorändring över en
**adaptiv** brusgräns `max(5e-4, 10 × median absolut relativ faktorändring)` per
instrument. Den fasta 40 %-grinden från V1 används inte.

| | |
|---|---|
| Instrument skannade | 418 (2 för korta) |
| **Faktorregimkandidater** | **2 784** |
| Instrument med minst en kandidat | 320 |
| Storleksfördelning | <1 % 957 · 1–5 % 1 504 · 5–20 % 175 · 20–100 % 92 · >100 % 56 |
| Persistens | >5 dagar 2 165 · ≤5 dagar 619 |

Det gamla registret med åtta brott fångade alltså **0,3 %** av de faktorregimskiften
som existerar, och missade hela klasser.

---

## 2. CORPORATE-ACTION-AVSTÄMNING

Källor: Börsdatas `dividend_calendar` (1 636 poster) och `stocksplits_from2000`
(429 splittar), samt Skatteverkets Aktiehistorik (5 478 rader). Skatteverkets
notation parsas till teoretisk multiplikator: `N a:b, kurs X` → TERP = (b·P + a·X)/(a+b);
`S a:b` → split; `F a:b` → fondemission. Unitstrukturer lämnas obeäknade.

| Avstämning | Antal |
|---|---|
| EXACTLY_RECONCILED (<0,5 % fel) | 1 631 |
| STRONGLY_RECONCILED (<5 %) | 90 |
| PARTIALLY_RECONCILED | 47 |
| AMBIGUOUS_EVENT_STRUCTURE | 43 |
| NO_MATCH | 973 |

**Positiv kontroll SAS: EXACTLY_RECONCILED, relativt fel −0,0000.**
TERP = (6,12 + 9 × 1,16)/10 = 1,656000; multiplikator 3,695652 mot observerad
3,695652. En verklig corporate action som matematiskt förklarar faktorhoppet
repareras inte bort.

---

## 3. COVID-2020-SVEP

Februari–december 2020, hela svenska universumet: **355** faktorregimskiften.
**13** har en registrerad utdelning på exakt 0,00 SEK på brottdatumet.

Sex av dessa är spuriösa permanenta skiften — de tre kända plus tre som den gamla
detektorn aldrig såg:

| Kod | Datum | Kvot | Persistens | ret(rå) | ret(just) |
|---|---|---|---|---|---|
| PNDX-B | 2020-04-06 | 1,8271 | 762 d | +0,068 | +0,951 |
| VBG-B | 2020-04-29 | 1,5341 | 252 d | −0,022 | +0,501 |
| SSAB-A | 2020-04-02 | 1,4911 | 508 d | −0,032 | +0,443 |
| **OEM-B** | 2020-04-23 | 1,2811 | 251 d | −0,005 | +0,275 |
| **SAAB-B** | 2020-04-02 | 1,1124 | 257 d | −0,001 | +0,112 |
| **PROF-B** | 2020-04-22 | 1,0820 | 508 d | −0,021 | +0,059 |

De övriga sju med nollutdelning (HPOL-B, NTEK-B, MEAB-B, TREL-B, ANOD-B, COOR,
HEXA-B) stämmer mot en verklig utdelning inom ±3 dagar och är giltiga.

**Ytterligare 85 persistenta NO_MATCH-skiften** i samma fönster saknar
betalningsevidens — NCC-B 1,2321, WALL-B 1,2180, NEWA-B 1,1951, SEB-A 1,1119,
SWED-A 1,0831, SKA-B 1,0412 med flera. Alla är bolag som drog in eller sköt upp
2019 års utdelning, men Börsdatas kalender har ingen 0,0-post för dem. **Utan
evidens repareras de inte.**

---

## 4. BEIJ-B — avgjort

Tre faktorskiften 2020, inte två:

| Datum | Kvot | Avstämning |
|---|---|---|
| 2020-04-17 | 1,365907 | NO_MATCH |
| **2020-06-26** | **1,006263** | **EXACTLY_RECONCILED — utdelning 1,75 SEK** |
| 2020-10-02 | 1,234378 | NO_MATCH |

Den **faktiskt betalda** utdelningen på 1,75 SEK har sin egen korrekta justering den
26 juni. April- och oktoberjusteringarna är därmed dubbelräkningar av en utdelning
som redan är korrekt hanterad — precis vid de två ursprungligen planerade
delposterna, varav den andra ströks.

Det motiverar tvåstegs-RESCALE **oberoende av beloppets okända ursprung**:

- **mekanism: känd** — två extra justeringar vid sidan av den enda korrekta
- **exakt felaktig formel: okänd** — ingen testad nivå (3,50 / 1,75 / 0) reproducerar 1,365907 eller 1,234378

Ingen 1,75-baserad teoretisk justering har applicerats.

---

## 5. FLERIE — annan defektklass

Rå `close` antar **tre värden under hela 2020**: 0,0002 (183 dagar), 0,0003 (57),
0,0005 (12) — medan `adjusted_close` varierar kontinuerligt (0,0258 → 0,0277 → 0,0282…).

Rotorsaken är **kvantisering**: efter kraftiga omvända splittar avrundas rå close till
fyra decimaler, vilket ger ±17 % upplösningsfel. Faktorn oscillerar av avrundning, inte
av corporate actions. Samma mönster i IMMNOV (raw 0,6582 / adj 65,8156) och VESTUM
(raw 0,0057 / adj 0,9333).

**Ingen RAW_SOURCE_REPAIR utförs.** Den justerade serien är oskadad, och v2:s regel R1
använder endast `adjusted_close` för avkastning. Rå close markeras som oanvändbar för
dessa instrument. Ingen extern källa har verifierats.

---

## 6. DEFEKTKLASSIFICERING OCH ÅTGÄRD

| Defektklass | Antal | | Åtgärd | Antal |
|---|---|---|---|---|
| VALID_CORPORATE_ACTION | 1 721 | | NO_ACTION | 1 721 |
| RAW_PRICE_ERROR | 601 | | BLOCK | 1 052 |
| UNKNOWN | 403 | | RESCALE | 8 |
| AMBIGUOUS_CORPORATE_ACTION | 39 | | SERIES_SPLIT | 3 |
| TEMPORARY_SOURCE_ERROR | 12 | | | |
| SPURIOUS_ADJUSTMENT_FACTOR | 8 | | | |

RESCALE: PNDX-B, SSAB-A, VBG-B, OEM-B, SAAB-B, PROF-B och BEIJ-B i två steg.
SERIES_SPLIT: BETS-B (2022-05-13), ATORX (2025-01-24), QLINEA (2025-01-13) — längsta
sammanhängande segment behålls enligt byggarens R8-konvention, ingen gissad TERP.

---

## 7. NY PRISVERSION

`validated/prices_adjustment_repair_v2/prices_validated_adjustment_repair_v2.json`

| | |
|---|---|
| Källa | `validated/prices/prices_validated.json`, sha `e3ed38b8…` (orörd) |
| Rader före → efter | 581 115 → **579 762** (−1 353, samtliga från seriedelning) |
| Serier | 420 → 420 |
| SHA256 | `2dff2fd0f3a116bdb4872a63d31a7148d0307269a2ba607ea29a8cc203a128a5` |
| Omskalade rader | 3 331 (adj-värden ändrade, inga rader borttagna) |
| Manifest | `REPAIR_V2_MANIFEST.json` med per-instrument-logg, evidens och rotorsaksklass |

---

## 8. EFTERKONTROLL

Detektorn kördes om på hela universumet, före mot efter: 2 753 → 2 708 faktorskiften.

| Krav | Utfall |
|---|---|
| SAS 2020-09-29 finns kvar | **PASS** |
| BEIJ-B 2020-06-26 (verklig utdelning) finns kvar | **PASS** |
| PNDX-B / SSAB-A / VBG-B borta | **PASS** |
| OEM-B / SAAB-B / PROF-B borta | **PASS** |
| BEIJ-B 2020-04-17 och 2020-10-02 borta | **PASS** |
| BETS-B / ATORX / QLINEA borta (seriedelning) | **PASS** |
| **Inga nya artificiella skarvar** | **PASS — 0 nya** |
| Ingen ±N-dagarsmaskering använd | **PASS** |
| Osorterade serier / dubbletter / ogiltiga värden | 0 / 0 / 0 |
| Datumspann · handelsdagar | 2020-01-02 … 2026-07-24 · 1 651 |

---

## 9. SLUTRAPPORT

| | |
|---|---|
| Faktorregimkandidater totalt | **2 784** |
| VALID_CORPORATE_ACTION | 1 721 |
| SPURIOUS_ADJUSTMENT_FACTOR | 8 |
| AMBIGUOUS_CORPORATE_ACTION | 39 |
| RAW_PRICE_ERROR | 601 |
| TEMPORARY_SOURCE_ERROR | 12 |
| UNKNOWN | 403 |
| RESCALE | 8 |
| SERIES_SPLIT | 3 |
| NO_ACTION | 1 721 |
| BLOCK | 1 052 |
| Ytterligare covid-2020-fall reparerade | **3** (OEM-B, SAAB-B, PROF-B) |
| Ytterligare covid-2020-kandidater utan evidens | **85** |
| Rader före → efter | 581 115 → 579 762 |
| SHA256 | `2dff2fd0f3a116bdb4872a63d31a7148d0307269a2ba607ea29a8cc203a128a5` |

**Status per instrument:** SAS NO_ACTION (giltig, fel 0,00 %) · BEIJ-B RESCALE i två
steg · PNDX-B / SSAB-A / VBG-B RESCALE · OEM-B / SAAB-B / PROF-B RESCALE (nyfunna) ·
BETS-B / ATORX / QLINEA SERIES_SPLIT · FLERIE BLOCK (kvantiseringsfel i rå close,
justerad serie oskadad).

---

## BLOCKERARE

**B1 — 85 covid-2020-kandidater utan betalningsevidens.** NCC-B, WALL-B, NEWA-B,
SEB-A, SWED-A, SKA-B m.fl. har persistenta faktorskiften i mars–juni 2020 utan
matchande corporate action. Börsdatas kalender saknar 0,0-poster för dem. Kräver en
utdelningskälla som skiljer *utbetald* från *föreslagen* utdelning.

**B2 — 403 UNKNOWN-kandidater i 104 instrument.** Domineras av preferensaktier
(NP3-PREF, K2A-PREF) med kvartalsutdelningar som saknas i kalendern, samt 241
kandidater i 39 instrument utan Börsdata-referens alls.

**B3 — rå close är oanvändbar för minst 3 instrument.** FLERIE, IMMNOV och VESTUM har
kvantiserad rå close. Ingen extern källa har verifierats, så defekten är diagnostiserad
men inte åtgärdad.

**B4 — 8 instrument med |justerad avkastning| > 200 %** kvarstår oundersökta i det
reparerade lagret (ABLI, CANTA, MOMENT, MORROW, OP m.fl.).

**B5 — magnituden för de 8 reparerade är fortfarande oförklarad.** Omskalningen är
korrekt eftersom den sanna multiplikatorn bevisligen är 1,0, men *varför* leverantören
valde just 1,8271 / 1,4911 / 1,5341 / 1,2811 / 1,1124 / 1,0820 / 1,3659 / 1,2344 är
okänt. Utan den kunskapen kan man inte utesluta att samma mekanism slagit till på
datum utan registrerad nollutdelning — vilket är exakt vad B1 beskriver.

**B6 — seriedelningen kostar data.** BETS-B, ATORX och QLINEA förlorar 1 353 rader.
Korrekt multiplikator kräver en primärkälla som värderar teckningsoptionerna i
unitstrukturerna.

---

Leveranser: `tools/price_adjustment_repair_v2.py` ·
`validated/prices_adjustment_repair_v2/{prices_validated_adjustment_repair_v2.json,
REPAIR_V2_MANIFEST.json, price_defect_registry_v2.json}`
