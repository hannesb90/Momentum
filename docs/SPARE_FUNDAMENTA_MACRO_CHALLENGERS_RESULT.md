# Spår E — FUNDAMENTA- och MACRO-challengers

Status: **SLUTFÖRD OCH LÅST**  
Spår D: **oförändrat och fortsatt slutligt fryst**  
Modelltuning/feature selection/alpha/exits: **inte utfört**

## Beslut

- **FUNDAMENTA TILLFÖR INTE ROBUST INFORMATION.** Både CatBoost och XGBoost försämras tydligt i OOS-IC, positiv datumandel, Sharpe, drawdown och leave-top-3-out. Resultatet kvarstår på den direkt jämförbara delmängden med `has_fundamenta=True`.
- **MACRO TILLFÖR INTE ROBUST INFORMATION.** CatBoost får en mindre förbättring i mean IC och mindre negativ top-30 IC, men top-30 är fortsatt negativ och leave-top-3-out försämras. XGBoost försämras i både IC och top-30. Robusthetskriteriet uppfylls därför inte.
- **E5 INTERAKTIONER KÖRS INTE.** Den preregistrerade grinden — stöd från CORE+MACRO utan försämrad koncentrationskollaps — passerades inte.

Detta ändrar inte Spår D:s negativa neutrala slutsats.

## Låsning och metod

E1 och E4 använder Spår D:s fasta CatBoost- och XGBoost-konfigurationer, tidsfönster, embargo, target, paneldatum, portföljkonstruktion och kostnad. Ingen parameter eller feature valdes efter resultat.

Aktiva frysta inputhashar kontrollerades före fit:

- CORE panel: `220e258669b1eed774e533065dec5ed8e5780edc0e31ec4eb3e841c128a1c974`
- CORE+FUNDAMENTA panel: `117ac6e811ff62ea62168fea2f55a6da430c43774794bed8733573dc4dd1eaaa`
- target: `6c2b87aad0e1853837b8d60a3b11e100bca781486b7c12966a27b9a8bd671d21`
- feature registry: `391a365fd73f981d682ed756deacb94d921f14d61a47628eb16ac1de9eb65f05`
- Spår D result lock: `897806429ffe02c1fffe031816ee27b70b68680b562d0305dffdda80fbd2519e`

Manifestverifieringen för A/B/C passerar: 13 aktiva artefakter byte-matchade, registry `1.2.0`.

## E1 — FUNDAMENTA

OOS test omfattar 6 781 observationer och 20 paneldatum per modell. 6 551 observationer (96,6 %) har fundamenta. Valideringen omfattar 4 511 observationer, varav 4 178 (92,6 %) har fundamenta. Native NaN-hantering användes; inga saknade fundamentalvärden nollkodades eller imputerades. `has_fundamenta` är provenance och användes inte som feature.

### Fullt identiskt observationsuniversum

| Modell | Dataset | mean IC | median IC | positiv andel | top-30 IC | CAGR | Sharpe | MaxDD | turnover | leave-top-3 excess |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| CatBoost | CORE | 0,087 | 0,081 | 100 % | -0,187 | 29,0 % | 1,083 | -10,7 % | 0,410 | 0,9 % |
| CatBoost | CORE+F | 0,031 | 0,029 | 65 % | -0,182 | 20,8 % | 0,497 | -16,0 % | 0,302 | -10,2 % |
| CatBoost | Δ | **-0,056** | -0,052 | -35 pp | +0,005 | -8,2 pp | -0,587 | -5,2 pp | -0,108 | **-11,1 pp** |
| XGBoost | CORE | 0,123 | 0,127 | 100 % | -0,221 | 35,5 % | 1,166 | -11,8 % | 0,393 | 5,6 % |
| XGBoost | CORE+F | 0,006 | 0,028 | 70 % | -0,410 | 12,5 % | 0,001 | -16,9 % | 0,257 | -7,8 % |
| XGBoost | Δ | **-0,117** | -0,099 | -30 pp | **-0,189** | -23,1 pp | -1,165 | -5,1 pp | -0,137 | **-13,4 pp** |

### Jämförbar delmängd med fundamenta

Även när båda prediktionsuppsättningarna utvärderas endast där `has_fundamenta=True` försämras mean IC med -0,048 för CatBoost och -0,102 för XGBoost. Leave-top-3-out excess försämras med -8,4 respektive -8,2 procentenheter. Detta falsifierar förklaringen att full-universumresultatet enbart orsakas av rader utan fundamentatäckning.

### Stabilitet och koncentration

- CatBoost CORE+F mean IC per år 2023/2024/2025: -0,083 / 0,044 / 0,006, mot CORE -0,040 / 0,067 / 0,124.
- XGBoost CORE+F: -0,033 / 0,030 / -0,038, mot CORE 0,036 / 0,117 / 0,135.
- CORE+F:s topp-3 blir CatBoost `XBRANE, SANION, MOB` och XGBoost `ONCO, QLINEA, SANION`. Leave-top-3-resultaten är negativa.
- Sektor 4 är fortsatt största urvalskoncentration: 40,2 % för CatBoost och 35,7 % för XGBoost. Förbättrad robusthet kan inte visas.

Permanent begränsning: 67/68 terminalinstrument saknar fundamenta. E1 är diagnostiskt och får inte tolkas som ett survivorship-säkert modellvalstest.

E1 aggregate SHA256: `01c93940c56f7d47d7105464d6b92da2d31de206e4b5dc0533b7a192ebc1dce8` (identisk vid full omkörning).

## E2/E3 — macro_panel och QA

Panelen byggdes utan åtkomst till target. As-of-regeln är senaste observation med `observation_date <= panel_date`; ingen framtida backfill. Rebalansering antas ske efter marknadsstängning, vilket gör samma dags observerade marknadsstängning tillgänglig.

Godkända råserier:

- Riksbanken: styrränta, svensk statsränta 2Y och 10Y, EUR/SEK och USD/SEK.
- Cboe: VIX.
- FRED: S&P 500 och Brent.
- Fryst V2-serie: bred rekonstruerad svensk marknadsavkastning.

Kreditkandidaten ICE BofA US High Yield OAS klassificerades **UTESLUTEN**: den hämtade snapshoten börjar 2023-08-08 och klarar inte 2020–2026-kravet. VSTOXX klassificerades **UTESLUTEN** eftersom ingen stabil officiell maskinläsbar källa hade validerats före preregistreringen. BNP, CPI och PMI uteslöts på förhand på grund av vintage-/revisionsrisk.

Featurepreregistreringen innehöll 46 kandidater. Fyra kreditfeatures föll i datakvalitetsgrinden; den frysta panelen innehåller 42 godkända features på 86 paneldatum 2020-01-03–2026-07-10. Alla externa godkända features har 100 % paneltäckning. Svensk marknadsserie har dokumenterade inledande lagg-nullvärden: ret3m 95,3 %, ret6m 91,9 %, ret12m 83,7 %, vol3m 96,5 %. De imputerades inte.

En pre-model QA hittade och reparerade ett fel innan frysning: daglig minimiobservationströskel hade gett 0 % coverage för svensk veckovolatilitet. Frekvensspecifik tröskel och annualisering infördes; slutlig coverage är 96,5 %.

- RAW source manifest aggregate: `5099e2c2b8c7c70e97220b1430f2db180484f4f7645e46f67d8e4444e8c82521`
- macro panel aggregate: `71a14cd2455024272fa55aab2face2d07fd0f64a1bc438b98b80b06264dc9fd4`
- macro panel bytes SHA256: `ad517fcbf38bc590adef771cdaf6810a9bdb3c57f74d20f9700d2d17ae99debc`

## E4 — MACRO

| Modell | Dataset | mean IC | median IC | positiv andel | top-30 IC | CAGR | Sharpe | MaxDD | turnover | leave-top-3 excess |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| CatBoost | CORE | 0,087 | 0,081 | 100 % | -0,187 | 29,0 % | 1,083 | -10,7 % | 0,410 | 0,9 % |
| CatBoost | CORE+M | 0,105 | 0,086 | 100 % | -0,148 | 16,2 % | 0,180 | -7,7 % | 0,430 | -7,3 % |
| CatBoost | Δ | +0,018 | +0,005 | 0 pp | +0,039 | -12,8 pp | -0,903 | +3,1 pp | +0,020 | **-8,2 pp** |
| XGBoost | CORE | 0,123 | 0,127 | 100 % | -0,221 | 35,5 % | 1,166 | -11,8 % | 0,393 | 5,6 % |
| XGBoost | CORE+M | 0,100 | 0,099 | 95 % | -0,242 | 20,6 % | 0,441 | -10,7 % | 0,390 | -8,9 % |
| XGBoost | Δ | -0,023 | -0,028 | -5 pp | -0,021 | -15,0 pp | -0,726 | +1,1 pp | -0,003 | **-14,5 pp** |

### Års- och koncentrationskontroll

- CatBoost CORE+M mean IC 2023/2024/2025: 0,022 / 0,087 / 0,139, mot CORE -0,040 / 0,067 / 0,124. Detta är den enda tydligt positiva generaliseringsindikationen.
- XGBoost CORE+M: -0,016 / 0,104 / 0,093, mot CORE 0,036 / 0,117 / 0,135.
- CatBoost top-30 förbättras men är fortsatt klart negativ (-0,148). XGBoost top-30 försämras (-0,242).
- Båda modellernas leave-top-3-out excess blir negativt. `XBRANE` är fortsatt största bidragstagare i båda modellerna.
- Största sektorandel är fortsatt sektor 4: 33,0 % CatBoost och 31,2 % XGBoost. Macro visar inte en robust minskning av tickerberoendet.

E4 aggregate SHA256: `d0081eff937bddf223043645bdac3e6233d9f6aa58ff5e69fdee2f14f3c2fe56` (identisk vid full omkörning).

## Slutlig adversarial bedömning

Inget dataintegritetsfel hittades i de frysta A/B/C/target-inputarna. Macro-byggens enda implementationsfel fångades före frysning och regressionstestades genom positiv, frekvenskorrekt coverage. RAW-hashkontroll, targetfri panelbyggnad, many-to-one-paneljoin, låsta Spår D-hashar och två fulla reproduktionskörningar passerade.

Spår E ger ingen grund för efterhandsmodifiering av Spår D, tuning eller interaktionssökning. Nästa vetenskapligt försvarbara slutsats är att varken nuvarande FUNDAMENTA eller denna preregistrerade MACRO-panel demonstrerar robust inkrementell information ovanpå CORE med de fasta modellfamiljerna.

## Artefakter

- `spare/e1_preregistration.json`
- `spare/e3_macro_preregistration.json`
- `spare/e4_preregistration.json`
- `spare/raw_macro_v1/source_manifest.json`
- `spare/macro_v1/macro_panel.json`, `qa.json`, `manifest.json`
- `spare/results/SPARE_E1_FUNDAMENTA_DIAGNOSTIC_V1/`
- `spare/results/SPARE_E4_MACRO_CHALLENGER_V1/`
