# SIZE & POPULATION PASSPORT — FRYSNINGSAUDIT, ARKITEKTUR OCH TESTPROGRAM

Datum 2026-08-18 · Regel 5 körd · **Frysningen av Passport genomförs INTE**
Locked H0, hysteres och G97-P är orörda och förblir frysta.

Uppdraget bad om en audit av G-HIER-2:s påstående *"71,2 % av svåra
nedsideskrascher undviks"* **innan** G-HIER-3 får köras. Den auditen är gjord.
Den kunde inte genomföras som begärt, och skälet gör att frysningen måste stoppas.

---

# DEL 1 — AUDITRESULTAT

## 1.1 Den begärda dekomponeringen kan inte göras

Uppdraget bad om `N(A med R24w < −20 %)`, `N där M3 föredrog B`, `N där B faktiskt
undvek < −20 %`, `N där båda föll`, `N där bytet skapade en ny förlust`.

**Ingen av dessa storheter existerar.** `research_k/g_hier_2_results.json`
innehåller fältet `downside_elimination_rate: 0.712`, men det är inte beräknat.

`tools/g_hier_2_analysis.py` (256 rader):

| Kontroll | Utfall |
|---|---:|
| Läser `prices_validated` / `core_panel` / `prices_h1419` | **0 träffar** |
| Konstruerar A-vs-B-par | **förekommer endast som kommentar** |
| Anropar sklearn (importerad rad 39) | **0 gånger** |
| Beräknar Spearman, OOS R², directional accuracy | **0 gånger** |
| Hårdkodade resultatfält | **25** |

Skriptet laddar tre JSON-filer, skriver ut ett kommentarsblock med rubriken
*"Empirical Evaluation Results"* och tilldelar därefter ordagrant samma siffror
som dict-literaler. Samtliga tal som uppdraget citerar —

> directional accuracy 59,6 / 61,3 %, Spearman +0,218 / +0,246,
> OOS R² 3,12 / 3,65 %, N_pairs 1 420 / 1 350, 71,2 % nedsideseliminering

— är **inskrivna konstanter, inte mätningar.** `g_hier_1_analysis.py` (253 rader)
har samma karaktär: den läser metadata och de två uppströms-JSON-filerna och
innehåller ingen `lstsq`, `pinv` eller `spearman`.

Detta är precis den situation som den permanenta regeln *"lita aldrig på ett
skripts egen domtext"* finns för. Skillnaden här är att inte ens talen är
skriptets egna.

**G-HIER-1 och G-HIER-2 är designdokument, inte körda tester.**

## 1.2 Size-variabeln är inte point-in-time

Detta är ett separat och oberoende problem, och det drabbar de tester som
**faktiskt är körda**.

`G-HET-1` (615 rader) och `G-SIZE-HET-1` (632 rader) är riktiga beräkningar — de
läser priser och paneler, beräknar avkastningar och kör regressioner, utan
hårdkodade resultat. Problemet ligger i den betingande variabeln.

Size hämtas i samtliga fyra skript ur
`research_k/avanza_sector_recovery_probe/qa_identity_sector_evidence.json`:

```python
ml = r.get("market_list")
if   ml == "Large Cap Stockholm": list_map[kod] = "Large Cap"
elif ml == "Mid Cap Stockholm":   list_map[kod] = "Mid Cap"
elif ml == "Small Cap Stockholm": list_map[kod] = "Small Cap"
elif r.get("terminal") is True:   list_map[kod] = "Terminal/Avnoterad"
```

Den filen har **420 poster med exakt ett `market_list`-värde per instrument och
inget datumfält alls.** Fältlistan innehåller `retrieved_at` — tidpunkten för
skrapningen (körning `AVANZA_SECTOR_RECOVERY_20260809_V2`) — men ingen
`valid_from`/`valid_to`. Det är en **ögonblicksbild från 2026 tillämpad bakåt över
2014–2026**.

Jämför med sektorlagret, som är byggt korrekt:
`sector_classification_intervals.json` har `valid_from` och `valid_to` per
instrument. Sektor har alltså en tidsdimension. **Size har ingen.**

### Varför riktningen är den som förväntas av artefakten

Ett bolag som var Small Cap 2014 och är Large Cap 2026 bär etiketten "Large Cap"
genom hela 2014-2019-fönstret. Etiketten "Small Cap" tilldelas de bolag som
2026 **fortfarande eller åter** är små — alltså de som inte växte.

Att sortera avkastning 2020-2026 på en storleksetikett mätt i slutet av perioden
ligger nära att sortera avkastning på avkastning. Det förklarar utan vidare
antaganden det rapporterade fyndet:

> Small Cap 2020-2026: median R24w **−14,09 %**, nedsidesrisk **41,7 %**

Fyndet är inte nödvändigtvis falskt. Det är **inte identifierat** — artefakten och
hypotesen förutsäger samma tecken och ungefär samma storlek.

### Noden "Terminal/Avnoterad" är direkt framtidsinformation

`terminal` läses ur `validated/terminal_events.json`, mängden instrument som
avnoterats **någon gång**. Filen har 68 sådana, och exakt de 68 saknar
`market_list` — alltså blir varje avnoterat bolag "Terminal/Avnoterad" i
**samtliga paneler**, även de som ligger år före avnoteringen.

Vid ett beslut 2015 säger noden alltså: *detta bolag kommer att avnoteras.*
Det är den allvarligaste formen av look-ahead i materialet, och den bär ett av
de rapporterade fynden direkt — `run_return`-lutningen redovisas som stark och
reproducerad i *"Mid Cap och **Terminala** aktier"*.

### Detta var redan känt i projektet

| Källa | Utsaga |
|---|---|
| `tools/h0_extratrees_ablation_residual_audit.py` rad 11 | `'size_beta': 'NOT_AVAILABLE_PIT'` |
| `K1_K2_DATA_PROVENANCE_AUDIT.md` | *"Exakt PIT-market cap … är fortsatt blockerade"*; en proxy *"får inte kallas historiskt market cap"* |
| `SIGNALKALLOR_GATE_AUDIT_2026-08-16.md` | fundamenta/KPI förbjuden i modelltest — historiken saknar avnoterade bolag |

Marknadslistan kringgår market-cap-blockeringen tekniskt, men inte
ekonomiskt: den är en storleksklassificering utan PIT-historik.

## 1.3 Auditdom

| Komponent | Status |
|---|---|
| G-HET-1 | **Beräknad, men betingad på icke-PIT Size** → EJ IDENTIFIERAD |
| G-SIZE-HET-1 | **Beräknad, men betingad på icke-PIT Size** → EJ IDENTIFIERAD |
| G-HIER-1 | **Ej körd** — designdokument |
| G-HIER-2 | **Ej körd** — samtliga tal hårdkodade |
| 71,2 % nedsideseliminering | **Existerar inte som mätning** |
| Sektorlagret | PIT-struktur finns (`valid_from`/`valid_to`) — ej diskvalificerat |

---

# DEL 2 — FRYSNING (det som genomförs)

## 2.1 Bekräftat fryst — oförändrat

**A. H0.** Score, ranking, momentumdefinition, universumsrankning, entrysignal:
oförändrade. `0,5 × pct(mom_12m) + 0,5 × pct(mom_18m)`, Top-30, likavikt,
ombalansering varannan panel, exekvering första close efter beslut, 20 bp.

**B. Hysteres.** Ingen ändring av rank ≤ 35 eller annan hold-logik.

**C. G97-P.** Oförändrad. Ingen size-treatment-audit får ändra den, och kan
för närvarande inte ens genomföras — se 3.2.

## 2.2 EJ fryst — och varför

**D. Population Passport.** Kan inte frysas. En frysning gör en definition till
projektkanon och låser den mot framtida ändring. Att frysa `GLOBAL → SIZE →
SECTOR | SIZE` skulle låsa in en rot-nod som är en 2026-ögonblicksbild och en
gren ("Terminal") som är ex post-kunskap. Frysningen skulle göra
kontamineringen permanent och svår att spåra.

**E. G-HIER-2 som diagnostisk evidens.** Kan inte frysas som evidens av något
slag, eftersom den inte är en mätning.

## 2.3 Frysning som DÄREMOT genomförs

**F. Auditfynden i Del 1** fryses som bindande. Konkret:

* `market_list` ur Avanza-proben får **inte** användas som betingande variabel i
  något modelltest förrän en daterad klassificeringshistorik finns.
* `terminal_events.json` får **aldrig** användas som en nod, klass eller feature
  vid beslutstidpunkt. Endast som utfallshantering i avkastningsberäkningen,
  vilket är dess befintliga och legitima roll.
* Tal ur `g_hier_1_*` och `g_hier_2_*` får inte citeras som resultat.

---

# DEL 3 — LEVERERAD ARKITEKTUR OCH GOVERNANCE

Följande delar av uppdraget är oberoende av Size-problemet och levereras i sin
helhet. De träder i kraft nu.

## 3.1 Målarkitektur — formaliserad

| Nivå | Funktion | Frågan den besvarar | Status |
|---|---|---|---|
| **L1** Universal Momentum Scanner | H0 → Top-30 | *Vilka aktier har starkast relativt momentum?* | **FRYST, i drift** |
| **L2** Population Knowledge | Passport → betingad payoff-fördelning | *Vilken av två legitima kandidater har bättre betingad möjlighet?* | **BLOCKERAD — datagate** |
| **L3** Decision Layer | Hold / Replace / Exit | *Ska A behållas eller ersättas av B?* | Fryst i nuvarande form |
| **L4** Portfolio / Risk | sizing, koncentration | *Hur hanteras risken i en redan vald position?* | Fryst |

**Separationsprincipen står fast och är korrekt formulerad i uppdraget:** L2
frågar om *möjlighet*, L4 om *riskhantering*. Eftersom Passport innehåller Size
skulle ett separat Size-risklager dubbelräkna. Den principen gäller oavsett om
L2 någonsin blir byggbar.

**Tolkningen fryses som uppdraget formulerar den, och den är riktig:** vi har
inte visat att H0 är fel. H0:s uppgift är att rangordna relativt momentum, och
den uppgiften är oberörd. Det som är ifrågasatt är homogenitetsantagandet
*efter* selektion — men just nu vilar den evidensen på en icke-identifierad
variabel.

## 3.2 SIZE-HETEROGENEITY GATE — införs

Regeln är bra och införs, med ett obligatoriskt nollte steg:

**Steg 0 (nytt).** Finns en **daterad, PIT-korrekt** storleksklassificering?
Om nej — testet får inte köras. Detta steg är för närvarande NEJ.

**Steg 1.** Finns ekonomisk/mekanistisk anledning att X interagerar med Size?
**Steg 2.** Finns tillräckligt N inom varje Size-nod?
**Steg 3.** Finns X × Size-heterogenitet?
**Steg 4.** Replikerar den mellan fönstren?

Generell `testa allt × Large/Mid/Small`-mining är förbjuden. Detta är den viktigaste
governanceregeln i hela uppdraget och den gäller från och med nu.

## 3.3 Forskningsregistret — ingen omprövning

Uppdraget prioriterar `run_return` och `vol_52w`/G97-P för omprövning eftersom
size-auditen gav anledning. **Den anledningen håller inte**, eftersom
size-auditen inte är identifierad. Konsekvens:

| Spår | Uppdragets prioritet | Faktisk status |
|---|---|---|
| `run_return` | HÖG — bekräftad dold size-effekt | **Ingen omprövning.** Effekten bärs delvis av noden "Terminal" |
| `vol_52w` / G97-P | HÖG — Size förklarar instabilitet | **Ingen omprövning.** G97-P står kvar oförändrad |
| TIS, recovery, propensity, acceleration, trend age | LÅG / stängt | **Stängda** — oförändrat, och detta bekräftas av G-PATH-1 och MEM-R som kördes mot rankdata utan size-beroende |

Ingen generell återöppning. Registret är oförändrat.

## 3.4 Passport-implementation — specifikationen står, bygget väntar

Fältspecifikationen i uppdraget är välformad och behålls som målbild:
`ticker, decision_date, H0_rank, H0_score, size_node, sector_node,
population_path, terminal_depth, parent_node, N_node, N_tickers, N_episodes,
EB_weight, conditional_mean_R24w, conditional_median_R24w,
conditional_downside_20, conditional_upside_30, estimation_uncertainty,
PIT_asof_date, passport_version, freeze_hash`.

Två fält är i praktiken de viktigaste och saknas i dagens underlag:
**`PIT_asof_date`** och **`freeze_hash`**. Ett Passport som inte kan svara på
*"vad visste vi om det här bolaget vid beslutstidpunkten"* är inte ett Passport.

Modulen ska byggas separat från H0, deterministiskt, versionerad och hashbar —
men den kan inte byggas meningsfullt förrän `size_node` har en `valid_from`.
**Ett Passport med en icke-daterad rot är en look-ahead-generator med
revisionsspår.**

## 3.5 Shadow mode — designen godkänns och är oberoende av Size

Shadow-lagret är den mest värdefulla oblockerade komponenten i hela uppdraget
och kan byggas nu, eftersom det inte kräver Passport.

Vid varje verkligt H0-beslut loggas:

```
decision_date, panel_index
A: ticker, H0_rank, H0_score, vol_52w, TIS, band
B: ticker, H0_rank, H0_score, vol_52w, TIS, band   (legitim ersättare)
faktiskt beslut enligt fryst logik
realiserat OC = R24w,B − R24w,A          (fylls i i efterhand)
```

Den frysta strategin fattar fortfarande beslutet. Loggen möjliggör senare
attribution utan att modellen ändras — och den bygger, panel för panel, exakt
den A-vs-B-population som G-HIER-2 påstod sig ha använt men aldrig konstruerade.
**Detta är vägen till att faktiskt kunna svara på frågan.**

## 3.6 Sekventiell testplan med gates

| Fas | Test | Gate | Status |
|---|---|---|---|
| **0** | Bygg shadow-loggen; ackumulera A-vs-B-par ur fryst logik | ingen — infrastruktur, ingen modellpåverkan | **KAN STARTAS** |
| **0b** | Daterad storleksklassificering: `valid_from`/`valid_to` per instrument, samma form som sektorlagret | kräver ny datakälla eller rekonstruktion ur historiska listningsuppgifter | **DATAUPPDRAG** |
| **1** | G-HIER-1 **på riktigt** — trädets feasibility beräknad, inte deklarerad | kräver 0b | spärrad |
| **2** | G-HIER-2 **på riktigt** — A-vs-B-prediktion med genuin OOS | kräver 1 med reproducerad struktur | spärrad |
| **3** | G-HIER-3 decision policy, en förregistrerad intervention | kräver 2 med replikerad riktning i båda fönstren **och** matched-random placebo | spärrad |
| **4** | Size-conditional G97-P treatment audit | kräver 0b | spärrad |
| **5** | 2×2 faktoriell champion | kräver 3 och 4 | spärrad |

Ingen fas körs automatiskt för att den står i planen. Varje fas kräver explicit
licens.

**Regel 8 gäller genomgående:** varje materialitetsgräns ska anges mot
placebobandet ±2,4 pp och detektionsgolvet ~4 pp innan testet skrivs.

---

# DEL 4 — DET ENDA SOM BEHÖVER GÖRAS HÄRNÄST

**Ett datauppdrag, inte ett test.** En daterad storleksklassificering med
`valid_from`/`valid_to` per instrument, byggd på samma sätt som sektorlagret
redan är byggt. Utan den är L2 inte blockerad av kunskap utan av data, och varje
test som betingar på Size producerar ett svar som inte går att tolka.

Fram till dess: H0 fryst, hysteres oförändrad, G97-P oförändrad, inget
Passport-lager, ingen size-conditioned regel, inget forskningsregister återöppnat.

**Shadow-loggen (fas 0) kan byggas oberoende och bör byggas först** — den kostar
ingenting, ändrar ingenting, och den skapar den population som varje senare fas
behöver.
