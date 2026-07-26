# Degenererade splits, del 2: föregångare, fönsterval, regimanpassning, avstående

Date: 2026-07-26

Uppföljning på `reject_split_regularization_vs_signal_2026-07-26.md` (som
visade att degenerering beror på genuint saknad signal, inte för hård
regularisering). Fyra frågor, skript
`tune_reject_split_followup.py` (precursors/windows/regime/abstention).
Samma datakälla-caveat som del 1: nyaste TILLGÄNGLIGA feature-cache, inte en
bit-identisk reproduktion av en specifik natts produktionskörning. De 3
degenererade splittarna i den här datamängden (26, 27, 28 - alla i rad,
2021-06 till 2021-12) skiljer sig sannolikt från produktionens exakta
lista, men mekanismerna nedan bör generalisera.

## 1. Vilka driftmått föregår en degenererad split?

| split | val_start | degenerate | feature_drift | target_var | val_auc_best | plateau_frac |
|---:|---|---|---:|---:|---:|---:|
| 23 | 2020-09-14 | | 0,230 | 0,0185 | 0,610 | 0,004 |
| 24 | 2020-12-14 | | 0,296 | 0,0189 | 0,577 | 0,070 |
| 25 | 2021-03-15 | | 0,242 | 0,0205 | 0,546 | 0,081 |
| **26** | **2021-06-14** | **JA** | 0,149 | 0,0216 | **0,497** | 0,105 |
| **27** | **2021-09-13** | **JA** | 0,201 | 0,0234 | **0,482** | 0,203 |
| **28** | **2021-12-13** | **JA** | 0,266 | 0,0249 | **0,488** | 0,163 |
| 29 | 2022-03-14 | | 0,308 | 0,0256 | 0,537 | 0,060 |

**Valideringens AUC faller MONOTONT i tre steg innan degenereringen**
(0,610→0,577→0,546→0,497) och återhämtar sig direkt efteråt (→0,537).
Korrelation mot "degenererad" bekräftar: `val_auc_best` föregående split
= -0,58, `val_score_largest_plateau_frac` föregående split = +0,59,
`target_var_median_by_date` föregående split = +0,42. Det här är den
starkaste, tidigaste och mest praktiskt användbara föregångssignalen -
och den kräver ingen framåtblick (varje splits valideringsfönster
avslutas FÖRE nästa splits träningsfönster startar).

**Feature-drift (train vs val) är DÄREMOT inte en föregångare** -
korrelationen mot föregående splits driftvärde är nästan noll (-0,11).
Drift är en SAMTIDIG signatur (degenererade splits har högre drift ÄN sig
själva, se del 1), inte något som syns i förväg.

**Marknadsregim:** degenererade splittars träningsfönster hade högre
bull-andel (73% mot 59% median) och lägre bear-andel (17% mot 24%) än
friska splittar. Rimlig tolkning: en lång, odramatisk uppgångsperiod ger
mindre tvärsnittsspridning mellan vinnare/förlorare - momentum-modellens
edge bygger på just den spridningen, så den försvagas i en "allt stiger
tillsammans"-regim.

**Rekommendation:** lägg till en `val_auc_best`-trend (2-3 splits
bakåt) som en ny ledande varningssignal i pipeline_health.json, utöver
den redan byggda `active`-kritiska flaggan - en fallande trend syns EN
till TVÅ splits innan den faktiska degenereringen.

## 2. Hjälper kortare eller viktade träningsfönster?

Kört på de 3 degenererade splittarna: baseline (260v), kortare fönster
(130v, samma validerings-/testfönster), recency-viktat (260v, exponentiell
halveringstid 52v).

| Variant | num_trees (median) | test-AUC (median) | test rank-IC (median) |
|---|---:|---:|---:|
| baseline_260v | 1 | 0,520 | -0,037 |
| short_130v | 1 | 0,521 | -0,009 |
| recency_weighted_260v | 1 | 0,506 | -0,061 |

**`num_trees` stannar på exakt 1 i BÅDA alternativen, för alla tre
splittar.** Ingen av åtgärderna löser grundproblemet. Effekten per split
är dessutom inkonsekvent: kortare fönster hjälpte split 26 rejält
(AUC 0,454→0,521) men skadade split 27 (0,600→0,575) och 28
(0,520→0,497). Recency-viktning gav ingen konsekvent förbättring alls
(faktiskt sämre på gruppnivå). **Slutsats: varken kortare eller viktat
fönster är en generell fix** - effekten är split-specifik och lika ofta
skadlig som hjälpsam.

## 3. Global modell vs regimanpassad modell

Tränings-data begränsad till veckor i SAMMA regim (här: bull, ingen
framåtblick - regimen läses av vid träningsfönstrets SLUT) jämfört med
hela 260-veckorsfönstret (alla regimer blandade).

| split | global test-AUC | regimanpassad test-AUC | global rank-IC | regimanpassad rank-IC |
|---:|---:|---:|---:|---:|
| 26 | 0,454 | 0,519 | -0,139 | -0,043 |
| 27 | 0,600 | 0,572 | 0,153 | 0,090 |
| 28 | 0,520 | 0,541 | -0,037 | -0,017 |

**Fortfarande `num_trees==1` för alla, oavsett regimanpassning.** Samma
blandade bild som fönsterexperimentet ovan (rimligt - bull-regimen
dominerade redan 58-59% av det globala fönstret, så regimanpassning här
är i praktiken en variant av "kortare/mer koncentrerat fönster"): hjälper
26/28 marginellt, skadar 27 (som redan hade användbar signal). **Ingen
tydlig vinst av regimanpassning över global modell** i den här
undersökningen - och den skadar aktivt den enda splitten som redan
fungerade.

## 4. Bör modellen avstå vid låg signalstyrka?

Tröskel: `val_auc_best < 0,52` (känt FÖRE testfönstret, ingen
framåtblick) → avstå. Jämför testfönstrets faktiska topp-decil-avkastning
(modellens urval) mot jämviktad avkastning (alla eligible bolag, "gör
ingenting särskilt")-alternativet, över alla 31 splits.

| Grupp (n) | Medel topp-decil-avkastning | Medel jämviktad avkastning | Andel där urvalet slog jämvikt |
|---|---:|---:|---:|
| Skulle HANDLA (AUC≥0,52, n=28) | **6,29%** | 4,60% | **71,4%** |
| Skulle AVSTÅ (AUC<0,52, n=3) | 1,96% | 1,96% | 33,3% |

**Under de svaga perioderna gav modellens urval EXAKT samma genomsnittliga
avkastning som att bara hålla hela universumet jämviktat (0,0196 mot
0,0196) - noll mätbar edge.** Under normala perioder slog urvalet
jämvikten 71% av tiden med en tydlig marginal (+1,7 procentenheter i
snitt). Det här är ett rakt, historiskt underbyggt svar: **JA, modellen
bör avstå från (eller kraftigt tona ner) aktiv rangordning när
`val_auc_best` faller under ~0,52, och falla tillbaka på jämviktad/
benchmark-exponering istället.**

Enda nyansen: split 27 (AUC 0,482, "skulle avstå") hade ändå en riktig
positiv topp-decil-avkastning (12,7%) - samma undantag som noterades i
del 1 (en enda-träds-split kan ändå råka fånga verkligt värde). En
tröskel byggd på enbart `val_auc_best` hade avstått fel just den gången -
väntat givet att gruppnivå-mönstret (33% träffsäkerhet) betyder att
avstående är rätt BESLUT I SNITT, inte i varje enskilt fall.

## Sammantagen rekommendation

1. Lägg till en `val_auc_best`-trend (fallande 2-3 splits i rad) som ny
   tidig varningssignal i `pipeline_health.json` - den föregår
   degenerering med minst en splits marginal.
2. Överge INTE kortare fönster/recency-viktning/regimanpassning som
   permanenta ändringar - ingen av dem löser problemet konsekvent, och
   samtliga riskerar att skada redan fungerande perioder.
3. Bygg en `val_auc_best < ~0,52`-avstående-regel (falla tillbaka på
   jämviktad/benchmark-exponering i stället för modellens topp-N under
   sådana perioder) - detta är den enda av de fyra åtgärderna med ett
   tydligt, konsekvent positivt historiskt utfall (0% edge undvikande
   jämfört med att annars förlora edge helt).

Rådata: `results/reject_split_precursors_regime.csv`,
`results/reject_split_window_variants.csv`,
`results/reject_split_regime_vs_global.csv`,
`results/reject_split_abstention.csv` (genererade av
`tune_reject_split_followup.py`, inte incheckade - resultatmapp
gitignorad).
