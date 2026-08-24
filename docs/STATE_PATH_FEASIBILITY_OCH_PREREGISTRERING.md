# MOMENTUM STATE, PATH & STOCK-SPECIFIC MEMORY — feasibility och förregistrering

Datum 2026-08-18 · **inget prediction-test kört** · locked H0, hysteres och G97-P orörda
Reproduktion: `tools/state_path_feasibility.py` → `research_k/state_path_feasibility.json`,
`research_k/state_path_redundans.json`

**Regel 5 körd** mot `research_k/*.json` och `docs/*.md`: inga nya artefakter sedan
memory-feasibility-auditen. Inga nya bindande beslut.

**Sammanfattad dom:** Lager B (population path) är **TESTABLE**. Lager C
(stock-specific) är **PARTIALLY TESTABLE** och blir i praktiken populationsdriven
efter shrinkage. MEM-F **dedupliceras bort**. Den viktigaste enskilda upptäckten är
en inversion som talar emot spårets premiss — se punkt I.

---

## A. H0 INFORMATION AUDIT

Verifierat mot faktisk kod (`derive_h0_scores`, `h1419_motor.momentum`,
`H0_LOCK.json`):

```
score(i,T) = 0,5 · pct(mom_12m(i,T)) + 0,5 · pct(mom_18m(i,T))
mom_Xm(i,T) = P(i,T) / P(i,T−X) − 1
```

H0:s hela informationsmängd per bolag och panel är alltså **fyra priser**:
P(T), P(T−12m), P(T−18m) — tre priser, samt tvärsnittet för percentileringen.
Saknad score → tvärsnittsmedian. Ingen bana, ingen historik, inget tillstånd.

| Lager | Vet H0 detta? |
|---|---|
| CURRENT STATE | **Ja** — score och rank är precis detta |
| PATH TO STATE | **Nej** — vägen mellan de tre prispunkterna är osynlig |
| STATE DURATION | **Nej** — H0 har inget tillståndsbegrepp och ingen minnesvariabel |
| STATE TRANSITIONS | **Nej** |
| STOCK-SPECIFIC HISTORY | **Nej** |
| PORTFOLIO OWNERSHIP | **Nej** i locked H0 — ingen hysteres, ingen retention. Ombalansering är mekanisk varannan panel |

**Viktig reservation som begränsar hela spåret:** 12m och 18m är *långa* fönster.
En bana som utspelats de senaste 12–18 månaderna är inte osynlig för H0 — den är
inbakad i slutpunkterna. H0 vet inte *formen*, men den vet *nettoresultatet* av
formen. Det är därför redundans, inte look-ahead, som är den verkliga faran här,
precis som uppdragets §10 säger. Punkt I kvantifierar den.

---

## B. PREVIOUS-EVIDENCE MAP

### Vad som redan är besvarat och därför inte får återöppnas

| Post | Fråga som redan är besvarad | Konsekvens här |
|---|---|---|
| **#44 Short-term reversal** | ALREADY TESTED — **nivå 2 nådd, nivå 4 misslyckad**. Band 1-5 fore_4v +10,72 % → framåt +0,21 %; band 26-30 +3,98 % → +0,87 %. Replikerar i båda fönstren. Exploatering 0/8 | **Rankförändring över korta horisonter (ΔRank) ÄR detta.** Får ej vara primär path-variabel |
| #43 Intermediate momentum | 12-2/12-7 skip monotont sämre i båda fönstren | ingen skip-variant |
| #20/21/61 Winner/momentum/trend persistence | `graduation_m12_to_m52` 368 graduates / 930 washouts = **28 % graduationsgrad** | **populationsbasfrekvens för MEM-C** |
| #22 Rank persistence | autokorrelation 4v = 0,6215, topp-60 | populationsbasfrekvens för state-persistens |
| #5 Incumbency / runway | band 1-5 varar 9,13 paneler | överlappar time-in-state delvis |
| #16 Re-entry cost | stämplade återinträden replikerar EJ (t 2,46 sent, t 0,33 tidigt) | re-entry stängd som egen fråga |
| G13/G17 | 97,7/95,7 % återhämtar sig; opp_cost negativ på varje horisont; "fortsatt förlorare" 54,5/48,7 % med opp_cost −17,0/−19,1 % | **detta ÄR MEM-F, redan mätt** |
| G97/G97-P | vol ~ idio r ≈ 0,99–1,00; attribution helt undvikande | vol måste kontrolleras, se punkt I |
| DD20, milstolpar, tidsstopp, re-entry-block | INGET/SVAGT STÖD; DD20 träff 44,5 % | inga drawdown-baserade exitregler |
| #67/68, #71-73, #74/75, #51 | trend efficiency, smoothness, directional consistency, acceleration — alla mäter **dagens bana** | kontrollvariabler, ej testvariabler |

### Vad som är genuint ortogonalt

| Post | Status | Kommentar |
|---|---|---|
| **#64 Trend age** | **NOT_TESTED** | Den enda helt oprövade posten i familjen. Motsvarar time-in-state |
| #65 Trend duration | DUPLIKAT av #64 | — |
| #17 Trend resumption | PARTIALLY_TESTED, **MEDIUM** | mätt mot STACK_H/waterfill, inte som betingad övergångssannolikhet |
| #69 Path dependency | DATA_BLOCKED (omklassificerad 2026-08-18) | den post detta spår angriper |

**Den avgörande distinktionen:** #64 har aldrig testats som *direkt prediktor av
avkastning* och inte heller som *modifierare av övergångssannolikhet*. Uppdragets
§6 kräver att dessa hålls isär — här väljs den senare formen, vilket är den som
inte överlappar #20/21/61.

---

## C. STATE-SPACE — minsta ekonomiskt motiverade

Härledd enbart ur H0:s egen urvalsgräns. Inga uppfunna nivåer.

| State | Definition | Motiv |
|---|---|---|
| **S** | rank ≤ 30 | H0:s **egen** urvalsgräns |
| **N** | rank 31–60 | samma gräns × 2, den enda icke-godtyckliga multipeln |
| **W** | rank > 60 | resten |
| — | ej rankbar denna panel | hanteras som frånvaro, ej som state |

Tre states, nio möjliga övergångar. Medvetet grovt: fler states ger sparse cells
och forskarfrihetsgrader (§4). Ingen state definieras på pris, volatilitet eller
drawdown — allt sådant är kontrollvariabler, inte tillstånd.

**Signal skilt från ägande (§16):** states byggs över **hela** PIT-universumet
(401 respektive 290 tickers), inte över tidigare ägda. Ett bolag kan ha en full
S-episod utan att någonsin ha ägts, eftersom locked H0 handlar varannan panel.

---

## D. PATH REPRESENTATION — två variabler, båda förregistrerade

| Variabel | Definition | Motiv för valet |
|---|---|---|
| **TIS** | time-in-state: antal sammanhängande paneler i nuvarande band | ren varaktighet; motsvarar #64, den enda oprövade posten |
| **DR2** | rankförändring över 2 paneler | 2 paneler = **en full H0-rebalanscykel**, härlett ur H0:s eget schema |

Inget mer. Ingen feature-sökning, ingen indikatorbank, inga trösklar valda på
utfall.

**DR2 dedupliceras till kontrollvariabel, inte testvariabel.** Rankförändring
över korta horisonter är ekonomiskt samma information som #44 short-term
reversal, vilken redan är på nivå 2 med replikerad prediktion och misslyckad
exploatering. Att testa DR2 som ny primär signal vore att återöppna en stängd
hypotes under nytt namn — förbjudet enligt §23.

**TIS blir därmed den enda primära path-variabeln.**

---

## E. POPULATION TRANSITION MAP — PIT-skattning

Vid varje panel T skattas övergångsmatrisen **expanderande** på paneler < T:

```
P̂(band_{T+1} = b' | band_T = b, TIS-hink, panel < T)
```

TIS-hinkar förregistrerade: `1 | 2-3 | 4-7 | 8-13 | 14+`. Fem hinkar, gränser
satta som ungefärliga dubbleringar — inte valda på utfall.

Uppmätta cellstorlekar i S-bandet (hela fönstret; PIT-skattningen har mindre
celler tidigt):

| TIS-hink | S 2020-2026 | S 2014-2019 | N 2020-2026 | N 2014-2019 |
|---|---:|---:|---:|---:|
| 1 | 474 | 475 | 993 | 1 065 |
| 2–3 | 482 | 533 | 710 | 869 |
| 4–7 | 479 | 593 | 246 | 370 |
| 8–13 | 399 | 475 | **30** | **66** |
| 14+ | 146 | 294 | **1** | **0** |

**S-bandet har inga sparse cells. N-bandet har det vid TIS ≥ 8.** Därför
förregistreras att N-bandets TIS toppas vid hinken `4-7`; högre hinkar slås ihop.

---

## F. STOCK-SPECIFIC MEMORY ovanpå populationen

Hierarkin är obligatorisk och shrinkage är en momentskattare, inte en tunad
parameter:

```
w_i(T) = n_i(T) / (n_i(T) + k(T)),   k(T) = σ²_inom / σ²_mellan
p̂_i(T)  = w_i · p_i(T) + (1 − w_i) · p_population(cell, T)
```

Båda varianserna skattas expanderande på paneler < T. Ingen gridsökning, k
räknas om vid varje panel. Ett bolag utan historik får w = 0 och bedöms helt av
A+B — stock-specific memory är en modifierare, aldrig ett krav (§3).

**Memory decay (§14) införs INTE i första testet.** Motivet är ex ante: den
förregistrerade konstruktionen ska vara så enkel som möjligt, och varje
halveringstid är en parameter som skulle behöva väljas. Decay får övervägas först
om populationslagret visar signal.

---

## G. SAMPLE SIZE — omräknat på transitionsnivå

Detta är den centrala omprövningen enligt §22, och den **upphäver den gamla
domen för populationslagret**.

| | 2020-2026 | 2014-2019 |
|---|---:|---:|
| Paneler / tickers | 66 / 401 | 79 / 290 |
| Rankobservationer | **23 293** | **21 896** |
| Transitioner | **22 884** | **21 604** |
| State-runs | 2 502 | 2 512 |
| Observationer per ticker, median | 66 | 79 |
| Transitioner per ticker, median | 65 | 78 |

### Övergångsmatriser

| | S→S | S→N | S→W | N→S | N→N | N→W | W→S | W→N | W→W |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2020-2026 | 1 506 | 353 | 81 | 348 | 987 | 606 | 95 | 610 | 18 298 |
| 2014-2019 | 1 895 | 363 | 80 | 373 | 1 305 | 660 | 72 | 672 | 16 184 |

P(S→S) = **77,6 % / 81,0 %.** Konsistent mellan fönstren.

### Time-in-state i S

Median **4 paneler**, kvartiler 2 och 8–9, max 29/44. Reell variation.

### Pullback/recovery, PIT-lösta (H = 13 paneler)

| | 2020-2026 | 2014-2019 |
|---|---:|---:|
| Lösta events | **361** | **369** |
| Recovery | 165 (**45,7 %**) | 188 (**50,9 %**) |
| Ingen recovery | 196 | 181 |
| Censurerade (ej lösta) | 83 | 76 |
| Per ticker, median (max) | 2 (5) | 2 (7) |
| Tickers med ≥1 löst | 199 | 167 |
| **Tickers med ≥3 lösta** | **44** | **52** |

### Täckning per beslutspanel — jämförelsen som avgör

| | Gamla M1-designen | TIS | DR2 |
|---|---:|---:|---:|
| Av 30 topp-kandidater per panel | **2,4 / 3,7** | **22,8 / 24,0** | **29,1 / 29,2** |

Path-representationen är alltså definierad för **tre fjärdedelar till hela**
tvärsnittet, mot en tjugondel för episodkonstruktionen. Den gamla
DATA_BLOCKED-domen gällde episodenheten och generaliserar inte hit.

**Men Lager C står kvar mot samma vägg vid en annan enhet:** 44 respektive 52
tickers har ≥3 lösta pullbacks. En bolagsspecifik recovery-frekvens från två
observationer kan bara anta 0/2, 1/2, 2/2.

---

## H. DEPENDENCE HANDLING

**Rå observationsräkning får aldrig redovisas som oberoende information.**

| Nivå | Rått antal | Ärlig effektiv enhet |
|---|---:|---|
| Transitioner | 22 884 / 21 604 | **2 502 / 2 512 state-runs** |
| Kluster | — | 399 / 290 tickers |
| Pullback-events | 361 / 369 | 199 / 167 tickers |

En sammanhängande S-period på 29 paneler ger 28 S→S-transitioner, men **en**
informationsenhet om trendens uthållighet. Förregistrerad inferens:
**cluster-robusta standardfel på ticker** som primärt, plus **block bootstrap
med 13-panelsblock och 2 000 dragningar** som projektstandard. Regel 6 gäller
varje horisont längre än en panel.

### Kraftanalys före testet (projektregel)

| Test | Effektiv n | Detekterbar skillnad vid t = 3 |
|---|---:|---|
| MEM-C, kontinuationsfrekvens (basnivå ~78–81 %) | ~450 S-runs | **≈ 12 pp** |
| MEM-R, recoveryfrekvens (basnivå ~46–51 %) | ~250 klustrade events | **≈ 16–19 pp** |

Detta är stora effekter. Testen kan alltså bara upptäcka en grov skillnad, aldrig
en subtil. Det ska stå i förregistreringen enligt Regel 8, inte upptäckas efteråt.

---

## I. CONFOUNDER PLAN — och spårets viktigaste fynd

Inom S-bandet, alltså betingat på tillståndet:

| | Spearman(TIS, H0-score) | Spearman(TIS, H0-rank) |
|---|---:|---:|
| 2020-2026 | **+0,523** | −0,512 |
| 2014-2019 | **+0,482** | −0,468 |

**Ungefär 25 % delad varians.** Detta är en inversion mot det gamla
memory-spåret och den bör läsas noga:

> Det minnesmått som hade **god täckning** (TIS) är **starkt redundant** med det
> H0 redan vet. Det minnesmått som var **ortogonalt** (episodhistorik, ρ ≈ 0,10)
> hade **obefintlig täckning**.

Mekanismen är enkel: för att stanna i topp-30 i fjorton paneler måste 12m- och
18m-momentum ha varit starkt hela tiden — och det är precis vad score mäter.
Time-in-state är till en fjärdedel en omskrivning av H0:s eget lookback-fönster.

Det upphäver inte hypotesen — 75 % av variansen är fri — men det gör
**residualisering obligatorisk**, inte valfri. Konkret: TIS ska residualiseras
mot score inom panel innan den används, och testet ska rapportera både rå och
residualiserad effekt.

Övriga obligatoriska kontroller, samtliga tillgängliga: aktuell H0-score och
rank (deciler inom panel), `vol_52w` (G97:s lärdom — "historiskt stora
recoveries" kan vara hög volatilitet i förklädnad; vol ~ idio r ≈ 0,99–1,00),
aktuell drawdown, DR2 som proxy för #44, samt trend efficiency/smoothness/
acceleration som redan är mätta.

---

## J. PRIMARY HYPOTHESIS — current-state sufficiency null

**H0-SUFFICIENCY NULL (förregistrerad, ej licensierad, ej körd):**

> Betingat på aktuell H0-score-decil inom panelen bär time-in-state ingen
> inkrementell information om nästa panels tillstånd.

Formellt, för observationer i state S vid panel T:

```
P(band_{T+1} = S | score-decil, TIS) = P(band_{T+1} = S | score-decil)
```

Utfallet är **nästa panels tillstånd**, inte avkastning. Det är avsiktligt:
horisonten är exakt en panel, så Regel 6 utlöses inte, ingen kostnadsmodell
behövs, och testet kan inte omärkligt glida till nivå 4.

Struktur vald **före** och inte efter resultat: `established` = TIS-hink 8-13
eller 14+, `emerging` = TIS-hink 1. Mellanhinkarna redovisas men ingår inte i
kontrasten.

---

## K. FALSIFICATION

**Population path-signal räknas som funnen endast om samtliga gäller:**

1. Skillnaden i kontinuationsfrekvens mellan `established` och `emerging`
   överstiger **12 pp** (kraftgolvet från punkt H) — Regel 8-gränsen anges alltså
   mot detektionsgolvet, inte godtyckligt.
2. Samma tecken i **båda** fönstren.
3. Effekten överlever **residualisering av TIS mot score inom panel**. Faller den
   här har vi återupptäckt H0:s eget lookback-fönster.
4. Effekten överlever kontroll för `vol_52w` och DR2.
5. Cluster-robust t på ticker ≥ 3, och block bootstrap-KI utesluter noll.

**Stock-specific memory räknas som funnet endast om, utöver 1–5:**

6. Avvikelsen `p_i − p_population(cell)` har egen prediktiv kraft när
   populationscellens nivå redan är kontrollerad.
7. Effekten kvarstår vid leave-one-ticker-out — den får inte bäras av ett fåtal
   bolag.

**Tre utfall är alla legitima och likvärdigt värdefulla (§12):**
A ingen path-information → spåret faller · B populationssignal men inget
bolagstillägg → state-modell möjlig, stock-specific faller · C båda.

---

## L. TARGET SEPARATION

| Target | Enhet och sample | Överlapp | Dom |
|---|---|---|---|
| **MEM-C** kontinuation | 1 940 / 2 338 S-övergångar, ~450 effektiva runs | #20/21/61 ger basfrekvensen 28 % graduation; **nytt är betingningen på TIS = #64** | **TESTABLE** |
| **MEM-R** recovery | 361 / 369 lösta pullbacks, 199/167 tickers | #17 trend resumption PARTIALLY; G13/G17 mätte utfall men inte betingad övergångssannolikhet | **TESTABLE** (population), **PARTIALLY** (stock-specific) |
| **MEM-F** failure | 196 / 181 no-recovery | **Exakt komplement till MEM-R** i ett binärt tillståndsutfall | **DEDUPLICERAS BORT** |

MEM-F kan bara bli distinkt om "breakdown" definieras på avkastning i stället för
tillstånd — och den mätningen är redan gjord: G13/G17:s "fortsatt förlorare",
54,5 % / 48,7 % av utgångarna med opportunity cost −17,0 % / −19,1 %. Att köra om
den under namnet MEM-F vore att återöppna en besvarad fråga.

---

## M. DATA VERDICT

| Lager | Dom | Grund |
|---|---|---|
| **A — current H0 state** | kontrollvariabel | fullständigt tillgänglig |
| **B — population path/state** | **TESTABLE** | 22 884 / 21 604 transitioner, 2 502 / 2 512 effektiva runs, TIS definierad för 22,8/24,0 av 30 kandidater per panel, inga sparse cells i S |
| **C — stock-specific memory** | **PARTIALLY TESTABLE** | 199/167 tickers har ≥1 löst pullback men bara **44/52 har ≥3**. Efter förregistrerad shrinkage kommer nästan all vikt att ligga på populationen. Kan köras, men utfallet är på förhand nära givet |
| MEM-F | **ALREADY ANSWERED** | G13/G17 |
| DR2 som primär signal | **ALREADY ANSWERED** | #44, nivå 2 nådd, nivå 4 misslyckad |

Den gamla DATA_BLOCKED-domen står kvar för sin egen konstruktion — fullständigt
avslutade episoder med T−20-separation och M1 = episodlängd. Ingen sänkning av
den gränsen föreslås här; enheten är en annan, inte gränsen.

---

## N. NEXT TEST — en (1) minimal informationstestkörning

**G-PATH-1 — TIME-IN-STATE SUFFICIENCY (nivå 2, population only). EJ KÖRD.**

* **Population:** samtliga (ticker, panel) i state S, hela PIT-universumet.
  Ägande spelar ingen roll.
* **Behandling:** TIS-hink, `established` (8+) mot `emerging` (1).
* **Kontroll:** H0-score-decil inom panel. Sekundärt `vol_52w` och DR2.
* **Utfall:** band vid T+1 = S eller inte. En panel, ingen överlappning.
* **Inferens:** cluster-robust på ticker; block bootstrap 13 paneler, 2 000
  dragningar.
* **Krav:** ≥ 12 pp skillnad, samma tecken i båda fönstren, överlever
  residualisering mot score.
* **Vad som INTE ingår:** ingen memory-score, ingen stock-specific komponent,
  ingen avkastning, ingen portfölj, ingen kostnad, ingen HMM, ingen ML.

Faller G-PATH-1 stängs hela spåret på nivå 2 och Lager C behöver aldrig köras.
Håller den licensieras Lager C som separat andra steg — inte automatiskt.

**Körs inte. Väntar på licens.**

---

# G-PATH-1 — RESULTAT (kört 2026-08-18)

`tools/g_path_1_time_in_state.py` → `research_k/g_path_1_results.json`,
`research_k/g_path_1_robusthet.json`

**Klassificering: NO INCREMENTAL PATH INFORMATION.**
Current-state sufficiency **stöds**. Spåret stängs på nivå 2.

## Rådifferensen ser överväldigande ut

| 2020-2026 | obs | **runs** | tickers | P(S→S) | P(→N) | P(→W) | **medianrank** |
|---|---:|---:|---:|---:|---:|---:|---:|
| EMERGING (TIS 1) | 463 | 463 | 220 | 0,5961 | 0,3413 | 0,0626 | **24** |
| ESTABLISHED (TIS ≥8) | 538 | **83** | 75 | 0,8569 | 0,1115 | 0,0316 | **9** |

| 2014-2019 | obs | **runs** | tickers | P(S→S) | P(→N) | P(→W) | **medianrank** |
|---|---:|---:|---:|---:|---:|---:|---:|
| EMERGING | 469 | 469 | 192 | 0,6525 | 0,3028 | 0,0448 | **24** |
| ESTABLISHED | 757 | **104** | 88 | 0,8771 | 0,0885 | 0,0343 | **10** |

Differens **+26,08 pp / +22,46 pp**. RR 1,44/1,34, OR 4,06/3,80.
Cluster-robust på ticker: t **10,17 / 8,57**. På state-run: t 10,41/9,15.
Kluster-bootstrap KI [+20,96, +30,91] / [+17,46, +28,02], **100 % av dragningarna positiva**.
Block bootstrap KI [+24,09, +31,34] / [+19,82, +28,37].
Leave-one-ticker-out: spann [+25,51, +26,52] / [+21,91, +22,97], **inget teckenbyte**, största enskilda tickerpåverkan **0,56 pp**.

Effekten är alltså stor, replikerad, extremt signifikant och inte buren av
enskilda bolag. Om testet stannat här hade det varit ett REPLICATED SIGNAL.

## Men grupperna är inte jämförbara

Fördelning över rankdeciler (decil 1 = rank 1–3, decil 10 = rank 28–30):

| 2020-2026 | d1 | d2 | d3 | d4 | d5 | d6 | d7 | d8 | d9 | d10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| EMERGING | 4 | 9 | 10 | 20 | 26 | 34 | 61 | 77 | 103 | **119** |
| ESTABLISHED | **103** | **104** | 75 | 70 | 48 | 39 | 36 | 30 | 18 | 15 |

Fördelningarna är nära spegelvända. ESTABLISHED sitter på rank 9, EMERGING på
rank 24. Ett namn på plats 9 har 21 platsers marginal till gränsen; ett på plats
24 har sex. Att det första oftare är kvar nästa panel är aritmetik, inte minne.

Detta är för övrigt inte en bugg i designen utan en nödvändig egenskap: ett namn
som legat i topp-30 i åtta paneler *måste* ha starkt momentum, och H0 rangordnar
på momentum. TIS och rank kan inte separeras genom urval — bara genom kontroll.

## Efter kontroll försvinner allt

| Kontroll | 2020-2026 | 2014-2019 |
|---|---|---|
| Matchad score-decil inom panel, poolad | **+2,06 pp** | **−5,31 pp** — **teckenbyte** |
| — andel celler positiva | 18,8 % | 16,0 % |
| — användbara celler (av totala) | 101 av 556 | 125 av 672 |
| LPM med score + rank, cluster-robust | −1,89 pp (t −0,55) | −1,18 pp (t −0,37) |
| **LPM med rankdecil-dummies** (icke-parametrisk i rank, hela urvalet) | **−0,46 pp** (t −0,14) | **−0,61 pp** (t −0,20) |
| — 95 % KI | **[−7,12, +6,19]** | **[−6,58, +5,36]** |

Den sista raden är den avgörande. Den använder hela urvalet (n = 1 001 / 1 226),
kontrollerar rank icke-parametriskt och klustrar på ticker.

## De fyra begärda redovisningarna

**1. Teckenreplikation.** Rått: samma tecken, men det tecknet är rankens.
Kontrollerat: båda punktskattningarna är **negativa** (−0,46 / −0,61 pp) —
konsistent tecken, men i motsatt riktning mot hypotesen och i praktiken noll.
Den matchade decilanalysen byter tecken (+2,06 / −5,31).

**2. Statistisk osäkerhet.** SE 3,39 / 3,05 pp efter kontroll. |t| = 0,14 och 0,20.

**3. Faktisk effektstorlek.** −0,46 pp och −0,61 pp.

**4. Når effekten ≈12 pp?** **Nej — och detta är inte ett underpowerat nej.**
Konfidensintervallens övre gränser är **+6,19 pp och +5,36 pp**, alltså klart
under det förregistrerade riktmärket. Testet **utesluter** aktivt en effekt av
materiell storlek. Det kan däremot inte utesluta en effekt på 2–5 pp.

Klassificeringen är därför NO INCREMENTAL PATH INFORMATION, **inte**
PROMISING-BUT-UNDERPOWERED. Skillnaden är viktig: vi har inte misslyckats med att
mäta, vi har mätt och funnit ungefär noll.

## Falsifieringskriterierna

| Kriterium för current-state sufficiency | Utfall |
|---|---|
| Skillnaden nära noll | **JA** — −0,46 / −0,61 pp |
| Tecknet byter mellan fönstren | JA i den matchade analysen |
| Effekten försvinner efter score-kontroll | **JA — fullständigt, 26 pp → 0 pp** |

Alla tre uppfyllda. Kriterierna för population path-signal faller på punkt 2
("kvarstår efter score-kontroll").

## Vad testet faktiskt visade

Att **P(S→S) är en funktion av rank inom S**, vilket redan var känt som
rankautokorrelation 0,6215 (#22). Time-in-state är en indirekt avläsning av
samma sak: den mäter hur långt in i topp-30 ett namn ligger, inte något om dess
väg dit. Det bekräftar och skärper punkt I i feasibility-analysen — TIS var
redundant med H0, och redundansen visade sig vara total när den mättes mot rank
i stället för mot score.

**Locked H0:s rank är en tillräcklig statistik för nästa panels tillstånd inom
state S.** Modellen har inte kastat bort användbar tillståndsinformation på den
här dimensionen.

## Konsekvenser

* **MEM-C stängs på nivå 2.**
* **Lager C, stock-specific memory, körs inte.** Villkoret var att
  populationslagret först skulle etableras. Det gjorde det inte.
* **#64 Trend age** går från FORREGISTRERAD_EJ_KORD till **ALREADY_TESTED —
  INGET STÖD**, med bevis: 26 pp rått, 0 pp efter rankkontroll, båda fönstren.
* **MEM-R** berörs inte av detta resultat. Den frågar om recovery efter
  försvagning och har en egen population (361/369 lösta pullbacks). Den förblir
  oprövad och olicensierad.
* H0 fryst, hysteres oförändrad, G97-P oförändrad. Ingen handelsregel.

## Metodlärdom

**Rå gruppskillnad i ett tillståndstest mäter i första hand var i ranklistan
grupperna ligger.** +26 pp med t = 10, 100 % positiva bootstrapdragningar och
stabil leave-one-out såg ut som ett av programmets starkaste fynd. Hela effekten
var rankposition. Varje framtida jämförelse mellan tillståndsgrupper inom topp-N
ska redovisa gruppernas **rankfördelning** innan någon differens tolkas — och
kontrollen ska vara icke-parametrisk i rank, eftersom en linjär rankkontroll
här gav −1,89 pp medan dummykontrollen gav −0,46 pp.

---

# MEM-R — STOCK-SPECIFIC RECOVERY MEMORY (kört 2026-08-18)

`tools/mem_r_recovery_memory.py` → `research_k/mem_r_results.json`
Regel 5 körd: inga nya artefakter sedan G-PATH-1. Gates respekterade — endast
H0-rankning används.

**Klassificering: NO STOCK-SPECIFIC RECOVERY MEMORY.**

## A. Rekonstruktion av den låsta definitionen — verifierad

| Element | Definition (oförändrad) | 2020-2026 | 2014-2019 |
|---|---|---:|---:|
| Event | band S vid T−1, icke-S vid T | 361 | 369 |
| Tickers | | 199 | 167 |
| Recovery | band = S i panel T+1…T+13 | **45,71 %** | **50,95 %** |
| Celler | N / W / ej rankbar | 288/64/9 | 300/68/1 |

**PIT-lösningstid för ett tidigare event j: `res(j) = min(första recoverypanel,
j+13)`** — den tidigaste tidpunkt då utfallet faktiskt är känt. Ett tidigare
event får ingå i minnet vid T endast om `res(j) < T`. Detta är strängare än
"eventet är över" och löser överlappsproblemet: två pullbacks från samma ticker
med 5 panelers mellanrum kan bara användas om den första hann lösas.

De 9 respektive 1 event där namnet lämnade det rankbara universumet ingår i
populationen men utesluts ur LPM, där rank är obligatorisk kontroll.

## B/C. Täckningskarta — ingen godtycklig minimigräns

| Tidigare lösta events vid nytt event | 0 | 1 | 2 | 3 | 4 | 5+ |
|---|---:|---:|---:|---:|---:|---:|
| 2020-2026 | 57,6 % | 26,9 % | 11,4 % | 3,3 % | 0,8 % | 0,0 % |
| 2014-2019 | 48,2 % | 27,1 % | 13,6 % | 7,3 % | 2,7 % | 1,1 % |

≥1: 42,4 % / 51,8 % · ≥2: 15,5 % / 24,7 % · ≥3: 4,2 % / 11,1 %
Tickers med minst ett tidigare event: **97 / 100**. Median historik: 0 / 1.

Ingen cutoff används. Hela populationen ingår; events utan historik får per
konstruktion exakt noll stock-specific deviation.

## Den avgörande diagnostiken — det finns ingen mellanbolagsvarians

Den förregistrerade momentbaserade empiriska Bayes-skattningen ger:

| | 2020-2026 | 2014-2019 |
|---|---:|---:|
| σ²_mellan, median | **0,000000** | **0,000000** |
| σ²_mellan, max | 0,014814 | 0,011685 |
| σ²_inom | 0,2498 | 0,2308 |
| Andel events där σ²_mellan = 0 | **92,8 %** | **87,0 %** |
| Shrinkagevikt, median | **0,0000** | **0,0000** |
| Shrinkagevikt, max | 0,0828 | 0,1563 |

Detta är resultatet, och det uppstår **innan** något samband med utfallet mäts.
Variansen i bolagens observerade recovery-frekvenser är i praktiken helt
förklarad av binomiell samplingsvarians. Det finns ingen mellanbolagskomponent
att skatta. Under den förregistrerade shrinkagen blir MEM-R därför ~0 för
varje event, precis som §C kräver: shrinkage får inte skapa information.

*Anmärkning:* den shrunkna LPM-koefficienten (8,58 och 71,18) ska **inte**
citeras. Regressorn har nära noll varians, så koefficienten är 1/w-skalad och
numeriskt meningslös. Den redovisas här enbart för att den finns i utfallsfilen.

## E. Confounding — fördelningarna före tolkning

| 2020-2026 | n | tickers | recovery | medianrank | andel N | p_pop |
|---|---:|---:|---:|---:|---:|---:|
| negativ dev | 22 | 17 | 0,5909 | 43,0 | 0,77 | 0,578 |
| ingen historik | 208 | 199 | 0,4615 | 43,0 | 0,77 | 0,605 |
| positiv dev | 105 | 69 | 0,4476 | **46,0** | 0,84 | 0,587 |

| 2014-2019 | n | tickers | recovery | medianrank | andel N | p_pop |
|---|---:|---:|---:|---:|---:|---:|
| negativ dev | 49 | 27 | 0,5918 | 40,5 | 0,84 | 0,660 |
| ingen historik | 178 | 167 | 0,5337 | 39,0 | 0,78 | 0,686 |
| positiv dev | 103 | 60 | 0,4466 | **45,0** | 0,83 | 0,659 |

Positiv-dev-gruppen ligger på sämre rank i båda fönstren (46 mot 43, 45 mot
40,5). Konfundering finns, om än långt mildare än i G-PATH-1.

## D/H. Effektstorlek — och riktningen

Rå skillnad positiv minus negativ dev: **−14,33 pp / −14,52 pp.**
RR 0,758 / 0,755. OR 0,561 / 0,557.

**Tecknet är negativt i båda fönstren — motsatt hypotesen.** Aktier med en
historik av *bättre än populationen* återhämtar sig **mer sällan** vid nästa
pullback.

LPM med kontroll för p_pop, rank och cell (koefficient på `dev`, som spänner
ungefär ±1):

| | koeff | SE | t | 95 % KI | n |
|---|---:|---:|---:|---|---:|
| 2020-2026 | −0,075 | 0,114 | −0,66 | [−0,298, +0,148] | 333 |
| 2014-2019 | −0,175 | 0,085 | −2,05 | [−0,342, −0,008] | 350 |

## F. Matched-random placebo — den obligatoriska falsifieringen

Samma antal tidigare events, hämtade ur **andra** tickers matchade på cell och
PIT-behörighet. 1 000 dragningar.

| | Placebo 95 %-band | median | sd | Observerad | Andel placebo minst lika extrem |
|---|---|---:|---:|---:|---:|
| 2020-2026 | [−0,096, +0,202] | +0,047 | 0,079 | −0,075 | **41,5 %** |
| 2014-2019 | [−0,159, +0,163] | +0,000 | 0,082 | −0,175 | **3,0 %** |

I det sena fönstret ligger den observerade effekten mitt i placebofördelningen.
I det tidiga fönstret ligger den nätt och jämnt utanför — men i **fel riktning**.

**Materialitetsgränsen, kalibrerad mot placebofördelningen som Regel 8 kräver:**
placebo-sd är 0,079/0,082, så en koefficient behöver ungefär **0,24** för t ≈ 3.
Omräknat: testet kan upptäcka en skillnad i recovery-sannolikhet på ungefär
**12 pp** över dev-spannet. Denna gräns är härledd ur MEM-R:s egen
placebofördelning, inte återanvänd från G-PATH-1.

## G. Beroende

| | events | tickers | bootstrap ticker, KI | andel positiva | LOO-spann | teckenbyte |
|---|---:|---:|---|---:|---|---|
| 2020-2026 | 361 | 199 | [−38,85, +18,03] pp | 16,2 % | [−17,14, −7,87] | nej |
| 2014-2019 | 369 | 167 | [−30,41, +2,39] pp | 4,1 % | [−16,33, −11,00] | nej |

Bootstrap-KI innehåller noll i båda fönstren. Störstas påverkan: SHOT −6,46 pp
och XANO-B −3,52 pp — inget enskilt bolag bär resultatet, men bingrupperna är
små (22 respektive 49 negativ-dev-events).

## I. Den kritiska distinktionen

Recovery **är** delvis förutsägbar — populationens basfrekvens skiljer sig
mellan celler och över tid, och p_pop bär den informationen. Frågan var om
*vilket bolag det är*, givet dess egen historik, förbättrar prognosen därutöver.

Svaret är nej, och mekanismen är identifierad: **σ²_mellan = 0.** All variation i
bolagens observerade recovery-frekvenser är samplingsbrus. Brus regredierar mot
medelvärdet, vilket är exakt vad det konsekvent negativa tecknet visar. Ett bolag
som råkat återhämta sig 2 gånger av 2 har ingen förhöjd sannolikhet nästa gång —
det har ett skattningsfel som korrigeras.

## J. Klassificering

**1. NO STOCK-SPECIFIC RECOVERY MEMORY.**

Motivering, konservativt tillämpad:

* Mellanbolagsvariansen är noll i 87–93 % av eventen; det finns ingenting att
  skatta även innan utfallet konsulteras.
* Rå riktning replikerar men är **motsatt hypotesen** (−14,3 / −14,5 pp).
* Effekten faller kraftigt efter current-state-kontroll (−0,075 / −0,175).
* Den **slår inte matched placebo i båda fönstren** — 41,5 % av placebona är
  minst lika extrema i det sena fönstret.
* Bootstrap-KI innehåller noll i båda fönstren.

Klassificering 2 (PROMISING-BUT-UNDERPOWERED) är utesluten: det är inte fråga om
en svag effekt i rätt riktning som saknar power, utan om noll mellanbolagsvarians
och ett tecken som pekar åt andra hållet.

## K. Beslutsträd

Utfallet är 1 → **MEM-R stängs, och därmed den nu testbara delen av
STATE/PATH/MEMORY-spåret.**

Status för hela spåret efter tre körningar:

| Gren | Utfall |
|---|---|
| Episodbaserat memory (M1) | DATA_BLOCKED — historikdjup |
| MEM-C / time-in-state (G-PATH-1) | NO INCREMENTAL PATH INFORMATION |
| **MEM-R / recovery memory** | **NO STOCK-SPECIFIC RECOVERY MEMORY** |
| MEM-F | deduplicerad bort (≡ MEM-R:s komplement; avkastningsformen = G13/G17) |
| DR2 / rankförändring | ALREADY ANSWERED (#44) |

Ingen memory-score byggd. Inget portföljtest. Ingen implementation
rekommenderas. H0 fryst, hysteres oförändrad, G97-P orörd.

## Metodlärdom

**Skatta variansdekompositionen innan sambandet.** Frågan "har bolag olika
recovery-benägenhet?" besvaras av σ²_mellan, inte av en regression. Här var
σ²_mellan noll i 87–93 % av eventen — hela hypotesen faller på en
momentskattning som tar sekunder, utan att utfallet behöver konsulteras. Varje
framtida bolagsspecifikt minnesdrag ska börja där.

**Ett konsekvent tecken i två fönster kan vara regression mot medelvärdet.**
−14,3 och −14,5 pp replikerade nästan exakt och överlevde leave-one-ticker-out.
Det såg ut som ett fynd med omvänt tecken. Det var skattningsfel som korrigerades
— vilket σ²_mellan-diagnostiken förutsade.
