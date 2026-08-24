# Historiskt universum ur Skatteverket, jämfört med EODHD-arkivet

Datum: 2026-08-08. **Inget har migrerats eller ändrats.** Legacy lästes read-only.
Verktyg: `tools/skatteverket_universe.py` (fristående v2-kod, ingen legacy-import).
Artefakter: `docs/probes/skatteverket_facts.json`, `docs/probes/universum_ar_for_ar.json`,
rådata i `raw/skatteverket/` (930 sidor, verbatim bytes + sha256 per hämtning).

Skatteverket används **enbart** för att fastställa vilka noterade bolag som funnits och när
de noterades/avnoterades — aldrig som källa för fundamenta.

---

## 1. Den återskapade listan

Skatteverkets A–Ö-index innehåller **1 648 bolag**, inklusive sedan länge avnoterade.

| | tidigare (legacy) | återskapad (v2) |
|---|---|---|
| bolag med hämtad sida | 727 (44 %) | **1 648 (100 %)** |
| tolkade | 714 | **1 639** |
| varav **avnoterade** | 88 | **634** |
| varav noterade | 591 | 883 |
| varav okänd status | 35 | 122 |
| ej tolkbar sidstruktur | 4 | 9 |

Den gamla listan hade **88 avnoterade bolag. Den återskapade har 634** — sju gånger fler.
Skälet är att den tidigare extraktionen matchades mot *dagens* universum och därför ärvde
precis den bias som skulle mätas.

930 sidor hämtades från skatteverket.se med 1,2 s paus, 0 fel. Varje sida sparades som
mottagna bytes med sha256 på samma bytes — den defekt som underkände legacys rådatalager
upprepas inte.

---

## 2. Matchningstaket — måste läsas före tabellerna

Skatteverket har bara **bolagsnamn**; EODHD har namn, kod och (ibland) ISIN. Kopplingen kan
därför bara göras på namn, och namnmatchning misslyckas ibland även när bolaget finns i båda.

Taket mäts på bolag som **enligt Skatteverket är noterade idag** och alltså per definition
måste finnas i EODHD:s aktiva katalog:

| matchning | träff |
|---|---|
| exakt normaliserat namn | 709/883 = **80 %** |
| + prefix/fuzzy (cutoff 0,90) | 796/883 = **90 %** |

**Taket är alltså 90 %.** En årgång som når 90 % täckning är i praktiken fullständig; allt
under är en verklig lucka. Kolumnen "mot tak" nedan är täckningen dividerad med 0,90.

---

## 3. Avnoteringar per år: Skatteverket som facit, EODHD som utfall

| år | SKV avnoteringar | i EODHD (exakt) | i EODHD (+fuzzy) | täckning | **mot tak** |
|---|---|---|---|---|---|
| 2010 | 30 | 2 | 3 | 10 % | **11 %** |
| 2011 | 31 | 0 | 0 | 0 % | **0 %** |
| 2012 | 40 | 0 | 2 | 5 % | **6 %** |
| 2013 | 22 | 0 | 1 | 5 % | **5 %** |
| 2014 | 25 | 3 | 5 | 20 % | **22 %** |
| 2015 | 23 | 10 | 11 | 48 % | 53 % |
| 2016 | 14 | 6 | 7 | 50 % | 55 % |
| 2017 | 18 | 7 | 9 | 50 % | 55 % |
| 2018 | 30 | 12 | 13 | 43 % | 48 % |
| 2019 | 20 | 6 | 6 | 30 % | 33 % |
| 2020 | 36 | 13 | 13 | 36 % | **40 %** |
| 2021 | 27 | 15 | 16 | 59 % | 66 % |
| **2022** | 42 | 33 | 37 | 88 % | **98 %** |
| 2023 | 38 | 23 | 25 | 66 % | 73 % |
| 2024 | 59 | 40 | 44 | 75 % | 83 % |
| 2025 | 65 | 44 | 51 | 78 % | 87 % |
| 2026 (delår) | 28 | 23 | 24 | 86 % | 95 % |

Sammanslaget:

| period | SKV avnoteringar | funna i EODHD | täckning | mot tak |
|---|---|---|---|---|
| 2010–2014 | 148 | 11 | 7 % | **8 %** |
| 2015–2021 | 168 | 75 | 45 % | 50 % |
| 2022–2026 | 232 | 181 | 78 % | **87 %** |

### Prisserierna

För de avnoterade som EODHD faktiskt har finns nästan alltid en fullständig prisserie:
`delisted/`-manifestet rapporterar `eod_ok 694, div_ok 694, splits_ok 694, errors []`.
I årsuppställningen har i stort sett varje matchat bolag en serie, och serien sträcker sig
fram till avnoteringsdagen i 13/13 (2020), 29/32 (2022) och 33/40 (2024) av fallen.

**Problemet är alltså inte prisseriernas kvalitet utan vilka bolag som över huvud taget
finns i arkivet.** Ett bolag som saknas har ingen serie alls — det syns aldrig i panelen,
och dess (typiskt dåliga) avkastning fram till avnoteringen räknas aldrig med.

Ett hårt, matchningsoberoende faktum bekräftar bilden: **arkivets tidigaste sista
handelsdag är 2013-07-23.** Inget instrument i `delisted/` slutade handlas före det. De
123 bolag Skatteverket registrerar som avnoterade 2010–2013 kan därför per konstruktion
inte ha någon prisserie i arkivet.

---

## 4. Universumstorlek per år

| år | SKV noterade vid årets slut | varav funna i EODHD | täckning |
|---|---|---|---|
| 2010 | 554 | 282 | 51 % |
| 2013 | 540 | 339 | 63 % |
| 2016 | 757 | 525 | 69 % |
| 2019 | 938 | 683 | 73 % |
| 2022 | 1 124 | 855 | 76 % |
| 2025 | 1 052 | 803 | 76 % |

Att täckningen av *noterade* bolag stiger från 51 % (2010) till 76 % (2022+) är delvis
matchningsbrus, men mönstret är detsamma som för avnoteringarna: ju längre bakåt, desto
sämre representation.

---

## 5. Svar på frågorna

**Vilka avnoterade bolag täcker EODHD respektive saknar?**
Av 634 avnoterade bolag i Skatteverkets historik återfinns 181 av de 232 som avnoterades
2022–2026, men bara 11 av de 148 som avnoterades 2010–2014. Namnexempel på saknade finns
per år i `docs/probes/universum_ar_for_ar.json`.

**Prisseriernas täckning för dessa?**
Fullständig för de bolag som finns (694/694 med eod, div och splits, 0 fel), och obefintlig
för dem som saknas. Arkivet innehåller ingen serie som slutar före 2013-07-23.

**Har 2010–2019 faktiskt survivorship-problem?**
**Ja, och det är allvarligt.** 2010–2014 saknas 93 % av alla avnoteringar. 2015–2021 saknas
ungefär hälften. Ett backtest på den perioden mäter i praktiken en portfölj där merparten av
bolagen som gick under aldrig fanns med.

**Tidigaste år där universum + prisdata kan anses tillräckligt komplett?**
**2022.** Det är första året som når matchningstaket (98 % av tak). 2021 ligger på 66 % av
tak och 2020 på 40 % — bägge har materiella luckor.

Två förbehåll:
- **2023 är den svaga punkten i den goda perioden** (73 % av tak) och sticker ut mot 2022
  (98 %) och 2024–2025 (83–87 %). Orsaken är inte utredd.
- Ett strikt krav på ≥90 % av tak varje enskilt år skulle lämna endast 2022 och 2026, vilket
  inte räcker för en modell med 52-veckors target. Med start 2022 accepteras en kvarvarande
  lucka på 51 av 232 avnoteringar (22 %) — en storleksordning mindre än 2010–2013.

### Korrigering av min tidigare rekommendation

Jag föreslog tidigare 2020-01-01. Det byggde på EODHD:s egna avnoteringsräkningar
(42 st 2020 såg rimligt ut) **utan nämnare**. Med Skatteverket som facit hade 2020
36 verkliga avnoteringar varav EODHD har 13 — 40 % av tak. **Rekommendationen flyttas till
2022-01-01.**

---

## 6. Vad detta inte avgör

- Kopplingen SKV↔EODHD är namnbaserad. Enskilda bolag kan vara felklassade; det är
  *årsmönstret* som bär, inte enskilda rader.
- 122 bolag har status "okänd" i Skatteverkets sidor och ingår inte i avnoteringsräkningen.
  De kan innehålla ytterligare avnoteringar.
- Fundamentafrågan är oförändrad: även med ett survivorship-säkert prisuniversum saknas
  fundamenta för de avnoterade bolagen (50 av 669 har ISIN-träff i Börsdata). Valet mellan
  väg A/B/C i `UNIVERSUM_OCH_KALLBESLUT.md` kvarstår.
