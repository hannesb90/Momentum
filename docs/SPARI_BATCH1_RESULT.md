# Research I — legacyhypoteser replikerade på V2, Batch 1

## Slutsats

Batch 1 hittar två nya, separata V2-challengerhypoteser med **STÖD**:

1. championrank + drawdown-resilience;
2. championrank + trend-strength.

Detta ändrar inte Spår H. Ingen av dem är ny champion och ingen historik har
skrivits om. De får endast bli separat frysta challengers med egen framtida
evidens efter ett nytt beslut.

Residual momentum, trend consistency och jump diffuseness får högst svagt
stöd. Prisdispersion får svagt stöd som regimdiagnostik. Inverse-vol och
target-vol klarar inte de förregistrerade riskkriterierna. Report/attention,
dividend-gap och insider-gap kan inte testas korrekt med frysta V2-inputs.

Batchen stoppar här. DD20, exits, streak, milestone och re-entry har inte körts.

## I0 och metod

Legacyinventeringen omfattar 420 källskript. Inventoryprocessen läste noll
legacyresultatfiler före preregistreringen. Fördelningen blev:

* REPLIKERA NU: 46;
* REPLIKERA SENARE — DATA SAKNAS: 7;
* REDAN TESTAD I V2: 35;
* FÖR LIK EN REDAN TESTAD HYPOTES: 13;
* RENT IMPLEMENTATIONS-/PRODUKTTEST: 90;
* EJ RELEVANT FÖR NY ARKITEKTUR: 229.

Batchordning, nio varianter, definitioner och beslutskriterier frystes innan
V2-target lästes. Alla tester använder targetfritt decision universe,
post-decision execution, 20 bp ensidig kostnad, verifierade terminaler och
samma benchmark. Target används endast i efterhandsutvärderingen.

En första körning stoppade före output på ett typfel (NumPy-array till en
listbaserad annualiseringsfunktion). Enda ändringen var `array.tolist()`.
Ingen parameter eller metoddefinition ändrades.

## Gemensamma referenser

| Referens | Mean IC52 | Median IC52 | Top-30 IC | Positiva datum | CAGR | Sharpe excess | MaxDD | Leave-3 CAGR | Leave-5 CAGR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Ren 12m | 0,1326 | 0,1647 | −0,0434 | 95 % | 17,34 % | 0,675 | −11,31 % | 6,43 % | 1,64 % |
| Fryst champion | 0,1555 | 0,1658 | −0,0250 | 100 % | 25,29 % | 1,379 | −4,43 % | 14,65 % | 10,56 % |
| Benchmark | – | – | – | – | 10,07 % | – | – | – | – |

Portföljmåtten är historiska OOS-resultat och inte untouched forward.

## Familjer

### 1. Report / attention / PEAD — KAN INTE TESTAS KORREKT

Legacy attention-testet såg inget stöd: låg rapportvolym gav inte starkare
PEAD än hög rapportvolym. Det resultatet är inte evidens eftersom det använde
legacyuniversum, MFN-cache och `close×volume`-semantik från den äldre kedjan.

V2 har 94,2 % täckning för den grövre proxyn `return_since_last_report_ttm`;
staleness är 0/45/183 dagar (min/median/max). Diagnostiskt ger proxyn mean IC
0,0417 men Top-30 IC −0,0926. Den är ackumulerad avkastning sedan ett
datumfält, inte verifierad initial rapportreaktion eller attention. V2 saknar
publiceringstid, surprise och QA-godkänd eventomsättning. Ingen eventportfölj
byggdes.

### 2. Dividend-gap — KAN INTE TESTAS KORREKT

Legacy såg starka fullsampletal (26v IC 0,191) men inkonsistent holdout,
inklusive negativ 8v-IC. Det byggde på PDF-extraktion, antagen negativ
teckenkonvention och äldre pris/universum.

V2:s registry utesluter dividend-yield och saknar en QA-godkänd PIT-kedja för
utdelningsförändring per aktie samt eventtid. Ingen legacydata importerades och
inget V2-resultat fabricerades. Den ekonomiska hypotesen är fortsatt öppen.

### 3. Dispersion/proxy — SVAGT STÖD

Legacyfältet var inte analytikerdispersion utan pris-/modellproxy. Även V2
testar det uttryckligen som prisproxy: tvärsnittsstandardavvikelsen i
`mom_12_1` per paneldatum.

På 20 OOS-paneler är Spearman mot championens IC −0,650. Mean IC är 0,181 i
låg-dispersion och 0,130 i hög-dispersion. Legacy hade samma riktning men
mycket svagare samband för motsvarande proxy (−0,117). V2-resultatet är endast
regimdiagnostik: variabeln är gemensam för alla aktier, samplet är litet och
ingen gate eller strategi byggdes.

### 4. Insider-gap — KAN INTE TESTAS KORREKT

Legacy FI-körningen såg positiv gap-IC på 8v, men rå insideraktivitet slog gapet
på 26v. Hämtningen hade nätverksavbrott och namnmatchning mellan emittent och
ticker. Den får därför inte betraktas som evidens.

Fryst V2 saknar manifesterade, identitets- och publikationstidsverifierade
FI-transaktioner. Legacycachen återanvändes inte. Hypotesen flyttas till data
saknas.

### 5. Residual momentum — SVAGT STÖD

Legacy rapporterade stark solo-IC, bland annat 0,148 i sin holdout. V2:s
definition använder endast fryst marknadsmodell; ingen falsk sektorneutralitet
byggdes.

| Variant | Mean IC | Top-30 IC | CAGR | Sharpe | MaxDD | Leave-3 | Leave-5 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Residual solo | 0,1447 | −0,0380 | 18,59 % | 0,774 | −8,51 % | 8,02 % | 3,78 % |
| 50/50 champion+residual | 0,1534 | −0,0191 | 20,34 % | 0,910 | −8,25 % | 9,39 % | 5,02 % |

Blendens Top-30 IC blir marginellt mindre negativ, men mean/median IC och alla
robusthetsmått är sämre än championen. Den gamla idén överlever som en rå
signal men inte som robust inkrementellt alpha ovanpå championen.

### 6. Momentum quality — STÖD, men inte ny champion

Den gamla `trend_consistency_52w` hade definitionsmismatch. V2-registret säger
andel positiva veckor, medan den aktiva panelkolumnen räknar positiva dagliga
observationer. Oberoende rekonstruktion visar max absolut avvikelse 0,282.
Research I använder den preregistrerade veckodefinitionen och ändrar inte C.

| Fast 50/50-blend med champion | Klass | Mean IC | Top-30 IC | CAGR | Sharpe | MaxDD | Leave-3 | Leave-5 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Drawdown resilience | STÖD | 0,1948 | 0,1217 | 23,85 % | 1,318 | −4,54 % | 15,98 % | 13,18 % |
| Trend strength | STÖD | 0,1678 | 0,0096 | 26,98 % | 1,576 | −2,68 % | 17,42 % | 13,24 % |
| Weekly trend consistency | SVAGT STÖD | 0,1887 | 0,0425 | 15,30 % | 0,639 | −5,48 % | 10,06 % | 7,81 % |
| Jump diffuseness | SVAGT STÖD | 0,1311 | 0,0949 | 17,29 % | 0,839 | −8,41 % | 10,59 % | 7,62 % |

Drawdown-resilience förbättrar samtliga primära rankingmått och bredden i
leave-out-resultatet, trots lägre CAGR. Trend-strength passerar också den
förregistrerade regeln och har positiv Top-30 IC. Resultaten är fortfarande
historiskt OOS på samma forskningsutsatta 20 IC-paneler. De är nya challenger-
hypoteser, inte bekräftad alpha.

Riskjusterat momentum och downside-riskjusterat momentum kördes inte igen;
de är redan testade i Spår F och ligger kvar i registret som sådana.

### 7. Inverse-vol sizing — INGET STÖD

Legacy hade vid ett tillfälle `inverse_vol_b075` som vinnare med rapporterad
CAGR 27,1 % och Sharpe 1,97, men på en annan modell, målhorisont och en kedja
med de kända legacybristerna.

På V2 hålls selection exakt oförändrad. Inverse-vol ger CAGR 24,82 %, Sharpe
1,447, MaxDD −5,18 %, turnover 0,218, leave-3 16,59 % och leave-5 13,02 %.
Sharpe/bredd förbättras, men MaxDD och turnover försämras och CAGR blir lägre.
Det passerar därför inte den preregistrerade riskregeln.

### 8. Target-vol — INGET STÖD

Legacy target-vol föll också sina egna senare kriterier. V2-testet använder
förregistrerad 10 % target, ingen leverage och cash för resterande exponering.
Rankings och aktieval är oförändrade.

Resultatet blir CAGR 16,52 %, Sharpe 0,636, MaxDD −4,45 %, turnover 0,170,
leave-3 9,19 % och leave-5 6,55 %. MaxDD förbättras inte materiellt och mycket
av excess/Sharpe försvinner. Ingen riskförbättring stöds.

## Multiple testing och reproducerbarhet

* Hypotesfamiljer: 8.
* Faktiska resultatgranskade varianter: 9.
* Preregistrerade varianter: 9.
* Diagnostiska följdtester: 0.
* Misslyckade varianter borttagna: 0.
* Skyddade A–H-filer: 211, ändrade: 0.
* Oberoende reproduktion: 17/17 filer byte-identiska.
* Resultatmanifest aggregate SHA256:
  `20b388f70bd61dabfedf1a2f660027a44fbcbee9fe0fd27870b1fa76da844701`.

## Beslut efter Batch 1

Spår H fortsätter exakt oförändrat. Research I stoppar före Batch 2.

Drawdown-resilience och trend-strength kan efter separat preregistrerat beslut
frysas som **nya challengers** och samla egen forwardevidens. De får inte
ersätta, ändra eller omtolka championen eller dess Spår H-journal.

Den återupptäckta consistency-mismatchen ska dokumenteras som befintlig
registry/panelbegränsning. Den påverkar inte H-championens 12m/18m-signal och
har inte reparerats inom Research I.
