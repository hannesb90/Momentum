# QUANT TERMINOLOGY → H0 GAP AUDIT — kumulativ ledger

Syfte: kartlägga vilka etablerade quant-fenomen som redan är besvarade för H0,
så att samma sak aldrig testas igen under ett annat namn.

**Ingen modelländring, ingen tuning, inga backtests i denna fas.**

Status: **Batch 1 (P0, begrepp 1–20) klar.** 306 begrepp återstår.

---

## H0:s faktiska mekanik — verifierad mot `trackh/H0_LOCK.json`

Detta måste stå först, eftersom flera av begreppen beskriver mekanismer som
STACK_H har men **H0 saknar**.

| Egenskap | H0:s låsta värde |
|---|---|
| Poäng | `0,5 × percentilrank(mom_12m) + 0,5 × percentilrank(mom_18m)` |
| Urval | Topp 30 |
| Viktning | **Lika vikt** (1/30) |
| Ombalansering | Var **andra** frusen fyraveckorspanel; ursprunglig fas behålls |
| På ombalanspanel | **Hela urvalet ersätts** av aktuell topp-30 |
| På mellanpanel | Innehaven behålls oförändrade |
| Exekvering | Första observerade stängning strikt efter beslutsdatum |
| Kostnad | 20 bp enkelsidigt |
| Saknad poäng | Fylls med datumets medianpoäng |

**H0 har alltså varken hysteres, band, no-trade-region, ersättningströskel,
stop-loss, trendgrind eller kassaregel.** Den enda tröghet som finns är att
mellanpanelen inte handlar.

## Kostnadstaket — avgör prioriteringen av begrepp 1–12

Uppmätt 2026-08-17 (`research_k/h0_h1_h2_tvafonster_results.json`):

| Fönster | H0:s omsättning | × 20 bp | H0:s CAGR |
|---|---:|---:|---:|
| 2020-2026 | 228,5 %/år | **0,46 %/år** | 7,57 % |
| 2014-2019 | 187,1 %/år | **0,37 %/år** | 31,54 % |

I H0 uppstår omsättning **enbart** när namn byts — likavikten skapar ingen
viktomsättning för behållna namn. Därför gäller:

> **En mekanism som bara minskar churn kan i absolut bästa fall lämna tillbaka
> 37–46 baspunkter per år, och bara om den eliminerar all handel.** En realistisk
> churn-minskning på 20–30 % är värd 8–14 bp/år. Det ligger en storleksordning
> under placebobandet (±2,4 pp) och under detektionsgolvet (~4 pp på 66 paneler).

**Konsekvens:** begrepp 1–12 kan bara ha ekonomisk betydelse via **urvalskanalen**
— vilka namn som ägs — aldrig via kostnadskanalen. Varje hypotes i den familjen
måste formuleras så att den ändrar innehaven, inte bara handelsfrekvensen.
Annars är den obeslutbar redan innan den körs.

---

## Ledger — begrepp 1–20

Kolumnen "Mot vilken modell" är avgörande: nästan all tidigare prövning gjordes
mot STACK_H eller mot en waterfill/invers-vol-konstruktion (baslinje 16,83 %),
inte mot H0:s likaviktade konstruktion.

| # | Begrepp | Finns i H0? | Status | Bevis | Mot vilken modell | Gap |
|---:|---|---|---|---|---|---|
| 1 | Rank hysteresis | Nej | PARTIALLY TESTED | `granskning_baslinjeredundans` (av/på: +0,09 / −1,78 pp), `granskning_statisk_vs_dynamisk_del2` D5, `hysteres_kop_och_agande` | STACK_H, waterfill | **MEDIUM** |
| 2 | Buffer zone / banding | Nej | PARTIALLY TESTED | `hysteres_kop_och_agande` (köp [lo,hi], behåll till H), `kopband_mot_ratt_modeller` (0/8), `korsfonster_kandidater`, D6 (nolloperation) | STACK_H, V_A, ERC, waterfill | **MEDIUM** |
| 3 | No-trade region | Nej (moot i vikttermer) | NOT TESTED | STACK_H:s NTZ 0,005 är en *vikt*regel; H0 har inga viktavvikelser att dämpa | — | LOW |
| 4 | Replacement hurdle | Nej | PARTIALLY TESTED | `a4_opportunity_cost_swap` poänggap G=0,02/0,05/0,10 (0/9), `granskning_statisk_vs_dynamisk` D1 | STACK_H | **MEDIUM** |
| 5 | Incumbency advantage | Delvis (mellanpanel) | PARTIALLY TESTED | `rankresan_djupanalys`, `runway_matning`, rankautokorrelation 0,6215 (topp-60, 4v) | waterfill, universumnivå | LOW — spegelbild av #1 |
| 6 | Portfolio inertia | Ja (8-veckorscykeln) | PARTIALLY TESTED | `a1_rebalansfrekvens` 4/8/12/16/24/52 v över alla faser | STACK_H | **MEDIUM** |
| 7 | Switching threshold | Nej | **DUPLIKAT av #4** | samma mekanism, annan etikett | — | — |
| 8 | Switching cost | Ja | **ALREADY TESTED** | 228,5 % resp. 187,1 % omsättning × 20 bp = 0,46 / 0,37 %/år | **H0 direkt** | **INGET** |
| 9 | Signal churn | Ja | ALREADY TESTED | `frekvens_vs_kraft`: autokorr 4v 0,6215 topp-60 / 0,9389 universum, implicerad daglig 0,9969 | H0:s rankning | LOW |
| 10 | Rank crossing | Ja | ALREADY TESTED | `genomfarter_identifierbara`: 105 av 237 spells ≤ 2 paneler = **44,3 %** | waterfill N=20 | LOW |
| 11 | Rank migration | Ja | ALREADY TESTED | `rankresan_djupanalys` (banans form, inträdesrank medel 13,57) | waterfill | LOW |
| 12 | Decision-boundary instability | Ja (topp-30-gränsen) | **NOT TESTED** | SPARF anger adjacent-rank stability 0,937 men mäter inte utfallskänslighet; poänggapet rank 1→30 är 0,1045, alltså **0,0036 per plats** | — | **HIGH** |
| 13 | Premature exit | Ja | PARTIALLY TESTED | `topp5_snav_utgang`, `utgangsregel_placebo`, SPARI Batch 2 "Framtida vinnare kapade" | waterfill; Batch 2 mot H0 | **MEDIUM** |
| 14 | Exit efficiency | Ja | ALREADY TESTED | `utgangsregel_placebo`: spelar det roll VILKA som kastas ut? 300 seeds → placebo | waterfill | LOW |
| 15 | Re-entry lag | Ja | **ALREADY TESTED** | SPARI Batch 2 re-entry block: **INGET STÖD**; `reentry_sparr_topp5` (Δ −0,002, placebo sd 0) | **Batch 2 mot H0** | LOW |
| 16 | Re-entry cost / missed return | Ja | ALREADY TESTED | `reversal_och_kopband` stämplade återinträden: +10,51 % mot färska −0,91 % (t 2,46) i 2020-2026, men +9,09 % mot +7,03 % (t 0,33) i 2014-2019 — replikerar ej | waterfill, båda fönstren | LOW |
| 17 | Trend resumption | Ja | PARTIALLY TESTED | `reversal_och_kopband` (reversal inuti topp-30), `momentumkurvan` | STACK_H, waterfill | **MEDIUM** |
| 18 | False breakdown | Nej | NOT APPLICABLE | H0 har ingen breakdown-utlösare; blir relevant först om en exitregel adderas. SPARF F7 trendbrottsexit: ingen passerade | SPARF-champion | LOW |
| 19 | Whipsaw / whipsaw loss | Ja | **NOT TESTED som storhet** | `genomfarter_identifierbara` räknar 44,3 % genomfarter men prissätter dem inte; T2:s −38,07 % reproducerade inte på STACK_H | waterfill | **HIGH** |
| 20 | Winner persistence | Ja | ALREADY TESTED | `graduation_m12_to_m52`: 368 graduates mot 930 washouts av 1 298 nyinträden = **28 % graduationsgrad**; `stora_vinnare_startfas` 143 mega mot 994 falska; `runway_matning` band 1-5 = 9,13 paneler | waterfill, universumnivå | LOW |

### Dubbletter registrerade så de inte testas igen

- **#7 Switching threshold ≡ #4 Replacement hurdle.** Samma mekanism.
- **#5 Incumbency advantage** är spegelbilden av **#1 Rank hysteresis** — en regel
  som ger incumbency ÄR hysteres. Testa den ena, inte båda.
- **#2 Buffer zone** är den tvåsidiga formen av **#1**. Ett gemensamt rutnät
  (köpgräns, säljgräns) täcker båda.
- **#3 No-trade region** är i H0 endast meningsfull som viktregel och H0 har inga
  viktavvikelser mellan ombalanseringar i den frysta specen.

---

## Förregistrerade falsifieringshypoteser — EJ KÖRDA

Formulerade minimalt, en per verklig lucka. Ingen av dem har körts.

### G12 — Beslutsgränsens instabilitet (HIGH)

**Motivering.** Poängskillnaden mellan rank 1 och rank 30 är 0,1045
percentilenheter, alltså 0,0036 per plats. Namnen kring gränsen skiljs av tal
i fjärde decimalen. Ingen har mätt hur mycket av H0:s utfall som hänger på vilka
namn som råkar hamna på plats 28–32.

**Hypotes.** Om H0:s poäng störs med brus av samma storleksordning som det
observerade poängavståndet per rankplats (σ = 0,0036), är den resulterande
CAGR-spridningen över 200 dragningar **mindre än ±1,0 procentenhet** i båda
fönstren.

**Falsifieras om** spridningen överstiger ±1,0 pp — då vilar H0:s redovisade
resultat i väsentlig grad på gränsbrus snarare än på signalen.

**Varför den är först.** Den mäter inte en förbättring utan **hur mycket av det
befintliga resultatet som är reellt**. Den är dessutom oberoende av alla
regelfrågor: faller den, ändras tolkningen av varje annat tal i programmet.

### G19 — Genomfarternas prislapp (HIGH)

**Motivering.** 44,3 % av alla innehav varar högst två paneler. De är räknade
men aldrig prissatta. Om den populationen är värdeförstörande finns där mer
pengar än i hela kostnadsbudgeten på 46 bp.

**Hypotes.** Innehav som varar ≤ 2 paneler har en genomsnittlig
positionsavkastning som **inte skiljer sig från noll** i båda fönstren, mätt som
avkastning under innehavstiden minus universumets avkastning samma paneler.

**Falsifieras om** genomfartspopulationen har signifikant negativ
överavkastning i båda fönstren — då är whipsaw en verklig och kvantifierad
kostnad, och först då är begrepp 1–7 värda att pröva som åtgärd.

**Ordningsföranmärkning.** G19 måste köras **före** G1/G2/G4/G6. Utan G19 vet vi
inte om det finns något att åtgärda, och skulle testa botemedel mot en sjukdom
vi inte konstaterat.

### G1+G2 — Hysteres och band på likaviktad H0 (MEDIUM, villkorad av G19)

**Motivering.** Varje tidigare hysterestest kördes mot invers-vol-viktade
konstruktioner. I dem skapar viktomräkning omsättning oberoende av namnbyten; i
H0 gör den inte det. Effekten kan därför skilja sig i tecken.

**Hypotes.** En tvåsidig regel — köp endast rank ≤ 30, behåll till rank > H för
H ∈ {35, 40, 45} — förbättrar H0:s netto-CAGR i **båda** fönstren.

**Falsifieras om** ingen enskild H är positiv i båda fönstren.

**Villkor:** körs endast om G19 visar att genomfarterna är värdeförstörande.

### G6 — Ombalanseringstakt för H0 (MEDIUM)

**Motivering.** A1 svepte takten mot STACK_H och fann att 8 veckor höll. H0 har
en annan omsättningsprofil (endast namnchurn) och kan ha ett annat optimum.

**Hypotes.** Ingen takt bland 4/8/12/16/24 veckor slår H0:s 8 veckor i **båda**
fönstren, mätt över **samtliga fasförskjutningar** per takt.

**Falsifieras om** någon takts sämsta fas slår 8 veckors medelfas i båda fönstren.

### G13+G17 — För tidig utgång och trendåterupptagning (MEDIUM)

Slås ihop till en hypotes eftersom de är samma händelse sedd från två håll: ett
namn säljs, och frågan är om det därefter återupptar sin trend.

**Hypotes.** Namn som lämnar H0:s topp-30 vid en ombalansering har under de
följande tre panelerna en avkastning som **inte överstiger** avkastningen för de
namn som ersatte dem, i båda fönstren.

**Falsifieras om** de utgående slår ersättarna i båda fönstren — då är H0:s
utbytesregel systematiskt för tidig.

---

## Batch 1 — slutsats: vad som ska testas först

| Ordning | Gap | Varför |
|---:|---|---|
| **1** | **G12 Beslutsgränsens instabilitet** | Mäter hur mycket av H0:s befintliga resultat som är reellt. Oberoende av alla regelfrågor och påverkar tolkningen av varje annat tal. |
| **2** | **G19 Genomfarternas prislapp** | 44,3 % av innehaven är oprissatta. Avgör om begrepp 1–7 överhuvudtaget har ett problem att lösa. |
| **3** | G13+G17 För tidig utgång | Enda kvarvarande diagnostik som kan visa en *riktning* i urvalskanalen. |
| **4** | G6 Takt för H0 | Billig, och A1:s svar gäller inte H0:s omsättningsprofil. |
| **5** | G1+G2 Hysteres och band | Villkorad — körs bara om G19 faller. |

**Sex av tjugo begrepp är redan färdigbesvarade** (#8, #9, #10, #11, #14, #15,
#16, #20 — åtta faktiskt), **två är dubbletter eller ej tillämpliga** (#3, #7,
#18), och **två är verkliga oprövade luckor med hög prioritet** (#12, #19).

Det starkaste enskilda resultatet ur kartläggningen är inte ett gap utan en
gräns: **kostnadskanalen för hela begreppsfamiljen 1–12 är 37–46 bp per år.**
Den siffran gör merparten av familjen obeslutbar i förväg, och det är billigare
att veta det nu än efter tolv körningar.

---

## Ledgerns regler

1. Ett fenomen som står som ALREADY TESTED får inte testas om under ett annat
   namn. Dubbletter registreras i tabellen ovan.
2. Varje rad måste ange **mot vilken modell** beviset gäller. Ett resultat mot
   STACK_H är inte ett svar för H0.
3. En hypotes flyttas till KÖRD först när den har en artefakt i `research_k/`
   och ett datum.
4. Nya begrepp läggs till i nummerordning från masterlistan; ledgern skrivs
   aldrig om bakåt, bara utökad.

---

# G12 KÖRD — 2026-08-17. Hypotesen HÅLLER i båda fönstren.

Artefakt: `research_k/g12_beslutsgransens_instabilitet_results.json`
Kod: `tools/g12_beslutsgransens_instabilitet.py`

## Primärt utfall (förregistrerat: σ = 0,0036, 200 dragningar)

| | 2020-2026 | 2014-2019 |
|---|---:|---:|
| H0 ostört | 7,57 % | 31,54 % |
| Poänggap rank 1→30 | 0,1044 → **0,00360**/plats | 0,1223 → **0,00422**/plats |
| Störd CAGR, medel | 7,37 % | 31,35 % |
| sd | 0,44 % | 0,38 % |
| 95 %-spann | [6,51 %, 8,25 %] | [30,54 %, 32,08 %] |
| **Halva bredden** | **0,87 pp** | **0,77 pp** |
| Vidd min→max | 2,41 pp | 2,12 pp |
| Namn i topp-30 som bruset byter | **0,58/panel** | **0,46/panel** |
| Ostört utfall, percentil | 66 % | 67 % |

Gränsen var ±1,0 pp. Båda ligger under. **Hypotesen håller.**

## Vad det betyder

**H0:s redovisade siffror är inte en artefakt av vilka namn som råkar hamna på
plats 28–32.** Att störa poängen med ett helt rankavstånds brus flyttar bara ett
halvt namn per panel in eller ut ur portföljen, och CAGR rör sig under en
procentenhet. Detta är en av få rena valideringar programmet producerat.

Robustheten håller långt bortom det förregistrerade bruset. Vid **4× brus**
(σ = 0,0144, motsvarande ~4 rankplatser) är spannet fortfarande bara ±1,6 pp
respektive ±1,3 pp, och medelvärdet faller 0,4–0,8 pp.

## Två sidofynd

**1. Den exakta ordningen är värd ungefär +0,2 pp/år — och det replikerar.**
Ostört minus medelstört är +0,20 pp i det sena fönstret och +0,19 pp i det
tidiga. Nästan identiskt i två oberoende fönster. Bruset kan bara sudda ut
information som finns, så differensen mäter vad den exakta ordningen kring
gränsen faktiskt bär.

**2. Brusets skadeverkan är monoton i det tidiga fönstret men inte i det sena.**

| σ | 2020-2026 | 2014-2019 |
|---|---:|---:|
| 0,5× | 7,25 % | 31,58 % |
| 1× | 7,28 % | 31,32 % |
| 2× | 7,50 % | 31,06 % |
| 4× | 7,18 % | 30,77 % |

I 2014-2019 är mer brus monotont sämre — rankningen bär verklig information kring
gränsen. I 2020-2026 finns inget sådant mönster; 2× brus ger till och med högre
CAGR än 1×. **Samma fönsterdelning som allt annat i programmet.**

## Ny strukturell gräns för ledgern

Utöver kostnadstaket (37–46 bp/år) etableras nu:

> **Gränsordningens värde: ~0,2 pp/år.** En regel som enbart OMORDNAR marginella
> kandidater — ersättningströskel (#4), switching threshold (#7) — har högst
> cirka 0,2 procentenheter att fånga. Det är långt under detektionsgolvet.

Denna gräns binder **inte** regler som ändrar *djupet* i köpzonen (hysteres #1,
band #2): de flyttar avsiktligt fler namn än brus gör, och deras effekt mäts på
annat sätt.

**Konsekvens för kön:** #4 och #7 nedgraderas från MEDIUM till **LOW**. De är nu
dubbelt bundna — av kostnadstaket och av gränsordningens värde — och kan inte
producera ett utslag som går att skilja från noll.

## Kön efter G12

| Ordning | Gap | Status |
|---:|---|---|
| ~~1~~ | ~~G12 Beslutsgränsens instabilitet~~ | **KÖRD — hypotesen håller** |
| **1** | **G19 Genomfarternas prislapp** | näst på tur; måste köras före G1/G2/G6 |
| 2 | G13+G17 För tidig utgång | — |
| 3 | G6 Takt för H0 | — |
| 4 | G1+G2 Hysteres och band | villkorad av G19 |
| — | ~~G4/#7 Ersättningströskel~~ | **nedgraderad till LOW efter G12** |

---

# G19 KÖRD — 2026-08-17. Hypotesen FALLER i båda fönstren.

Artefakt: `research_k/g19_genomfarternas_prislapp_results.json`
Kod: `tools/g19_genomfarternas_prislapp.py`

## Primärt utfall

| | 2020-2026 | 2014-2019 |
|---|---:|---:|
| Avslutade spells | 318 | 311 |
| Distinkta namn | — | 173 |
| Genomfarter (≤2 paneler) | 140 (**44,0 %**) | 123 (**39,5 %**) |
| Medelöveravkastning | **−8,95 %** | **−7,49 %** |
| Median | −7,66 % | −6,88 % |
| t, naivt | −8,69 | −6,53 |
| **t, klustrat på namn** | **−7,80** | **−6,18** |
| Längre innehav (>2 paneler) | +9,84 % (t 3,03) | +14,08 % (t 3,69) |
| Andel av portföljens paneltid | 14,6 % | 11,4 % |
| Genomfarter per år | 27,6 | 20,2 |
| Handelskostnad för dem | 0,37 %/år | 0,27 %/år |

Förregistreringen sade: falsifieras om signifikant negativ överavkastning i båda
fönstren. **Det är precis vad som inträffade**, med t −7,80 och −6,18 efter
namnklustring. Det är den starkaste och mest samstämmiga effekten programmet
uppmätt.

## Men resultatet är till stor del mekaniskt — och det är avgörande

**Ett namn hålls två paneler och säljs sedan PRECIS DÄRFÖR ATT dess rank föll,
och dess rank föll därför att det gick dåligt.** Mätningen är betingad på
utgången, och utgången styrs av samma avkastning som mäts.

"Namn som såldes snabbt gick dåligt" är alltså nära en tautologi. Detsamma
gäller hela längdfördelningen: innehav som varar 20+ paneler har +58 % till
+123 % överavkastning, men de varade länge **därför att** de fortsatte stiga.

| Längd (paneler) | 2020-2026 | 2014-2019 |
|---:|---:|---:|
| 2 | −8,95 % | −7,49 % |
| 4 | — | −7,60 % |
| 8 | — | −1,84 % |
| 14 | +19,30 % | +17,49 % |
| 20 | +58,31 % | +63,23 % |
| 22 | — | +122,84 % |

Tabellen är **deskriptiv, inte kausal**. Den är framkallad av urvalsregeln själv.

## Vad G19 därmed licensierar — och inte

**Licensierar:** det finns en stor, identifierbar population — 44 % respektive
39,5 % av alla innehav, 11–15 % av portföljens paneltid — med ett stort negativt
tal fäst vid sig. Det är tillräckligt för att motivera att man undersöker en
åtgärd.

**Licensierar INTE:** slutsatsen att −8,95 % är återvinningsbart. Vi vet inte om
namnen fortsatte falla efter försäljningen (då var utgången korrekt och det
finns inget att rätta) eller om de vände (då var utgången för tidig).

**Handelskostnaden är däremot fastställd och liten:** 0,37 respektive 0,27 % per
år för hela genomfartspopulationen. Det bekräftar kostnadstaket från Batch 1 —
kostnadskanalen är inte där pengarna finns.

## Konsekvens för kön

G19 pekar direkt in i **G13+G17**, som blir det avgörande testet i stället för
G1/G2:

> Vad gjorde genomfartsnamnen under de 2–4 paneler som följde efter
> försäljningen? Fortsatte de falla — då var utgången rätt. Vände de upp — då är
> den för tidig, och först då har hysteres och band något att fånga.

Det upplöser betingningsproblemet, eftersom perioden EFTER försäljningen inte
ingår i beslutet att sälja.

**G1+G2 förblir villkorade och flyttas bakom G13+G17.**

## Kön efter G19

| Ordning | Gap | Status |
|---:|---|---|
| ~~—~~ | ~~G12 Beslutsgränsens instabilitet~~ | KÖRD — hypotesen håller |
| ~~—~~ | ~~G19 Genomfarternas prislapp~~ | **KÖRD — hypotesen faller, men betingad** |
| **1** | **G13+G17 Utgångarnas efterspel** | avgörande; upplöser G19:s betingningsproblem |
| 2 | G6 Takt för H0 | oberoende, billig |
| 3 | G1+G2 Hysteres och band | villkorad av G13+G17, inte längre av G19 |
| — | ~~G4/#7 Ersättningströskel~~ | nedgraderad till LOW efter G12 |

## Metodlärdom att bära vidare i ledgern

Den förregistrerade hypotesen var **dåligt formulerad av mig**: den kunde inte
skilja "whipsaw förstör värde" från "utgångsregeln hittar förlorare korrekt".
Varje framtida hypotes om en population som definieras av ett beslut måste mäta
utfallet **efter** beslutet, inte under det.

---

# G13+G17 KÖRD — 2026-08-17. Dom: **NO PREMATURE-EXIT PROBLEM.**

Artefakt: `research_k/g13_g17_premature_exit_results.json`
Eventnivå: `research_k/g13_g17_premature_exit_events.jsonl` — **263 exits**, varje
rad granskbar i efterhand utan ny körning.
Kod: `tools/g13_g17_premature_exit_audit.py`

Population: alla H0-innehav som säljs efter ≤2 paneler. Ersättare: den likaviktade
korgen av namn som kom in vid samma ombalansering — ekonomiskt exakt dit kapitalet
gick i en likaviktad portfölj.

## Huvudresultat — opportunity cost, såld aktie minus faktisk ersättare

| Horisont | 2020-2026 | 2014-2019 | Poolat | Slår ersättaren |
|---|---:|---:|---:|---:|
| +1 panel (4 v) | −2,25 % (t −1,98) | −0,84 % (t −0,78) | −1,59 % | 39,9 % |
| +2 (8 v) | −1,00 % (t −0,56) | −2,22 % (t −1,45) | −1,57 % | 46,6 % |
| +3 (12 v) | −1,65 % (t −0,78) | −2,63 % (t −1,39) | −2,11 % | 47,0 % |
| +4 (16 v) | −2,10 % (t −0,95) | −4,17 % (t −1,80) | −3,04 % | 42,0 % |
| +6 (24 v) | −1,95 % (t −0,71) | −3,77 % (t −1,13) | −2,78 % | 41,1 % |
| +13 (52 v) | −1,59 % (t −0,37) | −11,74 % (t −1,99) | −6,22 % | 39,1 % |

**Negativ på varje horisont i båda fönstren.** De sålda namnen stiger absolut
(+0,16 % till +10,20 % poolat) men ersättarna stiger mer (+1,75 % till +16,42 %).
Endast 39–47 % av exits slår sin faktiska ersättare.

## Banan efter exit och återinträdena

| Mått | Poolat |
|---|---:|
| MAE, medel | −22,12 % |
| MFE, medel | +36,36 % |
| Drawdown före återhämtning | −4,40 % |
| Återhämtar till exitpriset inom 52 v | **96,7 %** |
| Återvänder till H0 | **48,3 %** (median 4 paneler) |
| Pris exit → återinträde, median | **+26,15 %** |
| Återköpt >20 % dyrare | 57,5 % |

**Detta ser ut som ett whipsawhaveri och är det inte.** Att 96,7 % återhämtar sig
och att medianåterköpet sker 26 % dyrare låter förödande — men pengarna låg inte
stilla under tiden. De låg i ersättarna, och ersättarna gick bättre. Sekvensen
"sälj lågt, köp tillbaka dyrare" är ekonomiskt irrelevant så länge kapitalet
under mellantiden arbetade i något som avkastade mer.

## Korrigering av min egen körning

Skriptets automatiska dom blev först **MIXED / CONDITIONAL** och licensierade
G1/G2/G6. **Den domen är förkastad.** Två av delpopulationerna var cirkulära:

* *"Snabb trendresumption"* definierades på avkastningen vid +1 och +2 paneler och
  mättes sedan på +4, som **innehåller** +1 och +2.
* *"Ekonomiskt undvikbara exits"* definierades direkt på `opp_cost > 0`.

Båda mätte alltså sin egen definition. Omräknat med **icke-överlappande** fönster
— gruppen definieras på +1..+2, opportunity cost mäts på +2..+13:

| Grupp | 2020-2026 | 2014-2019 |
|---|---:|---:|
| Trendresumption, överlappande (falskt) | +7,95 % | +7,68 % |
| **Trendresumption, icke-överlappande** | **+0,00 %** (t 0,00) | **−4,62 %** (t −0,57) |
| Alla korta exits, icke-överlappande | −1,76 % | −8,26 % |

**Hela effekten var ett artefakt av min definition.** Ingen framåtblickande edge
kvarstår.

Gruppen "återköpt >20 % dyrare" ger +18,08 % (t 2,19) i 2020-2026 men +1,46 %
(t 0,17) i 2014-2019 — replikerar inte. Den är dessutom definierad av en
**framtida händelse** (det faktiska återinträdet) och är därför inte
identifierbar vid exittillfället ens om den hade replikerat.

## Beslut

**NO PREMATURE-EXIT PROBLEM.** H0:s exitregel är i genomsnitt korrekt: de namn
som säljs underpresterar sina faktiska ersättare på varje mätt horisont, i båda
fönstren.

**G1/G2 hysteres och band licensieras INTE.** G6 licensieras inte heller av denna
väg; om den ska köras måste det motiveras separat som parameterverifiering, inte
som åtgärd mot för tidig utgång.

## Två metodlärdomar införda i ledgern

1. En delpopulation får **aldrig** definieras på samma avkastningsfönster som
   sedan mäts. Definiera på +1..+2, mät på +2..+13.
2. En delpopulation får **inte** definieras av en framtida händelse. Den är inte
   identifierbar vid beslutstillfället.

## Kön efter G13+G17

| Gap | Status |
|---|---|
| G12 Beslutsgränsens instabilitet | KÖRD — hypotesen håller |
| G19 Genomfarternas prislapp | KÖRD — faller, men betingad |
| G13+G17 Utgångarnas efterspel | **KÖRD — NO PREMATURE-EXIT PROBLEM** |
| G1+G2 Hysteres och band | **EJ LICENSIERAD** |
| G4/#7 Ersättningströskel | nedgraderad till LOW efter G12 |
| G6 Takt för H0 | ej licensierad av denna väg; kräver egen motivering |

**Hela begreppsfamiljen 1–7 är därmed stängd för H0** — bunden av kostnadstaket
(37–46 bp/år), av gränsordningens värde (~0,2 pp/år) och nu av att den skada de
skulle bota inte existerar.

Nästa steg är Batch 2 (begrepp 21–40), inte fler regeltester i denna familj.

---

# AVSTÄMNING 2026-08-17 — ett parallellt H0-spår saknades i ledgern

Vid förberedelserna för Batch 2 upptäcktes **~25 H0-specifika artefakter i
`research_k/` daterade 2026-08-16 och 2026-08-17** som inte ingick i Batch 1:s
underlag. De är inte skapade i denna session. Flera är förregistrerade med
SHA256 och har tvåfönsterskärmar, och de **stänger poster jag klassade som
luckor**.

Detta är exakt det fel ledgern finns till för att förhindra, och det måste
åtgärdas innan Batch 2 klassificeras — annars byggs Batch 2 på ett ofullständigt
underlag.

## Vad spåret redan har avgjort

| Artefakt | Förreg. | Tvåfönsterdom |
|---|---|---|
| `h0_reentry_score_improvement` | SHA `4b37169d…` | `positive_both_windows=False`, `ci_excludes_zero_both=False`, omsättning lägre i båda |
| `h0_temporary_exit_guard` | SHA `ec06f600…` | `positive_both_windows=False`, `ci_excludes_zero_both=False`, omsättning lägre, färre dyra återköp |
| `h1_contrarian_exposure` | SHA | `positive_both_windows=False` |
| `h1_contrarian_sign_exposure` | SHA | `positive_both_windows=False` |
| `h0_core_meta_exit` | SHA `8ad5b6e7…` | diagnostisk; utvecklingsfönster 2023 |
| `h0_exit_model_time_split` | SHA | diagnostisk |
| `h0_lgbm_consensus_exit` | SHA | diagnostisk |
| `h0_extratrees_topn_1419` | SHA | diagnostisk |
| `h0_churn_outcome_diagnostic` | — | pris­avkastning två paneler efter sälj/återköp; uttryckligen **inte** ett kontrafaktiskt alfamått |
| `h0_extratrees_full_decision_layer_audit` | — | `PROMISING-BUT-UNPROVEN` |
| `h0_extratrees_selection_skill_audit` | — | `SELECTION SKILL PROMISING-BUT-UNSTABLE` |
| `h0_exit_pattern_explorer_2014_2019`, `h0_exit_interaction_explorer_2014_2019` | — | utforskande |
| `h0_validator_model_race_1419` | — | diagnostisk |

## Rättelser till Batch 1

**`h0_reentry_score_improvement` stänger den lucka jag i luckanalysen kallade A6**
("re-entry villkorad på poängförbättring", legacy test11, som jag beskrev som
*"legacys högst prioriterade SHADOW-kandidat, aldrig prövad i v2"*). Den ÄR prövad
på H0, i båda fönstren, och faller. Rad #15 och #16 i ledgern står kvar som
ALREADY TESTED men får nu även H0-direkt evidens i stället för enbart Batch 2/
waterfill.

**`h0_temporary_exit_guard` och `h0_churn_outcome_diagnostic` överlappar mina
G19 och G13+G17.** Mina körningar var inte överflödiga — de mäter mot H0:s
*faktiska ersättare*, vilket `h0_churn_outcome_diagnostic` uttryckligen säger att
den inte gör — men slutsatserna pekar åt samma håll och ska läsas ihop.

**Två nya statusrader tillkommer** som Batch 1 inte hade begrepp för:
`PROMISING-BUT-UNPROVEN` (full decision layer) och `SELECTION SKILL
PROMISING-BUT-UNSTABLE`. De hör hemma i den distinktion Batch 2 ska tillämpa:
prediction skill ≠ decision skill ≠ portfolio value.

## Ny ledgerregel

> **Regel 5.** Före varje ny batch ska `research_k/` skannas efter artefakter
> daterade efter föregående batch. Ett parallellt spår kan ha stängt en post.
> Skanningen loggas i avstämningsavsnittet med datum och antal filer.

## Batch 2 — blockerad på indata

Masterlistan med 326 begrepp finns **inte i repot**. Batch 1:s poster 1–20 kom
ordagrant från användaren. Posterna 21–40 kan inte klassificeras utan att de
uppges, och att gissa dem skulle nyckla ledgern mot fel numrering och därmed
förstöra dess enda funktion.

**Rekommendation:** lägg masterlistan i `docs/QUANT_TERM_MASTERLIST.md` så att
den är fryst tillsammans med ledgern och inte behöver klistras in på nytt varje
batch.

---

# BATCH 2 — begrepp 21–40 (P0). Read-only, inga körningar.

Regel 5 tillämpad: skanning av `research_k/` efter 2026-08-17 12:10 gav endast
mina egna G12/G19/G13+G17 samt en fil ur det parallella spåret
(`h0_extratrees_full_decision_layer_audit`). Inget nytt sedan avstämningen.

## Modellvarning som gäller hela Batch 2

Två av de viktigaste bevisfilerna (`research_aj_signal_decay`, `fangstgrad_*`)
är märkta **H0** men ger CAGR 11,03 % respektive 11,62 % med 26,2–26,3 medelinnehav
över perioden 2021-07-16 → 2026-07-10. **Det låsta likaviktade H0 jag mätte ger
7,57 % med 30 innehav över 2020-2026.** Konstruktionen och perioden skiljer sig.

De behandlas därför som **H0-variant**, inte som låst-H0-bevis. Det är samma
disciplin som Batch 1 krävde åt andra hållet.

## Ledger — begrepp 21–40

| # | Begrepp | Status | Evidens | Modell evidensen gäller | Gap |
|---:|---|---|---|---|---|
| 21 | Momentum persistence | ALREADY TESTED | `graduation_m12_to_m52` (368 graduates / 930 washouts av 1 298), `runway_matning` (band 1-5 = 9,13 paneler), `stora_vinnare_startfas` (143 mega / 994 falska) | waterfill, universumnivå | LOW |
| 22 | Rank persistence | ALREADY TESTED | `frekvens_vs_kraft`: autokorr 4v **0,6215** topp-60, 0,9389 universum; `rankresan_djupanalys` | H0:s rankning (signalnivå) | LOW |
| 23 | Signal persistence | **DUPLIKAT av #22** | samma storhet mätt på samma objekt | — | — |
| 24 | Alpha decay | ALREADY TESTED | `research_aj_signal_decay`: baseline alpha 5,75 % (t 1,17); decay-regler A/B/C ger 5,12 / 6,10 / 5,57 % — alla inom brus | H0-variant, **ett fönster** | LOW |
| 25 | Alpha half-life | **DUPLIKAT av #24** | halveringstid är en parametrisering av samma avklingning | — | — |
| 26 | Holding-period mismatch | **PARTIALLY TESTED** | `research_aj_signal_decay` arm 1: horisontjusterat mål (8v+26v) kollapsar alfan från 5,75 % till **0,05 %** (t 0,01); arm 2 multi-horisont 5,31 % | H0-variant, ett fönster | **MEDIUM** |
| 27 | Maximum Favorable Excursion | PARTIALLY TESTED | G13+G17 mätte MFE **+36,36 %** för SÅLDA namn efter exit | H0 direkt, men bara sålda | **MEDIUM** |
| 28 | Maximum Adverse Excursion | PARTIALLY TESTED | G13+G17 mätte MAE **−22,12 %** för sålda; drawdown före återhämtning −4,40 % | H0 direkt, men bara sålda | **MEDIUM** |
| 29 | MFE capture ratio | **PARTIALLY TESTED — och fyndet är stort** | `fangstgrad_h0_h1_h2`: H0 fångar median **5,97 %** av vinnarnas rörelse men **11,31 %** av förlorarnas. Asymmetri **−5,34 pp**. H1: −1,10 pp. H2: −8,29 pp | H0-variant, **ett fönster** | **HIGH** |
| 30 | MFE giveback | **DUPLIKAT av #29** | giveback är komplementet till capture; ett test täcker båda | — | — |
| 31 | Opportunity cost | **ALREADY TESTED** | G13+G17: opp.cost negativ på **alla sex horisonter i båda fönstren**; 39–47 % slår ersättaren | **H0 direkt, båda fönstren** | INGET |
| 32 | Replacement effect | **DUPLIKAT av #31** | samma storhet sedd från ersättarens sida | — | — |
| 33 | Swap efficiency | **DUPLIKAT av #31** | G13+G17 mäter exakt bytets effektivitet; `a4_opportunity_cost_swap` (0/9) täcker regelversionen | H0 + STACK_H | — |
| 34 | Turnover drag | **ALREADY TESTED** | 228,5 % / 187,1 % omsättning × 20 bp = **0,46 / 0,37 %/år** | **H0 direkt, båda fönstren** | INGET |
| 35 | Turnover regularization / penalty | **NOT APPLICABLE** | H0 har ingen målfunktion att straffa — den är en rank-och-välj-regel. Som heuristik är den identisk med familj 1–7, **stängd** | — | — |
| 36 | Turnover buffer | **DUPLIKAT av #2/#3 — familj 1–7 STÄNGD** | får inte återöppnas under nytt namn | — | — |
| 37 | Signal smoothing | PARTIALLY TESTED | `a3_poangutjamning` 0/7 med **monoton** gradient; `granskning_baslinjeredundans` EMA2/EMA3 negativa mot både STACK_H och bar modell | STACK_H, BAR — **inte likaviktad H0** | LOW |
| 38 | Score margin | **ALREADY TESTED** | G12: marginalen är 0,0036/rankplats och dess informationsvärde **~0,2 pp/år**, replikerat | **H0 direkt, båda fönstren** | INGET |
| 39 | Forecast dispersion | PARTIALLY TESTED | `dispersion_och_ensemble`: spridning som konviktionsmått; look-ahead upptäckt och rättat, effekten föll till −0,54 % / +0,86 % | STACK_H, ERC | LOW |
| 40 | Winner concentration / right-tail | PARTIALLY TESTED | SPARI: champion 25,29 % → **leave-3 14,65 %**, leave-5 10,56 %; SPARF leave-3 14,14 %; `bredd_vs_koncentration` | SPARI-champion, SPARF, FR-overlay — **aldrig på likaviktad H0** | **MEDIUM** |

### Dubbletter länkade (6 av 20 begrepp)

`#23 ≡ #22` · `#25 ≡ #24` · `#30 ≡ #29` · `#32 ≡ #31` · `#33 ≡ #31` ·
`#36 ≡ #2/#3 (familj 1–7, stängd)`

## Det stora fyndet i Batch 2 — och varför det INTE är familj 1–7

`fangstgrad_h0_h1_h2` visar att H0 fångar **5,97 %** av vinnarnas rörelse men
**11,31 %** av förlorarnas. Asymmetrin är **−5,34 procentenheter** och går åt fel
håll.

Mekanismen bakom den är inte churn. Den är att **H0 är likaviktad och återställs
till 1/30 vid varje ombalansering.** Ett innehav som stigit 40 % sedan förra
cykeln trimmas ned till 1/30 igen; ett som fallit 20 % fylls på. H0 innehåller
alltså en systematisk kontrarian-ombalansering *inuti* portföljen, oberoende av
vilka namn som ägs.

**Detta ligger utanför familj 1–7.** Familj 1–7 handlar om *vilka namn* som byts
och när. Detta handlar om *hur mycket kapital* varje namn får medan det ägs, och
kan inte adresseras av hysteres, band, no-trade-region eller ersättningströskel.
G13+G17:s dom (exiterna är korrekta) rör det inte heller — den gäller
namnbytena, inte viktbanan.

Det är den enda genuint nya mekanismen Batch 2 identifierar.

## Förregistrerad hypotes — EJ KÖRD

### G29 — Likaviktsåterställningen som systematisk vinnartrimning (HIGH)

**Motivering.** H0 återställer till 1/30 var åttonde vecka. Fångstasymmetrin
−5,34 pp är mätt men aldrig förklarad, och aldrig prövad i två fönster eller på
det låsta likaviktade H0.

**Hypotes.** Om H0:s vikter tillåts driva med kursen mellan ombalanseringar i
stället för att återställas till 1/30, förändras netto-CAGR med **mindre än
±0,5 procentenheter** i båda fönstren.

**Falsifieras om** skillnaden överstiger ±0,5 pp i båda fönstren med samma
tecken — då är likaviktsåterställningen en ekonomiskt betydande, oavsiktlig
kontrarianregel inuti den frysta modellen.

**Not.** Detta är ingen ny tradingregel. Det mäter vad en befintlig, oavsiktlig
egenskap hos den frysta specen kostar eller tjänar. Samma karaktär som G12.

### G40 — Höger-svansberoende på låst H0 (MEDIUM)

**Motivering.** Leave-top-k är mätt på SPARI-championen och SPARF-championen,
båda invers-vol-viktade. Aldrig på likaviktad H0, där varje namn per definition
bidrar lika mycket kapital och svansberoendet därför borde se annorlunda ut.

**Hypotes.** H0:s CAGR utan sina tre största bidragsgivare faller med **mindre än
8 procentenheter** i båda fönstren.

**Falsifieras om** fallet överstiger 8 pp — då vilar H0 på ett fåtal namn i en
grad som inte framgår av det redovisade talet.

### G26 — Horisontmatchningen i två fönster (MEDIUM, villkorad)

`research_aj_signal_decay` visade att horisontjustering **kollapsar** alfan
(5,75 % → 0,05 %). Det stödjer nuvarande design, men mättes i ett fönster på en
H0-variant. En replikering i 2014-2019 på låst H0 vore bekräftande, inte
utforskande. **Låg prioritet just därför** — den kan bara bekräfta det vi redan
gör.

## Batch 2 — svar på A/B/C/D

**A. Redan besvarade (9 poster):** #21, #22, #24, #31, #34, #38 direkt; samt
#23, #25, #30, #32, #33 som dubbletter av dessa.

**B. Ej relevanta för H0 (2):** #35 (ingen målfunktion att straffa) och #36
(identisk med familj 1–7, permanent stängd).

**C. Genuina kvarvarande luckor (4):**
1. **#29/#30 fångstasymmetrin och likaviktsåterställningen** — HIGH
2. **#40 höger-svansberoende på låst H0** — MEDIUM
3. **#27/#28 MFE/MAE för INNEHAVDA positioner** (G13+G17 mätte bara sålda) — MEDIUM
4. **#26 horisontmatchning i andra fönstret** — MEDIUM men bekräftande

**D. Rangordnad testkö:**

| Ordning | Gap | Motiv |
|---:|---|---|
| **1** | **G29 likaviktsåterställningen** | Enda genuint nya mekanismen; utanför familj 1–7; mäter en oavsiktlig egenskap hos den frysta specen, inte en ny regel |
| **2** | **G40 svansberoende på låst H0** | Billig; bounds hur mycket av H0:s tal som vilar på tre namn; samma karaktär som G12 |
| 3 | #27/#28 MFE/MAE för innehav | Deskriptiv förberedelse till G29; ger fördelningen bakom fångstasymmetrin |
| 4 | G26 horisontmatchning | Bekräftande, inte utforskande — kör sist eller inte alls |

G29 och punkt 3 hör ihop: **kör dem i ordning 3 → 1**, eftersom MFE/MAE-fördelningen
för innehav är det deskriptiva underlaget som gör G29:s utfall tolkbart.

---

# G27/G28 + G29 KÖRDA — 2026-08-17. Dom: **NO MATERIAL RESET DRAG.**

Förregistrering: `research_k/g29_preregistration.json`, sha256 `e2a0675a4614e379…`
— skriven och låst **före** varje beräkning. Neutral allokeringsregel: frigjort
kapital delas lika mellan inträdande namn; vid inga inträden pro rata över
kvarvarande.

Artefakter: `research_k/g27_g28_g29_results.json`,
`research_k/g29_episoder.jsonl` (628 episoder),
`research_k/g29_portfolio_paths.json` (nettoserier för båda armarna).

**Invariantkontroll: 0 paneler med olika namnuppsättning i båda fönstren.** Armarna
äger exakt samma bolag; endast vikterna skiljer.

## Modellrättelse som ingår

Mina tidigare H0-körningar satte vikterna till 1/N vid **varje** panel, alltså även
på mellanpanelen där låst H0 inte handlar. Här driver vikterna på mellanpanelen i
båda armarna och återställning sker endast på rebalanspanelen. Nivån flyttas
marginellt (H0 2020-2026: 7,57 % → 7,20 %) men G12/G19/G13+G17:s domar berörs
inte — de mätte namnval, inte viktbanor.

## Steg 1 — G27/G28 MFE/MAE på låst H0

| | 2020-2026 | 2014-2019 |
|---|---:|---:|
| Positionsepisoder | 317 | 311 |
| MFE, medel | +31,91 % | +45,06 % |
| MAE, medel | −13,94 % | −10,87 % |
| Faktisk return, medel | +2,20 % | +18,77 % |
| **Fångstgrad (return/MFE), median** | **−0,193** | **0,244** |

H0 realiserar alltså en fjärdedel av toppen i det tidiga fönstret och **mindre än
noll** i det sena — medianepisoden i 2020-2026 avslutas under sitt startpris trots
att den varit uppe +31,9 % på vägen.

### Vad H0 gör vid nästa rebalance

| Läge | 2020-2026 | ret före | Δvikt | **ret efter 2 paneler** |
|---|---:|---:|---:|---:|
| B trimmas | 40,7 % | +15,91 % | −0,0048 | **+1,74 %** |
| C fylls på | 27,3 % | −7,41 % | +0,0030 | **−0,17 %** |
| D säljs | 32,0 % | −9,72 % | −0,0298 | — |

| Läge | 2014-2019 | ret före | Δvikt | **ret efter 2 paneler** |
|---|---:|---:|---:|---:|
| B trimmas | 42,0 % | +17,87 % | −0,0042 | **+4,01 %** |
| C fylls på | 31,5 % | −4,47 % | +0,0030 | **+4,25 %** |
| D säljs | 26,6 % | −5,46 % | −0,0302 | — |

**Korrelation mellan avkastning före rebalance och viktändring: −0,947 och −0,913.**
Det bekräftar mekaniken entydigt: **H0 tar systematiskt kapital från det som stigit
och tillför det som fallit.** Frågan är bara om det kostar något.

Grupperna definieras av *förfluten* avkastning, som är känd vid beslutet, och
utvärderas på *efterföljande* avkastning. Ingen framtidsbetingning.

## Steg 2 — G29 ablation

| | 2020-2026 A / B | 2014-2019 A / B |
|---|---|---|
| CAGR | 7,20 % / 6,38 % | 31,56 % / 30,67 % |
| **B − A CAGR** | **−0,82 %** | **−0,89 %** |
| Bootstrap KI | [−2,60 %, +3,92 %], t −0,09 | [−2,72 %, +0,71 %], t −0,48 |
| Volatilitet | — | 17,22 % / 17,56 % |
| MaxDD | −33,50 % / −35,84 % | −19,73 % / −21,34 % |
| Sharpe | — | 1,703 / 1,619 |
| Omsättning/år | 234,1 % / 177,0 % | 196,7 % / 147,6 % |
| Kostnad/år | — | 0,39 % / 0,30 % |
| Max vikt, högsta | 0,0823 / **0,1668** | 0,0596 / **0,1392** |
| Effektivt antal innehav | 29,7 / 25,7 | 29,8 / 26,3 |

### Attribution (2014-2019, aritmetisk summa över perioden)

| Källa | Bidrag |
|---|---:|
| Övervikt i drivna vinnare | **+18,21 %** |
| Undervikt i drivna förlorare | **−22,66 %** |
| Lägre omsättningskostnad i B | +0,60 % |
| Summa | −3,86 % |

Drift tjänar alltså på att äga mer av vinnarna — men **förlorar mer på att äga
mindre av förlorarna**. Namnen vars vikt drivit ned steg tillräckligt efteråt för
att påfyllningen skulle löna sig. Det är samma sak som steg 1 visar: påfyllda
namn ger +4,25 % mot trimmade namns +4,01 % i det tidiga fönstret.

**H0:s likaviktsåterställning är en köp-dippen-regel inuti portföljen, och den
betalar sig.**

### Robusthet

Fem största bidragsgivare till viktdifferensen: SIVE −3,13 %, HTRO +2,78 %,
BONEX +1,89 % (2020-2026); NET-B +6,36 %, G5EN +3,06 %, HNSA +2,35 % (2014-2019).
Det största enskilda namnet står för **187 % respektive 143 %** av
viktdifferensen — attributionen är alltså dominerad av ett fåtal namn och ska
inte överbetonas.

CAGR-differensens **tecken replikerar** över båda fönstren (−0,82 % och −0,89 %),
men bootstrapens konfidensintervall täcker noll i båda.

## Klassificering

**NO MATERIAL RESET DRAG.** Den förregistrerade falsifieringen — *DRIFT − RESET
överstiger +0,5 pp i båda fönstren* — inträffade inte. Drift är i stället
**sämre** med 0,82 och 0,89 procentenheter, med samma tecken i båda fönstren.

Utöver avkastningen försämrar drift risken entydigt: maxDD −2,3 respektive
−1,6 pp sämre, högsta enskilda vikt fördubblas till 16,7 % respektive 13,9 %, och
effektivt antal innehav faller från ~30 till ~26. Den enda fördelen är lägre
omsättning, värd 0,10 pp per år — långt under det viktbanan kostar.

## Rekommendation: spåret STÄNGS

Fångstasymmetrin från Batch 2 är **verifierad som mekanism men falsifierad som
problem**. H0 tar mycket riktigt kapital från vinnare och ger till förlorare
(korrelation −0,95), och realiserar bara en fjärdedel av MFE. Men att låta bli
kostar avkastning i båda fönstren och försämrar risken påtagligt.

**Inget separat viktarkitekturtest licensieras.** Stoppreglerna gäller: inga
1/20- eller 1/25-varianter, ingen score- eller volatilitetsviktning, inget tak på
vinnarvikt, ingen efterhandsvald hybrid.

Ett resultat värt att notera separat: `fangstgrad`-filernas asymmetri gällde en
H0-variant och pekade mot ett problem som inte finns på låst H0. Modellvarningen i
Batch 2 var alltså befogad och avgörande.

---

# BATCH 3 — begrepp 41–60 (momentumfamiljen). Read-only, inga körningar.

Regel 5: skanning efter 2026-08-17 14:00 gav endast mina egna G29-artefakter.
Inget parallellt spår har tillkommit.

**Referens genomgående: locked H0 = 7,20 % CAGR (2020-2026), 31,56 % (2014-2019)**
efter vikträttelsen i G29. Äldre filer märkta "H0" verifieras mot implementation,
period, antal innehav, rebalansfrekvens och viktlogik före klassificering.

## Fyra evidensnivåer — tillämpade strikt i denna batch

1. *signalen finns* · 2. *signalen predicerar avkastning* · 3. *signalen förbättrar
H0:s beslut* · 4. *signalen förbättrar faktisk portfölj*. Flera poster nedan når
nivå 1–2 och stannar där; det räknas inte som besvarat på nivå 4.

## Ledger — begrepp 41–60

| # | Begrepp | Mekanism | Relation till locked H0 | Status | Evidens | Modell | Gap |
|---:|---|---|---|---|---|---|---|
| 41 | Cross-sectional momentum | Relativ styrka inom tvärsnittet | **ÄR H0** — poängen är percentilrank inom datum | ALREADY TESTED | SPARF; H1419-replikering +12,15 pp (KI [+4,25, +23,74], t 3,27) | locked H0 | **INGET** |
| 42 | Time-series momentum | Egen historik, absolut trend — distinkt premie från tvärsnittet | **SAKNAS HELT.** Låst H0 har ingen trendgrind (verifierat i `H0_LOCK.json`) | **PARTIALLY TESTED** | SPARF F7 trendbrottsexit (ingen passerade); D8 SMA-längder mot STACK_H (SMA300 +1,91 %/−1,96 %, adaptiv 0/2); STACK_H har SMA200 inbyggd | SPARF-champion, STACK_H — **aldrig som tillägg till låst H0** | **MEDIUM** |
| 43 | Intermediate momentum | 12-2 / 12-7, hoppa över senaste månaden | H0 använder 12m och 18m **utan skip** | ALREADY TESTED | `reversal_och_kopband`: kanonisk 12_0 [0,1434 / 0,3008], skip_4v [0,1230 / 0,2491], skip_8v [0,1170 / 0,2187] — **monotont sämre i BÅDA fönstren** | H0-variant | LOW |
| 44 | Short-term reversal | Senaste månadens uppgång vänder | Mekanismen finns **i** H0:s topp | ALREADY TESTED — nivå 2 nådd, nivå 4 misslyckad | `reversal_och_kopband`: band 1-5 fore_4v +10,72 % → framåt +0,21 %; band 26-30 +3,98 % → +0,87 %, replikerar båda fönstren. Exploatering: `kopband_mot_ratt_modeller` 0/8, köpband 11-40 −2,81/−1,07, D6 nolloperation | H0-variant, V_A, ERC, STACK_H | LOW |
| 45 | Long-term reversal | 3–5 års omvändning | Inte i H0 | NOT TESTED | `kortare_lookback` täcker 3–24 mån, inte 36–60 | — | LOW — 3-5 år konsumerar nästan hela historiken; svag mekanistisk motivering |
| 46 | Residual momentum | Momentum efter borttagen marknads-/faktorexponering | Inte i H0 | PARTIALLY TESTED | SPARI Batch 1: residual solo mean IC 0,1447 men **Top-30 IC −0,0380**; 50/50-blend Top-30 IC −0,0191, CAGR 20,34 % — sämre på alla robusthetsmått | **SPARI-champion, ej locked H0** | LOW–MEDIUM |
| 47 | Idiosyncratic momentum | Samma sak, annan etikett | — | **DUPLIKAT av #46** | — | — | — |
| 48 | Industry momentum | Branschens momentum | Inte i H0 | PARTIALLY TESTED | K1: en post SVAGT STÖD, tre INGET STÖD; täckningsmatrisen: ingen PIT-försvarbar historisk sektorstatus | K1, SPARI | LOW |
| 49 | Sector momentum | Samma sak | — | **DUPLIKAT av #48** | — | — | — |
| 50 | Factor momentum | Momentum i faktoravkastningar | Inte i H0 | **NOT APPLICABLE** | Kräver PIT-faktoravkastningspanel som inte finns | — | — |
| 51 | Momentum acceleration | Andraderivatan — tilltagande styrka | Inte i H0; H0 ser bara nivån | **PARTIALLY TESTED** | `momentumkurvan` 0/6 mot STACK_H; `granskning_statisk_vs_dynamisk` D2 tvärsnittslutning: **−1,23 % / +1,90 %, tidig KI [+0,96, +3,21] utesluter noll, jackknife 6/6 mot 0/6** | **STACK_H — aldrig locked H0** | **HIGH** |
| 52 | Momentum deceleration | Samma mekanism, motsatt tecken | — | **DUPLIKAT av #51** | — | — | — |
| 53 | Momentum breadth | Andel namn med positivt momentum | Inte i H0 | PARTIALLY TESTED | K5 `market_breadth_6m`: **SVAGT/OSÄKERT**, 12 mot 8 paneler, första kronologiska halvan saknar båda tillstånd; legacys breddfynd återtogs som survivorship-belastat och förklarades omätbart | K5 på fryst H0 | LOW |
| 54 | Momentum spread | Spridningen i momentumpoäng | Finns implicit — poängmarginalen | ALREADY TESTED | **G12**: marginal 0,0036/rankplats, informationsvärde ~0,2 pp/år, replikerat; `dispersion_och_ensemble` (look-ahead upptäckt och rättad, −0,54 %/+0,86 %) | **locked H0** (G12) + STACK_H | LOW |
| 55 | Momentum concentration | Beroende av ett fåtal stora bidrag | Finns i H0 | **PARTIALLY TESTED** | `research_l_long_horizon`: CAGR 7,61 % → leave-top1 6,00 %, **leave-top3 4,06 %**, leave-top5 1,98 %; topp-3 andel 36,6 % (SIVE, ATIC, HTRO) | H0-variant nära låst (7,61 mot 7,20 %) — **endast sena fönstret** | **MEDIUM** — länkad till Batch 2:s G40 |
| 56 | Momentum crash | Abrupt förlorarrally efter björnmarknad | Inte observerad i H0:s data | **NOT TESTED — och ej falsifierbar** | K5: VIX-stress n=**1**, hög volatilitet n=3, negativ trend n=4 — OTILLRÄCKLIG DATA. 2020 var V-format, 2022 en utdragen nedgång; ingen klassisk momentumkrasch i urvalet | K5 | LOW |
| 57 | Momentum crash sensitivity | Beta mot kraschregim | — | **DUPLIKAT av #56** | — | — | — |
| 58 | Reversal risk | Risk för omvändning | — | **DUPLIKAT av #44 + #56** | — | — | — |
| 59 | Snapback / rebound | Sålda namn studsar tillbaka | Direkt observerad | **ALREADY TESTED** | **G13+G17 på locked H0**: 96,7 % återhämtar till exitpriset inom 52 v, MFE +36,36 % — men opportunity cost mot faktisk ersättare **negativ på alla sex horisonter i båda fönstren** | **locked H0, båda fönstren** | **INGET** |
| 60 | Trend strength | t-värde för prisets trendlutning | **ÄR H2** (50 % H0 + 50 % trendstyrka) | **ALREADY TESTED** | `h0_h1_h2_tvafonster`: H2 8,05 %/28,31 % mot H0 7,57 %/31,54 %; **Top-30 IC 0,0192 / 0,0057**; B−A +0,48 %/−3,23 % — faller tvåfönsterkravet | **locked H0-konstruktion, båda fönstren** | **INGET** |

### Dubbletter länkade (6 av 20)

`#47 ≡ #46` · `#49 ≡ #48` · `#52 ≡ #51` · `#57 ≡ #56` · `#58 ≡ #44 + #56` ·
`#55 ≡ #40 (Batch 2)`

### Transformationskontroll

**#43 intermediate momentum** och **#44 short-term reversal** är inte nya
informationskällor — de är omskärningar av samma prisserie H0 redan läser. Båda
är prövade och båda misslyckas som *inkrement*, vilket är den relevanta frågan.
**#54 momentum spread** är en transformation av H0:s egen poängfördelning och
avgjord av G12.

## Batch 3 — svar på A/B/C/D

### A. ALREADY ANSWERED (7 poster)

**#41** (H0 *är* cross-sectional momentum), **#43** (skip monotont sämre i båda),
**#44** (mekanismen replikerar men ingen regel fångar den, 0/8 + 0/6),
**#54** (G12 på locked H0), **#59** (G13+G17 på locked H0), **#60** (H2 faller),
samt **#53** som data-begränsad till SVAGT/OSÄKERT.

### B. NOT APPLICABLE / DUPLIKAT (7 poster)

**#50** factor momentum — kräver PIT-faktorpanel som inte finns.
**#47, #49, #52, #57, #58** — dubbletter, länkade i ledgern.
**#56/#57** momentum crash — formellt NOT TESTED men **ej ärligt falsifierbar**
med vårt urval: K5 har ett enda VIX-stressdatum. Ska inte generera ett test.

### C. GENUINA LOCKED-H0-LUCKOR (4)

1. **#51/#52 momentumacceleration** — den tvärsnittliga lutningsregeln är
   programmets enda fynd med KI som utesluter noll och 6/6 jackknife, men den
   är mätt mot **STACK_H**, aldrig mot locked H0.
2. **#42 time-series momentum** — locked H0 saknar varje absolut trendvillkor.
   STACK_H:s SMA200 är en av fyra overlays och paketet replikerar inte
   (+0,69 pp sent, −2,16 pp tidigt), men komponenten ensam är oprövad på H0.
3. **#55/#40 momentumkoncentration** — leave-top-k finns för det sena fönstret
   (7,61 → 4,06 % vid leave-top3) men **saknas helt för 2014-2019**.
4. **#46 residual momentum** — Top-30 IC negativ hos SPARI, men aldrig mätt på
   locked H0:s likaviktade konstruktion.

### D. RANGORDNAD TESTKÖ

Endast luckor med en rimlig mekanism genom vilken de kan förbättra *förståelsen
av* eller *besluten i* locked H0.

| Ordning | Gap | Motiv | Förregistrerad hypotes |
|---:|---|---|---|
| **1** | **#51/52 acceleration på locked H0** | Enda fyndet i hela programmet med KI som utesluter noll i ett fönster och stabil jackknife. Att veta dess tecken på den modell som faktiskt går framåt har reellt informationsvärde även om den inte får befordras | Att ta bort de 20 % av namnen vars H0-poäng försämrats mest över tre paneler ändrar locked H0:s netto-CAGR med **mindre än ±1,0 pp i det sena fönstret** |
| **2** | **#55/40 koncentration i tidiga fönstret** | Billig, oberoende av regelfrågor, och bounds hur mycket av H0:s 31,56 % som vilar på tre namn. Samma karaktär som G12 | Locked H0:s CAGR utan sina tre största bidragsgivare faller med **mindre än 8 pp i båda fönstren** |
| 3 | **#42 time-series momentum på locked H0** | Mekanistiskt distinkt från tvärsnittet och helt frånvarande i H0. Men SMA-komponenten har fallit i varje tidigare form | Ett absolut trendvillkor (pris ≥ SMA200) på locked H0 förbättrar netto-CAGR i **båda** fönstren |
| — | #46 residual momentum | **Läggs inte i kön.** Top-30 IC är negativ hos SPARI, alltså misslyckad redan på evidensnivå 3. Att köra om den på locked H0 saknar mekanistiskt skäl | — |
| — | #45, #50, #53, #56, #57 | **Läggs inte i kön** — data-blockerade, ej falsifierbara eller utan mekanism | — |

Tre av tjugo begrepp genererar alltså ett test, inte tjugo. Sju är besvarade,
sju är dubbletter eller ej tillämpliga, och tre luckor bedöms inte förtjäna en
körning trots att de formellt är oprövade.

---

# BATCH 3:s LICENSIERADE TESTER KÖRDA — 2026-08-17

Locked H0 reproducerade exakt i båda fönstren: **7,20 %** och **31,56 %**.
Artefakter: `research_k/g55_g51_g42_results.json`,
`research_k/g55_g51_g42_paneldata.jsonl` (urval per panel).

## A. G55/G40 — koncentration och höger-svansberoende

| | 2020-2026 | 2014-2019 |
|---|---:|---:|
| Bidragsgivare med positivt bidrag | 213 | 184 |
| HHI på positiva bidrag | 0,0249 (eff. 40,2) | 0,0177 (**eff. 56,4**) |
| Topp-1 andel av vinst | 7,7 % | 4,2 % |
| Topp-3 | 16,2 % | 11,0 % |
| Topp-5 | 24,6 % | 17,1 % |
| Topp-10 | 39,8 % | 30,7 % |
| CAGR utan topp-1 | 5,13 % (−2,07) | 29,99 % (−1,57) |
| **CAGR utan topp-3** | **2,64 % (−4,56)** | **27,99 % (−3,57)** |
| CAGR utan topp-5 | 1,69 % (−5,51) | 26,92 % (−4,64) |
| Trimmat bidrag (1:a/99:e pct) | 5,86 % | 31,01 % |
| Klassificering | **MODERATELY CONCENTRATED** | **ROBUST** |

**Den förregistrerade hypotesen håller i båda fönstren** — fallet vid borttagning
av topp-3 är 4,56 respektive 3,57 procentenheter, båda under gränsen 8 pp.

Men fönstren skiljer sig kvalitativt. I 2014-2019 bär topp-3 elva procent av
vinsten och det effektiva antalet bidragsgivare är 56. I 2020-2026 bär topp-3
sexton procent, effektivt antal 40, och att ta bort fem namn tar CAGR från 7,20 %
till **1,69 %** — nästan hela resultatet. Sämsta enskilda leave-one-out är SIVE
(−2,07 pp) respektive HNSA (−1,57 pp).

**Slutsats: H0 är inte höger-svansberoende, men det sena fönstrets resultat är
tunt.** 7,20 % med topp-5 borttagna blir 1,69 %; det talet ska ligga bredvid
7,20 % varje gång det citeras.

## B. G51/G52 — accelerationens inkrementella signal: **NO INCREMENTAL SIGNAL**

Definitionen återanvändes oförändrad: `H0_score(k, panel_i) − H0_score(k, panel_i−3)`.
Population: H0:s topp-30 vid beslutstidpunkten.

| Horisont | 2020-2026 rank-IC (t) | residual-IC (t) | 2014-2019 rank-IC (t) | residual-IC (t) |
|---|---:|---:|---:|---:|
| 4 v | −0,0325 (−1,31) | −0,0338 (−1,44) | −0,0056 (−0,27) | +0,0008 (0,04) |
| 8 v | −0,0435 (−1,84) | −0,0376 (−1,59) | +0,0159 (0,81) | +0,0236 (1,14) |
| 12 v | −0,0471 (−1,87) | −0,0451 (−1,84) | +0,0078 (0,37) | +0,0105 (0,47) |
| 24 v | −0,0400 (−1,55) | −0,0358 (−1,37) | +0,0017 (0,08) | +0,0065 (0,30) |

**Tecknet byter mellan fönstren på varje horisont, och ingen t når 1,96.**
Steg 3 är därmed **EJ LICENSIERAT** och kördes inte.

### Varför detta inte motsäger det tidigare D2-fyndet

D2:s regel filtrerade **hela universumet** — den tog bort lågsluttande namn innan
urvalet och ändrade därmed *vilka namn som kom in* i topp-30. Detta test mäter
inkrementell information *inom* topp-30, alltså ordningen bland redan valda namn.
Två olika marginaler.

Steg 3:s förregistrerade variant opererar på topp-30, så steg 2:s population är
rätt grind för den. Men D2:s universumfiltrering förblir oprövad på locked H0 —
och den ska inte köras nu: den skulle vara ett nytt test, inte det licensierade.

## C. G51/G52 portföljvärde — **EJ KÖRT**, ej licensierat

## D. G42 — SMA200

### Diagnostik

| Horisont | 2020-2026 över / under / diff (t) | residual-IC (t) | 2014-2019 över / under / diff (t) | residual-IC (t) |
|---|---|---:|---|---:|
| 4 v | +1,10 % / −3,18 % / **+4,28 % (2,99)** | +0,0340 (1,24) | +2,14 % / +2,92 % / −0,78 % (−0,46) | **+0,0523 (2,16)** |
| 8 v | +2,14 % / −4,50 % / **+6,64 % (2,76)** | +0,0358 (1,46) | +4,53 % / +4,57 % / −0,05 % (−0,03) | **+0,0542 (2,46)** |
| 12 v | +3,66 % / −5,75 % / **+9,40 % (3,23)** | +0,0275 (0,97) | +6,96 % / +6,03 % / +0,93 % (0,38) | **+0,0552 (2,35)** |
| 24 v | +8,77 % / −2,38 % / **+11,15 % (3,10)** | **+0,0747 (2,39)** | +14,34 % / +10,04 % / +4,30 % (1,20) | **+0,0882 (3,41)** |

Den **råa** skillnaden replikerar inte — den är stark i 2020-2026 och frånvarande
i 2014-2019. Men **residual-IC efter kontroll för H0-score är positiv på samtliga
åtta celler**, och signifikant på fyra av fyra i det tidiga fönstret.

Att den råa skillnaden är noll medan residualen är signifikant i 2014-2019 betyder
att SMA200-status samvarierar med H0-poängen där och maskeras av den.

### Portföljtest (licensierat av diagnostiken)

Namn under SMA200 ersätts av nästa H0-rankade kandidat över SMA200. N=30 hålls.
Ingen kassaregel.

| | 2020-2026 A → B | 2014-2019 A → B |
|---|---|---|
| CAGR | 7,20 % → **9,35 %** (+2,15) | 31,56 % → **33,16 %** (+1,60) |
| Volatilitet | 21,71 % → 21,72 % (+0,01) | 17,22 % → 16,80 % (−0,42) |
| MaxDD | −33,50 % → −34,97 % (**−1,47**) | −19,73 % → −18,30 % (+1,43) |
| Sharpe | 0,228 → 0,327 (+0,099) | 1,703 → 1,841 (+0,138) |
| Bootstrap KI | [−1,65 %, +5,78 %], t +1,45 | [−0,98 %, +3,26 %], t +1,07 |

**Positiv med samma tecken i båda oberoende fönstren.** Den förregistrerade
nollhypotesen — *SMA200 förbättrar inte netto-CAGR i båda fönstren* — förkastas
på punktskattningarna.

### Tre förbehåll som måste stå bredvid talen

1. **Båda konfidensintervallen täcker noll** (t +1,45 och +1,07). Riktningen
   replikerar, storleken är inte signifikant.
2. **Placebo har INTE körts.** Regeln byter ut namn, och programmets etablerade
   disciplin kräver jämförelse mot slumpmässigt utbyte av lika många namn.
   Utan den kan +2,15 pp inte kallas en edge. Detta är det första som ska göras.
3. **Mekanismen är inte ny i programmet.** `CONTROL_C_SMA200` finns redan i
   registret som HISTORICAL_REFERENCE_ONLY, och SPARF:s champion hade en
   SMA200-**skipgrind** som sänkte exponeringen. Det som prövats här är en
   **ersättningsregel** som håller N=30 konstant — en distinkt konstruktion, men
   inte en ny signal.

Dessutom: risken går åt olika håll i fönstren. MaxDD blir 1,47 pp **sämre** i det
sena fönstret och 1,43 pp bättre i det tidiga.

## E. Spår som STÄNGS

* **G51/G52 acceleration inom topp-30** — NO INCREMENTAL SIGNAL, tecknet byter
  mellan fönstren. Stängt. Familjen får inte återöppnas som "momentum
  deceleration", "signalförändring" eller liknande.
* **G55/G40 koncentration** — hypotesen håller i båda fönstren. Stängt som
  forskningsfråga; talet "7,20 % blir 1,69 % utan topp-5" behålls som
  redovisningskrav, inte som testkö.

## F. Vad som förtjänar ytterligare förregistrerad forskning

**Endast G42, och endast i denna ordning:**

1. **Placebo på SMA200-ersättningen** — slumpmässigt utbyte av lika många namn
   per panel, 200+ dragningar, båda fönstren. Faller regeln inom placebobandet
   stängs spåret omedelbart.
2. Om den överlever placebot: **attribution** — kommer vinsten från att undvika
   namnen under SMA200, eller från att ta in djupare rankade namn över SMA200?
   Det avgör om fyndet är trendfiltret eller köpbandet i förklädnad.
3. **Överlappskontroll mot SPARF F7 och `CONTROL_C_SMA200`** innan något
   beskrivs som nytt.

Ingenting befordras. H0 är fryst och forward startar 2026-09-04.

---

# G42 — TRE FALSIFIERINGSSTEG KÖRDA 2026-08-17. **SPÅRET STÄNGS.**

Artefakter: `research_k/g42_falsifiering_results.json`,
`research_k/g42_eventledger.jsonl` (171 byten, granskningsbar utan omkörning).
1000 placebodragningar per fönster, fast seed 20260817.

## Steg 1 — Placebo. **Faller i det tidiga fönstret.**

Placebot matchar exakt: antal byten per panel, N=30, rebalanstiming, exekvering,
kostnad, likaviktsåterställning **och det rankdjup G42 faktiskt når** (median 33,
max 59 respektive median 32, max 41). Placebot fick alltså inget sämre
kandidatuniversum.

| | 2020-2026 | 2014-2019 |
|---|---:|---:|
| G42 Δ CAGR | +2,15 % | +1,60 % |
| **Placebo medel** | **−1,12 %** | **+0,99 %** |
| Placebo p5 / p95 | −3,28 % / +0,89 % | −0,61 % / +2,60 % |
| G42:s percentil | **99,7 %** | **73,5 %** |
| **Ensidigt p** | **0,003** | **0,265** |
| Klarar placebo | **JA** | **NEJ** |

**Det avgörande talet är placebots medelvärde i det tidiga fönstret: +0,99 %.**
Att slumpmässigt byta ut lika många namn mot namn från rank 31–41 ger i sig
nästan en procentenhet. G42:s +1,60 % är alltså till största delen *att byta på
det djupet*, inte *SMA200-informationen*. Marginalen mot slumpen är 0,6 pp och
ligger mitt i placebofördelningen.

Det bekräftar exakt den alternativhypotes som skulle prövas: i det tidiga
fönstret fungerar regeln **som ett köpband i förklädnad**, inte som ett
trendfilter.

I det sena fönstret är bilden den motsatta — där kostar slumpmässiga byten
−1,12 % och G42 ligger på percentil 99,7.

## Steg 2 — Attribution. Mekanismen replikerar inte.

Dekomponering mot neutral referens M = medelavkastning för behållna topp-30-namn:
`B − A = (M − A) + (B − M)` = avoidance + selection.

| Horisont | 2020-2026 B−A (t) | avoidance (t) | selection (t) |
|---|---:|---:|---:|
| 4 v | +3,54 % (2,32) | **+5,55 % (4,38)** | **−2,01 % (−2,21)** |
| 8 v | +3,78 % (1,59) | **+6,58 % (3,03)** | −2,80 % (−1,82) |
| 12 v | +5,85 % (1,99) | **+10,47 % (4,06)** | **−4,62 % (−2,40)** |
| 24 v | +9,62 % (2,19) | **+12,75 % (3,53)** | −3,13 % (−1,30) |

| Horisont | 2014-2019 B−A (t) | avoidance (t) | selection (t) |
|---|---:|---:|---:|
| 4 v | +0,51 % (0,26) | −0,33 % (−0,21) | +0,84 % (0,67) |
| 8 v | +3,10 % (1,30) | +1,26 % (0,60) | +1,85 % (1,06) |
| 12 v | +4,54 % (1,53) | +1,66 % (0,59) | +2,88 % (1,38) |
| 24 v | +7,46 % (1,33) | +4,81 % (1,02) | +2,65 % (0,86) |

**Mönstren är motsatta.** I 2020-2026 kommer hela värdet från *avoidance* — att
inte äga namnet under SMA200 — medan *selection* är **signifikant negativ**:
ersättarna går sämre än de behållna namnen. I 2014-2019 är avoidance obetydlig
och inget är signifikant.

En mekanism som byter tecken mellan fönstren är ingen mekanism.

### Robusthet

12-veckorsvärdet +5,85 % faller till **+4,08 % utan ISOFOL** — ett enda namn bär
30 % av effekten. De tre största bidragen är +173,4 %, +129,8 % och −93,8 %. I
det tidiga fönstret: +4,54 % → +3,40 % utan SGG.

## Steg 3 — Overlap / novelty audit (read-only ur registret)

| Modell | Roll | Vad som händer med namn under SMA200 | N | CAGR | Vol | MaxDD | Status |
|---|---|---|---|---:|---:|---:|---|
| `T0_A_CONTROL_H0` | H0 topp-30, 50/50 12m+18m | inget filter | 30 | 7,57 % | 21,51 % | −33,81 % | HISTORICAL_REFERENCE_ONLY |
| `CONTROL_C_SMA200` | **H0 + SMA200 SKIP-grind** | **hoppas över, exponeringen sjunker** | <30 | **11,55 %** | 19,56 % | −28,82 % | HISTORICAL_REFERENCE_ONLY |
| `VA_RETURN_CHALLENGER` | **H0 + SMA200 + InvVol 1-6 %** | skip | <30 | 12,87 % | 18,39 % | −24,93 % | **ACTIVE_FROZEN_FORWARD** |
| G42 (detta test) | H0 + SMA200 **ersättning** | ersätts av nästa rankade över SMA200 | 30 | 9,35 % | 21,72 % | −34,97 % | kandidat |

Två saker framgår direkt.

**SMA200 är inte en ny signal i programmet.** Den sitter redan i den frysta
championen `VA_RETURN_CHALLENGER` och finns som eget registrerat kontrollobjekt.

**Skip-versionen är bättre än min ersättningsversion i samma fönster:** 11,55 %
mot 9,35 %, med lägre volatilitet och grundare drawdown. Ersättningskonstruktionen
är alltså inte bara icke-ny — den är sämre än den redan registrerade varianten.

*(Registrets tal använder H0-implementationen med viktåterställning varje panel,
alltså 7,57 % som baslinje. Jämförelsen skip mot ersättning är ändå giltig
eftersom båda mäts mot samma baslinje.)*

**Klassificering: B. KNOWN SIGNAL, NEW PORTFOLIO CONSTRUCTION** — och den nya
konstruktionen är underlägsen den kända.

## Slutdom mot de fyra evidensnivåerna

| Nivå | Utfall |
|---|---|
| 1. SMA200 har prediktiv information | **JA** — etablerat sedan tidigare, `CONTROL_C_SMA200` |
| 2. SMA200 tillför information utöver H0-score | **DELVIS** — residual-IC positiv i 8/8 celler |
| 3. SMA200 väljer bättre ersättningar än slumpen | **NEJ** — p 0,003 sent men **0,265** tidigt |
| 4. G42 förbättrar faktisk portfölj | **EJ VISAT** — nivå 3 föll |

Beslutsregeln var: *om G42 inte ligger tydligt i högersvansen relativt korrekt
matchat placebo i BÅDA fönstren — stäng G42.*

# **G42 STÄNGS som portföljkandidat.**

Attributionen och överlappsauditen behålls som metodkunskap men får enligt
förregistreringen inte användas för att rädda kandidaten.

## Vad som lärdes och ska bäras vidare

1. **Slumpmässiga byten på rank 31–41 gav +0,99 % i 2014-2019.** Varje framtida
   regel som hämtar namn djupare i rankningen måste jämföras mot det, annars
   mäter man köpbandet och kallar det något annat.
2. **Avoidance och selection kan ha motsatta tecken.** I 2020-2026 var selection
   signifikant **negativ** medan totaleffekten var positiv. Att bara rapportera
   B − A hade dolt det.
3. Ett enda namn (ISOFOL) bar 30 % av effekten i det sena fönstret.

Ingen ytterligare SMA-forskning licensieras: ingen annan längd, ingen buffer,
ingen regimregel, ingen kombination med andra overlays.

---

# BATCH 4 — begrepp 61–80 (prisbanans form). Read-only, inga körningar.

Regel 5: skanning efter 2026-08-17 16:00 gav noll nya artefakter.

Referens: locked H0 **7,20 %** (2020-2026) / **31,56 %** (2014-2019). Vid citering
av 7,20 % gäller Batch 3:s redovisningskrav: **1,69 % utan topp-5**.

## Centrala frågan för batchen

H0 använder momentum**nivå**. Två aktier med samma 12m-avkastning kan ha nått dit
på helt olika vägar. Frågan är inte om det går att bygga en snyggare
momentumindikator, utan: **innehåller vägen till dagens H0-score stabil
inkrementell information som H0-score/rank inte redan fångar?**

## Featureregistret — vad som redan existerar

`docs/probes/feature_registry.json` innehåller 53 features. Relevanta här:

| Feature | Formel | Täcker begrepp |
|---|---|---|
| `trend_consistency_52w` | andel positiva veckor, 52 v | #74, #75 |
| `trend_strength_52w` | t-stat, OLS(log(adj)~tid), 52 v | #66, #73 |
| `risk_adj_momentum_52w` | mom_52w / vol_52w | #77, #78, #79 |
| `max_drawdown_52w`, `drawdown_current_104w` | min(adj/running_max −1) | #76 |
| `skew_52w`, `kurtosis_52w` | fördelningsform, veckoavkastningar | #71, #72 (delvis) |
| `downside_vol_52w`, `idio_vol_52w`, `vol_13w`, `vol_52w` | risknormaliserare | #77–#80 |
| `residual_momentum_52w` | kumulativ residual mot marknadsmodell | #80 (IR-momentum) |

**Ingen feature mäter effektivitetskvot (nettorörelse delat med summan av
absoluta rörelser).** Det är den enda formen av bankvalitet som saknas helt.

## Ledger — begrepp 61–80 med dedupliceringsfamiljer

### Familj T — trendens ålder (61–65)

| # | Term | Mekanism | Relation till H0 | Status | Evidens | Modell |
|---:|---|---|---|---|---|---|
| 61 | Trend persistence | Trender fortsätter | Indirekt: H0 väljer på nivå, inte längd | ALREADY TESTED | `graduation_m12_to_m52` 368 graduates / 930 washouts; `runway_matning` band 1-5 = 9,13 paneler | waterfill, universumnivå |
| 62 | Trend exhaustion | Trender tar slut | Saknas | PARTIALLY TESTED | `momentumkurvan` "toppnära" (är mom_12m sitt 6-panelshögsta): **0/6** | STACK_H |
| 63 | Trend maturity | Var i trenden vi är | **DUPLIKAT av #62** | — | — | — |
| 64 | Trend age | Tid sedan trendstart | Saknas — ingen feature i registret | NOT TESTED | — | — |
| 65 | Trend duration | Trendens längd | **DUPLIKAT av #64** | — | — | — |

**Familjens prior är negativ.** G51/G52 (accelerationen, alltså förändringen i
H0-score) gav **NO INCREMENTAL SIGNAL** på locked H0 med teckenbyte mellan
fönstren. Trendålder är en nära släkting till samma information.

### Familj B — banans form (66–73)

| # | Term | Mekanism | Relation till H0 | Status | Evidens | Modell |
|---:|---|---|---|---|---|---|
| 66 | Trend quality | Hur ren trenden är | Finns som feature | **ALREADY TESTED** | = H2. `h0_h1_h2_tvafonster`: Top-30 IC 0,0192/0,0057, B−A +0,48 %/−3,23 % | **locked H0-konstruktion** |
| 67 | Trend efficiency | Nettorörelse / total rörelse | **SAKNAS HELT** | **NOT TESTED** | ingen feature, inget test | — |
| 68 | Price efficiency / efficiency ratio | Kaufman ER, samma sak | **DUPLIKAT av #67** | — | — | — |
| 69 | Path dependency | Vägen spelar roll | Abstraktion, inte en feature | NOT APPLICABLE som eget test | subsumeras av #67 och #71–73 | — |
| 70 | Return path | Avkastningsbanan | **DUPLIKAT av #69** | — | — | — |
| 71 | Smoothness of trend | Jämnhet | Delvis via skew/kurtosis | PARTIALLY TESTED | SPARI Batch 1 "jump diffuseness": **SVAGT STÖD** | SPARI-champion |
| 72 | Trend noise | Brus kring trenden | **DUPLIKAT av #71** | — | — | — |
| 73 | Trend-to-noise ratio | Signal delat med brus | ≈ trend_strength_52w (t-stat är just detta) | **DUPLIKAT av #66** | H2 faller | locked H0-konstruktion |

### Familj K — riktningskonsistens (74–75)

| # | Term | Status | Evidens | Modell |
|---:|---|---|---|---|
| 74 | Directional consistency | **PARTIALLY TESTED — BLOCKERAD** | `trend_consistency_52w` **vann först preliminärt i Spår F**, men adversarial QA fann att blueprinten säger andel positiva **veckor** medan aktiv C-kod räknar positiva **handelsdagar** (max abs avvikelse 0,282). **Spår F stoppades och resultatet ogiltigförklarades.** SPARF punkt 5: featuren är *"fortsatt felmärkt i fryst C och får inte användas innan ett separat C-beslut fattas"* | SPARF (ogiltigförklarad) |
| 75 | Positive-week ratio | **DUPLIKAT av #74** — det är exakt blueprintens definition | — | — |

SPARI Batch 2 lade till: framtida veckohypoteser får endast använda den
**oberoende veckorekonstruktionen**; en C-rättning kräver separat versionsbeslut.

**Detta är den enda posten i hela Batch 4 där en feature faktiskt vann innan den
föll — och den föll på ett definitionsfel, inte på ett resultat.**

### Familj R — riskjusterat momentum (76–80)

| # | Term | Status | Evidens | Modell |
|---:|---|---|---|---|
| 76 | Drawdown-adjusted momentum | **ALREADY TESTED** | = **H1**. `h0_h1_h2_tvafonster`: Top-30 IC **+0,0348 / +0,0528 (t 1,36 / 2,40)** — **positiv i BÅDA fönstren**. Men CAGR B−A +4,47 % / −5,48 % — faller tvåfönsterkravet | **locked H0-konstruktion** |
| 77 | Risk-adjusted momentum | **ALREADY TESTED** | `skarpare_ranking` D: **−4,75 % / −3,48 %** i båda fönstren. SPARI: redan testad i Spår F | STACK_H, SPARF |
| 78 | Volatility-adjusted momentum | **DUPLIKAT av #77** — `risk_adj_momentum_52w` = mom_52w/vol_52w | — | — |
| 79 | Sharpe momentum | **DUPLIKAT av #77** | — | — |
| 80 | Information-ratio momentum | **DUPLIKAT av #46** (residual momentum, stängd i Batch 3) | SPARI: Top-30 IC −0,0380 solo | SPARI-champion |

## Det viktigaste enskilda fyndet i Batch 4

**#76 drawdown-adjusted momentum (H1) är programmets enda feature som når
evidensnivå 3 i båda fönstren och ändå misslyckas på nivå 5.**

Top-30 IC +0,0348 och +0,0528, positiv i båda, signifikant i det tidiga. Alltså:
informationen finns, den är inkrementell, och den replikerar. Ändå ger H1 −5,48 pp
CAGR i det tidiga fönstret.

Förklaringen är dokumenterad sedan tidigare: **Track H är likaviktad.** H1 vet
mätbart vilka av de 30 som är bäst, och i en portfölj där alla får 3,33 % kan den
kunskapen inte omsättas. Det är den renaste illustrationen i hela programmet av
att prediction skill ≠ portfolio value — och den bör citeras när någon frestas
att läsa ett IC-tal som ett löfte.

## A. ALREADY ANSWERED (7 av 20)

**#61** trend persistence, **#66** trend quality (= H2, faller), **#71** smoothness
(jump diffuseness, SVAGT STÖD), **#73** trend-to-noise (= #66), **#76**
drawdown-adjusted (nivå 3 ja, nivå 5 nej), **#77** risk-adjusted (−4,75/−3,48),
**#80** IR-momentum (= residual, stängd Batch 3).

## B. NOT APPLICABLE / DUPLIKAT (9 av 20)

`#63 ≡ #62` · `#65 ≡ #64` · `#68 ≡ #67` · `#70 ≡ #69` · `#72 ≡ #71` ·
`#73 ≡ #66` · `#75 ≡ #74` · `#78 ≡ #77` · `#79 ≡ #77` · `#80 ≡ #46`

**#69/#70 path dependency** är en abstraktion, inte en mätbar feature. Den
subsumeras av #67 och #71–73 och ska inte generera ett eget test.

## C. GENUINA LOCKED-H0-LUCKOR (3)

1. **#67/#68 effektivitetskvot** — den enda formen av bankvalitet som saknas helt
   ur featureregistret, och den renaste formaliseringen av batchens centrala
   fråga: samma avkastning, olika väg.
2. **#74/#75 riktningskonsistens** — en feature som vann preliminärt och
   ogiltigförklarades på ett definitionsfel, inte på ett resultat. Blockeraren är
   känd och har en känd lösningsväg (oberoende veckorekonstruktion).
3. **#62/#64 trendens ålder och utmattning** — genuint oprövad på locked H0, men
   med negativ prior från G51/G52.

## D. RANGORDNAD TESTKÖ

Båda köade hypoteserna testar **information**, inte portföljregler, och båda
ändrar namnval om de går vidare.

| Ordning | Gap | Förregistrerad hypotes | Prio |
|---:|---|---|---|
| **1** | **#67/68 effektivitetskvot** | Bland namn med jämförbar aktuell H0-score/rank predicerar effektivitetskvoten (nettoförändring över 52 v delat med summan av absoluta veckoförändringar) framtida 4/8/13/26 v avkastning **med samma tecken i båda oberoende fönstren**, efter kontroll för aktuell H0-score/rank | **MEDIUM-HIGH** |
| **2** | **#74/75 riktningskonsistens** | Samma formulering med `trend_consistency_52w` beräknad ur den **oberoende veckorekonstruktionen** (inte fryst C, som är felmärkt) | **MEDIUM** |

**Båda markeras: REQUIRES MATCHED-RANDOM PLACEBO IF SIGNAL TEST PASSES.**

### Vad som INTE köas

* **#62/#64 trendålder** — negativ prior från G51/G52, som mätte nära besläktad
  information på locked H0 och gav teckenbyte. Köas inte utan nytt skäl.
* **Hela familj R (#76–80)** — #77 är kraftigt negativ i båda fönstren, #76 är
  avgjord på nivå 5, resten är dubbletter.
* **#69/#70** — inte en mätbar storhet.

### Ärlig prior för kön

Varje bankvalitetsfeature som prövats hittills har fallit: H2 trendstyrka faller,
acceleration ger teckenbyte, `momentumkurvan` 0/6, riskjusterat momentum
−4,75/−3,48. Jump diffuseness nådde bara SVAGT STÖD. **Förväntan bör vara att
även effektivitetskvoten faller.** Värdet ligger i att stänga den sista formen av
bankvalitet som inte är prövad, inte i att hitta något.

## Räkning

| | |
|---|---:|
| Begrepp i Batch 4 | 20 |
| Genuina locked-H0-luckor | **3** |
| Luckor som förtjänar en körning | **2** |
| Ekonomiskt distinkta mekanismer efter deduplicering | **4** (trendålder, banans form, riktningskonsistens, riskjustering) |
| Totalt genomgångna av 326 | **80** |

---

# BATCH 4:s TESTER KÖRDA — 2026-08-17. **Batch 4 STÄNGS.**

Artefakter: `research_k/g67_g74_results.json`,
`research_k/g67_g74_paneldata.jsonl` (4 350 observationer, granskningsbara utan
omkörning). Population: locked H0:s topp-30, 65 respektive 78 paneler.

### Förregistrerade definitionsbeslut (fattade före beräkning)

1. ER52 på **veckovisa** prisinkrement, ISO-veckor, sista handelsdag i veckan —
   eftersom featureregistrets övriga banmått alla räknar veckor.
2. Minst 45 av 52 veckoavkastningar krävs.
3. Ingen alternativ horisont. 52 veckor för båda måtten.
4. Spår F:s ogiltiga `trend_consistency_52w`-resultat användes **inte** för att
   välja definition, sätta tröskel, tolka riktning eller bekräfta hypotes. PWR52
   byggdes från den oberoende veckorekonstruktionen.

## Metodfynd som gäller retroaktivt: överlappande framåtfönster

Forward-horisonterna 8v, 12v och 24v mäts från paneler som ligger **en panel
isär**. En 6-panelshorisont överlappar därför med 5/6 mellan intilliggande
observationer. Ett t-värde som behandlar panelerna som oberoende är kraftigt
uppblåst.

Effektivt antal oberoende observationer ≈ n/h. Justeringen är t/√h.

**Detta gäller retroaktivt allt IC-arbete i programmet med h > 1 panel** — G51/G52
och G42:s diagnostik. I båda fallen var domen negativ, och en deflation av
t-värdena kan bara stärka en negativ dom. **Ingen tidigare dom ändras.** Men
G42:s diagnostiska residual-IC vid 24v (t 3,41) blir justerat t 1,39, vilket gör
att den delen av G42:s underlag var svagare än det redovisades som.

## A. G67/G68 Efficiency Ratio — **PROMISING-BUT-UNSTABLE**

| Fönster | Horisont | residual-IC | t naivt | **t justerat** | topp−botten | t just |
|---|---|---:|---:|---:|---:|---:|
| 2020-2026 | **4 v (h=1)** | **+0,0618** | 2,59 | **+2,59** | +2,48 % | +2,58 |
| 2020-2026 | 8 v | +0,0668 | 2,98 | +2,11 | +4,39 % | +2,18 |
| 2020-2026 | 12 v | +0,0730 | 2,86 | +1,65 | +5,82 % | +2,26 |
| 2020-2026 | 24 v | +0,1037 | 4,43 | +1,81 | +9,07 % | +1,59 |
| 2014-2019 | **4 v (h=1)** | **+0,0014** | 0,06 | **+0,06** | −0,18 % | −0,21 |
| 2014-2019 | 8 v | +0,0391 | 1,79 | +1,27 | +1,22 % | +0,74 |
| 2014-2019 | 12 v | +0,0632 | 2,86 | +1,65 | +1,58 % | +0,62 |
| 2014-2019 | 24 v | +0,1089 | 5,11 | +2,09 | +7,42 % | +1,50 |

**Tecknet är detsamma i båda fönstren på alla fyra horisonter** — det talar för
signalen. Men:

* **Den enda icke-överlappande horisonten (4 v) ger +0,0618 (t 2,59) i det sena
  fönstret och +0,0014 (t 0,06) i det tidiga.** Alltså exakt noll där.
* Efter överlappskorrigering når **inget** topp−botten-mått signifikans i det
  tidiga fönstret (t +0,62 till +1,50).
* Kvintilstrukturen är stigande i grova drag — Q1 är lägst i 7 av 8 celler och
  Q5 > Q1 i samtliga — men inte monoton i någon cell.

Klassificering: **PROMISING-BUT-UNSTABLE.** Riktningen replikerar; styrkan gör
det inte, och den rena horisonten visar ingenting i det tidiga fönstret.

## B. G74/G75 Positive Week Ratio — **NO INCREMENTAL SIGNAL**

| Fönster | 4 v | 8 v | 12 v | 24 v |
|---|---:|---:|---:|---:|
| 2020-2026 residual-IC (t just) | +0,0142 (0,58) | +0,0208 (0,64) | +0,0202 (0,53) | +0,0504 (0,89) |
| 2014-2019 residual-IC (t just) | **−0,0338 (−1,54)** | **−0,0351 (−1,09)** | **−0,0429 (−1,19)** | −0,0232 (−0,50) |

**Tecknet byter mellan fönstren på samtliga horisonter.** I det tidiga fönstret
är sambandet negativt — fler positiva veckor förutsäger *sämre* avkastning bland
jämförbart rankade namn — och kvintilerna faller från Q3 och uppåt (+6,2 %,
+8,4 %, +9,0 %, +5,0 %, +3,9 % vid 12 v). Inget t-värde når 1,96 efter
korrigering.

Det tidigare Spår F-resultatet, som hade denna feature som preliminär vinnare,
byggde på fel definition. **Byggd korrekt ur veckorekonstruktionen faller den.**

## C. Dedupliceringskontroll

| Fönster | n | Pearson | Spearman |
|---|---:|---:|---:|
| 2020-2026 | 1 980 | +0,460 | +0,465 |
| 2014-2019 | 2 370 | +0,420 | +0,417 |

Måtten är måttligt korrelerade — de mäter besläktade men inte identiska
aspekter av bankvalitet. **Den ömsesidiga kontrollen kördes inte**, eftersom den
bara är meningsfull om båda visar signal. Det är korrekt enligt förregistreringen
och inte en utelämnad körning.

## D. Evidensnivåer

| Nivå | ER52 | PWR52 |
|---|---|---|
| 1. Deskriptiv mekanism | JA | JA |
| 2. Prediction skill | JA sent, **NEJ tidigt** | NEJ |
| 3. **Inkrementell** prediction skill | **INSTABIL** | **NEJ** |
| 4. Decision skill | ej testad | ej testad |
| 5. Portfolio value | ej testad | ej testad |

Enligt H1-varningen: ett positivt IC är inte en förbättring av H0. H1 hade
Top-30 IC +0,0348/+0,0528 i **båda** fönstren — starkare replikation än ER52 —
och gav ändå −5,48 pp CAGR i det tidiga fönstret.

## E. Vad som STÄNGS

* **G74/G75 riktningskonsistens** — stängd. Teckenbyte, ingen signifikans efter
  korrigering. Familjen får inte återöppnas som "positive-day ratio",
  "win rate", "hit rate" eller liknande.
* **G67/G68 effektivitetskvot** — stängd **som kandidat**. Nådde inte
  REPLICATED INCREMENTAL SIGNAL, och förregistreringens grind var explicit.

## F. Förtjänar något ett separat decision/portfolio-test?

**Nej.** Förregistreringen var entydig: *om ingen av signalerna klassificeras
REPLICATED INCREMENTAL SIGNAL — stäng Batch 4, kör inget mer.*

ER52:s riktningsreplikation noteras i ledgern som den starkaste bankvalitets-
observationen programmet gjort, men den räcker inte, och ett portföljtest får
inte licensieras på ett PROMISING-BUT-UNSTABLE-utfall. Skulle ER52 tas upp igen
i framtida orörd data gäller **REQUIRES MATCHED-RANDOM PLACEBO IF SIGNAL TEST
PASSES** oförändrat.

**Efter Batch 1–4 finns inga öppna kandidater.** 80 av 326 begrepp genomgångna.

## Ny permanent metodregel

> **Regel 6.** Varje IC- eller kvintiltest med forward-horisont längre än en
> panel ska redovisa **överlappskorrigerat** t-värde (t/√h) vid sidan av det
> naiva. Ett naivt t-värde på överlappande fönster är inte ett bevis.

---

# BATCH 5 — begrepp 81–100 (risk- och volatilitetsfamiljen). Read-only.

Regel 5: inga nya artefakter sedan Batch 4.

## Avgörande fynd i underlaget: riskarkitekturmatrisen fanns redan

`research_k/research_v_risk_architecture_results.json` innehåller en **fullständig
bas × riskregel-matris på H0** som inte tidigare räknats in i ledgern. Bas
`A_H0_Original` (ren H0, inget ADV-filter, ingen SMA):

| Riskregel | CAGR | maxDD | vol | kassa | n_eff |
|---|---:|---:|---:|---:|---:|
| EW_Base (= H0) | 7,61 % | −33,81 % | 21,52 % | 0 % | 30,0 |
| **InverseVol** | **10,12 %** | −29,33 % | 20,08 % | 0 % | 26,8 |
| InvVol_TargetVol_15 % | 9,53 % | **−21,40 %** | 16,12 % | 11,0 % | 40,6 |
| TargetVol_17,5 % | 6,96 % | −29,39 % | 18,02 % | 10,9 % | 42,7 |
| TargetVol_15 % | 6,49 % | −28,00 % | 16,44 % | 17,2 % | 53,2 |
| TargetVol_12,5 % | 5,70 % | −25,67 % | 14,35 % | 27,1 % | 73,4 |
| ClusterPenalty | 7,61 % | −33,81 % | 21,52 % | 0 % | 30,0 |

**Invers volatilitetsviktning ger +2,51 pp på ren H0.** Volatilitetsmålsättning
kostar 1,1–1,9 pp och köper drawdown. Klusterstraff gör exakt ingenting.

**Men: ett enda fönster** (66 paneler, 2021-07-16 → 2026-07-10) och basen är
7,61 %, alltså den okorrigerade viktimplementationen — inte 7,20 %.

## Tre användningar av volatilitet hålls isär

**A = prediktion** (vet volatiliteten vilken aktie som går bäst?) ·
**B = viktning** (ska mindre volatila innehav få mer kapital?) ·
**C = exponering** (ska hela portföljens exponering ändras när risken är hög?)

## Ledger — begrepp 81–100

| # | Term | Typ | Relation till locked H0 | Status | Evidens | Modell | Familj | Gap |
|---:|---|:-:|---|---|---|---|:-:|---|
| 81 | Volatility scaling | C | Saknas | **DUPLIKAT av #82** | — | — | V-E | — |
| 82 | Volatility targeting | C | Saknas i H0; finns som `VB_CAPITAL_PRESERVATION` | ALREADY TESTED | `research_v`: TargetVol 12,5/15/17,5 % ger **−1,91/−1,12/−0,65 pp** och sänker maxDD 4–8 pp. SPARI Batch 1: **INGET STÖD** | H0-variant (ett fönster), SPARI-champion | V-E | LOW |
| 83 | Inverse-volatility weighting | B | **Saknas i locked H0** (likaviktad). Finns i V_A och STACK_H | **PARTIALLY TESTED** | `research_v` A_H0: **+2,51 pp** i ett fönster. SPARI Batch 1 INGET STÖD (annan modell). `granskning_baslinjeredundans` BAR (H0+SMA+invvol) 12,87 %/29,98 % mot locked H0 7,20 %/31,56 % — men SMA ingår och kan inte separeras | **H0-variant, ett fönster** | V-W | **HIGH** |
| 84 | Risk parity | B | Saknas | **DUPLIKAT av #83** (invvol är risk parity vid antagen nollkorrelation) | — | — | V-W | — |
| 85 | Equal risk contribution | B | Finns som `SHADOW_ERC_X2` (invvol^1,5) | PARTIALLY TESTED | Registret: ERC 13,60 %. Men byggd på V-familjens bas, inte likaviktad H0 | ERC-modellen | V-W | LÄNKAD till #83 |
| 86 | Volatility timing | C | Saknas | ALREADY TESTED | K5: marknadsvolatilitet 3m — **OTILLRÄCKLIG DATA** (17 låga mot 3 höga paneler). `research_n` N3 regimgrind: 5,77 % mot 7,61 % | K5 på fryst H0, H0-variant | V-E | LOW |
| 87 | Volatility regime | C | Saknas | **DUPLIKAT av #86** | — | — | V-E | — |
| 88 | Realized volatility | A/B | Finns som feature (`vol_13w`, `vol_52w`), används i viktning | PARTIALLY TESTED | Feature existerar; som **prediktor** inom topp-30 aldrig mätt på locked H0 | featureregistret | V-M | LÄNKAD till #97 |
| 89 | Downside volatility | A/B | Finns som `downside_vol_52w` | ALREADY TESTED | SPARI: *"downside-riskjusterat momentum … redan testat i Spår F"* | SPARF | V-M | LOW |
| 90 | Semivariance | A/B | **DUPLIKAT av #89** | — | — | — | V-M | — |
| 91 | Downside deviation | A/B | **DUPLIKAT av #89** | — | — | — | V-M | — |
| 92 | Upside/downside asymmetry | A | Delvis via `skew_52w` | PARTIALLY TESTED | SPARI Batch 1 jump diffuseness SVAGT STÖD; skew finns som feature men aldrig prövad som inkrementell prediktor | SPARI-champion | V-M | LOW |
| 93 | Volatility clustering | — | Tidsserieegenskap, inte tvärsnittlig | **NOT APPLICABLE** | H0 väljer tvärsnittligt; klustring är en egenskap hos en enskild serie över tid | — | V-M | — |
| 94 | Volatility persistence | — | **DUPLIKAT av #93** | — | — | — | V-M | — |
| 95 | Volatility-of-volatility | A | Ingen feature | NOT TESTED | — | — | V-M | LOW — svag mekanism för tvärsnittligt urval |
| 96 | Idiosyncratic volatility | A | Finns som `idio_vol_52w` | PARTIALLY TESTED | Feature existerar, aldrig prövad som inkrementell prediktor inom topp-30 | featureregistret | V-P | LÄNKAD till #97 |
| 97 | Low-volatility effect | A | Saknas som signal | **NOT TESTED** | Ingen IC-prövning inom locked H0:s topp-30. Invers-vol-viktning är den *portföljmässiga* uttrycksformen, inte signaltestet | — | V-P | **MEDIUM** |
| 98 | Low-beta anomaly | A | `beta_52w` finns som feature | **NOT TESTED** | Aldrig prövad som inkrementell prediktor | featureregistret | V-P | LÄNKAD till #97 |
| 99 | Beta-adjusted momentum | A | **DUPLIKAT av #46** residual momentum (stängd i Batch 3) | ALREADY TESTED | SPARI: residual solo Top-30 IC **−0,0380** | SPARI-champion | V-P | — |
| 100 | Defensive momentum | A | Momentum bland lågrisknamn = #97 ∩ H0 | **DUPLIKAT av #97** | — | — | V-P | — |

### Dedupliceringsfamiljer

`V-W` viktning (83, 84, 85) · `V-E` exponering (81, 82, 86, 87) ·
`V-M` mätning (88–95) · `V-P` lågriskanomalin (96–100)

Åtta av tjugo begrepp är rena dubbletter.

## A. ALREADY ANSWERED (6)

**#82** vol targeting (kostar 0,65–1,91 pp, köper drawdown; SPARI INGET STÖD),
**#86/#87** vol timing/regim (K5 otillräcklig data, regimgrind 5,77 %),
**#89/#90/#91** downside-familjen (Spår F), **#99** beta-adjusted (= residual,
stängd).

## B. NOT APPLICABLE / DUPLIKAT (10)

`#81 ≡ #82` · `#84 ≡ #83` · `#87 ≡ #86` · `#90 ≡ #89` · `#91 ≡ #89` ·
`#94 ≡ #93` · `#99 ≡ #46` · `#100 ≡ #97`

**#93/#94 volatilitetsklustring och -persistens är NOT APPLICABLE**: de är
tidsserieegenskaper hos en enskild aktie, medan H0 väljer tvärsnittligt. De
genererar inget test.

## C. GENUINA LOCKED-H0-LUCKOR (3)

1. **#83/#84/#85 invers volatilitetsviktning på locked H0, två fönster** — typ B.
   Ett fönster visar **+2,51 pp**. Den ändrar **inte vilka namn som ägs**, bara
   hur mycket. Batch 2 stängde reset-mot-drift, inte risk-baserad viktning.
2. **#97/#96/#98/#100 lågriskanomalin som inkrementell signal** — typ A. Aldrig
   prövad som IC inom locked H0:s topp-30, trots att `vol_52w`, `idio_vol_52w`
   och `beta_52w` alla finns i featureregistret.
3. **#95 volatilitet-av-volatilitet** — typ A, ingen feature, men svag mekanism.

## D. RANGORDNAD TESTKÖ

| Ordning | Gap | Typ | Förregistrerad hypotes | Prio |
|---:|---|:-:|---|---|
| **1** | **#83 invers-vol-viktning** | **B** | Att vikta locked H0:s topp-30 med invers 60-dagarsvolatilitet i stället för lika vikt, med samma namn, samma paneler, samma exekvering och samma kostnadsmodell, förbättrar netto-CAGR i **båda** oberoende fönstren | **HIGH** |
| **2** | **#97 lågriskanomalin** | **A** | Bland namn med jämförbar aktuell H0-score/rank predicerar **lägre** `vol_52w` framtida 4/8/13/26 v avkastning med samma tecken i båda fönstren, efter kontroll för aktuell H0-score/rank | **MEDIUM** |

**#83 kräver INTE matched-random placebo** — den byter inga namn. Det gör den
metodiskt mycket enklare att avgöra än allt som prövats sedan Batch 1: ingen
selection-skill-konfundering, ingen kandidatpool att matcha. Utfallet är rent
en viktfråga.

**#97 markeras REQUIRES MATCHED-RANDOM PLACEBO IF SIGNAL TEST PASSES** — om den
skulle gå vidare till en urvalsregel byter den namn.

### Vad som INTE köas

* **#82/#86 exponeringsfamiljen** — kostar avkastning i det enda fönster vi har
  och är riskkontroll, inte alfa. Dessutom är `VB_CAPITAL_PRESERVATION`
  (target-vol-modellen) **inte reproducerbar ur det kanoniska skriptet**; det
  är en dataintegritetsblockerare som måste lösas före allt target-vol-arbete.
* **#93/#94** — inte tvärsnittliga.
* **#95** — ingen rimlig mekanism för tvärsnittligt urval.
* **#89–#92** — Spår F täcker dem, och de är estimatorval snarare än mekanismer.

## E. RISK-FAMILY MAP

| Användning | Mekanismer | Status |
|---|---|---|
| **A — prediktion** | lågriskanomalin (97, 96, 98, 100), asymmetri (92), vol-av-vol (95) | **ÖPPEN** för 97-familjen; övriga låg prioritet |
| **B — viktning** | invers vol (83), risk parity (84), ERC (85) | **ÖPPEN** på locked H0; testad på andra modeller |
| **C — exponering** | vol scaling/targeting (81, 82), vol timing/regim (86, 87) | **STÄNGD** — kostar avkastning, K5 saknar data, V_B ej reproducerbar |

## F. METHODOLOGY FLAGS

1. **`research_v_risk_architecture` och `research_n_risk_engine` är ett fönster**
   (66 paneler, 2021-2026) och basen är 7,61 %, alltså den **okorrigerade**
   viktimplementationen. Inga av deras tal är locked-H0-bevis i tvåfönstermening.
2. **`research_n` N2_Trailing_Stop_15 %: 18,53 % mot 7,61 %.** Det är den största
   enskilda överavkastningen i hela materialet — och `passes_quality_framework`
   är **False**. Det är dessutom en drawdown-exit, alltså den familj SPARI Batch 2
   redan avgjorde på H0 (DD20 → INGET STÖD). **Får inte återöppnas** på grundval
   av detta ena tal.
3. **`VB_CAPITAL_PRESERVATION` går inte att reproducera** ur
   `research_ag_reconciliation_canonical.py` — target-vol är en nolloperation där
   och V-A/V-B ger bit-identiska serier. Blockerar allt #81/#82-arbete.
4. **Regel 6 berör Batch 5 endast marginellt**: nästan all evidens här är
   portföljnivå (CAGR/maxDD), inte IC med överlappande framåtfönster. Om #97 körs
   gäller Regel 6 fullt ut.

## Räkning

| | |
|---|---:|
| Begrepp i Batch 5 | 20 |
| Genuina locked-H0-luckor | **3** |
| Förtjänar en körning | **2** |
| Ekonomiskt distinkta mekanismer efter dedup | **4** (viktning, exponering, mätning, lågriskanomali) |
| Totalt genomgångna av 326 | **100** |

---

# G83 och G97 KÖRDA — 2026-08-17

Förregistrering `research_k/g83_g97_preregistration.json`, sha256
`df3bc9272dcf055c...`, låst före all beräkning. Artefakter:
`research_k/g83_g97_results.json` (inkl. nettoserier för båda armarna),
`research_k/g83_g97_paneldata.jsonl` (4 350 observationer).

## G83 — invers-vol-viktning: **FÖRBÄTTRAR ENDAST I ETT FÖNSTER**

Viktablation, typ B. **Invariantkontroll: 0 avvikelser** i namnuppsättning — båda
armarna äger exakt samma bolag varje panel. Ingen matched-random placebo behövs.

| | 2020-2026 A → B | 2014-2019 A → B |
|---|---|---|
| CAGR | 7,20 % → **8,57 %** (**+1,37**) | 31,56 % → **31,34 %** (**−0,22**) |
| Volatilitet | 21,71 % → 19,71 % | 17,22 % → 16,86 % |
| MaxDD | −33,50 % → −28,15 % (+5,35) | −19,73 % → −18,82 % (+0,91) |
| Sharpe | 0,228 → 0,321 | 1,703 → 1,726 |
| Omsättning/år | 234,1 % → 277,4 % | 196,7 % → 232,8 % |
| **Max vikt, högsta** | 0,082 → **0,220** | 0,060 → 0,082 |
| Effektivt antal, lägsta | 27,7 → **12,9** | 29,2 → 24,6 |
| Bootstrap B−A | +1,37 %, KI [−0,91 %, +4,52 %], t +0,40 | −0,22 %, KI [−1,80 %, +2,27 %], t −0,21 |

**Faller tvåfönsterkravet.** Riktningen replikerar inte, och ingetdera KI utesluter
noll.

Två observationer utöver domen:

* Riskmåtten förbättras i **båda** fönstren — volatilitet ned, drawdown upp
  5,35 respektive 0,91 pp, Sharpe upp. Invers-vol är alltså ett fungerande
  *riskinstrument*, precis som lönsamhetsgrindarna var det. Men inte ett
  avkastningsinstrument.
* Priset är koncentration: högsta enskilda vikt stiger från 8,2 % till **22,0 %**
  och effektivt antal innehav faller till 12,9 som lägst i det sena fönstret. Utan
  viktak — och locked H0 har inga — blir invers vol påtagligt koncentrerad.

Det tidigare enfönstertalet **+2,51 pp** från `research_v` blir **+1,37 pp** på den
viktkorrigerade basen. Ännu ett exempel på att den okorrigerade
H0-implementationen överdrev en effekt.

**V-W-familjen (#83/#84/#85) stängs.**

## G97 — lågriskanomalin: **REPLICATED INCREMENTAL SIGNAL**

Informationstest, typ A. IC mäts mot `vol_52w`; hypotesen förutsäger **negativ**
IC. Regel 6 tillämpad — **h=1 är den enda icke-överlappande horisonten och utgör
primärbeviset**.

| Fönster | Horisont | IC(vol) | residual-IC | t naiv | **t justerat** | låg−hög | kvintiler lågvol→högvol |
|---|---|---:|---:|---:|---:|---:|---|
| 2020-2026 | **4 v (h=1)** | −0,0914 | **−0,1067** | −4,05 | **−4,05** | +2,02 % | +1,5 +1,4 +0,9 +0,5 **−0,5** |
| 2020-2026 | 8 v | −0,1185 | −0,1244 | −4,73 | −3,34 | +4,88 % | +3,0 +2,3 +1,4 +1,0 −1,9 |
| 2020-2026 | 12 v | −0,1237 | −0,1302 | −4,61 | −2,66 | +6,15 % | +3,8 +2,9 +2,2 +1,0 −2,3 |
| 2020-2026 | 24 v | −0,1512 | −0,1583 | −5,10 | −2,08 | +10,87 % | +6,2 +7,4 +6,1 +1,2 −4,7 |
| 2014-2019 | **4 v (h=1)** | −0,0655 | **−0,0571** | −2,34 | **−2,34** | +0,91 % | +2,4 +3,0 +2,0 +2,8 +1,5 |
| 2014-2019 | 8 v | −0,1029 | −0,0925 | −4,23 | −2,99 | +2,61 % | +5,2 +5,4 +3,9 +5,0 +2,6 |
| 2014-2019 | 12 v | −0,1158 | −0,1052 | −4,88 | −2,82 | +4,11 % | +8,0 +7,6 +5,5 +7,5 +3,9 |
| 2014-2019 | 24 v | −0,1722 | −0,1640 | −7,76 | −3,17 | +11,09 % | +16,4 +15,0 +10,8 +15,0 +5,4 |

**Samma tecken på samtliga åtta celler, och den icke-överlappande horisonten är
signifikant i båda fönstren** (t −4,05 och −2,34). Kvintilstrukturen i 2020-2026
är monotont fallande vid 4 v.

Detta är **den första REPLICATED INCREMENTAL SIGNAL i hela auditen** (begrepp
1–100).

## Den avgörande spänningen mellan de två testen

G97 säger: bland H0:s topp-30 går lågvolatila namn bättre, med t −4,05 och −2,34.
G83 säger: att vikta efter invers volatilitet ger +1,37 och **−0,22** pp.

**Informationen finns och replikerar. Dess mest naturliga portföljuttryck gör det
inte.** Det är samma mönster som H1 (Top-30 IC +0,0348/+0,0528 men −5,48 pp CAGR),
fast här är båda leden mätta i samma körning på samma modell.

Tre möjliga skäl, ingen av dem prövad:
1. Invers vol är en **kontinuerlig lutning** som samtidigt koncentrerar — högsta
   vikt 22 %, effektivt antal ned till 12,9. Den koncentrationen kan äta upp
   informationsvinsten.
2. Signalen kan sitta i **ytterkanten** — att undvika högvolkvintilen — snarare
   än i en jämn lutning. Kvintiltabellen antyder det: i 2020-2026 är Q1–Q3 nära
   varandra (+1,5, +1,4, +0,9) medan Q5 är −0,5.
3. Omsättningen stiger 36–43 pp per år.

**Noteras också:** `skarpare_ranking` D prövade riskjusterat momentum som
*rankningsersättare* (mom/vol) och fick **−4,75 % / −3,48 %**. Det motsäger inte
G97 — det är en annan marginal. Att byta ut hela rankningen mot mom/vol förstör
urvalet; att mäta volatilitetens inkrementella information *inom* det befintliga
urvalet är en annan fråga. Samma distinktion som mellan D2 och G51.

## Konsekvens för ledgern

* **#83/#84/#85 (V-W viktning) STÄNGS** — faller tvåfönsterkravet, och priset i
  koncentration är högt.
* **#97 lågriskanomalin: REPLICATED INCREMENTAL SIGNAL på nivå 3.** Nivå 4 och 5
  är **inte** visade och får inte påstås.
* **#96 idiosynkratisk volatilitet och #98 low-beta var länkade till #97 och blir
  därmed LIVE frågor**, inte stängda genom länkning. De körs dock inte nu — det
  vore ett rutnät.

## Nästa förregistrerade test — FORMULERAT, EJ KÖRT

Enligt protokollet får en signal som klarar nivå 3 aldrig befordras direkt till
portföljregel. Nästa steg formuleras men körs inte:

> **G97-P — högvolkvintilen som urvalsregel.**
> Vid varje ordinarie H0-urval ersätts de sex namn i topp-30 som har högst
> `vol_52w` med de nästa H0-rankade kandidaterna. N=30 hålls. Ingen viktändring,
> ingen kassaregel, ingen tröskeloptimering, ingen alternativ kvintilgräns.
>
> **Nollhypotes:** regeln ändrar netto-CAGR med mindre än ±1,0 pp mot canonical
> locked H0.
>
> **REQUIRES MATCHED-RANDOM PLACEBO** — matchat på antal byten per panel, N,
> timing, exekvering, kostnad och det rankdjup regeln faktiskt når. Ett positivt
> CAGR-utfall utan placebo är inte selection skill.

Motivet att välja kvintilformen framför den kontinuerliga lutningen är
kvintiltabellen ovan, inte ett resultat: Q1–Q3 ligger nära varandra medan Q5
sticker ut. Det valet ska stå i förregistreringen innan testet körs.

## Räkning efter G83/G97

100 av 326 begrepp genomgångna. **En öppen kandidat: G97-P, formulerad men ej
körd.** Samtliga övriga spår stängda.

---

# G97-P KÖRD — 2026-08-17. **REPLICATED H0 IMPROVEMENT CANDIDATE**

Första kandidat i hela auditen (begrepp 1–100) som når den klassificeringen.
**Inte fryst. Inte champion. H0 oförändrad.**

Artefakter: `research_k/g97p_results.json`,
`research_k/g97p_panelledger.jsonl` (per panel: topp-30, de sex exkluderade med
vol och H0-rank, de sex ersättarna med rank, rankdjup).

## A. Invariantkontroller

| Kontroll | 2020-2026 | 2014-2019 |
|---|---|---|
| N=30 varje rebalanspanel | **JA** | **JA** |
| Exakt sex exkluderingar | **34 av 34** | **40 av 40** |
| Voldata tillgänglig, snitt | 30,0 / 30 | 30,0 / 30 |
| Ersättarnas rankdjup | alltid 31–36 | alltid 31–36 |
| Andra namnändringar än G97-P | inga | inga |
| Framtida voldata | nej — `bisect_right(veckodatum, paneldatum)` | samma |
| Ändringar i H0-score/rank | inga | inga |

Eftersom ersättarna alltid är de sex nästa H0-rankade är regelns **enda val vilka
sex som kastas ut**. Det gör placebot exakt matchat utan approximation.

## B. Portföljresultat

| | 2020-2026 H0 → G97-P | 2014-2019 H0 → G97-P |
|---|---|---|
| CAGR | 7,20 % → **8,81 %** (**+1,61**) | 31,56 % → **34,03 %** (**+2,47**) |
| Total return | — | 429,51 % → 492,86 % |
| Volatilitet | 21,71 % → 19,75 % | 17,22 % → 16,69 % |
| MaxDD | −33,50 % → −34,36 % (−0,86) | −19,73 % → −20,08 % (−0,35) |
| Sharpe | 0,228 → **0,333** | 1,703 → **1,904** |
| Omsättning/år | 234,1 % → 264,6 % | 196,7 % → 216,6 % |
| Kostnad/år | 0,47 % → 0,53 % | 0,39 % → 0,43 % |
| Effektivt antal / högsta vikt | 30 / 3,33 % oförändrat | 30 / 3,33 % oförändrat |
| **Bootstrap** | KI **[−2,36 %, +8,27 %]**, t +0,39 | KI **[−4,73 %, +5,35 %]**, t +0,84 |

Nollhypotesen var att effekten är mindre än ±1,0 pp. Den överskrids i båda
fönstren. **Men båda konfidensintervallen täcker noll.** Riktningen replikerar;
storleken är inte statistiskt fastställd.

Noteras: drawdown blir marginellt **sämre** i båda fönstren. Regeln är inte ett
riskinstrument.

## C. Matched-random placebo — 1000 dragningar per fönster

| | 2020-2026 | 2014-2019 |
|---|---:|---:|
| G97-P Δ CAGR | +1,61 % | +2,47 % |
| Placebo medel | **−3,16 %** | **−0,76 %** |
| Placebo median | −3,14 % | −0,78 % |
| Placebo p5 / p95 | −5,99 % / −0,54 % | −3,27 % / +1,74 % |
| **G97-P percentil** | **99,7 %** | **98,1 %** |
| **Ensidigt p** | **0,0030** | **0,0190** |
| Andel placebo som slår G97-P | 0,3 % | 1,9 % |
| Marginal mot slumpen | **+4,77 pp** | **+3,23 pp** |

**Klarar placebot i båda fönstren.** Det etablerar matched-random selection
skill: valet av vilka sex som kastas ut bär verklig information.

Men lägg märke till placebots medelvärde. **Slumpmässig exkludering är kraftigt
negativ** (−3,16 % i det sena fönstret). En stor del av G97-P:s marginal mot
slumpen är att den *undviker den skada slumpen orsakar*, inte att den adderar
avkastning. Det är två olika påståenden.

## D. Decision skill — ersättare minus utkastad

| Horisont | 2020-2026 medel / hit / t Regel6 / t NW | 2014-2019 medel / hit / t Regel6 / t NW |
|---|---|---|
| **4 v (h=1)** | **−1,59 %** / 55,4 % / −0,97 / −0,98 | **−0,57 %** / 50,8 % / −0,42 / −0,43 |
| 8 v | +1,09 % / 54,5 % / +0,33 / +0,59 | +1,57 % / 55,1 % / +0,69 / +0,90 |
| 12 v | +1,40 % / 58,6 % / +0,21 / +0,40 | +2,37 % / 57,3 % / +0,79 / +1,14 |
| 24 v | +4,71 % / 58,6 % / +0,49 / +0,89 | +5,63 % / 59,9 % / +0,84 / +1,92 |

Tecknen är identiska mellan fönstren på **varje** horisont, vilket uppfyller
kriteriet. **Men inget t-värde når signifikans i något fönster på någon horisont**,
och den enda icke-överlappande horisonten (4 v) är **negativ i båda**.

Detta är kedjans svagaste led och ska inte tonas ned.

## E. Robusthet och koncentration

| | 2020-2026 | 2014-2019 |
|---|---|---|
| B−A 12 v, otrimmat | +1,40 % | +2,37 % |
| 1 %-trimmat | +4,35 % | +2,37 % |
| Tre största namnbidrag | SIVE −662,6 %, ISOFOL +221,4 %, VESTUM −214,6 % | HNSA −212,8 %, SGG +166,2 %, IMMU +152,0 % |
| Utan största namnet | +4,82 % | +3,55 % |
| Största enskilda panel | 2026-03-20 (−590,3 %) | 2016-11-30 (−131,2 %) |

**Robusthetssignaturen är gynnsam, inte ogynnsam.** De största enskilda
bidragen går **mot** regeln, och att ta bort dem gör resultatet **bättre**
(+1,40 → +4,82 och +2,37 → +3,55). Effekten drivs alltså inte av ett fåtal
lyckosamma namn — den överlever sina egna värsta fall.

Per-namn-spridningen är däremot enorm (±600 %), vilket förklarar de svaga
t-värdena i D.

## F. Mekanism — avoidance eller selection (licensierad av C)

Referens M = medelavkastning för de 24 behållna namnen.
`B − A = (M − A) + (B − M)` = avoidance + selection.

| Horisont | 2020-2026 avoidance (t R6) | selection (t R6) | 2014-2019 avoidance (t R6) | selection (t R6) |
|---|---:|---:|---:|---:|
| 4 v | +0,24 % (+0,16) | **−1,83 % (−1,99)** | +0,14 % (+0,12) | −0,71 % (−0,88) |
| 8 v | +4,39 % (+1,72) | −3,30 % (−1,78) | +2,47 % (+1,48) | −0,90 % (−0,55) |
| 12 v | +4,15 % (+0,68) | −2,75 % (−1,03) | +2,85 % (+1,21) | −0,48 % (−0,20) |
| 24 v | +10,01 % (+1,28) | −5,29 % (−1,12) | +8,20 % (+1,52) | −2,57 % (−0,46) |

**Effekten är helt och hållet AVOIDANCE.** Avoidance är positiv i alla åtta
celler; selection är **negativ i alla åtta**, och signifikant negativ vid 4 v i
det sena fönstret.

Mekanismen är alltså: *högvolatila namn i topp-30 är sämre än de man behåller* —
inte *djupare rankade namn är bättre*. Ersättarna är faktiskt sämre än
genomsnittet av de behållna.

Detta är exakt samma attributionsmönster som G42 visade, och det förklarar
placeboresultatet: vinsten mot slumpen kommer från **vilka man behåller**, inte
från vilka man tar in.

## G. Slutklassificering

Kedjan, led för led:

| Led | Utfall |
|---|---|
| **1. Replikerad inkrementell prediction skill** | **✓** G97: t −4,05 / −2,34 vid h=1, samma tecken i 8/8 celler |
| **2. Decision skill** | **SVAG** — samma riktning i båda fönstren men ingen signifikans, och h=1 är negativ i båda |
| **3. Matched-random selection skill** | **✓** p 0,003 och 0,019; marginal +4,77 / +3,23 pp |
| **4. Portfolio value** | **RIKTNING ✓, STORLEK EJ FASTSTÄLLD** — +1,61 / +2,47 pp men båda KI täcker noll |

Samtliga fem förregistrerade kriterier är formellt uppfyllda:
prediction skill replikerar, portfolio value är positiv i båda, placebot klaras i
båda, decision skill har samma riktning i båda, och effekten drivs inte av
enstaka namn eller paneler.

# **REPLICATED H0 IMPROVEMENT CANDIDATE**

**Inte FROZEN. Inte CHAMPION. H0 är oförändrad och forward startar 2026-09-04.**

## Vad som återstår att veta innan kandidaten kan tas på allvar

1. **Led 2 är svagt.** Beslutskanalen är inte statistiskt etablerad, och dess
   renaste mätning går åt fel håll. En kandidat vars mekanism inte går att visa
   på den icke-överlappande horisonten är inte klar.
2. **Båda portfölj-KI täcker noll.** +1,61 och +2,47 pp är punktskattningar.
3. **Är högvol i topp-30 en proxy för något annat?** Likviditet, storlek,
   segment eller lönsamhet — alla mätta i tidigare batcher — kan samvariera med
   volatilitet. Det är inte kontrollerat.
4. **Drawdown blir sämre** i båda fönstren. Regeln köper avkastning, inte risk.

`#96` idiosynkratisk volatilitet och `#98` low-beta förblir separata live frågor
och kördes inte. De får **inte** användas som räddningsförsök eller förstärkning.

Ingen ytterligare G97-variant licensieras: ingen annan kvantil, ingen voltröskel,
ingen viktvariant, ingen parameterrobusthet kring sex.

---

# G97-P — MECHANISM / CONFOUNDER FALSIFICATION AUDIT, 2026-08-17

Syftet var att döda G97-P, inte förbättra den. Ingen ny regel, ingen optimering.
**G97-P:s portföljresultat används inte som bevis för mekanismen.**

Artefakt: `research_k/g97p_confounder_audit_results.json`.

## A. PIT-täckning bland topp-30-observationer

| Variabel | 2020-2026 | 2014-2019 |
|---|---:|---:|
| vol_52w | 100 % | 100 % |
| beta_52w | 100 % | 100 % |
| idio_vol_52w | 100 % | 100 % |
| size (börsvärde) | hög | **34,9 %** |
| lönsamhet (rörelsemarginal) | hög | **36,3 %** |
| likviditet | provisorisk proxy | **0 %** |
| **sektor** | **saknas** | **saknas** |

Tre begränsningar måste stå med resultatet:

* `illiquidity_amihud_13w` och `turnover_13w_msek` är **uteslutna ur
  featureregistret** ("kräver QA-godkänd faktisk ojusterad handelsvolym"). Den
  likviditetsproxy jag använt — median daglig omsatt krona över 13 veckor — är
  **inte QA-godkänd** och finns bara för 2020-2026.
* Ingen PIT-indexserie finns för 2014-2019. Marknadsproxyn för beta och
  idiosynkratisk vol är den **likaviktade universumavkastningen**.
* **Sektor kontrollerades aldrig.** K1 fann ingen PIT-försvarbar historisk
  sektorstatus. Det är en öppen, oprövad alternativförklaring.

## B. Vad de sex exkluderade faktiskt är (ex ante, 2014-2019)

| Variabel | high-vol (6) | övriga (24) | diff | t |
|---|---:|---:|---:|---:|
| **H0-rank** | **10,63** | **16,72** | **−6,09** | **−14,10** |
| H0-score | 0,9568 | 0,9300 | +0,0268 | +13,81 |
| vol_52w | 0,6013 | 0,0509 | +0,5503 | +2,27 |
| beta_52w | 2,3533 | 1,1340 | +1,2193 | +2,56 |
| idio_vol_52w | 0,5970 | 0,0469 | +0,5501 | +2,27 |
| size (log) | 7,14 | 8,47 | −1,33 | −11,17 |
| rörelsemarginal | −2 099,8 | −72,9 | −2 026,9 | −4,84 |

**G97-P kastar systematiskt ut de HÖGST rankade namnen** — rank 10,6 mot 16,7,
t −14,10. De är också de minsta, de minst lönsamma och de med högst beta.

Det öppnar en alternativförklaring som **inte** prövats här: begrepp #44
kortsiktig reversal visade att band 1-5 har sämst framåtavkastning i båda
fönstren. Om G97-P:s mål är koncentrerade till rank 1-10 kan regeln delvis vara
en omskrivning av den redan kända reversalen vid rankningens topp. Att
residual-IC kontrollerar för rank talar mot det, men frågan är inte avgjord.

## C. Residual-IC för vol_52w efter successiv confounderkontroll

| Kontroll | 2020-2026 4v (t) | 12v (t NW) | 2014-2019 4v (t) | 12v (t NW) |
|---|---:|---:|---:|---:|
| A H0-rank | −0,1067 (−4,05) | −0,1302 (−3,37) | −0,0571 (−2,34) | −0,1052 (−3,83) |
| B + size | −0,0872 (−3,04) | −0,1246 (−2,93) | −0,0918 (−2,76) | −0,1722 (−3,97) |
| C + likviditet | −0,0880 (−2,99) | −0,1154 (−2,92) | — (data saknas) | — |
| E + beta | −0,0799 (−2,88) | −0,0946 (−2,48) | −0,0581 (−2,36) | −0,1115 (−4,03) |
| F + lönsamhet | −0,0759 (−2,75) | −0,1032 (−2,52) | −0,0698 (−2,09) | −0,1266 (−3,32) |
| **G rank+beta+size** | **−0,0714 (−2,47)** | −0,1088 (−2,68) | **−0,0734 (−2,19)** | −0,1439 (−3,04) |

**vol_52w behåller negativ, signifikant residual-IC på den icke-överlappande
horisonten i BÅDA fönstren efter samtliga tillgängliga confounderkontroller.**
Effekten är inte size, inte likviditet, inte beta och inte lönsamhet.

## D. Matchad high-vol-falsifiering

Varje high-vol-namn paras med det topp-30-namn som har närmast H0-rank men lägre
vol. Rank är den enda variabel med 100 % täckning i båda fönstren; att matcha på
size, lönsamhet eller likviditet vore underdimensionerat (35 %, 36 %, 0 %).

| Fönster / horisont | n par | lågvol − högvol | median | hit | t (Regel 6) | bootstrap-KI | rankbalans |
|---|---:|---:|---:|---:|---:|---|---:|
| 2020-2026 4v | 396 | **+3,01 %** | +3,92 % | 58,8 % | **+2,43** | **[+0,68 %, +5,40 %]** | +0,0 |
| 2020-2026 12v | 384 | +6,70 % | +7,83 % | 60,2 % | +1,58 | [+1,44 %, +11,14 %] | +0,0 |
| **2014-2019 4v** | 474 | **+0,93 %** | +0,81 % | 52,7 % | **+1,10** | **[−0,72 %, +2,55 %]** | +0,4 |
| 2014-2019 12v | 462 | +3,96 % | +5,55 % | 58,0 % | +1,60 | [+1,30 %, +6,71 %] | +0,5 |

Rankbalansen är utmärkt (skillnad 0,0–0,5 platser). Riktningen är densamma i
alla fyra celler. **Men på den rena horisonten i det tidiga fönstret täcker
konfidensintervallet noll.**

## E. Beta och idiosynkratisk volatilitet — vad mäter G97 egentligen?

| Test (h=1) | 2020-2026 residual-IC (t) | 2014-2019 residual-IC (t) |
|---|---:|---:|
| vol \| rank | −0,1067 (−4,05) | −0,0571 (−2,34) |
| **vol \| rank + beta** | **−0,0799 (−2,88)** | **−0,0581 (−2,36)** |
| **vol \| rank + idio** | −0,0688 (−2,68) | **−0,0160 (−0,70)** |
| idio \| rank | −0,0891 (−3,34) | −0,0558 (−2,29) |
| **idio \| rank + vol** | **+0,0196 (+0,71)** | **−0,0060 (−0,25)** |
| beta \| rank | −0,0783 (−2,82) | −0,0317 (−1,42) |
| **beta \| rank + vol** | **−0,0486 (−1,72)** | **−0,0265 (−1,13)** |

Korrelationer: **vol~idio +0,99 (sent) och +1,00 (tidigt)**; vol~beta +0,55 / +0,95.

Tre svar:

1. **Är G97 en beta-effekt? NEJ.** Beta försvinner efter kontroll för vol i båda
   fönstren (t −1,72 och −1,13). Vol överlever kontroll för beta i båda.
2. **Är G97 en idiosynkratisk-vol-effekt?** Frågan går **inte att avgöra**.
   Korrelationen är +0,99 till +1,00 — det är samma storhet mätt två gånger. I
   det sena fönstret överlever total vol kontroll för idio (t −2,68) och idio
   överlever inte vol (+0,71). I det tidiga fönstret **överlever ingen av dem
   den andra** (−0,70 och −0,25).
3. **Har total vol_52w egen information efter dessa kontroller?** Mot beta: ja,
   i båda. Mot idio-vol: **replikerar inte**.

## F. Avoidance efter stratifiering — mönstret vänder

| Fönster / horisont | high-vol i rank 16-30 | high-vol i topp-15 |
|---|---:|---:|
| 2020-2026 4v | **+4,56 % (t +3,38)** | +0,35 % (t +0,26) |
| 2020-2026 12v | +9,25 % (t +2,09) | +3,00 % (t +0,59) |
| **2014-2019 4v** | **−0,58 % (t −0,42)** | **+1,77 % (t +2,20)** |
| 2014-2019 12v | +3,05 % (t +0,73) | +3,37 % (t +1,55) |

**Var i topp-30 avoidance-värdet sitter vänder mellan fönstren.** I det sena
fönstret kommer det helt från nedre halvan; i det tidiga från övre halvan, och
nedre halvan är där negativ. Mekanismens *lokus* replikerar alltså inte, även om
dess *tecken* gör det.

## G. Alternativförklaringar — vad faller och vad står kvar

| Alternativ förklaring | Utfall |
|---|---|
| Size / börsvärde | **FALLER** — vol överlever (t −3,04 / −2,76) |
| Likviditet | **FALLER** i det sena fönstret (t −2,99); ej testbar i det tidiga |
| Beta / marknadsexponering | **FALLER** — beta överlever inte kontroll för vol i något fönster |
| Lönsamhet / kvalitet | **FALLER** — vol överlever (t −2,75 / −2,09) |
| Parsimonisk kombination | **FALLER** — vol överlever (t −2,47 / −2,19) |
| **Idiosynkratisk volatilitet** | **STÅR KVAR — ej separerbar, r = +0,99/+1,00** |
| **Sektor / bransch** | **STÅR KVAR — aldrig kontrollerad, PIT-data saknas** |
| **Reversal vid rankningens topp (#44)** | **STÅR KVAR** — de exkluderade är rank 10,6 mot 16,7 (t −14,10); ej prövat |

## H. Slutklassificering

Kedjan, med varje led hållet isär:

| Led | Utfall |
|---|---|
| prediction skill | ✓ |
| incremental prediction skill | ✓ båda fönstren, h=1 |
| **mechanism** | **överlever alla mätbara confounders, men är INTE IDENTIFIERAD** |
| decision skill | svag (från G97-P: ingen signifikans, h=1 negativ) |
| matched-random selection skill | ✓ p 0,003 / 0,019 |
| portfolio value | riktning ✓, storlek ej fastställd |

Ingen av de tre förregistrerade etiketterna passar rent, och jag tvingar inte in
resultatet i en:

* **Inte** *LIKELY PROXY / MECHANISM NOT REPLICATED* — vol behåller riktning och
  signifikans i båda fönstren efter size, likviditet, beta och lönsamhet.
* **Inte** *PROXY FOR [MECHANISM]* — ingen enskild variabel förklarar effekten.
  Idio-vol *kan* inte skiljas från vol (r ≈ 1,00), men det är kollinearitet inom
  samma konstrukt, inte en alternativ mekanism.
* **Inte fullt** *MECHANISM ROBUST TO OBSERVED CONFOUNDERS* — det matchade testet
  täcker noll på den rena horisonten i det tidiga fönstret, och avoidance-lokuset
  vänder mellan fönstren.

# **G97-P: MECHANISM SURVIVES OBSERVED CONFOUNDERS BUT IS NOT IDENTIFIED**

Vad det konkret betyder: *hög volatilitet* i H0:s topp-30 bär negativ information
som inte är storlek, likviditet, beta eller lönsamhet. Men om det är **total**
eller **idiosynkratisk** volatilitet går inte att avgöra med denna data, sektor är
aldrig kontrollerad, och regeln träffar systematiskt rankningens topp — där en
redan känd reversaleffekt sitter.

**Ingen freeze. Ingen champion. H0 oförändrad. Forward startar 2026-09-04.**

Ingen ny körning licensieras: ingen alternativ kvantil, ingen voltröskel, ingen
idio-vol- eller betastrategi, inget sektorfilter, ingen kombinationsscore.

---

# BATCH 6 — BLOCKERAD PÅ INDATA. Städning av ledgern utförd.

Datum: 2026-08-17. **Masterlistans poster 101–120 finns inte i mitt underlag.**

Posterna 1–100 har uppgetts ordagrant, batch för batch. Listan finns fortfarande
inte i repot. Att gissa fram 101–120 skulle nyckla ledgern mot fel numrering och
därmed förstöra dess enda funktion — att garantera att samma fenomen aldrig
testas två gånger under olika namn.

**Detta är andra gången indata blockerar en batch** (se avstämningen tidigare
samma dag). Rekommendation kvarstår: lägg listan i
`docs/QUANT_TERM_MASTERLIST.md` så att den fryses tillsammans med ledgern.

## Regel 5-skanning

Noll nya artefakter i `research_k/` efter G97-P-auditen. Inget parallellt spår
har tillkommit.

## Ledgerintegritet — verifierad

| Kontroll | Utfall |
|---|---|
| Begrepp i ledgern | 100, spann 1–100 |
| Dubblettnummer | inga |
| Saknade nummer | inga |
| Körda hypoteser | **14** |
| Metodlärdomar | 18 |
| Permanenta regler | 2 (Regel 5 skanning, Regel 6 överlappskorrigering) |

Statusfördelning över 100 begrepp:

| Status | Antal |
|---|---:|
| ALREADY_TESTED | 48 |
| DUPLIKAT | 24 |
| PARTIALLY_TESTED | 17 |
| NOT_APPLICABLE | 6 |
| NOT_TESTED | 5 |

**Nästan hälften är avgjorda och en fjärdedel är dubbletter.** Endast fem av
hundra står som oprövade, och samtliga fem bedömdes inte förtjäna en körning.

## Fyra stale poster i hypoteskön — rättade

Granskningen hittade fyra poster som låg kvar i `hypoteser_ej_korda` men som
inte var aktiva kandidater:

| Post | Rättelse |
|---|---|
| **G40** höger-svansberoende | **Var i praktiken besvarad av G55** — samma körning, samma skript. Leave-top3 föll 4,56 / 3,57 pp mot gränsen 8 pp. Flyttad till körda med anmärkning om förbiseendet. |
| **G1_G2** hysteres och band | Formellt **EJ LICENSIERAD** sedan G13+G17 gav NO PREMATURE-EXIT PROBLEM. Familj 1–7 är stängd. Markerad `i_aktiv_ko: false`. |
| **G6** takt för H0 | **EJ LICENSIERAD** av G13+G17-vägen. Kräver egen motivering som parameterverifiering, inte som åtgärd mot för tidig utgång. Markerad. |
| **G26** horisontmatchning | **NEDPRIORITERAD** — bekräftande, inte utforskande. `research_aj` visade redan att horisontjustering kollapsar alfan från 5,75 % till 0,05 %. Markerad. |

**Aktiv kö efter städningen: TOM.** Det är det korrekta tillståndet — Batch 1–5
stängde varje spår, och G97-P är den enda kandidaten, med mekanismen ej
identifierad och ingen ny körning licensierad.

## Läget inför Batch 6

| | |
|---|---|
| Genomgångna begrepp | **100 av 326** |
| Öppna kandidater | 1 — G97-P, ej fryst, mekanism ej identifierad |
| Aktiv testkö | tom |
| G97:s tre öppna alternativförklaringar | idiosynkratisk volatilitet (ej separerbar, r ≈ 1,00), sektor (PIT-data saknas), reversal vid rankningens topp (#44) |

När 101–120 uppges klassificeras de mot detta läge. Skulle något av dem
oberoende motsvara någon av de tre öppna G97-förklaringarna markeras det
**POTENTIAL INDEPENDENT EXPLANATION OF G97** och får påverka prioriteringen —
men inte generera en G97-variant.

---

# BATCH 6 — begrepp 101–120. Read-only gap audit.

Numreringen är nu fryst i `docs/QUANT_TERM_MASTERLIST.md`, som är auktoritativ
källa. Poster 1–100 oförändrade. Regel 5: noll nya artefakter.

Denna batch är till stor del **metodologisk och modell-livscykelrelaterad**, inte
signalrelaterad. Flera poster är ramverk programmet redan tillämpar, inte
hypoteser som kan prövas.

## Mekanismfamiljer (dedupliceringsnycklar)

| Familj | Poster | Karaktär |
|---|---|---|
| **M-R** regim och gating | 101, 110 | mekanism |
| **M-I** interaktion | 102, 103 | mekanism |
| **M-D** evidensnivåer | 104, 105 | **ramverk, ej hypotes** |
| **M-E** ensemble och oenighet | 106, 107 | mekanism |
| **M-M** metamodell | 108, 109 | mekanism |
| **M-G** styrning | 111, 112 | **infrastruktur, redan implementerad** |
| **M-Dr** drift | 113, 114, 115 | mekanism |
| **E** vinster och estimat | 116–120 | mekanism |

## Ledger — 101–120

| # | Term | Relation till locked H0 | Status | Evidens | Modell | Prio |
|---:|---|---|---|---|---|---|
| 101 | Regime dependence | Saknas som villkor; men **programmets mest genomgripande observerade mönster** | **ALREADY TESTED, otillräckligt** | K5: **0/6 stabila samband**, VIX-stress n=1, hög vol n=3; `research_n` N3 regimgrind 5,77 % mot 7,61 %; auditens egen korpus: **33 % av 106 varianter positiva tidigt och negativa sent**, median Δ −1,03 % sent mot −0,29 % tidigt | K5 på fryst H0 (20 IC-datum), research_n H0-variant, tvåfönsterkorpusen | **HIGH** |
| 102 | Feature interaction | H0 har två inputs, additivt 50/50 | PARTIALLY TESTED | `skarpare_ranking` C samstämmighet topp-60/topp-40: **+0,03/−0,85 och +1,08/−0,90** — faller; ET-familjen | STACK_H; ET på H0 (exposed data) | MEDIUM |
| 103 | Non-linear interaction | Saknas | PARTIALLY TESTED | `h0_extratrees_full_decision_layer_audit`: **PROMISING-BUT-UNPROVEN**; `h0_extratrees_selection_skill_audit`: **SELECTION SKILL PROMISING-BUT-UNSTABLE**, med dokumenterad begränsning: källan bevarar *aggregerade* IN/OUT-medelvärden, inte observationer per aktie och ombalansering | H0 + ExtraTrees, parallellt spår, `EXPOSED_DATA_RESEARCH` | MEDIUM |
| 104 | Prediction skill vs decision skill | **Är auditens ramverk** | **NOT APPLICABLE som test — ALREADY ANSWERED som fynd** | H1: Top-30 IC +0,0348/+0,0528 men CAGR −5,48 pp; G97 mot G83 i samma körning; G97-P: placebo ✓ men decision skill svag och h=1 negativ | locked H0 | — |
| 105 | Decision skill vs portfolio value | **Är auditens ramverk** | **NOT APPLICABLE som test — ALREADY ANSWERED** | samma som #104 | locked H0 | — |
| 106 | Model disagreement | Saknas | ALREADY TESTED | `dispersion_och_ensemble` del B: blandningar av de sex frysta, 1 av 3 positiv i båda; `h0_validator_model_race_1419`; `h0_lgbm_consensus_exit` | STACK_H/ERC; H0 för konsensus-exiten | LOW |
| 107 | Ensemble diversity | Saknas | **DUPLIKAT av #106** | — | — | — |
| 108 | Second-stage model / meta-model | Saknas | PARTIALLY TESTED | `h0_core_meta_exit`: prediktionskorrelation **0,1366 i utveckling → 0,0517 i oberoende fönster**; `h0_extratrees_*`: H0 topp-30 → ET → topp-20 | H0, parallellt spår, `diagnostic_only` | MEDIUM |
| 109 | Meta-labeling | Saknas | **DUPLIKAT av #108** — meta-labeling är en second-stage-modell på beslutet | — | — | — |
| 110 | Conditional model / gating | Saknas | **DUPLIKAT av #101** | `h0_extratrees_conditional_regime_audit` (förregistrerad, tidiga fönstret, ex-ante-terciler LOW/MID/HIGH) | H0 + ET, exposed data | — |
| 111 | Champion–challenger framework | **Redan implementerat** | **NOT APPLICABLE** | `canonical_final_model_registry`: ACTIVE_FROZEN_FORWARD / HISTORICAL_REFERENCE_ONLY / observation-only; SPARH förseglat forwardprotokoll | — | — |
| 112 | Shadow model / shadow portfolio | **Redan implementerat** | **NOT APPLICABLE** | SHADOW_ERC_X2, SHADOW_FUNDAMENTAL_RISK_OVERLAY, SHADOW_PRUNED_STACK_D, SHADOW_INTEGRATED_STACK_H, OBS_C_PROFIT_GATE_FCF | — | — |
| 113 | Model decay / concept drift | Relevant | PARTIALLY TESTED | `research_aj_signal_decay` (ett fönster, H0-variant); `h0_exit_model_time_split`; **`h0_core_meta_exit` 0,1366 → 0,0517 ÄR uppmätt concept drift**; motvikt: H1419-replikeringen +12,15 mot +12,73 pp visar att kärnsignalen **inte** förfaller | H0-variant, H0 parallellspår, locked H0 för replikeringen | LOW |
| 114 | Feature drift | H0 har exakt **två** inputs, båda percentilrankade | **DUPLIKAT av #22** rank persistence | Legacy RISK-5 mätte featuredrift per fold (`resid_mom` 5× mest instabil) — men på LambdaRank, ej H0. För H0 är frågan rankens autokorrelation: **0,6215** | legacy LambdaRank; #22 på H0:s rankning | — |
| 115 | Prediction drift | **Strukturellt omöjlig** | **NOT APPLICABLE** | H0:s output är percentilrank, som per konstruktion är likformigt fördelad varje panel. Det finns ingen prediktionsfördelning att drifta. Gäller ET/LGBM-lagret, inte locked H0 | — | — |
| 116 | Earnings momentum | Saknas | **ALREADY TESTED** | K3: **samtliga fem** fundamental-change-mått **INGET STÖD**. Revenue growth YoY Δ mean IC −0,0299; rörelsemarginalexpansion −0,0250; EBITDA-marginal −0,0229; **FCF-marginal −0,0837** | matched H0 + fast 50/50-blend | LOW |
| 117 | Earnings revisions | Saknas | **DATA_BLOCKED** | Ingen analytikerestimatdata i det validerade lagret | — | — |
| 118 | Analyst revision momentum | Saknas | **DUPLIKAT av #117, DATA_BLOCKED** | — | — | — |
| 119 | PEAD | Saknas | PARTIALLY TESTED, **ett fönster** | `pead_eget_spar.py` — MFN börjar 2020, tvåfönsterkriteriet **kan inte** uppfyllas före 2032; SPARJK: report/PEAD **SVAGT STÖD**, insider INGET STÖD | STACK_H, 2020-2026 | LOW |
| 120 | Earnings surprise | Saknas | PARTIALLY TESTED via proxy; estimatversionen DATA_BLOCKED | `pead_eget_spar` använder initial kursreaktion från sista stängning före `market_known_time` till första efter, som surprise-proxy. Den estimatbaserade definitionen kräver analytikerdata som saknas | STACK_H, ett fönster | LOW |

## A. ALREADY ANSWERED (4)

**#101** regimberoende — men *otillräckligt*, se D. **#106** model disagreement.
**#116** earnings momentum — K3, fem mått, samtliga INGET STÖD.
**#104/#105** är besvarade som *fynd* men är inte testbara mekanismer.

## B. DUBBLETTER OCH EJ TILLÄMPLIGA (8)

`#107 ≡ #106` · `#109 ≡ #108` · `#110 ≡ #101` · `#114 ≡ #22` · `#118 ≡ #117`

**#104, #105** — auditens eget ramverk, inte hypoteser.
**#111, #112** — redan implementerad infrastruktur. Programmet *har* ett
champion–challenger-register och fyra shadowmodeller. Ingenting att testa.
**#115 prediction drift är strukturellt omöjlig för locked H0**: percentilrank är
likformig varje panel per konstruktion. Det är den skarpaste NOT_APPLICABLE i
hela auditen.

## C. GENUINA LOCKED-H0-LUCKOR (2)

1. **#101/#110 regimberoende, prövat över BÅDA fönstren.** K5 föll på
   sampelstorlek — VIX-stress hade **ett** datum, hög volatilitet tre, negativ
   trend fyra. Det tidiga fönstret finns nu och **fördubblar ungefär
   panelantalet** (79 mot 66). Samtidigt är regimberoende programmets mest
   genomgripande observerade mönster: 33 % av 106 varianter byter tecken mellan
   fönstren.
2. **#103 icke-linjär interaktion.** ET-evidensen är `EXPOSED_DATA_RESEARCH` med
   aggregerad källdata och klassificeringen PROMISING-BUT-UNSTABLE. En ren
   prövning saknas — men se avsnitt I.

## D. DATA-BLOCKED (2)

**#117/#118 earnings revisions och analyst revision momentum** — ingen
analytikerestimatdata finns. **#119/#120 PEAD och earnings surprise** är inte
data-blockerade men **fönster-blockerade**: MFN börjar 2020 och
tvåfönsterkriteriet kan inte uppfyllas före 2032.

## E. POTENTIAL INDEPENDENT EXPLANATION OF G97

Två poster belyser G97:s kvarvarande problem oberoende av G97 självt:

* **#101/#110 regimberoende** — G97-P:s avoidance-lokus **vänder** mellan
  fönstren: rank 16-30 bär effekten i det sena fönstret (+4,56 %, t +3,38), övre
  halvan i det tidiga (+1,77 %, t +2,20) där nedre halvan är negativ. Det är
  regimberoende i regelns mekanism, inte i dess tecken.
  **POTENTIAL INDEPENDENT EXPLANATION OF G97.**
* **#102/#103 interaktion** — G97-P:s mål är koncentrerade till rankningens topp
  (rank 10,6 mot 16,7). En volatilitet × rank-interaktion är exakt den
  strukturen. **POTENTIAL INDEPENDENT EXPLANATION OF G97.**

Detta påverkar **prioriteringen** av #101. Det får **inte** generera en
vol×rank-score, en sektorjusterad G97 eller någon annan G97-variant.

## F. RANGORDNAD TESTKÖ — en post

| Ordning | Gap | Prio | Motiv |
|---:|---|---|---|
| **1** | **#101/#110 regimberoende över båda fönstren** | **HIGH** | Kan falsifiera en befintlig H0-egenskap, inte bara addera en regel. K5:s blockerare var sampelstorlek och den är delvis löst. Är dessutom programmets mest genomgripande mönster och en oberoende förklaring till G97:s instabilitet. |

## G. FÖRREGISTRERAD HYPOTES

### G101 — Regimberoende i locked H0, båda fönstren

**Motivering.** K5 klassade 0 av 6 samband som stabila, men fyra av sex föll på
otillräcklig data. Med båda fönstren finns ~145 paneler mot K5:s 20 IC-datum.

**Regimdefinitioner — endast befintliga PIT-features, inga nya:**
`market_regime_trend` = index[T]/SMA(index, 26 v) − 1 och `market_regime_vol` =
std(index veckoavkastningar, 13 v). Marknadsproxy: likaviktad
universumavkastning, samma som i confounderauditen, eftersom ingen PIT-indexserie
finns för 2014-2019.

**Hypotes.** Locked H0:s överavkastning mot sitt eget likaviktade universum
**skiljer sig inte** mellan förregistrerade regimterciler (LOW/MID/HIGH), mätt
poolat över båda fönstren, med tercilgränser satta **expanderande** och aldrig på
hela stickprovet.

**Falsifieras om** skillnaden mellan HIGH- och LOW-tercilen överstiger 5
procentenheter årlig överavkastning **med samma tecken i båda fönstren separat**.

**Detta är ett informationstest om H0 självt, inte en gate.** Ingen
exponeringsregel, ingen kassaregel och ingen challenger får skapas ur utfallet.
Skulle hypotesen falsifieras är nästa steg att *formulera* en förregistrerad
gate-prövning, inte att köra en.

**Ingen matched-random placebo krävs** — testet ändrar inga namn.

## I. NOT TESTED som ändå INTE förtjänar körning

* **#103 icke-linjär interaktion.** Formellt oprövat rent, men: `skarpare_ranking`
  C prövade samstämmighetskravet (båda horisonterna inom topp-N) och det föll i
  båda fönstren. ET-familjen finns redan och står på PROMISING-BUT-UNSTABLE. En
  ny interaktionsmodell på två percentilrankade inputs har låg mekanistisk
  motivering, och den enda intressanta interaktionen — vol × rank — är förbjuden
  som G97-variant. **Köas inte.**
* **#108/#109 metamodell.** Parallellspårets egen mätning visar
  prediktionskorrelation 0,1366 → **0,0517** mellan utvecklings- och oberoende
  fönster. Det är ett negativt resultat, inte en lucka.
* **#113 model decay.** Delvis besvarad, och H1419-replikeringen (+12,15 mot
  +12,73 pp) är starkt bevis att kärnsignalen inte förfaller. Marginellt värde.
* **#119/#120 PEAD och earnings surprise.** Fönster-blockerade till 2032. Ett
  test nu kan per konstruktion inte möta programmets eget kriterium.

## J. Räkning

| | |
|---|---:|
| Begrepp i Batch 6 | 20 |
| ALREADY_TESTED | 4 |
| PARTIALLY_TESTED | 7 |
| DUPLIKAT | 3 |
| NOT_APPLICABLE | 5 |
| DATA_BLOCKED | 1 |
| Genuina locked-H0-luckor | **2** |
| Förtjänar en körning | **1** |
| Mekanismfamiljer efter dedup | **6**, varav 2 är infrastruktur och inte hypoteser |
| **Totalt genomgångna av 326** | **120** |

---

# G101 KÖRD — 2026-08-17. **REPLICATED REGIME HETEROGENEITY — UNSTABLE**

Diagnostiskt. Ingen gate, ingen tradingregel, ingen G97-variant. H0 oförändrad.
Artefakter: `research_k/g101_regimberoende_results.json`,
`research_k/g101_paneldata.jsonl` (145 paneler).

## A. PIT och invarianter

| | 2020-2026 | 2014-2019 |
|---|---|---|
| Locked H0 reproducerar | **JA** (7,20 %) | **JA** (31,56 %) |
| Likaviktat universum | 1,06 % | 17,84 % |
| Paneler | 66 | 79 |
| Regimvärden med värde | trend 66, vol 66 | trend 79, vol 79 |
| **Oklassificerade** (expanderande krav ≥12 föregående) | 12 | 12 |

Regimvariabler enligt featureregistret, oförändrade: `market_regime_trend` =
index/SMA(index, 26 v) − 1 och `market_regime_vol` = std(index veckoavkastningar,
13 v). Tercilgränser satta **expanderande** ur enbart föregående paneler; ingen
full-sample-kvantil.

**Indexproxyn är en dokumenterad approximation:** ingen PIT-indexserie finns i det
frysta lagret för 2014-2019, så indexet är den kumulativa likaviktade
universumavkastningen per ISO-vecka.

## B–C. Trendregim

### 2020-2026 (LOW 11 / MID 26 / HIGH 17)

| Tercil | n | ann. excess | hit | IR | H0 | universum |
|---|---:|---:|---:|---:|---:|---:|
| LOW | 11 | +4,03 % | 55 % | 0,57 | +38,43 % | +33,07 % |
| MID | 26 | −0,90 % | 46 % | −0,09 | −7,06 % | −6,21 % |
| HIGH | 17 | **+9,08 %** | 65 % | 0,74 | +21,02 % | +10,94 % |

**HIGH − LOW +5,05 %**, block-bootstrap KI **[−11,00 %, +16,63 %]**, 59 % positiva
dragningar. Leave-one-panel-out [−1,20 %, +11,19 %]. 5 %-trimmat +4,55 %.
**Ej monoton.**

### 2014-2019 (LOW 26 / MID 25 / HIGH 16)

| Tercil | n | ann. excess | hit | IR | H0 | universum |
|---|---:|---:|---:|---:|---:|---:|
| LOW | 26 | +10,46 % | 62 % | 1,30 | +32,80 % | +20,23 % |
| MID | 25 | +4,68 % | 60 % | 0,63 | +27,49 % | +21,79 % |
| HIGH | 16 | **+30,12 %** | **81 %** | **3,62** | +44,11 % | +10,75 % |

**HIGH − LOW +19,67 %**, block-bootstrap KI **[+10,05 %, +29,92 %]**, **100 %
positiva dragningar**. Leave-one-panel-out [+13,86 %, +22,85 %]. 5 %-trimmat
+16,19 %. **Ej monoton.**

## D. Volatilitetsregim

| | LOW | MID | HIGH | HIGH − LOW | KI | andel pos |
|---|---:|---:|---:|---:|---|---:|
| 2020-2026 | +2,20 % (28) | +10,20 % (15) | −3,46 % (11) | **−5,66 %** | [−18,22 %, +12,68 %] | 43 % |
| 2014-2019 | +11,64 % (26) | +10,66 % (16) | +14,84 % (25) | **+3,19 %** | [−21,19 %, +25,51 %] | 57 % |

**Tecknet vänder.** Ingen replikation.

## E. Tvåfönsterreplikation

| Regim | 2020-2026 | 2014-2019 | Poolat | Samma tecken | > 5 pp båda | Falsifierar? |
|---|---:|---:|---:|:-:|:-:|:-:|
| **trend** | +5,05 % | +19,67 % | +10,32 % | **JA** | **JA** | **JA** |
| vol | −5,66 % | +3,19 % | +2,26 % | NEJ | NEJ | nej |

Den förregistrerade nollhypotesen **falsifieras för trendregimen**: HIGH − LOW
överstiger 5 pp med samma tecken i båda fönstren separat.

## F. Robusthet — och varför utfallet klassas som instabilt

Tre skäl att inte kalla detta ett stabilt regimberoende:

1. **Konfidensintervallet i det sena fönstret täcker noll** ([−11,00 %,
   +16,63 %], 59 % positiva dragningar). Endast det tidiga fönstret har ett
   intervall som utesluter noll.
2. **Magnituden skiljer sig fyrfaldigt** — +5,05 % mot +19,67 %.
3. **Ingen monotonicitet i något fönster.** MID är *lägst* i båda: −0,90 % mot
   LOW +4,03 % respektive +4,68 % mot LOW +10,46 %. Strukturen är U-formad, inte
   en gradient. En "mer trend → mer alfa"-berättelse har alltså inget stöd i
   mellantercilen.

Robusthetsmåtten i övrigt är godtagbara: leave-one-panel-out håller tecknet i det
tidiga fönstret genomgående, 5 %-trimning ändrar utfallet marginellt (+16,19 %
respektive +4,55 %), och största enskilda panel bidrar +7,70 % respektive +8,19 %
av en total på tjugo- respektive femprocentsnivå.

## Den viktigaste tolkningsreservationen

**Regimvariabeln och utfallet delar samma underliggande serie.**
`market_regime_trend` byggs ur universumindexet, och överavkastningen mäts som H0
minus samma universum. En tvärsnittlig momentumstrategi går mekaniskt bättre när
marknaden nyligen trendat, eftersom trendpersistens och tvärsnittsmomentum delar
samma underliggande exponering.

Det är inte ett PIT-fel — regimen är känd vid beslutstidpunkten. Men det är ett
starkt skäl till att **A kan gälla utan att B gör det.** Att H0:s alfa är större i
trendande marknader betyder inte att man kan tjäna på att sätta på och av H0
efter regim; den slutsatsen kräver ett eget test som inte är kört.

## G. Deskriptiv G97-koppling

**CONSISTENT WITH G97 HETEROGENEITY.**

Motivet är specifikt: G97-P är en **volatilitets**regel, och det är just
**volatilitetsregimen** som inte replikerar här — tecknet vänder mellan fönstren
(−5,66 % mot +3,19 %). En volbaserad regel ärver den instabiliteten. Att G97-P:s
avoidance-lokus vänder mellan fönstren är därmed förenligt med att
volatilitetsregimstrukturen själv är instabil.

Detta är **deskriptivt och inte kausal evidens**, och det får inte generera någon
G97-variant, vol×regim-score eller gate.

## H. Slutklassificering

# **REPLICATED REGIME HETEROGENEITY — UNSTABLE**

Trendregimen falsierar nollhypotesen formellt — samma tecken, över 5 pp i båda
fönstren — men konfidensintervallet täcker noll i det sena fönstret, magnituden
skiljer fyrfaldigt, och strukturen är U-formad snarare än monoton.
Volatilitetsregimen replikerar inte alls.

**Ingen gate licensieras.** Testet prövade **A** (har H0 regimberoende alfa) och
gav ett instabilt ja. **B** (kan regimtiming förbättra H0) är **helt oprövat** och
får inte antas följa.

H0 är oförändrad. Ingen parameterändring. Inget fryst. G101 stängs.

---

# BATCH 7 — begrepp 121–140 (fundamenta och kvalitet). Read-only gap audit.

Numreringen utökad i `docs/QUANT_TERM_MASTERLIST.md` till 140 poster; 1–120
oförändrade. Regel 5: inga nya artefakter.

## Vad projektet faktiskt redan har testat på fundamenta

Detta måste stå först, eftersom det avgör nästan hela batchen.

**K3 — fundamental CHANGE, fem mått, samtliga INGET STÖD** (matched H0 + fast
50/50-blend):

| Mått | Δ mean IC | Δ median IC | Δ Top-30 IC |
|---|---:|---:|---:|
| Revenue growth YoY | −0,0299 | −0,0371 | −0,0654 |
| Operating-margin expansion YoY | −0,0250 | −0,0426 | −0,0018 |
| EBITDA-margin expansion YoY | −0,0229 | −0,0296 | −0,0078 |
| **FCF-margin expansion YoY** | **−0,0837** | −0,0968 | −0,0996 |
| Lägre share-count dilution YoY | −0,0026 | −0,0261 | −0,1124 |

**Reservation:** samtliga fem har **noll terminalinstrument**. Resultaten är
survivorship-begränsade.

**Övrig fundamentalevidens:**

| Spår | Fråga | Utfall | Modell |
|---|---|---|---|
| **K7** | kvalitet som riskoverlay (soliditet primär) | **INGET STÖD** | H0-familjen |
| **K8** | lönsamhetsgrind, EBIT > 0 | **SVAGT STÖD** — CAGR +0,10 pp, maxDD +2,09 pp, t_paired −0,096 | V_A, ett fönster |
| **K9** | accruals | **SVAGT STÖD** — Δmean IC52 **+0,0329**, ΔTop-30 IC **+0,0240**, positiv IC-andel 0,849 mot 0,792. Men block1 **+0,0842** mot block2 **−0,0165** | H0 + 50/50-blend, 53 paneldatum |
| **K2** | värdering inom momentum (EBIT/EV) | **SVAGT STÖD**, familjen öppen endast för forward-only observation | H0-familjen |
| **SPARE E1** | fundamenta som ML-features | **FÖRSÄMRAR TYDLIGT** — CatBoost Δmean IC −0,056 och leave-top-3 −11,1 pp; XGBoost Δmean IC −0,117, ΔTop-30 IC −0,189, leave-top-3 −13,4 pp | CatBoost/XGBoost |
| **Egna, 2026-08-16** | lönsamhet som grind/tilt/kvot mot STACK_H | **0 av 7** och **0 av 12** positiva i båda fönstren | STACK_H |

**PIT-täckning för samtliga KPI-baserade fundamentalfeatures: 2015–2026, men
endast 28 % av raderna ligger till och med 2019.** Det tidiga fönstret har
alltså cirka en tredjedels täckning. Det gäller `100_Tillvaxt_Totala_Tillgangar`,
`28_Bruttomarginal`, `36_ROC`, `37_ROIC` — alla verifierade nu.

## Ledger — 121–140

| # | Term | Nivå/förändring/acc. | Relation till locked H0 | Status | Evidens | Modell |
|---:|---|---|---|---|---|---|
| 121 | Quality momentum | nivå × momentum | Saknas | **ALREADY_TESTED** | SPARI Batch 1 #6 prövade PRIS-kvalitet (drawdown-resiliens, trendstyrka) = STÖD men ej champion → stängt som #66/#76. Fundamental läsning = #133, testad 0/7 och 0/12 | SPARI-champion; STACK_H |
| 122 | Fundamental momentum | förändring | Saknas | **ALREADY_TESTED** | **= K3 exakt**, fem mått, samtliga INGET STÖD | matched H0 + 50/50 |
| 123 | Revenue momentum | förändring | Saknas | **ALREADY_TESTED** | K3 revenue growth YoY, ΔIC −0,0299 | matched H0 |
| 124 | Margin momentum | förändring | Saknas | **ALREADY_TESTED** | K3 operating-margin −0,0250 och EBITDA-margin −0,0229 | matched H0 |
| 125 | Cash-flow momentum | förändring | Saknas | **ALREADY_TESTED** | K3 FCF-margin **−0,0837**, batchens sämsta | matched H0 |
| 126 | Profitability momentum | förändring | — | **DUPLIKAT av #124** — förändring i lönsamhet ÄR marginalförändring | — | — |
| 127 | Return-on-capital momentum | förändring | Saknas | NOT_TESTED | `36_ROC`, `37_ROIC` finns (28 % täckning t.o.m. 2019); K3 testade inte ROC/ROIC-förändring | — |
| 128 | Balance-sheet momentum | förändring | Saknas | NOT_TESTED som förändring | K7 testade soliditet som **nivå** → INGET STÖD | H0-familjen |
| 129 | **Asset growth / investment effect** | nivå av förändring | **Saknas helt** | **NOT_TESTED** | `100_Tillvaxt_Totala_Tillgangar_r12` finns, 344 bolag. Närmaste prövade släkting är K3:s share-count dilution, ΔIC **−0,0026** — alltså neutral, inte negativ | — |
| 130 | Accrual anomaly | nivå | Saknas | **ALREADY_TESTED** | **K9 SVAGT STÖD** med positiva deltan men teckenbyte mellan tidsblock (+0,0842 / −0,0165) | H0 + 50/50-blend |
| 131 | Earnings quality | nivå | — | **DUPLIKAT av #130** — accruals är standardmåttet på vinstkvalitet | — | — |
| 132 | Gross profitability | nivå | Saknas | PARTIALLY_TESTED | `28_Bruttomarginal` finns; Novy-Marx-argumentet är att brutto slår rörelse. Rörelsemarginal och FCF-marginal är testade 0/7 och 0/12; brutto specifikt inte | STACK_H för släktingarna |
| 133 | Operating profitability | nivå | Saknas | **ALREADY_TESTED** | K8 SVAGT STÖD; egna tester 0/7 och 0/12; segmentdiagnostiken gav +16,0/+16,4 % kvintilspread (nivå 2–3) men noll portföljvärde | V_A, STACK_H, locked H0-segment |
| 134 | Quality-minus-junk / kvalitetsfaktor | nivå, komposit | Saknas | PARTIALLY_TESTED | **SPARE E1** är den närmaste kompositprövningen: fundamenta som featureblock försämrar allt (leave-top-3 −11,1 och −13,4 pp) | CatBoost/XGBoost |
| 135 | Financial distress | nivå, komposit | Saknas | **DATA_BLOCKED i praktiken** | Komponenter finns (soliditet, nettoskuld/EBITDA) men en distressmodell kräver flera samtidigt; 28 % täckning t.o.m. 2019 | — |
| 136 | Piotroski F-score | komposit av nivå + förändring | Saknas | **DATA_BLOCKED i praktiken** | Kräver nio signaler varav flera är YoY-förändringar. Med 28 % radtäckning i det tidiga fönstret och krav på **samtliga nio** blir effektiv täckning väsentligt lägre | — |
| 137 | Altman Z-score | komposit | Saknas | **DATA_BLOCKED i praktiken** | Fem kvoter inklusive marknadsvärde; samma täckningsproblem | — |
| 138 | Fundamental acceleration | acceleration | Saknas | NOT_TESTED | K3 prövade **första** differensen; acceleration är andra differensen och kräver tre år per bolag → täckningen kollapsar. G51 visade dessutom att acceleration i PRIS-poängen gav NO INCREMENTAL SIGNAL | — |
| 139 | Fundamental inflection / turnaround | acceleration | Saknas | NOT_TESTED i v2 | Legacy N3-59/N3-60 "kassaflödesinflektion och persistens" — men på **LambdaRank**, ej H0 | legacy LambdaRank |
| 140 | **Price–fundamental confirmation / divergence** | interaktion | **FINNS REDAN I H0-FAMILJEN** | **ALREADY_TESTED / IMPLEMENTERAD** | Det **är** FR-overlayen: `conf_fn` i `stack_h_motor` viktar ned obekräftade namn med 0,75, och `SHADOW_FUNDAMENTAL_RISK_OVERLAY` (13,20 %) är den frysta modellen. `research_ad_orthogonal_risk`: sannolikhet för >10 % förlust **0,093 bekräftade mot 0,195 obekräftade** (n=504/1476), p5 −0,134 mot −0,207 | STACK_H, FR-modellen |

### Dedupliceringsfamiljer

| Familj | Poster | Status |
|---|---|---|
| **F-CH** fundamental förändring | 122–128 | K3 täcker 122–126; 127/128 oprövade varianter med starkt negativ prior |
| **F-LEV** nivå och lönsamhet | 132, 133, 134 | grundligt testad, redundant |
| **F-ACC** accruals och vinstkvalitet | 130, 131 | K9 SVAGT STÖD med tidsblocksvändning |
| **F-DIST** distress och kompositer | 135, 136, 137 | täckningsblockerade |
| **F-ACC2** acceleration och inflektion | 138, 139 | oprövade, täckningen kollapsar |
| **F-CONF** bekräftelse | 140 | **redan implementerad i frysta modeller** |
| **F-INV** investering | 129 | **den enda genuina luckan** |

Dubbletter: `#126 ≡ #124` · `#131 ≡ #130`

## A. ALREADY ANSWERED (8)

**#121, #122, #123, #124, #125, #130, #133, #140.** Fem av dem är K3:s fem mått.
**#140 är särskilt värt att notera: den är inte en lucka utan en redan
implementerad mekanism** i STACK_H och `SHADOW_FUNDAMENTAL_RISK_OVERLAY`, och
bekräftelse förutsäger **risk** starkt (9,3 % mot 19,5 % sannolikhet för >10 %
förlust).

## B. DUBBLETTER / EJ TILLÄMPLIGA (2)

`#126 ≡ #124` profitability momentum är marginalförändring. `#131 ≡ #130`
earnings quality är accruals.

## C. PARTIALLY TESTED (2)

**#132** gross profitability — släktingarna testade, brutto specifikt inte.
**#134** QMJ — SPARE E1 är närmaste kompositprövning och den försämrar allt.

## D. DATA-BLOCKED (3)

**#135, #136, #137.** Inte för att data saknas i sig, utan för att **kompositerna
kräver flera samtidiga fält och det tidiga fönstret har 28 % radtäckning.** En
F-score som kräver nio signaler samtidigt får väsentligt lägre effektiv täckning
än 28 %. Detta ska **inte** repareras med imputering.

## E. GENUINA LOCKED-H0-LUCKOR (4, varav 1 licensieras)

1. **#129 asset growth / investment effect** — den enda som är både ekonomiskt
   ortogonal mot H0:s prissignal, oprövad, och har en existerande PIT-feature.
2. **#127 ROC/ROIC-förändring** — oprövad men samma familj som K3:s fem, alla
   negativa.
3. **#128 balansräkningsförändring** — oprövad som förändring; nivån föll i K7.
4. **#138/#139 acceleration och inflektion** — oprövade men täckningen kollapsar.

## F. POTENTIAL INDEPENDENT EXPLANATION OF G97

**#129 asset growth** markeras. G97-auditen visade att de sex high-vol-namnen är
de **minsta** och **minst lönsamma** i topp-30. Höga tillgångstillväxttal är en
karakteristik som plausibelt samvarierar med båda — tillväxtbolag som expanderar
balansräkningen. Lönsamhet kontrollerades redan och förklarade **inte**
vol-effekten; tillgångstillväxt är en **annan** kanal och är inte kontrollerad.

Det får påverka prioriteringen. Det får **inte** generera en G97-variant, en
asset-growth-justerad G97 eller en kombinationsscore.

## G. RANGORDNAD TESTKÖ — en post

| Ordning | Gap | Prio | Motiv |
|---:|---|---|---|
| **1** | **#129 asset growth / investment effect** | **MEDIUM-HIGH** | Ekonomiskt ortogonal mot både momentum och lönsamhet. Feature finns (344 bolag). Närmaste prövade släkting (share-count dilution) var **neutral, −0,0026**, inte negativ — till skillnad från K3:s övriga fyra. Dessutom en oberoende kandidatförklaring till G97. **Inte HIGH** enbart på grund av 28 % täckning i det tidiga fönstret. |

## H. FÖRREGISTRERAD HYPOTES

### G129 — Tillgångstillväxt som inkrementell information

**Definition.** `100_Tillvaxt_Totala_Tillgangar_r12`, PIT med senaste
`report_date` ≤ paneldatum − 5 dagar. Ingen alternativ definition, ingen
vinsorisering, ingen tröskel.

**Population.** Locked H0:s topp-30 vid beslutstidpunkten, begränsat till namn
med värde. **Täckningen redovisas per fönster och panel innan något delta
tolkas**; understiger den 20 av 30 namn i en panel utesluts panelen.

**Hypotes.** Bland namn med jämförbar aktuell H0-score/rank predicerar **högre**
tillgångstillväxt **lägre** framtida 4/8/12/24 v avkastning — alltså negativ
inkrementell IC — **med samma tecken i båda oberoende fönstren** efter kontroll
för aktuell H0-score/rank.

**Regel 6 gäller:** endast h=1 är icke-överlappande och utgör primärbeviset;
överlappskorrigerat t redovisas för h>1.

**Falsifieras om** tecknet skiljer sig mellan fönstren eller om h=1 inte är
signifikant i något av dem.

**Detta är ett informationstest, inte en portföljregel.** Skulle det passera
gäller **REQUIRES MATCHED-RANDOM PLACEBO IF SIGNAL TEST PASSES**, och nästa steg
formuleras då — det körs inte.

## I. Oprövade som ändå INTE förtjänar en körning

* **#127 ROC/ROIC-förändring.** Samma familj som K3:s fem mått, där **alla fem**
  gav negativa deltan på mean, median och Top-30 IC. ROC är marginal ×
  omsättningshastighet; den nya kanalen är omsättningshastighet, och
  `asset_turnover_ttm` finns men har ingen egen positiv evidens. Prior för svag.
* **#128 balansräkningsförändring.** Nivån (soliditet) föll i K7 med INGET STÖD.
  Förändringen är samma familj som K3.
* **#132 gross profitability.** Novy-Marx-distinktionen mot rörelsemarginal är
  reell men fin, och rörelse- och FCF-marginal är testade i sex olika
  konstruktioner utan portföljvärde. Att byta täljare räddar sannolikt inte
  familjen.
* **#134 QMJ.** SPARE E1 visade att fundamenta som featureblock **försämrar**
  leave-top-3 med 11–13 pp. En komposit är ett större featureblock, inte ett
  mindre.
* **#138/#139 acceleration och inflektion.** Andra differensen kräver tre års
  historik per bolag; med 28 % radtäckning i det tidiga fönstret blir det inte
  falsifierbart. G51 visade dessutom att acceleration i prispoängen gav NO
  INCREMENTAL SIGNAL.

## J. Ledgerintegritet och räknare

| | |
|---|---:|
| Begrepp i Batch 7 | 20 |
| ALREADY_TESTED | 8 |
| DUPLIKAT | 2 |
| PARTIALLY_TESTED | 2 |
| DATA_BLOCKED | 3 |
| NOT_TESTED | 5 |
| Genuina locked-H0-luckor | **4** |
| Förtjänar en körning | **1** |
| Mekanismfamiljer efter dedup | **7**, varav 1 redan implementerad |
| **Totalt genomgångna av 326** | **140** |

---

# G129 KÖRD — 2026-08-17. **NO INCREMENTAL SIGNAL.**

Artefakter: `research_k/g129_asset_growth_results.json`,
`research_k/g129_paneldata.jsonl` (4 350 observationer).
Locked H0 reproducerade exakt i båda fönstren (7,20 % / 31,56 %).

## A. Definition — låst före all resultatberäkning

| | |
|---|---|
| Källa | `validated/kpi_pit/100_Tillvaxt_Totala_Tillgangar_r12.json` |
| Konstruktion | Börsdatas egen R12-serie, levereras färdigberäknad; ingen konstruktion gjord här |
| Enhet | **procent** (median 7,50 = 7,5 % tillväxt) |
| PIT | senaste `report_date` ≤ paneldatum − 5 dagar |
| Valuta | fältet finns men tillväxt är en **enhetslös kvot**; ingen omräkning behövs, valutabuggen kan inte återuppstå |
| Negativa värden | tillåtna och behållna, **29 %** av raderna |
| Saknade `v` | **noll rader**; missingness uppstår enbart av att rapport saknas före paneldatum |
| Winsorisering | **INGEN finns, INGEN lades till** |

Fördelningen har extrem högersvans: min −94,9 %, p1 −46,7 %, median +7,5 %,
p99 +338 %, **max +31 408 %**. Rangbaserad inferens (Spearman på percentilrank)
är immun mot det; att införa vinsorisering hade varit ett nytt definitionsval.

**Två saker som sänker bevisvärdet och ska stå med:**

* **Asset growth finns inte i `feature_registry.json`.** Registret har
  `revenue_growth_yoy`, `eps_growth_yoy`, `shares_growth_yoy` och
  `asset_turnover_ttm` — men ingen asset growth. Detta är alltså PIT-korrekt
  **rådata, inte en QA-registrerad feature**.
* En alternativ definition kunde byggts ur `57_Totala_Tillgangar_r12` som
  nivå[t]/nivå[t−4 kvartal] − 1. Den **konstruerades inte**, eftersom två
  definitioner skulle inneburit ett val efter att utfallet setts.

## B. Coverage — och den är förödande i det tidiga fönstret

| | 2020-2026 | 2014-2019 |
|---|---:|---:|
| Paneler | 66 | 79 |
| Giltiga av 30, medel | 28,47 | **11,15** |
| Median / min / max | 29 / 25 / 30 | 17 / **0** / 25 |
| Andel paneler ≥ 20/30 | **100 %** | **41,8 %** |
| Andel observationer giltiga | 94,9 % | **37,2 %** |
| **Coverage första halvan** | 28,3 | **0,9** |
| Coverage andra halvan | 28,6 | 21,2 |

**Det tidiga fönstrets första hälft har i praktiken noll täckning** — 0,9 av 30
namn. Primäranalysen där vilar på 32 paneler av 79, alla från 2017 och senare.

## C. Coverage-selection audit

Namn **med** asset-growth-data jämfört med namn **utan**:

| Variabel | 2020-2026 MED / UTAN (t) | 2014-2019 MED / UTAN (t) |
|---|---|---|
| H0-rank | 15,37 / 16,80 (**−1,88**) | 15,82 / 14,47 (**+1,78**) |
| H0-score | 0,9443 / 0,9387 (**+1,98**) | 0,9340 / 0,9402 (**−1,91**) |
| vol_52w | 0,0726 / 0,0798 (−1,76) | 0,0568 / 0,0574 (−0,32) |
| framtida 4v | +1,17 % / +2,76 % (−0,79) | +1,89 % / +2,44 % (−0,76) |

**Missingness selekterar, och den selekterar i motsatt riktning i de två
fönstren.** I det sena fönstret har namn med data *bättre* rank och högre score;
i det tidiga *sämre* rank och lägre score, båda med t nära 2. Det är i sig ett
skäl att inte lita på ett positivt utfall om ett sådant hade uppstått.

## D. Primärt utfall, h=1 — **fel tecken i båda fönstren**

Förväntad riktning: hög tillgångstillväxt → **lägre** framtida avkastning, alltså
**negativ** residual-IC.

| Fönster | rank-IC | **residual-IC** | t | bootstrap-KI | Q1−Q5 | paneler |
|---|---:|---:|---:|---|---:|---:|
| 2020-2026 | +0,0371 | **+0,0206** | +0,83 | [−0,0282, +0,0699] | +0,44 % | 65 |
| 2014-2019 | +0,0263 | **+0,0330** | +0,76 | [−0,0498, +0,1138] | **−0,67 %** | 32 |

**Tecknet är positivt i båda fönstren — motsatt investment-effektens riktning.**
Ingetdera är signifikant, och båda konfidensintervall täcker noll. Q1−Q5 (låg
minus hög tillväxt) byter dessutom tecken mellan fönstren.

## E. Sekundära horisonter (endast diagnostiskt, Regel 6)

| Horisont | 2020-2026 residual-IC (t R6) | 2014-2019 residual-IC (t R6) |
|---|---:|---:|
| 8 v | +0,0074 (+0,25) | +0,0477 (+0,86) |
| 12 v | −0,0156 (−0,39) | +0,0353 (+0,65) |
| 24 v | −0,0342 (−0,53) | +0,0538 (+0,76) |

I det sena fönstret vänder tecknet till negativt vid 12 och 24 veckor; i det
tidiga förblir det positivt hela vägen. **Ingen horisont är signifikant efter
överlappskorrigering**, och en längre horisont får inte rädda ett misslyckat
h=1-test.

## F. Tvåfönsterreplikation mot de fyra kraven

| Krav | Utfall |
|---|---|
| 1. Förväntat tecken i båda fönstren på h=1 | **NEJ** — båda positiva, förväntat negativt |
| 2. Inget tydligt teckenbyte efter H0-kontroll | **NEJ** — sena fönstret vänder mellan 8 v och 12 v |
| 3. Ekonomiskt meningsfull låg mot hög tillväxt | **NEJ** — Q1−Q5 byter tecken (+0,44 % mot −0,67 %) |
| 4. Coverage inte huvudsakligen en missingness-effekt | **KAN INTE VERIFIERAS** — 0,9/30 i tidiga fönstrets första hälft, och selektionen vänder riktning |

## G. Robusthet — ej körd

Steg 8 var villkorat av att h=1-signalen passerade. Den gjorde inte det, så
leave-one-panel-out, trimning och coverage-threshold-sensitivitet **kördes
inte**. Att köra dem nu skulle vara att söka en tröskel där signalen fungerar.

## H. G97-diagnostik

Frågan: har G97-P:s sex high-vol-exkluderade namn högre asset growth än övriga?

| | 2020-2026 | 2014-2019 |
|---|---:|---:|
| Rå skillnad i asset growth | **+577,97 pp (t +3,38)** | **+28,56 pp (t +4,10)** |
| Efter kontroll för H0-rank (rangenheter) | **−1,37 (t −2,22)** | **+1,69 (t +3,14)** |

Rått har de high-vol-exkluderade **dramatiskt** högre tillgångstillväxt i båda
fönstren — det stämmer med bilden av små, olönsamma expansionsbolag. Men
+577,97 procentenheter är uppenbart drivet av extremsvansen (max +31 408 %) och
ska inte tas som ett medelvärde i vanlig mening.

**Efter kontroll för H0-rank — samma kontroll som G97:s residual-IC använde —
vänder riktningen mellan fönstren:** −1,37 rangenheter i det sena, +1,69 i det
tidiga, båda signifikanta men med motsatt tecken.

# **NOT CONSISTENT WITH G97 CONFOUNDING**

Tillgångstillväxt ger ingen stabil förklaring till volatilitetseffekten. Den är
en stark deskriptiv karakteristik hos high-vol-gruppen men försvinner som
förklaring så snart rank kontrolleras — och den vänder riktning mellan fönstren.
G97:s mekanism förblir oidentifierad, och asset growth kan inte läggas till
listan över falsifierade alternativ eftersom rankkontrollen ger motstridiga
svar.

## I. Evidenskedjans status

| Led | Utfall |
|---|---|
| PIT och definition | **OK**, men rådata utan QA-registrering |
| Coverage | **UNDERKÄND i det tidiga fönstret** (0,9/30 i första hälften) |
| Prediction skill | ingen |
| **Inkrementell prediction skill** | **NEJ — fel tecken i båda fönstren, inget signifikant** |
| Decision skill | ej prövad, ej licensierad |
| Portfolio value | ej prövad, ej licensierad |

## J. Slutklassificering

# **NO INCREMENTAL SIGNAL**

Testet misslyckas på sina egna villkor: tecknet är positivt i båda fönstren där
investment-effekten kräver negativt, inget t-värde når signifikans, och Q1−Q5
byter tecken. Coverage-problemet är en **andra** invändning som hade gjort ett
positivt utfall otillförlitligt — men det behövs inte för domen.

**Inget decision- eller portföljtest licensieras.** Steg 7 och 8 kördes inte.

**#129 stängs.** Därmed är **hela F-INV-familjen stängd**, och Batch 7:s samtliga
sju mekanismfamiljer är avgjorda eller blockerade. Aktiv kö: tom.

Investment-effekten är väldokumenterad i internationell litteratur. Att den inte
syns här är förenligt med det övriga fundamentalmaterialet: K3:s fem mått,
K7, SPARE E1 och mina egna lönsamhetstester pekar alla samma väg — **fundamenta
tillför inte inkrementell information till H0:s prissignal i detta universum.**

---

# BATCH 8 — begrepp 141–160 (storlek, likviditet, volym, kapacitet). Read-only.

Masterlistan utökad till 160; 1–140 oförändrade. Regel 5: inga nya artefakter.

## Den avgörande QA-statusen — verifierad, oförändrad

`docs/probes/feature_registry.json`, ordagrant:

| Feature | Status |
|---|---|
| `illiquidity_amihud_13w` | **UTESLUTEN** — *"kräver QA-godkänt faktiskt ojusterat handelspris"* |
| `turnover_13w_msek` | **UTESLUTEN** — samma formulering |
| `volume_trend_13w` | `mean(v,4v)/mean(v,föreg.9v)−1` — **ingen uteslutning** |

Blockeringen gäller **det ojusterade handelspriset**, inte volymen. Det delar
batchen exakt i två: allt som kräver omsatt **värde** är blockerat, medan rena
**volymkvoter** är tillgängliga.

### Governancefynd som måste redovisas

`tools/research_v_portfolio_risk_architecture.py` bygger sitt ADV-filter som
`turnover = close × volume` med `r.get("close", r["adj"])` och tröskeln
1 000 000 kr/dag. **Det är exakt den konstruktion featureregistret förklarar
utesluten i väntan på QA.** Kontrollarmen `B_H0_ADV1M` (8,89 % mot A:s 7,61 %)
vilar därmed på icke-QA-godkänd data. Talet får inte citeras som evidens för ett
likviditetsfilter.

## Tre frågor som hålls isär

**A prediktion** · **B portföljkonstruktion** · **C implementationsrealism**.
Evidens för C är inte en alfasignal för A; evidens för A är inte en tradingregel
för B.

## Ledger — 141–160

| # | Term | Fråga | Status | Evidens | Modell |
|---:|---|:-:|---|---|---|
| 141 | Size effect | A/B | **PARTIALLY_TESTED** | G97:s confounderaudit kontrollerade size (vol överlevde, t −3,04/−2,76) — men det testar size som **confounder**, inte som **inkrementell signal**. Segmentdiagnostiken gav storlekstercilernas kvintilspread: stora +1,8 %/+3,5 % per år mot hela universumets +6,5 %/+20,3 % | locked H0 (segment + G97-audit) |
| 142 | Small-cap effect | A | **DUPLIKAT av #141** | — | — |
| 143 | Micro-cap effect | A | **NOT_APPLICABLE** | Universumet är storleksfiltrerat; mikrobolag ingår inte i H0:s kandidatpopulation | — |
| 144 | Liquidity premium | A | **DUPLIKAT av #145** — samma storhet, omvänt teckenkonvention | — | — |
| 145 | Illiquidity premium | A | **DATA_BLOCKED** | kräver omsatt värde | — |
| 146 | Amihud illiquidity | A | **DATA_BLOCKED** | `illiquidity_amihud_13w` UTESLUTEN | — |
| 147 | Turnover / share turnover | A | **DATA_BLOCKED** | Kunde i princip byggas som volym/antal aktier utan pris, men det vore en **ny oregistrerad feature**. Att konstruera den är inte licensierat | — |
| 148 | Dollar-volume / traded-value | A | **DATA_BLOCKED** | `turnover_13w_msek` UTESLUTEN | — |
| 149 | **Trading-volume momentum** | A | **NOT_TESTED** | **= `volume_trend_13w` exakt.** Featuren finns, är **inte** utesluten, och ingår i C-panelen och `h0_core_meta_exit`s 33 features — men har **aldrig prövats som fristående inkrementell signal på locked H0** | featurepanelen |
| 150 | Volume-price confirmation | A | **NOT_TESTED** | Legacy `tune_attention_gap` var DATA SAKNAS i täckningsmatrisen. Interaktion mellan volym och pris, ej prövad | legacy |
| 151 | Abnormal volume | A | **DUPLIKAT av #149** — volym mot egen baslinje är samma konstruktion, annan parametrisering | — | — |
| 152 | Volume shock | A | **DUPLIKAT av #149/#151** | — | — |
| 153 | Liquidity shock | A | **DATA_BLOCKED** | kräver en likviditetsserie | — |
| 154 | Liquidity risk | A | **DATA_BLOCKED** | kräver en marknadslikviditetsfaktor | — |
| 155 | Market-impact proxy | C | **DATA_BLOCKED** | samma pris-QA som Amihud | — |
| 156 | Capacity constraint | C | **DATA_BLOCKED** för ett rigoröst svar | Deltagandegrad kräver omsatt värde. Se implementationsavsnittet | — |
| 157 | Crowding | A/C | **DATA_BLOCKED** | Kräver innehavs- eller flödesdata över förvaltare. FI:s blankningsregister var den närmaste positionsdatan och stängdes 2026-08-16 (INGET STÖD, 0,5 %-tröskeln för tunn) | FI-spåret |
| 158 | Breadth / participation | A | **PARTIALLY_TESTED — endast betydelse (1)** | K5 `market_breadth_6m` som **regim**: SVAGT/OSÄKERT, 12 mot 8 paneler. Betydelse (2) momentumbredd inom kandidatpopulationen och (3) deltagande i en enskild akties rörelse är **oprövade** | K5 på fryst H0 |
| 159 | ADV constraint / liquidity screen | B/C | **PARTIALLY_TESTED, ej QA-godkänd data** | `research_v` B_H0_ADV1M 8,89 % mot 7,61 % (+1,28 pp), ett fönster, byggd på `close × volume` som registret förklarat utesluten | H0-variant, ett fönster |
| 160 | Implementation shortfall | C | **PARTIALLY_TESTED** | SPARG kostnadsstress: 0/20/40/60/100 bp → 25,91/25,29/24,67/24,05/22,81 % CAGR. **Break-even ≈ 534 bp per ensidig omsättning.** Men det är en platt enhetskostnad — ingen impactmodell, ingen kapacitetsdimension | SPARG-champion, ett fönster |

### Dedupliceringsfamiljer

`SZ` storlek (141–143) · `LQ` likviditetsnivå (144–148, 153, 154) ·
`VO` volymdynamik (149–152) · `IMP` implementation och kapacitet (155, 156, 159, 160) ·
`CRW` positionering (157) · `BR` bredd (158)

Dubbletter: `#142 ≡ #141` · `#144 ≡ #145` · `#151 ≡ #149` · `#152 ≡ #149`

## A–D. Sammanfattning per klass

**Redan besvarade: 0.** Ingen post i batchen är fullt avgjord på locked H0.

**Dubbletter / ej tillämpliga: 5** (#142, #143, #144, #151, #152).

**Partially tested: 4** (#141, #158, #159, #160).

**DATA_BLOCKED: 9** — #145, #146, #147, #148, #153, #154, #155, #156, #157.
**Nästan halva batchen faller på en enda öppen QA-punkt.**

## E. Genuina locked-H0-luckor (3)

1. **#149/#151/#152 volymmomentum** — den enda featuren i hela likviditets- och
   volymfamiljen som finns, inte är utesluten, och aldrig prövats fristående.
2. **#141 size som inkrementell signal** — delvis täckt av segmentarbetet och
   G97:s confounderkontroll, men aldrig som ett rent inkrementellt IC-test.
   Täckningsbegränsad (28 % till och med 2019).
3. **#158 betydelse (2) och (3)** — momentumbredd inom kandidatpopulationen och
   deltagande i enskild akties rörelse. Men nya breddefinitioner ska inte
   uppfinnas för att fylla luckan.

## F. Implementation- och kapacitetsluckor — och den viktigaste åtgärden

Kostnads**nivån** är stresstestad: 0–100 bp ändrar CAGR med 3,1 pp och
break-even ligger på ~534 bp. Slutsatsen är inte känslig i det intervallet.

Men **tre dimensioner saknas helt**: marknadspåverkan som funktion av
orderstorlek, deltagandegrad mot ADV, och kapacitetstak i kronor. Alla tre
kräver omsatt värde, och omsatt värde kräver det QA-godkända ojusterade
handelspriset.

> **Den högst värderade åtgärden i hela Batch 8 är inte ett test. Det är att
> genomföra QA på det ojusterade handelspriset.** Den enskilda punkten
> blockerar nio av tjugo begrepp, hela kapacitetsfrågan, och gör dessutom
> `research_v`s befintliga ADV-resultat ociterbart.

Det är ett datauppdrag, inte en forskningshypotes, och det ska inte lösas med
en proxy.

## G. POTENTIAL INDEPENDENT EXPLANATION OF G97

**#149 volymmomentum** markeras. G97:s mekanism är oidentifierad, och
volatilitet och handelsintensitet är empiriskt nära besläktade utan att vara
samma sak. Volymmomentum är dessutom den enda kandidatförklaringen i denna batch
som faktiskt går att mäta med tillgänglig data.

**Sex förklaringar hålls isär och får inte slås ihop:** size · total volatilitet
· idiosynkratisk volatilitet · likviditet · handelsintensitet · marknadspåverkan
· reversal vid rankningens topp. Ingen kombinationsfeature, ingen
vol×likviditet-regel, ingen vol×size-regel, ingen G97-variant.

Noteras: **size är redan prövad som G97-confounder och förklarade inte
vol-effekten** (vol överlevde med t −3,04 och −2,76). Den återupptas inte här.

## H. Rangordnad testkö — en post

| Ordning | Gap | Prio | Motiv |
|---:|---|---|---|
| **1** | **#149 volymmomentum som inkrementell signal** | **MEDIUM** | Enda mätbara luckan i batchen. Featuren är registrerad och oblockerad. Ortogonal mot prisnivåmomentum i konstruktionen. Oberoende kandidatförklaring till G97. **Inte HIGH** — den är en volymtransformation av samma prisserie H0 redan läser, och programmets prior för sådana är negativ. |

## I. Förregistrerad hypotes

### G149 — Volymmomentum som inkrementell information

**Definition, låst.** `volume_trend_13w` = `mean(v, 4 v) / mean(v, föregående 9 v) − 1`,
oförändrad ur featureregistret. Ingen alternativ lookback, ingen normalisering,
ingen vinsorisering. **Endast rå volym `v` används — inget pris, ingen omsatt
krona.** Därmed berörs inte den öppna QA-punkten.

**Population.** Locked H0:s topp-30 vid beslutstidpunkten. Coverage redovisas per
panel och fönster **innan något delta tolkas**; understiger den 20 av 30 utesluts
panelen.

**Hypotes.** Bland namn med jämförbar aktuell H0-score/rank predicerar
`volume_trend_13w` framtida 4/8/12/24 v avkastning **med samma tecken i båda
oberoende fönstren** efter kontroll för aktuell H0-score/rank.

**Riktningen förregistreras inte.** Litteraturen är tvetydig: volymbekräftelse
talar för positivt samband, uppmärksamhets- och överhettningshypotesen för
negativt. Kravet är **teckenreplikation**, inte en riktning vald i efterhand.

**Regel 6:** endast h=1 är icke-överlappande och utgör primärbeviset.

**Falsifieras om** tecknet skiljer sig mellan fönstren eller h=1 inte är
signifikant i något av dem.

**REQUIRES MATCHED-RANDOM PLACEBO IF SIGNAL TEST PASSES.**

## J. Begrepp som INTE förtjänar en körning

* **#141 size som inkrementell signal.** Segmentdiagnostiken har redan mätt
  storlekstercilernas spread på locked H0 och G97-auditen har kontrollerat size.
  Ett rent IC-test skulle vara det tredje angreppet på samma variabel, med 28 %
  täckning i det tidiga fönstret. Låg marginell information.
* **#150 volume-price confirmation.** Är en interaktion mellan #149 och
  prisrörelsen. Prövas inte innan #149 har ett resultat — annars testas
  interaktionen före huvudeffekten.
* **#158 (2)/(3) bredd.** Kräver att jag uppfinner definitioner som inte finns i
  registret. Instruktionen förbjuder det uttryckligen och jag delar bedömningen.
* **Samtliga nio DATA_BLOCKED.** Ett datagap är inte en forskningslucka.

## K. Ledgerintegritet och räknare

| | |
|---|---:|
| Begrepp i Batch 8 | 20 |
| ALREADY_TESTED | **0** |
| PARTIALLY_TESTED | 4 |
| DUPLIKAT | 4 |
| NOT_APPLICABLE | 1 |
| **DATA_BLOCKED** | **9** |
| NOT_TESTED | 2 |
| Genuina locked-H0-luckor | 3 |
| Förtjänar en körning | **1** |
| **Totalt genomgångna av 326** | **160** |

---

# G149 KÖRD — 2026-08-17. **NO INCREMENTAL SIGNAL** (dubbelt bestämd)

Artefakt: `research_k/g149_volume_momentum_results.json`.
Locked H0 reproducerade exakt (7,20 %).

## A. Feature, PIT och det strukturella fyndet

Definition använd **oförändrad** ur `spar_c_features_core_v2.py`:
`mean(daglig v, senaste 4 v) / mean(daglig v, föregående 9 v) − 1`, med kravet
minst 20 observationer i nämnarfönstret. Endast rå volym; inget pris, ingen
omsatt krona — den öppna pris-QA:n berörs alltså inte.

### Tvåfönstertestet är strukturellt omöjligt

| Kontroll | Utfall |
|---|---|
| `validated/prices_h1419/` fältnamn | **endast `d` och `adj`** |
| Hämtade `h1419_bygg_prisryggrad.py` volym? | **nej** — sökning ger noll träffar |
| `validated/prices` rader med volym per år | 2020: 86 884 · 2021: 89 159 · … · 2026: 48 726 · **före 2020: noll** |

**Volym existerar inte i det validerade lagret före 2020.** `volume_trend_13w` är
därför per konstruktion en enfönsterfeature, och det primära kravet — samma
tecken i båda oberoende fönstren — kan aldrig prövas.

**Detta gäller hela VO-familjen**, inte bara #149: `#150 volume-price
confirmation`, `#151 abnormal volume` och `#152 volume shock` bygger alla på
samma volymfält och är därmed lika strukturellt enfönster.

## B–D. Den tillgängliga halvan, kör som dokumenterad enfönsterdiagnostik

Täckningen är **utmärkt**: medel 30,0 av 30, min 29, 100 % av panelerna över
gränsen. Resultatet är alltså inte ett täckningsproblem.

| Horisont | rank-IC | residual \| score | t | t R6 | residual \| score + vol_52w | t | Q5−Q1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| **4 v (h=1)** | −0,0071 | **−0,0118** | **−0,52** | −0,52 | **−0,0146** | −0,63 | −0,22 % |
| 8 v | +0,0217 | +0,0182 | 0,72 | +0,51 | +0,0125 | 0,51 | +1,57 % |
| 12 v | +0,0153 | +0,0134 | 0,56 | +0,32 | +0,0077 | 0,33 | +2,22 % |
| 24 v | −0,0096 | −0,0142 | −0,60 | −0,25 | −0,0242 | −1,20 | −0,65 % |

Kvintiler vid h=1, från låg till hög volymtrend: **+0,89 % · +0,63 % · +1,01 % ·
+0,52 % · +0,67 %.** Ingen struktur alls.

**Tecknet är inte ens stabilt mellan horisonter inom samma fönster** — negativt
vid 4 v, positivt vid 8 och 12 v, negativt igen vid 24 v. Inget t-värde närmar
sig signifikans, varken naivt eller efter Regel 6.

## E. Kontroll mot vol_52w

Kontrollen ändrar ingenting: −0,0118 blir −0,0146 vid h=1. Det finns ingen effekt
att tillskriva vare sig volymtrend eller volatilitet — båda är noll här.

## F. G97-diagnostik — **ej körd**

§5 villkorade den på att G149 visade någon replikerbar signal. Det gjorde den
inte. Att köra den ändå vore att leta efter ett samband i en signal som redan
fallit.

## G. Slutklassificering

# **NO INCREMENTAL SIGNAL**

Domen är **dubbelt bestämd**:

1. Tvåfönsterkravet kan **inte** prövas — volym finns inte före 2020.
2. I det fönster som finns visar featuren **ingenting**, med full täckning, och
   utan stabilt tecken ens mellan horisonter.

Punkt 2 är den viktigare: spåret stängs på **evidens**, inte enbart på ett
datagap. Hade den tillgängliga halvan visat något hade utfallet blivit
PROMISING-BUT-UNSTABLE med ett permanent tak — här behövs inte den distinktionen.

## H. Licensieras något framtida decision-test?

**Nej.** Inget portföljtest, ingen alternativ volymlängd, ingen
abnormal-volume-feature, ingen volym × pris-interaktion.

**Volymmomentum-spåret stängs.** Och eftersom volymfältet saknas före 2020 är
**hela VO-familjen (#149–#152) stängd för tvåfönstertestning** — inte bara den
prövade posten.

Aktiv kö: tom.

### Konsekvens för ledgern

Volymblockeringen har nu två separata orsaker som ska hållas isär:

* **Pris-QA** (`illiquidity_amihud_13w`, `turnover_13w_msek`): blockerar allt som
  kräver omsatt **värde**. Åtgärdbar genom QA på det ojusterade handelspriset.
* **Volymhistorik**: blockerar allt som kräver volym **före 2020**. Åtgärdbar
  endast genom att hämta historisk volym till h1419-lagret — ett större
  datauppdrag som aldrig påbörjats.

Den andra punkten var inte känd före denna körning och läggs till som
permanent anmärkning.

---

# BATCH 9 — begrepp 161–180 (värdering). Read-only.

Masterlistan utökad till 180; 1–160 oförändrade.

## RÄTTELSE FÖRST — jag missade en gällande gate-audit

`docs/SIGNALKALLOR_GATE_AUDIT_2026-08-16.md` fanns redan när jag körde Batch 7,
och den innehåller följande rad:

> **Fundamenta/KPI · Rapportdatum finns · Historik saknar avnoterade bolag ·
> Survivorship-riktningen okontrollerbar · FÖRBJUDEN I MODELLTEST**

**G129 (asset growth) kördes alltså 2026-08-17 på data som projektet dagen innan
förklarat förbjuden i modelltest.** Utfallet blev NO INCREMENTAL SIGNAL, så
domen står — men testet borde inte ha licensierats.

Orsaken är ett fel i min egen Regel 5: den skannade endast `research_k/*.json`
efter nya artefakter, inte `docs/*.md`. **Regel 5 utvidgas härmed till att
omfatta båda.**

Samma dokument gatar dessutom återköp:

> **Återköp · Ej godkänd · Har endast transaktionsdatum, ingen marknadskänd
> tidpunkt · Datablockerad**

`buyback_transaktioner.json` har 42 802 rader med stark täckning i **båda**
fönstren (1 524 rader 2014, 1 303 rader 2019) — men **inget publiceringsdatum**.
Att anta att marknaden kände till ett köp på transaktionsdagen vore look-ahead.
Det var precis den invändning jag stod i begrepp att formulera; den är redan
projektets dokumenterade beslut.

## K2 i detalj — den enda faktiskt prövade delen av familjen

53 paneldatum, median 322 namn per panel, mot H0 + fast 50/50-blend.

| Feature | KPI | Δ mean IC52 | **Δ Top-30 IC52** | block1 / block2 | Survivorship |
|---|---|---:|---:|---|---|
| **ebit_ev_yield** (PRIMARY) | `17_EBIT_EV` | **+0,0797** | **−0,0024** | +0,1076 / +0,0527 | värsta fall **−0,0691**, spegel **−0,0538**, **TECKNET VÄNDER** |
| earnings_ev_yield | `16_E_EV` | +0,0697 | +0,0089 | +0,0959 / +0,0445 | — |
| ev_ebitda | `11_EV_EBITDA` | **−0,0173** | **−0,0482** | −0,0068 / −0,0274 | — |
| ev_sales | `15_EV_S` | +0,0542 | **−0,0217** | +0,0968 / +0,0131 | — |

Klassificering: **SVAGT STÖD**, support_bars [T, T, **F**, T, T, T].

**Två fynd som avgör hela värderingsfamiljen:**

1. **Värdering förbättrar rankningen av universumet men inte av de trettio namn
   H0 faktiskt äger.** Δ mean IC är positiv för tre av fyra mått, men Δ Top-30 IC
   är **negativ eller noll i tre av fyra**. Samma mönster som residual momentum
   (#46, Top-30 IC −0,0380).
2. **Primärmåttets survivorship-gränser vänder tecknet** — från +0,0797 till
   −0,0691 respektive −0,0538. Hela resultatet kan vara survivorship.

Det förklarar också gate-auditens formulering: survivorship-riktningen är
okontrollerbar eftersom KPI-historiken saknar avnoterade bolag.

## Ledger — 161–180

| # | Term | Typ (A–E) | Status | Evidens / orsak | Modell |
|---:|---|:-:|---|---|---|
| 161 | Value factor | D | **DATA_BLOCKED (gate)** | komposit av gatade inputs; K2 prövade fyra beståndsdelar | — |
| 162 | Book-to-market | A | **DATA_BLOCKED (gate)** | `4_PB_r12` finns, 28 % täckning t.o.m. 2019, KPI förbjuden i modelltest | — |
| 163 | Earnings yield | A | **ALREADY_TESTED** | K2 `earnings_ev_yield`: Δmean +0,0697, ΔTop-30 **+0,0089** | H0 + 50/50-blend |
| 164 | **EBIT/EV** | A | **ALREADY_TESTED** | K2 PRIMARY: Δmean +0,0797 men **ΔTop-30 −0,0024** och survivorship vänder tecknet | H0 + 50/50-blend, 53 paneler |
| 165 | EBITDA/EV | A | **ALREADY_TESTED** | K2: Δmean **−0,0173**, ΔTop-30 **−0,0482** | H0 + 50/50-blend |
| 166 | Free-cash-flow yield | A | **DATA_BLOCKED (gate)** | `13_EV_FCF`, `76_P_FCF` finns men KPI förbjuden; ej prövad i K2 | — |
| 167 | Sales-to-price | A | **ALREADY_TESTED** | K2 `ev_sales`: Δmean +0,0542, **ΔTop-30 −0,0217** | H0 + 50/50-blend |
| 168 | Dividend yield | A | **DATA_BLOCKED** | SPARI Batch 1: *"V2:s registry utesluter dividend-yield och saknar QA-godkänd PIT-kedja"*; `1_Direktavkastning` har 28 % täckning | SPARI |
| 169 | Shareholder yield | A | **DUPLIKAT/DATA_BLOCKED** — summan av #168 och #170, båda blockerade | — | — |
| 170 | **Buyback yield** | A | **DATA_BLOCKED (gate, explicit)** | 42 802 transaktioner med **stark täckning i båda fönstren**, men **inget publiceringsdatum**. Transaktionsdatum ≠ marknadskänd tidpunkt | gate-auditen |
| 171 | Composite value | D | **DUPLIKAT av #161** | — | — |
| 172 | Value spread | C | **DATA_BLOCKED (gate)** | tvärsnittlig spridning i samma gatade mått | — |
| 173 | Relative valuation | C | **DUPLIKAT av #172** | — | — |
| 174 | Historisk värdering / mean reversion | C | **DATA_BLOCKED** | kräver lång värderingshistorik per bolag; 28 % täckning t.o.m. 2019 gör den obyggbar | — |
| 175 | Value momentum | B | **DATA_BLOCKED (gate)** | förändring i värdering innehåller dessutom mekaniskt prisinformation och måste separeras från H0 | — |
| 176 | Value trap | — | **NOT_APPLICABLE som egen feature** | Litteraturens definition — billigt bolag vars fundamenta/pris fortsätter försämras — täcks av K3 fundamental change (INGET STÖD), K7 kvalitet (INGET STÖD), FR-overlayen (#140) och H0:s eget momentum. **Ingen ny "value trap score" uppfinns** | K3, K7, FR |
| 177 | Growth-adjusted value | D | **DATA_BLOCKED (gate)** | `19_PEG_r12` finns men gatad | — |
| 178 | Quality-adjusted value | D | **DATA_BLOCKED (gate)** | kombination av två gatade familjer | — |
| 179 | **Momentum–value interaction** | E | **ALREADY_TESTED** | **K2 ÄR detta** — spårets namn är *value within momentum*. Interaktionen är alltså redan prövad och gav SVAGT STÖD med negativ Top-30 IC | H0 + 50/50-blend |
| 180 | Cheapness with catalyst | E | **DATA_BLOCKED** | kräver både gatad värdering och en eventkälla; gate-auditen avvisade rapport/PEAD (*"inget inkrementellt stöd givet H0"*) och FI-insider | gate-auditen |

### Dedupliceringsfamiljer

`V-LVL` värderingsnivå (162–167) · `V-DIST` utdelning och återköp (168–170) ·
`V-COMP` kompositer (161, 171, 177, 178) · `V-REL` relativ och historisk (172–174) ·
`V-CHG` värderingsförändring (175) · `V-INT` interaktioner (176, 179, 180)

Dubbletter: `#169 ≡ #168 + #170` · `#171 ≡ #161` · `#173 ≡ #172`

## A–E. Sammanfattning

**A. Already answered: 4** — #163, #164, #165, #167. Alla fyra ur K2, samtliga med
negativ eller försumbar Top-30 IC.

**B. Dubbletter / ej tillämpliga: 4** — #169, #171, #173, #176.

**C. Partially tested: 0.**

**D. Data-blocked: 12** — #161, #162, #166, #168, #170, #172, #174, #175, #177,
#178, #180, samt #169 i sin blockerade del.

**E. Genuina locked-H0-luckor: 0.**

Det är första batchen utan en enda licensierbar lucka, och orsaken är inte att
allt är testat utan att **hela dataunderlaget är formellt förbjudet i modelltest**.

## F. Valuation-data och PIT-audit

| Krav | Utfall |
|---|---|
| Fundamental täljare känd vid paneldatum | ja, `report_date` finns |
| Pris/EV-nämnare från korrekt datum | ja i KPI-serierna |
| **Historik för avnoterade bolag** | **NEJ — detta är blockeraren** |
| Historisk täckning | **28 % av raderna t.o.m. 2019** för samtliga sex kontrollerade KPI:er |
| Publiceringstidpunkt för återköp | **saknas helt** |

Survivorship-riktningen är okontrollerbar, och K2:s egna gränser visar konkret
vad det betyder: primärmåttets tecken vänder.

## G. POTENTIAL INDEPENDENT EXPLANATION OF G97

**Ingen.** Värderingsdatan är gatad och kan därför inte användas för att förklara
G97:s mekanism. Att köra en vol-mot-värdering-jämförelse på förbjuden data vore
att kringgå gaten via en diagnostisk bakdörr.

## H. Testkö

**Tom.** Ingen post i 161–180 licensieras.

## I. Förregistrerade hypoteser

**Inga.** Att formulera en hypotes på data som är förbjuden i modelltest vore att
skapa en lucka som inte kan stängas hederligt.

## J. Vad som skulle krävas för att öppna familjen

Gate-auditens fem krav gäller oförändrat. För värderingsfamiljen konkret:

1. En **oföränderlig historisk KPI-export som inkluderar avnoterade bolag** —
   det ensamt skulle lyfta förbudet mot fundamenta i modelltest.
2. **Publiceringstidpunkt per återköpstransaktion** — det ensamt skulle öppna
   #170 och därmed halva #169, och det är den enda posten i batchen med redan
   god tvåfönstertäckning.

Båda är datauppdrag, inga forskningshypoteser.

## K. Ledgerintegritet och räknare

| | |
|---|---:|
| Begrepp i Batch 9 | 20 |
| ALREADY_TESTED | 4 |
| DUPLIKAT | 3 |
| NOT_APPLICABLE | 1 |
| **DATA_BLOCKED** | **12** |
| NOT_TESTED | 0 |
| **Genuina locked-H0-luckor** | **0** |
| Förtjänar en körning | **0** |
| **Totalt genomgångna av 326** | **180** |

---

# BATCH 10 — BLOCKERAD PÅ INDATA. Utvidgad Regel 5 utförd.

Datum: 2026-08-17. **Masterlistan innehåller exakt 180 numrerade poster.**
`docs/QUANT_TERM_MASTERLIST.md` säger under rubriken `## 181–326`: *"Ännu inte
överförda."* Poster 181–200 kan därför inte klassificeras.

Detta är tredje gången indata blockerar en batch. Rekommendationen kvarstår
oförändrad: överför resterande 146 begrepp till masterlistan i ett svep, så
behöver ingen framtida batch vänta.

## Regel 5 i sin utvidgade form — den fungerade

Den utvidgning jag gjorde efter Batch 9:s miss (skanna `docs/*.md`, inte bara
`research_k/*.json`) gav omedelbart utdelning. Skanningen hittade
**`docs/PLACERINGSAUDIT_HISTORISKA_TESTER_2026-08-16.md`**, ett bindande
governancedokument jag inte hade läst.

### Vad det säger

Auditen utlöstes av **mitt eget fynd** i `SEGMENT_HORISONT_DIAGNOSTIK.md` steg 4:
att lönsamhetsgrinden *före* hysteresen och portföljkvoten *efter* hysteresen gav
**12,12 % mot 9,90 %** trots identiskt ekonomiskt villkor. Det parallella spåret
tog upp fyndet och granskade hela testkorpusen för placeringskänslighet.

Motorns kanoniska ordning fastställs explicit:

1. hysteres (behåll rank ≤ 35) → 2. påfyllnad till 30 → 3. SMA-/handlingsbarhets-
filter → 4. ERC, FR, vikttak, NTZ, kostnad.

**Domen: ingen historisk V2-dom ändras och ingen bred omkörning är motiverad.**
Fjorton testfamiljer granskades. Lönsamhet var det enda fall där samma
ekonomiska villkor rimligen hade två placeringar, och det är redan prövat i båda
formerna. Övriga är antingen redan före hysteresen (SPARF F4/F7-grindar, SPARI
signalblend, A3), ej urvalskänsliga (invers-vol, target-vol, A1, A2), eller
path-beroende innehavsregler där en förhandsgrind *vore en annan hypotes*
(SPARI Batch 2 DD20/milstolpe/tidsstopp/re-entry, topp-5-spärr, A4, köpband).

### Ny permanent regel — införd i ledgern

> **Regel 7.** Varje ny regel som kan uttryckas **både** som kandidatfilter och
> som portföljtvång ska **preregistrera placeringen**. Om båda placeringarna
> fortfarande uttrycker samma ekonomiska hypotes ska **båda köras och redovisas
> separat**, och **ingen bättre variant får väljas efter resultatet**.

Det binder varje framtida post i testkön.

## Ledgerstatus vid blockeringen

| | |
|---|---:|
| Begrepp i masterlistan | 180 (spann 1–180, inga hål, inga dubbletter) |
| Genomgångna av 326 | **180** |
| Körda hypoteser | 16 |
| Aktiv testkö | **tom** |
| Öppna kandidater | 1 — G97-P, ej fryst, mekanism ej identifierad |
| Permanenta regler | **7** |
| Metodlärdomar | 28 |

### Bindande gate-/governancebeslut som överordnar forskningskön

| Beslut | Källa | Innebörd |
|---|---|---|
| Fundamenta/KPI **förbjuden i modelltest** | gate-audit 2026-08-16 | survivorship-riktningen okontrollerbar |
| Återköp **datablockerad** | gate-audit 2026-08-16 | transaktionsdatum ≠ marknadskänd tidpunkt |
| Riktkurser **datablockerade** | gate-audit 2026-08-16 | en snapshot, ingen revisionshistorik |
| Omsatt värde/ADV/Amihud blockerat | featureregistret | kräver QA-godkänt ojusterat handelspris |
| Volym saknas före 2020 | G149 | varje volymfeature är strukturellt enfönster |
| Placeringen ska preregistreras | placeringsaudit 2026-08-16 | Regel 7 ovan |

Gate-auditens egen slutsats står oemotsagd: *"Det finns ingen ytterligare
försvarbar signal att lägga ovanpå H0 från den aktuella lokala arsenalen."*

När 181–200 uppges klassificeras de mot detta läge.

---

# BATCH 10 — begrepp 181–200 (attribution, diversifiering, aktiv risk, viktning, payoff)

Masterlistan utökad till 200; 1–180 oförändrade. Regel 5 (research_k + docs):
inga nya artefakter.

## A. Viktigaste nya fyndet — H0 slår knappt sitt totalavkastningsbenchmark

`research_m_quality_stability` har tre **redan preregistrerade** benchmarks och
måtten finns beräknade:

| Benchmark | Bench CAGR | H0 CAGR | **Excess** |
|---|---:|---:|---:|
| **XACT Sverige UCITS ETF (total return)** | 7,59 % | 7,61 % | **+0,02 %** |
| OMXSPI (prisindex) | 2,74 % | 7,61 % | +4,87 % |
| V2-universum, likaviktat TR | — | — | — |

**Mot ett brett svenskt totalavkastnings-ETF är H0:s överavkastning +0,02
procentenheter** under 2021-07-16 → 2026-07-10. De +4,87 % mot OMXSPI är till
övervägande del **utdelningsgapet** — OMXSPI är ett prisindex, XACT är total
return.

Kompletterande mått för samma period: `market_beta` **0,8083**,
`sharpe_vs_broad_tr` **0,0342**, `rolling_24m_win_rate` **0,4146**.

Detta gäller en **H0-variant** (7,61 %, okorrigerade vikter) i **ett** fönster,
och ska inte överföras till locked H0 utan omräkning. Men riktningen är
oundviklig och den hör hemma överst i denna batch: **frågan "hur aktiv är H0:s
risk" har delvis redan ett svar, och svaret är att informationskvoten mot ett
passivt TR-alternativ ligger nära noll i det sena fönstret.**

## B. Klassificering 181–200

| # | Term | Grupp | Status | Evidens | Modell |
|---:|---|:-:|---|---|---|
| 181 | Selection effect | A | **ALREADY_TESTED** | G97-P slog matched-random placebo (p 0,003/0,019) → selection skill etablerad; G13+G17: sålda underpresterar sina faktiska ersättare på alla sex horisonter; G12: beslutsgränsen robust | **locked H0, båda fönstren** |
| 182 | Allocation effect | A | **ALREADY_TESTED** | G29 reset mot drift **−0,82/−0,89 pp**; G83 invers-vol **+1,37/−0,22 pp**. Båda med identisk namnuppsättning (invariantkontroll 0 avvikelser) | **locked H0, båda fönstren** |
| 183 | Selection–allocation interaction | A | **NOT_APPLICABLE** | Brinson-interaktionstermen kräver benchmarkvikter per konstituent, vilka saknas. G29/G83 isolerar dessutom allokering rent genom att hålla namnen fasta — interaktionen är per konstruktion noll i den designen | — |
| 184 | Diversification drag | B | **PARTIALLY_TESTED** | A2 mätte variansvinsten direkt: **+0,02 till +0,07 pp** för staggerade kohorter, med sleeve-korrelation 0,90–0,97 | STACK_H (A2) |
| 185 | Concentration premium | B | **ALREADY_TESTED** | G55/G40: topp-3 bär 16,2 %/11,0 % av vinsten; CAGR utan topp-3 **2,64 %/27,99 %**, utan topp-5 **1,69 %**. G83 visade att invers-vol ökar koncentrationen (max vikt 8,2→22,0 %) utan replikerad avkastningsvinst | **locked H0** |
| 186 | **Effective number of bets** | B | **NOT_TESTED** | `avg_n_effective = 30,0` i `research_v` är **viktbaserat** (1/HHI vid likavikt), **inte korrelationsjusterat**. Ingen eigen-/PCA-baserad ENB finns i projektet | — |
| 187 | Correlation clustering | B | **PARTIALLY_TESTED** | `research_v` `CLUSTER_PENALTY`: **7,61 % — exakt identiskt med EW_Base**, alltså noll effekt. A2: sleeve-korrelation 0,90–0,97 | H0-variant, ett fönster |
| 188 | Active share | C | **DATA_BLOCKED** | Kräver benchmarkets **konstituentvikter över tid**. XACT Sveriges innehavshistorik finns inte i projektet | — |
| 189 | Tracking error | C | **PARTIALLY_TESTED** | Benchmarkserier finns (`research_m`, tre stycken preregistrerade); TE inte explicit rapporterad | H0-variant, ett fönster |
| 190 | Information ratio | C | **PARTIALLY_TESTED** | `sharpe_vs_broad_tr` **0,0342** och excess **+0,02 %** mot TR-ETF:en → IR nära noll i det sena fönstret | H0-variant, ett fönster |
| 191 | Risk contribution | D | **PARTIALLY_TESTED** | `SHADOW_ERC_X2` **är** equal-risk-contribution (invvol^1,5), 13,60 % i registret; `research_v` V4 innehåller riskbidragsdiagnostik och en 6 %-riskcap | **ERC/shadow, EJ locked H0** |
| 192 | Marginal contribution to risk | D | **DUPLIKAT av #191** | MCR är derivatan av samma storhet | — |
| 193 | Risk budgeting | D | **DUPLIKAT av #191** | ERC *är* en riskbudget | — |
| 194 | Position sizing | D | **ALREADY_TESTED** | G83 invers-vol och G29 reset/drift på **locked H0**; SPARI Batch 1 invers-vol och target-vol: **INGET STÖD** | locked H0 + SPARI |
| 195 | Conviction weighting | D | **DUPLIKAT av #196** | konviktion operationaliseras som score | — |
| 196 | Score weighting | D | **NOT_TESTED** | se motargumentet i avsnitt J | — |
| 197 | Rank weighting | D | **NOT_TESTED** | se motargumentet i avsnitt J | — |
| 198 | Upside capture | E | **PARTIALLY_TESTED** | `research_v`: **0,8557** | H0-variant, ett fönster |
| 199 | Downside capture | E | **PARTIALLY_TESTED** | `research_v`: **0,7730** | H0-variant, ett fönster |
| 200 | Positive skew / right-tail | E | **ALREADY_TESTED** | G55/G40 mätte höger-svansberoendet fullt ut i båda fönstren; HHI-effektiva bidragsgivare 40,2 respektive 56,4 | **locked H0, båda fönstren** |

**Payoff-asymmetrin är gynnsam:** H0 fångar 85,6 % av uppgången och bara 77,3 %
av nedgången. Det är förenligt med `market_beta` 0,81 och Sortino > Sharpe.

## C. Deduplicerade mekanismfamiljer

`AT` attribution (181–183) · `DIV` diversifiering (184–187) ·
`ACT` aktiv risk (188–190) · `WGT` viktning (191–197) · `PAY` payoff (198–200)

Dubbletter: `#192 ≡ #191` · `#193 ≡ #191` · `#195 ≡ #196`

## D. Already answered (5)

#181, #182, #185, #194, #200 — samtliga på **locked H0** och fyra av fem i båda
fönstren. Attributionsfrågan "var kommer alfan ifrån" är alltså i huvudsak redan
besvarad: **selection skill finns och är placebo-verifierad; allocation har
prövats i två riktningar och ingen replikerar.**

## E. Genuina locked-H0-luckor (1)

**#186 effective number of bets.** Det enda begreppet i batchen som är
oprövat, ekonomiskt distinkt, och byggbart av **oblockerad** data — det kräver
endast prisserier, inga KPI:er, ingen volym, inget omsatt värde.

`avg_n_effective = 30,0` mäter viktkoncentration, inte oberoende risk. Frågan
"hur många oberoende vad H0:s trettio innehav faktiskt representerar" är öppen.

## F. Data-blocked (1)

**#188 active share** — kräver benchmarkets konstituentvikter över tid. Inte
åtgärdbart utan en historisk innehavsexport för XACT Sverige.

## G. POTENTIAL INDEPENDENT EXPLANATION OF G97

**#186/#187 markeras.** Om G97-P:s sex högvolatila namn också är inbördes högt
korrelerade skulle deras exkludering höja det effektiva antalet bets — en
riskstruktureffekt snarare än en avkastningsprognos. Det vore en oberoende
förklaring till varför regeln fungerar utan att någon prediktionsmekanism är
identifierad.

Det får påverka prioriteringen av #186. Det får **inte** generera en
vol × korrelations-feature eller någon G97-variant.

## H. Rangordnad testkö — en post

| Ordning | Gap | Prio | Motiv |
|---:|---|---|---|
| **1** | **#186 effective number of bets** | **MEDIUM** | Enda oprövade, oblockerade och distinkta posten. Ren diagnostik som inte kan förbättra CAGR — men den avgör om H0:s trettio innehav är trettio bets eller fem, vilket är en förutsättning för att tolka varje riskmått i portföljen. Dessutom oberoende kandidatförklaring till G97. |

## I. Förregistrerad hypotes

### G186 — Effektivt antal bets i locked H0

**Definition, låst.** Meucci's effective number of bets på **korrelationsmatrisen
för de faktiskt innehavda namnen**, beräknad per rebalanspanel:
ENB = exp(−Σ pᵢ ln pᵢ) där pᵢ är varje principalkomponents andel av
portföljvariansen, med komponenterna från egenvärdesuppdelning av
kovariansmatrisen för de 30 namnens **veckoavkastningar över 52 veckor**,
strikt till och med paneldatum.

Ingen alternativ ENB-definition, ingen shrinkage, ingen klusteralgoritm.
Endast prisdata. **Berörs inte av någon gällande gate.**

**Primärt utfall.** Medianen av ENB per panel, redovisad separat för båda
fönstren, jämte det viktbaserade 1/HHI (= 30 vid likavikt) som referens.

**Hypotes.** Locked H0:s effektiva antal bets är **minst 10** i median i båda
fönstren — alltså att de trettio innehaven representerar minst en tredjedel så
många oberoende riskkällor som namn.

**Falsifieras om** medianen understiger 10 i något fönster. Då är H0 väsentligt
mindre diversifierad än antalet innehav antyder, och varje riskmått i projektet
— inklusive maxDD-jämförelserna i G29, G83 och G97-P — måste läsas om i det
ljuset.

**Ingen placebo krävs** — testet ändrar inga namn och inga vikter. Regel 7 är
inte tillämplig: detta är en diagnostik, inte en regel med en placering.

**Detta är ett rent diagnostiskt test.** Ett lågt ENB licensierar **ingen**
åtgärd — inte klusterviktning, inte korrelationsstraff, inte ändrat N. Sådant
skulle kräva en egen förregistrering, och `research_v`s CLUSTER_PENALTY gav
redan exakt noll effekt.

## J. NOT_TESTED som ändå inte förtjänar körning

**#196 score weighting och #197 rank weighting.** Batchens egen regel kräver en
separat ex ante-mekanism. Den saknas, och evidensen pekar åt fel håll:

* **H0:s egen Top-30 IC är negativ eller noll** — −0,0250 i SPARI:s championtabell,
  +0,0205 respektive **−0,0442 (t −1,92)** i `h0_h1_h2_tvafonster`. Att vikta
  efter rank skulle alltså tilta mot de namn som går något **sämre**.
* **Poängen är nästan platt**: 0,1045 percentilenheter mellan rank 1 och 30, och
  G12 mätte ordningens hela informationsvärde till **~0,2 pp/år**.
* **H1 är det permanenta motexemplet**: den hade Top-30 IC +0,0348/+0,0528 och
  gav ändå −5,48 pp CAGR. Att kunna rangordna inom portföljen är inte
  detsamma som att kunna tjäna på det.

Att köa score- eller rankviktning vore att öppna viktoptimeringen som Batch 2
och Batch 5 stängde, under ett nytt namn.

**#189/#190/#198/#199** — måtten finns beräknade på en H0-variant i ett fönster.
Att räkna om dem på locked H0 i båda fönstren är **bokföring, inte forskning**,
och köas inte som ett test.

## K–L. Ledgerintegritet och räknare

| | |
|---|---:|
| Begrepp i Batch 10 | 20 |
| ALREADY_TESTED | 5 |
| PARTIALLY_TESTED | 7 |
| NOT_TESTED | 3 |
| DUPLIKAT | 3 |
| NOT_APPLICABLE | 1 |
| DATA_BLOCKED | 1 |
| Genuina locked-H0-luckor | **1** |
| Förtjänar en körning | **1** |
| **Totalt genomgångna av 326** | **200** |

## Familjer som kan stängas

* **AT attribution (181–183)** — stängd. Selection och allocation är båda
  besvarade på locked H0; interaktionstermen är inte definierbar utan
  benchmarkvikter.
* **WGT viktning (191–197)** — stängd med undantag för #191:s locked-H0-status.
  Position sizing är testad, ERC finns som fryst shadowmodell, och score-/
  rankviktning saknar ex ante-mekanism.
* **PAY payoff (198–200)** — stängd. Höger-svansen är fullt mätt i båda fönstren
  och capture-måtten finns; asymmetrin är gynnsam.

---

# G186 KÖRD — 2026-08-17. **MATERIAL HIDDEN RISK CONCENTRATION**

Förregistrering `research_k/g186_preregistration.json`, sha256 `891fc11c69aa0649…`,
låst före all beräkning. Artefakter: `research_k/g186_results.json`,
`research_k/g186_paneldata.jsonl` (145 paneler).

## A–B. Governance och invarianter

Regel 5 (research_k + docs): inget nytt. **Locked H0 reproducerade exakt** i båda
fönstren, 7,20 % och 31,56 %. **Noll paneler föll bort** — samtliga 66 respektive
79 hade full historik, median 52 veckor och 30 namn per matris.

## C. Definition

Meucci (2009) principalportföljer: `Sigma = E Λ E'`, `w̃ = E'w`,
`p_i = w̃_i² λ_i / (w'Σw)`, `ENB = exp(−Σ p_i ln p_i)`. Veckovisa enkla
avkastningar, trailing 52 veckor, strikt PIT, lika vikt över de namn H0 faktiskt
äger. Sample-kovarians som primär; Ledoit-Wolf som **förregistrerad** sensitivitet.

## D. Primärt tvåfönsterresultat

| | 2020-2026 | 2014-2019 |
|---|---:|---:|
| Giltiga paneler | 66 av 66 | 79 av 79 |
| **Median ENB (sample)** | **2,99** | **2,96** |
| Medel | 3,26 | 3,19 |
| Q10 / Q25 / Q75 / Q90 | 1,65 / 2,25 / 4,20 / 5,22 | 1,55 / 2,03 / 4,34 / 5,00 |
| Min / max | 1,20 / 7,88 | 1,23 / 6,79 |
| Andel paneler ENB < 5 | 84,9 % | 89,9 % |
| **Andel ENB < 10** | **100 %** | **100 %** |
| **ENB / 30** | **0,100** | **0,099** |
| Median ENB, Ledoit-Wolf | 4,16 | 3,80 |
| Halvor (första/andra) | 2,53 / 3,95 | 3,00 / 2,87 |

**Den preregistrerade hypotesen — median ENB ≥ 10 i båda fönstren — faller, och
den faller med bred marginal.** Inte en enda panel av 145 når ENB 10.

H0:s trettio likaviktade innehav beter sig som ungefär **tre oberoende
riskbets**. Ledoit-Wolf-korrigeringen lyfter siffran till 3,8–4,2, precis som
den förregistrerade biasanalysen förutsåg — men den ändrar inte storleksordningen.

## E–F. Eigen- och korrelationsdiagnostik

| | 2020-2026 | 2014-2019 |
|---|---:|---:|
| Median pairwise korrelation | **0,125** | **0,123** |
| Största egenvärdets andel av tillgångsvariansen | 30,3 % | 22,8 % |
| Tre största egenvärdenas andel | 58,4 % | 46,5 % |
| Ledoit-Wolf shrinkage-delta | 0,570 | 0,528 |

**Här ligger den intressanta spänningen.** Den genomsnittliga parvisa
korrelationen är bara **0,12** — låg. Ändå är ENB 3.

Förklaringen är mekanisk och värd att skriva ut: en **likaviktad long-only**
portfölj laddar nästan hela sin varians på den gemensamma faktorn, eftersom det
är den enda komponent som inte diversifieras bort när man adderar namn. Att
första principalkomponenten bara utgör 23–30 % av *tillgångarnas* varians hindrar
inte att den utgör merparten av *portföljens*.

## G. Deskriptivt samband med efterföljande risk

| | 2020-2026 | 2014-2019 |
|---|---:|---:|
| korr(ENB, efterföljande 3-panelsvolatilitet) | **−0,327** | +0,142 |
| korr(ENB, efterföljande 3-paneldrawdown) | +0,092 | +0,018 |

Tecknet vänder mellan fönstren på volatilitetssambandet. **Ingen gate
licensieras härav** och sambandet ska inte tolkas som prediktivt.

## H. G97-P riskkoncentration — **resultatet går emot hypotesen**

| | 2020-2026 | 2014-2019 |
|---|---:|---:|
| Pairwise korr **mellan de sex exkluderade** | +0,067 | **+0,073** |
| Pairwise korr **mellan övriga 24** | +0,135 | **+0,151** |
| Korr high-vol mot övriga | +0,085 | +0,094 |
| **De sex andel av portföljvariansen** | **39,0 %** | **34,3 %** |
| **Δ ENB (G97-P minus H0)** | **−1,50** | **−1,28** |
| Andel paneler med positivt Δ ENB | 14 % | 6 % |

Två fynd som pekar åt motsatt håll mot den hypotes som motiverade markeringen:

1. **De sex högvolatila namnen är MINDRE korrelerade med varandra än de övriga
   är** — 0,07 mot 0,15. De klustrar alltså inte.
2. **Att exkludera dem SÄNKER det effektiva antalet bets** med 1,3–1,5, i 86–94 %
   av panelerna. De bidrog med idiosynkratisk, okorrelerad varians; kvar blir en
   mer homogen och inbördes mer korrelerad rest.

De bär visserligen 34–39 % av portföljvariansen mot 20 % vid likavikt — men det
är en *volatilitets*effekt, inte en *korrelations*effekt.

# **NOT CONSISTENT WITH G97 RISK-CONCENTRATION EXPLANATION**

Och det stärker gåtan snarare än löser den: **G97-P fungerar trots att den
minskar den effektiva diversifieringen.** Dess prediktiva mekanism förblir
oidentifierad.

## I. Robusthet

Leave-one-panel-out på medianen: **[2,986, 2,992]** respektive **[2,95, 2,98]** —
utfallet hänger inte på någon enskild panel. Noll bortfall, median 52 veckor och
30 namn per matris. Ledoit-Wolf-sensitiviteten korsar inte tröskeln 10 i något
fönster.

## J. Slutklassificering

# **MATERIAL HIDDEN RISK CONCENTRATION**

Median ENB understiger 10 i båda fönstren, inte marginellt utan med faktor tre,
och estimatorvalet ändrar inte domen.

## K. Vad fyndet betyder ekonomiskt

**H0:s riskdiversifiering är ungefär en tiondel av dess nominella.** Varje
riskmått i projektet som implicit antagit trettio ungefär oberoende innehav ska
läsas om i det ljuset — inklusive maxDD-jämförelserna i G29, G83 och G97-P, där
skillnader på en till fem procentenheter i drawdown nu framstår som brus kring en
gemensam faktor snarare än som strukturella egenskaper.

Det förklarar också varför **A2:s staggerade kohorter gav en variansvinst på
endast +0,02 till +0,07 pp**: med tre effektiva bets finns nästan ingenting att
diversifiera bort genom tidsförskjutning.

## L. Vad fyndet uttryckligen INTE visar

**Tre reservationer, och den första är en kritik av min egen förregistrering.**

1. **Tröskeln 10 var illa kalibrerad.** ENB kring 3 är nära vad **vilken
   likaviktad long-only aktieportfölj som helst** uppvisar, eftersom marknads-
   faktorn dominerar. Utan ett jämförelse-ENB — för ett slumpmässigt urval av 30
   namn ur samma universum, eller för universumet självt — kan jag **inte** säga
   att H0 är ovanligt koncentrerad. Jag satte tröskeln och den var för hög.
   Domen följer förregistreringen, men dess *tolkning* måste vara försiktigare än
   etiketten låter.
2. **Lågt ENB betyder inte att H0 är dålig**, och det betyder inte att en
   diversifieringsregel skulle förbättra avkastningen. `research_v`s
   CLUSTER_PENALTY gav redan exakt noll effekt.
3. **Lågt ENB är inte samma sak som return concentration.** G55/G40 mätte
   40,2 respektive 56,4 effektiva bidragsgivare till *avkastningen*. Att
   riskstrukturen har 3 dimensioner och avkastningsbidragen 40–56 källor är
   inte motsägelsefullt — det är två olika storheter, precis som
   förregistreringen slog fast.

## M. Motiveras något separat framtida test?

**Ett, och det är en kalibrering, inte en strategi.** Det enda som skulle göra
G186:s tal tolkbara är ett referens-ENB: samma beräkning på (a) ett slumpmässigt
urval av 30 namn ur samma PIT-universum och (b) hela universumet likaviktat.
Utan det vet vi bara att H0 har tre bets, inte om det är få.

Det formuleras här men **körs inte**, och det får inte utvidgas till någon regel:

> **G186-K.** Median-ENB för 200 slumpmässiga likaviktade 30-namnsurval ur H0:s
> PIT-universum, per panel och fönster, med identisk estimator och identiskt
> 52-veckorsfönster. **Hypotes:** H0:s median-ENB skiljer sig **inte** från det
> slumpmässiga urvalets med mer än 1,0. Faller den är H0 verkligt avvikande;
> håller den är ENB ≈ 3 en egenskap hos svensk long-only aktieexponering och
> inte hos H0.

Ingen ny tradingregel, ingen viktoptimering, ingen clusterregel, ingen
sektorgate. H0 oförändrad. G97-P oförändrad. Ingen freeze.

---

# G186-K KÖRD — 2026-08-17. **NORMAL LONG-ONLY ENB**

## Detta korrigerar G186:s etikett

G186 klassade locked H0 som **MATERIAL HIDDEN RISK CONCENTRATION** på median
ENB 2,99 / 2,96 mot en tröskel på 10. Jag flaggade samtidigt att tröskeln kunde
vara illa kalibrerad. **Kalibreringen visar nu att den var det.**

Artefakter: `research_k/g186k_results.json`, `research_k/g186k_paneldata.jsonl`
(128 paneler). Seed 20260818, 200 dragningar per panel.

## A–B. Invarianter och konstruktion

Locked H0 reproducerade exakt (7,20 % / 31,56 %).

För rättvis jämförelse används ett **rektangulärt veckoraster**: panelens 52
senaste ISO-veckor, och endast namn med fullständig historik — identiskt för H0
och slumpportföljerna. G186 använde parvis snitt, vilket inte går att tillämpa
konsekvent på 200 slumpdragningar.

| | 2020-2026 | 2014-2019 |
|---|---:|---:|
| Paneler använda | 66 av 66 | **62 av 79** |
| Bortfall (rektangulär regel) | 0 | **17** |
| Universumstorlek med full 52v-historik, median | 341 | 274 |
| H0 ENB under rektangulär regel | 2,99 | 2,93 |
| H0 ENB i G186 (parvis snitt) | 2,99 | 2,96 |

Rasterregeln flyttar H0:s tal med högst 0,03 — de två beräkningarna är i praktiken
identiska, vilket gör jämförelsen giltig.

## C–D. H0 mot slumpmässiga EW30 ur samma PIT-universum

| | 2020-2026 | 2014-2019 |
|---|---:|---:|
| **H0 median ENB** | **2,99** | **2,93** |
| **Slump EW30 median ENB** | **2,59** | **2,49** |
| **Skillnad H0 − slump** | **+0,40** | **+0,43** |
| Slumpens Q5 / Q25 / Q75 / Q95 | 1,40 / 1,94 / 3,34 / 4,52 | 1,35 / 1,87 / 3,28 / 4,42 |
| **H0:s percentil i slumpfördelningen** | **78,2 %** | **62,0 %** |
| Andel paneler där H0 < slumpens median | 19,7 % | 33,9 % |
| Andel paneler där H0 < slumpens Q10 | **3,0 %** | **1,6 %** |

**H0 ligger inte under slumpen — den ligger något över, i båda fönstren, med
samma tecken och nästan samma magnitud.** H0 hamnar på 78:e respektive 62:a
percentilen av vad ett slumpmässigt 30-namnsurval ur samma universum ger, och
faller under slumpens tionde percentil i bara 1,6–3,0 % av panelerna.

Stabilitet över halvor: +0,81 / +0,89 (sent) och +0,39 / +0,69 (tidigt) — samma
tecken i alla fyra delfönster.

## E. Sekundär matchning — volatilitetsstratifierad slump

| | 2020-2026 | 2014-2019 |
|---|---:|---:|
| Stratifierad slump, median ENB | 2,48 | **3,53** |
| H0 minus stratifierad | +0,51 | **−0,60** |

**Tecknet vänder mellan fönstren.** Diagnostiken är därmed **inconclusive** och
får inte tolkas. Den enda avläsning som är försvarbar är negativ: den ger inget
stöd för att H0:s ENB skulle drivas av dess volatilitetsprofil.

## F. Sensitivitet

Ledoit-Wolf på H0: median 4,10 respektive 3,82 mot sample 2,99 och 2,93 — samma
uppjustering som i G186. **LW kördes endast på H0**, inte på de 200
slumpdragningarna per panel, så sensitiviteten gäller nivån och inte skillnaden.
Eftersom H0 och slumpen mäts med **identisk** estimator är differensen ändå
jämförbar.

## G. Slutklassificering

# **NORMAL LONG-ONLY ENB**

|H0 − slump| är 0,40 och 0,43 — båda långt under gränsen 1,0, med samma tecken
i båda fönstren.

## H. Vad resultatet betyder

**ENB kring 3 är normalt för en likaviktad long-only svensk aktieportfölj med 30
namn.** Det är inte en egenskap hos H0 utan hos tillgångsslaget: marknadsfaktorn
dominerar portföljvariansen oavsett vilka trettio namn man väljer, även när den
genomsnittliga parvisa korrelationen bara är 0,12.

Och H0 är **marginellt bättre** än slumpen, inte sämre. Momentumurvalet
koncentrerar alltså inte risken mer än ett slumpmässigt urval gör — om något
något mindre.

### Formell rättelse av G186

G186:s dom **MATERIAL HIDDEN RISK CONCENTRATION** var korrekt enligt sin egen
förregistrering men **vilseledande som beskrivning**. Tröskeln på 10 hade ingen
empirisk grund, och jag satte den. Den korrekta läsningen av G186 och G186-K
tillsammans är:

> H0 har ungefär tre effektiva riskbets, vilket är **normalt** för konstruktionen
> och marginellt bättre än ett slumpmässigt urval. Det är inte ett dolt problem.

G186:s **substantiella** fynd står dock kvar oförändrade och är fortfarande
viktiga: att riskdiversifieringen är en tiondel av den nominella påverkar hur
maxDD-jämförelserna i G29, G83 och G97-P ska läsas, och det förklarar varför A2:s
staggerade kohorter bara gav +0,02 till +0,07 pp. **Det som faller är etiketten
"ovanlig koncentration", inte observationen.**

## I. Vad resultatet INTE betyder

1. **Det säger inte att låg ENB är oproblematisk** — bara att den inte är
   H0-specifik. En portfölj med tre effektiva bets bär koncentrerad faktorrisk
   oavsett om alla andra också gör det.
2. **Det licensierar ingen regel.** Inget klusterstraff, ingen sektorgate, ingen
   risk parity, inget alternativt N. `research_v`s CLUSTER_PENALTY gav redan
   exakt noll effekt.
3. **Det säger ingenting om G97.** G186 visade att G97-P *sänker* ENB; G186-K
   ändrar inte den observationen och försöker inte förklara den.
4. **Den sekundära volatilitetsmatchningen är inconclusive** och får inte
   citeras åt något håll.
5. **17 av 79 paneler föll bort** i det tidiga fönstret på den rektangulära
   regeln. Slutsatsen där vilar på 62 paneler, inte 79.

## Familjen stängs

**DIV-familjen (184–187) är därmed helt avgjord.** Diversification drag,
concentration premium, effective number of bets och correlation clustering är
alla besvarade, och ingen av dem licensierar en åtgärd.

Aktiv kö: tom. H0 oförändrad. G97-P oförändrad. Ingen freeze.

---

# BATCH 11 — begrepp 201–220 (exekvering, kostnad, timing, kapacitet)

Masterlistan utökad till 220; 1–200 oförändrade. Regel 5 (research_k + docs):
inga nya artefakter, inga nya bindande beslut sedan G186-K.

## Fyra frågor som hålls strikt isär

**A kostnadsantagande** — vad vi antar att handeln kostar.
**B faktisk exekveringsfriktion** — spread, slippage, impact.
**C timing** — fas, kalender, exekveringslag.
**D kapacitet** — hur mycket kapital konstruktionen tål.

**SPARG:s kostnadsstress är evidens för A och ingenting annat.** Den varierar ett
platt enhetspris (0/20/40/60/100 bp) och säger ingenting om spread, impact eller
kapacitet. Att citera den som stöd för B eller D vore en kategorifel.

## Ledger — 201–220

| # | Term | Fråga | Status | Evidens | Modell |
|---:|---|:-:|---|---|---|
| 201 | Implementation shortfall | A | **DUPLIKAT av Batch 8 #160** | SPARG: 0/20/40/60/100 bp → 25,91/25,29/24,67/24,05/22,81 %; break-even ~534 bp | SPARG-champion, ett fönster |
| 202 | Slippage | B | **DATA_BLOCKED** | Ingen intraday- eller spreaddata i det frysta lagret; 20 bp är ett *blandat* antagande som täcker slippage utan att mäta den | — |
| 203 | Market impact | B | **DATA_BLOCKED** (= Batch 8 #155) | kräver omsatt värde → pris-QA | — |
| 204 | Bid–ask spread | B | **DATA_BLOCKED** | ingen spreadserie finns | — |
| 205 | Transaction-cost drag | A | **ALREADY_TESTED** | Batch 1: H0:s omsättning **228,5 %/187,1 % per år × 20 bp = 0,46 %/0,37 % per år** | **locked H0, båda fönstren** |
| 206 | Explicit vs implicit costs | B | **DATA_BLOCKED** | 20 bp är ett enda blandat tal; uppdelningen kräver spread- och impactdata | — |
| 207 | Turnover decomposition | A | **ALREADY_TESTED** | Batch 1: H0:s omsättning uppstår **enbart vid namnbyten** — likavikten skapar ingen viktomsättning för behållna namn. Det *är* dekompositionen | **locked H0** |
| 208 | Rebalancing drag | C | **ALREADY_TESTED** | **G29**: drift mot reset gav **−0,82/−0,89 pp** för drift. Det finns alltså ingen ombalanseringsdrag — reset är bättre | **locked H0, båda fönstren** |
| 209 | Rebalancing premium | C | **DUPLIKAT av #208** — samma test, omvänd formulering. Premien är +0,82/+0,89 pp | — | — |
| 210 | Timing luck | C | **PARTIALLY_TESTED** | **A1** mätte fasspridning över **samtliga** förskjutningar: vid 8 veckor sd 0,46 %/2,04 %; vid 52 veckor **8,2 pp spann** enbart från startvecka. Fasövervikten i kontraktet: +0,33/+1,44 pp | **STACK_H — ej locked H0** |
| 211 | Rebalance timing sensitivity | C | **DUPLIKAT av #210** | — | — |
| 212 | Staggered rebalancing | C | **ALREADY_TESTED** | **A2**: 2–13 kohorter, samtliga negativa (−0,30 till −9,85 pp). Sleeverna är **0,90–0,97 korrelerade**; variansvinsten +0,02 till +0,07 pp | STACK_H |
| 213 | Overlapping portfolios | C | **DUPLIKAT av #212** — staggerade kohorter *är* överlappande portföljer | — | — |
| 214 | Holding-period overlap | — | **NOT_APPLICABLE som portföljmekanism** | Detta är **Regel 6**, en permanent statistisk regel om överlappande framåtfönster, redan i kraft sedan Batch 4. Inte en testbar portföljegenskap | — |
| 215 | Execution lag | C | **ALREADY_TESTED / IMPLEMENTERAD** | `EXECUTION_TIMING_REPAIR_DF.md`: preregistrerad regel — ingen order till close T eller äldre; market-on-close efter beslut T; exekvering till justerad stängning **första observerade handelsdag efter T**. Spår D gick från ogiltig V2 till exekverbar V3 | **locked H0 (D/F-reparationen)** |
| 216 | **Signal-to-execution decay** | C | **NOT_TESTED** | Samma dokument säger uttryckligen: *"Ingen alternativ executionvariant testades."* Legacy N3-82 prövade lag 0/1/2/5 dagar × 1x/2x kostnad — men på **LambdaRank**, inte H0 | — |
| 217 | Capacity | D | **DATA_BLOCKED** (= Batch 8 #156) | kräver ADV i omsatt värde | — |
| 218 | Participation rate | D | **DATA_BLOCKED** | kräver ADV | — |
| 219 | Trade netting | A | **NOT_APPLICABLE** | H0:s omsättningsmått är redan nettat: `sum|Δw|/2`. Utan orderdata finns inget ytterligare att mäta | locked H0 |
| 220 | Portfolio transition cost | A | **DUPLIKAT av #205** | övergångskostnaden *är* omsättning × enhetskostnad | — |

### Dedupliceringsfamiljer

`COST-A` kostnadsantagande (201, 205, 207, 219, 220) · `FRIC-B` faktisk friktion
(202, 203, 204, 206) · `TIME-C` timing (208–216) · `CAP-D` kapacitet (217, 218)

Dubbletter: `#201 ≡ Batch 8 #160` · `#209 ≡ #208` · `#211 ≡ #210` ·
`#213 ≡ #212` · `#220 ≡ #205` · `#203 ≡ Batch 8 #155`

## A. Already answered (5)

**#205** kostnadsdrag (0,46/0,37 % per år på locked H0) · **#207**
omsättningsdekomposition · **#208** ombalanseringsdrag (G29: reset är **bättre**,
ingen drag existerar) · **#212** staggerad ombalansering (A2, samtliga negativa)
· **#215** exekveringslag (D/F-reparationen, preregistrerad och implementerad).

## B. Dubbletter och ej tillämpliga (7)

Fem rena dubbletter plus **#214** och **#219**. #214 är särskilt värt att notera:
*holding-period overlap är Regel 6*, en statistisk korrigeringsregel som redan
gäller för all IC-inferens — inte en portföljmekanism som kan testas.

## C. Data-blocked (6)

**#202, #203, #204, #206** — hela **FRIC-B**-familjen. Ingen spread-, intraday-
eller impactdata finns. **#217, #218** — hela **CAP-D**-familjen, blockerad av
pris-QA:n på omsatt värde.

**Tolv av tjugo begrepp i denna batch är alltså antingen redan besvarade eller
blockerade av datagap.** Ett datagap får inte omvandlas till en forskningshypotes.

## D. Genuina locked-H0-luckor (2)

1. **#216 signal-to-execution decay** — explicit oprövad enligt D/F-dokumentets
   egen formulering, och den enda posten i batchen som är både distinkt,
   oblockerad och tvåfönstertestbar.
2. **#210/#211 timing luck på locked H0** — A1 mätte mekanismen grundligt men på
   **STACK_H**. Se avsnitt H för varför den ändå inte licensieras separat.

## E. Koppling till G97-P

**Ingen.** Inget begrepp i 201–220 ger en oberoende förklaring till G97-P:s
mekanism. Exekveringsfriktion och kapacitet är portföljegenskaper, inte
prediktiva mekanismer, och att konstruera en vol × exekveringskoppling vore
precis den G97-variant som är förbjuden.

## F. Rangordnad testkö — en post

| Ordning | Gap | Prio | Motiv |
|---:|---|---|---|
| **1** | **#216 signal-to-execution decay** | **MEDIUM** | Enda distinkta, oblockerade och tvåfönstertestbara luckan. Implementationsrealism, vilket enligt Batch 8:s prioriteringsordning kan motivera ett test även utan CAGR-förbättring. Ex ante-mekanismen är tydlig: om H0:s edge försvinner vid några dagars fördröjning är strategin bräcklig mot verklig orderhantering. |

## G. Preregistrerad hypotes

### G216 — Signalens tålighet mot exekveringsfördröjning

**Konstruktion.** Canonical locked H0 i övrigt oförändrad: samma urval, samma
paneler, samma likavikt, samma 20 bp, samma ombalanseringskalender. **Enda
ändringen** är exekveringsdagen.

**Armar, låsta i förväg:** exekvering till justerad stängning på handelsdag
**T+1** (kanonisk, D/F-reparationens regel), **T+2**, **T+3** och **T+5**.
Ingen annan lag prövas, ingen kostnadsvariation, ingen partiell exekvering.

**Regel 7:** ej tillämplig — detta är varken kandidatfilter eller portföljtvång
utan en exekveringsparameter. **Ingen matched-random placebo krävs** — inga namn
byts, endast dagen då samma byten genomförs.

**Primärt utfall.** Netto-CAGR per arm och fönster, samt Δ mot T+1.

**Hypotes.** Locked H0:s netto-CAGR faller med **mindre än 1,0 procentenhet**
mellan T+1 och T+5 i **båda** oberoende fönstren.

**Falsifieras om** fallet överstiger 1,0 pp i något fönster. Då är H0:s
redovisade avkastning beroende av att komma in på nästa dags stängning, och varje
praktisk fördröjning — sen orderläggning, illikvid öppning, delfyllnad — äter
en materiell del av resultatet.

**Biprodukt som redovisas men inte utgör ett eget test:** samma harness ger
fasspridningen för locked H0 gratis (två faser vid 8 veckors ombalansering).
Den rapporteras som kvalificering av talen 7,20 % och 31,56 %, **inte** som
utfallet av en separat hypotes.

## H. Vad som uttryckligen INTE ska testas

* **#210/#211 timing luck som eget test.** A1 prövade sex takter över **samtliga**
  fasförskjutningar och etablerade mekanismen fullständigt: vid 8 veckor är
  fasspridningen liten (sd 0,46 %/2,04 %), vid 52 veckor stor (8,2 pp). Att köra
  om det på locked H0 mäter samma mekanism på en annan viktning. Marginell
  information — och fasspridningen faller ut gratis ur G216:s harness.
* **#212/#213 staggering.** A2 gav samtliga negativa utfall och förklarade varför:
  sleeverna är 0,90–0,97 korrelerade. G186 stärkte förklaringen — med ~3
  effektiva bets finns nästan inget att diversifiera bort över tid. Familjen
  stängd.
* **Hela FRIC-B och CAP-D.** Blockerade av data, inte av kunskap. Att bygga en
  spread- eller impactproxy vore precis det gate-auditen förbjuder.
* **#219 trade netting.** Redan implicit i `sum|Δw|/2`. Utan orderdata finns
  ingenting att dekomponera.

## I. Vilka frågor kräver enbart dataarbete

Tre poster skulle öppnas av **ett enda** datauppdrag — QA på det ojusterade
handelspriset:

| Post | Vad som låses upp |
|---|---|
| #203 market impact | impactmodell mot orderstorlek |
| #217 capacity | kapacitetstak i kronor |
| #218 participation rate | deltagandegrad mot ADV |

Ytterligare två kräver **ny** data som inte finns lokalt alls: **#204 bid–ask
spread** och **#202 slippage** behöver en historisk spread- eller intradayserie.

Ingen av dessa är en forskningshypotes.

## Räkning

| | |
|---|---:|
| Begrepp i Batch 11 | 20 |
| ALREADY_TESTED | 5 |
| DUPLIKAT | 5 |
| DATA_BLOCKED | 6 |
| NOT_APPLICABLE | 2 |
| PARTIALLY_TESTED | 1 |
| NOT_TESTED | 1 |
| Genuina locked-H0-luckor | 2 |
| **Licensierade tester** | **1** |
| **Totalt genomgångna av 326** | **220** |

---

# G216 — SIGNAL-TO-EXECUTION DECAY (kört 2026-08-17)

Skript `tools/g216_execution_decay.py`, utfall `research_k/g216_execution_decay.json`.
Preregistrerad i Batch 11. Diagnostiskt robusthetstest, inte ett förbättringsförsök.

## Konstruktion

Endast exekveringsdagen ändras. Score, rankning, urval, N=30, schema,
likaviktsåterställning och kostnadsmodell är oförändrade och beräknas ur
beslutsdatum T.

**T+n mäts i handelsdagar i den frysta prisserien**, inte kalenderdagar. Helger
och helgdagar existerar inte i serien, så T+1 är alltid nästa faktiska handelsdag
— över en långhelg är T+1 fyra kalenderdagar senare, vilket är den korrekta
motsvarigheten till en order lagd efter stängning T.

De två frysta motorerna har **olika exitkonvention**, ett befintligt förhållande
som inte fick ändras här. Generaliseringen gjordes därför inuti varje motors egen
konvention, med samma regel i båda: **förskjut båda ändpunkterna (n−1)
handelsdagar framåt.**

| Fönster | entry | exit |
|---|---|---|
| 2020-2026 (`H.execution_engine`) | p(T)+n | p(T_nästa)+n |
| 2014-2019 (`M._bygg_retmap`) | p(T)+n | p(T_nästa)+n−1 |

## Kontroller — samtliga passerade

| # | Kontroll | Utfall |
|---:|---|---|
| 1 | n=1 reproducerar frysta returns_map | **max abs diff 0,0** på 36 120 + 22 910 = **59 030 nycklar**, noll nyckelavvikelser. T+1 är canonical *per konstruktion*, inte per approximation |
| 1b | canonical CAGR | **7,20 % / 31,56 %** exakt, med vol 21,71/17,22 och maxDD −33,50/−19,73 |
| 2 | signalen räknas inte om | rankningen läses ur samma frysta `rankings[dt]` i alla armar; endast `returns_map` byts |
| 3 | identiska namnuppsättningar | **0 avvikelser** i alla armar och båda fönstren; inträden 347/341 och utgångar 317/311 identiska |
| 4 | ingen look-ahead | 0 fall där entry ligger på eller före beslutsdagen, 0 fall där signalen ser pris efter T |
| 5 | kostnader identiska | 20 bp på samma viktomsättning; omsättning 234,1→237,2 % och 196,7→197,4 % |

Omsättningsskillnaden på ~0,3 pp kommer enbart av att viktdriften följer en
något annan prisbana — inte av fler affärer.

## Utfall 2020-2026 (66 paneler)

| Arm | CAGR | Δ mot T+1 | Sharpe | Vol | MaxDD | Oms/år | Byten | Ej exekverbara |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **T+1** | **7,20 %** | — | 0,228 | 21,71 % | −33,50 % | 234,1 % | 664 | 41 / 1 980 |
| T+2 | 7,68 % | **+0,48 pp** | 0,266 | 20,42 % | −30,30 % | 234,1 % | 664 | 42 |
| T+3 | 7,38 % | **+0,18 pp** | 0,274 | 18,75 % | −29,10 % | 235,0 % | 664 | 42 |
| T+5 | 9,84 % | **+2,64 pp** | 0,377 | 20,14 % | −28,65 % | 237,2 % | 664 | 45 |

Bootstrap T+5 − T+1: **+2,64 pp, KI [−1,30, +8,29], t 0,293.** Ej falsifierad.
Stegvis +0,48 / −0,30 / +2,46 — **inte monoton**.

## Utfall 2014-2019 (79 paneler)

| Arm | CAGR | Δ mot T+1 | Sharpe | Vol | MaxDD | Oms/år | Byten | Ej exekverbara |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **T+1** | **31,56 %** | — | 1,703 | 17,22 % | −19,73 % | 196,7 % | 652 | 32 / 2 370 |
| T+2 | 27,76 % | **−3,80 pp** | 1,467 | 17,40 % | −22,17 % | 197,5 % | 652 | 34 |
| T+3 | 27,34 % | **−4,22 pp** | 1,521 | 16,51 % | −16,28 % | 196,7 % | 652 | 34 |
| T+5 | 27,74 % | **−3,82 pp** | 1,591 | 16,03 % | −13,92 % | 197,4 % | 652 | **64** |

Bootstrap T+5 − T+1: **−3,82 pp, KI [−7,26, +2,78], t −0,674.**
Preregistrerad gräns −1,0 pp överskriden → **FALSIFIERAD i detta fönster.**
Stegvis −3,80 / −0,42 / +0,40 — **inte monoton.**

## Decay-profilen — formen är avgörande

Detta är **inte gradvis decay.** I 2014-2019 sker **hela** förändringen i ett
enda steg, T+1 → T+2 (−3,80 pp), och därefter är kurvan platt (−0,42, +0,40).
Ett gradvis signaldecay skulle ge ungefär lika stora steg hela vägen ut till T+5.
Det gör den inte. Det är en **nivåförskjutning vid en enda dag**, inte ett
avtagande.

Och i 2020-2026 finns ingen försämring alls — där är T+1 den **sämsta** av de
fyra armarna.

## De tre observationerna som avgör tolkningen

**1. Tecknet är inte konsistent mellan fönstren.** T+5 är +2,64 pp i det ena och
−3,82 pp i det andra. Det är tvåfönsterkriteriet som faller, precis som för alla
andra prövade mekanismer.

**2. Båda utfallen ligger inuti bruset.** KI:na är [−1,30, +8,29] och
[−7,26, +2,78] — **båda innehåller noll**, |t| är 0,29 och 0,67. Ingendera
skillnaden är statistiskt urskiljbar.

**3. Den preregistrerade gränsen var felkalibrerad — mitt fel.** Jag satte 1,0 pp
i Batch 11 utan att hålla den mot det som redan var känt: placebobandet är
**±2,4 pp** och detektionsgolvet på 66 paneler är **~4 pp**. En gräns på 1,0 pp
ligger alltså långt under den nivå där brus rutinmässigt slår igenom. Domen
"FALSIFIERAD" är därför formellt korrekt men substantiellt oinformativ — gränsen
var i praktiken omöjlig att inte överskrida.

Domen ändras inte i efterhand. Den redovisas som fälld, med anmärkningen att
kriteriet var för hårt satt.

## Tolkning — A / B / C / D

**D: instabil och icke-monoton timingeffekt.**

* **inte A** (robust) i punktskattning — 3,8–4,2 pp i 2014-2019 är för stort för
  att kallas robust, även om det inte är signifikant.
* **inte B** (gradvis decay) — hela förändringen ligger i ett enda dagsteg och
  kurvan är därefter platt. Det är formen som utesluter B, och det är den
  diagnostiskt viktigaste observationen i hela testet.
* **inte C** (systematiskt beroende av T+1-antagandet) — **T+1 är bäst i
  2014-2019 men sämst i 2020-2026.** Hade den kanoniska konventionen varit
  systematiskt smickrande skulle den ha smickrat i båda fönstren. Det gör den
  inte. Det är ett direkt svar på en legitim invändning mot D/F-reparationen,
  som valde T+1 utan att pröva alternativ.
* **D** är kvar: riktningen växlar mellan fönster, profilen är icke-monoton inom
  fönster, och alla differenser ligger i bruset.

**T+5 är inte en förbättring och blir inte en kandidat.** Att T+5 slår T+1 i
2020-2026 är ett utfall inuti ett brusband, med motsatt tecken i det andra
fönstret. Testets riktning var robusthet mot fördröjning, inte val av
exekveringsdag.

## Genomförbarhet — den enda riktade signalen

Antalet innehav som **inte går att exekvera** vid vald dag:

| Fönster | T+1 | T+2 | T+3 | T+5 |
|---|---:|---:|---:|---:|
| 2020-2026 (av 1 980) | 41 (2,07 %) | 42 | 42 | 45 (2,27 %) |
| 2014-2019 (av 2 370) | 32 (1,35 %) | 34 | 34 | **64 (2,70 %)** |

I 2014-2019 **fördubblas** antalet icke-exekverbara innehav mellan T+3 och T+5.
Detta är den enda storhet i testet som rör sig monotont och i samma riktning i
båda fönstren. Den mäter datatäckning i tunna namn, inte avkastning, men den är
den relevanta praktiska varningen: ju längre fördröjning, desto fler positioner
som inte går att fylla alls.

## Fasspridning (deskriptiv, endast T+1)

Ur samma harness, utan någon ytterligare executionvariant:

| Fönster | Kontraktets fas | Alternativ fas | Spann |
|---|---:|---:|---:|
| 2020-2026 | 7,20 % | 4,95 % | **2,25 pp** |
| 2014-2019 | 31,56 % | 28,60 % | **2,96 pp** |

**Kontraktet ligger på den gynnsamma fasen i båda fönstren.** Det bekräftar och
förstorar A1:s STACK_H-fynd (+0,33/+1,44 pp) — för locked H0 är fasfördelen
2,25/2,96 pp. Fasmedelvärdet är 6,08 % respektive 30,08 %.

Anmärkning: den alternativa fasen ombalanserar på panel 0 och 1 i följd,
eftersom första panelen alltid handlar. En panels kanteffekt, ingen betydelse
för storleksordningen.

**Detta får inte användas för att välja fas eller exekveringsdag.** Det är en
kvalificering av två redovisade tal.

## Hur 7,20 % / 31,56 % bör kvalificeras hädanefter

Inga tidigare domar ändras. Men två redovisade tal ska hädanefter citeras med
sitt sammanhang:

> 7,20 % och 31,56 % är punktskattningar i **en cell** av ett rutnät som spänns
> upp av fas och exekveringsdag. Den realiserade spridningen i det rutnätet är
> **2,25–2,96 pp från fas** och **0,5–4,2 pp från exekveringsdag**, och
> kontraktscellen ligger på den gynnsamma fasen i båda fönstren.

Talen ska inte citeras med två decimaler som om de vore egenskaper hos
strategin. De är egenskaper hos strategin *plus* ett godtyckligt val av
startvecka och exekveringsdag. Detta stärker den redan noterade fasövervikten;
det ogiltigförklarar ingen tidigare jämförelse, eftersom alla jämförelser körts
i samma cell för båda armarna.

## Metodlärdom

**En falsifieringsgräns måste hållas mot detektionsgolvet innan den skrivs.** Jag
förregistrerade 1,0 pp för G216 trots att placebobandet ±2,4 pp och
detektionsgolvet ~4 pp var kända sedan tidigare batchar. En gräns under
detektionsgolvet gör ett test oförmöget att skilja effekt från brus i den ena
riktningen och garanterar nästan falsifiering i den andra. **Varje framtida
preregistrering ska explicit ange gränsen i förhållande till placebobandet.**

Andra lärdomen: **profilens form bär mer information än dess nivå.** Att hela
förändringen ligger i ett enda dagsteg och därefter är platt uteslöt "gradvis
signaldecay" på ett sätt som ingen punktskattning eller KI hade kunnat göra.

## Status efter G216

H0 förblir fryst och oförändrad. G97-P oförändrad. Inga följdtester
licensierade. Batch 12 ej påbörjad. Kön är tom.
