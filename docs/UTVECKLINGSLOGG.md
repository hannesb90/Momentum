# Momentum – Utvecklingslogg & beslutsregister

> **Syfte med detta dokument.** En destillerad kontext för människor *och
> AI-agenter* som ska fortsätta arbeta i repot. Det fångar **resonemanget,
> testerna och resultaten** bakom modellens nuvarande tillstånd — utan
> chatthistorik. Läs detta + `docs/MODELLANALYS.md` så har du hela bilden av
> *varför* koden ser ut som den gör och vad som redan är prövat och förkastat.
>
> Komplement: `docs/MODELLANALYS.md` (extern kvalitets-/forskningsgranskning,
> 2026-06-26). Detta dokument är nyare och uppdaterar flera av dess slutsatser
> (särskilt: era-analysen besvarade den öppna frågan "tillför strategin värde
> mot index?" — svaret blev *nej, inte i den moderna algo-eran*).

Senast uppdaterad: 2026-06-28

---

## 1. Projektet i en mening

**Momentum** är en ML-baserad momentum-/trendhandelsapp för svenska aktier
(FastAPI-backend + React/Vite-PWA), driftad på en Raspberry Pi. Mål: *tillräckligt
bra för att fungera som referens för handel åt en bred publik.* Den centrala
designprincipen genom hela arbetet har varit **brutal ärlighet**: vi behåller bara
ändringar som bevisar sig på den frusna holdouten / rent OOS, och vi reverterar
allt som bara ser bra ut in-sample.

Stack & drift:
- **Backend:** `momentum_ml/` – LightGBM + LSTM-ensemble, walk-forward med
  purge/embargo, isotonisk kalibrering, Kelly-/risk-paritets-sizing, realistisk
  backtester (kostnader, sqrt-impact, likviditetsspread, drawdown-guard,
  korrelations-/sektorspärr, marknadsfilter).
- **Frontend:** `frontend/` – PWA, segment-toggle (stor-/småbolag), signal-/
  aktievyer, backtest- och OMXS30-jämförelse.
- **Drift:** Pi:n kör API + en sync-timer (var 15:e min) + en tränings-timer.
  Molnmiljön där koden utvecklas når **varken Yahoo eller mfn.se** (egress-spärr)
  → all datahämtning/körning sker på Pi:n.

---

## 2. Strategins design (nuvarande) + rationale

Nyckelparametrar i `momentum_ml/config.py` och *varför* de är som de är:

| Parameter | Värde | Varför |
|---|---|---|
| `FORWARD_WEEKS` | 13 (≈kvartal) | 4v låg i **reversal**-regimen (aktier som just stigit rekylerar) → trendande bolag fick aldrig signal (SAAB-fallet). 13v ligger i **momentum**-regimen. |
| `REBALANCE_WEEKS` | =13 | Veckovis handel på en kvartalssignal churnar portföljen (~40 %+ omsättning/v) → 8–20 pp/år i kostnadsdrag. Håll innehavet en hel horisont. |
| `EMBARGO_WEEKS` | =13 | Purge/embargo i walk-forward (López de Prado) – sista labelsen i ett fönster överlappar annars nästa fönsters features. |
| `XS_TARGET` | True (q=0.67) | **Tvärsnitts-target**: positiv klass = topp-tertil av universumets framåtavkastning *samma vecka*. Absolut target (">5 %") gör att prob_up kollapsar mot basfrekvensen i svaga perioder (platt, AUC~0.5). Relativ fråga ger äkta dispersion att vikta på (Jegadeesh-Titman). |
| `MOM_FORMATION_WEEKS`/`MOM_SKIP_WEEKS` | 52 / 4 | Klassisk **12-1-momentum** (formation 52v, hoppa över senaste 4v) – skip-fönstret undviker kortsiktig reversering. |
| `CONVICTION_BLEND` | 0.5 | Krymp conviction-vikt mot likavikt (Ledoit-Wolf-anda). prob_up är <0.5 för nästan alla → ren Kelly kollapsar till få namn. Blend håller N diversifierade innehav. |
| `SIZING_MODE` | `inverse_vol` | Fördelar vikt ∝ 1/volatilitet (risk-paritet) bland de N namnen. Slog conviction på hela rutnätet (se §5). Urvalet (vilka N) styrs alltid av prob_up. |
| `VOL_TARGET_ENABLED` / `_ANNUAL` | True / 0.10 | **Target-vol-overlay** (Barroso & Santa-Clara): skalar bruttoexponering mot 10 % årlig vol, long-only, tak 1.0 (skalar bara ner mot kontanter). Sänkte drawdown kraftigt (se §5). |
| `MAX_POSITIONS` | 10 (large), 20 (small) | Sizing-svep: 10 optimalt för storbolag; småbolag tjänar på mer diversifiering. |
| `MARKET_FILTER_EXPOSURE` | bull/sideways/bear = 1.0/0.6/0.25 | Long-only de-risking mot kontanter i svag regim (Faber/dual-momentum), aldrig blankning. |
| Kostnader | courtage 0.1 % + slippage 0.1 % + sqrt-impact + likviditets-spread (0.05–2 %) | Realistisk exekvering; spreaden växer för tunt handlade bolag så småbolagsavkastning inte blir illusorisk. |
| `HOLDOUT_WEEKS` | 104 | ~2 år som modellen aldrig tränas på – den ärliga domaren. |
| Segment | large=[Large,Mid]→`results/`, small=[Small]→`results/small/` | **Två separata modeller** så tvärsnitts-rangordningen sker inom jämförbara bolag (en stabil storbolagstrend drunknar annars i småbolagens kast – SAAB föll från prob_up 1.0 till 0.35 i blandat universum). |

Universum (Large/Mid): **126 tickers, 46 features** efter likviditets-/delisting-filter.

---

## 3. DEN STORA INSIKTEN: era-analysen

Det viktigaste enskilda resultatet i hela projektet.

**Frågan:** håller edgen i den algo-dominerade eran (Stockholmsbörsen blev
algo/HFT-tung ~2010-2013: Nasdaq INET okt 2010 + MiFID I)? Verktyg:
`momentum_ml/era_analysis.py` (skär resultatet per startår, alfa mot likaviktat
och mot OMXS30).

**Svaret (Large/Mid):** det tidigare firade "+3.1 % mot OMXS30" var en
**artefakt av kontaminerad uppvärmningsperiod (2010-2015)**. På rent OOS (2016+)
**förlorar strategin mot OMXS30** — alfa ca **−7 % till −17 %**, och försämras
mot nutid.

**Konsekvens:** vår pris-only-edge är till stor del **bortarbitrerad** i den
moderna eran. Alla efterföljande pris-baserade förfiningar (fler features, annan
sizing, riskoverlay) kan göra ritten *jämnare* men **återuppväcker inte alfan**.
Detta motiverade pivoten till **alt-data** (§6) som enda trovärdiga väg till
durabel edge.

⚠️ **Ej testat ännu:** `era_analysis.py small`. Småbolag är den mest intressanta
jaktmarken (sämre algo-täckning → edge överlever längre) MEN också den mest
**survivorship-flattrade** (yfinance saknar döda bolag) → ett positivt utfall
där går inte att lita på; ett negativt vore mycket talande. Öppen punkt.

---

## 4. Pris-only-modellens edge-mått

`capture_analysis.py` mäter kvantil-spread (snitt framåtavkastning hög vs låg
prob_up). Pris-modellen gav **+9.7 pp** capture-spread in-sample — modellen
*rangordnar* rätt. Problemet är inte rangordningen utan att den **inte räcker
för att slå index netto** i den moderna eran (§3). Detta är nyckeln till att
förstå alla revertade feature-experiment: modellen är redan **maxad på prisdata**.

---

## 5. Experimentlogg (hypotes → resultat → beslut)

Kronologiskt. "Holdout"/"capture" = de ärliga måtten. Baslinjen Large/Mid 13v:
**CAGR 14.0 %, Sharpe 1.07, Sortino 1.29, MaxDD −28.2 %, capture +9.7 pp.**

| # | Experiment | Resultat | Beslut |
|---|---|---|---|
| 1 | **Alltid-investerad topp-N** (bugg: gatad på raw_kelly>0 → bara ~24 % investerad) | Rangordna relativt på prob_up bland behöriga, likavikt-fallback | ✅ **Adopterat** |
| 2 | **Tvärsnitts-target** (XS_TARGET) mot absolut ">5 %" | Fixade platt prob_up (0.307 för alla) → äkta dispersion | ✅ **Adopterat** |
| 3 | **Rebalans 1v → 13v** | Skar veckovis churn-kostnad (~8–20 pp/år) | ✅ **Adopterat** |
| 4 | **Horisont 4v → 13v + mom_12_1** | Flyttade från reversal- till momentum-regim; SAAB får nu fulla positioner | ✅ **Adopterat** |
| 5 | **Conviction-blend sizing** | Fixade kollaps till ~5 namn (Kelly→0 under 50 % prob) | ✅ **Adopterat** |
| 6 | **Universumexpansion** (brett Small/Micro/Nano) | Halverade avkastningen; Large/Mid bättre även på 13v | ❌ **Revertat** (service kör Large/Mid) |
| 7 | **v2-features** (mom_vol_scaled, mom_consistency) | Holdout −0.9 %→**−3.5 %**, capture +9.7→**−0.6** (inverterad!) | ❌ **Revertat** |
| 8 | **PEAD-features** (pris-baserade) | Holdout −0.9 %→**−4.4 %**, capture kollapsade till +0.4 | ❌ **Revertat** |
| 9 | **Händelsestyrd rebalansering** (hysteres/SMA-exit) | CAGR 14 %→**1.7 %**, DD **−52 %** (SMA-brott säljer vinnare i rekyler) | ❌ **Revertat** (calendar kvar) |
| 10 | **Sizing-svep** (blend×npos) | 10 namn @ blend 0.5 optimum för large; fler/högre conviction sämre | ✅ Bekräftade default |
| 11 | **Horisont-svep** | 13v optimalt ±någon vecka | ✅ Bekräftade 13v |
| 12 | **Börsdata-fundamenta** | 599 kr/mån äter upp all förbättrad vinst vid användarens kapital | ❌ **Avvisat (ekonomi)** |
| 13 | **Era-analys** (algo-eran) | Alfa vs OMXS30 −7 %→−17 %, edge borta i modern era (§3) | 🔑 **Omdirigerade strategin** |
| 14 | **Inverse-vol sizing** | Slog conviction på hela rutnätet: CAGR 14.0→**14.3**, Sharpe 1.07→**1.10**, alfa −1.7→**−1.4**, holdout 0.0→**+0.7** | ✅ **Adopterat** |
| 15 | **Target-vol-overlay @10 %** | Sharpe 1.07→**1.16**, Sortino 1.29→**1.60**, MaxDD −28.2→**−20.6 %**, holdout 0.0→**+0.7** (kostar CAGR 14.0→13.4) | ✅ **Adopterat** |
| 16 | **Extern granskning** (HQM/DMN-rapport) | Mest redan gjort, redan testat-och-förkastat, eller horisont-fel för long-only/kvartal; 2 punkter värda test → #14, #15 | Delvis adopterat |
| 17 | **Momentum-kvalitetsgrind** (håll bara namn med abs. 12-1 > tröskel) | STOR: robust platå, topp >10% (CAGR 12.4→**14.3**, Sharpe 1.12→**1.25**, alfa −3.3→**−1.4**, MaxDD −19.9→**−17.6**, holdout +1.3→**+4.4**). SMÅ: helperiod bättre men **holdout SÄMRE** (−2.3→−3.8). | ✅ **Adopterat per-segment** (stor: på >10%, små: av) |
| 18 | **MFN-sentiment (alt-data, A-spåret)** – LLM-poängsatt PM-ton (Haiku), 5 000-sample, OOS 2016+ | **INGEN edge.** Event pos−neg −0.6pp, väsentliga −1.5, **rapporter −0.3**, guidance −0.6, **VD-ton i rapporter +0.1**, tvärsnitt −0.8. Horisont-svep 1/2/4/8/13/26v: −0.4/−0.4/−0.3/−0.2/−0.6/+0.7 (26v = brus). Allt driver +3-4% på bull-basränta; tonen separerar inte. | ❌ **Förkastat** (validate-first, ~35 kr) |
| 20 | **Nattträningens tillförlitlighet** (2026-07-22, samma kväll som #19 – flera problemspår) – nattkörningen misslyckades tyst flera kvällar i rad (`run_watched.sh`:s minnesvakt avbröt, "-" framför `ExecStart` dolde felet för systemd) | Root causes hittade och fixade: (1) `Environment=PATH=/opt/momentum/venv/bin` (utan `/usr/bin:/bin`) gjorde att `run_watched.sh` inte gick att köra alls (`env: 'bash': No such file or directory`) - upptäckt vid manuell körning, `results/stats.json` låg kvar på FÖREGÅENDE dag trots att timern kört. (2) Även efter PATH-fixen byggde `main.py` om HELA feature-matrisen (2010→idag, alla bolag) tre gånger per segment - en gång i varje av de tre subprocesserna (train-lgbm/train-lstm/predict, körs i separata processer för att undvika en OpenMP/PyTorch-trådpool-SIGILL vid återanvändning, bekräftat på Pi 4B) - trots att `build_features()` är en REN funktion av en tickers prisserie. (3) Även med features cachade kunde `MomentumLGBM.fit_walk_forward()` (31-38 splits, oberoende modeller per split) fortfarande avbrytas MITT I - hela walk-forward-träningen fick börja om från split 1 varje gång, upprepade gånger samma kväll. | ✅ **Adopterat**: PATH-fix i `momentum-train.service`; persistent per-ticker features-cache i `feature_engineering.py` (`cache/features_by_ticker/`, nyckel = hash(prisdata)+hash(kod+config), verifierad bit-för-bit identisk output); inom-körning-cache i `main.py` mellan de tre subprocesserna (44min→20min CPU-tid samma körning); walk-forward-checkpoint i `lgbm_model.py` (`_lgbm_walkforward_checkpoint.joblib`, sparas EFTER varje split, atomär temp-fil+`os.replace`, samma hash-baserade invalidering) - verifierat empiriskt: en simulerad krasch efter split 10/38 följt av återupptagning gav SAMMA 38 modeller och IDENTISKA split-datum som en ostörd körning; `momentum-train-verify.timer` (02:50 dagligen) verifierar+kör om automatiskt om ett segment ändå saknar färska resultat |
| 19 | **Hold-forever-utvärdering + härdighets-fundamenta** (`tune_hold_forever.py`, `tune_hold_forever_fundamentals.py`) – håller köpsignalerna som LÅNGA innehav (portföljdisciplinen är köp-och-behåll, backtesten mäter kvartalsrotation)? | Momentum-edgen är en **entry-edge, inte ägar-edge**: median-excess +1.4% @13v → **−24% @156v**, win 54%→37% (2650 inträden 2010–). Medlen bärs av få extremvinnare (156v-medel +1239% vid 37% win). MEN topp-tercil fundamenta-komposit vid köpet (ROE+tillväxt+låg skuld, ≥2/3, point-in-time 2019+) var **enda gruppen som höll**: 104v +3.1%/51% win, 156v −5.3%/47% (vs −18 till −28%/28–35% för resten), och fångade 156v-**dubblare 2,4×** oftare (21% vs ~8%). Skyddar INTE vänstersvansen (topp-tercilen hade lika många halverare, 11%) – nedsidan förblir säljvaktens jobb. Förbehåll: ett regimfönster (2019–23), survivorship, grov point-in-time. Rapportreaktions-sidospåret (`tune_report_dip_reversal.py`, "köp överdrivna rapportdippar"): ingen studs-edge, varken 26v eller 156v – kraftigaste dropparna är oftast äkta varningar, milda dippar studsar. | ✅ **Adopterat**: `PORTFOLIO_HOLD_FUND_BONUS` (±0.08) i köp-vaktens rank för balanced/buffett (av för momentum-profilen); dipp-köp förkastat |
| 21 | **Kärn-insättning tajmad mot dipp** (`backtest_core_dip_timing.py`) – ska den MÅNATLIGA kärninsättningen (10 000 kr, EUNL.DE) vänta med att köpa tills priset fallit X% från insättningsdagens (löne­dagens, ~25:e) pris, i stället för att köpas direkt – ouppfyllt köp jämkas in senast nästa insättningsdag? Daglig upplösning (2010–2026, 198 cykler) krävdes – veckobars döljer en 1–2%-dipp helt. | **Ingen edge, marginellt sämre.** NAV-CAGR 12.4% (schemalagt, dagens beteende) vs 12.2/11.9/11.9/12.0% för −1/−2/−3/−5%-trösklar; slutvärde/insatt +215.9% vs +214.4/213.8/213.2/213.2%. Andelen cykler som faktiskt träffade tröskeln (i stället för att tvångsköpas vid deadline) sjönk 56%→13% när tröskeln höjdes 1%→5% – i en stigande marknad hinner de flesta cyklerna aldrig dippa, och tvångsköpet "en månad senare" landar då oftast på ett HÖGRE pris än om man bara köpt direkt, vilket äter upp vinsten från de gånger dippen väl kom. Diagnostik (separat, ingen strategi byggd på den): svagt positiv "payday-effekt" dag +1/+2 efter insättningsdagen (+0.14pp vs snittets +0.05pp) men **inte statistiskt signifikant** (t-test p≈0.15, n=198) – ingen grund för att tro att man missar ett stort flödesdrivet uppsving genom att vänta. (Utvecklingsanteckning: första körningen visade orimligt NAV-CAGR 47% pga en bokföringsbugg – en insättningsdag är både slutdatum för föregående cykel OCH startdatum för nästa, och en dag→cykel-uppslagning byggd cykel-för-cykel lät den senare tyst skriva över den förras post, så föregående cykels tvångsköp-deadline aldrig utvärderades och `value_after` återanvände ett pre-insättning-värde trots att `pending`-saldot redan runnit på – fixad genom en enda sekventiell dagslogg utan förbyggd uppslagning.) | ❌ **Förkastat** (samma mönster som #19:s rapportdipp-sidospår – ingen tajmnings-edge) |
| 22 | **Krisdjup + björnpaus för kärnan** (`backtest_core_crisis_buying.py`, uppföljning på #21) – tre delfrågor: (a) vilken NEDGÅNGSNIVÅ (5–50% från toppen) ger bäst framåtavkastning, testat på lång historik (S&P 500 sedan 1927, MSCI World TR sedan 1972, EUNL.DE sedan 2010) – inte bara #21:s 16 år; (b) generaliserar mönstret över FLERA breda index, inte bara den ägda ETF:en; (c) är det bättre att PAUSA nya köp helt under en klassificerad björnregim (kontant, släpp in vid vändning – aldrig testat mot en "köp alltid"-baslinje, bara mot en invers-ETF-hedge i `backtest_bear_hedge.py`). | **(a+b) Inget robust mönster.** På de LÅNGA, breda indexen är sambandet mellan djup och framåtavkastning INTE monotont: S&P 500 1-årsmedian +19,8% vid −20% men bara +12,8% vid −30% och +8,8% vid −50% (n=2, otillförlitligt) – 3–5-årshorisonterna lika hackiga, ofta under den obetingade baslinjen (t.ex. −30% på World TR: 3-årsmedian +6,8% mot baslinjens +23,7%). Antal händelser rasar snabbt vid djupare trösklar (12→7→5→2 på S&P 500 för 20→30→40→50%) – för få för att lita på i endera riktningen. EUNL.DE (kort historik, 2010–2026, mestadels en enda lång tjurmarknad + V-formad covid-återhämtning) visar DÄREMOT ett rent monotont "djupare=bättre"-mönster (5%→+10,5%, 20%→+32,3% 1-årsmedian) – men det förklaras bäst av att fönstret bara täcker EN gynnsam regim, inte en generell lag; de långa seriernas brus talar emot att dra den slutsatsen brett. Alltså: **påståendet "måste vara klart bättre att köpa tungt vid −20%" håller INTE upp** över 50–100 års historia, även om det ser ut att stämma i just den senaste tjurmarknaden. (c) **Björnpaus ≈ ingen skillnad.** NAV-CAGR 11,3% (pausa i björn, kontant till vändning) vs 11,4% (köp alltid) på PORTFOLIO_CORE_ETF, 2011–2026 (14,8 år, 35 björn-månader av 178) – slutvärde 4 677 187 vs 4 695 918 (nästan identiskt). | ❌ **Förkastat** (inget krisdjup-tröskelvärde eller björnpaus-regel adopterad för kärnan – för brusigt/obevisat över lång historik) |
| 23 | **Insynsköp-gap mot FI:s fulla register** (`tune_insider_gap_fi.py`, uppföljning på #12-eran-syskonet `tune_insider_gap.py` som landade OAVGJORT pga bara 30 PDMR-poster i MFN-cachen) – samma hypotes (nettoinsynsköp UTAN prisreaktion → fördröjd uppvärdering), men mot Finansinspektionens fulla öppna insynsregister (`altdata/fi_insynsregistret.py`, ny skrapare mot marknadssok.fi.se – ett gammalt pip-paket för samma register pekade mot en nedlagd domän). Kördes i TVÅ pass: (1) 53/181 large-cap-bolag gav träffar (bolagsnamn matchade FI:s exakta juridiska form rakt av), n=1184; (2) efter att ha upptäckt och fixat en namnmatchningsbugg (FI kräver kärnnamnet utan "AB"/"(publ)"-bolagsform, delsträngsmatchning) steg täckningen till 72/181 bolag, n=2206. | **Pass 1 (ofullständigt urval) såg ut som en STARK, tydlig edge**: gap_score IC 0,18–0,27 på alla fyra celler (8v/26v × hela/holdout), slog buy_only_score (rått nettoköp) överallt, holdout STARKARE än helperiod – misstänkt bra, flaggat för omkörning innan det litades på. **Pass 2 (mer komplett urval) visar att effekten var kraftigt uppblåst av det ofullständiga, icke-representativa urvalet**: IC krympte till 0,04–0,19, och 8v-holdout **klarar inte längre skriptets egen tröskel** – buy_only_score (IC 0,192) slår faktiskt gap_score (IC 0,173) där, tvärtom mot "reaktionsfiltret tillför nåt utöver rått insynsköp"-hypotesen. 26v-horisonten håller fortfarande (gap_score IC 0,163 mot buy_only 0,101, positiv Q5−Q1 på båda helperiod/holdout) men klart svagare än pass 1:s siffror antydde. Lärdom: ett urval som "råkar matcha" kan vara systematiskt snedvridet, inte bara mindre – dubbelkolla ALLTID en oväntat stark signal med bättre täckning innan den litas på. | 🟡 **Delvis/inte adopterat** (svagare stöd på 26v, inget stöd på 8v – mer övertygande än #12-syskonets OAVGJORT, men inte starkt nog för att bygga in som köp-vakts-feature ännu; skulle behöva fler bolag/längre historik för en säkrare dom) |
| 24 | **Svenskt mikrobolag billigt vs global jämförelsekorg** (`tune_global_relative_value.py`) – Sivers Semiconductors-fallet (n=1: P/S 2,9x vs globala foton-/RF-korgen 5,8–896x precis FÖRE en 600%+-uppgång) väckte frågan: generaliserar "billigast i sin globala jämförelsegrupp" som köpsignal, särskilt i HETA sektorer (korgens egen värdering historiskt hög)? Systematiskt svep: hela svenska IT+Health Care small/micro/nano-universumet (288 bolag) mot två handplockade globala korgar (halvledare/foton, medtech), årliga P/S-ögonblicksbilder 2022–2025, händelser taggade sval/normal/het sektor via korgens egen P/S-percentil. | **Replikerar INTE.** 427 "billig vs global korg"-händelser, ALLA negativ median-excess på alla horisonter – och "het sektor" (244 händelser, där Sivers-tesen förutspådde STARKAST edge) gav de SÄMSTA resultaten av alla tre grupper (13v −8,3%/36% win, sämre än sval/normal). Metodologisk brasklapp: IT-korgens egen värdering steg MONOTONT varje år (7,7x→19,6x 2022–2025) - "het sektor" blandas därför ihop med "hände 2025" (för nytt för mogen framåtavkastning), samma dödläge som #-kvalitetsbetygstestet. Sivers-fyndet ser ut som ett äkta men ISOLERAT n=1-exempel som inte generaliserar till en regel. | ❌ **Förkastat** (bekräftar användarens egen försiktighet - "hur många ANDRA som såg likadant ut UTAN att rallya") |
| 25 | **Otto-metodens (OT Analytics) värderingsband som regel** (`tune_otto_valuation_band.py`) – ett bolags EGEN historiska Börsvärde/EBIT(DA)-multipel (lägsta↔högsta) som köp-/sälj-gränser, i stället för en bransch-multipel eller extern jämförelsekorg. Två regler testade separat på samma 288-bolagsuniversum: (A) köp vid egen-historisk-LÄGSTA multipel, (B) framåtavkastning EFTER egen-historisk-HÖGSTA multipel (stödjer "ta hem vinsten vid riktkurs"?). Bakåtblickande TTM-approximation (Ottos EGEN metod använder framåtblickande guidade/estimerade EBIT(DA), ingen sådan källa finns systematiskt för hela universumet). | **Asymmetriskt resultat - sälj-sidan håller, köp-sidan inte.** (A) Köp vid egen-billigast: NEGATIV på alla horisonter (13v −5,7%/40% win, 26v −10,5%/38%) - att ett bolag är "billigast någonsin" mot sin egen historik är oftare en varningssignal (resultatet har kollapsat av en riktig anledning) än ett missat läge, i den här mikrobolagspopulationen. (B) Efter egen-dyrast: kort momentum-eko (13v +2,4%/51% win) men vänder tydligt negativt från 26v (−3,8%→−25,0% vid 52v) - stödjer faktiskt "ta hem vinsten nära riktkurs". | 🟡 **Delvis adopterat-värdigt**: sälj-disciplinen (B) har verkligt stöd och är värd att bygga in i säljvakten; köp-disciplinen (A) förkastas |
| 26 | **"Baka ihop kaksmulorna" – IntegratedBacktester** (`backtest/integrated_backtest.py`, `tune_integrated_backtest.py`) – hittills har bara kärnmodellens rena pris→signal-steg körts genom en riktig backtest; härdighets-bonusen, insynsköp-bonusen och säljvaktens eskaleringsstege (inkl. modellens riktkurs, #25) har bara körts LIVE mot senaste ögonblicksbild, aldrig walk-forward. Byggde en `IntegratedBacktester(MomentumBacktester)` som rekonstruerar de tre lagren POINT-IN-TIME (merge_asof mot fundamenta-CSV:erna för härdighet, cache/otto_band för riktkursen, FI:s fulla insynsregister för insynsklustring – alla utan lookahead, se filens docstring för vad som INTE kunde göras point-in-time: offentlig riktkurs, LLM-kvalitetsbetyg, MFN-textflaggor) och lägger till en TVINGAD säljvakt (nivå 2 = 50% delförsäljning, nivå 3 = full exit vid SMA20-brott). Körd mot Large/Mid-segmentets riktiga signals.csv (200 bolag, 2010–2026, 813 veckor). Sanity-check (alla tre lager AV) gav bit-för-bit identiskt resultat mot en oförändrad `MomentumBacktester` – bekräftar att integrationen inte läcker lookahead eller ändrar basbeteendet av misstag. | **Kaksmulorna löser INTE "slår inte index"-problemet, men de är inte meningslösa heller.** HOLDOUT (frusen, 2024-07-29→2026-07-20, 103v, OMXS30 bred samma fönster **+31,5%/CAGR +14,8%**): baseline (kärnmodellen ensam) CAGR **−3,2%** (Sharpe −0,25, MaxDD −17,4%) → integrerad CAGR **+0,1%** (Sharpe +0,05, MaxDD **−9,8%**, nästan halverad). Förlusten vänds alltså till ett nollresultat och drawdownen krymper kraftigt – men gapet mot index (+14,8% CAGR samma period) är fortfarande enormt, ~15 procentenheter/år. HELPERIOD (2010–2026, 15,6 år, index CAGR +9,5%): baseline CAGR **15,1%** (slår index med +5,6pp/år) → integrerad CAGR **9,3%** (i praktiken index-paritet, −5,8pp sämre än kärnmodellen ensam) – lagren äter alltså upp en del av kärnmodellens LÅNGSIKTIGA edge i utbyte mot bättre riskkontroll i just den här holdouten. Ärlig slutsats: "modellen slår inte index" står kvar även efter ihopbakningen – den samlade produkten är en FÖRSVARSMEKANISM (mindre förlust, mindre drawdown när kärnmodellen har det tufft), inte en ny avkastningskälla. | 🟡 **Delvis adopterat**: `IntegratedBacktester` bevarad som verktyg för framtida riskanalys/kalibrering av säljvaktens trösklar – men INTE en ersättning för kärnmodellens signal i produktion, och påståendet "modellen slår inte index" kvarstår obesvarat/obekräftat trots ihopbakningen |
| 27 | **Komponent-för-komponent-genomlysning av #26:s gap mot index** – #26:s holdout-gap (~15pp/år, ~30pp kumulativt över 2 år) kändes orimligt stort vid granskning; i stället för att acceptera totalsiffran testades varje riskmekanism/signallager ISOLERAT, ett i taget, på båda segmenten (large/small), för att se vilka som faktiskt håller vad de lovar. Fyra delfrågor: (a) är gapet ens mätt rätt och på rätt scope; (b) håller de 5 portföljnivå-riskmekanismerna (regimfilter, drawdown-guard, vol-target, korrelationsfilter, sektorspärr) i `backtester.py` vad de lovar, isolerat; (c) samma sak för `IntegratedBacktester`:s tre signallager (härdighet/insynsköp/säljvakt); (d) VARFÖR bröt modellens egen rangordningsskicklighet i holdout – ren IC-mätning (Spearman pred_return vs realiserad avkastning) plus `lgbm.print_fold_diagnostics()`/`print_feature_importance_by_period()` (mergade i Stage 0 samma dag, aldrig körda förrän nu). | **(a) Gapet var korrekt mätt, men fel scope.** XACT-SVERIGE.ST självt +30,5% i exakt samma fönster mot portföljvärde −3,6% – ingen mätbugg. Men #26 testade bara large-cap-halvan av Sverige-satelliten (15% av `PORTFOLIO_TARGET`); breda kärnan (65%) ska per definition inte slå index, och tema-satelliten (20%) är redan dömd i #8 ("ACWI slog rotationens alla varianter"). **(b) Riskmekanismerna är segmentspecifikt olika värda – ingen universell regel höll.** Regimfiltret var rent SKADLIGT för large (avstängt: holdout-CAGR −1,8%→**+6,3%**, helperiod 15,6%→**19,5%**, ingen sämre drawdown) men svagt skyddande för small. Drawdown-guarden var overksam för large (triggades aldrig i mätperioden) men KRITISK för small (avstängd: helperiod-MaxDD −35,5%→**−48,3%**) – rotorsak: portföljens all-time-peak var 2021-08-02, guarden triggades av 2022 års räntehöjningskrasch och har ALDRIG släppt sen dess (fastlåst på 30%-golvet i fyra år, genom HELA holdout) – inte en bugg: även indexet (XACT Småbolag) stod fortfarande −15,2% under sin 2021-topp fyra år senare. Vol-target skyddade verkligt för large (avstängd: helperiod-MaxDD −19,5%→−29,6% för bara +1,1pp extra CAGR), overksam för small. Explicit "alltid 100% investerad"-test (regim+guard båda av): höll för large (bättre på alla mått) men var TYDLIGT SÄMRE för small (holdout −2,8%→**−10,5%**, helperiod-MaxDD −35,5%→**−53,0%**) – motbevisar en generell "alltid investerad är bäst"-regel. **(c) Härdighet/insynsköp är gratis, den TVINGADE säljvakten är hela notan.** Isolerad ablation: härdighetsbonus och insynsköpsbonus kostar ±0,3pp helperiod-CAGR i båda segmenten (ibland bättre MaxDD gratis). Säljvaktens tvingade nivå-2-delförsäljning ENSAM förklarar nästan hela #26:s uppmätta kostnad: −5,1pp/år (large) resp. −4,8pp/år (small) för en jämförelsevis blygsam drawdown-vinst – den klipper exakt den fetsvansade uppgången momentum-edgen bygger på. Bästa avvägningen (härdighet+insynsköp PÅ, säljvakt EJ tvingad – matchar redan hur appen fungerar, nivå 2 är rådgivande där) bevarar nästan hela kärnmodellens långsiktiga CAGR (large 15,3% mot baseline 15,6%) och ger ändå en liten verklig holdout-förbättring. **(d) Root cause: en genuin regimbrytning 2022 för large, kroniskt svagare/brusigare edge (aldrig en ren brytpunkt) för small.** IC (Spearman pred_return vs realiserad FORWARD_WEEKS-avkastning): båda segmenten har statistiskt robust genuin rangordningsskicklighet över hela historien (large IC=0,056 t=10,1; small IC=0,070 t=15,3 – small till och med HÖGRE), men i holdout har large:s skicklighet VÄNTS (IC=−0,056, t=−5,14, bara 33% av veckorna rätt håll) medan small:s bara försvagats mot brus (t=−1,38, ej signifikant). Fold-diagnostiken visar varför: large hade konsekvent positiv per-fold-avkastning 2016–2022 (inkl. en extrem covid-återhämtnings-anomali 2020–2021, +168%/+104% på två splits) som VÄNDER NEGATIV exakt vid räntehöjningscykelns start hösten 2022 (−16,4%/−24,1%, Sharpe −0,76/−0,88) och förblir svag/blandad sen dess – sammanfallande med att klassiska momentum-features (`ema_cross_21_55`, `rs_26w`) tappar ur topp-10 feature-importance till förmån för fundamenta (`rev_growth_yoy`). Small visar INGEN sådan ren brytpunkt: 18 av 31 splits saknar helt köpbara kandidater, och bland de som har data är tecknet blandat redan från 2017 (en tidig −26,8%/Sharpe −5,96-avvikelse) – konsekvent svagare/brusigare urval genom hela historien, inte en enskild brytning. | 🟡 **Delvis adopterat/diagnostiskt**: inga produktionsflaggor ändrade ännu (allt kört mot engångsskript, `config.py` orört) – men tre konkreta, evidensbaserade uppföljningar identifierade: (1) regimfiltret bör omprövas SEGMENTSPECIFIKT (av för large, kvar för small) i stället för en global på/av-inställning; (2) `IntegratedBacktester`s säljvakt bör som DEFAULT vara rådgivande (ej tvingad) om verktyget någonsin används normativt – matchar redan appens skarpa beteende; (3) large-modellens holdout-svaghet är nu förklarad (2022 års regimbrytning, momentum→fundamenta-feature-drift) snarare än en olöst gåta – öppnar för en riktad uppföljning (t.ex. dynamisk feature-viktning eller regimmedveten omkalibrering) i stället för blint vidhållande av en modell byggd för en regim som inte längre gäller |
| 28 | **Regimklassificerarens SMA-fönster – laggtest** (uppföljning på #27b) – large har sin EGEN regimklassificerare (likaviktad proxy av segmentets 200 bolag, inte ett delat/generellt index – verifierat), och den läste rätt håll (79% av holdout-veckorna bull, matchar segmentets egna +16,5% breddrally). Frågan var därför inte RIKTNING utan TIMING: är `REGIME_SMA_WEEKS=26` för trögt för att hänga med när en dipp vänder? Svep 8/13/17/26/39/52 veckor, large-segmentet, holdout+helperiod. | **Kortare fönster vinner på BÅDA axlar samtidigt – inte en avvägning.** 13v: holdout-CAGR −1,8%→**+0,4%**, helperiod-CAGR i praktiken oförändrad (15,6%→15,3%), men helperiod-MaxDD förbättras kraftigt **−19,5%→−13,9%** (bättre än att stänga av filtret helt, som gav −20,4%). Mönstret höll konsekvent över hela svepet (8v/13v/17v gav alla klart bättre MaxDD än 26v/39v/52v), inte bara vid ett enskilt bästa-värde – minskar (men eliminerar inte) risken för att bara ha hittat en parameter som råkar passa denna ENA holdout-period. Adopterat: `REGIME_SMA_WEEKS: 26→13`. Facit mot index EFTER ändringen: holdout fortfarande långt efter (modellen +0,8% kumulativt mot index +30,5%, gap ~30pp – ändringen räddar INTE holdout-perioden), men helperiod-edgen mot index bevarad (+5,5pp/år, i praktiken oförändrat från +5,6pp/år) med klart mindre värsta-fall-dropp. | ✅ **Adopterat**: `config.py` `REGIME_SMA_WEEKS=13` (var 26) – strikt bättre än status quo på risk, i praktiken oförändrat på avkastning; löser inte "slår inte index i holdout" men är en ren förbättring av riskmekanismen som redan fanns |

**Etablerade sanningar ur loggen:**
1. Modellen är **maxad på prisdata** – feature-additioner överanpassar (#7, #8).
2. Risk-hygien (#14, #15, #17) gör kurvan snyggare men **skapar ingen ny alfa** –
   kvar i negativt territorium mot OMXS30.
3. **Alt-data (regulatorisk PM-text) bär ingen OOS-drift** (#18) – inte i order,
   inte i rapporter, inte i VD-ord, inte på någon horisont. Både pris- OCH
   text-sentiment-vägarna är därmed uttömda. Marknaden prisar uppenbarligen in
   även PM-*tonen* effektivt på vår horisont, inte bara den snabba reaktionen.
4. **Att baka ihop ALLA validerade delsignaler till en produkt löser inte
   "slår inte index"** (#26) – den samlade produkten (kärna + härdighet +
   insynsköp + säljvakt) krymper förlusten och drawdownen i holdout, men
   gapet mot index (~15pp/år i holdout-fönstret) består, och lagren kostar
   dessutom en del av kärnmodellens egen långsiktiga edge (helperiod CAGR
   15,1%→9,3%). De många "kaksmulorna" är var för sig äkta, små
   riskförbättringar – inte, tillsammans, en ny avkastningskälla.
5. **Riskmekanismer ska bedömas isolerat och segmentspecifikt, aldrig som en
   universell "alltid på"/"alltid av"-regel** (#27) – regimfiltret var
   direkt skadligt för large men svagt skyddande för small; drawdown-
   guarden var overksam för large men höll small från en −53% (i stället
   för −35,5%) MaxDD under en verklig, ännu inte återhämtad krasch sedan
   2021. Large-modellens holdout-svaghet är en genuin regimbrytning hösten
   2022 (räntehöjningscykeln, momentum-features tappar feature-importance
   till förmån för fundamenta) – inte brus och inte en bugg. Small har
   aldrig haft en lika stabil edge (18/31 walk-forward-splits saknar
   köpbara kandidater helt, brusigt tecken redan 2017) – ett annat, mer
   grundläggande problem än large.

---

## 6. Alt-data-spåret (A-spåret) – MFN-sentiment

**Hypotes:** durabel edge kräver något algon inte trivialt arbitrerar bort:
**tonen i bolagens egna regulatoriska pressmeddelanden** (PEAD-anda – marknaden
under-reagerar på nyhetston, driften håller i sig veckor framåt).

**Varför MFN.se:** Modular Finance distribuerar nordiska regulatoriska PM och har
ett **arkiv med publiceringstidsstämpel** → *point-in-time text utan look-ahead*,
vilket är förutsättningen för en ärlig backtest av en textsignal.

**Byggt (i `momentum_ml/altdata/`, validate-first):**
- `mfn_fetch.py` – hämtar + cachar PM point-in-time. `probe`-läge dumpar MFN:s
  råsvar så parsern låses mot **faktisk** form (endpointen gissas inte blint).
- `sentiment.py` – poängsätter varje PM (sentiment −2..+2, materialitet 0..3,
  kategori) med **Claude Haiku 4.5** via **Batch-API (−50 %)**, cache per PM-id,
  nyckel ur `ANTHROPIC_API_KEY` (aldrig i repot; `cache/` är gitignorad).
- `backtest_sentiment.py` – OOS (2016+) event-studie + tvärsnitts-capture-spread,
  speglar `capture_analysis.py`.
- `README.md` – körordning på Pi:n, kostnad, beslutsregel.

**Ekonomi:** Haiku ~**$0.004/PM**. Live-drift ~ören/vecka. Historisk backtest
~$20 (smal) till ~$100 (brett), batchat. **API-nyckeln är gratis** –
pay-as-you-go, ingen prenumeration, spend limit kan sättas. Engångskostnad på en
hundralapp mot Börsdatas 599 kr/mån *för evigt* – det är hela poängen.

**Beslutsregel (samma som fällde #7/#8):** är både event- och tvärsnitts-spreaden
tydligt positiva (störst för materiella PM) → äkta edge värd att bygga in som
feature. Annars: pris-only har redan allt, spara pengarna.

**Status:** koden ligger redo. Kräver innan körning på Pi:n: (1) en
Anthropic-nyckel i `~/.momentum.env`, (2) bekräftelse att Pi:n når mfn.se
(`mfn_fetch.py probe "Saab"` först, granska `_probe_*.txt`).

---

## 7. Drift & ops (Pi) – fallgropar att känna till

- **Två kataloger:** `/opt/momentum/src` (git-klon, pullas av timern) och
  `/opt/momentum/momentum_ml` (deploy-kopia, dit `sync.sh` rsync:ar; **härifrån
  körs scripts och API**). `cache/`, `results/`, `deploy/` exkluderas ur rsync.
- **sync.sh är nu idempotent** (2026-06-28): rsync:en körs *alltid* och beslut om
  API-omstart fattas på vad rsync faktiskt överförde (`--itemize-changes`), inte
  på git-HEAD. Tidigare gatades rsync på "before != after" → **skip-fälla**: låg
  src redan på rätt commit men deploy-kopian inte → deploy uppdaterades aldrig
  (en tune-körning kördes med gammal `SIZING_MODE` pga detta).
- **Servicen kör `sync.sh` från `src`**, inte deploy-kopian (deploy/ är
  självexkluderad → bootstrap-fälla annars). Ändringar i `deploy/` (systemd-units,
  sync.sh) kräver **engångs manuell kopiering** + `daemon-reload`.
- **requirements.txt-ändring** auto-installeras INTE – sync varnar, pip körs
  manuellt.
- **Verifiera alltid deploy-kopian** innan du litar på en körning:
  `grep -E "^SIZING_MODE|^VOL_TARGET" /opt/momentum/momentum_ml/config.py`.
- **Montrose-mäklarorder = riktiga pengar** – integrationen (2026-07-16) är
  medvetet begränsad: innehavs-LÄSNING (`sync_montrose_holdings.py` → samma
  portföljfil som appen) + FÖRIFYLLDA köpbiljetter (`montrose_ticket.py` →
  "Skapa ticket"-knappen i Nästa köp). En biljett lägger ALDRIG en order –
  användaren bekräftar själv i Montrose-appen. Bara köp (side=Buy), alltid
  ISK-kontot, aldrig kreditkontot. Teknik: headless `claude -p` på Pi:n
  (Claude-prenumerationen, ingen API-nyckel), Montrose-MCP:n LOKALT
  registrerad (`claude mcp add --transport http montrose
  https://mcp.montrose.io` + `claude mcp login montrose`) – den kontobundna
  claude.ai-connectorn syns inte i headless-läge. `--allowedTools` låser
  varje anrop till exakt search_instruments + create_trade_ticket.
  Användarens riktiga portfölj (~170 k kr) är känslig finansiell data.
- **Två buggar fixade 2026-07-23** (upptäckta via en användarfråga om en
  orimlig −8,1% på Hem:s pappersportfölj-widget):
  1. **Veckodags-ankring**: Yahoo kan leverera en enskild tickers `1wk`-staplar
     på en ANNAN veckodag än resten av universumet (INCOAX.ST konsekvent
     tisdags-ankrad sedan 2019, allt annat måndags-ankrat). Utan normalisering
     blir varje sådan tisdag en HELT EGEN rad i `signals.index`/backtestens
     datumindex - dubblerade "veckor" som gör `_compute_stats`s CAGR/Sharpe
     (hårdkodat `ann=52, weeks=len(rets)`) fel, OCH kan trigga en spurios
     ombalansering i pappershandeln på ett datum där nästan ingen ticker
     faktiskt har färsk data. Fixat i `data/data_loader.py::_clean`
     (`resample("W-MON").last()`) - samma mönster som redan fanns i
     `backtest/accumulation.py::normalize_weekly_panel()` för ETT fristående
     forskningsskript, nu i huvudpipelinen så ALLA konsumenter skyddas.
  2. **PaperTrader-segmentläcka**: `PaperTrader()`s `results_dir`-default
     (`config.RESULTS_DIR`) fångas vid MODUL-IMPORT (main.py:s importrad),
     INNAN segmentväxlingen (`config.RESULTS_DIR = seg["results_dir"]`) hinner
     köra i `main()`. Utan explicit `results_dir` skrev båda segmenten hela
     tiden till SAMMA delade `results/paper_state.json`/`paper_ledger.csv` -
     `results/small/` fick aldrig sin egen pappersportfölj, bara tyst
     blandad/överskriven beroende på körordning. Fixat genom
     `PaperTrader(results_dir=config.RESULTS_DIR)` på anropsplatsen (där
     värdet redan är rätt segment-satt). Den korrupta delade liggaren gick
     inte att reda ut i efterhand - arkiverad, båda segmenten börjar om rent.
     **Läxa**: ett default-argument som pekar på ett modul-nivå-värde som
     muteras vid körning är en klassisk Python-fälla - fångas vid definition,
     inte vid anrop. Genomsökt HELA kodbasen efter samma mönster (2026-07-23):
     `models/ensemble.py::_topn_invested_weights` har en likadan riskfylld
     signatur (`n: int = config.MAX_POSITIONS`, som också muteras per segment
     i `main.py`) men triggas ALDRIG i praktiken - båda anropsställena skickar
     `n=` explicit. Inga andra levande instanser hittades.

---

## 8. Öppna frågor & nästa steg

1. **`era_analysis.py small`** – ✅ KÖRT: småbolag förlorar mot Svenska Småbolag-
   index i ren OOS (−6.8% 2016+, −9.3% 2023+), trots survivorship-uppblåst data.
   Ingen edge i småbolag heller.
2. **MFN-validering (A-spåret)** – ✅ KÖRT & FÖRKASTAT (#18): ingen OOS-drift i
   PM-/rapport-/VD-ton på någon horisont. Alt-data-text-spåret är dött.
3. **Småbolag genom #14/#15** – `tune_sizing.py small` + `tune_voltarget.py small`
   (risk-hygienen är bara validerad på large; configvärdena är globala).
4. **Survivorship-fri prisdata** – kvarstår som blockare för trovärdiga
   småbolagsresultat (Norgate/Polygon/EODHD). MFN löser bara *text*-sidans
   look-ahead, inte pris-sidans survivorship.
5. **Ablation nedåt (gyllene medelvägen)** – `tune_ablation.py`. Vi vet att
   *addera* features överanpassar (#7, #8) men har aldrig mätt om en ENKLARE
   modell har lika/bättre edge. Kör `logo` (leave-one-group-out) först, sedan
   ev. `backward` (girig eliminering). Positiv Δcapture vid borttagen grupp =
   gruppen är brus → skär bort. Vinnande minimal uppsättning re-valideras med
   fulla pipelinen på holdouten innan adoption.
6. **Produktpositionering** – landa som ärligt analys-/utbildningsverktyg
   (cap-viktat index = den ärliga, oslagna ribban) vs jaga alt-data-edge. +
   regulatorisk (MiFID) bedömning före publik lansering (se MODELLANALYS.md §6.4).
7. **C-spår: fundamental microcap-screener** (`altdata/quality_screener.py`) –
   AKTIVT. Diskretionär tratt (LLM mot checklistan + nyckeltals-extraktion →
   OT-style värderingsdiagram). Kör: `mfn_fetch.py fetch quality` → `quality_screener.py
   score` → `chart`. Ej backtestbart; urval, inte bevis.
8. **D-spår: sektor-/ETF-trendrotation – BYGGT & DÖMT** (`etf_rotation.py`,
   `tune_etf_rotation.py`, `etf_thesis.py`): dual momentum över 37 ETF:er
   (region/sektor/tema, `data/rotation_universe.csv`) med absolut-filter +
   defensivt ben, 40v-regim på MSCI World, VIX+kredit-stress-overlay,
   korrelationsblockering. Ärliga domen (netto, OOS via tune-svepet): **ACWI
   slog rotationens alla varianter** → rotationen är integrerad ENBART som
   tema-satellit i next_buy (risk-on-gatad, max tema-hinken i PORTFOLIO_TARGET),
   aldrig kärna – appen märker den "Taktiskt – rotationen slår inte index
   netto". `etf_thesis.py` (kausalt idéträd, enda LLM-inslaget) är uttryckligen
   EJ signal. Kör: `python etf_rotation.py signal | backtest | flow`.

---

## 9. Filkarta (var saker bor)

```
momentum_ml/
  config.py                  # ALLA parametrar (med inline-rationale & beslutsdatum)
  data/data_loader.py        # yfinance-hämtning, universum, delisting-/likviditetsfilter
  features/feature_engineering.py  # ~46 features, XS-target, 12-1, float32
  models/
    lgbm_model.py, lstm_model.py
    ensemble.py              # combine + sizing (_size_date: SIZING_MODE conviction/inverse_vol)
  backtest/
    backtester.py            # walk-forward, kostnader, _vol_target_factor, marknadsfilter, DD-guard
    benchmark.py, regime.py, threshold_opt.py, bootstrap.py, drift_monitor.py
  main.py                    # CLI: --segment, träning/prediktion, signals.csv (namn, limit-priser)
  api/main.py                # FastAPI, segment-param, /api/segments, OMXS30-serie
  altdata/                   # A-spåret: MFN-sentiment (fetch/sentiment/backtest + README)
    quality_screener.py      # C-spåret: kvalitativ fundamental sållning (LLM läser rapporter
                             #   mot din checklista + extraherar nyckeltal → värderingsdiagram).
                             #   DISKRETIONÄRT, ej backtestbart.
  # Analysverktyg (efter-bearbetning, ingen omträning):
  baseline_compare.py        # ML vs ren regel-momentum
  capture_analysis.py        # capture-spread / fångar stora rörelser
  tune_sizing.py             # svep CONVICTION_BLEND × MAX_POSITIONS × SIZING_MODE
  tune_voltarget.py          # svep target-vol-overlay (av/10/15/20 %)
  tune_horizon.py            # svep FORWARD_WEEKS
  tune_ablation.py           # ABLATION nedåt: skär feature-grupper, hitta gyllene medelvägen
  era_analysis.py            # alfa per startår vs likavikt & OMXS30 (algo-era-testet)
  deploy/                    # systemd-units + sync.sh (kopieras manuellt)
frontend/                    # PWA (segment-toggle, signaler, backtest, OMXS30-linje)
docs/
  MODELLANALYS.md            # extern kvalitets-/forskningsgranskning (2026-06-26)
  UTVECKLINGSLOGG.md         # detta dokument
```

---

## 10. Den röda tråden (för en agent som tar över)

1. Strategin är tekniskt gedigen och **rangordnar rätt** (capture +9.7 pp).
2. Men i den **moderna algo-eran slår den inte OMXS30** (era-analysen) – pris-only-
   edgen är till stor del bortarbitrerad.
3. Vi har **uttömt prisdata**: feature-additioner överanpassar, sizing/horisont
   är vid optimum, risk-overlays förbättrar bara *risk*, inte alfa.
4. **Alt-data-spåret (MFN-sentiment) är testat och förkastat (#18):** PM-/rapport-/
   VD-ton bär ingen OOS-drift på någon horisont. Både pris och text är därmed
   uttömda som *alfa*-källor.
5. **Slutsats/landning:** Momentum är inte ett index-slående system och ska inte
   marknadsföras så. Det är ett **gediget, transparent analys-/utbildningsverktyg**
   för svenska aktier, med ärlig OMXS30-jämförelse och reell risk-hygien (grind,
   inverse-vol, vol-target). Det är en trovärdig produkt; ett falskt edge-påstående
   vore det inte. (Ev. kvarvarande teoretiska alt-data-trådar – nyhets-/social-buzz,
   insynshandel, fundamenta – är dyrare/brusigare och bör mötas med samma skepsis;
   jaga dem inte utan en billig validate-first-test som #18.)
6. Behåll disciplinen: **bevisa på holdout/OOS, annars reverta.** Det är så vi
   kommit hit utan att lura oss själva – inklusive att säga "nej" till alt-data.
