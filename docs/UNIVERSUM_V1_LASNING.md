# Verifiering och låsning av universum för dataset_v1.0

Datum: 2026-08-08. **Ingen modellträning, ingen migrering.** Legacy read-only.
Underlag: `docs/probes/instrument_master.json`, `docs/probes/missing_price_history.json`,
`docs/probes/prisnivabrott.json`.

---

## 1. Verifiering bolag för bolag: Nasdaq Stockholm 2020–2026

**68 avnoteringar** enligt Skatteverket. **67 har prisserie i EODHD. En saknas.**

| år | avnoteringar | med serie | saknas |
|---|---|---|---|
| 2020 | 13 | 13 | 0 |
| 2021 | 11 | 11 | 0 |
| 2022 | 14 | 14 | 0 |
| 2023 | 5 | 4 | **1** |
| 2024 | 9 | 9 | 0 |
| 2025 | 14 | 14 | 0 |
| 2026 (delår) | 2 | 2 | 0 |

### 2023 års 80 % — förklarad

Den enda saknade observationen i hela perioden:

| bolag | orgnr | avnoterad | typ | survivorship-risk |
|---|---|---|---|---|
| Aligro Planet Acquisition Company AB | 559301-7261 | 2023-08-23 | **SPAC** (förvärvsbolag utan verksamhet) | **försumbar** |

Ett SPAC har ingen rörelse, ingen omsättning och inga fundamenta, och handlas nära sitt
spärrade kapital. Det ingår inte i ett investerbart storbolagsuniversum. Att EODHD i övrigt
täcker svenska SPAC:ar framgår av att Creaspac AB (`CPAC-SPAC`) finns med full serie —
Aligro är alltså en enskild lucka hos leverantören, inte ett systematiskt bortfall av en
bolagstyp.

**"80 % 2023" var 4 av 5, där den femte var ett SPAC.**

### Kontroll av att klassificeringen inte döljer något

- **Okänd marknadsplats 2020–2026:** 1 bolag (Phase Holographic Imaging, har serie).
- **Status "okänd" i Skatteverkets sida, aktivitet 2020+:** 41 bolag, varav 8 utan serie:
  Atari SA SDB, Italeaf S.p.A SDB, GiG Software PLC SDB, District Metals Corp.,
  Smart Wires Technology Ltd, Smart Valor AG, Oatly Group AB, Rederi AB Gotland.
  **Samtliga är depåbevis (SDB), utländska bolag eller icke-Nasdaq-handel** — ingen är en
  svensk Nasdaq Stockholm-stamaktie. De påverkar inte universumet.

**Slutsats steg 1: täckningskontrollen håller.** För Nasdaq Stockholm 2020–2026 saknas en
enda observation, och den är ett SPAC utanför det investerbara universumet.

---

## 2. Men täckning är inte samma sak som korrekthet — två fynd som blockerar frysning

Verifieringen avslöjade två problem i prisryggraden som är oberoende av survivorship.

### 2.1 Sex "avnoteringar" är bolagshändelser, inte bolagsdöd

Serier som fortsätter ≥3 månader efter Skatteverkets avnoteringsdatum:

| bolag | avnoterad | serie t.o.m. | tolkning |
|---|---|---|---|
| Nordic Waterproofing Holding A/S | 2020-11-25 | 2025-03-24 (+52 mån) | flytt A/S → svensk AB, handeln fortsatte |
| Besqab Bostadsutveckling AB | 2024-04-11 | 2026-07-24 (+27 mån) | omstrukturering, noterad efterföljare |
| HiQ International AB | 2020-11-13 | 2021-12-20 (+13 mån) | **se 2.2 — datafel** |
| Cavotec SA | 2025-07-30 | 2026-07-24 (+12 mån) | fortsatt handel |
| SSM Holding AB | 2021-01-07 | 2021-12-20 (+11 mån) | uppköpsprocess pågick under året |
| Feelgood Svenska AB | 2021-08-06 | 2021-12-17 (+4 mån) | uppköpsprocess |

Inget av dessa är en survivorship-händelse. **Avnotering i Skatteverkets mening är inte
detsamma som att bolaget upphör att vara investerbart** — den distinktionen måste kodas
explicit i VALIDATED, annars räknas namnbyten och redomiciliering som konkurser.

Ingen serie slutade ≥2 månader *före* sitt avnoteringsdatum, vilket är den viktigare
riktningen: det finns inga trunkerade serier som skulle dölja en nedgång.

### 2.2 Nivåbrott i prisserierna — 206 av 1 598 serier (12,9 %)

Systematisk genomsökning efter dygnsförändringar utanför intervallet [1/20, 20×]:

| grupp | serier | med nivåbrott |
|---|---|---|
| delisted | 590 | 74 (12,5 %) |
| active | 1 008 | 132 (13,1 %) |

Minst fyra distinkta felklasser:

1. **Sentinelvärdet 1 000 000,00 som "kurs".** Malmbergs, BTS-B, CTT, Fagerhult, Havsfrun,
   SkiStar, Svolder, FastPartner — alla med `close` exakt 1 000 000,00 dagen före brottet,
   koncentrerat kring 1999-12-30 → 2000-01-03. Det är ett platshållarvärde, inte ett pris.
2. **Instrumentåteranvändning efter uppköp.** `HIQ` faller **2020-11-06 från 72,10 till
   0,0945** (0,0013×) och fortsätter i 275 dagar på öreniv. HiQ köptes av Triton för 73 kr.
   Naivt använd ger serien en falsk −99,9 %-vecka. **Detta är survivorship-problemets
   spegelbild: i stället för att radera en förlorare skapas en fiktiv katastrofförlust.**
3. **Leverantörsbrett datum-artefakt 2019-06-07 → 2019-06-10.** Promore Pharma, Neodynamics,
   Papilly, Africa Energy och Oscar Properties Pref B bryter alla på exakt samma dagpar.
   Det är en händelse hos leverantören, inte i marknaden.
4. **Ojusterade historiska nivåer.** RusForest 29 117 → 2,00, Midway A 14 638 → 25,37,
   Hemfosa 1 830 → 56 — pre-split-värden som aldrig justerats.

Utöver dessa finns äkta corporate actions som ser likadana ut i rådata, t.ex. Lundin Energy
2022-06-20 (444 → 10,23) vid Aker BP-transaktionen. **Automatiskt bortfiltrerande vore fel** —
klassificering krävs, inte klippning.

Fullständig lista: `docs/probes/prisnivabrott.json`.

---

## 3. Låsning

**Universumdefinitionen låses:**

```
dataset_v1.0.universum:
  marknadsplats : Nasdaq Stockholm
  startdatum    : 2020-01-01
  facit         : Skatteverkets aktiehistorik (instrument_master, 1 648 bolag)
  prisryggrad   : EODHD ST-arkiv (active + delisted)
  nyckel        : ISIN i första hand, EODHD Code sekundärt, ticker ALDRIG för avnoterade
  bilaga        : missing_price_history.json (336 bolag), versionerad
```

**Uttryckligt förbehåll, som ska följa med varje resultat byggt på v1.0:**

> `dataset_v1.0` representerar **inte hela svenska börsen.** Det omfattar Nasdaq Stockholm
> från 2020-01-01. Spotlight Stock Market och NGM/Nordic SME är medvetet uteslutna eftersom
> deras avnoterade bolag saknas i prisdatan till 76–83 % och universumet därför inte kan
> göras survivorship-säkert för dem. First North är uteslutet ur v1.0 eftersom täckningen är
> 0/7 både 2019 och 2020 och fullständig först från 2022. Resultat från v1.0 gäller svenska
> huvudlistan, inte småbolagssegmentet.

**Frysning kan ännu inte ske.** Universumet är avgjort, men prisryggraden har 206 serier med
nivåbrott (§2.2) och sex felklassade avnoteringar (§2.1). Dessa måste klassificeras i
VALIDATED innan `dataset_v1.0` kan få en hash och frysas.

---

## 4. Nästa steg

- **Spår A, återstår:** klassificera de 206 nivåbrotten (sentinel / instrumentåteranvändning /
  leverantörsartefakt / äkta corporate action) och koda avnotering kontra bolagshändelse.
- **Spår B, påbörjas nu:** fullständig revision av fundamentadatan mot exakt detta universum —
  PIT-korrekthet, historisk täckning per feature/år/bolag, avnoterade bolag, definitioner,
  skalor/extremvärden, rapportdatum och källkonsistens. Varje möjlig fundamentalfeature
  klassificeras GODKÄND / KRÄVER ÅTGÄRD / UTESLUTEN.
