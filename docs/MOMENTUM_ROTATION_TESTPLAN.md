# Momentum – testplan för rotation, innehav och återköp

Skapad: 2026-07-26
Statusvärden: `EJ KÖRD`, `PÅGÅR`, `KLAR – FÖRKASTAD`, `KLAR – SHADOW`,
`KLAR – PRODUKTIONSKANDIDAT`, `PRODUKTION`.

> **OBS 2026-07-30:** denna fil försvann av misstag från `fortytwolocal`
> (troligen i samband med att hemkatalogen börjat användas för ett nytt,
> orelaterat projekt) och har återskapats från konversationskontext. Test
> 1-8:s ursprungliga resultat är oförändrade; Test 6 har fått ett nytt
> omvaliderings-avsnitt (se längst ner i specifikationen och körloggen)
> efter en omkörning mot den nya LambdaRank-baslinjen (Test 10,
> `momentum.local`).

## Gemensamt testprotokoll

Alla varianter ska jämföras med samma frusna produktionsbaslinje och använda
samma universum, priser, risklager och realistiska handels­kostnader.

Obligatoriska mätetal:

- CAGR
- Sharpe
- Max drawdown
- Omsättning
- Genomsnittlig innehavstid
- Antal återköp
- Missade storvinnare

Resultat ska redovisas för:

- Hela perioden
- Perioden före 2024
- Modern period från 2024
- Frusen holdout

Ingen variant flyttas till produktion enbart på förbättring i hela perioden.
Modern period/holdout, kostnadsrobusthet och tillräckligt antal händelser måste
också stödja förändringen.

## Testkö

| # | Test | Status | Resultat/artefakt | Beslut |
|---:|---|---|---|---|
| 1 | Köp-/behåll-hysteresis: köp Top-10, behåll till Top-15/Top-20 | KLAR – FÖRKASTAD | `/home/hannesb/test01_buy_hold_hysteresis.csv` | Historisk förbättring mot strikt Top-10 men negativ modern/holdout; långt sämre än produktion |
| 2 | Separata köp- och behållregler för momentum | KLAR – FÖRKASTAD | `/home/hannesb/test02_separate_momentum_hold_gate.csv` | Små historiska vinster men ingen konsekvent modern/holdout-förbättring |
| 3 | Bekräftad exit: utanför behållzon 2–3 veckor | KLAR – FÖRKASTAD | `/home/hannesb/test03_confirmed_exit.csv` | Hjälper veckochurn men når inte produktion och missar fler storvinnare |
| 4 | Cooldown efter exit: 2–6 veckor, undantag för extrem rank | KLAR – FÖRKASTAD | `/home/hannesb/test04_exit_cooldown.csv` | Lägre churn men negativ modern/holdout-alpha och fler missade vinnare |
| 5 | Opportunity-cost-byte: minst fem rankplatser eller score-gap | KLAR – FÖRKASTAD | `/home/hannesb/test05_opportunity_cost_swap.csv` | För låg absolut avkastning; score-gap håller inte tydligt i holdout |
| 6 | Intraperiod-utvärdering vid bruten tes | KLAR – SHADOW (omvaliderad 2026-07-30, se nedan) | `/home/hannesb/test06_intraperiod_thesis_break.csv` | Scorefall 20pp förbättrar modern/holdout och MaxDD men kostar helperiods-CAGR (ursprunglig dom, 2026-07-26) – **omvalideringen 2026-07-30 visar att `either`/`relative_10` nu är mer lovande än `score_drop_20`, se nedan** |
| 7 | Minsta innehavstid: 2–3 veckor, riskstop undantagen | KLAR – FÖRKASTAD | `/home/hannesb/test07_minimum_holding.csv` | Lägre historisk churn men negativ modern/holdout-effekt |
| 8 | Score-utjämning: EMA 2–4 veckor | KLAR – KRÄVER OMPRÖVNING (omvaliderad 2026-07-30) | `/home/hannesb/test08_score_smoothing.csv` | EMA2/EMA3 förbättrade alla perioder (ursprunglig dom, 2026-07-26) – **omvalideringen 2026-07-30 visar att holdout-förbättringen (+3,05pp) INTE håller, span4 nu marginellt bäst istället, se nedan** |
| 9 | Partiell nedskalning före full exit | KLAR – SHADOW (2026-07-30, se nedan) | `/home/hannesb/test09_partial_scaledown.csv` | Tydligt bättre än rå veckovis churn (instant_exit) på alla mått, men obevisat mot den riktiga kalenderbaslinjen |
| 10 | Åldringsbonus för innehav som levererar | KLAR – FÖRKASTAD (2026-07-30) | `/home/hannesb/test10_age_bonus.csv` | Hjälper bara i äldre data, flat-till-sämre i modern/holdout |
| 11 | Re-entry endast efter scoreförbättring från exitnivån | KLAR – SHADOW (2026-07-30) | `/home/hannesb/test11_reentry_threshold.csv` | Konsekvent modern+holdout-förbättring, ingen overfitting; högst prioriterad kandidat av Test 9-12 |
| 12 | Adaptiv holdingperiod efter score | KLAR – SHADOW (2026-07-30) | `/home/hannesb/test12_adaptive_holding.csv` | Stor förbättring mot svag baslinje men adaptive_8_4 sämre än baslinjen i holdout (overfitting); rekommendera endast adaptive_4_2 vid uppföljning |
| 13 | Vinstskydd: reducera men behåll kärnposition | KLAR – FÖRKASTAD (2026-07-30) | `/home/hannesb/test13_profit_trim.csv` | Kostar CAGR historiskt, ingen kompenserande fördel i modern/holdout |
| 14 | Regimberoende churn | KLAR – FÖRKASTAD (2026-07-30) | `/home/hannesb/test14_regime_churn.csv` | Försumbar historisk vinst, byter tecken till negativt i holdout |
| 15 | Portföljbytesbudget: högst 2–3 fullständiga byten per vecka | KLAR – FÖRKASTAD (2026-07-30) | `/home/hannesb/test15_swap_budget.csv` | Litet, inkonsekvent resultat, tecknet byter mellan budgetnivåerna i modern/holdout |

## Specifikationer

### 1. Köp-/behåll-hysteresis

Köp endast från Top-10 men behåll befintliga innehav tills de faller under
Top-15 respektive Top-20. Jämför båda med produktionsbaslinjen.

Resultat 2026-07-26:

- Produktionsbaslinje: CAGR 12,13%, Sharpe 1,06, MaxDD -21,41%,
  omsättning 4,64×/år och genomsnittlig innehavstid 15,61 veckor.
- Strikt veckovis Top-10: CAGR -1,91%, Sharpe -0,18, MaxDD -33,83%,
  omsättning 16,31×/år och innehavstid 2,87 veckor.
- Top-15-behållzon: CAGR 0,19%, Sharpe 0,07, MaxDD -31,19%,
  omsättning 15,62×/år och innehavstid 4,22 veckor.
- Top-20-behållzon: CAGR 2,70%, Sharpe 0,29, MaxDD -30,62%,
  omsättning 13,77×/år och innehavstid 5,42 veckor.
- Top-20 förbättrade hela perioden med 4,61 procentenheter CAGR mot strikt
  Top-10, men försämrade modern period med 4,57 procentenheter och frusen
  holdout med 3,24 procentenheter.
- Top-15/Top-20 gav 1 695/1 302 återköp över hela perioden och missade
  49/75 nya Top-10-episoder som därefter steg minst 30% på 13 veckor.
- Beslut: förkastad. Hysteresis hjälper den dåliga veckovisa churn-baslinjen
  historiskt men håller inte i modern data och når inte produktionsbaslinjen.

### 2. Separata köp- och behållregler för momentum

Behåll momentumgrinden för nya köp men använd lägre eller ingen momentumgräns
för redan ägda innehav.

Resultat 2026-07-26:

- Isolerad ordinarie 10%-grind: CAGR 12,60%, Sharpe 1,10, MaxDD -19,46%,
  omsättning 4,64×/år och genomsnittlig innehavstid 15,65 veckor.
- Sänkt behållgrind till 5%: +0,20 procentenheter CAGR över hela perioden,
  men -0,05 i modern period och -0,03 i frusen holdout.
- Ingen momentumgrind för ägda: +0,27 procentenheter CAGR över hela perioden
  och +0,21 i holdout, men -0,65 i modern period samt sämre historisk MaxDD
  än 10%-grinden.
- Återköp föll marginellt 315 → 311/304; omsättning och innehavstid ändrades
  endast lite. En missad storvinnare noterades för varianten utan behållgrind.
- Beslut: förkastad. Effekten är liten och byter tecken mellan perioderna.

### 3. Bekräftad exit

Sälj endast när aktien har legat utanför behållzonen två respektive tre veckor
i följd.

Resultat 2026-07-26:

- Bäst över hela perioden var Top-20 med tre veckors bekräftelse: CAGR 10,07%,
  Sharpe 0,79, MaxDD -27,18%, omsättning 9,66×/år och innehavstid 11,89 veckor.
- Top-15 med två veckors bekräftelse var bäst modernt: CAGR +0,56% och
  holdout -1,69%, jämfört med omedelbar Top-15-exit -1,93% respektive -4,04%.
- Bekräftelse minskade återköpen kraftigt men ökade missade storvinnare:
  bästa långsiktiga Top-20/3v hade 534 återköp och 118 missade storvinnare.
- Ingen variant slog produktionsbaslinjens 12,13% CAGR, Sharpe 1,06 och
  omsättning 4,64×/år. Beslut: förkastad som fristående produktionsregel.

### 4. Cooldown efter exit

Blockera återköp i 2, 4 och 6 veckor. Testa ett fördefinierat undantag för
extrem rank utan att välja gräns på holdout.

Resultat 2026-07-26:

- Cooldown 2/4/6 veckor sänkte omsättningen över hela perioden från
  16,74×/år till 14,82/14,15/13,57× och återköpen från 2 475 till
  2 084/1 848/1 694.
- CAGR förbättrades endast 0,34/0,39/0,29 procentenheter och förblev negativ.
- Alla cooldowns försämrade modern period eller holdout mot strikt Top-10.
  De missade 59/78/86 storvinnare över hela perioden.
- Beslut: förkastad. Churnvinsten kompenserar inte för blockerade vinnare.

### 5. Opportunity-cost-byte

Byt endast när den nya kandidaten är tydligt bättre än det svagaste innehavet.
Testa minst fem rankplaceringars gap samt ett kausalt score-gap.

Resultat 2026-07-26:

- Score-gap 0,10 var bäst över hela perioden: CAGR 0,62%, Sharpe 0,11,
  MaxDD -31,49%, omsättning 14,97×/år och 1 769 återköp.
- Mot strikt veckovis Top-10 förbättrade den CAGR med 2,39 procentenheter
  historiskt och 1,20 modernt, men endast 0,09 i holdout.
- Rankgap >5 försämrade holdout med 1,06 procentenheter. Samtliga varianter
  låg långt under produktionsbaslinjen och missade 28–43 storvinnare.
- Beslut: förkastad.

### 6. Intraperiod-utvärdering

Kontrollera om tesen brutits genom extrem relativ svaghet eller negativ
signalförändring och lämna då positionen tidigt.

Resultat 2026-07-26:

- Relativ svaghet på -10 procentenheter försämrade alla perioder.
- Scorefall på minst 20 percentilenheter sänkte total CAGR 12,13% → 9,67%,
  men förbättrade modern CAGR -4,47% → -1,67% och holdout -6,98% → -1,85%.
- MaxDD förbättrades totalt -21,41% → -18,51%, modernt -19,81% → -11,65%
  och i holdout -18,11% → -9,77%.
- Omsättning steg 4,64× → 5,15×/år, innehavstid föll 15,61 → 8,55 veckor
  och 31 historiska storvinnare missades, men bara två i modern period.
- Beslut: shadow. Tydlig modern riskförbättring, men den stora historiska
  CAGR-kostnaden hindrar produktion utan tröskelrobusthet/forwardstöd.

**Omvalidering 2026-07-30 (mot LambdaRank/Test 10-baslinjen, `test06_intraperiod_thesis_break.py`, se UTVECKLINGSLOGG.md #97):**

- `score_drop_20` (den ursprungligen utpekade regeln) håller INTE längre:
  frozen_holdout CAGR -0,32% mot baseline -0,29% (i praktiken oförändrat),
  modern CAGR 4,76% mot baseline 4,92% (SÄMRE, inte bättre som 2026-07-26).
- `either` (relativ ELLER scorefall) är nu den mest lovande regeln:
  frozen_holdout CAGR +1,44% mot baseline -0,29% (+1,74pp), bäst MaxDD
  (-13,64% mot -14,38%) – men kostar mest i helperiod (-0,30pp genomgående).
- `relative_10` visar den mest balanserade profilen: nästan kostnadsfri i
  helperiod/pre2024 (+0,16pp/+0,25pp, FAKTISKT POSITIVT) samtidigt som
  holdout förbättras (+0,91pp).
- Slutsats: grundmönstret (tesbrotts-exit hjälper risk/holdout mot liten
  CAGR-kostnad) håller under LambdaRank, men VILKEN regel som är bäst har
  ändrats – bevaka `either`/`relative_10`, inte längre bara `score_drop_20`.
  Fortsatt SHADOW, ingen produktionsändring.

### 7. Minsta innehavstid

Håll nya positioner minst två respektive tre veckor. Befintlig riskstop får
fortfarande sälja.

Resultat 2026-07-26:

- Två/tre veckors minimum förbättrade historisk CAGR mot strikt veckovis
  Top-10 med 0,48/1,05 procentenheter och minskade omsättning 16,79× till
  15,27/14,71× per år.
- Modern effekt var -0,31/+0,01 procentenheter och holdout -0,54/-0,63.
- Reglerna missade 47/77 storvinnare och låg långt under produktion.
- Beslut: förkastad.

### 8. Score-utjämning

Ranka på kausal EMA av modellscore med span 2, 3 och 4 veckor.

Resultat 2026-07-26:

- EMA2: CAGR 14,00%, Sharpe 1,18, MaxDD -16,68% mot isolerad span1
  12,27%, 1,03 och -23,29%.
- EMA3: högst balanserad effekt, CAGR 14,34%, modern förbättring +2,75
  procentenheter och holdout +3,05; MaxDD -15,85%.
- EMA4 gav högst total CAGR 14,56% men svagare modern/holdout-robusthet.
- EMA2/3 minskade total omsättning och återköp men missade 64/83 historiska
  storvinnare; modern riskjusterad portfölj förbättrades ändå.

**Omvalidering 2026-07-30 (mot LambdaRank/Test 10-baslinjen, `test08_score_smoothing.py`, se UTVECKLINGSLOGG.md #98): HOLDOUT-FÖRBÄTTRINGEN HÅLLER INTE.**
frozen_holdout negativ för ALLA spans (span1 -4,18%, span2 -4,22%, span3
-4,33%, span4 -4,18%) – skillnaderna är försumbara (≤0,15pp), den tidigare
"+3,05pp för EMA3"-effekten är BORTA. Modern period: span4 nu marginellt
bäst (+0,55pp), span2/span3 flata/svagt negativa. Rekommendation nedgraderad
från "shadow, redo för forwardvalidering" till "kräver omprövning – om EMA2
redan används i ett live-challenger-spår bör det flaggas för avstämning".
- Beslut: EMA2 och EMA3 stannar i shadow. EMA2 finns redan i Large-challengern;
  EMA3 läggs till som forskningsjämförelse. Ingen produktion innan samma test
  körts med exakt produktionssizing och forwardobservationer.

*(Omvalidering mot LambdaRank/Test 10-baslinjen pågår 2026-07-30, se UTVECKLINGSLOGG.md/niva3_status_handoff.md för resultat när klart.)*

### 9. Partiell nedskalning

Minska vikten stegvis innan full exit.

**Resultat 2026-07-30 (`test09_partial_scaledown.py`, mot LambdaRank/Test 10-baslinjen, se UTVECKLINGSLOGG.md #99):**

- `PartialScaledownBacktester`: en aktie som faller ur veckans Top-10 får
  sin viktmultiplikator DECAYAD (inte nollställd) tills den återkommer i
  Top-10 eller sjunker under floor=0,05 (full exit). Tre varianter:
  `instant_exit` (decay=1,0), `decay_50pct`, `decay_33pct`.
- Konsekvent förbättring på ALLA mått: all-period CAGR 2,18%→6,08%→**7,43%**
  (instant→decay50→decay33), Sharpe 0,26→0,56→0,67, MaxDD -33,91%→-31,90%→
  **-31,32%**. Modern -1,93%→-0,92%→**-0,73%**. Holdout -4,36%→**-3,43%**→-3,77%.
  Turnover/rebuys kraftigt ned (1036→646→644).
- **VIKTIG RESERVATION:** `instant_exit`-baslinjen är RÅ VECKOVIS Top-10
  (samma svaga baslinje som Test 1 redan avfärdade, CAGR ~2%), INTE
  produktionens riktiga 13-veckors kalenderombalansering (CAGR ~9-9,5%
  enligt Test 6/8:s `production_calendar`). Decay_33pct:s bästa siffra
  (7,43%) ligger fortfarande UNDER kalenderbaslinjen.
- Beslut: SHADOW. Löser tydligt "rå veckovis churn"-problemet, men obevisat
  om det slår den FAKTISKA produktionsbaslinjen – kräver uppföljande test
  (decay-variant mot `production_calendar`, inte bara mot `instant_exit`)
  innan produktionsbeslut.

### 10. Åldringsbonus

Öka trögheten före exit för äldre innehav som fortsatt levererar.

**Resultat 2026-07-30 (`test10_age_bonus.py`, se UTVECKLINGSLOGG.md #100):**

- `AgeBonusBacktester`: aktie utanför strikt top-10 behålls om hållen
  >= min_age_weeks OCH lönsam sen köp OCH inom bonus_keep_rank.
- all/pre2024: modesta förbättringar (+0,74pp/+0,94pp CAGR bäst variant).
- modern: ALLA varianter SÄMRE än strict_top10 (-0,04 till -0,55pp).
- frozen_holdout: i praktiken oförändrat eller sämre (±0,00 till -0,64pp).
- Beslut: FÖRKASTAD. Till skillnad från Test 9 hjälper detta bara i äldre,
  mindre relevant data – ingen robust vinst i modern/holdout.

### 11. Re-entry endast efter förbättring

Återköp endast när score förbättrats en fördefinierad andel från exitnivån.

**Resultat 2026-07-30 (`test11_reentry_threshold.py`, se UTVECKLINGSLOGG.md #102):**

- `ReentryThresholdBacktester`: en aktie som lämnar Top-10 får sin
  `selection_rank` vid exit-tillfället sparad; återköp blockeras tills
  aktuell `selection_rank` >= exit-rank + `threshold` (percentilenheter,
  0-1-skala). Tre varianter: `strict_top10` (kontroll), `threshold_5pp`,
  `threshold_10pp`.
- Motsatt mönster mot Test 12: kostar historisk CAGR men förbättrar
  KONSEKVENT både modern och holdout för båda trösklarna. all: 2,86% →
  2,49% → 1,12%. modern: **-3,43%** → **-1,34%** → **-1,00%** (bäst).
  frozen_holdout: **-6,63%** → **-3,14%** → **-3,10%** (bäst). Turnover
  kraftigt ned.
- Beslut: SHADOW – mest konsekventa modern+holdout-förbättringen av hela
  Test 9-12-batchen, inget overfitting-tecken. Högst prioriterad kandidat
  för uppföljande test mot `production_calendar`.

**UPPFÖLJNING 2026-07-30 (`tune_reentry_threshold_production.py`, se
UTVECKLINGSLOGG #149) – KLAR, kört mot RIKTIGA `MomentumBacktester`/
`REBALANCE_WEEKS=52`, inte längre bara `TrackedBacktester`:** bekräftar och
skärper originalfyndet avsevärt. 10%-tröskeln: holdout CAGR +2,0%→+4,2%
(fördubblad), Sharpe 0,42→1,08 (mer än fördubblad), MaxDD -7,3%→-3,3%
(nästan halverad), mot en dev-kostnad på ~2,4pp CAGR. 5%-tröskeln visar
samma riktning, svagare. 297 (10%)/236 (5%) faktiskt blockerade återköp –
en genuint bindande mekanism. **Status höjd: "redo för produktionsövervägande"**,
inte längre bara SHADOW – men fortfarande bara EN holdout-period uppmätt,
verifiera mot small-segmentet och/eller en oberoende period innan
implementationsbeslut.

### 12. Adaptiv holdingperiod

Låt högre score ge längre tillåten innehavstid.

**Resultat 2026-07-30 (`test12_adaptive_holding.py`, se UTVECKLINGSLOGG.md #101):**

- `AdaptiveHoldingBacktester`: en aktie som faller ur Top-10 får en
  "grace"-period (tillåtna sammanhängande veckor utanför Top-10 innan full
  exit) satt vid KÖPTILLFÄLLET utifrån entry-scorepercentilen (>=90:e →
  `min_high` veckor, 70–90:e → `min_mid`, annars 0). Tre varianter:
  `strict_top10` (kontroll), `adaptive_4_2`, `adaptive_8_4`.
- **Två buggar hittade och fixade under körningen** (se UTVECKLINGSLOGG.md
  #101 för fulla detaljer): (1) grace mättes ursprungligen fel från
  köptillfället istället för exit-tillfället; (2) `prob_up` visade sig vara
  en KONSTANT 0,5 för alla aktier under LambdaRank (samma kända "Kelly/
  prob_up-mismatch" som redan är olöst) – bytt mot `selection_rank`, som är
  informativ. **Relevant för alla framtida skript som använder `prob_up`
  för trösklar/sortering – kolumnen är obrukbar under nuvarande modell.**
- all: strict_top10 CAGR 2,71% → adaptive_4_2 7,47% (+4,76pp) →
  adaptive_8_4 7,88% (+5,17pp, bäst). pre2024: 3,85% → 9,15% → 9,72%
  (bäst). modern: -2,70% → **-0,49%** (adaptive_4_2 bäst) → -0,93%.
  frozen_holdout: -4,96% → **-3,77%** (adaptive_4_2 bäst, enda som
  förbättrar) → **-5,53%** (adaptive_8_4 SÄMRE än baslinjen).
- Beslut: SHADOW, samma reservation som Test 9 (svag rå-veckovis baslinje,
  ej produktionens kalenderbaslinje) PLUS tydligt overfitting-tecken:
  `adaptive_8_4` bäst historiskt men sämst i modern/holdout. Rekommendera
  endast `adaptive_4_2` vid ev. uppföljning mot `production_calendar`.

### 13. Vinstskydd utan total exit

Efter stor uppgång reduceras en del av positionen medan en kärna behålls.

**Resultat 2026-07-30 (`test13_profit_trim.py`, se UTVECKLINGSLOGG.md #103):**

- `ProfitTrimBacktester`: en hållen aktie som är upp minst `trim_threshold`
  sen köp får sin vikt skalad till `core_fraction` av normal position-vikt
  (kärna behålls, säljs inte helt), oavsett Top-10-status. Frigjort kapital
  omallokeras INTE. Tre varianter: `strict_top10` (kontroll),
  `trim_30pct_core50`, `trim_50pct_core50`.
- Genomgående negativt eller platt. all: 2,68% → 1,39% (-1,29pp) → 1,79%
  (-0,88pp). pre2024: -1,52pp/-1,09pp. modern och frozen_holdout: i
  praktiken oförändrade åt båda hållen (±0,1-0,2pp).
- Beslut: FÖRKASTAD. Ren kostnad utan mätbar fördel någonstans – trolig
  orsak: frigjort kapital lämnas oinvesterat istället för att omallokeras.

### 14. Regimberoende churn

Öka trögheten i sidledes marknad och minska den i trendmarknad.

**Resultat 2026-07-30 (`test14_regime_churn.py`, se UTVECKLINGSLOGG.md #104):**

- `RegimeChurnBacktester`: återanvänder basklassens egen kausala
  regimklassificering (`classify_regimes`) – i "sidledes" behålls innehav
  inom en bredare `sideways_keep_rank`, i "bull"/"bear" gäller strikt
  Top-10. Tre varianter: `strict_top10`, `sideways_keep15`,
  `sideways_keep20`.
- Små, försumbara effekter. all: +0,42pp/+0,49pp. pre2024: +0,50pp/+0,63pp.
  modern: ±0,04/-0,17pp (försumbart). frozen_holdout: **-0,13pp/-0,51pp**
  (negativt, keep20 sämst i just den viktigaste perioden).
- Beslut: FÖRKASTAD. Liten historisk vinst som byter tecken till negativt i
  holdout – ingen robust modern/holdout-fördel.

### 15. Portföljbytesbudget

Begränsa fullständiga byten till två respektive tre per vecka.

**Resultat 2026-07-30 (`test15_swap_budget.py`, se UTVECKLINGSLOGG.md #105):**

- `SwapBudgetBacktester`: högst `max_swaps` fullständiga exit+entry-byten
  per vecka, prioriterat sämst rankad innehav mot bäst rankad ny kandidat;
  överskott skjuts upp. Tre varianter: `strict_top10` (kontroll),
  `budget_3`, `budget_2`. **Bugg hittad och fixad**: första körningen gav
  0 trades i ALLA varianter (inkl. kontroll) eftersom modellen krävde ett
  matchat exit+entry-par för varje "byte" – en tom portfölj kunde då
  aldrig fyllas. Fixat genom att skilja på gratis köp i lediga platser och
  budgetbegränsade byten i en redan full portfölj.
- Litet, inkonsekvent resultat efter fixen. all: 3,88% → 4,15% → 4,21%
  (svagt positivt, konsekvent riktning). modern/frozen_holdout: tecknet
  BYTER mellan budget_3 och budget_2 (t.ex. holdout: strict -5,81% →
  budget_3 -6,15% SÄMRE → budget_2 -5,73% försumbart bättre).
- Beslut: FÖRKASTAD. Tecknet växlar mellan budgetnivåerna i de mest
  relevanta perioderna – tyder på brus, inte en robust effekt.

**Med detta är Test 9-15 (hela den ursprungliga testkön) klara.** Test
11 (re-entry-tröskel) och Test 12 (adaptiv holdingperiod, endast
`adaptive_4_2`) är de enda SHADOW-kandidaterna värda uppföljning mot
`production_calendar`; övriga (9, 10, 13, 14, 15) förkastade eller kvar i
sin ursprungliga SHADOW/kräver-omprövning-status från tidigare i tabellen.

## Tidigare relaterade tester

- Large vecka-4 innehavsutvärderare, full portföljsimulering:
  `KLAR – FÖRKASTAD`. Hela perioden +0,08 procentenheter CAGR, modern period
  -0,01 procentenheter, frusen holdout +0,06 procentenheter och endast 30
  rotationer. Artefakt:
  `/home/hannesb/large_week4_portfolio_backtest.csv`.
- Sellwatch nivå 3 med direkt ersättning och cooldown:
  `KLAR – FÖRKASTAD`. Negativt över hela perioden och otillräckligt robust
  stöd i holdout.

## Körlogg

| Datum | Test | Händelse |
|---|---:|---|
| 2026-07-26 | – | Testplan sparad; samtliga nya tester väntar på körning. |
| 2026-07-26 | 1 | Full portföljsimulering klar. Top-15 och Top-20 förkastade. |
| 2026-07-26 | 2 | Separata momentumgrindar klara och förkastade. |
| 2026-07-26 | 3 | Bekräftad exit startad. |
| 2026-07-26 | 3 | Sex bekräftelsevarianter klara och förkastade. |
| 2026-07-26 | 4 | Cooldown-test startat. |
| 2026-07-26 | 4 | Cooldown 2/4/6 veckor klart och förkastat. |
| 2026-07-26 | 5 | Opportunity-cost-byte startat. |
| 2026-07-26 | 5 | Rank- och score-gap klara och förkastade. |
| 2026-07-26 | 6 | Intraperiod-utvärdering startad på kausala veckopunkter. |
| 2026-07-26 | 6 | Scorefall 20pp flyttat till shadow; relativ svaghet förkastad. |
| 2026-07-26 | 7 | Minsta innehavstid startad. |
| 2026-07-26 | 7 | Minsta innehavstid 2/3 veckor klar och förkastad. |
| 2026-07-26 | 8 | EMA-score 2–4 veckor startat. |
| 2026-07-26 | 8 | EMA2/EMA3 klara och kvar i shadow. |
| 2026-07-26 | 9 | Partiell nedskalning startad. |
| 2026-07-30 | – | **Fil återskapad efter oavsiktlig borttagning på fortytwolocal (arbetet flyttat till momentum.local sen tidigare).** |
| 2026-07-30 | 6 | Omvaliderad mot LambdaRank/Test 10-baslinjen (`momentum.local`). `score_drop_20` håller inte längre, `either`/`relative_10` mer lovande nu. Kvar i SHADOW. Se UTVECKLINGSLOGG.md #97. |
| 2026-07-30 | 8 | Omvaliderad mot LambdaRank/Test 10-baslinjen. Holdout-förbättringen (+3,05pp) håller INTE, span4 nu marginellt bäst istället för EMA2/3. Nedgraderad till "kräver omprövning". Se UTVECKLINGSLOGG.md #98. |
| 2026-07-30 | 9 | Nytt skript skrivet från spec och kört. Tydligt bättre än rå veckovis-baslinje på alla mått, men obevisat mot riktiga kalenderbaslinjen. SHADOW. Se UTVECKLINGSLOGG.md #99. |
| 2026-07-30 | 10 | Nytt skript skrivet från spec och kört. Hjälper bara i äldre data, flat-till-sämre i modern/holdout. Förkastad. Se UTVECKLINGSLOGG.md #100. |
| 2026-07-30 | 12 | Nytt skript skrivet från spec och kört (kört före Test 11 av prioriteringsskäl). Två buggar hittade och fixade under körningen (grace mätt fel + `prob_up` konstant 0,5 under LambdaRank). Stor förbättring mot svag baslinje men adaptive_8_4 overfittar (sämre i holdout). SHADOW, rekommendera endast adaptive_4_2. Se UTVECKLINGSLOGG.md #101. |
| 2026-07-30 | 11 | Nytt skript skrivet från spec och kört. Konsekvent modern+holdout-förbättring för båda trösklarna, inget overfitting-tecken. SHADOW, högst prioriterad kandidat av Test 9-12. Se UTVECKLINGSLOGG.md #102. |
| 2026-07-30 | 13 | Nytt skript skrivet från spec och kört. Kostar CAGR historiskt, ingen fördel i modern/holdout. Förkastad. Se UTVECKLINGSLOGG.md #103. |
| 2026-07-30 | 14 | Nytt skript skrivet från spec och kört (återanvände basklassens regimklassificering). Försumbar historisk vinst, negativt i holdout. Förkastad. Se UTVECKLINGSLOGG.md #104. |
| 2026-07-30 | 15 | Nytt skript skrivet från spec och kört. Bugg hittad och fixad (tom portfölj kunde aldrig fyllas). Litet, inkonsekvent resultat efter fix. Förkastad. Se UTVECKLINGSLOGG.md #105. **Test 9-15 (hela ursprungliga kön) klara.** |
