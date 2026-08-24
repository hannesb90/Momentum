# Spår G – falsifiering av V4:s exekverbara champion

Datum: 2026-08-09  
Slutklassificering: **B — CHAMPION LOVANDE MEN EJ BEKRÄFTAD**

## Slutsats

V4-championen överlever G utan ny data-/implementationsblockerare. Den visar en
historiskt stabil förbättring i cross-sectional IC mot ren 12m och positiv total
excess i båda möjliga 8v-faserna, efter varje leave-one-ticker-out-test, utan
terminalinstrument och vid 100 bp kostnad.

Den klarar däremot inte kraven för **A — robust stödd**. Portföljexcessen är
koncentrerad: Top-5 förklarar 96,8 % av aritmetisk excess och leave-top-5 lämnar
bara 0,50 % excess CAGR. Den alternativa fasens leave-top-3-excess är bara
0,32 %, mer än hälften av blockexcessen uppstår i 2025 H2, 98,2 % av holdings
har overifierad membership och bootstrapintervallet för CAGR-förbättringen mot
12m korsar noll. Det finns ingen untouched forward-panel efter V4-frysningen.

Resultatet klassas inte som C eftersom ΔIC är positivt i bootstrap, ingen enskild
ticker förklarar resultatet, båda faserna har positiv total excess och championen
är tydligt mindre koncentrationsskör än den rena 12m-baslinjen.

25,29 % är ett historiskt backtestutfall, inte förväntad framtida CAGR.

## G0 hard gate

| Kontroll | Resultat |
|---|---|
| V4 freeze SHA256 | PASS: `6716e083…d7f5c3d` |
| Freeze paths/bytes/hash/räkningar | 43/43 PASS |
| A/B/C | 13/13 PASS |
| D reproduktion | 8/8 byte-identisk |
| F reproduktion | 15/15 byte-identisk |
| Äldre + nya regressioner | 9/9 PASS |
| Fysisk future-data-ablation | 35 700 ekonomiposter; ranking/holdingbeslut identiska |
| Exekverade championtrades | 276, samtliga efter decision date |
| 60 stängda-marknadsfall | PASS, nästa faktiska handelsdatum |
| Target-/terminalretroaktiv selection | inga träffar |
| Alternativ executionvariant | ingen testad |

G0 passerade innan G1+ kördes.

## Fryst referens och 12m

| Mått | 12m | Champion | Skillnad |
|---|---:|---:|---:|
| Mean IC52 | 0,1326 | **0,1555** | +0,0229 |
| Top-30 IC52 | −0,0434 | **−0,0250** | +0,0184 |
| CAGR | 18,67 % | **25,29 %** | +6,62 pp |
| Excess CAGR | 8,60 % | **15,21 %** | +6,62 pp |
| Sharpe excess | 0,687 | **1,379** | +0,692 |
| MaxDD | −12,77 % | **−4,43 %** | +8,34 pp |
| Turnover | 0,297 | **0,196** | −0,101 |

Top-30 IC är fortfarande negativ. Förbättring betyder alltså mindre negativ
Top-30-ranking, inte positiv toppranking över hela samplet.

På delmängden med komplett 18m är mean IC 0,1569 mot 0,1330 för 12m. Resultatet
skapas därför inte av den frysta missingregeln.

## Tidsblock

| Block | Mean IC | Top-30 IC | Excess CAGR | Andel absolut blockexcess |
|---|---:|---:|---:|---:|
| 2024 H1 | 0,226 | +0,026 | +18,41 % | 22,1 % |
| 2024 H2 | 0,104 | −0,123 | +4,89 % | 10,0 % |
| 2025 H1 | 0,139 | +0,028 | +10,51 % | 15,6 % |
| 2025 H2 | 0,188, endast en observerbar IC-dag | +0,034 | +28,25 % | 52,3 % |

Alla fyra block har positiv portföljexcess, men mer än hälften av absolut
blockexcess kommer från 2025 H2 där endast en full 52v-target är observerbar.

## 8v rebalancefas

| Fas | CAGR | Excess CAGR | Sharpe | MaxDD | Leave-top-3 excess |
|---|---:|---:|---:|---:|---:|
| Fryst fas 0 | 25,29 % | 15,21 % | 1,379 | −4,43 % | +4,57 % |
| Fas 1 | 20,51 % | 10,44 % | 1,038 | −11,81 % | +0,32 % |

Minimum/median/mean/maximum CAGR är 20,51/22,90/22,90/25,29 %. Championfasen
är bäst av två. Absolut excess överlever, men koncentrationsrensad excess är nära
noll i den andra fasen.

## Tickerkoncentration

| Ablation | Namn | Andel aritmetisk excess | Kvarvarande excess CAGR |
|---|---|---:|---:|
| Top 1 | NELLY | 29,9 % | +10,49 % |
| Top 3 | NELLY, LUG, ATIC | 68,9 % | +4,57 % |
| Top 5 | + SANION, OVZON | 96,8 % | +0,50 % |
| Top 10 | plus AMBEA, AVARDA, HOFI, RAY-B, SAAB-B | 149,0 % | −6,64 % |

Samtliga leave-one-ticker-out-körningar behåller positiv excess. Sämst är att
utelämna NELLY: 10,49 % excess CAGR. Problemet är således en liten grupp om
fem–tio tickers, inte ett enda namn.

Ren 12m är ännu mer koncentrerad: leave-top-3 ger −1,97 % excess och Top-3
förklarar 119,9 % av dess aritmetiska excess. Championen förbättrar robustheten
relativt 12m men når inte bred absolut robusthet.

## Sektor och universum

Historiskt versionerad PIT-sektordata saknas. Dagens `sectorId` har inte
backcastats; sektortestet är därför ej genomförbart.

Large/Mid/Small- och likviditetssegment saknas också i PIT-form. Av championens
780 holdingrader har endast 14, eller 1,8 %, `membership_verified=True`. 98,2 %
ligger i den dokumenterat okända membershipdelen. Detta bevisar inte läckage men
gör universumgeneraliserbarheten svag.

## Terminaler

24 verifierade terminalinstrument rankas och åtta ägs: ABLI, CALTX, CCOR-B, CS,
DORO, NPAPER, PROB och RESURS. Alla har selection före terminal och verifierad
post-entry hantering.

| Diagnostik | CAGR | Excess CAGR | Sharpe | MaxDD |
|---|---:|---:|---:|---:|
| Inklusive terminaler | 25,29 % | 15,21 % | 1,379 | −4,43 % |
| Utan terminaler | 25,05 % | 14,98 % | 1,314 | −4,83 % |

Terminalinstrument förklarar inte resultatet och terminalförluster censureras inte.

## 18m missing och ties

* 215/9 108 beslutsposter saknar äkta 18m: 2,36 %.
* 0/780 championholdings saknar 18m.
* Inga missingnamn ligger kring rank 25–35.
* Top-30-cutoff har en unik score på 25/26 datum och två ties på ett datum.

Ingen systematisk missing-/tie-fördel hittades.

## Kostnadsstress

| Ensidig kostnad | CAGR | Excess CAGR | Sharpe | MaxDD |
|---|---:|---:|---:|---:|
| 0 bp | 25,91 % | 15,84 % | 1,424 | −4,25 % |
| 20 bp | 25,29 % | 15,21 % | 1,379 | −4,43 % |
| 40 bp | 24,67 % | 14,59 % | 1,333 | −4,71 % |
| 60 bp | 24,05 % | 13,97 % | 1,287 | −4,98 % |
| 100 bp | 22,81 % | 12,74 % | 1,190 | −5,52 % |

Beräknad break-even är cirka 534 bp per registrerad ensidig turnover. Slutsatsen
är inte känslig för det preregistrerade intervallet 0–100 bp.

## Benchmark

Benchmark använder samma targetfria decision universe och samma post-decision
execution. Oberoende återberäkning av varje period avviker högst `6,94e-18`.
Benchmark-CAGR är 10,07 %. Benchmark debiteras ingen tradingkostnad, vilket gör
den starkare och inte artificiellt svagare.

## Tidsberoende block-bootstrap

10 000 moving-block-drag, tre paneldatum per block:

| Estimat | 95 % intervall | P(positiv) |
|---|---:|---:|
| Mean IC | 0,127–0,183 | 100,0 % |
| ΔIC mot 12m | +0,005–+0,041 | 99,5 % |
| Periodexcess | −0,03–+1,47 % | 97,1 % |
| Sharpe | −0,038–2,508 | 97,1 % |
| ΔCAGR mot 12m | −7,09–+20,63 pp | 84,3 % |
| Δ periodexcess mot 12m | −0,45–+1,45 % | 83,7 % |
| Leave-top-3 periodexcess | ungefär −0,75–+0,73 % | 51,3 % |

IC-förbättringen har klart bättre statistiskt stöd än portföljförbättringen.
Samplet är endast 20 targetobserverbara IC-datum och 26 portföljperioder.

## Untouched forward

Paneler till och med 2026-07-10 fanns före V4-frysningen 2026-08-09 och kan inte
retroaktivt betraktas som untouched. Antal förseglade paneler strikt efter V4: 0.

**CHAMPION HAR INTE ÄNNU VERIFIERATS PÅ TILLRÄCKLIG UNTOUCHED FORWARD-DATA.**

Forwardprotokollet är aktivt för framtida paneldatum men inga historiska
predictions får skrivas om.

## Slutlig adversarial review

Inga nya fel hittades i targetseparation, PIT/as-of, post-decision execution,
terminalbokföring, adjusted close, holdings persistence, kalenderhantering,
turnover/kostnad enligt fryst konvention, benchmark eller entity-resolution-
beroendet. Portföljperioderna är icke-överlappande 4v-perioder; IC använder
överlappande 52v-targets och dess lilla sample redovisas explicit.

Kvarvarande negativa fynd är koncentration, periodberoende, membership-osäkerhet,
negativ Top-30 IC, bred statistisk osäkerhet för portföljförbättringen och avsaknad
av verklig forwarddata. De är inte reparerade eller optimerade bort.

## Slutbesked

**B — CHAMPION LOVANDE MEN EJ BEKRÄFTAD**

Championkonfigurationen är oförändrad. Nästa steg är förseglad forwardvalidering,
inte mer historisk optimering.
