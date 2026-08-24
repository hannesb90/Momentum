# Luckanalys: UTVECKLINGSLOGG och legacy-testlistor mot v2

Datum: 2026-08-16. Genomgång av `momentum_prod_work/docs/` (legacy, read-only)
mot v2:s täckningsdokument, för att hitta tester som aldrig flyttats över.

## Vad som granskats

| Källa | Omfattning |
|---|---|
| `UTVECKLINGSLOGG.md` | 7 501 rader, ~200 loggposter, N3-01 → N3-126 + LSTM/plattformsspåret |
| `MOMENTUM_ROTATION_TESTPLAN.md` | 15 mekanismtester, `test01`–`test15` |
| `EDGE_RISK_SCENARIO_TESTKO.md` | 40 poster, TIER 1–4 |
| `FORBATTRINGSKO.md` | ~40 punkter från extern kodgranskning |
| `UTVECKLINGSLOGG_SMALL.md` | small-spåret, förkastat 2026-08-04 |

Mot: `LEGACY_V2_COVERAGE_MATRIX.md` (46/46), `RESEARCH_MASTER_INDEX_V_TO_AF.md`,
`SPARF`, `SPARI Batch 1–3`, `SPARJK`, samt de 236 skripten i `tools/`.

## Huvudfyndet

**Täckningsmatrisens 46 poster är uteslutande `run_*.py` och `tune_*.py`.
Rotationstestplanens 15 tester (`test01`–`test15`) finns inte med i någon av
dem.** Sökning på `test0`/`test1[0-5]_` i matrisen ger noll träffar, och ingen
v2-fil nämner rotationstestplanen. Det är en hel testfamilj som aldrig
inventerades vid v2-omstarten.

De 15 kördes 2026-07-26 och omvaliderades 2026-07-30 mot **LambdaRank/Test 10-
baslinjen** — alltså legacy-modellen med `prob_up`-baserat urval, inte H0.
Fyra av dem stannade i SHADOW-status, det vill säga lovande men aldrig avgjorda.

## A. Genuina luckor, körbara på befintlig data i båda fönstren

Rangordnade efter värde, inte efter hur lätta de är.

### A1. Rebalansfrekvens bortom 8 veckor — **högst värde**

SPARF F6 var ett **tvåpunktstest**: 4 veckor mot 8 veckor. Åtta vann och blev
kontrakt. Ingen längre takt prövades någonsin.

Legacy prövade fem takter och kom till motsatt hörn: *"ROTATIONSTAKTEN ÄR
FLASKHALSEN: kontraktets 52v är sämst av fem prövade takter"* (2026-08-04), och
efter kontroll över startveckor *"13v är enda som överlever"* (2026-08-05).

Rebalansfrekvensen är en av modellens tre grundparametrar (signal, N,
frekvens). Två av tre valdes på ett svep; den tredje valdes på två punkter.
`sched_fn` är redan en parameter i `stack_h_motor.py` — svepet 4/8/12/16/26
veckor är några rader kod.

### A2. Staggerade kohorter (legacy N3-55)

Dela kapitalet i k delportföljer som rebalanserar med förskjuten fas i stället
för en portfölj som rebalanserar allt samtidigt. Ingen ny signal, ingen ny
tröskel att överanpassa — ren variansreduktion.

Aldrig prövat i v2. Har dessutom en egenskap vi saknar helt: den gör resultatet
oberoende av vilken startvecka backtestet råkar börja på. Legacy mätte
startveckekänslighet systematiskt; v2 har aldrig gjort det.

### A3. Poängutjämning, EMA 2–4 paneler (test08)

Går rakt på det problem vi grävt i hela veckan: rankningen är platt (0,1055
percentilenheter mellan rank 1 och 30) och ett bra kvartal flyttar ett bolag 13
platser, vilket gör toppen till en symptomlista över nyligen accelererade namn.
Utjämning av poängen dämpar precis det bruset.

Legacy: EMA2/EMA3 förbättrade *alla* perioder i första körningen, men
omvalideringen 2026-07-30 mot LambdaRank-baslinjen höll inte (holdout +3,05 pp
föll bort, span4 blev marginellt bäst). Oavgjort, och aldrig prövat på H0.

### A4. Opportunity-cost-byte, `swap_10` (test05 + loggen 2026-08-05)

Detta är **legacys starkaste enskilda fynd** och det är inte replikerat i v2.
Rättelseposten 2026-08-05 lyder:

> `swap_10` är den enda mekanism i hela sessionen som klarar BÅDA kontrollerna
> — placebo (percentil 100 på båda fönstren) och lotteri (över SE i båda
> fönstren). Ingen annan mekanism, konfiguration eller insättningsregel har
> gjort det.

Mekanismen: byt ut ett innehav som underpresterar mot index sedan köp, när en
kandidat överstiger det med ett poänggap. Distinkt från hysteres — hysteres
säger *när man får behålla*, swap säger *när det är värt att byta*. STACK_H har
det första men inte det andra.

Loggen bär också en metodlärdom vi bör ta med: framåteffekten föll monotont för
varje "förbättring" av mekanismen (+2,61 → +1,27 → +0,30 pp), eftersom varje
optimering valdes på en enskild kalender.

### A5. Intraperiod-ingång och intraperiod-tesbrott (test06 + logg 2026-08-04)

Legacy: *"Intraperiod-ingång prövad på RISK: LOVANDE, dagens andra mekanism som
klarar hela kontrollkedjan."* test06 stannade i SHADOW.

`tools/frekvens_vs_kraft.py` besvarade en **annan** fråga — om tätare mätning
ger statistisk kraft (nej, t beror på kalendertid, inte samplingstäthet). Den
säger ingenting om huruvida det lönar sig att *agera* inuti panelen. Vi har
dagliga justerade priser i båda fönstren, så detta är byggbart.

### A6. Re-entry villkorad på poängförbättring (test11)

Legacy-status: SHADOW, *"högst prioriterad kandidat av Test 9-12"*, konsekvent
förbättring i både modern och holdout utan overfittingtecken.

V2 testade **tidsbaserad** återköpsspärr (Batch 2, INGET STÖD) och karens i
denna session. Aldrig villkoret "får köpas tillbaka först när poängen är X
bättre än vid exit". Täckningsmatrisen avfärdade den på formen "KAN INTE
REPLIKERAS ENTYDIGT — legacy-rutnätet 0/5/10 pp har inget unikt värde" — men
det hindret gäller inte längre, eftersom du uttryckligen sagt att trösklarna är
lösa exempelsiffror.

### A7. Omsättningsbromsar: bytesbudget och minsta innehavstid (test15, test07)

Båda begränsar *namnbyten*. STACK_H:s NTZ (0,005) är en **viktbroms** — den
hindrar små viktjusteringar, inte in- och utträden. Legacy förkastade båda, men
mot en modell med helt annan omsättningsprofil (veckovis mot 56-dagars).

### A8. Lägre prioritet, men gratis att köra på befintlig motor

- **Adaptiv holdingperiod** (test12) — legacy SHADOW, `adaptive_4_2` rekommenderad
- **Åldringsbonus** (test10) — legacy FÖRKASTAD
- **Partiell nedskalning** (test09) — legacy SHADOW
- **Vinstskydd utan total exit** (test13) — legacy FÖRKASTAD
- **Regimberoende churn** (test14) — legacy FÖRKASTAD

Not om de två sista i familjen: täckningsmatris #23 avfärdade graderad exit som
"DUPLIKAT/SAMMA HYPOTES" genom **resonemang**, inte genom körning.

## B. Lucka som kräver ett beslut, inte bara en körning

### B1. Nordisk universumutvidgning via Börsdata (EDGE-16)

Den enda posten i hela legacy-kön som aldrig ens påbörjades: *"stort
datainhämtningsprojekt, medvetet ej påbörjat, kräver en egen session/beslut om
datakällor."* Vi har numera Börsdata Pro och API:et är inlagt.

Men det bryter det förseglade universumet. Det kan bara vara forward-forskning
med egen journal från sin freeze-tidpunkt — aldrig en ändring av den frysta
modellen 19 dagar före forward-start.

## C. Vad som INTE är luckor

Redan avgjort i v2, ingen anledning att röra:

| Mekanism | Var | Utfall |
|---|---|---|
| Individ-drawdown DD20 | Batch 2 | INGET STÖD |
| Milstolpe 13v / 26v | Batch 2 | INGET STÖD |
| Tidsstopp 8v | Batch 2 | SVAGT STÖD, ej befordrad |
| Återköpsspärr (tidsbaserad) | Batch 2 | INGET STÖD |
| Rank-exit, trendbrott, momentumförlust, drawdown-exit | SPARF F7 | ingen passerade |
| Invers-vol, target-vol, sizing | Batch 1 | INGET STÖD |
| Korrelationsrefill 0,85 | Batch 3 | INGET STÖD |
| ROA / lönsamhetskvalitet | Batch 3 | INGET STÖD |
| Residual momentum, dispersion | Batch 1 | SVAGT STÖD |
| Portföljstorlek N | SPARF F5 + takfelssvepet | N=30 |
| PEAD | `pead_eget_spar.py` | eget spår, ett fönster |
| Streak, ATR/high-low | — | datablockerade, fortfarande blockerade |

`FORBATTRINGSKO.md` är i princip helt legacy-appens produktionskod — Kelly-
sizing, LGBM-kalibrering, API-autentisering, atomiska filskrivningar. Den rör
inte v2:s modell. Två punkter är ändå värda att bära med sig som
exekveringsrealism: kostnaden använder samma dags ADV (borde laggas en bar), och
rebalanseringens ordning kan göra resultatet radordningsberoende
(permutationstest saknas).

## Varning som gäller hela listan

**Varje positiv dom i UTVECKLINGSLOGG kördes mot LambdaRank/LSTM-modellen med
`prob_up`-baserat urval.** Ingen av dem är ett resultat för STACK_H — de är
hypoteser med känd riktning, inget mer.

Basfrekvensen är känd och den är låg: de tre legacy-mekanismer som såg starkast
ut (DD20, återköpsspärr, milstolpe) föll **allihop** när de faktiskt kördes på
v2. Och v2:s egen historik är att av ~88 prövade varianter var ~6 nominellt
positiva i båda fönstren, alla med konfidensintervall som täcker noll — färre
än slumpen ger.

Förvänta alltså att det mesta av A1–A8 faller. Värdet ligger i att luckorna
stängs och inventariet blir sant, inte i att något förväntas överleva.

Undantaget är **A1**, som inte är en tilläggsregel utan en grundparameter som
valdes på två punkter. Den förtjänar att avgöras oavsett utfall.
