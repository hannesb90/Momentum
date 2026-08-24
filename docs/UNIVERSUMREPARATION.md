# Reparation av det historiska universumet

Datum: 2026-08-08. **Inget migrerat, ingen modellträning.** Legacy read-only.
Verktyg: `tools/instrument_master.py`. Artefakter: `docs/probes/instrument_master.json`,
`docs/probes/missing_price_history.json`.

Frågan: går det att bygga ett survivorship-säkert prisuniversum tidigare än 2022, i stället
för att kasta 2010–2021?

**Kort svar: ja — men svaret beror helt på vilken marknadsplats universumet omfattar.**
För Nasdaq Stockholm är täckningen fullständig från **2020**. För Spotlight och Nordic SME
blir den aldrig bra.

---

## 1. instrument_master

1 648 bolag ur Skatteverkets aktiehistorik, 1 647 tolkade. Per bolag: namn,
**organisationsnummer** (815/930 nyhämtade sidor, ~88 %), status, första notering,
avnoteringsdatum och -orsak, namnbyten, corporate actions samt **bytestabellen**
(uppköp/fusion → efterföljande bolag). 637 är avnoterade.

## 2. Entity resolution med stabila identifierare

I stället för namn-mot-namn används en kedja med registrerad metod per rad. Bryggorna
hittades i legacy: `borsapi/companies_all_*.json` (namn/ISIN/ticker), MFN-posternas
`isins`+`tickers`, och Börsdatas instrumentlista.

| metod | antal |
|---|---|
| ISIN via eget namn | 705 |
| exakt namn | 388 |
| ISIN via alternativt namn (namnbyte) | 45 |
| fuzzy namn | 43 |
| exakt namn via alternativt namn | 23 |
| via efterföljare (uppköp/fusion) | 15 |
| **ingen träff** | **428** |

Effekten på avnoteringstäckningen, mot ren namnmatchning tidigare:

| år | namnmatchning | **med identifierarkedja** |
|---|---|---|
| 2022 | 88 % | **93 %** |
| 2024 | 75 % | **81 %** |
| 2025 | 78 % | **83 %** |
| 2026 | 86 % | **93 %** |

## 3. De kvarvarande saknade 2022–2026 granskade en och en

41 bolag. Fördelningen är entydig:

- **Spotlight Stock Market och Nordic SME (NGM): 30 av 41.**
- Utlandsnoterade parallellnoteringar: Nexstim Oyj, Linkfire A/S, Eevia Health Oy, Zwipe AS.
- Aktieslagshändelser, inte bolagsdöd: Akelius Residential (**D-aktien** avnoterad, bolaget
  finns kvar).
- **Nasdaq Stockholm: ett enda bolag** (Aligro Planet Acquisition Company, en SPAC).

## 4. Marknadsplats är den förklarande variabeln

Avnoteringar med prisserie i EODHD, per marknadsplats och år:

| år | Nasdaq Stockholm | First North | Spotlight | NGM/Nordic SME |
|---|---|---|---|---|
| 2010 | 3/12 (25 %) | 0/2 | 0/13 | 0/3 |
| 2011 | 2/9 (22 %) | 0/8 | 1/11 | 0/4 |
| 2012 | 3/6 (50 %) | 0/11 | 0/21 | 0/2 |
| 2013 | 0/5 (0 %) | 0/4 | 0/10 | 0/3 |
| 2014 | 4/7 (57 %) | 1/4 | 1/12 | 0/1 |
| 2015 | 5/8 (62 %) | 6/10 (60 %) | 1/4 | 0/1 |
| 2016 | 3/7 (43 %) | 3/4 (75 %) | 0/3 | – |
| 2017 | **4/4 (100 %)** | 5/6 (83 %) | 1/7 | 0/1 |
| 2018 | 6/11 (55 %) | 7/11 (64 %) | 1/6 | 0/1 |
| 2019 | 7/8 (88 %) | 0/7 (0 %) | 1/2 | 0/3 |
| **2020** | **13/13 (100 %)** | 0/7 (0 %) | 0/13 | 1/3 |
| **2021** | **11/11 (100 %)** | 6/10 (60 %) | 0/4 | 0/2 |
| **2022** | **14/14 (100 %)** | **19/19 (100 %)** | 5/7 | 1/2 |
| 2023 | 4/5 (80 %) | 16/19 (84 %) | 4/8 | 0/6 |
| 2024 | **9/9 (100 %)** | 31/34 (91 %) | 8/11 | 0/5 |
| 2025 | **14/14 (100 %)** | 27/30 (90 %) | 9/14 | 4/7 |
| 2026 | **2/2 (100 %)** | **16/16 (100 %)** | 5/6 | 2/3 |
| **totalt** | **104/145 (72 %)** | 137/202 (68 %) | **37/152 (24 %)** | **8/47 (17 %)** |

**Nasdaq Stockholm är fullständigt täckt varje år från 2020** (undantag 2023: 4 av 5).
First North är fullständigt först från 2022 och har två helt tomma år (2019 och 2020, 0/7
båda). Spotlight och NGM är otäckta genom hela perioden.

## 5. missing_price_history

`docs/probes/missing_price_history.json`: **336 avnoterade bolag utan prisserie**, med
organisationsnummer, avnoteringsdatum, orsak och upplösningsmetod.

**Verifierat att listan är äkta lucka, inte matchningsfel:** vid lös tokenmatchning
(Jaccard ≥ 0,6) mot hela EODHD-katalogen får endast **2 av 336** någon träff alls —
Akelius D-aktie och Eevia Health. Övriga **334 finns inte i EODHD över huvud taget.**

## 6. Finns serierna någon annanstans?

| källa | utfall |
|---|---|
| `cache/eodhd_delisted/` (84 tickers, separat cache) | delmängd av arkivet, inget nytt |
| `borsapi/companies_all_*.json` (965 namn) | **0 av 336** återfinns |
| EODHD-katalogen med lös matchning | 2 av 336 |
| Börsdata | avnoterade instrument raderas hos leverantören (tidigare fastställt) |

Ingen av de saknade serierna finns alltså någon annanstans i legacy. Att hämta dem skulle
kräva en ny leverantör med historik för avnoterade svenska mikrobolag (Spotlight/NGM) —
en inköpsfråga, inte en teknisk.

---

## 7. Slutsats om startdatum

Startdatumet är inte en egenskap hos datan utan hos **universumdefinitionen**:

| universum | tidigaste år med i praktiken fullständig avnoteringstäckning |
|---|---|
| **Nasdaq Stockholm** | **2020** (100 % 2020, 2021, 2022; 88 % 2019) |
| Nasdaq Stockholm + First North | **2022** (First North är 0/7 både 2019 och 2020) |
| Alla marknadsplatser inkl. Spotlight/NGM | uppnås aldrig; ~85 % som bäst |

Eftersom modellen handlar likvida storbolag — Spotlight- och NGM-mikrobolag filtreras ändå
bort av likviditets- och börsvärdeskraven — är **Nasdaq Stockholm det relevanta
universumet, och då är 2020 försvarbart**. Det är två år tidigare än den slutsats ren
namnmatchning gav, och reparationen var alltså rätt väg.

För 2010–2013 finns däremot ingen räddning: EODHD:s arkiv innehåller ingen serie som slutar
före 2013-07-23, och 2010–2013 saknar 82 av 90 avnoteringar oavsett marknadsplats.

**Rekommendation:** `dataset_v1.0` byggs med Nasdaq Stockholm-universum från **2020-01-01**,
med `missing_price_history` som permanent, versionerad bilaga så att kvarvarande lucka alltid
kan redovisas. Om First North ska ingå flyttas startdatum till 2022-01-01.

Frågan om fundamentatäckning (spår B) är fortfarande separat och obesvarad.
