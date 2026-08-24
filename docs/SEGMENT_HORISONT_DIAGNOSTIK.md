# Fungerar momentum olika i olika segment?

Datum: 2026-08-16. **Diagnostiskt — ingen portföljregel, ingen befordran.**

Hypotesen: momentum borde vara kortare på små, olönsamma bolag och längre på
stora kvalitetsbolag, som drivs av annat. Vi har prövat horisonter *globalt*
(3+6, 6+12, 3+12, 6+18, rena 3m och 6m — alla föll), men ett globalt test tar ut
effekten mot sig själv om kort fungerar på små och lång på stora.

Segmentuppdelat var detta oprövat.

## Metod

PIT-segmentering per panel: storlekstercil på börsvärde (KPI 50, r12) och
lönsamhet på rörelsemarginal (KPI 29, r12) över/under noll, båda med senaste
`report_date` ≤ panel − 5 dagar. Spearman-IC mellan momentum över h veckor och
**nästa** panels avkastning, samt kvintilspread på H0:s faktiska poäng.

**Förbehåll som begränsar allt nedan:** KPI-historiken börjar på allvar 2017
(2015: 4 rader, 2016: 264). Det sena fönstret har 65 av 66 paneler; **det tidiga
har 43 av 79** och är i praktiken 2017-2019. Endast SEK-rapporterande bolag
ingår i storleksindelningen (90 % av raderna) — att räkna om EUR/USD över elva
år skulle införa mer fel än det löser.

## Steg 1 — horisontpreferens per segment (IC)

### 2020-2026

| Segment | n/panel | 3m | 6m | 12m | 18m | 24m | bäst |
|---|---:|---:|---:|---:|---:|---:|---|
| ALLA | 353 | +0,010 | +0,030 | +0,044 (t 2,6) | +0,045 (t 2,9) | +0,043 | 18m |
| liten | 98 | +0,010 | +0,043 (t 2,5) | **+0,054 (t 2,8)** | +0,050 | +0,044 | 12m |
| mellan | 97 | +0,010 | +0,020 | +0,032 | +0,026 | +0,036 | 24m |
| stor | 97 | −0,022 | −0,012 | +0,011 (t 0,4) | +0,019 | +0,008 | 18m |
| olönsam | 58 | −0,016 | +0,012 | +0,005 | +0,003 | +0,007 | 6m |
| lönsam | 250 | +0,003 | +0,020 | +0,035 (t 1,8) | +0,029 | +0,023 | 12m |
| stor+lönsam | 90 | −0,025 | −0,020 | +0,009 (t 0,3) | +0,013 | +0,004 | 18m |

### 2014-2019 (43 paneler)

| Segment | n/panel | 3m | 6m | 12m | 18m | 24m | bäst |
|---|---:|---:|---:|---:|---:|---:|---|
| ALLA | 274 | +0,035 | +0,046 | +0,072 (t 4,8) | +0,069 (t 4,9) | +0,066 | 12m |
| liten | 53 | +0,058 | +0,086 (t 3,1) | +0,100 (t 3,4) | **+0,103 (t 3,5)** | +0,089 | 18m |
| mellan | 52 | +0,009 | +0,005 | +0,052 | +0,048 | +0,037 | 12m |
| stor | 52 | +0,013 | +0,029 (t 0,9) | +0,023 | +0,025 | +0,008 | 6m |
| olönsam | 25 | +0,059 | +0,074 | +0,110 | +0,120 (t 3,3) | +0,103 | 18m |
| lönsam | 135 | +0,017 | +0,035 | +0,050 | +0,054 (t 3,0) | +0,042 | 18m |
| stor+lönsam | 49 | +0,025 | +0,039 | +0,032 | +0,045 (t 1,3) | +0,027 | 18m |

### Horisonthypotesen faller

**1 av 8 segment har samma bästa horisont i båda fönstren**, och den enda
(stor+lönsam, 18m) har t 0,5 respektive 1,3 — alltså inte skild från noll.

Riktningen vänder dessutom. I det sena fönstret är liten bäst på 12m och stor på
18m — *längre på stora*, som hypotesen säger. I det tidiga är liten bäst på 18m
och stor på 6m — *kortare på stora*, tvärtom.

Horisontpreferensen per segment är brus.

## Steg 2 — den ekonomiska spreaden, och varför den ändrar slutsatsen

IC mäter om ordningen är rätt. Det som går att handla är skillnaden mellan
topp- och bottenkvintilen. De två svarar inte samma sak.

| Segment | 2020-2026 spread/panel | t | per år | 2014-2019 spread/panel | t | per år |
|---|---:|---:|---:|---:|---:|---:|
| ALLA | +0,49 % | 0,79 | +6,5 % | +1,43 % | 4,14 | +20,3 % |
| liten | **−0,08 %** | −0,09 | −1,1 % | +1,66 % | 1,42 | +23,9 % |
| mellan | +1,08 % | 1,35 | +15,0 % | +1,81 % | 2,53 | +26,2 % |
| **stor** | **+0,14 %** | **0,21** | **+1,8 %** | **+0,27 %** | **0,41** | **+3,5 %** |
| olönsam | −0,91 % | −0,63 | −11,3 % | +2,22 % | 0,96 | +33,0 % |
| **lönsam** | **+1,15 %** | **2,04** | **+16,0 %** | **+1,17 %** | **2,43** | **+16,4 %** |
| liten+olönsam | −1,36 % | −0,70 | −16,3 % | — | — | — |
| stor+lönsam | +0,12 % | 0,19 | +1,6 % | +0,22 % | 0,32 | +2,9 % |

## Vad som faktiskt replikerar

**1. På stora bolag är signalen så gott som död — i båda fönstren.**
+1,8 %/år och +3,5 %/år i spread, mot +6,5 % och +20,3 % för hela universumet,
t 0,21 och 0,41. Momentum rangordnar inte stora bolag. Användarens intuition att
*"stora rider på helt andra signaler"* har stöd — men det vi kan säga är bara att
de inte rider på denna.

**2. Lönsamhet är den enda segmentering som replikerar med samma storlek.**
+16,0 %/år respektive **+16,4 %/år**, t 2,04 och 2,43. Två oberoende fönster,
nästan identiskt utfall. Det är den starkaste replikationen någon
segmentindelning gett i programmet.

**3. Olönsamma bolag är brus, inte kort momentum.** −11,3 %/år i det sena
fönstret, +33,0 %/år i det tidiga (t 0,96). Ingen horisont räddar dem. Hypotesen
att momentum är *kortare* där får inget stöd — det finns inget momentum där att
förkorta.

**4. Småbolagens starka IC går inte att handla i det sena fönstret.** IC +0,054
med t 2,8 — men kvintilspreaden är **−0,08 %**, alltså noll. Rangordningen är
rätt i genomsnitt medan ytterkanterna är brusdominerade. Detta är den viktigaste
metodvarningen i hela tabellen: **läs aldrig ett IC-tal som ett löfte om
handelsbar spread.**

## Koppling till det som redan är gjort

K8:s EBIT-grind gav **+2,09 pp drawdown gratis** utan att nå stöd på avkastning,
och K7 visade att lönsamhet förutsäger risk starkt (FCF-marginal t −5,89).
Diagnostiken här förklarar varför: grinden tar bort just det segment där
signalen inte har någon spread. Vinsten var riskminskning, inte urvalsförbättring
— och det är exakt vad man ska vänta sig av att stänga av ett brusigt delrum.

`OBS_C_PROFIT_GATE_FCF` ligger redan som observation-only i registret. FR-overlayen
nedviktar obekräftade namn med faktor 0,75, vilket är en svag form av samma sak.

## Vad detta INTE säger

Det säger inte att modellen ska byta universum eller delas i lager. Spreaden
mäts *inom* segment på ett universum som redan är storleksfiltrerat, och
kvintilspread är inte samma sak som vad en 30-namnsportfölj med vikttak och
hysteres faktiskt tjänar.

Det säger heller ingenting om orsaken. Att stora bolag inte rangordnas av
momentum kan bero på analytikertäckning, indexflöden, ägarstruktur eller att
vårt stora segment helt enkelt är för homogent — det går inte att avgöra här.

## Reproduktion

```
tools/segment_horisont_diagnostik.py
research_k/segment_horisont_diagnostik_results.json
```

---

# Steg 3 — bär lönsamheten över till en portföljregel?

Datum: 2026-08-16. Sju varianter mot STACK_H **och** mot den bara modellen, i
båda fönstren. Baslinjerna reproducerade (13,56 % / 27,82 % och 12,87 % / 29,98 %),
motorkontroll med regeln avstängd gav exakt baslinjen i båda fallen.

## Vad som skiljer detta från K8

K8 (2026-08-13) prövade en grind på **absolut** rörelseresultat (KPI 55 > 0) mot
VA_RETURN_CHALLENGER i **ett** fönster: CAGR +0,10 pp, maxDD +2,09 pp,
t_paired −0,10, klassad SVAGT STÖD. Här används **marginal** i stället för nivå,
**båda** fönstren, **två** baslinjer, och grind/vikttilt/ranktilt plus en
tvärsnittlig tröskel.

## Utfall mot STACK_H

| Variant | CAGR 26 | Δ | CAGR 19 | Δ | Δ19 endast täckta paneler | maxDD 26 | maxDD 19 |
|---|---:|---:|---:|---:|---:|---:|---:|
| grind: marginal ≤ 0 | 12,12 % | −1,44 % | 28,03 % | +0,21 % | +0,36 % | −0,80 % | +0,63 % |
| grind: marginal ≤ 5 % | 11,85 % | −1,71 % | 29,06 % | +1,24 % | +2,14 % | **+1,74 %** | **+1,07 %** |
| grind: nedersta tredjedelen | 12,12 % | −1,44 % | 29,25 % | +1,43 % | +2,48 % | **+2,19 %** | **+0,59 %** |
| grind: FCF-marginal ≤ 0 | 11,22 % | −2,34 % | 25,38 % | −2,44 % | −4,19 % | **+3,18 %** | **+1,20 %** |
| vikt ×0,75 vid marginal ≤ 0 | 13,70 % | +0,14 % | 27,72 % | −0,10 % | −0,17 % | −0,09 % | +0,01 % |
| vikt ×0,50 vid marginal ≤ 0 | 13,60 % | +0,04 % | 27,74 % | −0,08 % | −0,15 % | −0,14 % | +0,40 % |
| ranktilt vid marginal ≤ 0 | 13,48 % | −0,08 % | 27,89 % | +0,07 % | +0,11 % | −0,58 % | −0,32 % |

**Noll av sju positiva i båda fönstren på avkastning.** Mot den bara modellen är
två nominellt positiva (vikttilt ×0,75 och ×0,50), men deras tidiga delta är
+0,03 % och +0,09 % — alltså noll. Vikttilten gör nästan ingenting eftersom
FR-overlayen redan nedviktar obekräftade namn med 0,75.

## Men drawdown replikerar, och det gör inget annat i programmet

De tre strängare grindarna förbättrar maxDD i **båda** fönstren: +1,74/+1,07 pp,
+2,19/+0,59 pp och +3,18/+1,20 pp. Det är mer konsekvent än något
avkastningsresultat programmet producerat.

Priset är 1,4–2,3 procentenheter CAGR i det sena fönstret. K8 mätte samma
riskvinst som gratis; mot STACK_H och i två fönster är den det inte.

**Lönsamhet är ett riskinstrument, inte ett alfainstrument.** Det är samma
slutsats som K7 och K8 nådde, nu bekräftad i två fönster och med marginal i
stället för nivå.

## Varför diagnostikens +16 %/år inte kom med

Kvintilspreaden jämför de översta 20 % med de nedersta 20 % *bland lönsamma
bolag i hela universumet* — 250 namn i det sena fönstret. Portföljen håller
topp-30 av allt, och **bara 11–12 % av topp-30 är olönsamma** (3,1 av 28 med känd
marginal i det sena fönstret, 2,5 av 20,6 i det tidiga).

Grinden har alltså nästan ingenting att ta bort, och det den tar bort sitter
högt i rankningen. Momentumurvalet har redan gjort merparten av
lönsamhetssorteringen åt oss.

**Läsanvisning till resultatfilen:** `traffar`-kolumnen är 0,12–0,77 för
grindarna men 3,24 för vikttilten. Det är inte en inkonsekvens — räknaren mäter
*innehav som bryter mot regeln*, och en grind gör per konstruktion att sådana
innehav aldrig uppstår. För grindarna är det relevanta talet 3,1 namn per panel
som aldrig får komma in.

## Reproduktion

```
tools/lonsamhetstilt_mot_stack_h.py
research_k/lonsamhetstilt_mot_stack_h_results.json
```

---

# Steg 4 — poängfaktor och portföljkvot

Datum: 2026-08-16. Grinden läser bara **tecknet** på marginalen. Diagnostiken
mätte kvintilspread, alltså **magnitud**. Två former som använder magnituden:

* **A. Poängfaktor** — `poäng = (1−w) × H0 + w × percentilrank(marginal)`.
  H0 är redan i percentilenheter, så skalorna är jämförbara. Namn utan data får
  medianpercentilen 0,5, alltså neutralt.
* **B/C. Portföljkvot** — minst q av 30 måste vara lönsamma (B), eller minst q i
  översta marginaltredjedelen den panelen (C). En konstruktionsregel, inte ett
  urvalsfilter: den släpper in olönsamma namn så länge de är få nog.

Rum att binda på: av topp-30 är 24,9 lönsamma och 11,4 i toppmarginaltredjedelen
i det sena fönstret; 17,0 och 7,8 i det tidiga.

## A — poängfaktorn har en platå, inte en spik

Ett grovt svep såg ojämnt ut (w=0,05 plus, 0,10 minus, 0,20 plus). Ett finare
svep visar att w=0,10 är avvikelsen, inte toppen:

| w | Δ 2020-2026 | KI 2020-2026 | Δ 2014-2019 |
|---:|---:|---|---:|
| 0,100 | −0,56 % | [−3,67 %, +2,54 %] | −0,04 % |
| 0,125 | +0,04 % | [−3,75 %, +3,52 %] | +1,34 % |
| **0,150** | **+1,19 %** | [−2,60 %, +4,99 %] | **+1,98 %** |
| **0,175** | **+1,20 %** | [−2,22 %, +4,58 %] | +1,47 % |
| 0,200 | +0,82 % | [−2,86 %, +4,23 %] | +1,97 % |
| 0,225 | +0,34 % | [−3,94 %, +3,92 %] | +1,73 % |
| 0,250 | −1,56 % | [−5,94 %, +2,88 %] | +1,33 % |
| 0,300 | −1,80 % | [−6,60 %, +2,38 %] | +2,03 % |

**Positiv i båda fönstren för w mellan 0,125 och 0,225.** Det tidiga fönstret är
positivt hela vägen till 0,30. Samtliga konfidensintervall i det sena fönstret
täcker dock noll med bred marginal.

## Placebot avgör, och det delar fönstren

Samma inblandning men med en **slumpmässigt omkastad** faktor i stället för
marginal, 30 dragningar:

| w | Fönster | Placebo ± 2 sd | Regelns Δ | Utfall |
|---:|---|---|---:|---|
| 0,20 | 2020-2026 | [−5,41 %, +1,29 %] | +0,82 % | **inom — kan inte skiljas från slump** |
| 0,20 | 2014-2019 | [−2,30 %, +1,62 %] | +1,97 % | **UTANFÖR** |
| 0,30 | 2020-2026 | [−8,65 %, +1,51 %] | −1,80 % | inom |
| 0,30 | 2014-2019 | [−2,66 %, +1,97 %] | +2,03 % | **UTANFÖR** |

Placebomedlet är kraftigt negativt i det sena fönstret (−2,06 %, sd 1,67 %): att
blanda in **vilken** faktor som helst späder ut momentumsignalen och kostar. Mot
den bakgrunden är +0,82 % ungefär 2,9 pp bättre än ren utspädning — men
placebospridningen är så stor att det inte går att skilja från tur.

I det tidiga fönstret bär marginalen däremot information utöver utspädning.
**Samma fönsterdelning som allt annat i programmet.**

## B och C — kvoter faller entydigt

| Variant | Δ 26 | Δ 19 | byten/panel | maxDD 26 |
|---|---:|---:|---:|---:|
| minst 27 lönsamma av 30 | −1,04 % | +0,35 % | 1,2 / 2,3 | −2,66 % |
| minst 28 lönsamma av 30 | −1,04 % | +0,42 % | 1,7 / 2,5 | −2,96 % |
| minst 29 lönsamma av 30 | −2,71 % | −0,27 % | 2,1 / 2,8 | −4,47 % |
| minst 30 lönsamma av 30 | −3,66 % | +0,13 % | 2,6 / 3,1 | −5,77 % |
| minst 10 i toppmarginaltredjedel | −0,72 % | −0,36 % | 0,6 / 0,8 | −2,44 % |
| minst 15 i toppmarginaltredjedel | −1,88 % | −1,61 % | 2,6 / 1,9 | −1,14 % |
| minst 20 i toppmarginaltredjedel | −1,28 % | −2,01 % | 5,0 / 3,2 | −2,09 % |

Noll av sju. Kvoten på hög marginal (C) är negativ i **båda** fönstren — den
renaste avvisningen i hela lönsamhetsspåret.

**Och kvoterna gör drawdown SÄMRE** (−1,14 till −5,77 pp), tvärtemot grinden som
förbättrade den. Att tvinga in lönsamma namn längre ned i rankningen tillför risk.

## Implementationsfyndet som är större än effekterna

Kvot q=30 och grinden "marginal ≤ 0" är samma ekonomiska villkor: portföljen ska
bara innehålla lönsamma bolag. De ger **12,12 % mot 9,90 %** — en skillnad på
**2,22 procentenheter**.

Skälet är ordningen. Grinden filtrerar kandidatlistan **före** hysteresen, så
urvalet fylls på djupare ned i rankningen. Kvoten byter **efter** hysteresen och
tvingar fram extra omsättning för att uppfylla villkoret.

Det är större än nästan varje effekt vi mätt i hela programmet. **Var i kedjan en
regel placeras spelar större roll än vilken regel det är** — och det gäller
retroaktivt varje regeltest där placeringen inte prövades i båda ordningarna.

## Reproduktion

```
tools/lonsamhet_poangfaktor_och_kvot.py
research_k/lonsamhet_poangfaktor_och_kvot_results.json
```
