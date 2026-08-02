# Second review av tidigare tester – 2026-08-01

## Slutsats

Tidigare tester stödjer inte fler breda parametergridar. De mest lovande nya
ingångarna är i stället **villkorade mekanismer**: när kort momentum ska komplettera
52 veckor, när en exit verkligen är informativ och när modellens osäkerhet ska
ändra signaltyp snarare än exponering. Resultat mellan gamla skript är inte fullt
jämförbara: deras rapporterade baslinjer varierar kraftigt. Alla uppföljningar
måste därför gå genom en gemensam produktionsbacktester och en frusen DEV-period.

Den gamla holdouten är forskningsexponerad. Den får visas som känslighetsanalys,
men får inte välja hypotes, tröskel eller produktionsbeslut.

## Nya högprioriterade testfamiljer

### SR-1 – Villkorad 52v + 13v, inte statisk blend

**Fynd:** 52v är stark huvudsignal. En statisk 20% 13v-overlay förbättrade DEV/OOF,
medan ett äldre ensembletest gav noll nettovinst och hade `n=0`/NaN i sin IC-del.

**Ny hypotes:** 13v tillför information främst när 13v accelererar i samma riktning
som 52v eller när 52v-rankingen är osäker. Testa endast tre förregistrerade regler:

1. 20% 13v bara när 13v- och 52v-rank är överens.
2. 20% 13v bara vid positiv 13v-rankförändring.
3. 13v används som tie-break inom översta 52v-kvantilen, inte i hela universumet.

Primärmål: median top-decile edge och netto-CAGR på DEV. Sekundärt: omsättning och
stabilitet per år/split. Ingen ny viktgrid efter att reglerna sett resultaten.

### SR-2 – Osäkerhet som modell-/horisontväxel

**Fynd:** LGBM/LSTM-oenighet som filter eller nedviktning var sämre än baslinjen
och nästan likvärdig med slumpkontrollen.

**Ny hypotes:** oenighet säger inte ”äg mindre”, utan ”den långsiktiga rankingen är
osäker”. Testa om hög oenighet förbättras av 13v tie-break, högre re-entry-krav
eller att behålla befintligt innehav i stället för att rotera. Jämför mot en
slumpmässig grupp med exakt samma antal blockerade affärer.

### SR-3 – Regiminteraktioner som faktiskt kan påverka LambdaRank

**Fynd:** `tune_regime_feature` gav exakt samma IC i samtliga splits. En ren
marknadsregim är konstant inom varje veckas rankinggrupp och kan därför inte
rangordna aktier mot varandra.

**Ny hypotes:** använd interaktioner, exempelvis regim × beta, regim × residual-
momentum, regim × volatilitet och regim × likviditet. Alternativt två separata
rankers, men endast om varje regim har tillräcklig effektiv stickprovsstorlek.
Först ett DEV-only IC/ablationstest; ingen portföljgrid innan signalvärde finns.

### SR-4 – Re-entry efter orsak, inte generell ranktröskel

**Fynd:** 5–10 procentenheters re-entry-krav sänkte DEV-CAGR men förbättrade den
gamla holdoutens Sharpe/MaxDD. Den generella regeln blockerade 236–297 återköp.

**Ny hypotes:** effekten kan komma från ett fåtal dåliga återköp efter trendbrott,
inte från all re-entry. Testa separata kohorter: frivillig rankrotation, drawdown-
exit, trendexit och likviditets-/datastopp. Jämför fast cooldown 4/13 veckor mot
förbättrad rank, och kräv positiv effekt i majoriteten av DEV-år/splits.

### SR-5 – Drawdown-exit med rankbekräftelse och omedelbar ersättare

**Fynd:** -40% cash/rotate gav bara 22 triggers men något bättre riskmått; tajta
ATR-stoppar förstörde CAGR genom whipsaw/cash-drag. Rotation var bättre än kontant.

**Ny hypotes:** exit ska kräva både positionsdrawdown och försämrad tvärsnittsrank.
Förregistrera -30/-40% och rank under topp 30/50%; köp omedelbart bäst rankad
ersättare. Rapportera eventnivå, bidrag per år och resultat med varje enskilt event
leave-one-out så att ett fåtal krascher inte skapar falsk edge.

### SR-6 – Vinsthemtagning som sällsynt tillståndsmaskin

**Fynd:** fasta take-profit-nivåer är fel; vinnare fortsatte i snitt. Den enda
negativa gruppen var ”melt-up + trendbrott”, men bara sju event och därför inte
beslutsduglig.

**Ny hypotes:** armera efter extrem sektorrelativ uppgång och sälj först efter
bekräftelse från peak-drawdown + rankförsämring. Gör matched-control-eventstudie
mot bolag med samma storlek, sektor, volatilitet och tidigare uppgång. Ingen
tröskel får väljas på de sju gamla eventen.

### SR-7 – Nykvalificerade signaler som separat sleeve

**Fynd:** nykvalificerade hade högre medianavkastning, positiv andel och lägre
spridning än etablerade över 13/26/52 veckor. Detta är ett av de tydligaste
obehandlade fynden, men kan vara påverkat av survivorship och dagens universum.

**Ny hypotes:** en liten, kapacitetsbegränsad sleeve för nya topp-N-inträden eller
en `newly_qualified × rank_change`-feature. Först måste kohorten byggas ur PIT-
universum. Testa därefter 0/10/20% sleeve på DEV med samma totalantal innehav.

### SR-8 – Riskjusterat momentum endast i hög idiosynkratisk risk

**Fynd:** riskjustering gav nästan samma median-DEV-edge, men förbättrade flera
svaga splits och den forskningsexponerade holdouten. Global transformation verkar
späda ut starkt råmomentum.

**Ny hypotes:** använd riskjustering bara i universumets högsta volatilitetskvartil
eller vid negativ marknadsregim; lämna övriga ranker orörda. Mät om förbättringen
kommer från bättre nedsidesselektion eller bara lägre beta.

## Metod- och datatester som måste föregå nya alpha-beslut

### SR-9 – Gemensam baslinjeparitet

Gamla skript rapporterar baslinje-CAGR från cirka 6,6% till 21,2% trots att de
beskriver Large. Bygg ett kontraktstest där varje tune-skript först måste matcha
den kanoniska backtesterns NAV, antal innehav, affärer, kostnader och veckoreturer.
Avvikelse över 1 bp per vecka eller olika affärsantal gör testet ogiltigt.

### SR-10 – Corporate-action jump quarantine

Robusthetstestet flaggade många hopp på ±60–260%. Kontrollera dessa mot PIT-split/
utdelningsdata och kör leave-one-ticker-out samt winsoriserad känslighetsanalys.
Detta ska inte ”städa” riktiga avkastningar, utan visa om alpha drivs av feljusterade
priser eller enstaka namn.

### SR-11 – Rankingkalibrering, inte sannolikhetskalibrering

Precision/recall-testet fick konstant prediktion 0,5 och Brier 0,25. LambdaRank-
score är inte en klassannolikhet. Ersätt testet med rankpercentil → framtida
excess-avkastning, top-k precision, NDCG och isotonic calibration tränad strikt
inom varje walk-forward-DEV. Det gamla sannolikhetstestet ska inte tolkas som att
modellen saknar signal.

### SR-12 – Ekonomiskt relevanta koncentrationsmått

20/25%-taket triggade aldrig och testade därför ingenting. Mät i stället sektor-
HHI, faktorbeta, korrelation och active share mot index. Om en restriktion testas
ska den ha en förregistrerad minsta triggerfrekvens; annars är resultatet endast
”mekanismen var inaktiv”.

### SR-13 – Dynamiskt N separeras från marknadsexponering

Dynamiskt N ändrade både diversifiering och enskild positionsvikt och var sämre i
gammal holdout. Testa först fast bruttoexponering/positionsrisk med kontinuerlig
breddsignal. Jämför därefter (a) fler namn, (b) mindre total exponering och (c)
lägre vikt per namn, så orsaken kan identifieras.

### SR-14 – Likviditetstest på realistiskt kapital

Likviditetstaket band bara två köp i den historiska simuleringen. Skala AUM i
förregistrerade nivåer och modellera deltagandegrad, spread, nästa-dags exekvering
och successiv påfyllnad. Detta är kapacitets-/implementationsalpha, inte en ny
rankfeature.

## Prioriterad genomförandeordning

1. SR-9 och SR-10: utan jämförbar baslinje och rena corporate actions är resten
   inte beslutsdugligt.
2. SR-1 och SR-3: störst sannolikhet att öka själva rankningens edge.
3. SR-7 och SR-8: starka delgruppsfynd, men PIT-krav först.
4. SR-2, SR-4 och SR-5: minska dåliga rotationer och vänstersvans utan cash-drag.
5. SR-6, SR-11–SR-14: värdefull diagnostik/implementation, lägre omedelbar alpha.

## Inte nya tester

- Fler statiska 13/26/52-vikter utan villkor.
- Fler generella take-profit- eller ATR-trösklar.
- Ytterligare koncentrationstak som inte väntas binda.
- Val av variant efter bästa siffran i den gamla holdouten.
- Small-replikering innan PIT-fundamenta och universum är godkända.

## Tillägg 2026-08-02 – teknisk exit och fear/greed

### SR-45 – Armerad teknisk exit efter stark uppgång

Armera ett innehav när dess 52v-avkastning når översta sektorrelativa decilen.
Ingen fast vinsthemtagningsnivå används. Exit sker först när ett förregistrerat
tekniskt trendbrott inträffar, primärt stängning under ett fallande 20v-medelvärde,
med samtidig rankförsämring. Köp omedelbart bästa behöriga ersättare. Jämför mot
fortsatt innehav, befintlig generell trendexit och samma tekniska signal utan
föregående stark uppgång. Eventstudie och leave-one-event-out föregår adoption.

### SR-46 – Externt Fear & Greed som PIT-komponent

Testa ett externt Fear & Greed-mått endast om historiska komponentvärden och
publiceringstidpunkter kan verifieras point-in-time. Måttet är en separat extern
komponent, inte primär svensk regimdefinition. Jämför ledtid, falska regimskiften
och portföljutfall mot en enkel svensk indextrend. Amerikanska data får inte
retroaktivt fyllas eller väljas efter utfall.

### SR-47 – Svensk kausal fear/greed-komposit

Bygg en svensk komposit av förregistrerade komponenter: bred indextrend,
marknadsbredd, realiserad volatilitet/volatilitetsförändring, tvärsnittskorrelation
och tillgänglig ränt-/stressproxy. Kör först komponentablation och placebokontroll.
Testa därefter tre separata användningar: tidigare bull/bear-detektion,
bruttoexponering och exit. Ett gemensamt resultat får inte dölja vilken användning
eller komponent som bidrar.
