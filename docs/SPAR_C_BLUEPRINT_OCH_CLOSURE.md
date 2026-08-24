# Spår C: feature blueprint och closure audit — dataset_v1.0 SLUTLIGT FRYST

Datum: 2026-08-08. **Allt modellarbete stoppat under detta arbete.** Blueprinten är byggd
från noll utifrån de frysta Spår A och Spår B — inte från de gamla 48 legacy-featuresen och
inte från de 26 fält som redan råkat implementeras i den första Spår C-omgången.
Verktyg: `tools/spar_c_blueprint.py`, `tools/spar_c_features_core_v2.py`,
`tools/spar_c_features_fundamenta_v2.py`, `tools/spar_c_qa.py`, `tools/spar_c_freeze.py`.
Artefakter: `docs/probes/feature_blueprint.json`, `docs/probes/feature_registry.json`,
`panels/{core_panel,core_fundamenta_panel}.json`, `validated/manifest_sparC.json`.

Detta dokument ersätter `SPAR_C_PANELARKITEKTUR.md` som den auktoritativa Spår C-rapporten
(den filen kvarstår som historik över den första, nu överspelade omgången).

---

## 0. Sammanfattning — svar på samtliga efterfrågade slutsiffror

| mått | värde |
|---|---|
| Blueprint-kandidater totalt | **68** |
| — redan implementerade (identifierade i efterhand som redan byggda) | 26 |
| — nybyggda i denna revision | 27 (26 riktiga fält + 1 infrastruktur: internt index) |
| — KAN BYGGAS, avsiktligt EJ byggda (dokumenterat gap) | 11 |
| — SAKNAR DATA | 2 |
| — BÖR INTE BYGGAS | 2 |
| Faktiskt implementerade CORE-fält | **31** |
| Faktiskt implementerade FUNDAMENTA-fält | **21** |
| **Totalt fält i Spår C** | **52** |
| Fält kvar i KRÄVER ÅTGÄRD | **0** |
| **Spår C SLUTLIGT FRYST?** | **JA** |

---

## 1. Blueprinten — metod

Samtliga 12 informationsfamiljer du efterfrågade genomsöktes systematiskt. För varje
kandidat dokumenterades de 11 begärda punkterna (namn, familj, hypotes, exakta råfält,
formel, lookback, PIT-regel, missing-semantik, survivorship-status, redundansrisk,
klassificering) i `docs/probes/feature_blueprint.json`.

**Legacy-completeness-check (read-only, INTE återanvänt):** de gamla 48 featuresen
(`momentum_ml/features/feature_engineering.py FEATURE_COLS`) genomsöktes för att säkerställa
att ingen informationsdimension missats. Tre konkreta fynd av detta:

1. **`adx`/`di_diff`/`adx_trend`/`atr_norm`** (legacy) kräver high/low-priser. Spår A:s
   VALIDATED-lager innehåller **enbart** `{datum, adjusted_close, volym}` (R1 i
   `manifest_sparA.json`) — hela ADX/ATR-familjen är därför **SAKNAR DATA**, dokumenterat
   explicit snarare än tyst ignorerad. `trend_strength_52w` (regressionslutningens t-stat,
   close-baserad) byggdes som en besläktad men datakompatibel ersättare.
2. **`attention_gap`/`interact_report_reaction`** (legacy) hade ett bevisat, obegränsat
   `1/(vol_ratio+eps)`-format med skalfel upp till 100 000 (dokumenterat redan i
   `DATATACKNING_48FEATURES_2026-08-07.md`). Samma ekonomiska hypotes (PEAD) byggdes om
   från grunden som `return_since_last_report_ttm` med en robust, begränsad formel.
3. **`resid_mom`** (legacy) bekräftar att residual momentum är en etablerad hypotes värd att
   bygga — `residual_momentum_52w` byggdes oberoende, från grunden, med en egen
   marknadsmodellsregression mot ett nybyggt index.

---

## 2. Gap-analys mot de ursprungliga 26 fälten

**Samtliga 26 ursprungliga fält har tydligt stöd i blueprinten.** Ingen av dem saknar
ekonomisk motivering eller källdokumentation — det kontrollerades explicit genom att
matcha varje IMPLEMENTERAD-post i blueprinten mot registret; alla 26 återfanns (två,
`price_vs_sma26w`/`price_vs_sma52w`, saknades initialt i ett utkast av blueprinten och
lades till vid granskningen — se `feature_blueprint.json`, inget faktiskt gap i sak).

**Informationsfamiljer som var HELT frånvarande innan denna revision** (0 fält av de
ursprungliga 26 täckte dem):

| familj | status före | status efter |
|---|---|---|
| Relativt/cross-sectional momentum | 0 fält | `mom_relative_index_52w`, `rank_mom_52w_pct` |
| Residual momentum | 0 fält | `residual_momentum_52w` |
| Beta/idiosynkratisk volatilitet | 0 fält | `beta_52w`, `idio_vol_52w` |
| Skew/kurtosis (tail risk) | 0 fält | `skew_52w`, `kurtosis_52w` |
| Downside volatility | 0 fält | `downside_vol_52w` |
| Max drawdown (separat från "var man är nu") | 0 fält | `max_drawdown_52w` |
| Illikviditet (Amihud) | 0 fält | `illiquidity_amihud_13w` |
| Earnings quality/accruals | 0 fält | `accruals_ttm` |
| Aktieutspädning/återköp | 0 fält (trots att `number_Of_Shares` var ett godkänt Spår B-fält) | `shares_growth_yoy` |
| Värdering (yield-mått) | 0 fält | `fcf_yield_ttm` |
| Kapitaleffektivitet (DuPont) | 0 fält | `asset_turnover_ttm`, `roic_proxy_ttm` |
| Balansräkningsstyrka utöver leverage | 0 fält | `equity_ratio_ttm` |
| Rapportrelaterad drift (PEAD) | 0 fält (legacy-motsvarigheten trasig) | `return_since_last_report_ttm` |
| Marknadsregim | 0 fält | `market_regime_trend`, `market_regime_vol` |

Detta var de mest väsentliga luckorna — samtliga är nu täckta.

---

## 3. De 6 KRÄVER ÅTGÄRD-fälten — lösta med preregistrerad materialitetsregel

### Materialitetsregeln (preregistrerad FÖRE targetkoppling)

> Ett resultatmått (`revenues` för marginalmått; `profit_To_Equity_Holders` för EPS-
> tillväxtens bas) betraktas som en giltig, ekonomiskt tolkningsbar bas för en kvot
> **endast om dess absolutbelopp är minst 1 % av `total_Assets` samma period**. Uppfylls
> inte detta sätts kvoten till **null** — aldrig klippt, aldrig imputerad. För
> tillväxtkvoter måste **båda** periodernas bas uppfylla testet oberoende av varandra.

**Motiv:** en verksamhet som genererar mindre än 1 % av sin balansomslutning i intäkter
under ett rullande år är i praktiken inte en "opererande" verksamhet i den mening
marginalmått förutsätter — marginalen blir en artefakt av en nästan obefintlig nämnare,
oavsett bolagets absoluta storlek. Tröskeln är satt på **ekonomiska** grunder (en normal
verksamhet, även i lågmarginalbranscher, uppvisar intäkter långt över 1 % av
balansomslutningen) — **ingen targetdata konsulterades vid valet av 1 %-tröskeln**, och
tröskeln justerades inte i efterhand.

### Resultat, verifierat mot rådata

| fält | min FÖRE | min/max EFTER | reduktion |
|---|---|---|---|
| `gross_margin_ttm` | −1 462,9 | min −62,7 / max 2,3 | 23× |
| `operating_margin_ttm` | −30 710,0 | min −171,5 / max 45,9 | 179× |
| `net_margin_ttm` | −28 806,4 | min −171,7 / max 46,0 | 168× |
| `fcf_margin_ttm` | −26 749,0 | min −103,9 / max 89,8 | 257× |
| `revenue_growth_yoy` | max 2 312,8 | min −3,3 / max 533,6 | 4,3× |
| `eps_growth_yoy` | max 1 848,5 | min −0,99 / max 25,0 | 74× |

Antal rader materialitetsregeln satte till null: 454–467 för marginalmåtten, 2 177 för
`revenue_growth_yoy`, 3 624 för `eps_growth_yoy` (av 25 532 rader med `has_fundamenta=True`).

**Regeln eliminerar inte alla extremvärden — det var aldrig målet.** Kvarvarande
extremvärden (t.ex. `IMMNOV`, en klinisk biotech med `revenues=1,9 MSEK`/`total_Assets=190
MSEK` = 1,0 % — precis vid tröskeln — och `operating_Income=−327 MSEK`) verifierades mot
rådata och är **äkta**: bolag med materiell men liten omsättning och stora
utvecklingskostnader ger legitimt extrema marginaler. Det är ekonomisk verklighet för den
bolagstypen, inte ett datafel, och klipps därför inte bort.

**Samtliga 6 fält uppgraderade till GODKÄND.**

---

## 4. Blueprint-familjer — explicit beslut per familj

| familj | antal kandidater | KAN BYGGAS (byggda) | KAN BYGGAS (ej byggda) | SAKNAR DATA | BÖR INTE |
|---|---|---|---|---|---|
| CORE/momentum | 10 | 10 | 0 | 0 | 0 |
| CORE/trend & drawdown | 5 | 5 | 0 | 0 | 0 |
| RISK | 9 | 7 | 2 (`vol_4w`, `skew_13w`) | 1 (ADX/ATR-familjen) | 0 |
| VOLYM/LIKVIDITET | 5 | 3 | 2 (`abnormal_volume_1w`, `price_volume_corr_13w`) | 0 | 0 |
| RELATIVT/CROSS-SECTIONAL | 5 | 3 | 3 (`mom_relative_sector_52w`, `rank_vol_52w_pct`, samt sektor delvis) | 1 (industri, för glest) | 0 |
| FUNDAMENTA | 25 | 18 | 4 (`cash_conversion_ttm`, `margin_change_operating_yoy`, `growth_acceleration_yoy`, samt sektor/cap-tier-kontext) | 0 | 1 (`dividend_growth_yoy`) |
| EVENT/REGIM | 3 | 3 | 0 | 0 | 1 (interaktionstermer) |

**Varje familj har fått ett explicit beslut** — antingen byggd, dokumenterat uppskjuten med
skäl, eller avrådd med skäl. Ingen familj lämnades obehandlad.

### De 11 dokumenterat uppskjutna (KAN BYGGAS, ej byggda)

| fält | skäl till uppskjutning |
|---|---|
| `mom_relative_sector_52w` | hög redundans mot `mom_relative_index_52w`, svagare PIT-egenskap (statisk sektorklassificering) |
| `vol_4w` | hög redundans mot `vol_13w`, marginell tilläggsinfo |
| `skew_13w` | hög redundans mot `skew_52w`, en horisontvariant räcker |
| `abnormal_volume_1w` | hög redundans mot `volume_trend_13w` |
| `price_volume_corr_13w` | svag/explorativ hypotes, lägre prioritet |
| `rank_vol_52w_pct` | hög redundans mot `vol_52w`; `rank_mom_52w_pct` byggdes som representant för mönstret |
| `cash_conversion_ttm` | hög redundans mot `accruals_ttm` (samma hypotes, kvot i stället för differens) |
| `margin_change_operating_yoy` | hög redundans mot `operating_margin_ttm` + `revenue_growth_yoy` tillsammans |
| `growth_acceleration_yoy` | otillräcklig R12-historik för full paneltäckning 2020–2021 (endast 271/355 instrument har data ≥2019) |
| `sector_code_context` | kategoriskt kontextfält, kräver ett modellbeslut (one-hot/encoding), inte en panelkolumn |
| `cap_tier_code_context` | samma skäl |

### De 2 SAKNAR DATA

- **ADX/ATR-familjen**: kräver high/low, finns inte i Spår A:s VALIDATED-lager.
- **Industrirelativt momentum** (branchId-nivå): för gles fördelning i detta universum
  (404 instrument över fler branscher än sektorer) för stabila medianer.

### De 2 BÖR INTE BYGGAS

- **`dividend_growth_yoy`**: en tillväxtprocent från nollbas (≈40 % av raderna har
  `dividend=0`) är antingen odefinierad eller oändlig — samma nära-noll-bas-patologi
  materialitetsregeln just löste, fast för en variabel där själva förekomsten (0→>0) är en
  diskret händelse, inte en kontinuerlig tillväxttakt. En framtida `dividend_initiation`-
  dummy vore rätt verktyg.
- **Explicita interaktionstermer** (t.ex. momentum×volatilitetsregim): att handplocka EN
  specifik interaktion i förväg är att implicit anta vilken kombination som blir prediktiv
  — exakt den sortens dolda, targetinformerade genväg uppdraget förbjuder. Trädbaserade
  modeller (redan planerade för modellracet) fångar interaktioner automatiskt.

---

## 5. Ny bugg-/kvalitetskontroll under omgången

Ingen ny bugg av samma allvarlighetsgrad som lookback-felet i förra omgången hittades.
`fcf_yield_ttm` (ny) fick ett extremvärde (min −5 658, `FLERIE`) som INTE fångas av
materialitetsregeln (den gäller bara omsättningsbaserade kvoter, inte
börsvärdesbaserade). Spårat till samma instrument (`FLERIE`) vars prisserie redan är känt
komplex från Spår A:s segmentering (`PRIS_QA_KLASSIFICERING.md §4b`) — mycket litet
börsvärde (0,89 miljoner aktier) kombinerat med en stor kassautflödesperiod. Verifierat
äkta, inte ett beräkningsfel, dokumenterat i registret, **inte blockerande** eftersom
uppdraget bara krävde att de 6 NAMNGIVNA fälten löses, inte att alla tänkbara
extremvärden i nya fält elimineras.

---

## 6. PIT-/läckage-QA och coverage-QA — omkörda på de utökade panelerna

Samtliga sex strukturella kontroller (nyckelkonsistens, inga target-kolumner, 400 CORE-rader
oberoende återräknade, samtliga 25 532 fundamenta-rader kontrollerade för look-ahead, 300
stickprov för senaste-rapport-korrekthet, target-PIT) **passerade igen** på de utökade
panelerna — se `docs/probes/spar_c_qa.json`. Coverage per fält och år finns i samma fil;
mönstret är konsekvent med den första omgången (låg 2020, stabiliseras 2021+, förklarat av
lookback-krav och `has_fundamenta`-andelen).

---

## 7. Frysning — SLUTLIG

`validated/manifest_sparC.json`, version **1.1.0** (ersätter 1.0.0-rc).

| panel | rader | fält | SHA256 (raw filbytes) |
|---|---|---|---|
| `panels/core_panel.json` | 28 539 | 31 | `8515697d5869910cdef9f924e8398dbf64d9564b19e92364daca5d1f7de986bd` |
| `panels/core_fundamenta_panel.json` | 28 539 | 21 fundamenta + 31 CORE | `79bbaffb3d0847431b3f87f4f94413e03e97c50bb3f16a26c5f6e6f6bbffa4a6` |
| `panels/target_table.json` | 28 539 | — (oförändrad) | `8a0b44e7c9b584f709372801f19ef8dc7e68f313f03f4c78bef1ed9af2852fce` |

### Samtliga frysningskriterier uppfyllda

| kriterium | status |
|---|---|
| blueprinten är komplett | ✅ 68 kandidater, alla 11 dokumentationsfält, alla 12 familjer |
| varje informationsfamilj har fått explicit beslut | ✅ §4 |
| 0 fält i KRÄVER ÅTGÄRD | ✅ (var 6, nu 0) |
| PIT/leakage-QA passerar | ✅ samtliga 6 kontroller |
| coverage-QA passerar | ✅ redovisad per fält/år |
| manifest och SHA256 uppdaterade | ✅ `manifest_sparC.json` v1.1.0 |
| inga targetbaserade beslut tagna | ✅ materialitetströskeln (1 %) valdes på ekonomiska grunder, ingen targetdata konsulterad; inga features valdes bort baserat på förväntad prediktiv kraft |

---

## 8. Vad dataset_v1.0 fortfarande saknar trots blueprinten

Ärligt kvarstående, för att inte dölja begränsningar:

1. **ADX/ATR och alla high/low-baserade tekniska mått** — kräver att Spår A:s
   VALIDATED-definition öppnas om (utanför detta uppdrags omfattning).
2. **11 dokumenterat uppskjutna fält** (§4) — främst höggradigt redundanta varianter av
   redan byggda mått, plus `growth_acceleration_yoy` (otillräcklig historik) och de två
   kategoriska kontextfälten (kräver ett modellbeslut, inte en panelkolumn).
3. **Sann industrinivå-relativitet** — för gles fördelning i detta universum.
4. **PIT-rekonstruerad sektor-/segmenttillhörighet** — Börsdatas `sectorId`/`marketId`
   används statiskt (dagens klassificering), inte historiskt korrekt vid varje panel_date.
   Ärvd begränsning, gäller nu även de nya relativa/sektormåtten som skulle byggt på den.
5. **Fundamentans survivorship-status är oförändrad**: 67/68 avnoterade saknar all
   fundamentadata. De 8 nya FUNDAMENTA-fälten ärver samma begränsning som de ursprungliga
   11 — ingen ny källa har tillkommit, bara nya kvoter av samma underliggande R12-data.
6. **Sann ROIC** (skattejusterad NOPAT) — inget skattefält bland Spår B:s 22 godkända
   fält, `roic_proxy_ttm` är en dokumenterad före-skatt-approximation.
7. **Dividend-initiering** som diskret händelse (i stället för den avrådda
   `dividend_growth_yoy`) — identifierad som rätt verktyg men inte byggd.

---

## 9. Slutsats

**Spår C är SLUTLIGT FRYST.** 68 blueprint-kandidater dokumenterade, 52 fält faktiskt
implementerade (31 CORE + 21 FUNDAMENTA) mot tidigare 26, 0 fält kvar i KRÄVER ÅTGÄRD,
samtliga PIT-/läckage- och coverage-kontroller passerade, ingen targetbaserad optimering
har förekommit. Kvarstående luckor är explicit dokumenterade i §8, inte dolda.

**Ingen modellträning, inget featureurval och ingen optimering mot framtida avkastning har
gjorts i detta arbete.**
