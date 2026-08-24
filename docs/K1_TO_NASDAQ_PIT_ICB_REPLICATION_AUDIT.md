# K1 → NASDAQ PIT ICB — REPLICATION AUDIT & PREREGISTRERING

Datum: 2026-08-18 · Status: **PREREGISTRERING LÅST — INGA TESTER KÖRDA**
Preregistrering SHA256: `d9254c5e01ebe8fe3dcdaad9ce6c08c603f4d23bb8b8679282ffe25618a2ae9a`

Detta dokument är först en provenance-/governanceaudit, därefter en preregistrering.
Det **ändrar inga historiska resultat och inga gamla domar**. Varje K1-experiment som
föll mot sin egen preregistrering redovisas fortsatt som fallet. Frågan här är en annan:
*är experimentet informativt för H0 V3 + PIT ICB?*

---

## STEG 0 — Pre-flight

| Kontroll | Utfall |
|---|---|
| `tools/repo_integrity_gate.py` | **PASS** |
| H0 V3 freeze-kedja (prereg → indata-manifest → implementation → resultat) | **hash-verifierad OK** |
| H0 V3 ändrad i detta uppdrag | **Nej** |
| Forskningstester körda i detta uppdrag | **Noll** |

---

## STEG 1 — Vad K1 faktiskt testade (rekonstruerat ur koden, inte ur sammanfattningar)

Källa: `tools/spark_k1_sector_information_diversification.py` (120 rader), läst rad för rad.

Tre fynd som ingen tidigare sammanfattning nämnde:

**1. K1 kördes inte mot H0.** Baslinjen i koden är
`sparg/results/SPARG_V4_EXECUTABLE_CHAMPION_FALSIFICATION_V3` — SPARG V4:s champion.
Varken locked H0 eller H0 V3.

**2. Sektoretiketten var statisk och odaterad.** `sector_classification_v1` ger ett enda
`canonical_sector` per instrument, plus sex manuella (`AGRO, ETX, JOSE, MIC-SDB, SMF, TETY`).
0 av 420 instrument har mer än ett intervall. K1:s eget QA-dokument sa det rent ut:
*"Historiska sektorbyten mellan snapshots kan inte observeras fullständigt."*

**3. K1 använde aldrig tvåfönsterkriteriet.** Ett fönster, delat i kronologiska halvor.

Exakta definitioner som återanvänds oförändrade i replikationen:

```python
z['sector_momentum']  = z.groupby(['panel_date','sector']).score.transform('mean')
z['sector_relative']  = z.score - z.sector_momentum
z['positive']         = z.mom_52w > 0
z['sector_breadth']   = z.groupby(['panel_date','sector']).positive.transform('mean')
```

Diversifieringens fem villkor (alla måste hålla) och dess tie-break-algoritm
(fönsterbredd 3, `min(pool, key=(counts[sector], -score, kod))`, N=30) är likaså
återgivna ordagrant i preregistreringen.

---

## STEG 2 — Klassificering av varje K1-hypotes

Skillnaden mellan *"det experimentet föll"* och *"är det informativt idag"* är avgörande.
Fyra av hypoteserna behövde temporal sektorinformation för att över huvud taget vara
**identifierade** — och den informationen fanns inte. Att de föll är korrekt redovisat;
det de föll mot var dock en statisk etikett, inte sektortillhörighet vid beslutstidpunkten.

| # | Hypotes | K1:s dom (står kvar) | Klassificering |
|---|---|---|---|
| A | Sector momentum | SVAGT STÖD (mean IC52 +0,0214; föll temporal falsifiering −0,0266 / +0,0694) | **REQUIRES_PIT_ICB_REPLICATION** |
| B | Sector-relative momentum | INGET STÖD (−0,0004; halvor +0,0063 / −0,0071) | **REQUIRES_PIT_ICB_REPLICATION** |
| C | Sector breadth | INGET STÖD (−0,0125; Top-30 −0,0674) | **REQUIRES_PIT_ICB_REPLICATION** |
| D | Diversification tie-break | INGET STÖD — HHI-reduktion 4,49 % mot preregistrerat ≥ 5 % | **REQUIRES_PIT_ICB_REPLICATION** |
| E | K1G soft sector penalty | `'K1G':'SKIPPED'` — hoppades över **före** resultat | **NOT_PREVIOUSLY_TESTED** |
| F | Industry-relative momentum | markerad DELVIS TESTBAR, kördes aldrig | **NOT_PREVIOUSLY_TESTED** |
| G | Sektorspecifika KPI:er | DATABLOCKERAD (480/480 HTTP 400) | **DATA_BLOCKED** |

**A–D:** varje feature är en funktion av sektortillhörighet *vid t*. Med en statisk etikett
mäts en storhet som per konstruktion inte kan röra sig. Nasdaq-P1 visar att den rör sig:
**176 av 756 instrument byter industry, 398 av 756 byter supersector.** Det är inte ett skäl
att ogiltigförklara den gamla domen — det är skälet att hypotesen fortfarande är oavgjord.

**D** förtjänar en särskild notering: den föll på **ett** av fem villkor, och missade med
0,51 procentenheter. De fyra andra villkoren höll. Det gör den till en replikationskandidat,
inte till ett skäl att flytta tröskeln. Tröskeln ≥ 5 % står oförändrad.

**E** förblir olicensierad. K1 hoppade över den eftersom ingen icke-godtycklig straffparameter
kunde väljas utan parametersökning. Det skälet står oförändrat, och mandatets villkor
(parameterfri eller på förhand ekonomiskt definierad) är inte uppfyllt.

**F** är den enda genuint nya hypotesen. K1 hade exakt canonical industry för 352 av 420
instrument; Nasdaq ger nu industry med 95 % täckning på V3:s universum.

**G** står kvar som blockerad — både på data och på att `fundamental_kpis` är
`FORBIDDEN_IN_MODEL_TEST` i governanceregistret.

Ingen hypotes klassificeras som `VALID_AND_STILL_INFORMATIVE` eller `VALID_FOR_OLD_SYSTEM_ONLY`:
samtliga testade hypoteser delar samma identifikationsbrist. Ingen klassificeras som `INVALID` —
inget experiment var felkonstruerat mot sin egen preregistrering.

---

## STEG 3 — ICB-datagate

Mätt mot **H0 V3:s faktiska eligible universum** (inte mot V2:s råa rankningspopulation),
med uppslagsregeln *senaste rapportmånad vars `known_from` ≤ beslutsdatum*:

| Fönster | Nivå | Täckning | Sämsta panel | p10 |
|---|---|---|---|---|
| 2014-2019 | industry | 95,4 % | 86,7 % | 90,0 % |
| 2014-2019 | supersector | 95,4 % | 86,7 % | 90,0 % |
| 2020-2026 | industry | 94,9 % | 86,7 % | 90,0 % |
| 2020-2026 | supersector | 94,9 % | 86,7 % | 90,0 % |

**`known_from`-brott: 0.** Ingen månad M:s data används före sin publicering.
Gaten passerar med marginal till STOP-tröskeln (80 % per panel).

Taxonomiregimskiftet 2012-01 → 2012-02 ligger före båda fönstren och påverkar dem inte.
Instrument utan ICB vid beslutstidpunkten exkluderas ur featureberäkningen för den panelen
men behålls i portföljen — ingen imputering, ingen bakåtprojektion.

---

## STEG 4–6 — ICB-PIT REPLICATION FAMILY

Fem replikationer, samtliga mot **fryst, oförändrad H0 V3** (signal, parametrar, viktning,
kostnad, rebalansfrekvens orörda) och **H0 V3:s PIT-eligibility som universum**.

| ID | Namn | Typ | Definition |
|---|---|---|---|
| R1 | Sector momentum | information | K1:s formel ordagrant, industry-nivå |
| R2 | Industry-relative momentum | information | **ny** — score minus industry-medel |
| R3 | Diversification tie-break | beslutsregel | K1:s algoritm ordagrant, fönster 3, N=30 |
| R4 | Sector-relative momentum | information | K1:s formel ordagrant |
| R5 | Sector breadth | information | K1:s formel ordagrant |

**Acceptanskriterier är K1:s egna, ordagrant** — inga nya, inga justerade. R1/R2/R4/R5 mäts
mot K1:s IC-kriterium (`mean_ic52 ≥ 0,01` och `median ≥ 0` och `top30 ≥ 0` och
`positive_ic_share ≥ 0` och `Δmean_ic52 > 0` i båda halvorna). R3 mäts mot K1:s femvillkorstest
(HHI ≤ 0,95×, fler effektiva sektorer, CAGR ≥ −1 pp, excess Sharpe ≥ −0,05, omsättning ≤ 1,25×).

**Skärpningen ligger enbart i replikationskravet:** kriteriet måste hålla **oberoende i båda
fönstren**. En replikation som passerar i ett fönster räknas som fallen. Det är också familjens
primära multipeltestkontroll; samtliga fem redovisas alltid tillsammans.

Regel 6 (överlappskorrigerat `t/√h`) och Regel 8 (materialitet mot placebobandet ±2,4 pp och
detektionsgolvet ~4 pp) gäller per test.

**Steg 6 explicit:** diversifieringsregeln är preregistrerad **oförändrad**. Frågan är om den
fördefinierade regeln replikerar — inte vilken sektorbegränsning som fungerar bäst. K1:s
utfall (CAGR 25,29→27,27 %, Sharpe 1,379→1,488, MaxDD −4,43→−2,94 %, HHI −4,49 %) är
uttryckligen **förbjudna** som underlag för nya parametrar eller trösklar.

Förbjudet i hela familjen: grid search, parameteroptimering, efterhandsändrade trösklar,
featurekombination efter observerade resultat, tree/hierarkiska interaktioner, Size × Sektor.

---

## STEG 7 — Ordning mot trädspåret

**ICB-replikationen ska gå före Size-replikationen, och båda före varje trädspår.**

Skälet är inte preferens utan identifierbarhet. G-HIER-1/G-HIER-2 står som
`NON_COMPUTED_CLAIM`, och G-HET-1/G-SIZE-HET-1 som `NOT_IDENTIFIED`. Ett träd över
Size × Sektor skattar en interaktion mellan två dimensioner som **ingen av dem är
identifierad var för sig** på PIT-korrekt data. Interaktionen kan då inte tolkas —
den skulle ärva båda dimensionernas identifikationsbrist och dölja den bakom en
modellstruktur som ser ut att ha svarat.

Ordningen är alltså: (1) sektor identifierad PIT-korrekt, (2) size identifierad PIT-korrekt,
(3) först därefter är frågan om interaktion välställd. Sektor går först eftersom ICB-datan
redan är byggd, validerad och gate-passerad; size-serien kräver ytterligare arbete.

Internt i familjen: R1 → R2 → R3 → R4 → R5. Prediktion före beslut, enligt projektets
etablerade evidensstege. R3 körs dock även om R1 och R2 faller — den är självständigt
försvarbar som *riskbegränsning*, och dess kriterier är koncentrationsbaserade, inte
avkastningsbaserade.

---

## STOP

Preregistreringen är färdig, hashad och tidsstämplad. **R1–R5 har inte körts.**
Exekvering kräver separat mandat.
