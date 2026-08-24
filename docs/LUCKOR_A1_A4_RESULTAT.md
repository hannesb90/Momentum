# Luckor A1–A4 körda mot STACK_H — resultat

Datum: 2026-08-16. Baslinjen reproducerade i varje körning (13,56 % / 27,82 %).
Samtliga fyra fyller luckor identifierade i `LEGACY_LUCKANALYS_2026-08-16.md`.

**Sammanfattning: ingen av de fyra ska adderas.** Men A1 och A2 gav tillsammans
ett fynd om den frysta modellen som inte handlar om någon tilläggsregel.

---

## A1 — Rebalansfrekvens (SPARF F6 var ett tvåpunktstest)

Svep 4/8/12/16/24/52 veckor, **varje takt över samtliga fasförskjutningar**.
Att bara köra en fas mäter vilken startvecka som råkade passa, inte takten.

### 2020-2026

| Takt | medel | min | max | sd | oms/år | maxDD | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|
| 4 veckor | 12,44 % | 12,44 % | 12,44 % | 0,00 % | 361 % | −24,68 % | 0,567 |
| **8 veckor (kontrakt)** | **13,23 %** | 12,91 % | 13,56 % | 0,46 % | 309 % | −23,89 % | 0,626 |
| 12 veckor | 12,59 % | 12,06 % | 12,94 % | 0,47 % | 283 % | −23,51 % | 0,597 |
| 16 veckor | 12,62 % | 12,14 % | 13,59 % | 0,68 % | 267 % | −21,77 % | 0,637 |
| 24 veckor | 12,43 % | 11,05 % | 13,78 % | 1,04 % | 243 % | −20,82 % | 0,652 |
| 52 veckor | 9,71 % | 6,65 % | 14,84 % | 2,42 % | 214 % | −19,43 % | 0,524 |

### 2014-2019

| Takt | medel | min | max | sd | oms/år | maxDD | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|
| 4 veckor | 28,08 % | 28,08 % | 28,08 % | 0,00 % | 297 % | −14,85 % | 1,711 |
| **8 veckor (kontrakt)** | **26,38 %** | 24,93 % | 27,82 % | 2,04 % | 258 % | −15,63 % | 1,611 |
| 12 veckor | 25,63 % | 24,06 % | 27,41 % | 1,69 % | 243 % | −15,12 % | 1,595 |
| 16 veckor | 24,17 % | 22,34 % | 26,14 % | 1,68 % | 234 % | −15,17 % | 1,541 |
| 24 veckor | 22,49 % | 20,64 % | 26,18 % | 2,01 % | 221 % | −15,02 % | 1,458 |
| 52 veckor | 17,91 % | 14,34 % | 22,43 % | 2,44 % | 210 % | −13,74 % | 1,226 |

**Ingen takt slår 8 veckor i båda fönstren, inte ens när man får välja dess
bästa fas.** Fyra veckor vinner i det tidiga fönstret (+1,71 pp) och förlorar i
det sena (−0,79 pp). Allt längre är monotont sämre i båda.

Bootstrap på bästa fas mot kontraktet: samtliga konfidensintervall täcker noll
utom 52 veckor i 2014-2019, som är signifikant **sämre** (−5,39 pp, t −2,09).

Legacys påstående *"52v är sämst av fem prövade takter"* replikerar alltså
kraftigt. Påståendet *"13v är enda som överlever"* gör det inte — riktningen
mot långsammare rotation är fel på H0.

**Två saker som inte handlar om valet av takt:**

Långsammare rebalans förbättrar drawdown monotont i båda fönstren (2020-2026:
−24,68 % → −19,43 %) och Sharpe upp till 24 veckor i det sena fönstret. Den
riskprofilen vänder helt i det tidiga (Sharpe 1,711 → 1,226). Det är alltså
ingen stabil riskvinst, bara en fönstereffekt.

Fasspridningen växer kraftigt med takten. Vid 52 veckor är spannet 6,65–14,84 %
i 2020-2026 — **8,2 procentenheter enbart beroende på vilken vecka man startar**.
Det är ett självständigt argument mot långsam rotation oavsett medelvärde.

---

## A2 — Staggerade kohorter (legacy N3-55)

Dela kapitalet i k delportföljer med förskjuten rebalansfas. Ingen ny signal,
ingen ny tröskel — ren variansreduktion.

| Konstruktion | CAGR 26 | Δ | CAGR 19 | Δ | medelkorr mellan sleeves |
|---|---:|---:|---:|---:|---:|
| 8 veckor, 2 kohorter | 13,26 % | −0,30 % | 26,39 % | −1,43 % | 0,97 |
| 12 veckor, 3 kohorter | 12,65 % | −0,91 % | 25,65 % | −2,17 % | 0,96 |
| 16 veckor, 4 kohorter | 12,68 % | −0,88 % | 24,20 % | −3,62 % | 0,95 |
| 24 veckor, 6 kohorter | 12,50 % | −1,06 % | 22,53 % | −5,29 % | 0,93 |
| 52 veckor, 13 kohorter | 9,78 % | −3,78 % | 17,97 % | −9,85 % | 0,90 |

**Faller, och orsaken är entydig: sleeverna är 0,90–0,97 korrelerade.** Det finns
ingen diversifiering att skörda. Variansvinsten — kohortens CAGR minus
medelsleevens — är +0,02 till +0,07 procentenheter. Praktiskt noll.

Sleeverna är så lika för att de äger nästan samma namn. Hysteresen på rank 35
och den tröga signalen gör att en portfölj som rebalanserar i fas 0 och en som
rebalanserar i fas 1 håller i stort sett samma 30 bolag. Staggering sprider ut
besluten i tiden men ändrar knappt vad som ägs.

**Fasspridningen i A1 är alltså inte skördbar.** Den är inte oberoende
variation, den är samma portfölj med en tidsförskjutning.

---

## Fyndet som A1 och A2 ger tillsammans

Kohorten ligger per konstruktion nära *medelfasen*. Kontraktet ligger på
*bästa* fasen — i båda fönstren:

| Fönster | Kontraktets registrerade CAGR | Medelfas | Sämsta fas | Fasövervikt |
|---|---:|---:|---:|---:|
| 2020-2026 | 13,56 % | 13,23 % | 12,91 % | **+0,33 pp** |
| 2014-2019 | 27,82 % | 26,38 % | 24,93 % | **+1,44 pp** |

Det registrerade talet är alltså den gynnsamma av två möjliga startfaser, i
båda fönstren. Det är inget fel — fasen valdes på en förregistrerad ankarpunkt,
inte i efterhand — men spridningen mättes aldrig, så den har heller aldrig
redovisats.

**Konsekvens: 13,56 % bör läsas som 13,2 ± 0,3 %, och 27,82 % som 26,4 ± 1,4 %.**
Det ändrar inte modellen och ska inte ändra den 19 dagar före forward-start. Det
ändrar vilken precision talet tål när det citeras.

---

## A3 — Poängutjämning (legacy test08)

EMA och glidande medel över 2–4 paneler på H0-poängen, in i den kanoniska motorn.

| Variant | CAGR 26 | Δ | CAGR 19 | Δ | utbytta namn i topp-30 |
|---|---:|---:|---:|---:|---:|
| EMA span 2 | 11,92 % | −1,64 % | 26,12 % | −1,70 % | 2,8 / 2,2 |
| EMA span 3 | 12,28 % | −1,28 % | 25,69 % | −2,13 % | 4,5 / 3,5 |
| EMA span 4 | 11,12 % | −2,44 % | 24,96 % | −2,86 % | 5,9 / 4,4 |
| glidande medel 2 | 11,05 % | −2,51 % | 27,54 % | −0,28 % | 3,7 / 3,0 |
| glidande medel 3 | 12,91 % | −0,65 % | 24,95 % | −2,87 % | 5,4 / 4,5 |
| glidande medel 4 | 10,44 % | −3,12 % | 24,21 % | −3,61 % | 6,6 / 5,6 |
| halv dämpning (0,5 + 0,5 EMA3) | 12,24 % | −1,32 % | 26,95 % | −0,87 % | 2,6 / 1,8 |

**Noll av sju positiva i båda fönstren, och gradienten är monoton: mer
utjämning är sämre, i båda fönstren och i båda utjämningsfamiljerna.**
Placebot för den minst dåliga varianten ligger inom bandet i båda fönstren.

Detta är ett verkligt besked, inte brus — en konsekvent gradient över två
oberoende fönster och två metoder är inte slumpmönster.

**Det motsäger "sen på bollen"-intuitionen direkt.** Utjämning gör beslutet
senare, och det kostar. Poängens *färskhet* bär värde även om dess *upplösning*
är platt. Rankningen är brusig men bruset är inte det som skadar oss.

---

## A4 — Opportunity-cost-byte (legacy `swap_10`)

Legacys starkaste enskilda fynd: *"den enda mekanism i hela sessionen som klarar
BÅDA kontrollerna"*. Regeln: byt ut ett innehav som underpresterar mot
universumet med mer än U sedan köp, när bästa icke-ägda kandidat överstiger dess
poäng med mer än G. Byte tillåtet på varje panel, även icke-rebalanspaneler.

Motorkontroll: med bytesregeln avstängd ger skriptet exakt 13,56 %.

| Variant | CAGR 26 | Δ | CAGR 19 | Δ | byten/panel |
|---|---:|---:|---:|---:|---:|
| U=0 %, inget poänggap | 7,53 % | −6,03 % | 23,25 % | −4,57 % | 26,2 / 26,9 |
| U=5 % | 11,62 % | −1,94 % | 28,15 % | +0,33 % | 1,7 / 1,8 |
| U=10 % | 11,56 % | −2,00 % | 27,54 % | −0,28 % | 1,2 / 1,1 |
| U=20 % | 13,66 % | +0,10 % | 27,65 % | −0,17 % | 0,6 / 0,4 |
| U=10 % + G=0,02 | 12,56 % | −1,00 % | 28,67 % | +0,85 % | 0,8 / 0,7 |
| U=10 % + G=0,05 | 12,70 % | −0,86 % | 28,84 % | +1,02 % | 0,7 / 0,6 |
| U=10 % + G=0,10 | 13,18 % | −0,38 % | 28,90 % | +1,08 % | 0,4 / 0,4 |
| U=10 % + F1 | 11,83 % | −1,73 % | 28,31 % | +0,49 % | 1,2 / 1,0 |
| U=10 % + G=0,05 + F1 | 12,48 % | −1,08 % | 28,64 % | +0,82 % | 0,6 / 0,6 |

**Noll av nio positiva i båda fönstren.** Legacys starkaste fynd replikerar inte
på STACK_H.

Mönstret är systematiskt: swap är genomgående svagt **positivt** i 2014-2019
(+0,33 till +1,08 pp) och genomgående **negativt** i 2020-2026. Ju mer aggressiv
regeln är, desto sämre — vid U=0 % byts 26 av 30 namn per panel och modellen
tappar 6 procentenheter.

### Delresultat som ändå är värt att bära med sig

Placebot för U=20 % i 2020-2026: slumpmässiga byten av lika många namn ger
−1,64 % (sd 0,77), regeln ger +0,10 % — **utanför bandet**. Regelns *val av
offer* är alltså bättre än slumpen med ungefär 1,7 procentenheter.

Men i 2014-2019 ligger den inom bandet, så kriteriet är inte uppfyllt.

Tolkningen: STACK_H:s innehav är redan så välvalda att omsättning förstör värde
även när man omsätter de *rätta* namnen. Urvalsförmågan finns; den räcker inte
för att betala för bytet.

---

## Reproduktion

```
tools/a1_rebalansfrekvens.py       research_k/a1_rebalansfrekvens_results.json
tools/a2_staggerade_kohorter.py    research_k/a2_staggerade_kohorter_results.json
tools/a3_poangutjamning.py         research_k/a3_poangutjamning_results.json
tools/a4_opportunity_cost_swap.py  research_k/a4_opportunity_cost_swap_results.json
```

Kvar av luckanalysen: A5 (intraperiod-ingång), A6 (re-entry på poängförbättring),
A7 (bytesbudget, minsta innehavstid), A8 (adaptiv holdingperiod, åldringsbonus,
partiell nedskalning, vinstskydd, regimchurn).

## Anmärkning utan åtgärd

`stack_h_motor.py`s egen utskrift jämför **årlig** omsättning (309 %) mot
registrets **per-panel**-tal (24 %). Samma storhet, olika enhet — 24 % × 13 =
312 %. Etikettmiss i utskriften, inget räknefel, och inget som rör den frysta
modellen.
