# FI:s blankningsregister — datalager och utfall

Datum: 2026-08-16. Status: **INGET STÖD.** Källan är nedladdad, validerad och
permanent arkiverad; ingen regel ur den befordras.

## Vad källan är

Finansinspektionens blankningsregister publicerar varje **betydande
nettoblankningsposition** i svenska emittenter. Rapporteringsplikt inträder vid
0,1 %, men **publiceringströskeln är 0,5 %** — allt därunder är osynligt.

Två filer laddades från fi.se:

| Fil | sha256 | Rader |
|---|---|---|
| `raw/fi_blankning/fi_blankning_Hist_20260816T065556Z.ods` | `cf93e8fc5d5d2504…` | 38 201 |
| `raw/fi_blankning/fi_blankning_Aktuell_20260816T065556Z.ods` | `3bc2bfe91b055afc…` | 239 |

Normaliserat lager: `validated/fi_blankning/fi_blankning_normaliserad.jsonl`,
38 394 unika poster, **2010-05-10 → 2026-08-14**, 421 unika ISIN.

Detta är den **enda nya datakällan i hela programmet som har historik i båda
fönstren**. MFN börjar 2020, insynsregistret 2020, Börsdatas shorts-endpoint är
en ögonblicksbild utan tidsserie. FI-blankning kunde därför som första nya källa
prövas mot tvåfönsterkriteriet.

## Rekonstruktion

Registret är en **händelselogg**, inte en tidsserie: en rad = en innehavare, en
emittent, ett datum, en procentsats. En position gäller tills samma innehavare
rapporterar en ny siffra; `<0,5` betyder att innehavaren gått under
publiceringströskeln och sätts till noll.

Aggregerad blankning för ett bolag vid datum D = summan av varje innehavares
senast rapporterade position ≤ D. Punkt-i-tid säkras med **4 dagars lagg**
(FI publicerar dagen efter positionsdatum, kl 15:30, plus marginal).

## Varför den inte kan bära en regel

Täckningen är för tunn för att röra portföljen:

| | 2020-2026 | 2014-2019 |
|---|---|---|
| Namn i topp-30 med någon rapporterad position | 2,9 | **0,5** |
| — därav över 1 % | 1,7 | 0,3 |
| — därav över 2 % | 1,0 | 0,1 |
| Andel av universumet med position | 13,7 % | **3,7 %** |

I det tidiga fönstret berör en uteslutningsregel alltså **ett namn vartannat
panelbeslut**. Registret var nytt då (211 poster 2012, 918 år 2013) och
marknadspraxis för blankning i svenska småbolag var långt mindre utbredd.

## Råsambandet

Riktningen är den väntade men styrkan är inte där:

| Fönster | Blankade ≥1 % | Övriga | Skillnad | t |
|---|---|---|---|---|
| 2020-2026 | −0,192 %/panel | +0,222 % | −0,415 % | −1,16 |
| 2014-2019 | +1,030 %/panel | +1,337 % | −0,308 % | −0,92 |

Blankade namn går sämre i båda fönstren, men ingendera skillnaden är
signifikant, och effekten är för liten för att överleva att bara ~2 av 30
innehav berörs.

## Tolv regler mot STACK_H

Baslinjen reproducerade exakt (13,56 % / 27,82 %).

| Regel | CAGR 26 | Δ | CAGR 19 | Δ | Båda + |
|---|---|---|---|---|---|
| N1 uteslut ≥ 0,5 % | 12,29 % | −1,27 % | 28,67 % | +0,85 % | — |
| N1 uteslut ≥ 1 % | 12,94 % | −0,62 % | 28,86 % | +1,04 % | — |
| N1 uteslut ≥ 2 % | 12,76 % | −0,80 % | 28,30 % | +0,48 % | — |
| N2 halverad vikt ≥ 1 % | 13,81 % | +0,25 % | 27,97 % | +0,15 % | JA |
| N2 vikt ×0,75 ≥ 1 % | 13,59 % | +0,03 % | 27,88 % | +0,06 % | JA |
| N3 rankstraff 0,5 | 13,45 % | −0,11 % | 27,98 % | +0,16 % | — |
| N3 rankstraff 2,0 | 13,02 % | −0,54 % | 27,97 % | +0,15 % | — |
| F1 uteslut stigande ≥ +0,5 pp | 13,93 % | +0,37 % | 28,76 % | +0,94 % | JA |
| F1 uteslut stigande ≥ +1 pp | 13,92 % | +0,36 % | 28,16 % | +0,34 % | JA |
| F2 bonus vid fallande | 13,60 % | +0,04 % | 27,70 % | −0,12 % | — |
| K1 kontrar +0,5 | 13,73 % | +0,17 % | 27,69 % | −0,13 % | — |
| K1 kontrar +2,0 | 12,82 % | −0,74 % | 27,51 % | −0,31 % | — |

Fyra av tolv positiva i båda fönstren — färre än de sex som ren slump ger.

## Placebo avgör saken

Varje regel som byter ut namn jämfördes mot slumpmässig uteslutning av lika
många namn per panel, 60 dragningar:

| Regel | Fönster | Placebo ± 2 sd | Regelns Δ | Utfall |
|---|---|---|---|---|
| N1 ≥ 1 % | 2020-2026 | [−2,88 %, +0,40 %] | −0,62 % | inom |
| N1 ≥ 1 % | 2014-2019 | [−1,38 %, +1,22 %] | +1,04 % | inom |
| N1 ≥ 0,5 % | 2020-2026 | [−3,45 %, +0,82 %] | −1,27 % | inom |
| N1 ≥ 0,5 % | 2014-2019 | [−1,44 %, +0,87 %] | +0,85 % | inom |
| F1 stigande | 2020-2026 | [−2,33 %, +0,57 %] | +0,37 % | inom |
| F1 stigande | 2014-2019 | [−1,37 %, +1,02 %] | +0,94 % | inom |

**Samtliga ligger inom placebobandet.** F1:s +0,94 pp i det tidiga fönstret
kommer från en regel som utesluter 0,1 namn per panel — det är ett fåtal
enskilda uteslutningar, inte en effekt.

Notera att placebomedelvärdet är negativt (−0,88 % till −1,31 % i 2020-2026):
att slumpmässigt plocka bort namn ur toppen kostar. Regelns Δ ligger något över
placebomedlet men långt inom spridningen.

## Slutsats

Blankningsdata bär ingen regel i denna modell. Skälet är strukturellt, inte
statistiskt brus i mätningen: publiceringströskeln på 0,5 % gör att endast
3,7–13,7 % av universumet någonsin syns, och momentumtoppen är inte där
blankarna sitter. Källan arkiveras som avslutad.

Vad som **inte** prövats och inte heller kan prövas: positioner under 0,5 %,
och blankningens nivå i förhållande till free float (FI publicerar procent av
aktiekapital, inte av float).

## Reproduktion

```
tools/parse_fi_blankning.py     # ODS -> validated/fi_blankning/*.jsonl
tools/fi_blankning_signal.py    # 12 regler + placebo mot STACK_H
research_k/fi_blankning_signal_results.json
```
