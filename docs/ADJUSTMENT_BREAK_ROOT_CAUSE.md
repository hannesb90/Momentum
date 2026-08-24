# ROOT-CAUSE-DIAGNOSTIK — 8 PERMANENTA JUSTERINGSBROTT

Datum: 2026-08-19 · Status: **DIAGNOSTIK KLAR — INGEN DATA ÄNDRAD**

Inga forskningstester körda. Inga canonical- eller frysta filer ändrade.

---

## METOD

`factor(t) = close(t) / adjusted_close(t)` är produkten av alla händelsemultiplikatorer
**strikt efter** t. Därav följer det avgörande testet:

> Om faktorkedjan **efter** brottet stämmer exakt mot kända händelser, motsvarar
> brottets multiplikator **ingen händelse** och är därmed spuriös.

Källor: EODHD-arkivet (1 704 instrument), Börsdatas `dividend_calendar` (1 636 poster)
och `stocksplits_from2000` (429 splittar), samt Skatteverkets Aktiehistorik
(5 478 rader). Metoden kräver aldrig att vi vet *varför* en faktor har ett visst
värde — bara vad den korrekta multiplikatorn borde vara.

---

## HUVUDTABELL

| Instrument | Brott | Faktor före → efter | Obs. kvot | Kedja efter brottet | Corporate action | Utlovat | Faktiskt | Teoretisk kvot | Avstämningsfel | Klass | Konf. | Åtgärd |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **SAS** | 2020-09-29 | 3,6957 → 1,0000 | 3,695652 | **EXAKT** | Nyemission 9:1 à 1,16 | genomförd | genomförd | **3,695652** | **0,00 %** | VERIFIED | HÖG | ingen |
| **PNDX-B** | 2020-04-06 | 2,0094 → 1,0998 | 1,827090 | **EXAKT** | Utdelning indragen | 3,60 kr | **0,00 kr** | 1,000000 | +82,7 % | STRONGLY_SUPPORTED | HÖG | omskalning |
| **SSAB-A** | 2020-04-02 | 2,1150 → 1,4184 | 1,491082 | **EXAKT** (2 ppm) | Utdelning indragen | 1,50 → 0,75 | **0,00 kr** | 1,000000 | +49,1 % | STRONGLY_SUPPORTED | HÖG | omskalning |
| **VBG-B** | 2020-04-29 | 1,7983 → 1,1722 | 1,534062 | **EXAKT** (1 ppm) | Utdelning indragen | 4,50 kr (2019) | **0,00 kr** | 1,000000 | +53,4 % | STRONGLY_SUPPORTED | HÖG | omskalning |
| **BEIJ-B** | 2020-04-17 | 5,7912 → 4,2398 | 1,365907 | residual 1,3366 | Utdelning halverad | 3,50 kr (2×1,75) | 1,75 kr | 1,000000 | +36,6 % | STRONGLY_SUPPORTED | MEDEL-HÖG | omskalning ×2 |
| **BETS-B** | 2022-05-13 | 1,7848 → 1,2623 | 1,413981 | residual 1,1066 | Split+inlösen 2:1, 1,97 kr | 1,97 kr | genomförd | 1,031315 | −27,1 % | PARTIALLY | MEDEL | seriedelning |
| **ATORX** | 2025-01-24 | 0,04213 → 0,00356 | 11,825481 | residual 3,5627 | Nyemission N 37 unit:10 à 0,10 | genomförd | genomförd | 2,899047 | −75,5 % | PARTIALLY | MEDEL | seriedelning |
| **QLINEA** | 2025-01-13 | 0,00757 → 0,00107 | 7,067685 | residual 1,0710 | Nyemission N 77 unit:4 à 0,10 | genomförd | genomförd | 3,623321 | −48,7 % | PARTIALLY | MEDEL | seriedelning |

---

## FYND 1 — SAS är ingen defekt

TERP = (6,12 + 9 × 1,16) / 10 = **1,656000**, vilket är exakt lika med `adjusted_close`
dagen före. Teoretisk multiplikator 6,12 / 1,656 = **3,695652** mot observerad
**3,695652** — relativt fel **0,00 %**.

Justeringen är korrekt utförd enligt standardkonvention. En 9:1-emission till 81 %
rabatt ger ett genuint enormt justeringshopp. Detektorns kriterium
`|ret(adj) − ret(close)| > 0,15` kan inte skilja en **korrekt stor** justering från
en **spuriös**. SAS ska aldrig ha hamnat i rättelsen.

**Åtgärd: ingen dataändring.** Att ta bort en korrekt TERP-justering skulle införa
ett fel, inte rätta ett.

---

## FYND 2 — systemfelet i april 2020 är bekräftat

Mönstret **föreslagen utdelning → justering applicerad → förslaget ändrat/indraget →
justeringen aldrig reverserad** är verifierat, inte bara hypotetiskt:

1. Börsdata registrerar ett ex-datum med belopp **0,0 SEK** på exakt brottdatumet för
   PNDX-B (2020-04-06), SSAB-A (2020-04-02) och VBG-B (2020-04-29).
2. Faktorkedjan **efter** brottet stämmer exakt mot kända utdelningar 2021–2026:
   PNDX-B 1,099764 mot 1,099764 (exakt), SSAB-A 1,418416 mot 1,418419 (2 ppm),
   VBG-B 1,172234 mot 1,172233 (1 ppm).
3. Alltså: multiplikatorn vid brottet motsvarar **ingen händelse**. Den korrekta
   multiplikatorn för en utdelning på 0 kr är 1,0.

Kontrollen mot normala år stärker slutsatsen. SSAB-A:s övriga utdelningsjusteringar
ligger på 1,053–1,125 (2001, 2003, 2009, 2022, 2023, 2024). Årets 1,491 är en
storleksordning fel. VBG-B har bara **två** faktorbyten över 5 % i hela sin 33-åriga
historik: splitten 2006 (exakt 4,000002) och detta.

### BEIJ-B: två justeringar, en utdelning

BEIJ-B har **två** oförklarade faktorbyten: 2020-04-17 (1,365907) och **2020-10-02**
(1,234378). Det motsvarar exakt de två planerade delutdelningarna om 1,75 kr i april
och oktober, varav den andra ströks. Börsdata visar att endast en post betalades —
1,75 kr den 2020-06-26. Alla övriga stora faktorbyten i BEIJ-B:s serie är exakta
splittar (2,000 / 2,000 / 2,000 / 3,000).

### Magnituden stämmer inte

Ingen testad utdelningsnivå reproducerar de observerade kvoterna, vare sig mot rå
close eller mot adjusted close — bästa träff ligger 23–74 % fel. Mekanismen är
verifierad; **beloppets ursprung är det inte**. Därför STRONGLY_SUPPORTED, inte
VERIFIED.

---

## FYND 3 — tre ytterligare fall som detektorn aldrig såg

Systemsökning över hela v2-universumet, februari–december 2020: **86** faktorbyten
över 5 %, varav **74** utan utdelning eller split inom fem dagar, varav **6** med
exakt nollutdelning registrerad på datumet.

De tre kända är PNDX-B, SSAB-A och VBG-B. De tre nya:

| Kod | Datum | Kvot | ret(adj) |
|---|---|---|---|
| OEM-B | 2020-04-23 | 1,2811 | +0,275 |
| SAAB-B | 2020-04-02 | 1,1124 | +0,112 |
| PROF-B | 2020-04-22 | 1,0820 | +0,059 |

Alla tre har ret(adj) **under 40 %** och passerade därför aldrig detektorns
urvalsgrind. Samma defekt, mindre magnitud. Det befintliga brottsregistret är
alltså inte uttömmande.

---

## FYND 4 — en annan defektklass: FLERIE

FLERIE har **45** faktorbyten över 5 % under 2020, med `ret_close` som bara antar
värdena −0,40, −0,3333, 0, +0,50 och +0,6667 — priset alternerar mellan två nivåer.
Det är ingen corporate action utan ett **råprisfel** (`RAW_PRICE_ERROR`). FLERIE
fångades redan av byggarens R7-slutning för 2024-06-19…2024-07-31, men 2020-perioden
är oadresserad.

---

## REKOMMENDERAD ÅTGÄRD PER INSTRUMENT

Generell ±N-dagarsborttagning är falsifierad för permanenta faktorbyten och används inte.

| Instrument | Metod | Varför ekonomiskt korrekt |
|---|---|---|
| **SAS** | ingen ändring | Justeringen är korrekt. Undanta verifierade nyemissioner från detektorn i stället. |
| **PNDX-B** | omskalning: `adj × 1,827090` för datum < 2020-04-06 | Sann multiplikator är bevisligen 1,0 (utdelning 0 kr). Kräver inte att vi vet varför faktorn har sitt värde. |
| **SSAB-A** | omskalning: `adj × 1,491082` för datum < 2020-04-02 | d:o |
| **VBG-B** | omskalning: `adj × 1,534062` för datum < 2020-04-29 | d:o |
| **BEIJ-B** | omskalning i två steg: först `×1,234378` före 2020-10-02, sedan `×1,365907` före 2020-04-17 | Två justeringar men en betald utdelning. Verifiera därefter mot 1,75 kr den 2020-06-26. |
| **BETS-B** | **seriedelning (R8)** vid 2022-05-13, alternativt trunkering | En verklig händelse inträffade, så hela faktorn får inte tas bort. Korrekt multiplikator går inte att fastställa; seriedelning är då den enda åtgärd som inte inför ett nytt fel. Brottdatumet ligger dessutom fem dagar före Skatteverkets ex-datum. |
| **ATORX** | **seriedelning (R8)** vid 2025-01-24 | Verklig, kraftigt utspädande emission. TERP är tvetydig eftersom unitstrukturen innehåller två teckningsoptionsserier vars värde inte ingår i formeln. |
| **QLINEA** | **seriedelning (R8)** vid 2025-01-13 | Samma skäl. |

---

## SLUTRAPPORT

1. **ROOT_CAUSE_VERIFIED: 1 av 8** (SAS, avstämningsfel 0,00 %).
2. **Utdelningsrelaterade: 4** — BEIJ-B, PNDX-B, SSAB-A, VBG-B.
3. **Emission/split/inlösen: 4** — SAS, ATORX, QLINEA, BETS-B.
4. **ROOT_CAUSE_UNKNOWN: 0.** Fyra är STRONGLY_SUPPORTED, tre PARTIALLY_EXPLAINED.
5. **April 2020 visar ett generellt reversal-fel: JA**, bekräftat på tre oberoende sätt
   (nollutdelning på exakt datum, exakt kedjeavstämning efter brottet, avvikande
   magnitud mot alla andra års justeringar). Tre ytterligare kandidater hittade.
6. **Åtgärd per instrument:** se tabellen ovan — 1 ingen ändring, 4 omskalning,
   3 seriedelning.
7. **Måste RATTELSE_JUSTERINGSBROTT_V1 ersättas? JA.**
   R4 är fel behandling för samtliga åtta. Tre skäl:
   - den kan per konstruktion inte ta bort en permanent faktorändring
   - den behandlar SAS, där ingen defekt finns
   - dess källregister är inte uttömmande — minst tre fall till finns i samma fönster

   Ersättningen behöver **två** metoder, inte en: **omskalning** där multiplikatorn
   bevisligen ska vara 1,0, och **seriedelning (R8)** där en verklig händelse
   inträffade men rätt multiplikator inte kan fastställas. Plus en detektor som
   undantar verifierade corporate actions i stället för att flagga dem.

---

Maskinläsbar diagnostik: `research_k/adjustment_break_rootcause/adjustment_break_rootcause.json`
