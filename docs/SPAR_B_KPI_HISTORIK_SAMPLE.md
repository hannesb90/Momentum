# Spår B: sample-validering av Börsdata KPI-historik (EBITDA/Capex/återköp)

Datum: 2026-08-08. Ingen modellträning. Detta dokument täcker enbart
sample-validering enligt mandatet, INNAN fullskalig hämtning.

## 1. Endpoint

`GET /v1/instruments/{insId}/kpis/{kpiId}/{reportType}/{priceType}/history`

- `reportType` ∈ {`year`, `quarter`, `r12`} — verifierat, andra värden ger HTTP 400.
- `priceType` = `mean` — enda testade värde som fungerar för rena fundamentafält
  (`1`, `high`, `low`, `last` gav samtliga HTTP 400 för EBITDA/Capex).
- Svarsformat: `{"kpiId", "reportTime", "priceValue", "values": [{"y","p","v"}, ...]}`.
- Ogiltigt/onåbart `insId` ger HTTP 200 med `"values": []` (inte 404) — bekräftat
  med `insId=-1`.

## 2. KPI-ID:n och definitioner (Börsdatas egen metadata)

| kpiId | nameSv | nameEn | format | Status |
|---|---|---|---|---|
| 54 | EBITDA | EBITDA | MCURR | **Fungerar** via `.../history` |
| 64 | Capex | Capex | MCURR | **Fungerar** via `.../history` |
| 213 | Återköp Mkr 1 månad | Buyback Million 1 month | (inget) | **Fungerar INTE** via `.../history` (HTTP 400, alla reportType) |
| 214 | Återköp Mkr 3 månader | Buyback Million 3 months | (inget) | Samma som ovan |
| 215 | Återköp Mkr 1 år | Buyback Million 1 year | (inget) | Samma som ovan |

**Återköp kräver en ANNAN endpoint:** `GET /v1/holdings/buyback?instList=...`
(hittad via Börsdatas swagger-spec). Ger transaktionsnivå-data, inte
KPI-aggregat:

```json
{"insId": 3, "values": [
  {"change": 1940000, "changeProc": 0.094, "price": 32.124, "currency": "CHF",
   "shares": 63981245, "sharesProc": 3.116, "date": "2021-11-17T00:00:00"}, ...
]}
```

Detta är BÄTTRE för PIT-syften än ett fiskalperiod-baserat KPI: varje rad har
ett explicit `date`-fält (troligen transaktions-/rapporteringsdatum, se §6 om
embargo-hantering). KPI 213–215 (de kalenderbaserade "1 månad/3 månader/1 år"-
aggregaten) hör sannolikt till Börsdatas screener-verktyg och är inte avsedda
att hämtas historiskt via denna endpoint — de behövs inte när
transaktionsdata finns direkt.

## 3. Sample (4 av 5 begärda kategorier)

| kategori | bolag | insId | resultat |
|---|---|---|---|
| stort aktivt | ABB Ltd | 3 | OK, se §8 om avvikelse |
| litet aktivt | Image Systems AB | 108 | OK |
| avnoterat | Ledstiernan AB / EMPIR-B | 147 | OK, se §9 om Spår A-fynd |
| brutet räkenskapsår | Lagercrantz | 124 | OK |
| valuta-/redovisningsförändring | — | — | **Inget sådant bolag hittades** — sökt i samtliga 359 redan hämtade Spår B-instrument (`reports`-data), 0 bolag med mer än en valuta över sin rapportserie. Dokumenterat som empiriskt frånvarande i urvalet, inte utelämnat. |

## 4. PIT-mappning — verifierad, entydig

`(insId, y, p)` från KPI-historiken mappar **exakt** mot `(insId, year, period)`
i den redan validerade `reports`-datan (Spår B Track A), som har `report_Date`.
Verifierat för ABB:

```
year-KPI:  {y:2025, p:5, v:6860.0}
year-rapport: {year:2025, period:5, report_Date:'2026-01-29'}
quarter-rapport Q4 2025: {year:2025, period:4, report_Date:'2026-01-29'}   <- identiskt datum
r12-KPI:   {y:2025, p:4, v:6860.0}                                         <- identiskt värde
```

Regel: `year`-typ med `p=5` och `r12`-typ med `p=4` för samma år representerar
SAMMA underliggande observation (helår) och blir kända samtidigt — vid Q4-/
årsrapportens `report_Date`. `quarter`-typ `(y,p)` mappar direkt mot
kvartalsrapportens egna `(year,period)` → `report_Date`.

**PIT-regel att implementera:** ett KPI-värde är tillgängligt i panelen
tidigast `report_Date` (från motsvarande rapportpost) för den period värdet
avser — aldrig kalenderårsslut, periodslut eller hämtningsdatum. Ingen
approximation används; `report_Date` finns alltid för matchande period i
redan hämtad `reports`-data.

## 5. Fältet `p` — empiriskt verifierat, INTE kodat som antagande förrän nu

Testat över 4 bolag (stort/litet/avnoterat/brutet räkenskapsår) och 6–10 år
per bolag:

- **`reportType=quarter`:** `p` = kvartalsnummer 1–4. Matchar exakt
  `period`-fältet i `reports/quarter`.
- **`reportType=r12`:** `p` = kvartalsnumret rullande-12-månader slutar vid.
  `r12(y,p=4) == year(y,p=5)` exakt, verifierat för samtliga fullständiga år
  i samplet (ABB, Lagercrantz, Image Systems, Ledstiernan).
- **`reportType=year`:** `p=5` för VARJE fullständigt rapporterat år, i
  SAMTLIGA fyra bolag och samtliga historiska år i samplet (2017–2025).
  `p<5` förekommer ENDAST för innevarande, ännu ej fullständiga
  räkenskapsår, och matchar då exakt antalet hittills rapporterade kvartal
  (t.ex. Image Systems `{y:2026,p:2}` — bara Q1+Q2 2026 rapporterade).
  Lagercrantz (brutet räkenskapsår) bekräftar att `y` följer BOLAGETS EGET
  fiskalår (visar `y:2027,p:1` redan nu) — INTE kalenderår.
- **Slutsats:** `p=5` = fullständigt räkenskapsår är verifierat generellt
  (4 bolag, olika storlek/status/räkenskapsårstyp), inte ett antagande från
  ett enda bolag. `p` är för övrigt SAMMA konvention som `reports`-endpointens
  egna `period`-fält (1–4=kvartal, 5=helår) — inte en separat, egen
  KPI-specifik kod.

## 6. Restatement-/revisionsrisk — INTE verifierbar, dokumenterad begränsning

Svarsformatet `{y,p,v}` innehåller INGET versions-, revisions- eller
hämtningsdatum. Det går alltså inte att direkt bevisa om ett historiskt värde
är det UR SPRUNGLIGEN rapporterade eller ett senare omräknat/korrigerat
värde, eftersom det skulle kräva en verklig historisk ögonblicksbild
(point-in-time-arkiv) från den tidpunkt värdet ursprungligen publicerades —
något som inte finns tillgängligt.

**Detta är samma begränsning som redan gäller (och accepterades) för
`reports`-endpointen**, som redan är godkänd och i produktion i Spår B Track
A utan att revisionsspårning finns där heller. Ingen ny, sämre risk
introduceras — men risken kvarstår och dokumenteras explicit:
**om Börsdata retroaktivt korrigerar en historisk EBITDA-/Capex-siffra, skulle
denna panel visa det KORRIGERADE värdet under det GAMLA datumet, vilket är en
teoretisk (ej testbar) läckagerisk.** Rekommendation: dokumentera i
manifestet som känd, oåtgärdad PIT-begränsning (samma status som
`reports`-datans motsvarande begränsning), inte som blockerande.

## 7. Buyback: nolla vs. saknas

`/v1/holdings/buyback` gav 0 träffar för Image Systems (insId 108) och
flera träffar för övriga. En tom lista från en LYCKAD (HTTP 200,
`error: null`) anropsrespons tolkas som "verifierat inga återköp under den
period Börsdata har transaktionsdata för" — SKILT från ett bolag som saknar
Börsdata-täckning helt (då matchar insId inte alls, se `_matchning.json`).
Denna åtskillnad måste bevaras explicit i PIT-/normaliseringslagret (punkt 12
i mandatet) — implementeras i fullskalefasen, inte testad uttömmande än.

## 8. Upptäckt problem — EBITDA vs. EBIT-rimlighet (ABB, ej blockerande)

Ekonomisk identitetskontroll (EBITDA ≥ EBIT, eftersom EBITDA=EBIT+avskrivningar≥EBIT):

| bolag | resultat |
|---|---|
| Lagercrantz (124) | **Godkänd** — EBITDA konsekvent 30–45 % högre än `operating_Income` för samtliga 6 testade år, ekonomiskt rimligt. |
| ABB Ltd (3) | **AVVIKELSE** — `operating_Income` (55 794 för 2025) är ~8× STÖRRE än KPI-EBITDA (6 860), vilket är omöjligt (EBITDA kan aldrig vara mindre än EBIT). Dessutom `gross_Income` (125 854) större än rimlig total omsättning för bolaget, och `net_sales` är `null`. |

**Klassificering:** avvikelsen ligger i den REDAN GODKÄNDA `reports`-datan
(operating_Income/gross_Income), inte i den nya KPI-historik-datan — KPI-
historikens EGEN interna konsistens (year(p=5)==r12(p=4)) höll perfekt även
för ABB. Sannolik orsak: ABB rapporterar i USD och är dubbelnoterat/utländskt
(schweiziskt bolag); en valutakonverterings- eller skalningsavvikelse i
`reports`-endpointen för denna typ av utländsk emittent är den mest
sannolika förklaringen, men är INTE verifierad här. **Inte blockerande för
KPI-historik-hämtningen**, men flaggas för särskild granskning vid
fullskale-QA (identitetskontrollerna i punkt 8 i mandatet) — reparera INTE
tyst, klassificera per bolag.

## 9. Upptäckt (ej åtgärdat) Spår A-fynd — Ledstiernan/EMPIR-B

Instrument_master anger `Ledstiernan AB` avnoterad 2010-05-14 med EODHD-kod
`EMPIR-B`. Men `/v1/holdings/buyback` visar en ÅTERKÖPSTRANSAKTION daterad
2020-12-15 för samma `insId` (147) — ett bolag kan inte göra återköp tio år
efter att det upphörde att vara noterat. Detta tyder på samma mönster som de
redan åtgärdade namnbytes-/redomicilieringsfallen (bolaget bytte namn till
"Empir Group" och fortsatte handlas, men avnoteringshändelsen för det GAMLA
namnet "Ledstiernan" kopplades ändå till den fortsatt aktiva koden).

**Åtgärdas INTE nu** — i enlighet med instruktionen rörs inte Spår A utan att
ett konkret fel först reproducerats och dokumenterats. Detta är den
dokumentationen; en eventuell fix hanteras som en separat, uttrycklig
Spår A-uppgift om/när den prioriteras.

**Uppdatering vid fullskalehämtningen:** roten till fyndet är nu identifierad
precist. Spår A-universumet innehåller TVÅ separata koder med SAMMA ISIN
(SE0010769182) och samma Börsdata-insId (147): `EMPIR-B` ("Ledstiernan AB")
och `SAFETY-B` ("mySafety Group AB") — sannolikt samma instrument som bytt
namn flera gånger (Ledstiernan → Empir Group → mySafety Group, eller
liknande kedja) utan att kollapsas till en identitet i `instrument_master`.
Praktisk konsekvens för KPI-hämtningen: `insId→kod`-mappningen kunde bara
tilldela datan till EN kod (SAFETY-B fick samtliga 396 rader, EMPIR-B fick 0)
— en täckningslucka för EMPIR-B, inte korrupt data. Fortsatt INTE åtgärdat i
Spår A; dokumenterat här som skäl till varför EMPIR-B saknar KPI-täckning.

## 10. Sammanfattning — blockerande problem?

**Inga blockerande problem hittade.** Full hämtning kan köras enligt
mandatets punkt 10 (RAW → normalisering → PIT-mappning → QA, orört RAW).
Kvarstående, ej blockerande punkter att hantera under fullskale-QA:
- §6 restatement-risk: dokumentera som känd begränsning i manifestet.
- §8 ABB-avvikelsen: klassificera per bolag under identitetskontrollerna,
  exkludera inte automatiskt.
- §9 Ledstiernan/EMPIR-B: flagga som möjligt kvarstående Spår A-fel, rör inte
  Spår A nu.
- §12 (mandatet) nolla-vs-saknas för återköp: implementeras explicit i
  normaliseringslagret.
