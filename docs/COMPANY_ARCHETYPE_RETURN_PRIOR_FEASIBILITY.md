# COMPANY ARCHETYPE / RETURN PRIOR / REMAINING RUNWAY — Feasibility, deduplicering och statistisk identifiering

Datum: 2026-08-18 · **Strikt diagnostisk feasibility-leverans** · **Inga prediction- eller portföljtester körda**  
Status: Locked H0, hysteres, G97-P och alla frysta komponenter helt orörda.  
Regel 5 verifierad mot `research_k/*.json` och `docs/*.md`. samtliga governance- och datagates överordnade.

---

## EXECUTIVE SUMMARY & DOM

| Delspår | Slutklassificering | Huvudorsak / Begränsning |
|---|---|---|
| **A. Company Archetype Prior (Bred Sektor K1)** | **TESTABLE WITH RESTRICTION** | Bred sektorklassificering täcker 420/420 instrument (inkl. 68 terminala). Kräv obligatorisk känslighetsanalys utan `MANUAL_EXPERT_CLASSIFICATION` (6 st). |
| **B. Company Archetype Prior (Fundamenta/KPI)** | **FORBIDDEN IN MODEL TEST** | Historisk fundamentadatabas saknar avnoterade bolag. Survivorship-skevheten kan inte kontrolleras (Gate 2026-08-16). |
| **C. Company Archetype Prior (Size / Market Cap / EV)** | **DATA_BLOCKED** | Falled PIT-gate `K2A`. Utestående aktier (`number_Of_Shares`) har split- och reporting-ambiguities. Inga proxys tillåtna. |
| **D. Company-Specific Historical Prior** | **PARTIALLY TESTABLE** | Enbart 27 tickers (2020–2026) och 41 tickers (2014–2019) har $\ge 2$ separerade episoder i Top-30. Krymper ($w_i \to 0$) till populations-/archetype-prior för >85 % av universumet. |
| **E. Remaining Runway Distribution** | **TESTABLE** | Kan definieras PIT-korrekt som betingad framtida avkastningsfördelning (relativ opportunity cost) givet H0-rankdecil vid panel $T$. Inga post-hoc-toppar. |
| **F. Bolagsrelativ Drawdown / Pullback** | **REDUNDANT WITH EXISTING SIGNAL** | Möjlig fälla: Om inte måttet visar inkrementellt stöd *efter* kontroll för H0-rank + standardvolatilitet ($\sigma_i$), är det endast volatilitet under nytt namn ($r \approx 0,99$ mot G97-P). |

---

## A. DEFINIERA DEN EXAKTA BLINDA FLÄCKEN

### 1. Exakt vilken bolagsinformation H0 känner till vid varje beslutspunkt

Locked H0 beräknas exklusivt via följande signalfunktion och tvärsnittsrangordning:

$$\text{score}(i, T) = 0{,}5 \cdot \text{pct}(\text{mom}_{12m}(i, T)) + 0{,}5 \cdot \text{pct}(\text{mom}_{18m}(i, T))$$

$$\text{mom}_{Xm}(i, T) = \frac{P(i, T)}{P(i, T - X)} - 1$$

H0:s samlade kunskap om ett bolag vid panel $T$ består uttryckligen av **tre prispunkter**: $P(T)$, $P(T-12m)$, $P(T-18m)$, samt tvärsnittspositionen i percentiler vid panel $T$.

### 2. Tredelad informationsmatris

```
┌─────────────────────────────────────────────────────────────────────────┐
│ INFORMATIONSUPPDELNING I LOCKED H0                                       │
├─────────────────────────────────────────────────────────────────────────┤
│ 1. EXPLICIT ANVÄND INFORMATIONSMÄNGD                                     │
│    • Slutpris P(T), historiskt pris P(T-12m), historiskt pris P(T-18m)   │
│    • Relativ tvärsnittsrankning (percentil 0–100 %) i aktiva universumet │
├─────────────────────────────────────────────────────────────────────────┤
│ 2. IMPLICIT INFORMATION I 12M/18M MOMENTUM                              │
│    • Multi-månaders nettoavkastning (har bolaget stigit kraftigt?)       │
│    • Grov korrelation mot volatilitet i tail-regimer                     │
│    • Kluster av starka sektorer (om hel sektor stiger hamnar flera där)  │
├─────────────────────────────────────────────────────────────────────────┤
│ 3. INFORMATION SOM H0 HELT SAKNAR                                       │
│    • Company Archetype / Struktur (Investment, Verkstad, Growth, Bank)  │
│    • Size / Storleksklass (Large Cap vs Small Cap/First North)          │
│    • Company Return Prior (Volatilitet, Skewness, Tail-risk, Win-rate)  │
│    • Operativ/Finansiell profil (Lönsamhet, Skuldsättning, Utspädning)   │
│    • Remaining Runway / Payoff Asymmetry (Upside vs Downside ratio)     │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3. Utvärdering av påståendet

> *"Conditional on current H0 score/rank, two companies are treated essentially the same regardless of company archetype and historical return distribution."*

**KORREKT.** Inom locked H0 är urval, vikttilldelning, retention och exiter uteslutande en funktion av $\text{score}(i, T)$ (och dess rangordning). Givet $\text{rank}(A, T) = k$ och $\text{rank}(B, T) = k$, behandlar H0 bolag A och B exakt identiskt, oavsett om A är Investor AB (stabilt investmentbolag med låg volatilitet och begränsad tail-skew) och B är Storytel/Biovica (högvolatilt tillväxt-/biotechbolag med bred tail-fördelning).

---

## B. DEFINIERA COMPANY VISIT CARD (INVENTERING & GATES)

En inventering av PIT-korrekta egenskaper som beskriver ett bolag har genomförts och stämts av mot samtliga frysta governance- och datagates i projektet.

### B1. Relativt permanenta egenskaper
- **Börsålder / Listing Age**: Tid sedan första handelsdag i V2-universumet (AVAILABLE).
- **Bolagsålder / Founding Age**: Etableringsår från Bolagsverket om verifierbart; annars UNKNOWN.
- **Sektor & Industri**: Avanza-sektorklassificering (`K1_SECTOR_CLASSIFICATION_V1_IMMUTABLE_2026-08-09`). Omfattar 11 breda sektorer (AVAILABLE WITH RESTRICTION) och fin industri för 352/420 tickers (PARTIALLY AVAILABLE).
- **Bolagstyp / Archetype**: Sektordriven struktur (Investment, Industri/Verkstad, Bank/Finans, Fastighet, Råvara, Biotech, Tech/Software).
- **Size / Storlek (Market Cap / EV)**: **DATA_BLOCKED** per Gate `K2A` (oklar PIT-semantik och splitrestatements för utestående aktier `number_Of_Shares`).
- **Maturity / Livscykel**: Kombinerad börsålder, omsättningsskala och lönsamhetsstatus.

### B2. Historiskt marknadsbeteende
- **Långsiktig volatilitet**: 1y/3y/5y historicized annualized volatility (AVAILABLE).
- **Marknads-Beta**: Beta mot OMXSPI/OMXS30GI beräknat expanderande (AVAILABLE).
- **Idiosynkratisk volatilitet**: Residualvolatilitet mot marknadsmodell (**REDUNDANT**; G97-auditen visade $r(\text{vol}, \text{idio\_vol}) \approx 0{,}99\text{--}1{,}00$).
- **Skewness & Tail behaviour**: 95:e/5:e percentilen av veckoavkastningar (AVAILABLE).
- **Drawdown- & Recoveryfördelning**: Median-drawdown under korrektioner och tid till återhämtning (AVAILABLE).
- **Trend-/Momentumepisoders längd**: Time-in-state (TIS) i Top-30/Top-60 (AVAILABLE via State/Path-spåret).

### B3. Finansiell/operativ profil
- **Tillväxt, Lönsamhet, Marginaler, Skuldsättning, Utspädning m.fl.**:
  - *Governance Audit*: `SIGNALKALLOR_GATE_AUDIT_2026-08-16` & `FUNDAMENTAL_QA`.
  - *Status*: **FORBIDDEN IN MODEL TEST**. Historisk fundamentadata saknar avnoterade bolag (survivorship bias kan ej kontrolleras).

---

## C. DATAINVENTERING OCH KLASSIFICERING

Samtliga potentiella visitkortsvariabler har inventerats mot källstöd, PIT-status, survivorship-status och governance-gates:

| Variabelklass | Variabelnamn | Datakälla | Djup | PIT-status | Survivorship-status | Coverage 2014-19 / 2020-26 | Terminalbolag täckta? | QA-status | Registrerad Gate-status | Slutklassificering |
|---|---|---|---|---|---|---|---|---|---|---|
| **Permanent** | Börsålder / Listing Age | Master / EODHD | 2012–2026 | Fullt PIT | Ren | 100 % / 100 % | Ja (68/68) | Verifierad | Ja | **AVAILABLE** |
| **Permanent** | Bred Sektor (11 sektorer) | Avanza Crosswalk `K1` | 2012–2026 | Entity Class. | Ren (68/68 täckta) | 100 % / 100 % | Ja (68/68) | Freeze V1 | K1 Gate | **AVAILABLE WITH RESTRICTION** |
| **Permanent** | Fin Industri | Avanza Crosswalk `K1` | 2012–2026 | Entity Class. | Delvis (352/420) | 83,8 % / 83,8 % | Delvis | Freeze V1 | K1 Gate | **PARTIALLY AVAILABLE** |
| **Permanent** | Market Cap / EV | Börsdata API | 2012–2026 | **FAILED PIT** | Saknas för terminala | 0 % terminala | FAILED QA | K2A Gate | **DATA_BLOCKED** |
| **Beteende** | Långsiktig Volatilitet (1y/3y) | Prispanel V2 | 2014–2026 | Fullt PIT | Ren | 100 % / 100 % | Ja (68/68) | Verifierad | Ja | **AVAILABLE** |
| **Beteende** | Marknads-Beta | Prispanel V2 | 2014–2026 | Fullt PIT | Ren | 100 % / 100 % | Ja (68/68) | Verifierad | Ja | **AVAILABLE** |
| **Beteende** | Idiosynkratisk Volatilitet | Prispanel V2 | 2014–2026 | Fullt PIT | Ren | 100 % / 100 % | Ja (68/68) | Verifierad | G97 Gate | **REDUNDANT** ($r \approx 1{,}0$ mot total vol) |
| **Beteende** | Return Skewness & Quantiles | Prispanel V2 | 2014–2026 | Fullt PIT | Ren | 100 % / 100 % | Ja (68/68) | Verifierad | Nej | **AVAILABLE** |
| **Beteende** | Episodvaraktighet (TIS) | Rankpanel V2 | 2014–2026 | Fullt PIT | Ren | 100 % / 100 % | Ja (68/68) | Verifierad | State/Path | **AVAILABLE** |
| **Finansiell** | Omsättning/Vinsttillväxt | Börsdata API | 2012–2026 | Rapportdatum | **FAILED (Saknar avnoterade)** | 0/68 terminala | FAILED QA | Fund. Gate | **FORBIDDEN IN MODEL TEST** |
| **Finansiell** | Net Debt / Skuldsättning | Börsdata API | 2012–2026 | Rapportdatum | **FAILED (Saknar avnoterade)** | 0/68 terminala | FAILED QA | Fund. Gate | **FORBIDDEN IN MODEL TEST** |
| **Finansiell** | Utspädning / Återköp | Transaktionsfil | 2016–2026 | **FAILED PIT** | Ingen timestamp | Okänd | FAILED QA | Gate Audit | **DATA_BLOCKED** |

---

## D. DEN CENTRALA STATISTISKA IDÉN

### 1. Matematisk formulering
Problemet modelleras inte som ett deterministiskt kurstak, utan som en **Betingad Framtida Avkastningsfördelning**:

$$P(R_{t \to t+h} \mid \text{H0 state}_t, \text{Company Prior}_i)$$

där:
- $\text{H0 state}_t$: Betingat rankband/score-decil för bolag $i$ vid panel $T$ (t.ex. Top 10 eller Top 30).
- $\text{Company Prior}_i$: Sektor/archetype-gruppering $\theta_A$ eller bolagets egen historiska fördelningsparameter $(\mu_i, \sigma_i, \gamma_i)$ skattad strikt ex-ante (expanderande fönster $< T$).

### 2. Robust skattningsbara parametrar och utfall
- **Tröskelsannolikheter (Upside Tail)**: $P(R_{t \to t+h} > +10\%)$, $P(R_{t \to t+h} > +20\%)$, $P(R_{t \to t+h} > +30\%)$, $P(R_{t \to t+h} > +50\%)$.
- **Tröskelsannolikheter (Downside Tail)**: $P(R_{t \to t+h} < -10\%)$, $P(R_{t \to t+h} < -20\%)$, $P(R_{t \to t+h} < -30\%)$.
- **Fördelningsmoment & Kvantiler**: Median forward return, conditional mean, övre kvantiler ($q_{75}, q_{90}$), undre kvantiler ($q_{10}, q_{25}$), Expected Shortfall ($\text{CVaR}_{95}$), samt Upside/Downside Asymmetry Ratio $\frac{P(R > +20\%)}{P(R < -20\%)}$.

### 3. Fasta horisonter ex-ante
- Horisonter låses till $h \in \{4, 12, 24, 52\}$ veckor (motsvarande 1, 3, 6, 13 paneler).
- **Strikt regel**: Ingen horisont får väljas eller justeras efter resultat.

---

## E. REMAINING RUNWAY DISTRIBUTION

### 1. Definition utan framtidsinformation och post-hoc-toppar
"Remaining Runway" mäts **INTE** som maximal kursnivå framåt ($\max_{t \in [T, T+h]} P_t$), vilket skulle införa allvarlig right-censoring och look-ahead bias.

Istället definieras Remaining Runway som **den betingade överlevnads- och avkastningsfördelningen över horisont $h$ givet information känd vid $T$**:

$$\text{Runway}_i(T, h) \sim F_{R_{T \to T+h} \mid \text{Rank}(i, T), \text{Prior}_i}$$

Två bolag med identisk H0-rank kan uppvisa helt olika runway-profiler:
- **Bolag A (Stabilt/Moget)**: $P(+30 \% \text{ inom } 24v) = \text{låg}$, $P(-20 \%) = \text{låg}$ (Snäv fördelning, låg vol).
- **Bolag B (Tillväxt/Volatilt)**: $P(+30 \% \text{ inom } 24v) = \text{hög}$, $P(-20 \%) = \text{hög}$ (Bred tail-fördelning, hög vol).

---

## F. ABSOLUT VS RELATIV RUNWAY (OPPORTUNITY COST)

### 1. Utvärdering av mätmått
Absolut aktieavkastning $R_i[T \to T+h]$ fångar i hög grad generell marknadsbeta och makro. Eftersom H0 är en tvärsnittsmodell med fasta platser (t.ex. 10 eller 30 innehav) är det relevanta beslutsproblemet **Opportunity Cost**:

$$\text{"Är innehav } A \text{ fortfarande ett bättre val än den bäst tillgängliga ersättningskandidaten } B \text{ (rank 31)?"}$$

### 2. De tre relativformuleringarna
1. **Forward Excess Return**: $R_i[T \to T+h] - R_{\text{market}}[T \to T+h]$.
2. **Forward Rank Retention**: $P(\text{Rank}_i(T+h) \le 30 \mid \text{Rank}_i(T) \le 30)$.
3. **Probability of Beating Replacement Candidate**: $P(R_i[T \to T+h] > R_{\text{Candidate\_31}}[T \to T+h])$.

**Slutsats**: Formulering 3 (sannolikheten att slå nästa H0-kandidat) motsvarar bäst H0:s faktiska beslut, i linje med ledgerposterna #31 (Opportunity cost), #32 (Replacement effect) och #42 (Swap efficiency).

---

## G. CONDITION ON H0 — OBLIGATORISKT IDENTIFIERINGSKRAV

### 1. Erfarenheten från G-PATH-1
G-PATH-1 visade att en enorm rå avkastningsskillnad mellan två grupper helt eliminerades när kontroll för nuvarande H0-rank infördes. 

**Obligatorisk regeln**: Ingen skillnad mellan bolagstyper får tillskrivas company knowledge om grupperna samtidigt har olika H0-score/rank.

### 2. Kontrollmetodik
- **Icke-parametrisk kontroll**: Rankdecil inom panel (t.ex. Band 1: rank 1–10; Band 2: rank 11–20; Band 3: rank 21–30) samt score-decil.
- **Matched Observations / CEM**: Parvis matchning av bolag från olika archetyper med identisk H0-rank vid panel $T$.
- Redovisa **alltid** både **RÅ EFFEKT** och **CONDITIONAL / RESIDUAL EFFEKT** ($\Delta IC_{\text{residual}}$ eller $\beta_{\text{prior}} \mid \text{H0 rank}$).

---

## H. POPULATION → ARCHETYPE → COMPANY (KRYMPNING & SAMPLE SIZE)

### 1. Hierarkisk Empirical-Bayes-struktur

```
MARKET
  │
  ▼
ARCHETYPE / SECTOR (K1)
  │
  ▼
COMPANY SPECIFIC PRIOR
  │
  ▼
CURRENT H0 STATE (Rankdecil)
```

Skattningsmodell för bolagsprior (moment-baserad shrinkage utan fria parametrar):

$$\hat{\theta}_i(T) = w_i(T) \cdot \bar{X}_i(T) + (1 - w_i(T)) \cdot \bar{X}_{\text{archetype}}(T)$$

$$w_i(T) = \frac{n_i(T)}{n_i(T) + k(T)}, \quad k(T) = \frac{\sigma^2_{\text{inom}}}{\sigma^2_{\text{mellan}}}$$

### 2. Kvantifiering av historiskt djup per bolag i Top-30

Ur den faktiska rankpanelen i V2:
- I fönstret 2020–2026 (66 paneler) har medianbolaget i Top-30 endast **12 paneler** (ca 24 veckors data).
- Endast **27 tickers** i 2020–2026 har $\ge 2$ separerade momentumepisoder i Top-30.
- I fönstret 2014–2019 (79 paneler) har endast **41 tickers** $\ge 2$ separerade episoder.

> **Slutsats**: Över 85 % av bolagen i Top-30 saknar tillräcklig bolagsspecifik historik ($n_i < 30$). Därför kommer varje bolagsspecifik prior vid strikt shrinkage ($w_i \to 0$) att kollapsa till **Archetype / Populations-prior**.

---

## I. STATIONARITET OCH DRIFT

### 1. Identifierade driftproblem
- **Lifecycle drift**: Ett ungt tillväxtbolag mognar och får lägre volatilitet och förändrad avkastningsprofil over 5–10 år.
- **Volatility drift**: Makroregimer (t.ex. COVID 2020 vs ränteuppgång 2022) förändrar basvolatiliteten för hela marknaden.
- **Structural breaks**: Förvärv, avknoppningar eller förändrade affärsmodeller ändrar tail-egenskaper.

### 2. Utvärdering av fönster
"Bolagets hela livstids-historik" är **INTE** försvarbar som prior på grund av icke-stationaritet. Kräv expanderande fönster med nyare viktning eller rullande 3–5 års fönster. Ingen halveringstid får optimeras i efterhand.

---

## J. ENTRY VS HOLD VS EXIT SEPARATION

Tre helt skilda användningsområden måste särskiljas:

1. **ENTRY**: Kan company prior förbättra valet mellan två H0-kandidater i Top-10?
2. **HOLD**: Kan den identifiera vilket befintligt innehav (rank 11–25) som har attraktiv remaining runway?
3. **EXIT**: Kan den indikera när opportunity cost gentemot en ny kandidat blivit för hög?

**Diagnostisk hypotes**: Archetype/prior-information bedöms vara mest relevant för **HOLD/EXIT** (utvärdering av återstående runway vs volatilitetsdrag) snarare än ENTRY. Detta behandlas strikt som en hypotes att testa, inte ett byggantagande.

---

## K. DRAWDOWN ÄR RELATIVT BOLAGET & DEDUPLICERING

### 1. Konceptualisering
En $-10\%$ rörelse i ett lågvolatilt investmentbolag ($\sigma \approx 15\%$) motsvarar en $\sim 2{,}5$-sigma-händelse (potentiellt tesbrott). Samma $-10\%$ i ett högvolatilt tillväxtbolag ($\sigma \approx 50\%$) är normalt brus ($< 1$-sigma).

### 2. Strikt deduplicering mot existerande signaler
Måttet måste dedupliceras mot:
- G97-P (högvolatilitetsfilter)
- Total volatilitet / Idiosynkratisk volatilitet ($r \approx 0{,}99\text{--}1{,}00$)
- Marknads-Beta
- State/Path/Memory-spåret ($TIS$, $DR2$, $MAE$)

**Krav**: Bolagsrelativ drawdown måste visa inkrementell förklaringskraft *efter kontroll för bolagets standardvolatilitet ($\sigma_i$) och H0-rank*. Annars är det endast volatilitet under nytt namn.

---

## L. RELATION TILL G97-P

### 1. Diagnostisk analys
G97-P filtrerar bort högrisk-/högvolatilitetsaktier över en specifik volatilitetströskel. Högvolatila aktier i det svenska universumet är kraftigt anrikade i vissa archetyper (t.ex. biotech, små tillväxtbolag, prospektering), medan mogna verkstads- och investmentbolag återfinns i låg/medvolatilitetssegmentet.

### 2. Klassificering
**POTENTIAL INDEPENDENT EXPLANATION OF G97**: Company archetype prior erbjuder en möjlig strukturförklaring (skilda payoff-fördelningar) till varför G97-P:s volatilitetsfilter fungerar.

*Restriktioner*: Ingen G97-variant får skapas, ingen interaktion vol $\times$ archetype testas, ingen G97-optimering.

---

## M. DEN VIKTIGASTE FALSIFIERINGEN

### 1. Primär falsifieringspremiss
> *"Conditional on current H0 score/rank AND realized 1y volatility, company archetype and/or historical company return distribution contains NO incremental information about the future return distribution ($P(R_{t \to t+h} \mid \text{H0 rank}, \sigma) = P(R_{t \to t+h} \mid \text{H0 rank}, \sigma, \text{Archetype})$)."*

### 2. Tidiga falsifieringskriterier
1. Archetype/prior-effekter försvinner efter icke-parametrisk kontroll för H0-rankdecil + 1y volatilitet.
2. Effekterna skiftar tecken eller kollapsar mellan de två oberoende fönstren (2014–2019 vs 2020–2026).
3. Bolagsspecifik prior kollapsar helt i populationsprio vid Empirical-Bayes shrinkage.

---

## N. MULTIPLE TESTING & HÖGST TRE HYPOTESER

För att förhindra feature-explosion och overfitting tillåts **högst tre förregistreringsbara hypoteser**:

1. **H-ARCHETYPE-1 (Broad Sector Archetype Prior)**:  
   *Betingat på H0-rankdecil och 1-årig volatilitet uppvisar breda sektor-archetyper (t.ex. Industri/Investment vs Tech/Growth) statistiskt signifikanta skillnader i conditional 24-veckors tail-avkastning ($P(R > +30\%)$ vs $P(R < -20\%)$).*

2. **H-VOL-RUNWAY-1 (Volatility-Normalized Pullback)**:  
   *Betingat på H0-rankband har en pullback normaliserad med bolagets egen volatilitet ($\frac{\Delta P}{\sigma_i}$) högre diagnostisk förklaringskraft för framtida rank-retention än absolut procentuell drawdown.*

3. **H-HOLD-RUNWAY-1 (Relative Opportunity Cost for Hold/Exit)**:  
   *Betingat på rank 11–30 och time-in-state har högvolatila tillväxt-archetyper en kortare återstående runway ($P(\text{Rank} \le 30 \text{ vid } T+4 \text{ paneler})$) än lågvolatila mogna archetyper.*

*Förbud*: Ingen gridsearch, ingen feature selection efter IC, ingen ML-modell.

---

## O. NEGATIVE CONTROL DESIGN

En negativ kontroll registreras ex-ante:

- **Baseline Model**: $P(R_{t \to t+h} \mid \text{H0 rank}, \text{Total Volatilitet}, \text{Beta})$
- **Challenger Model**: $P(R_{t \to t+h} \mid \text{H0 rank}, \text{Total Volatilitet}, \text{Beta}, \text{Company Archetype / Prior})$

**Krav för godkännande**: Challenger-modellen måste uppvisa statistiskt signifikant förbättring i log-likelihood / residual-IC ($t > 2{,}0$) på oberoende paneler. Om Challenger inte slår Baseline, underkänns Company Visit Card och spåret stängs.

---

## P. LEVERANS OCH SLUTGILTIGA BESLUT

### 1. Slutklassificering per delspår

1. **Company Archetype Prior (Bred Sektor K1)**: **TESTABLE WITH RESTRICTIONS**  
   *(Bred sektor täcker 420/420 tickers; kräver obligatorisk känslighetsanalys utan manual tags).*
2. **Company Archetype Prior (Fundamenta / Size / EV)**: **DATA_BLOCKED & FORBIDDEN IN MODEL TEST**  
   *(Survivorship bias i fundamenta; PIT share count ambiguity i K2A market cap).*
3. **Company-Specific Historical Prior**: **PARTIALLY TESTABLE**  
   *(Krympning $w_i \to 0$ gör att >85 % av Top-30 styrs av populations/archetype-prior).*
4. **Remaining Runway Distribution (Opportunity Cost)**: **TESTABLE**  
   *(Definierad som betingad relativ avkastningsfördelning givet H0-rank).*
5. **Bolagsrelativ Drawdown**: **REDUNDANT WITH EXISTING SIGNAL**  
   *(Subsumeras av volatilitet och G97-P om inte inkrementell effekt påvisas).*

---

### 2. Slutgiltiga beslut på huvudfrågorna

1. **Finns här en verklig informationslucka i H0?**  
   **JA.** Locked H0 är helt blind för bolagets struktur, volatilitets profil och return distribution tail-form. H0 behandlar alla bolag med samma rank identiskt.

2. **Kan den identifieras med befintlig data?**  
   **JA, DELVIS.** Kan identifieras via bred sektor (K1 V1 freeze) och prisderiverade fördelningsparametrar (volatilitet, skewness, TIS). **NEJ** för fundamental- och storleksbaserade archetyper (blockerade av data/governance-gates).

3. **Vilken är i så fall den minsta, renaste första hypotesen?**  
   **H-ARCHETYPE-1**: Betingat på H0-rankdecil och 1y volatilitet ger bred sektorklassificering (K1) inkrementell information om den betingade 24-veckors tail-avkastningsfördelningen ($P(R > +30\%)$ vs $P(R < -20\%)$).

4. **Vilket resultat skulle falsifiera hela idén tidigt?**  
   Om den residuala effekten av archetype/prior på framtida avkastningsfördelning är statistiskt noll ($t < 2{,}0$ eller $\Delta IC_{\text{residual}} \approx 0$) efter kontroll för H0-rankdecil och standard 1-årig volatilitet, falsifieras hela konceptet och spåret stängs omedelbart.

---
*Slut på feasibility-dokumentation för COMPANY ARCHETYPE / RETURN PRIOR / REMAINING RUNWAY.*
