# REPOSITORY INTEGRITY & FREEZE RECONCILIATION

Datum 2026-08-18 · Auktoritativ · **Inga alpha-, signal-, decision-, portfolio- eller size-tester körda**
Gate: `tools/repo_integrity_gate.py` → `research_k/repo_integrity_gate_result.json`

Underlag: `docs/PROVENANCE_DISCREPANCY_AUDIT_2026-08-18.md`

**Git saknas** (`fatal: not a git repository`). Provenance har därför spårats ur
artefaktkedjor, frysnings-JSON, mtime och innehållshashar. 10 435 filer skannade.

---

## 0. Det avgörande hashfyndet

De tre hasharna i `FREEZE_REGISTRY.md` för H0, hysteres och G97-P motsvarar
**ingen fil i repot**. Detta är inte gamla hashar av senare redigerade filer —
en fullständig innehållsskanning av samtliga 10 435 filer ger noll träffar.

Samtidigt verifierar repots **verkliga** frysningsmekanism exakt:

| Frysnings-JSON | Låst fil | Registrerad sha256 | Verifiering |
|---|---|---|---|
| `H1419_PREREG_FREEZE.json` | `h1419_exakt_h0_preregistration.json` | `87cb01d6…74133e` | **MATCH** |
| `H1419_PREREG_FREEZE_V2.json` | `h1419_exakt_h0_preregistration_v2.json` | `23cd3cde…7ee2b3` | **MATCH** |
| `sector_classification_v1/manifest.json` | (K1) | `816cb6b3…523041` | **MATCH** |

Repot fryser alltså **preregistreringar**, inte skriptfiler. `FREEZE_REGISTRY.md`
pekar på skriptfiler med hashar utan känd källa. Det är två olika mekanismer, och
bara den ena har evidens.

---

## 1. H0 CORE MOMENTUM ENGINE

| | |
|---|---|
| **Canonical implementation** | `tools/h1419_kor_exakt_h0.py` |
| **Canonical inputs** | `research_k/h1419_exakt_h0_preregistration.json` (4 852 B, sha `87cb01d6…`) |
| **Frysningsevidens** | `H1419_PREREG_FREEZE.json`, `status: LOCKED_BEFORE_ANY_RESULT`, `locked_utc 2026-08-15T19:04:01Z` |
| **Result artifact** | `research_k/h1419_exakt_h0_RESULTAT.json`, `run_utc 19:05:35Z`, `las_verifierat: true` |
| **Registrerad hash (FREEZE_REGISTRY)** | `e27863ef…4e7687` — **matchar ingen fil i repot** |
| **Faktisk skripthash** | `c94fd568c0764bd1fede73c25e8f6441b9a16eb4b57c5310adb08c3cfc474690` |
| **Reproducerbarhet** | **Omkörd 2026-08-18. Bitidentisk utom `run_utc`.** Skriptet självverifierar preregistreringens hash och samtliga låsta indatafiler innan körning |

### Resultatkälla — och rättelsen

Skriptets egen artefakt, fönster **2014–2019**, 79 paneler, medelinnehav 27,4:

```
H0:               CAGR 27,39 %   vol 14,09 %   MaxDD −12,09 %   Sharpe 1,785
likaviktat univ.: CAGR 18,77 %   vol 13,00 %   MaxDD −15,25 %   Sharpe 1,272
primärt utfall:   Δ +8,62 pp   KI [+3,30, +15,19]   t +2,46   DOM: STÖD
```

`CURRENT_RESEARCH_STATE.md` anger *"H0 Core Momentum Engine … CAGR 13,56 %,
MaxDD −24,32 %"* för denna fil. Det är **fel modell och fel fönster**:
13,56 %/−24,32 % står ordagrant i `tools/stack_h_motor.py` rad 17 som
**SHADOW_INTEGRATED_STACK_H på 2020-2026** (ERC invvol^1,5 + FR-overlay +
hysteres rank 35 + NTZ 0,005 + SMA200).

### Kvarstående tvetydighet

Två frysningsgenerationer existerar och båda verifierar. `RESULTAT.json` och
skriptet refererar **V1**; `tools/h1419_motor.py` refererar i sin docstring
**V2** (`sha 23cd3cde…`). Vilken generation som är kanonisk för nedströms
motorer är inte dokumenterat.

**Status: `RECONSTRUCTABLE_FREEZE`.** Originalfrysningen är rekonstruerad ur
evidens och resultatet reproducerat. Den felaktiga freeze-posten bevaras.

---

## 2. HYSTERES BEHÅLLNINGSREGEL

| | |
|---|---|
| **Canonical implementation** | `tools/hysteres_kop_och_agande.py` — rad 25: **`DIAGNOSTISKT`** |
| **Canonical inputs** | ingen preregistrering hittad |
| **Frysningsevidens** | **ingen** |
| **Result artifact** | `hysteres_kop_och_agande_results.json`, `status:` *"DIAGNOSTISKT — ingen fryst fil ändrad, ingen försegling bruten, **ingen challenger**"* |
| **Registrerad hash** | `c94812a1…726581` — **matchar ingen fil i repot** |
| **Faktisk hash** | `fef90f15b25f6ee491807c4f30e0564a839b8ca2c17b434554c8d759222ada87` |

### Semantisk verifiering — regeln är inte den registrerade

Koden implementerar **ingen** fast gräns. Docstring rad 11: *"Generell
parametrisering: köpband [lo, hi], ägandegräns H, portföljtak N. Baslinjen är
lo=1, hi=N, H=N."* Rad 127 använder variabeln `H`. Skriptet är ett **rutnät**:
*"STEG 3 är portföljrutnätet, STEG 4 placebo på bästa cellen."*

Artefaktens bästa cell är **`N10_kop15-25_H30`** — N=10, köp i band 15–25,
ägande till rank 30. Registrets *"rank <= 35"* och *"minskar omsättning med
38,5 %"* finns **ingenstans** i artefakten; strängarna `38,5`, `38.5` och `0.385`
förekommer inte. `rank <= 35` är `hyst_rank=35`, standardvärdet i
`stack_h_motor.py` — alltså **STACK_H:s** parameter, en annan modellfamilj.

Enligt `FINAL_RESEARCH_INVENTORY_AFTER_K1_K3_K5.json` gav den bästa cellen
20,37 % mot kanonisk N=10:s 16,58 %, men med **KI [−9,52, +10,09], t 0,35, och
bästa av 23 celler**.

Komponenten saknas i `final_system_freeze_manifest.json` (den förseglade
forward-frysningen 2026-08-10).

**Status: `FREEZE_PROVENANCE_UNRESOLVED`.** Ingen preregistrering, ingen
frysningsartefakt, ingen hash som pekar på någon fil, en regelbeskrivning som
koden inte implementerar, och ett resultat vars konfidensintervall innehåller
noll. Det finns inget original att rekonstruera.

---

## 3. G97-P TAIL RISK EXCLUSION

| | |
|---|---|
| **Canonical implementation** | `tools/g97p_hogvolsvans.py`, `K = 6  # LÅST` (rad 47) |
| **Canonical inputs** | `research_k/g83_g97_preregistration.json`, `status: LOCKED_BEFORE_ANY_COMPUTATION`, `written_utc 2026-08-17T13:33:21Z`, refererar locked H0 = 0,072 / 0,3156 |
| **Result artifact** | `research_k/g97p_results.json`, `run_utc 13:43:59Z`, + `g97p_panelledger.jsonl` |
| **Registrerad hash** | `74191a27…192039` — **matchar ingen fil i repot** |
| **Faktisk hash** | `a8a96ab3504295a938c6769b8b7ed2efdd3512952d549517b0b36d23b0e44ec6` |

### Semantisk verifiering — bekräftad, och registret har fel

Artefaktens eget `regel`-fält, ordagrant:

> `"exkludera de sex hogsta vol_52w i topp-30, ersatt med rank 31-36"`

Skriptet rad 3: *"SEX namn är låst (6/30 = **20 %**)"*. **Den registrerade
beskrivningen "97,5:e percentilen volatilitetssvans" är felaktig** och får inte
användas. Regeln är den högsta femtedelen inom en trettiogrupp.

### Resultatkälla — registrets prestandapåstående motsägs

| Fönster | H0 CAGR | G97-P CAGR | Δ | Bootstrap-KI | H0 MaxDD | G97-P MaxDD |
|---|---:|---:|---:|---|---:|---:|
| 2020-2026 | 7,20 % | 8,81 % | +1,61 pp | `ki_lo −0,0236` — **innehåller noll** | −33,50 % | **−34,36 %** |
| 2014-2019 | 31,56 % | 34,03 % | +2,47 pp | `[−0,0473, +0,0535]`, t 0,842 — **innehåller noll** | −19,73 % | **−20,08 %** |

`FREEZE_REGISTRY.md`: *"Sänker MaxDD med +4,8 pp"*. Artefakten visar att MaxDD
blev **sämre i båda fönstren**. Båda bootstrap-intervallen innehåller noll.

Komponenten skapades **2026-08-17**, en vecka **efter** den förseglade
forward-frysningen (2026-08-10), och saknas i `final_system_freeze_manifest.json`.
I `quant_term_h0_gap_ledger.json` har den karaktären av **förregistrerad kandidat**,
inte fryst regel.

**Status: `FREEZE_PROVENANCE_UNRESOLVED`.** Preregistreringen och beräkningen är
äkta och spårbara, men det finns ingen frysningshändelse, och registrets
beskrivning är fel om både regeln och utfallet.

---

## 4. K1 SECTOR CLASSIFICATION

| | |
|---|---|
| **Frysningsevidens** | `research_k/sector_classification_v1/manifest.json`, `K1_SECTOR_CLASSIFICATION_V1_IMMUTABLE_2026-08-09` |
| **Registrerad hash** | `816cb6b3…523041` |
| **Faktisk hash** | `816cb6b38a2130728bd282e8352c74ccf119f374b8747717c0b0603fa5523041` — **MATCH** |
| **Scope i manifestet** | *"classification/provenance only; no target, IC, alpha or backtest"* |
| **Input** | `qa_identity_sector_evidence.json` — samma fil som bär den icke-PIT `market_list` |
| **Output** | `sector_classification_intervals.json` med `valid_from`/`valid_to` |

Sektorlagret lägger en tidsdimension ovanpå en odaterad källa. Hashen verifierar
och manifestets scope är korrekt avgränsat. Att intervallrekonstruktionen är
materiellt riktig är **inte** verifierat i detta uppdrag och ligger utanför dess
mandat.

**Status: `VERIFIED_ORIGINAL_FREEZE`** (hash och scope). Härledningens
materiella riktighet är oprövad.

---

## 5. DOKUMENTAVSTÄMNING

Rättat (verifierbart ur kod/artefakt), med historiken bevarad:

| Dokument | Åtgärd |
|---|---|
| `DATA_GOVERNANCE_REGISTRY.md` / `.json` | `list_segment` → `FORBIDDEN_IN_MODEL_TEST`, `date_fields: []`, `qa_status: FAILED_PIT_HISTORY_GATE`. Tidigare felaktiga påståenden bevarade i `correction`-fält och rättelsenot |
| `FREEZE_REGISTRY.md` | Hashverifieringsnot tillagd. **De påstådda hasharna är oförändrade** — att skriva in de faktiska hade raderat fyndet |

**Ej ändrat, lämnas som beslutsunderlag:** `CURRENT_RESEARCH_STATE.md` §1
(H0-raden), `RESEARCH_INDEX.md` (G97-P-beskrivningen), samt hysteresens och
G97-P:s status som frysta komponenter. Dessa kräver ett explicit beslut om vad
som ska stå, inte en ensidig omskrivning.

### Bekräftas oförändrat

| | |
|---|---|
| `list_segment` / `market_list` | **FÖRBJUDEN** som historisk conditioning-variabel tills PIT-historik finns |
| Terminalstatus | får **aldrig** användas ex ante |
| G-HET-1, G-SIZE-HET-1 | `NOT_IDENTIFIED` |
| G-HIER-1, G-HIER-2 | `NON_COMPUTED_CLAIM` |
| G-HIER Passport | **inte fryst** |
| CLOSED_NEGATIVE-spår | återöppnas inte utan ny evidens |
| Öppna kandidater | **0** |

---

## 6. PIT-SIZE DATAGATE (dokumenteras endast — inget byggs)

`list_segment` får status `ALLOWED` först när **samtliga** villkor är uppfyllda
och QA-granskade separat:

1. **Historiskt daterad** — `valid_from`/`valid_to` per instrument och segment.
2. **Tillgänglig vid paneldatum** — segmentet måste ha varit publikt känt vid T.
3. **Ingen 2026-snapshot bakåt** — en `retrieved_at` är inte en `valid_from`.
4. **Ingen framtida terminalinformation** — avnoteringsstatus får först tilldelas
   från och med faktisk händelsetidpunkt, aldrig retroaktivt över hela historiken.
5. **Reproducerbar källa och transformation** — dokumenterad hämtning, hashad
   råfil, deterministisk transform.
6. **Separat QA** innan status ändras, med samma stringens som K1-sektorlagret.
7. **Segmentbyten måste finnas** — en källa där inget bolag någonsin byter segment
   är per definition inte en historik.

Ingen omkörning av G-HET-1, G-SIZE-HET-1, G-HIER-1 eller G-HIER-2 får ske innan
denna gate passerat.

---

## 7. SLUTTABELL

| COMPONENT | CODE VERIFIED | RESULT VERIFIED | HASH VERIFIED | SEMANTICS VERIFIED | FINAL STATUS |
|---|:---:|:---:|:---:|:---:|---|
| **H0 Core** | JA | JA (bitidentisk omkörning) | **NEJ** (registerhash utan källa) | JA (27,39 %/−12,09 %, 2014-2019) | `RECONSTRUCTABLE_FREEZE` |
| **Hysteres** | JA | NEJ (självdeklarerat diagnostiskt) | **NEJ** | **NEJ** (rutnät, ej rank≤35) | `FREEZE_PROVENANCE_UNRESOLVED` |
| **G97-P** | JA | JA (men KI innehåller noll) | **NEJ** | **NEJ** (sex av 30, ej 97,5-percentil) | `FREEZE_PROVENANCE_UNRESOLVED` |
| **K1 Sector** | N/A | N/A | **JA** | JA (scope korrekt avgränsat) | `VERIFIED_ORIGINAL_FREEZE` |

```
REPOSITORY INTEGRITY:      FAIL
RESEARCH MAY RESUME:       NO
OPEN RESEARCH CANDIDATES:  0
```

## 8. STOPP

Stoppregeln är utlöst. Två av fyra frysta komponenter har olöst
frysnings-provenance och två av fyra har felaktig semantisk beskrivning i
registret.

Inget har gissats. Inga ersättningsresultat har skapats. Ingen modell har
ändrats. Inget forskningsspår har startats. **H0 har körts om — men enbart som
reproduktionskontroll av en fryst komponent mot dess egen låsta preregistrering,
vilket uppdragets punkt 1.D uttryckligen kräver.**

### Vad som krävs för att lyfta FAIL

1. **Beslut om hysteres.** Antingen tas den bort ur FREEZE_REGISTRY, eller så
   licensieras en preregistrerad omkörning som fastställer en faktisk regel.
   Nuvarande post beskriver en regel som koden inte innehåller.
2. **Beslut om G97-P.** Beräkningen är äkta men konfidensintervallen innehåller
   noll och MaxDD-påståendet är motsagt. Antingen omklassificeras den till
   förregistrerad kandidat, eller så licensieras en frysningshändelse med
   korrekt beskrivning.
3. **H0:s freeze-post** pekas om till preregistreringskedjan
   (`H1419_PREREG_FREEZE.json` → `87cb01d6…`), och det klargörs om V1 eller V2 är
   kanonisk för nedströms motorer.
4. **Två texträttelser** — H0-raden i `CURRENT_RESEARCH_STATE.md` och
   G97-P-beskrivningen i `RESEARCH_INDEX.md`.

Punkt 1–3 kräver beslut, inte utredning. Utredningen är klar.

---

# DEL II — GOVERNANCE RECONCILIATION VERKSTÄLLD (2026-08-18)

Utredningen ovan accepterad som beslutsunderlag. Besluten 1–5 verkställda.
**Inga alpha-, signal-, portfolio-, size-, hysteres- eller G97-P-tester körda.
Ingen modellparameter optimerad.**

## BESLUT 1 — H0: kanonisk version fastställd till V2

Avgjord **enbart** ur artefakter. Prestanda användes inte som kriterium.

| Evidens | Innehåll |
|---|---|
| **Explicit supersession** | `h1419_exakt_h0_preregistration_v2.json` har ett `ersatter`-fält som namnger V1 med dess sha256 och pekar på var V1:s resultat publicerades |
| **Dokumenterad datadefekt i V1** | V1:s universumfilter krävde Main Market-ISIN i *dagens* lista och uteslöt därmed **44 bolag** som låg på Main Market 2014-2019 men avnoterades 2020-2026, varav **38 med terminal-event**. Defekten upptäcktes genom att det likaviktade universumet (+18,77 %/år) låg orimligt högt över index (~12 %/år) |
| **Nedströmsberoende** | `tools/h1419_motor.py` rad 19 läser `prices_h1419_universum_v2.json`, rad 5 refererar `H1419_PREREG_FREEZE_V2`. Motorn som **samtliga verifierade 2014-2019-spår** använder beror på V2 |
| **Tidsordning** | V2 låst 20:03:55Z efter V1 19:04:01Z |

V1 gav 27,39 %, V2 gav 29,99 %. Att V2 presterar högre är **incidentellt** —
valet följer survivorship-defekten. V2:s **hederlighetsklausul** kräver att V1
alltid redovisas jämte V2, vilket nu är inskrivet i samtliga register.

### Verifierad kedja

```
PREREGISTRATION  h1419_exakt_h0_preregistration_v2.json      sha 23cd3cde…  MATCH
INPUT MANIFEST   7 låsta indatafiler i indata_last            samtliga 7    MATCH
IMPLEMENTATION   tools/h1419_kor_exakt_h0_v2.py               självverifierar låset
RESULT           h1419_exakt_h0_RESULTAT_V2.json              refererar prereg-hash
DECISION         dom: STÖD
FREEZE           H1419_PREREG_FREEZE_V2.json                  LOCKED_BEFORE_ANY_RESULT
REPRODUKTION     omkörd 2026-08-18                            bitidentisk utom run_utc
```

**Verifierat resultat, 2014-2019, 79 paneler, medelinnehav 27,5:**
CAGR **29,99 %**, vol 15,00 %, MaxDD **−14,63 %**, Sharpe 1,850.
Likaviktat universum 17,84 %. Δ **+12,15 pp**, KI [+4,25, +23,74], t +3,27.

### Felattribueringen rättad

13,56 % / −24,32 % står ordagrant i `stack_h_motor.py` rad 17 som
**SHADOW_INTEGRATED_STACK_H på 2020-2026**. Talen är borttagna från H0 i samtliga
register och ersatta med V2:s artefaktbundna tal.

**Känd begränsning, öppet deklarerad:** V2:s
`created_before_any_return_computed` är `False`. Preregistreringen skrevs efter att
V1:s avkastningar observerats. Det står i artefakten, är inte dolt, och hanteras av
hederlighetsklausulen. Det är den enda kvarvarande svagheten i H0:s kedja.

## BESLUT 2 — Hysteres omklassificerad

`FROZEN_DECISION_RULE` → **`UNVERIFIED_DECISION_RULE_REQUIRES_REVALIDATION`**.
Varken `CLOSED_NEGATIVE` eller `INVALID`. Ingen licens att köras om. `rank ≤ 35`
får inte användas som verifierat eller fryst resultat. Historiken bevarad i
`FREEZE_REGISTRY.md` rättelse 2 och `INVALIDATED_AND_SUPERSEDED_RESULTS.md` punkt 5.

## BESLUT 3 — G97-P omklassificerad

`FROZEN_RISK_RULE` → **`COMPUTED_BUT_NOT_VALIDATED_CANDIDATE`**.

Verifierad implementation, dokumenterad exakt enligt kod:
**K = 6 — de sex högsta `vol_52w` inom Top-30 exkluderas och ersätts med rank
31–36** (6/30 = 20 %). Alla påståenden om *"97,5:e percentilen"* borttagna.

Verifierade resultat, inskrivna i registren:

| Fönster | Δ CAGR | Bootstrap-KI | MaxDD H0 → G97-P |
|---|---:|---|---|
| 2020-2026 | +1,61 pp | `ki_lo −0,0236` — **korsar noll** | −33,50 % → **−34,36 %** |
| 2014-2019 | +2,47 pp | `[−0,0473, +0,0535]`, t 0,842 — **korsar noll** | −19,73 % → **−20,08 %** |

MaxDD förbättrades inte i något fönster. Påståendet *"+4,8 pp
MaxDD-förbättring"* saknar verifierad provenance och motsägs av artefakten.
Räknas **inte** som öppen forskningskandidat. Ingen licens att köras om.

## BESLUT 4 — K1 oförändrad

`VERIFIED_TAXONOMY`. Implementation, manifest och status orörda.

## BESLUT 5 — Size / hierarki oförändrat

`list_segment`/`market_list` `FORBIDDEN_IN_MODEL_TEST` · terminalstatus aldrig
ex ante · G-HET-1/G-SIZE-HET-1 `NOT_IDENTIFIED` · G-HIER-1/G-HIER-2
`NON_COMPUTED_CLAIM` · Passport inte fryst · ingen återöppning ·
PIT-size-datauppdraget separat och ej genomfört.

## Integrity gate V2

`tools/repo_integrity_gate.py` omskriven att testa frysningssemantiken mot
`research_k/freeze_chains.json`. PASS kräver att varje FROZEN-komponent har hela
kedjan verifierad. Ej frysta komponenter tillåts utan FAIL förutsatt att de inte
anges som frysta, inte är beroende för en fryst komponent, inte bär en öppen
kandidat, och har konsekvent status i samtliga register.

**Negativt testad** — gaten passerar inte tomt:

| Injicerat brott | Utfall |
|---|---|
| K1:s manifesthash ändrad en tecken | **FAIL** — `1_CHAIN_FREEZE: manifesthash stämmer inte` |
| Hysteres upphöjd till `FROZEN` | **FAIL** — `1_CHAIN_FREEZE: FROZEN men frysningsartefakt saknas` |

Kedjedefinitionen återställd bitidentiskt efter testerna.

Under bygget av V1 av gaten hittade och rättade jag en egen bugg: check 5
flaggade korrekt förbjudna variabler enbart för att de har beskrivande datumfält.

---

## SLUTKONTROLL

| COMPONENT | CURRENT STATUS | PROVENANCE STATUS | CANONICAL ARTIFACT | RESULT STATUS | ALLOWED USE |
|---|---|---|---|---|---|
| **H0 Core** | `FROZEN` | hela kedjan verifierad | `h1419_exakt_h0_preregistration_v2.json` (`23cd3cde…`) | 29,99 % / −14,63 % / Δ +12,15 pp, reproducerad bitidentiskt | baslinje och beroende |
| **K1 Sector** | `VERIFIED_TAXONOMY` | manifesthash verifierad | `sector_classification_v1/manifest.json` (`816cb6b3…`) | intervall med `valid_from`/`valid_to` | endast populationsstratifiering |
| **Hysteres rank≤35** | `UNVERIFIED_DECISION_RULE_REQUIRES_REVALIDATION` | ingen frysning, ingen preregistrering | `hysteres_kop_och_agande_results.json` (självdeklarerat diagnostiskt) | rutnät, bästa cell `N10_kop15-25_H30`, KI korsar noll | **ingen** |
| **G97-P (K=6)** | `COMPUTED_BUT_NOT_VALIDATED_CANDIDATE` | preregistrering + beräkning äkta, ingen frysning | `g97p_results.json` | Δ +1,61/+2,47 pp, KI korsar noll i båda, MaxDD sämre i båda | **ingen** |

```
REPOSITORY INTEGRITY:      PASS
FROZEN COMPONENTS:         [H0_CORE (V2), K1_SECTOR]
UNVERIFIED COMPONENTS:     [HYSTERES_RANK35, G97P_TAIL]
CLOSED VALID RESEARCH:     [G-PATH-1, G-PATH-2, H-ORIGIN-1, G-PROP-1]
NOT IDENTIFIED:            [G-HET-1, G-SIZE-HET-1]
NON-COMPUTED CLAIMS:       [G-HIER-1, G-HIER-2]
OPEN RESEARCH CANDIDATES:  0
RESEARCH MAY RESUME:       YES
```

### Vad PASS betyder — och inte betyder

PASS betyder att **repots auktoritativa status nu är sanningsenlig mot den
provenance som faktiskt kunnat verifieras**. Det betyder inte att det finns
forskning att bedriva: **öppna kandidater är 0**. `RESEARCH MAY RESUME: YES` säger
att integritetsspärren inte längre blockerar — inte att något spår är licensierat.

Kvarvarande verkliga begränsningar, oförändrade av denna reconciliation:

1. **H0 V2:s preregistrering skrevs efter att V1:s avkastningar observerats.**
   Öppet deklarerat i artefakten och hanterat av hederlighetsklausulen, men det är
   en svaghet som inte kan repareras retroaktivt.
2. **K1:s intervallrekonstruktion är inte materiellt verifierad** — endast hash och
   scope.
3. **PIT-size finns inte.** Datagaten i avsnitt 6 är oförändrad och ej passerad.
4. **Repot har ingen versionshantering** (`fatal: not a git repository`). All
   provenance vilar på artefaktkedjor och innehållshashar. Detta är den enskilt
   största kvarvarande strukturella risken — det var frånvaron av git som gjorde
   hashfyndet mödosamt och som gör framtida tystnad möjlig.
