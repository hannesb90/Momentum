# Granskning av samtliga förkastade tester — testspecifika begränsningar

Datum: 2026-08-16. Frågan: föll testerna för att mekanismerna saknar värde, eller
för att testerna byggdes på ett sätt som gjorde ett positivt utfall omöjligt?

Fyra misstankar prövades **empiriskt**, inte bedömdes. Tre falsifierades. En
bekräftades delvis. Och granskningen frilade en mekanism som ingen tidigare
körning hade isolerat.

---

## Materialet

**106 varianter** med tvåfönsterutfall extraherade ur `research_k/*.json`, plus
81 med bara ett fönster. Tio testfamiljer plus A1–A4.

### Det första som syns i materialet

| Teckenmönster (2020-2026, 2014-2019) | Antal | Andel |
|---|---:|---:|
| positiv i sena, positiv i tidiga | 10 | 9 % |
| positiv i sena, negativ i tidiga | 16 | 15 % |
| **negativ i sena, positiv i tidiga** | **35** | **33 %** |
| negativ i sena, negativ i tidiga | 45 | 42 % |

Median Δ: **−1,03 %** i 2020-2026, **−0,29 %** i 2014-2019. **75 % av allt vi
prövat är negativt i det sena fönstret**, mot 58 % i det tidiga.

**Tvåfönsterkriteriet är i praktiken ett "måste överleva 2020-2026"-kriterium.**
Det sena fönstret gör nästan hela förkastandearbetet. Det är i sig en
testspecifik begränsning som aldrig redovisats.

---

## L1 — Mättes reglerna mot en baslinje som redan gör deras jobb?

**Misstanken.** STACK_H innehåller hysteres rank 35, NTZ 0,005, ERC och
FR-overlay. Hysteresen ejicerar redan namn vars rank förfallit — samma arbete
som en exitregel, en swapregel och delvis en utjämningsregel gör. En regel som
prövas mot en baslinje som absorberat dess effekt kan bara mäta det marginella
tillskottet, och ett nollresultat betyder då *"tillför inget utöver hysteresen"*,
inte *"mekanismen saknar värde"*.

**Testet.** Åtta regler kördes mot två baslinjer: BAR (Control C + invers vol,
inga overlays) och STACK_H.

| Regel | mot BAR 26 / 19 | mot STACK_H 26 / 19 | Dom |
|---|---:|---:|---|
| poängutjämning EMA3 | −1,70 % / −3,32 % | −1,28 % / −2,13 % | äkta förkastande |
| poängutjämning EMA2 | −0,49 % / −2,25 % | −1,64 % / −1,70 % | äkta förkastande |
| köpband rank 11-40 | −5,22 % / −1,54 % | −2,81 % / −1,07 % | äkta förkastande |
| köpband rank 16-45 | −7,89 % / −4,09 % | −5,35 % / −1,33 % | äkta förkastande |
| kort momentum 30 % | −3,07 % / −0,70 % | −1,26 % / +2,24 % | äkta förkastande |
| kort momentum 15 % | −1,55 % / −0,05 % | −0,38 % / +0,93 % | äkta förkastande |
| N=20 | +1,61 % / −4,00 % | +4,11 % / −2,96 % | äkta förkastande |
| N=40 | −3,04 % / −2,28 % | −3,75 % / −0,86 % | äkta förkastande |

**FALSIFIERAD.** Noll av åtta blir positiva mot den bara modellen. Inget
förkastande var ett baslinjeartefakt.

**Bifynd som inte handlar om reglerna.** BAR ger 12,87 % / 29,98 %, STACK_H ger
13,56 % / 27,82 %. Overlayerna hjälper alltså med +0,69 pp i det sena fönstret
och skadar med **−2,16 pp** i det tidiga. Den frysta modellens egna tillägg
replikerar inte över fönster.

---

## L2 — Var trösklarna statiska när de borde varit relativa?

**Misstanken.** Nästan varje regel använder ett fast tal som gäller identiskt
2014–2026: "blankning över 1 %", "underpresterar med 10 %", "rank under 40". Men
blankningstäckningen gick från 3,7 % till 13,7 % av universumet, och
volatiliteten fördubblades 2020. Ett fast tal är olika händelser i olika
perioder. Den relativa formen — "de 10 % mest blankade *denna panel*" — flyttar
med fördelningen.

**Testet.** Tre regler byggdes om från absolut till tvärsnittlig form, plus
regimbetingade varianter. Tolv körningar.

Resultat: **1 av 12 positiv i båda fönstren**, och den enda (swap 20 % endast i
bear, +0,02 % / +0,16 %) rör 2,6 respektive 0,1 namn per panel — den är noll.

**INTE BEKRÄFTAD som räddning.** Den relativa formen ändrar effektens storlek
men inte domen.

**Men den frilade något.** Se L5.

---

### L2 fortsatt — hela konverteringsprogrammet

Del 1 konverterade tre familjer. Del 2 och 3 tog resten. **35 konverteringar
totalt, 3 nominellt positiva — och alla tre visade sig vara artefakter.**

| Omgång | Konverterade | Varianter | Nominellt positiva |
|---|---|---:|---:|
| Del 1 | swap, lutning, blankning, regimbetingning | 12 | 1 |
| Del 2 | drawdown, hysteres, köpband, utjämning | 16 | 2 |
| Del 3 | trendfilter, lookback | 7 | 0 |

**D4 drawdown-exit vol-normaliserad.** DD20 säljer vid −20 % från egen topp,
samma tal för ett kraftbolag med 18 % årsvol som för ett förhoppningsbolag med
65 %. Den naturliga dynamiska formen är −k gånger namnets egen volatilitet.
Jämfört vid *matchad exitfrekvens*:

| Form | Δ 26 / 19 | exits/panel | fönsterspann |
|---|---|---:|---:|
| statisk −20 % | −1,01 % / +1,30 % | 3,9 / 2,1 | 2,31 pp |
| dynamisk −0,5 × vol | −0,32 % / +0,26 % | 3,1 / 2,3 | 0,58 pp |
| statisk −15 % | −1,01 % / +1,06 % | 5,8 / 4,1 | 2,07 pp |
| dynamisk −0,4 × vol | −0,60 % / +1,80 % | 4,8 / 4,0 | 2,40 pp |

Vid den ena kalibreringen krymper fönsterspannet kraftigt, vid den andra växer
det. **Ingen konsekvent effekt** — vol-normalisering räddar inte DD20 och
förklarar den inte heller. Båda formerna faller.

**D5 hysteres som percentil — strukturellt omöjlig att pröva som skärpning.**
Topp 10 % av 277 namn är 27,7 namn, alltså färre än N=30. Percentilformen
degenererar därför till *hysteres helt av* så snart tröskeln är snävare än
portföljstorleken; 5 % och 10 % gav identiska siffror, och båda är exakt lika
med `use_hysteresis=False` (13,65 % / 29,60 %). Konverteringen går inte att
göra åt det håll man vill.

Biprodukten är däremot informativ: **hysteresen kostar −1,78 pp i det tidiga
fönstret och ger +0,09 pp i det sena.** Samma teckenbyte som allt annat.

**D6 köpband på poänggap — strukturell nolloperation.** Poolen är alltid
sorterad på poäng och vi tar alltid dess topp-N. Ett gapdefinierat pool kan
därför aldrig ändra urvalet: är gapet vitt räcker poolen och topp-N är oförändrad,
är det snävt faller regeln tillbaka på topp-N. Fyra gap från 0,005 till 0,03 gav
alla **exakt +0,00 %**. Mekanismen är matematiskt identisk med rankbandet, som
redan prövats och fallit (−2,81 % / −1,07 %).

**D7 adaptiv utjämningsspan.** EMA-span styrd av rankomsättningen: −1,60 % till
−1,93 % i det sena fönstret, −0,64 % till −3,16 % i det tidiga. Sämre än fast
span, som redan var sämre än ingen utjämning.

**D8 trendfilter med adaptiv längd.** Statisk SMA200 reproducerade exakt
(+0,00 %), vilket validerar implementationen. Adaptiv längd skalad mot namnets
volatilitet: +0,13 % / −0,80 % och −0,17 % / −1,58 %. Noterbart är att den
statiska SMA300 ger +1,91 % tidigt och −1,96 % sent — teckenbytet igen.

**D9 lookback betingad på volatilitetsregim.** Luta signalen mot snabbare
information bara i hög volatilitet: −0,16 % / +1,30 %, −0,86 % / +1,74 %,
−1,68 % / +0,52 %. Noll av tre.

### Vad konverteringsprogrammet visade

**Den dynamiska formen ändrar storleken på effekterna men inte domen.** I varje
enda familj återkommer samma teckenbyte — negativt i det sena fönstret, positivt
i det tidiga. Den relativa formen flyr inte regimskillnaden, eftersom
regimskillnaden inte orsakas av feljusterade trösklar.

Två konverteringar visade sig dessutom vara omöjliga att göra alls i den riktning
man vill (D5, D6). Det är värt att veta: de stod på listan som otestade, men de
är inte otestbara utan meningslösa.

---

## L3 — Drivs förkastandet av V-bottnarna 2020 och 2022?

**Misstanken.** Varje regel som beskär eller roterar säljer nedtryckta namn strax
innan de vänder. 2020-2026 innehåller två skarpa V-bottnar; det tidiga fönstret
inga (noll paneler under −8 %).

**Testet.** Nettodifferensen mot baslinjen dekomponerad på nedgångs-, uppgångs-
och vändpaneler (panelen *efter* ett fall större än −8 %).

| Regel | vändpanelernas bidrag, 2020-2026 |
|---|---:|
| swap 10 % sämsta | **+1,9 %** |
| swap 20 % sämsta | **+5,0 %** |
| lutning bort 20 % | **+1,6 %** |
| lutning bort 33 % | **+3,7 %** |

**FALSIFIERAD, och tvärtom.** Vändpanelerna är reglernas *bästa* paneler.
Beskärning fungerar genom en V-botten. Hypotesen var fel.

---

## L4 — Vilar förkastandet på ett fåtal paneler?

**Testet.** Andel av det totala underskottet som de fem värsta panelerna bär, i
2020-2026:

| Regel | totalt | fem värsta | andel |
|---|---:|---:|---:|
| swap 20 % | −13,2 % | −12,4 % | 94 % |
| lutning bort 20 % | −5,4 % | −6,1 % | 114 % |
| lutning bort 33 % | −5,3 % | −8,1 % | 152 % |
| blankning bort 10 % | −0,9 % | −6,4 % | 718 % |

Fem paneler av 66 bär hela underskottet, och datumen är utspridda (2021-12-03,
2023-05-19, 2025-07-11, 2025-12-26) — inte krasdatum.

**Men jackknife per år motsäger fragilitet.** Släpp ett kalenderår i taget:

| Regel, 2020-2026 | utan 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | positiva |
|---|---:|---:|---:|---:|---:|---:|---:|
| lutning bort 33 % | −1,0 % | −2,4 % | −1,2 % | −0,8 % | −1,5 % | −1,8 % | **0/6** |
| lutning bort 20 % | −1,3 % | −1,6 % | −0,8 % | −1,5 % | −1,1 % | −1,0 % | **0/6** |

**DELVIS BEKRÄFTAD men utan konsekvens.** De fem värsta panelerna är utspridda
över olika år, så inget enskilt år bär resultatet. Det negativa utfallet är
stabilt.

---

## L5 — Var det tidiga fönstrets positiva utfall datakontaminering?

**Misstanken.** Detta är den allvarligaste. 2014-2019-serierna är
rekonstruerade och bär känd kontaminering; brottklassificeringen flaggade 17
namn med R4-brott (endagsspikar, justeringsfel, ojusterade splittar). **En regel
som slänger ut namn med kraftiga negativa poängrörelser slänger ut exakt de
namn som har artificiella nivåskiften.** Det skulle skapa ett falskt positivt
utfall i just det fönstret.

**Testet.** Kör om med alla 17 R4-namn helt borttagna ur universumet.

| Regel | med R4-namn | utan R4-namn | kvar av effekten |
|---|---:|---:|---:|
| lutning bort 20 % | +1,90 % | +1,90 % | **100 %** |
| lutning bort 33 % | +3,44 % | +3,81 % | **111 %** |
| swap 10 % sämsta | +1,33 % | +0,68 % | **51 %** |

**FALSIFIERAD för lutningsregeln, BEKRÄFTAD för swap.** Halva swap-regelns
tidiga fördel var kontaminerade serier — en verklig testspecifik begränsning som
inte var känd. Lutningsregeln påverkas inte alls.

---

## Det som överlevde granskningen

Den relativa lutningsregeln — **ta bort de 20–33 % av namnen vars H0-poäng
försämrats mest de senaste tre panelerna** — är den enda mekanism i hela
programmet som klarar varje kontroll granskningen kastar på den:

| | 2014-2019 | 2020-2026 |
|---|---|---|
| Δ CAGR (q=20 %) | **+1,90 %** | −1,23 % |
| Konfidensintervall | **[+0,96 %, +3,21 %]** — utesluter noll | [−2,21 %, +0,26 %] |
| t | +2,09 | −1,44 |
| Jackknife per år | **6/6 positiva** | 0/6 positiva |
| Utan kontaminerade serier | 100 % kvar | — |
| Δ CAGR (q=33 %) | **+3,44 %**, KI [+1,11 %, +6,34 %] | −1,46 %, KI [−3,20 %, −0,21 %] |

Detta är **inte brus**. Det är en stabil, statistiskt signifikant effekt i det
tidiga fönstret och en stabil, nästan signifikant effekt med **motsatt tecken** i
det sena.

Mekanismen är en tvärsnittlig rankförfallsexit. SPARF F7 prövade rank-exit och
fann inget — men det var en *absolut* regel (sälj vid rank > X). Den relativa
formen prövades aldrig.

### Vad det betyder

Ett äkta teckenbyte är ett sämre besked än ett nollresultat, inte ett bättre.
En mekanism som gav +1,9 pp under sex år och −1,2 pp under de följande sex är
inte något man tar in i en modell som ska köras framåt — man vet inte vilket
tecken nästa sexårsperiod har.

Men det ändrar hur programmets samlade nollresultat ska läsas. Slutsatsen är
inte *"ingenting fungerar"*. Den är: **mekanismerna fungerar i det tidiga
fönstret och slutar fungera i det sena, systematiskt, 33 % av alla varianter.**
Något i marknaden ändrades mellan perioderna, och det är den frågan som är värd
att ställa — inte fler tilläggsregler.

---

## Begränsningar som består och som INTE gick att testa bort

| # | Begränsning | Berör | Kan åtgärdas? |
|---|---|---|---|
| L6 | **Detektionsgolvet.** 66 paneler ger t ≈ 0,35 för en 2 pp-effekt. Allt under ~4 pp är oupptäckbart. | alla 106 varianter | Nej. Kräver kalendertid, inte tätare mätning. |
| L7 | **Ett fönster bara.** MFN och KPI-historiken börjar 2020. PEAD, K2, K7–K9 kan aldrig möta kriteriet. | ~81 envariabelutfall | Nej, förrän 2032. |
| L8 | **Panelupplösning 28 dagar.** Mekanismer som verkar inuti panelen är osynliga. | intraperiod, streak, minsta hålltid | Delvis — dagliga priser finns. Ej gjort (A5). |
| L9 | **Universum låst till large.** Modellen ser 420/290 namn. Regler som behöver småbolag kan inte visa sig. | alla | Nej, utan att bryta förseglingen. |
| L10 | **Takfelet.** Vikttaket bryts i 95,5 % av panelerna. Varje regel som ändrar vikter mäts genom ett trasigt tak. | alla vikt-tilts | Nej — felet är del av den frysta specen. |
| L11 | **Fasövervikten.** Kontraktets tal är den gynnsamma av två rebalansfaser (+0,33 pp sent, +1,44 pp tidigt). | alla jämförelser mot baslinjen | Redovisad, se `LUCKOR_A1_A4_RESULTAT.md`. |
| L12 | **Bästa-av-N inom ett fönster.** Tidiga familjer valde celler ur rutnät i ett fönster. | SPARI-batcherna, ablationen | Åtgärdad för kandidaterna i `korsfonster_kandidater.py`, ej för de äldre. |

**L11 tillsammans med L6 är avgörande för hur tabellerna ska läsas:** ett utfall
under ~0,5 pp i det sena fönstret eller ~1,5 pp i det tidiga ligger inom
fasbruset och betyder ingenting alls, oavsett tecken.

---

## Reproduktion

```
tools/granskning_baslinjeredundans.py            research_k/granskning_baslinjeredundans_results.json
tools/granskning_statisk_vs_dynamisk.py          research_k/granskning_statisk_vs_dynamisk_results.json
tools/granskning_var_uppstar_forkastandet.py     research_k/granskning_var_uppstar_forkastandet_results.json
```

Baslinjen (13,56 % / 27,82 %) och motorkontrollen (regel avstängd = baslinjen)
verifierades i varje körning.
