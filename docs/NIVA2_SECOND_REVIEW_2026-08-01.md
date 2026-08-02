# Second review – Nivå 2: modell, target, innehavstid och beslutskedja

Datum: 2026-08-01. Scope: Large i första hand; Small får aldrig ärva slutsats
utan separat PIT-/segmentvalidering. Produktion ändras inte av denna review.

## Sammanfattande dom

Nivå 2 är **inte slutgiltigt validerad som ett enda modellbeslut**. Historiken
har blandat minst sex separata val: modellobjective, targethorisont, embargo,
rotationsfrekvens, scorekalibrering/sizing och portföljfilter. Flera svep ändrade
flera av dessa samtidigt och valde dessutom på den gamla holdouten. Därför går
det inte att säga att 52v+LambdaRank är den garanterat bästa arkitekturen.

Det betyder inte att produktionen ska rullas tillbaka. Den sparade produktionen
är klart bättre än de statiska challengers under de senaste fem åren. Rätt dom
är därför: behåll produktionen tills vidare, frys binary raw-score som challenger,
och bygg om Nivå 2 som en faktoriserad DEV/OOF-turnering med ny forwarddata.

## Vad som faktiskt är bevisat

1. SR-9 reproducerar nu produktionens historiska NAV deterministiskt över 814
   veckor, max avvikelse 0,000761 bp. Den gemensamma backtestmotorn är därmed en
   giltig jämförelsegrund när hela Large-kontraktet appliceras.
2. På identiska 25 DEV/OOF-splits med 52v target/rotation vann binary objective
   portföljmåttet över LambdaRank: 8,0 % mot 6,7 % CAGR och Sharpe 0,96 mot 0,83.
3. I full output/sizing-kedja på gemensam OOF 2016–2022 vann binary 17,8 %/1,33
   mot LambdaRank 15,3 %/1,14. Binary raw score kollapsade inte: median 124 unika
   scores per datum och medianplatå 1,59 %.
4. Senaste fem årens diagnostik 2021-07-27–2026-07-27 gav binary -0,6 % CAGR,
   statisk LambdaRank -2,4 %, sparad faktisk produktion +5,8 % och XACT Sverige
   +7,47 %. Binary är alltså +1,8 pp/år bättre än den jämförbara statiska
   LambdaRank-challengern, men -6,4 pp/år sämre än faktiskt sparad produktion och
   -8,1 pp/år efter index. Ingen challenger är redo att ersätta produktion.
5. Universumet innehåller teoretiskt tillräckligt med vinnare (#56/facit), men
   facit använder framtidsdata och anger bara ett tak; det bevisar inte att en
   realiserbar modell kan fånga gapet.

## Vad som inte längre är säkert bevisat

### 52 veckor som target

- #30 var helt ogiltigt på grund av cache som återanvände fel targethorisont.
- #31 rättade cachen och fann att Large 52v var sämre än 13v i den dåvarande
  pre-LambdaRank-modellen, medan Small 52v vann.
- #124 fann senare att 52v vann monotont efter LambdaRank, men testet kördes före
  den fullständiga kontraktsgaten och beskrivs självt som endast partiellt
  patchat. Dessutom användes holdout som avgörande jämförelse.
- Slutsats: 52v är en rimlig produktionstatus men inte ett slutgiltigt isolerat
  targetval. Resultatet kan bero på objective och portföljfrekvens.

### 52 veckor som innehavstid/rotation

Äldre rotationssvep för 13v-modellen fann att 13v rotation vann. Senare tester
kopplade target, embargo och rotation till samma värde. Det isolerar inte om
vinsten kommer från vad modellen lär sig eller hur länge portföljen håller.
Staggered 52v-kohorter och fast-target/varierad rotation är ännu inte avgjorda
genom det nya kontraktet.

### LambdaRank som modellobjective

Adoption #68 byggde på IC/spread, inte slutlig topp-15-portfölj. Den korrigerade
turneringen visar att LambdaRank kan vinna generell rank-IC men förlora netto-
CAGR/Sharpe. Modellobjective ska därför väljas på netto-top-15, inte IC ensamt.

### Den gamla binary-modellen

Den gamla kalibrerade modellen gav stora 0,5-platåer och är fortsatt förkastad.
Den nya `binary_raw_v1` är en annan kandidat: råscore, ingen isotonic-kollaps,
full upplösningsgate och låst kontrakt. De två får inte blandas ihop.

## Identifierade confounders i Nivå 2

1. **Target–rotation-confound:** FORWARD/EMBARGO/REBALANCE ändrades tillsammans.
2. **Objective–horisont-confound:** flera horisontresultat tillhör olika
   modellgenerationer (binary före migration, LambdaRank efter).
3. **Kalibrering–ranking-confound:** gammal `prob_up` kollapsade trots varierande
   raw score; ranking och Kelly-sizing använde olika scorebegrepp.
4. **Portföljkontrakt:** N=10/15, marknadsexponering och sektorkarta har varierat.
5. **Holdout selection:** flera beslut valdes med den nu forskningsexponerade
   tvåårsholdouten.
6. **Staleness/retraining:** senaste fem år visar att statiskt extrapolerade
   splitmodeller kan vara mycket sämre än den faktiskt regenererade produktionen.
7. **Benchmarkmetod:** index får inte gå genom aktiesektortak; detta hittades och
   rättades i binary-replayen.
8. **Segmentöverföring:** Large- och Small-resultat har olika tecken och får inte
   dela target/rotationbeslut utan eget test.

## Modellspår som Nivå 2 tidigare underskattat

- Raw-score binary/pointwise ranking.
- Regression av excessavkastning.
- Upper-tail listwise loss som prioriterar topp-15 framför hela ordningen.
- Tvåsteg: sannolikhet/screen först, rank inom godkänd övre halva därefter.
- Residualranker som kompletterar huvudmodellens fel i toppkvantilen.
- Regim-/segmentexperter, men endast med tillräckligt sampel och aktiespecifika
  interaktioner; ren marknadsregim är konstant inom LambdaRank-gruppen.
- Staggered 52v-kohorter och rank-hysteresis som portföljarkitektur, inte ny alpha.
- 52v som ägarsignal med 13v endast som tie-break; preliminärt lovande men måste
  köras om genom full kontraktsgate.

## Obligatorisk faktoriserad omtestmatris

Kör i följande ordning och stoppa vid gate-fel:

1. **Target endast:** binary med 13v/52v target, båda exekverade med samma fasta
   52v portföljregel. Sekundär 26v är kontroll, inte gridvinnare.
2. **Rotation endast:** vinnande frusna targetmodell exekveras med 13v respektive
   52v samt 4/13 staggered 52v-kohorter. Ingen omträning mellan armar.
3. **Objective endast:** binary, LambdaRank, upper-tail, regression och tvåsteg
   på vinnande target/rotation, identiska splits/budget/features.
4. **Score/sizing endast:** likaviktat raw-rank mot empiriskt DEV-kalibrerad
   sizing. Ingen isotonic-kalibrering får styra rangordningen.
5. **Pipeline-ablation:** raw modell → rank-EMA → eligibility/gate → sizing →
   LSTM-blend, ett led i taget, med top-15-Jaccard och nettoeffekt per led.
6. **Retraining/staleness:** fast modell mot schemalagd omträning; rapportera
   alpha som funktion av veckor sedan senaste fit.
7. **Segmentreplikering:** först när Large-valet är låst körs exakt samma protokoll
   separat för Small efter godkänd PIT-fundamentatäckning.

## Beslutsprotokoll

- Endast nested DEV/OOF väljer arm. Gammal holdout visas diagnostiskt men har
  noll rösträtt.
- Primärmål: netto-alpha mot passiv korrekt benchmark; därefter Sharpe och MaxDD.
- Rapportera split-/årsmajoritet, turnover, kostnader, Jaccard och scoreupplösning.
- Multipeltestledgern räknar varje arm, krasch och omkörning.
- En vinnare fryses utan mer tuning och måste vinna på ny paper/forwardperiod.
- Ingen produktion ändras om vinnaren bara förbättrar IC eller gammal holdout.

## Nuvarande driftsbeslut

1. Behåll nuvarande produktion tills vidare.
2. `results/challengers/binary_raw_v1.joblib` är frusen shadow, uttryckligen
   `production=False` och `tuning_locked=True`.
3. Publicera/journalför shadowval från
   `results/challengers/binary_raw_v1_shadow_signals.csv` parallellt framåt.
4. Återöppna produktionsbyte först efter den faktoriserade matrisen och ny
   forwardevidens. Senaste fem årens diagnostik är en varning mot omedelbart byte.

## Genomfört efter review: isolerat targettest

Steg 1 är genomfört utan gammal holdout. Binary 13v och 52v använde exakt samma
65 146 feature-rader, featurehash, 21 walk-forward-splits, 52v embargo och full
portföljpipeline med fast 52v rotation. Positiv klass var 33,56 % för båda;
targetetiketterna var 70,89 % överens.

- Binary 13v target: CAGR 25,6 %, Sharpe 1,80, MaxDD -19,3 %.
- Binary 52v target: CAGR 22,8 %, Sharpe 1,63, MaxDD -19,2 %.
- XACT Sverige samma OOF-fönster: CAGR 15,17 %, Sharpe 0,90, MaxDD -28,2 %.

13v-targeten vinner steg 1 med +2,8 pp CAGR och +0,17 Sharpe. Detta betyder inte
13v rotation. Nästa steg håller 13v-targetmodellen frusen och isolerar
13v/52v/staggered exekvering. Första försöket stoppade före träning på namnlöst
cacheindex; schemat normaliserades och den giltiga omkörningen ovan ersätter det.

`results/niva2_method_compliance.json` är **NOT_PRODUCTION_READY**. Targetgaten
är PASS, men rotation/staggered, objective-omtest på vinnande target/rotation,
sizing, pipelineablation, retraining cadence och minst 52 veckors oberoende
forward återstår i den ordningen. Gamla objective-turneringen är `STALE_ORDER`.

## Genomfört steg 2: isolerad rotation på frusen stage 01

Hashkedjan verifierades före körning. Samma frusna binary-13v-targetsignaler
exekverades utan omträning eller holdout: calendar52 25,6 % CAGR/1,80 Sharpe/
-19,3 % MaxDD (vinnare); staggered4 22,5/1,54/-22,2; staggered13
21,8/1,50/-22,1; calendar13 21,4/1,49/-21,1.

Arkitekturen inför nästa steg är fryst till **13v target + 52v calendar
rotation** i `results/niva2_stages/02_rotation_isolation.json`. Nästa steg är
objective-turnering på exakt denna target/rotation.

`niva2_stage_control.py` SHA-256-hashar varje artefakt och föräldramanifest.
Nästa stage vägrar starta om tidigare artefakter ändrats. Rollback sker till
senaste `FROZEN_PASS`.

## Genomfört steg 3: objective på låst target och rotation

Fem objectives tränades oberoende på samma 65 146 feature-rader, 21 purgade
splits, 13v target och calendar52-portfölj. LambdaRank vann med 26,2 % CAGR,
1,89 Sharpe och -20,1 % MaxDD. Binary gav 25,6/1,80/-19,3, tvåsteg
24,9/1,78/-17,8, upper-tail 22,5/1,65/-18,4 och regression
21,7/1,59/-21,3. Gammal holdout användes inte.

Det korrigerar den tidigare slutsatsen från turneringen på 52v target: när
target och rotation isoleras i rätt ordning vinner LambdaRank, men bara med
+0,6 pp CAGR och +0,09 Sharpe mot binary. Därför fryses LambdaRank som vinnare
för nästa metodsteg utan påstående att objectivebytet ensamt skapat huvuddelen
av alpha. Stage 03 är hashkedjad `FROZEN_PASS`. Nästa steg är enbart
score/sizing på denna låsta kandidat; produktion får ännu inte ändras.

## Genomfört steg 4: score/sizing på låst Stage-03-urval

Urvalet hölls identiskt i alla 13 armar; bara vikterna ändrades. Korrelations-
filtret stängdes av inom detta isoleringstest eftersom dess viktberoende annars
kan byta portföljmedlemmar. Ingen holdout användes. Vinnaren var 75 %
inverse-vol, 25 % likavikt: CAGR 27,1 %, Sharpe 1,97, MaxDD -19,8 %. Likavikt
gav 27,0/1,90/-20,0 och full inverse-vol 27,0/1,97/-20,0. Raw-rank och kausalt
empirisk rank-sizing gav ingen förbättring och förkastas.

Stage 04 är hashkedjad `FROZEN_PASS`. Nästa isolerade test är pipelineablation
på LambdaRank + 13v target + calendar52 + inverse-vol 0,75. Skillnaden mot
likavikt är liten i CAGR, så sizing ska beskrivas som riskjustering och inte som
en stor ny alphakälla.

## Genomfört steg 5: sekventiell pipelineablation

Utan omträning/holdout gav rå LambdaRank 20,6 % CAGR och 1,49 Sharpe. Rank-EMA
gav exakt samma resultat och topp-15 (median Jaccard 1,0), alltså ingen uppmätt
inkrementell edge. Eligibility/momentumgrinden gav den stora förbättringen till
27,0 %/1,90, ändrade urvalet materiellt (Jaccard 0,50) och sänkte rotationens
omsättning. Inverse-vol 0,75 höjde till 27,1 %/1,97. Korrelationsfiltret sänkte
till 26,7 %/1,94 och förkastas.

LSTM-blend var inte del av den låsta Stage-03-objectivevinnaren; att lägga till
den här skulle kräva ny modellträning och bryta isoleringen. Stage 05 fryser
därför eligibilitygrind + inverse-vol 0,75 utan korrelationsfilter. Nästa steg
är retraining/staleness, följt av oberoende forwardvalidering.

## Genomfört steg 6: retraining cadence och staleness

Kausalt omtest utan holdout gav exakt 27,1 % CAGR/1,97 Sharpe för refit var
13:e, 26:e och 52:e vecka. Calendar52 gör att samtliga tre har ny fit på varje
handelsrotation, så tätare fit kan inte tillskrivas alpha. Vid 104v cadence var
modellen 52 veckor gammal varannan rotation och resultatet föll till
24,9 %/1,82. Statisk modell föll till 16,1 %/1,22.

Metodbeslutet är årlig omträning precis före calendar52-rotationen. Tätare
modelluppdatering är tillåten för diagnostik men inte motiverad av portfölj-
endpointen. Stage 06 är `FROZEN_PASS`; återstående produktionsbevis kan inte
backtestas fram utan måste samlas på minst 52 veckors ny forwardperiod med en
verklig årsrotation.

## Stage 07 startad: oberoende forward

Forwardperioden är förregistrerad från 2026-07-27 till tidigast 2027-07-26 med
52 observationer och en verklig årsrotation som minimikrav. Kandidat, samtidig
produktion och XACT Sverige startar på 100 000 kr. Månadsinsättningar separeras
från TWR. Gammal holdout har fortsatt noll rösträtt och inga parametrar får
ändras retroaktivt.

Stage 07 är `ACTIVE_FORWARD`, inte produktionsgodkänd. Dess hashmanifest fryser
protokoll, modell och startsignaler; ordet `FROZEN_PASS` i manifestet avser bara
att preregistreringen är tekniskt intakt. Två felaktiga retrostarter på
2025-07-28 arkiverades och ogiltigförklarades innan resultat kunde beräknas.

Veckovis insamling körs automatiskt måndagar 22:15 via användartimer. Den
hashfrysta uppdateraren är append-only, fail-closed vid saknade priser och kan
inte själv godkänna modellen. Vid årsgränsen sätts `ROTATION_DUE`; en explicit
fryst omträning/rotation krävs innan observationerna kan fortsätta som en ny
kohort.
