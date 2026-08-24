# V2 slutlig forskningsinventering och nästa arbetsordning

## Slutsats

V2 behöver inte göras mer komplex för komplexitetens skull. H0 har överlevt neutralt ML-race, statisk fundamenta, makro, momentumhorisonter, prisväg/risk/trend, exits, sizing, korrelationsrefill, sektorinformation och hela den deduplicerade legacyinventeringen. Det som återstår är främst **ny bolagsspecifik eventinformation**, inte fler transformationer av samma prisdata.

## Vad som är testat och falsifierat

| Hypotesfamilj | Slutstatus | Slutsats |
|---|---|---|
| Ridge/ElasticNet, LightGBM, XGBoost, CatBoost på CORE | INGET STÖD | Slog inte enkel momentum robust på primära rankingmått. |
| Statisk FUNDAMENTA och macro i modeller | INGET STÖD | Inget robust marginalbidrag; fundamenta har dessutom survivorshipbias. |
| Momentumarkitektur 6/9/12/18m, kombinationer, Top-N, rebalance | FORWARD-ONLY | H0 valdes historiskt; G säger lovande men ej bekräftad. Ingen ny grid. |
| Drawdown resilience och trend strength | FORWARD-ONLY | Historiskt stöd; frysta H1/H2 kräver egen forwardevidens. |
| Consistency, jump diffuseness, residual momentum, dispersionproxy | SVAGT STÖD | Inte robust nog; prisproxyfamiljen är uttömd. |
| ATR-normalisering, ADX och ATR-stop | SVAGT STÖD | Ingen godkänd challenger. |
| Inverse-vol och target-vol | INGET STÖD | Förbättrade inte risk/alpha robust. |
| DD20, milestone exits, re-entry, rank/holding exits | INGET/SVAGT STÖD | Ingen robust exitregel; time stop endast svagt. |
| Correlation refill 0,85 | INGET STÖD | Ny korrelationstie-break på samma historik vore duplicering/tuning. |
| ROA/profitability och fundamental förändring | INGET STÖD | K3: revenue, marginaler, FCF och dilution gav inget; ej survivorship-safe. |
| Makro-/regimdiagnostik | SVAGT/OTILLRÄCKLIGT | K5 fann högst osäkra samband; ingen gate får härledas. |
| Sector momentum, sector-relative och breadth | INGET STÖD | Sector momentum var positivt men tidsinstabilt. |
| Sector-diversification tie-break | FORWARD-ONLY, FORMELLT INGET STÖD | HHI −4,49% missade låst ≥5%-gräns; ingen retuning. |
| Value within momentum | DATABLOCKERAD | PIT market cap/EV kan inte byggas på verifierad aktie-/splitbasis. |
| Report/PEAD, insider, dividend, buyback/issuance | DATABLOCKERADE | Inte falsifierade; saknar ännu färdig immutable PIT-eventgrund. |

Den fullständiga deduplicerade maskinläsbara matrisen finns i `research_k/FINAL_RESEARCH_INVENTORY_AFTER_K1_K3_K5.json`.

## Genuint obesvarad ny information

| Prioritet | Familj | Exakt fråga | Datastatus och blockerare |
|---:|---|---|---|
| 1 | Report / Attention / PEAD | Bekräftar eller motsäger ny rapportinformation H0 och följs den av drift? | MFN `published_at`, eventtyp, identitet och terminalcoverage måste bli immutable QA-godkända. |
| 2 | Insider | Tillför marknadskända insiderköp/-försäljningar information conditional on H0? | Officiell FI-historik, registreringstid, rättelser och terminalmapping krävs. |
| 3 | Event confirmation within momentum | Skiljer förregistrerade positiva/negativa events H0-kandidater? | Öppnas först efter att respektive J-källa är fryst. |
| 4 | Buyback / shareholder yield / issuance | Bekräftar faktisk kapitalallokering momentum eller visar dilution? | Known-time, negativa/nollposter och issuance-denominator är olösta. |
| 5 | Dividend-gap | Ger en offentliggjord utdelningsförändring plus initial reaktion senare drift? | Announcement/decision time saknas; ex-date får inte ersätta den. |
| 6 | K2 value within momentum | Tillför PIT-värdering information bland starka momentumaktier? | Outstanding shares, effective dates, splitbasis och aktieslagsaggregation saknas. NOT SURVIVORSHIP SAFE även efter teknisk lösning. |

Report och insider är de två högst prioriterade familjerna eftersom de är ekonomiskt distinkta från H0 och har en realistisk väg till PIT-data. Value är relevant men ska inte öppnas med en proxy. Dividend och buyback väntar tills verklig market-known time finns.

## Portföljkonstruktion är inte alpha

H0 har effective sectors 4,93 och top-two-sector weight 51,54%. K1:s tie-break gav lägre HHI, högre historisk CAGR/Sharpe och lägre MaxDD, men HHI-reduktionen var 4,49% mot krävt 5%. Den är därför formellt underkänd och får endast leva som en separat förseglad forward-hypotes.

Korrelationsbaserad refill har redan testats i Research I Batch 3 och fick inget stöd. En ny korrelationstie-break med annan tröskel eller formulering på samma historik är inte genuint ny; det är parameterretuning och **EJ MOTIVERAD**. Sizing, target-vol och exits är också redan täckta.

## Vad måste ske före slutligt modellbeslut?

### A — bör rimligen testas om datan klarar QA

1. Report/PEAD conditional on H0.
2. Insider conditional on H0.

Dessa är de enda två återstående familjerna som både är tydligt informationsmässigt nya och har en realistisk dataanskaffningsväg. De behöver inte försena starten av H0-forward, men bör avslutas innan det breda historiska forskningsprogrammet stängs definitivt.

### B — värdefullt men kan vänta

- Event-confirmation som samlad fråga efter separata eventtester.
- Buyback/shareholder yield om semantik och known-time senare löses.
- K2 value om en oberoende shares-outstanding-källa tillkommer.

### C — blockerad tills ny data finns

- Dividend-gap.
- Buyback/issuance i nuvarande dataläge.
- PIT market cap/EV och value.

### D — ska inte forskas vidare historiskt

- Nya momentumhorisonter, vikter, Top-N eller rebalancefaser.
- Fler riskjusterade momentum-, trend-, consistency-, jump-, ATR- eller ADX-varianter.
- ML-/macro-/fundamentablends på samma data.
- Nya exit-, stop-, sizing-, sektor- eller korrelationsparametrar.
- Retuning av K1:s tie-break eller dess 5%-gräns.

## Stoppkriterier

V2:s diskretionära alphaforskning stoppas när följande gäller:

1. Report och insider har antingen testats från immutable PIT-data eller dokumenterats permanent blockerade.
2. Ingen återstående familj tillför ekonomiskt distinkt information; omformulering av befintlig prisdata räknas inte.
3. Varje öppnad familj får en enda preregistrerad huvuddefinition, inte ett grid.
4. Om report och insider inte visar robust inkrementell conditional-on-H0-information stängs historisk alphaforskning och H0 behålls.
5. Value, dividend och buyback öppnas endast vid faktisk ny data; deras blockering håller inte programmet artificiellt öppet.
6. Ingen portföljregel får retunas historiskt. Lovande underkända idéer är forward-only.
7. Nästa bekräftelse för H0 ska komma från untouched forward, inte ännu en historisk variant.

## Forwardbeslut

**Ja — H0 bör redan nu fortsätta ett strikt, orört forward/paper-test parallellt med dataarbetet.**

Principerna är:

- exakt fryst H0, universum, 8v-fas, V4 execution, kostnad och terminalhantering,
- ranking, Top 30, holdings och trades förseglas före framtida utfall,
- append-only logg med data-as-of, kodversion, manifest och SHA256,
- aldrig skriva om historisk prediction efter datakorrigering,
- H1/H2 och framtida challengers får egna separata journaler från respektive freeze-tidpunkt,
- challengerresultat får aldrig ändra eller förorena H0:s forwardhistorik,
- checkpoints styrs av antal nya perioder/IC-datum, aldrig av resultatkvalitet.

Det slutliga arbetsflödet är därför: **fortsätt H-forward nu → slutför MFN → slutför FI/J3 → testa report om QA passerar → testa insider om QA passerar → stäng historisk forskning eller vänta på verkligt ny data.**
