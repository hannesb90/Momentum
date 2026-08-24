# Spår C: feature- och panelarkitektur för dataset_v1.0

Datum: 2026-08-08. **Ingen modellträning, inget featureurval baserat på framtida avkastning.**
Byggd från noll — ingen legacy-kod, legacy-cache eller legacy-config importerad; endast
Spår A och Spår B:s frysta VALIDATED-lager använda som källa.
Verktyg: `tools/spar_c_target.py`, `tools/spar_c_features_core.py`,
`tools/spar_c_features_fundamenta.py`, `tools/spar_c_qa.py`, `tools/spar_c_freeze.py`.
Artefakter: `panels/{target_table,core_panel,core_fundamenta_panel}.json`,
`docs/probes/{target_manifest,feature_registry,spar_c_qa}.json`,
`validated/manifest_sparC.json`.

---

## 0. Sammanfattning

| leverabel | status |
|---|---|
| Target (preregistrerad, byggd separat från features) | **klar** — 28 539 rader, 404 instrument |
| Feature registry (26 fält, formel+hypotes+lookback dokumenterat) | **klar** |
| CORE-panel (Spår A enbart) | **klar, survivorship-säker** |
| CORE+FUNDAMENTA-panel (+ Spår B, med provenance) | **klar, INTE survivorship-säker för fundamenta** |
| PIT-/läckage-QA | **klar — samtliga strukturella kontroller passerade** |
| Coverage-QA per år/instrument/fält | **klar** |
| Fältklassificering | **18 GODKÄNDA, 6 KRÄVER ÅTGÄRD, 0 UTESLUTNA, 2 provenance** |
| Manifest + SHA256 för båda panelerna | **klar, `validated/manifest_sparC.json`** |

**En bugg hittades och rättades under bygget** (redovisas i §4 — täckningskontrollen fångade
den, inte PIT-kontrollen, vilket är värt att notera för framtida arbete).

---

## 1. Target — preregistrerad, byggd separat från features

`tools/spar_c_target.py`, källa **enbart** `validated/prices/prices_validated.json`.

| parameter | värde | motiv |
|---|---|---|
| `target_horizon_weeks` | **52** | matchar den redan uttryckligen efterfrågade frågeställningen för modellracet ("52v-target") — en preregistrering av ett redan ställt krav, inte ett nytt påhitt |
| `embargo_weeks` | **52** | minimiregeln embargo ≥ horisont: ingen testrads etikettfönster får överlappa en träningsrads |
| `rebalance_weeks` | **4** | panelens observationsfrekvens (en rad per instrument var 4:e vecka). Halverar etikettöverlappet från 52× (veckovis) till 13× utan att göra panelen ohanterligt gles |
| universumfilter | Nasdaq Stockholm, PIT-dynamiskt via Spår A:s serie (start=IPO/2020-01-01, slut=avnotering/2026-07-24) | ärver Spår A:s låsta universumdefinition |

`target(instrument, T) = adj[T+52v] / adj[T] − 1`, med `adj` = Spår A:s redan
split-/utdelningsjusterade serie. **Ingen** ny justering görs här.

**Höger-censurering, inte saknad data:** rader vars 52-veckorsfönster sträcker sig bortom
instrumentets sista VALIDATED-datum får `target = null`. Det är en äkta, förväntad egenskap
hos ett point-in-time-dataset — de senaste ≈52 veckorna av panelen kan per definition inte ha
ett upplöst utfall ännu.

| utfall | antal | andel |
|---|---|---|
| target beräknad | 23 411 | 82,0 % |
| höger-censurerad | 5 128 | 18,0 % |
| saknar prispunkt exakt vid target-datum | 0 | 0 % |

`target_table.json` sha256: `8a0b44e7c9b584f709372801f19ef8dc7e68f313f03f4c78bef1ed9af2852fce`

---

## 2. Feature registry — 26 fält, samtliga dokumenterade

`docs/probes/feature_registry.json`. Varje fält har: källa (exakt vilket Spår A/B-fält),
formel, ekonomisk hypotes, lookback, missing-semantik och slutlig klassificering.

### CORE (13 fält, enbart Spår A: `adj`, `v`)

| fält | formel | hypotes | lookback |
|---|---|---|---|
| `mom_4w`…`mom_52w`, `mom_12_1` | prisförändring över N veckor | momentum, olika horisonter | 4–52v |
| `vol_13w`, `vol_52w` | std av veckoavkastningar | realiserad volatilitet/riskkontroll | 13/52v |
| `price_vs_sma26w`, `price_vs_sma52w` | avstånd till glidande medelvärde | trendföljning | 26/52v |
| `high52w_ratio`, `low52w_ratio` | avstånd till 52v-extremer | ankareffekt | 52v |
| `turnover_13w_msek` | genomsnittlig daglig omsättning | likviditetsproxy | 13v |
| `volume_trend_13w` | volymförändring, senaste 4v mot föregående 9v | volymmomentum | 13v |

### FUNDAMENTA (11 kvoter + 2 provenance-fält, Spår B:s R12-tabell)

**R12 (rullande 12 månader) valdes som enda fundamentakälla** — den ger både TTM-flöden och
balansräkningssnapshots i en enda kvartalsvis uppdaterad rad, redan verifierad 100 % identisk
med årsdatan vid Q4 (`FUNDAMENTAL_QA.md §9`). Ingen blandning år/kvartal.

| fält | formel | hypotes |
|---|---|---|
| `roe_ttm`, `roa_ttm` | lönsamhet/eget kapital, /totala tillgångar | kvalitetsfaktor |
| `gross_margin_ttm`…`fcf_margin_ttm` | resultatmått/`revenues` | lönsamhets-/kassaflödeskvalitet |
| `net_debt_to_equity`, `current_ratio` | balansräkningsrelationer | finansiell risk/stabilitet |
| `revenue_growth_yoy`, `eps_growth_yoy` | R12 mot R12 ~52v tidigare | tillväxt, TTM-mot-TTM undviker säsong |
| `dividend_yield_ttm` | R12-utdelning / pris (Spår A) | standard värdefaktor |
| `has_fundamenta`, `fundamenta_days_since` | provenance | **obligatorisk** enligt uppdrag |

---

## 3. PIT-koppling av fundamenta — princip

För varje `(instrument, panel_date)` tas **den senaste R12-raden vars `report_date ≤
panel_date`**, via binärsökning i en per-instrument sorterad datumindex. En rapport blir
synlig i panelen exakt den dag den publicerades, aldrig tidigare. Tillväxtmått jämför två
sådana oberoende as-of-uppslag ~52 veckor isär.

**Survivorship-varning, upprepad explicit eftersom den aldrig får glömmas bort:** 67 av 68
Nasdaq Stockholm-bolag som avnoterades 2020–2026 saknar all fundamentadata
(`FUNDAMENTAL_QA.md`). `has_fundamenta=False` sätts uttryckligen på varje sådan rad — panelen
gissar aldrig ett värde. **CORE+FUNDAMENTA-panelen är därför INTE survivorship-säker för
fundamentakolumnerna**, till skillnad från CORE-panelen och target, som är det i sin helhet.

---

## 4. En bugg hittades — via coverage-QA, inte PIT-QA

Första byggkörningen gav `mom_4w`…`mom_12_1` en täckning på **0,0–0,1 %**, med värden
klustrade kring exakt noll. Orsaken: lookback-funktionens toleranskontroll jämförde det
funna historiska datumet mot **dagens datum** (`t0`) i stället för mot **måldatumet**
(`T − N veckor`) — koden accepterade i praktiken nästan vilket pris som helst nära `T` som
"N veckor tillbaka", vilket gav kvoter nära 1 (avkastning nära noll) och, för de flesta rader,
inget giltigt pris alls inom den (felaktigt beräknade) toleransen.

**Detta var inte ett PIT-läckage — alla data som användes låg fortfarande ≤ `panel_date`.**
Det var ett rent beräkningsfel som PIT-kontrollen (som bara verifierar "inget datum efter
gränsen") aldrig kunde fånga, men som täckningskontrollen omedelbart avslöjade genom en
orimlig 0-procentssiffra. **Detta är själva skälet till att både PIT-QA och coverage-QA krävs
— de fångar olika felklasser.** Bugg rättad, panelen ombyggd, samtliga hashar nedan är från
den rättade versionen.

---

## 5. PIT-/läckage-QA — samtliga kontroller passerade

`tools/spar_c_qa.py`, sex oberoende kontroller:

| kontroll | metod | utfall |
|---|---|---|
| 1. Nyckelkonsistens | `(kod, panel_date)` identiska mellan target/CORE/CORE+FUND | **identiska**, 28 539 rader i alla tre |
| 2. Inga target-kolumner i featurepanelerna | sökning efter `target`/`fwd`/`forward` i kolumnnamn | **inga träffar** |
| 3. Empirisk PIT, CORE | 400 slumpade rader återräknade oberoende direkt från VALIDATED-priser | **0 avvikelser** |
| 4. Empirisk PIT, FUNDAMENTA | samtliga 25 532 rader med `has_fundamenta=True` kontrollerade: `report_date ≤ panel_date` | **0 look-ahead** |
| 4b. Senaste-rapport-kontroll | 300 stickprov: är den använda rapporten verkligen den senaste ≤ `panel_date`? | **0 avvikelser** |
| 5. Target-PIT | `price_date ≤ panel_date` för samtliga target-rader | **0 fel** |

Kontroll 3 är en **oberoende återräkning** från rådata, inte en granskning av kodens egen
logik — den skulle ha fångat buggen i §4 om den körts före täckningskontrollen (den gjorde
det, i den andra körningen, efter rättningen).

---

## 6. Coverage-QA

Fullständig tabell per fält och år i `docs/probes/spar_c_qa.json`. Mönstret är genomgående
begripligt: täckningen är låg 2020 (otillräcklig lookback-historik för de längre fönstren —
`mom_52w`/`mom_12_1` är **0,0 % 2020**, korrekt eftersom inget instrument kan ha 52 veckors
historik det första kalenderåret av en panel som börjar 2020-01-01) och stabiliseras snabbt:

| fält | 2020 | 2021 | 2023+ |
|---|---|---|---|
| `mom_4w` | 91,9 % | 99,2 % | ≥99,8 % |
| `mom_52w` | **0,0 %** | 93,3 % | ≥97,1 % |
| `roe_ttm` (fundamenta) | 80,4 % | 83,8 % | ≥90,9 % |
| `eps_growth_yoy` (fundamenta) | 68,3 % | 68,4 % | ≥76,7 % |

Fundamentafälten har generellt lägre täckning än CORE (68–90 % mot 82–98 %) — direkt
förklarat av `has_fundamenta`-andelen (332/404 instrument, 82,2 %) och att tillväxtmåtten
kräver **två** oberoende as-of-träffar.

**Instrument med minst en fundamentarad: 332/404 (82,2 %).**

---

## 7. Extremvärden — flaggade, aldrig klippta

Ingen vinsorisering, ingen imputering, konsekvent med uppdraget. Två mönster hittades och
**verifierades äkta genom stickprov mot rådata**, inte antagna:

- **Momentum-/volymmått**: enstaka extrema utfall (`mom_52w` max 78,6× för VESTUM 2021,
  `volume_trend_13w` max 110,7×) — kontrollerade mot källdata och bekräftat genuina
  marknadshändelser, inte beräkningsfel.
- **Fundamentala marginal-/tillväxtmått**: en **nära-noll-bas-patologi**. Exempel: `IMMU`
  (2021) hade `revenues = 0,032 MSEK` och `gross_Income = −46,8 MSEK`, vilket ger
  `gross_margin_ttm = −1463` — matematiskt korrekt, ekonomiskt meningslöst som "marginal".
  `IRLAB-A` (2022) hade genuin omsättningstillväxt från en mycket liten bas, vilket ger
  `revenue_growth_yoy = 2313` (231 300 %). **Sex fält bär detta mönster** (§8) och är därför
  klassade KRÄVER ÅTGÄRD, inte UTESLUTNA — informationen är giltig för normala bolag, bara
  farlig utan ett materialitetsfilter som **inte** införts här.

---

## 8. Fältklassificering — slutlig

| klass | antal | fält |
|---|---|---|
| **GODKÄND** | 18 | samtliga 13 CORE-fält + `roe_ttm`, `roa_ttm`, `net_debt_to_equity`, `current_ratio`, `dividend_yield_ttm` |
| **KRÄVER ÅTGÄRD** | 6 | `gross_margin_ttm`, `operating_margin_ttm`, `net_margin_ttm`, `fcf_margin_ttm`, `revenue_growth_yoy`, `eps_growth_yoy` — samtliga p.g.a. nära-noll-bas-patologin i §7; kräver ett omsättnings-/resultatgolv eller annan materialitetsspärr före modellanvändning |
| **UTESLUTEN** | 0 | — |
| **GODKÄND (provenance)** | 2 | `has_fundamenta`, `fundamenta_days_since` |

Ingen feature uteslöts helt — även KRÄVER ÅTGÄRD-fälten är PIT-korrekta och källverifierade,
de kräver bara en efterbehandling som medvetet inte gjorts i Spår C (ingen vinsorisering utan
uttryckligt beslut).

---

## 9. Manifest och hashar — Spår C fryst

`validated/manifest_sparC.json`, med explicit beroende på Spår A:s och Spår B:s hashar.

| panel | rader | SHA256 (raw filbytes) |
|---|---|---|
| `panels/core_panel.json` | 28 539 | `d876af2f68af86c78a8a93ccec403afdd57203fa9e54da13343783aaf5e217c9` |
| `panels/core_fundamenta_panel.json` | 28 539 | `dee1297c1bb124b4a4efc7e1c7a158618e81b48c7f566864fd844d5dec2a5deb` |
| `panels/target_table.json` | 28 539 | `8a0b44e7c9b584f709372801f19ef8dc7e68f313f03f4c78bef1ed9af2852fce` |

(Hashar beräknade på filens rå bytes exakt som de ligger på disk — enklast att självständigt
verifiera med `sha256sum`. Byggskriptens interna utskrifter under körning visade en annan,
kanoniserad/sorterad hash av samma innehåll — samma data, annan serialiseringsordning, ingen
inkonsekvens.)

---

## 10. Kända begränsningar — gäller hela Spår C

1. Segmentmedlemskap (Large/Mid/Small Cap) tas vid dataset-byggtillfället, inte
   PIT-rekonstruerat historiskt.
2. `REBALANCE_WEEKS=4` ger 13× överlapp mellan konsekutiva 52-veckorsetiketter —
   `embargo_weeks=52` är preregistrerat för en framtida splittare, men ingen splittning görs
   i Spår C.
3. De sex nära-noll-bas-fälten (§8) kräver ett materialitetsfilter som inte är infört.
4. CORE+FUNDAMENTA-panelen är inte survivorship-säker för fundamentakolumnerna — CORE-delen
   och target är det.
5. 13 CORE + 11 FUNDAMENTA-fält är en avsiktligt avgränsad, väldokumenterad uppsättning
   standardfaktorer — inte en uttömmande genomgång av alla tänkbara kombinationer av Spår
   A/B:s råfält.

**Ingen modellträning eller featureurval baserat på framtida avkastning har gjorts.** Spår C
levererar ett granskningsbart, reproducerbart dataset — inte en alfahypotes.
