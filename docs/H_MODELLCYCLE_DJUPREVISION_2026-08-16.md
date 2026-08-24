# Djuprevision av H-modellernas hela beslutscykel

Datum: 2026-08-16. Omfattning: H0 (Track H), H1 och H2 från fryst data till
beslut, urval, exekvering och utfallsuppföljning. Detta är en revision, inte en
ny modellvariant. Inga lockfiler, journaler eller forwardresultat har ändrats.

## Kort dom

**Signal- och urvalslogiken är enkel och internkonsekvent.** Revisionen fann en
aktiv versionskonflikt i prisbackbonen; den är nu återställd byteidentiskt från
de samtidiga 2026-08-15-backuperna av både prisfil och A-manifest. H0:s fulla
verifiering samt den nya gemensamma preflighten passerar igen. H1/H2:s egna
verifieringssvar är fortfarande snävare än H0:s, så preflighten ska vara ett
obligatoriskt operativt steg före alla tre förseglingar.

H0/H1/H2 är dessutom avsiktligt fullt investerade efter köp: 30 namn à 1/30.
De har ingen marknadsregimregel och ingen fast 10 %-kassa. Det är korrekt enligt
låsen, men innebär också att modellen inte är konstruerad för att aktivt söka
marknadsskydd mellan ombalanseringar.

## Den faktiska beslutskedjan

```text
PIT-priser + PIT-universum
        ↓  (beslutsdatum, endast då känd information)
H0: rank(12 mån momentum) + rank(18 mån momentum)
        ↓
H1: 50 % H0 + 50 % drawdown-resiliens
H2: 50 % H0 + 50 % trend-t-statistik
        ↓
Top 30, lika vikt 3,33 % vardera
        ↓
Beslut var fjärde vecka; nytt urval var åttonde vecka
        ↓
Första observerade handelsstängning efter beslut + 20 bp enkelsidig kostnad
        ↓
Append-only prediktion → exekvering → portföljutfall → 52-v. targetutfall
```

På mellanpanelen hålls föregående innehav. På en ombalanseringspanel ersätts
hela urvalet av aktuell Top-30. Detta ger konsekvent, enkel exponering men
innebär att ingen stop-loss, market-timing eller kassagrind finns i H0/H1/H2.

## Fynd och prioritet

| Prioritet | Fynd | Oönskad följd | Status / nödvändig kontroll |
|---|---|---|---|
| **P0** | H0:s V4-prisfrysning fallerar. Låset förväntar 32 699 306 byte för `validated/prices/prices_validated.json`; aktiv fil är 32 695 623 byte och ändrades 2026-08-15. | Det går inte att bevisa att H0-beslut använder det frysta datalagret. H0 stoppar säkert, men får inte köras framåt i detta tillstånd. | Återställ exakt fryst fil **eller** skapa en uttryckligen ny, separat version/freeze. Ändra aldrig den gamla filen och fortsätt som om låset gällde. |
| **P0** | H1/H2:s `verify` passerar trots H0:s prisfrysfel. | Falsk driftsignal: challenger kan beskrivas som "PASS" medan dess gemensamma H0-bas inte är verifierad. | Operatörsgrind före varje H1/H2-seal måste först köra H0:s fulla freeze-verifiering och stoppa på fel. |
| **P1** | H1/H2 validerar sin inbox väsentligt svagare än H0. De kräver inte `known_at`, upstream-manifest, unika universumnamn, fullständiga roller eller `next_scheduled_trading_date`. | PIT- och exekveringsprincipen kan kringgås av ett formellt giltigt men otillräckligt inboxpaket. | Eftersom challenger-koden är låst: använd en separat, loggad preflight-wrapper med H0:s strikta kontroller; skriv inte om H1/H2-låsen. |
| **P1** | H1/H2 förseglingskod registrerar beslut men saknar H0:s separata append-only exekverings- och utfallshändelser. | Svagare spårbarhet mellan avsiktligt urval, faktiskt pris och uppmätt effekt; lättare att få ett bokfört beslut utan komplett ekonomisk uppföljning. | Skapa en extern operativ journal/protokoll för H1/H2 eller ett nytt versionerat challenger-spår; kalla inte enbart prediktionsfilen för full cykelkontroll. |
| **P1** | Alla kritiska kontroller i forwardkoden använder till stor del Python `assert`. | Körning med `python -O` tar bort kontrollerna. Då kan framtidspriser, fel datum eller fel hash passera. | Operativ regel: kör aldrig med `-O`; preflight ska kontrollera `__debug__ is True`. I nästa version ersätts asserts med explicita fel. |
| **P1** | H0:s kalenderfil är låst men inte läst av motorn; motorn räknar bara `FIRST + 28 dagar`. Kalendern innehåller bl.a. 2026-12-25 som beslutspanel. | En helg-/helgdagspanel kan få ett manuellt angivet exekveringsdatum utan maskinellt bevis att det är första möjliga handelstillfälle. | Lås beslutskalender och exekveringskalender tillsammans; verifiera att det deklarerade datumet är första observerade handelsdag efter beslut. |
| **P1** | Mellan ombalanseringar behålls tidigare innehav även om de saknas i den nya investerbara listan. | Delisting, handelsstopp eller ny icke-investerbarhet kan hamna mellan ”håll” och den ekonomiska terminalhanteringen. | Fördefiniera och logga en tvingande exitgren för ej handlingsbara befintliga innehav, inklusive cash/terminalvärde. Testa den före första skarpa panelen. |
| **P2** | H2 beräknar trend på observationsindex. Det är enligt låset, men saknade handelsdagar komprimerar tid och det finns ingen separat täthets-/stale-price-grind utöver minst 200 observationer. | Trend-t-talet kan bli olika ekonomiska objekt för likvida och glesa aktier, trots samma "52 kalenderveckor". | Övervaka antal observationer och största datumglapp per valt namn; ändra inte H2 utan nytt spår. |
| **P2** | Saknade H1/H2-faktorer får medianrank och kan ändå komma in via hög H0-rank. | En aktie med otillräcklig 52-v. historia får neutral, inte negativ, behandling. Detta är dokumenterat men kan ge oavsiktlig exponering mot kort historik. | Logga faktor-täckning och antal Top-30 med medianimputering per panel; bedöm först efter forwardobservationer. |
| **P2** | Historiska motorer använder inte identisk exekveringsdefinition: 2020–26-motorn använder första pris strikt efter panel, medan 2014–19-motorn använder första pris efter inträde och sista pris på/innan nästa panel. | Fönsterjämförelser blandar delvis signal/regim med exekveringskonvention. Skillnader nära noll ska inte tolkas som modellskillnader. | Märk alla sådana resultat som diagnostiska; en framtida jämförelse måste hålla exekvering konstant innan den avgör promotion. |
| **P2** | Äldre Stack-H-resultat använde clip → renormalisera och kunde bryta 6 %-taket. | Riskkontrollens avsedda effekt uteblev exakt när koncentrationen skulle begränsas. | Åtgärdat endast i separata `STACK_H_REPAIRED_*`-diagnostiker. Inga äldre Stack-H-resultat får användas som deploymentevidens. |
| **P1** | Den historiska H0-stabilitetsmotorn fyllde på saknade universumnamn även på mellanpaneler, medan den förseglade forwardmotorn behåller föregående innehav till nästa 8v-ombalansering. | 21 köp och 21 sälj utanför planerad ombalansering (30 procentenheters kumulativ ensidig turnover) gör den historiska serien till en närliggande, inte exakt, forwardreproduktion. | Historiska resultat märks som diagnostiska. Forwardpreflight stoppar nu ärvda icke-investerbara innehav på mellanpanel i stället för att låta dem passera tyst. |

## Kontroll: ger varje åtgärd den tänkta effekten?

| Lager | Avsedd effekt | Faktiskt resultat enligt kod/revision | Dom |
|---|---|---|---|
| H0 12+18m rank | Fånga uthålliga relativa vinnare | Rang, medianimputering, Top-30 och lika vikt följer låset. Isolerad testsvit passerar. | Logiskt korrekt, men ej operativt redo p.g.a. P0. |
| H1 drawdown-resiliens | Minska vikt på namn med dålig egen prisväg | Faktor blandas 50/50 med H0 och genomförs konsekvent. Saknade data blir neutral rang, inte filter. | Avsedd signal, men behöver striktare indata/preflight. |
| H2 trendstyrka | Föredra jämn statistisk prisbana | OLS-t-stat genomförs enligt låst observationsindex-definition. | Avsedd signal, men likviditets-/glappkänslig. |
| Lika vikt / Top-30 | 100 % enkel, diversifierad aktieexponering | Exakt 30 × 3,33 % efter varje ombalansering. Ingen fast cash. | Ger avsedd exponering; ger **inte** marknadsskydd. |
| 8-veckors urvalsperiod | Begränsa omsättning och brus | Urval byts på varannan panel, hålls däremellan. | Fungerar, men saknar explicit tvingande-exit-gren mellan ombalanseringar. |
| Första pris efter beslut | Undvika look-ahead | H0 kan kontrollera ett deklarerat datum, men bevisar inte själv att datumet är första marknadspris. H1/H2 kontrollerar mindre. | Otillräckligt som ensamt bevis; kräver operativ preflight. |
| Stack H:s SMA-kassa | Dämpa namnspecifik nedtrend | Sänker risk men historiskt inte robust CAGR; tidigare viktgräns var dessutom fel. | Ingen promotion; inte en skyddad komponent i H0/H1/H2. |

## Vad vi vet om ekonomisk adekvans

Det finns inte stöd för en automatiserad bull/bear-gate. Den förregistrerade
K5-regimdiagnostiken fann 0/6 stabila regimsamband: negativa trend-, högvol- och
VIX-stresslägen hade för få paneler för en regel. Den konträra H1-regeln
"positiv bred sexmånaderstrend → cash" testades separat och försämrade CAGR
med 15,61 pp i 2014–19 och 8,66 pp i det senare fönstret.

Det betyder inte att marknadsrisk saknar betydelse. Det betyder att den hittills
testade informationen inte kan avgöra *nästa* period tillräckligt väl för att
motivera cash. H0/H1/H2 ska därför bedömas som fullt investerade
aktieurvalsmodeller, inte som allvädersportföljer.

Den största ekonomiska sårbarheten är koncentration av realiserad avkastning:
H0:s historiska stabilitetsrevision fann att topp fem namn bar cirka 92 % av
aritmetisk överavkastning i full historik. Det är en övervakningsrisk, inte ett
bevis för en ny filterregel. Följ därför framåt: topp-1/top-3-bidrag,
branschkoncentration, faktorimputering, omsättning, faktisk exekveringslagg och
skillnaden mellan planerat och erhållet pris.

### Churn och dyra återköp

H0 säljer inte och köper samma aktie på samma ombalansering: `set`-differensen
gör att ett oförändrat innehav inte handlas. Däremot finns verkliga
ut-och-tillbaka-cykler över flera 8v-ombalanseringar. I 2021--26-serien fanns
130 återköp av tidigare sålda namn; 113 återköptes över tidigare säljpris och
medianpremien var 30,75 %. Det är en reell opportunity-cost-/churnrisk, inte
ett bevis på ett kodfel: momentum får rationellt återköpa ett namn när dess
relativa styrka återkommer. Men en enkel tidsbaserad återköpsspärr har redan
testats och gav inget stöd. En eventuell förbättring måste därför pröva den
distinkta hypotesen "återinträde först efter material poängförbättring", i ett
nytt preregistrerat spår — inte smygas in i H0.

## Rekommenderad ordning före första forwardpanelen

1. **Stoppa och åtgärda P0:** fastställ varför prisfilen ändrades. Återställ
   byteidentisk fryst fil eller besluta en ny, separat och omsluten version.
2. Kör en **gemensam preflight** för H0/H1/H2 som kräver: H0:s fulla
   freeze-verifiering, `__debug__`, hashes, PIT-tidsstämplar, unika tickers,
   prisernas maxdatum ≤ beslut och verifierat första handelsdatum för exekvering.
3. Fördefiniera hantering av delisting/handelsstopp på en mellanpanel och testa
   grenen i en isolerad fixture.
4. Se till att H1/H2 får samma append-only exekverings- och utfallslogg som H0,
   dock som separat operativ kontroll så att deras befintliga lås inte skrivs om.
5. Först därefter: försegla första panelen. Inga nya urvals-, cash- eller
   viktregler ska smygas in för att åtgärda driftbrister.

## Utförda kontroller

- `tools/test_sparh_forward.py`: passerar i isolerad fixture (kalenderfas,
  framtidspris/target-avvisning, no-overwrite, journals hashkedja och
  exekveringsdatum mot deklarerad plan).
- `tools/sparh_forward.py verify`: **FAIL** på ovanstående prisfrysdifferens.
- `tools/spari_forward_challengers.py H1 verify` och `H2 verify`: PASS, men med
  den begränsade verifieringsomfattning som beskrivs i P0/P1.

## Genomförda åtgärder efter revisionen

- Återställde `validated/prices/prices_validated.json` och
  `validated/manifest_sparA.json` från deras byteidentiska 2026-08-15-backuper.
  De matchar V4-frysningen; backupfilerna behölls.
- Lade till `tools/preflight_h_cycle.py`. `verify-locks` kräver aktiv Python
  utan `-O`, H0:s fulla V4/ABC-verifiering och H1/H2:s låshashar. `validate-inbox`
  kontrollerar tidstämplar, hashade roller, upstream-proveniens, unikhet,
  mål-/framtidsfält, prisordning och ärvda oinvesterbara innehav mellan
  ombalanseringar.
- Efter åtgärden passerar både `python3 tools/preflight_h_cycle.py verify-locks`
  och `python3 tools/sparh_forward.py verify`.
