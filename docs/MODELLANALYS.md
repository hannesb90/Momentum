# Djupanalys: Momentum-appen vs riktiga plattformar och forskning

> Mål med granskningen: bedöma om appen är *tillräckligt bra för att fungera som
> referens för handel åt en bred publik*. Slutsatsen är ärlig: tekniskt är detta
> ett ovanligt gediget bygge — på flera punkter mer rigoröst än de flesta
> hobby-/retail-verktyg — men det är **ännu inte** lämpligt som handelsreferens
> för allmänheten, av några hårda skäl (survivorship bias, avsaknad av
> jämförelseindex/alfa, ingen live-historik, viss dataläckage, och regulatorisk
> klassificeringsrisk). Nedan: vad som redan håller måttet, var bristerna finns,
> och en prioriterad väg framåt.

Datum: 2026-06-26

---

## 0. Status efter åtgärder (2026-06-26)

Följande punkter är nu **åtgärdade i kod** (allt utom #1 datakälla och #4 juridik,
som medvetet väntar):

| # | Punkt | Status |
|---|---|---|
| 2 | Benchmark / alfa / beta | ✅ `backtest/benchmark.py`, i stats.json + frontend (Backtest + Overview) |
| 3 | Live track record | ✅ `backtest/paper_trader.py`, `/api/paper-ledger`, Overview-kort |
| 5 | Purge/embargo i walk-forward | ✅ `walk_forward_splits(embargo_weeks=FORWARD_WEEKS)` |
| 6 | Long-only / marknadsexponering | ✅ beta exponerad + tydligt kommunicerad (full long-short kvarstår som större projekt) |
| 7 | Spread för småbolag | ✅ likviditetsberoende halv-spread i kostnadsmodellen |
| 8 | DSR `trial_sr_std` | ✅ skattas empiriskt från tröskelsökningen |
| 1 | Survivorship-fri data | ⏳ väntar (kräver betald datakälla) |
| 4 | Regulatorisk status | ⏳ väntar (kräver jurist) |
| 10 | Fundamenta-features | ⏳ kopplad till #1:s datakälla (point-in-time) |

> Viktigt: dessa är **kod**-åtgärder. De blir synliga i siffrorna först efter en
> full omträning (träningsservicen), och benchmark/alfa avgör då om de tidiga-
> entry-features och den nya tröskeln faktiskt skapar *mer-* avkastning mot index.

---

## 1. Sammanfattande omdöme

| Dimension | Betyg | Kommentar |
|---|---|---|
| Mjukvaru-/pipeline-kvalitet | ★★★★☆ | Ren, modulär, end-to-end, polerad PWA. |
| Statistisk rigor (overfitting-skydd) | ★★★★☆ | DSR/PSR, block bootstrap, frusen holdout, walk-forward, kalibrering. Saknar purged/embargo-CV. |
| Realism i backtest (kostnader) | ★★★☆☆ | Sqrt-marknadsimpact + likviditetstak är rätt metodik; men spreadkostnad för svenska småbolag underskattas, och survivorship bias är allvarlig. |
| Vetenskaplig förankring (signaler) | ★★★★☆ | Momentum/likviditet/volatilitet = exakt de signaler topplitteraturen lyfter (Gu/Kelly/Xiu). |
| Lämplighet som publik handelsreferens | ★★☆☆☆ | Blockeras av survivorship bias, avsaknad av benchmark/alfa, ingen live-historik och regulatorisk risk. |

**Kärnbudskap:** appen är en imponerande *ingenjörs- och pedagogikprodukt*. För att bli en *trovärdig handelsreferens* krävs framför allt tre saker: (1) survivorship-fri point-in-time-data, (2) jämförelse mot ett passivt index (alfa, inte bara absolutavkastning), och (3) en verifierad live-/pappershandelshistorik. Utan dessa kan man inte säga om strategin tillför värde eller bara återskapar (en sämre version av) indexavkastning.

---

## 2. Så gjordes granskningen

- **Kodgranskning** av hela pipelinen: feature engineering, LGBM+LSTM-ensemble med walk-forward, isotonisk sannolikhetskalibrering, Kelly-sizing, backtester (kostnader/likviditet/korrelations- och sektorspärrar/drawdown-guard), robusthet (block bootstrap + PSR/DSR), drift-monitor, regimanalys, datainläsning.
- **Litteratur**: Jegadeesh & Titman (momentum), tvärsnitts- vs tidsserie-momentum, residual-/volatilitetsskalad momentum, Gu, Kelly & Xiu (*Empirical Asset Pricing via Machine Learning*, RFS 2020), López de Prado (*Advances in Financial Machine Learning*; PSR/DSR; purged & combinatorial purged CV).
- **Plattformsjämförelse**: QuantConnect/LEAN, Zipline + Alphalens/Pyfolio, Backtrader, samt robo-advisor-/copy-trading-perspektiv.
- **Regelverk**: ESMA/MiFID II om vad som utgör investeringsrådgivning och om disclaimers.

Källor listas i avsnitt 8.

---

## 3. Vad som redan håller hög klass

Detta ska sägas tydligt — flera delar är bättre än i typiska retail-projekt:

1. **Frusen holdout (104 v).** Modellen tränas aldrig på de sista ~2 åren. Detta är *exakt* rätt disciplin och saknas i de flesta hobbybacktester.
2. **Walk-forward + isotonisk kalibrering på valideringsdata** (aldrig på träningsdata). Att kalibrera sannolikheter innan de matas in i Kelly-sizing är något även proffs ofta hoppar över.
3. **Deflated Sharpe Ratio (Bailey & López de Prado).** Att överhuvudtaget deflatera för multipeltestning är ovanligt moget. Den nyligen tillagda tröskelsökningen räknas dessutom in i `n_trials`, vilket är metodologiskt korrekt.
4. **Sqrt-marknadsimpact** (`MARKET_IMPACT_COEF·√(trade/ADV)`) + **likviditetstak** (max 10 % av ADV/vecka). Detta är just den standardspecifikation litteraturen rekommenderar för exekveringskostnad — inte den naiva "fast %"-modellen.
5. **Signalvalen är vetenskapligt förankrade.** Gu/Kelly/Xiu (2020) finner att de dominerande prediktorerna i ML-baserad aktieprissättning är *varianter av momentum, likviditet och volatilitet* — precis appens feature-grupper.
6. **Riskhantering på portföljnivå:** korrelationsfilter (slår ihop redundanta positioner), sektorexponeringstak (40 %), drawdown-guard som de-leveragar. Detta är mer än de flesta retail-strategier har.

---

## 4. Jämförelse mot riktiga plattformar

| Förmåga | Denna app | QuantConnect/LEAN | Zipline+Alphalens | Backtrader |
|---|---|---|---|---|
| Survivorship-fri, point-in-time-data | ✗ (yfinance) | ✓ (terabyte point-in-time, corporate actions) | delvis (bundles) | ✗ (egen data) |
| Live/pappershandel mot mäklare | ✗ | ✓ | ✗ | delvis |
| Faktor-/performance-attribuering | begränsad | ✓ | ✓ (Alphalens/Pyfolio standard i akademisk quant) | begränsad |
| Alternativ data (sentiment, insynshandel) | ✗ | ✓ (40+ vendorer) | ✗ | ✗ |
| Konsumentvänligt UI / pedagogik | ✓✓ (unik styrka) | ✗ (utvecklarverktyg) | ✗ | ✗ |
| Statistiskt overfitting-skydd inbyggt | ✓ (DSR/bootstrap) | delvis (egen kod) | ✗ | ✗ |

**Tolkning:** appens nisch är inte att konkurrera med LEAN som institutionell backtester — det är att vara en *förklarande, konsumentvänlig momentum-dashboard*. Det är en reell och försvarbar styrka. Men de tre sakerna proffsplattformar tar för givna och som appen saknar — **point-in-time-data, live-exekvering och attribuering mot benchmark** — är just de som krävs för att resultaten ska gå att lita på som handelsreferens.

---

## 5. Förankring i forskningen

- **Tvärsnitts-momentum** (Jegadeesh & Titman 1993; bekräftad 2001 och i 30-årsöversikten 2022) köper relativa vinnare. Appen använder relativ styrka (`rs_*`, `rank_*`) men slutsignalen är *absolut* (P(upp) > tröskel) snarare än ren topp-N-rotation. Litteraturen visar att relativ konstruktion ofta är robustare — den nyligen införda data-drivna tröskeln mildrar detta men ersätter inte en topp-N-design.
- **Förbättringar som litteraturen pekar ut och som appen delvis/inte fångar:**
  - *Residual-momentum* (momentum på faktorjusterade avkastningar) ger högre och stabilare premie — **saknas**.
  - *Volatilitetsskalning av positioner* (ex ante invers volatilitet) — **finns delvis** via Kelly-vol-targeting.
  - *Intermediär look-back* (utelämna senaste månaden för att undvika kortsiktig reversering) — **saknas** (appen använder bl.a. `roc_4w` direkt).
- **ML lönar sig — men marginellt och kostnadskänsligt.** Gu/Kelly/Xiu visar att träd/neuronnät kan dubbla regressionsbaserade strategier, men nettoavkastning efter kostnader är där de flesta ML-signaler dör. En 1,5-Sharpe i friktionsfri backtest kan falla under 0,5 efter realistisk fill-modellering. Appens kostnadsmodell är därför *avgörande* — och underskattar troligen spreadkostnaden i illikvida svenska småbolag.

---

## 6. Identifierade brister och förbättringar (prioriterat)

### KRITISKT (blockerar "referens för bred publik")

1. **Survivorship bias i datan.** yfinance ger bara bolag som finns idag. Konkursade/avnoterade/uppköpta saknas helt → CAGR/Sharpe överskattas systematiskt, värst bland småbolag (som du just utökade till). Koden *erkänner* detta i en docstring, men för en publik referens är det diskvalificerande tills point-in-time-data används (t.ex. Norgate, Polygon, EOD Historical).
2. **Ingen benchmark / inget alfa.** Hela appen visar *absolut* avkastning. Den jämför aldrig mot köp-och-behåll av OMXS30/indexet. En strategi med 1,1 % CAGR när indexet gav ~10 %/år *förstör* värde — men det syns inte. **Detta är den enskilt viktigaste saknade biten för en handelsreferens.** Lägg till indexjämförelse (CAGR, Sharpe, max DD) och rullande relativ avkastning överallt där backtest-statistik visas.
3. **Ingen live-/pappershandelshistorik.** Backtest ≠ verklighet. Innan allmänheten ska kunna "lita på" signalerna behövs en framåtblickande, tidsstämplad track record (paper trading), helst med samma kostnadsantaganden som backtesten.
4. **Regulatorisk klassificering.** ESMA är tydlig: publika trade-signaler kan i app-/sociala-medier-kontext utgöra *personlig* investeringsrådgivning, och **disclaimers tar inte bort den klassificeringen** eller ansvaret. Att rikta detta till "bred publik" kan trigga MiFID II-skyldigheter (lämplighetsbedömning, kostnadsupplysning m.m.). Måste utredas juridiskt innan publik lansering.

### HÖGT

5. **Dataläckage i walk-forward (saknad purge/embargo).** Targets är 4-veckors framåtavkastning. Mellan tränings-, validerings- och testfönster finns ingen "purging"/embargo, så de sista ~4 veckornas labels i ett fönster överlappar nästa fönsters features. López de Prado: använd **purged k-fold** (och helst **Combinatorial Purged CV**) som ger lägre Probability of Backtest Overfitting och pålitligare DSR. Minst: lägg in en `FORWARD_WEEKS`-embargo mellan train/val/test.
6. **Long-only.** Akademisk momentum är long-short; long-only fångar bara halva premien och bär full marknadsrisk. Antingen kommunicera tydligt att detta är en long-only-tolkning, eller lägg till en kort-/neutral-ben (eller en marknadshedge).
7. **Spread-/kostnadskalibrering för småbolag.** 0,1 % courtage + 0,1 % slippage är rimligt för Large Cap men optimistiskt för Micro/Nano Cap där spreaden kan vara 1–3 %+. Inför en likviditetsberoende spreadkostnad (t.ex. funktion av ADV/cap-tier), annars blir den utökade småbolagsavkastningen illusorisk.

### MEDEL

8. **DSR-förenkling.** `trial_sr_std = 1.0` antas i stället för att skattas från de faktiska trial-Sharpe-kvoternas spridning. Skatta den empiriskt när flera parameterval körs, annars kan DSR vara fel-kalibrerad.
9. **Regimanalysen är inte path-dependent** (erkänt i koden). OK som diagnostik, men kommunicera att CAGR/MaxDD per regim inte är handlingsbara på samma sätt.
10. **Inga fundamenta/point-in-time-faktorer.** Endast pris/volym. Att lägga till value/quality/size (point-in-time, för att undvika look-ahead) ligger i linje med faktormomentum-litteraturen och Gu/Kelly/Xiu.
11. **Hyperparametrar är statiska** (LGBM/LSTM). Risk för subtil överanpassning över tid; överväg periodisk omval inom walk-forward (med purge).

---

## 7. Väg framåt — konkret roadmap

**Fas 1 – Trovärdighet (måste, före varje publik ambition)**
- Byt datakälla till survivorship-fri point-in-time (Norgate/Polygon/EODHD).
- Lägg till **benchmark överallt**: index-CAGR/Sharpe/MaxDD + rullande relativ avkastning och "alfa vs OMXS30".
- Inför purge/embargo i walk-forward (minst `FORWARD_WEEKS`), helst CPCV.

**Fas 2 – Realism**
- Likviditets-/cap-tier-beroende spreadkostnad.
- Starta tidsstämplad paper trading; visa live-track record i appen bredvid backtesten.

**Fas 3 – Edge**
- Residual-momentum + intermediär look-back (utelämna senaste månaden).
- Utvärdera long-short eller marknadshedge.
- Point-in-time-fundamenta som tilläggsfeatures.

**Fas 4 – Regelefterlevnad & kommunikation**
- Juridisk bedömning av MiFID-status; tydlig "utbildning, ej rådgivning"-positionering som faktiskt håller (inte bara en disclaimer).
- Visa osäkerhet ärligt: holdout-siffror först, konfidensintervall, och "så här illa kan det gå".

---

## 8. Källor

- Jegadeesh & Titman, momentum — 30-årsöversikt: <https://link.springer.com/article/10.1007/s11408-022-00417-8>
- Tvärsnitts- vs tidsserie-momentum (CME): <https://www.cmegroup.com/education/files/improving-time-series-momentum-strategies.pdf>
- Gu, Kelly & Xiu, *Empirical Asset Pricing via Machine Learning* (RFS 2020): <https://academic.oup.com/rfs/article/33/5/2223/5758276>
- López de Prado, *Advances in Financial Machine Learning* (kap. om CV/överanpassning): <https://toc.library.ethz.ch/objects/pdf03/e01_978-1-119-48208-6_01.pdf>
- Purged & Combinatorial Purged Cross-Validation: <https://en.wikipedia.org/wiki/Purged_cross-validation>
- Backtest-överanpassning, jämförelse av out-of-sample-metoder: <https://www.sciencedirect.com/science/article/abs/pii/S0950705124011110>
- Plattformsjämförelse (QuantConnect/Zipline/Backtrader): <https://alphagaindaily.com/en/blog/backtrader-vs-zipline-vs-quantconnect>
- QuantConnect data/survivorship: <https://newyorkcityservers.com/blog/quantconnect-review>
- Realistisk backtest (kostnader/slippage/sqrt-impact): <https://www.hyper-quant.tech/research/realistic-backtesting-methodology>
- Square-root market impact: <https://mfe.baruch.cuny.edu/wp-content/uploads/2012/09/Chicago2016OptimalExecution.pdf>
- ESMA om definitionen av investeringsrådgivning under MiFID II: <https://www.esma.europa.eu/sites/default/files/2023-07/ESMA35-43-3861_Supervisory_briefing_on_understanding_the_definition_of_advice_under_MiFID_II.pdf>
- ESMA/Freshfields om reviderad rådgivningsdefinition: <https://www.freshfields.com/en/our-thinking/blogs/risk-and-compliance/understanding-the-definition-of-investment-advice-under-mifid-esma-revises-13-y-102ik46>
