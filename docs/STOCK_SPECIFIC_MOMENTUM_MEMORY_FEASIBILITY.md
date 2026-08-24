# STOCK-SPECIFIC MOMENTUM MEMORY — genomförbarhetsanalys

Datum 2026-08-18 · separat forskningsspår · **inget prediction-test kört**
Reproduktion: `tools/memory_sample_size_audit.py` → `research_k/memory_sample_size_audit.json`
och `research_k/memory_separation_audit.json`

Locked H0 orörd. G97-P orörd. Ingen memory-score byggd. Ingen handelsregel licensierad.

**Dom: DATA_BLOCKED (historikdjup).** Skälet är inte att en datakälla saknas i
världen, utan att båda frysta fönstren har **noll burn-in** och att utvidgningen
bakåt redan är dokumenterad som survivorship-blockerad.

---

## A. Innehåller H0 redan detta minne?

**Nej — i praktiken ingenting alls.** Det är spårets starkaste sida.

H0:s score är `0,5 × pct(mom_12m) + 0,5 × pct(mom_18m)`. Varje komponent är en
punkt-till-punkt-avkastning: **två priser**. Ingen bana, inget tillstånd, ingen
hysteres, inget ägandeminne — locked H0 ombalanserar mekaniskt.

Den enda historik H0 bär är att 18m-fönstret innehåller 12m-fönstret. Skillnaden
kodar månad 12–18, alltså en grovt eftersläpande momentum — inte episodhistorik.

Uppmätt, med antal tidigare avslutade episoder som minnesmått:

| | Spearman mot H0-score | mot H0-rank |
|---|---:|---:|
| 2020-2026 | **+0,126** | −0,124 |
| 2014-2019 | **+0,091** | −0,090 |

Ungefär **1 % delad varians**. Minnet är alltså i allt väsentligt ortogonalt mot
det H0 redan vet. Frågan är genuint distinkt.

Att skilja från detta: rankautokorrelationen 4v = 0,6215 (ledgerpost #22) mäter
att *dagens tillstånd* består. Det är något annat än historik över *tidigare
avslutade* episoder.

---

## B. Överlappande respektive icke-överlappande tidigare tester

### Överlappar INTE — dessa stänger inte frågan

Samtliga mäter formen på den **aktuella** kursbanan, inte tidigare avslutade
episoder. De är precis vad §1 i uppdraget exkluderar:

| # | Begrepp | Utfall |
|---:|---|---|
| 51 | Momentum acceleration | residual-IC byter tecken mellan fönstren |
| 67/68 | Trend efficiency / efficiency ratio | +0,0618 (t 2,59) sent, +0,0014 (t 0,06) tidigt |
| 71–73 | Smoothness / trend noise | svagt stöd, dubbletter |
| 74/75 | Directional consistency / positive-week ratio | teckenbyte på samtliga horisonter |

**Rättelse av min egen tidigare klassificering.** Ledgerpost **#69 Path
dependency** står som `NOT_APPLICABLE — subsumeras av #67 och #71-73`. Det var
förhastat. #67 och #71-73 mäter dagens bana; de säger ingenting om ett bolags
beteende under *tidigare, avslutade* episoder. **#69 ska omklassificeras till
DATA_BLOCKED enligt denna analys**, inte till NOT_APPLICABLE.

### Överlappar — men som POPULATIONSKONTROLL, inte som konkurrent

Detta är den viktiga insikten för §8. Allt vi har mätt om persistens är
**tvärsnittsgenerellt**, aldrig bolagsspecifikt — vilket betyder att vi redan
äger falsifieringsriktmärket, men aldrig har kunnat fylla behandlingsarmen:

| Källa | Populationsbasfrekvens |
|---|---|
| `graduation_m12_to_m52` (#20/21/61) | **368 graduates mot 930 washouts av 1 298 nyinträden = 28 % graduationsgrad** |
| `frekvens_vs_kraft` (#22) | rankautokorrelation 4v = 0,6215, topp-60 |
| `runway_matning` (#5) | band 1–5 varar 9,13 paneler |
| G13/G17 | 97,7 %/95,7 % av sålda namn återhämtar sig; opp_cost negativ på varje horisont |
| Återinträdeskohorten | +6,28 % mot färska namns +1,97 %, t 2,46 — **n = 19** |

Det sista talet är i sig en varning: hela återinträdespopulationen i ett fönster
är 19 observationer.

---

## C. PIT-definition av episod och tillståndsövergång

Byggd enbart på H0:s **egen** gräns. Inga uppfunna prisnivåer.

| Begrepp | Definition |
|---|---|
| STARK state | rank ≤ 30 i H0:s rankning — H0:s egen urvalsgräns |
| SVAG state | rank > 30, eller ej rankbar den panelen |
| Episod | maximal sammanhängande följd av STARK-paneler |
| Episodstart | STARK vid T, SVAG vid T−1 |
| Fortsatt momentum | STARK vid både T−1 och T |
| Försvagning / exit | SVAG vid T, STARK vid T−1 — **här avslutas episoden** |
| Avslutad episod | först vid försvagningspanelen; en pågående episod bidrar med noll |
| Återinträde | en senare episodstart för samma ticker |
| Recoverytid | antal paneler från försvagning till nästa episodstart |

**PIT-regel:** vid panel T får endast episoder vars försvagningspanel ligger
strikt före T räknas. **Kontrollerat explicit: 0 brott** i samtliga fyra
konfigurationer.

**Signal skild från ägande.** Definitionen rör enbart rankning. Ett bolag kan ha
en full episod utan att någonsin ha fått plats bland de 30 innehaven — locked H0
handlar bara varannan panel, så ägande och signaltillstånd är olika saker.

**Hysteres-känslighet.** Locked H0 har ingen hysteres; STACK_H behåller ner till
rank 35. Flyttas gränsen 30 → 35, alltså 17 %:

| | Episoder totalt | Andel topp-30-obs med ≥2 tidigare |
|---|---:|---:|
| 2020-2026, gräns 30 | 444 | 20,9 % |
| 2020-2026, gräns 35 | 528 (+19 %) | 22,7 % |
| 2014-2019, gräns 30 | 445 | 27,9 % |
| 2014-2019, gräns 35 | 502 (+13 %) | 31,9 % |

Episodräkningen rör sig **13–19 %** på en 17-procentig gränsflytt. Definitionen
är alltså materiellt godtycklig i sin kvantitet, om än inte i sin riktning.

---

## D. Kandidatmått och hård deduplicering

De sju kandidaterna kollapsar till två familjer plus en som måste kasseras:

| Kandidat | Behandling |
|---|---|
| A continuation rate · B recovery propensity · E successful re-entry rate | **Samma statistik** — "andel tidigare övergångar som gick bra", mätt vid tre olika övergångstyper. Dedupliceras till **en RATE**. |
| C recovery time · D episode longevity | Båda är **varaktigheter**. Dedupliceras till **en DURATION**. |
| F failure rate | **= 1 − A.** Rent komplement. Stryks. |
| G within-episode drawdown tolerance | Ett **prisbane**-mått inuti episoden. Kollapsar mot vol/MAE och därmed mot G97-P (vol~idio r ≈ 0,99–1,00) och #71-73. **Stryks som konfunderad.** |

### Vald primärkonstruktion, ex ante: **M1 = medellängd på bolagets tidigare avslutade episoder** (paneler)

Motiv: parameterfri, definierad redan vid en enda avslutad episod, direkt
ekonomiskt tolkbar ("det här bolaget brukar hålla starka tillstånd länge"), och
den av de två familjerna som har bäst täckning. RATE-familjen kräver en
observationshorisont för att avgöra om ett återinträde "skulle" ha skett, vilket
både inför en parameter och skapar högercensurering.

**Ingen andra konstruktion väljs.** Sample-size-utfallet nedan gör en andra
meningslös.

### Separationskravet — den avgörande designpunkten

En episod som avslutades nyligen ligger **inuti H0:s egen 18-månaders lookback**
(18 m / 28 dagar ≈ 19,6 ≈ **20 paneler**). Ett minne byggt på den episoden
mäter delvis om dagens momentum, alltså exakt "längre lookback i förklädnad" som
§1 och §12.6 förbjuder.

**Därför krävs: episoden måste vara avslutad före T − 20 paneler.** Utan det
kravet är hypotesen inte den hypotes som ställdes.

---

## E. Sample size — den avgörande mätningen

Fönstren: 2020-2026 har 66 paneler (2021-07-16 → 2026-07-10), 401 tickers.
2014-2019 har 79 paneler (2014-01-01 → 2019-12-25), 290 tickers.

**Noll burn-in.** Priser börjar 2020-01-02 respektive 2012-07-02, och 18m-kravet
gör att första rankbara panel *är* första utvärderingspanel i båda fönstren. Det
finns alltså ingen rankninghistorik före utvärderingsperioden. Minnet kan bara
byggas upp inuti det fönster som testas.

### Episodstruktur

| | 2020-2026 | 2014-2019 |
|---|---:|---:|
| Avslutade episoder totalt | 444 | 445 |
| Episodlängd, median (medel, max) | 2 (4,1 · 29) | 2 (4,8 · 44) |
| Gap mellan episoder, median (medel) | 3 (9,1) | 3 (9,6) |
| Avslutade episoder per ticker, median (q75, max) | **1** (2 · 6) | **1** (2 · 7) |

En full cykel — episod plus gap — är i medeltal **13–14 paneler ≈ ett år**. I ett
femårsfönster utan burn-in hinner medianbolaget alltså med **en** episod.

### Tillgängligt minne vid beslutstillfället, topp-30-kandidater

| Andel med N tidigare avslutade episoder | 2020-2026 | 2014-2019 |
|---|---:|---:|
| **Naivt** (avslutad före T) ≥1 | 46,0 % | 58,5 % |
| **Naivt** ≥2 | 20,9 % | 27,9 % |
| **Separerat** (avslutad före T−20) ≥1 | **17,9 %** | **27,2 %** |
| **Separerat** ≥2 | **8,1 %** | **12,4 %** |
| **Separerat** ≥3 | **2,6 %** | **5,7 %** |
| Unika tickers med ≥2 separerade episoder | **27** | **41** |

Bland paneler ≥ 20, alltså där minne alls kan finnas: ≥2 separerade episoder för
11,6 % / 16,6 % av observationerna.

### Vad detta betyder konkret

> **Per beslutspanel har i genomsnitt 2,4 av 30 kandidater (2020-2026) och 3,7 av
> 30 (2014-2019) ett minne byggt på minst två separerade episoder.**

Man kan inte rangordna 30 namn på ett drag som existerar för 2–4 av dem. Och
"minst två episoder" betyder att en andel bara kan anta värdena 0/2, 1/2 eller
2/2 — precis det degenererade fall §6 varnar för. Populationen med ≥3
separerade episoder, där en frekvens ens börjar bli meningsfull, är **2,6 % / 5,7 %**
av observationerna och vilar på 27 respektive 41 distinkta bolag.

---

## F. Populationsminne mot bolagsspecifikt minne

Metoden är klar och genomförbar — det är bara data som fattas.

Populationsbasfrekvensen ska betingas på **samma aktuella tillstånd**, inte tas
som ett globalt snitt. Konkret: för varje panel och varje rankdecil beräknas
populationens medelvärde av M1 bland namn i samma decil, expanderande och PIT.
Bolagsspecifikt minne är sedan **enbart avvikelsen**:

```
M1_specifik(i,T) = M1(i,T) − M1_population(decil(i,T), T)
```

Endast avvikelsen får gå in i prediction-testet. Är den prediktiva kraften
noll i avvikelsen men positiv i nivån har vi återupptäckt ett generellt
momentum-state, inte bolagsminne. `graduation_m12_to_m52`:s 28 % graduationsgrad
är det färdiga riktmärket.

---

## G. Hierarkisk konstruktion utan parameteroptimering

Krävs — men räddar inte sample size, och det är viktigt att säga rakt ut:
**shrinkage skapar ingen information, den hindrar bara överanpassning.** Bolag
med 0–1 episoder dras helt till populationssnittet och bidrar då med exakt noll
bolagsspecifik signal. Testets effektiva urval förblir de 27 respektive 41
bolagen.

Formen, om den någonsin blir aktuell, är en momentskattare — inte en tunad
parameter:

```
w_i(T) = n_i(T) / (n_i(T) + k(T)),    k(T) = σ²_inom / σ²_mellan
M1_shrunk = w_i · M1_i + (1 − w_i) · M1_population
```

där båda varianserna skattas **expanderande och enbart på paneler < T**. Ingen
gridsökning, inget val av k mot framtida avkastning, k omräknas vid varje panel.

---

## H. Primär preregistrerad hypotes

**G-MEM (förregistrerad, ej licensierad, ej körd).**

Bland aktier med jämförbar aktuell H0-rank predicerar högre `M1_specifik`
— shrinkad medellängd på bolagets tidigare avslutade momentumepisoder, samtliga
avslutade före T−20 — högre framtida avkastning på den icke-överlappande
4-veckorshorisonten, i **båda** fönstren med samma tecken.

Kontroller: aktuell H0-rank (decilbetingat), aktuellt momentumtillstånd
(STARK/SVAG), populationsbasfrekvens per decil. Regel 6 gäller varje horisont
längre än en panel. Regel 8: gränsen ska anges mot placebobandet ±2,4 pp och
detektionsgolvet ~4 pp innan testet skrivs.

---

## I. Falsifieringskriterier

Testet faller om något av följande inträffar:

1. **Populationsfalsifieringen (obligatorisk).** `M1_specifik` — avvikelsen —
   saknar prediktiv kraft medan nivån har den. Då är fyndet ett generellt
   momentum-state.
2. **Teckenbyte mellan fönstren.** Samma kriterium som allt annat i programmet.
3. **Kollaps mot lookback.** Om effekten försvinner när separationskravet T−20
   skärps ytterligare är den längre lookback i förklädnad.
4. **Otillräcklig täckning.** Om andelen kandidater med användbart minne är för
   låg för att rangordna — vilket den **redan är konstaterat vara**.
5. Effekten bärs av ett fåtal bolag: leave-one-out per ticker ändrar tecken.

---

## J. Bedömning: **DATA_BLOCKED**

Inte `ALREADY ANSWERED` — punkt A visar att H0 inte innehåller minnet
(ρ ≈ 0,09–0,13) och punkt B visar att inget tidigare test har mätt bolagsspecifik
historik. Frågan är genuint öppen och genuint distinkt.

Inte `TESTABLE` — kraftanalysen faller på kriterium I.4 innan testet ens byggs.
Med separationskravet har **2,4 av 30 kandidater per panel** ett minne på minst
två episoder, buret av **27 respektive 41 distinkta bolag**. En tvärsnittsrankning
på ett drag som existerar för 8 % av kandidaterna kan inte producera ett tolkbart
IC, och shrinkage flyttar inte den gränsen.

**Blockeringens natur.** Detta är ett **historikdjupsproblem**, inte en saknad
datakälla. Båda fönstren har noll burn-in därför att 18m-lookbacken förbrukar
exakt den historik som finns före första panelen. Det som skulle krävas är
rankninghistorik **före** utvärderingsfönstren — och den vägen är redan
dokumenterad som stängd i `H0_HISTORICAL_UNIVERSE_RECOVERY_2010_2019.md`:
**SURVIVORSHIP-BLOCKERAT**. Officiella Nasdaq-filer finns i världen men inte i
projektet som immutable RAW, och prisarkivet saknar en materiell del av de
avnoterade Main Market-instrumenten.

Spåret ansluter därmed till den befintliga datauppdragslistan i ledgerns avsnitt
om dataarbete. Det öppnas av **ett** uppdrag: ett survivorship-försvarbart
universum plus prisarkiv för 2010–2013, vilket skulle ge 2014-2019-fönstret
cirka 26 paneler burn-in och ungefär fyrdubbla andelen kandidater med användbart
separerat minne.

**Vad som INTE ska göras under tiden:** inget test på naiva episoder (utan
T−20-separation), eftersom det mäter H0:s egen lookback igen; ingen memory-score;
ingen sänkning av separationskravet för att få upp täckningen. Det sista vore att
välja en definition efter dess datatäckning.
