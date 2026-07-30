# Edge/Risk/Scenario-testkö – ny prioritering 2026-07-30 (användarbeslut)

> **STATUS: AKTIV KÖ, ERSÄTTER TILLFÄLLIGT NATTKÖN.** Användaren beordrade
> 2026-07-30 (kväll/natt) att pausa den pågående autonoma Tier 3/4-nattkörningen
> i `niva3_status_handoff.md` och köra dessa nya idéer i stället. Se
> "PAUS-status" längst ner i den filen för exakt vad som stoppades och var.
>
> Källa för alla poster: en fristående research-genomgång (subagent, ingen
> kod skriven/körd under research-fasen) som läste `niva3_status_handoff.md`,
> `UTVECKLINGSLOGG.md` (#1-119), `FORBATTRINGSKO.md`, `MODELLANALYS.md`,
> `CONDITIONAL_MODEL_AUDIT.md`, samtliga 57 `tune_*.py`-filnamn, samt kod i
> `features/feature_engineering.py`, `models/ensemble.py`, `models/entry_policy.py`,
> `backtest/backtester.py`, `backtest/regime.py`, `backtest/sector_momentum.py`/
> `theme_momentum.py`, `portfolio.py` (säljvakt/refill), `config.py`. Medvetet
> kontrollerat mot LCA-1..35 och alla 57 `tune_*.py`-ämnen för att undvika
> dubbletter – se "Medvetet bortvalda dubbletter" i respektive avsnitt nedan.

**Regler (samma som nattkön):** kör EN i taget, logga resultat i
`docs/UTVECKLINGSLOGG.md` som vanligt (fortsätt numreringen, verifiera alltid
med `grep -oE "^\| [0-9]+ \|" docs/UTVECKLINGSLOGG.md | sort -n | tail -3`
innan nästa post skrivs). Bocka av `[ ]` → `[x]` HÄR i denna fil när en post
är klar, med hänvisning till UTVECKLINGSLOGG-postnumret. Krascher: debugga/
försök igen enligt känt buggmönster (se `niva3_status_handoff.md`); annars
lägg åt sidan och gå vidare.

**Kostnadsklasser** (styr ordningen inom varje prioritetstier – billigast/
säkrast först):
- 🟢 **MÄTNING** – ren analys av redan sparad data (`results/*.csv`, cache),
  ingen ny träning, inget nytt skript med okänd buggrisk. Minuter.
- 🟡 **LÄTT SKRIPT** – nytt litet fristående skript i `tune_*.py`-stil (IC-check,
  räkning), ingen full walk-forward-omträning. ~2-10 min körtid.
- 🟠 **TRÄNING/SVEP** – kräver en eller flera fulla walk-forward-träningar
  eller backtest-körningar. 20-90 min, samma buggrisk-klass som kvällens
  `tune_*.py`-körningar (DROP_FEATURES-ordning, `attach_fundamentals_features`,
  stale cache – se känt buggmönster i handoff-filen INNAN körning).
- 🔴 **STOR ÄNDRING** – kräver ny targetdefinition, ny datakälla, eller
  arkitekturändring. Egen dedikerad session, inte en kvällskörning.

---

## TIER 1 – Högst prioritet (konkret, kodgrundad, hanterbar kostnad)

- [x] **1. [SCN-KÖP-1] `entry_policy.py`s köpregler har ALDRIG körts genom ett
      historiskt backtest** 🟠 – **KLAR, se UTVECKLINGSLOGG #127.**
      `tune_entry_policy_backtest.py` skrivet och kört (small-segmentet,
      enda segmentet där `blocked_overextended` kan ha effekt – för `large`
      visade kodläsningen att `decide_entry()` aldrig sätter `eligible=False`).
      Resultat: regeln triggar råvärdesmässigt ofta (2153 observationer) men
      var bara BINDANDE 4 gånger i hela historiken (resten av kandidaterna
      låg redan utanför topp-20 eller var redan ägda) – backtest-utfallet är
      i praktiken oförändrat (dev bit-identiskt, holdout CAGR +1,30%→+1,40%,
      brusnivå). Oron var obefogad – ingen kodändring motiverad.
- [x] **2. [EDGE-1] `resid_mom`-featurens bugfix (aritmetisk→geometrisk
      kedjning) är inte bekräftat omtränad + aldrig solo-IC-testad** 🟡 –
      **KLAR, se UTVECKLINGSLOGG #121.** `tune_resid_mom_ic.py` skrivet och
      kört (återanvänder `results/abstention_features.pkl`, ingen ny träning).
      Resultat: (a) mtime-kedjan visar att BÅDE `lgbm_model.pkl` och
      `lgbm_model_serving.pkl` tränades EFTER bugfixen – "kräver omträning"-
      varningen är sannolikt redan inaktuell. (b) Solo-IC är STARKT: hela
      perioden IC=+0,105 (t=+17,3), HOLDOUT IC=+0,148 (100% av veckorna
      positivt tecken) – starkast av alla solo-IC-testade features hittills,
      slår #119:s bästa Börsdata-mått. Ingen produktionsändring, men en
      kvarstående öppen fråga om stale feature-cache noterad i #121.
- [x] **3. [EDGE-2] Kvalitet × momentum-interaktion (QMJ-mönster) aldrig
      testad** 🟡 – **KLAR, se UTVECKLINGSLOGG #122.** `tune_quality_momentum_
      interact.py` skrivet och kört. Resultat: rank-produkt-featuren klarar
      HOLDOUT-tröskeln (IC=+0,086) men inte DEV (+0,039<0,05) – för svagt för
      säker "bygg in"-rekommendation. Klassiska QMJ-testet (momentum-IC
      betingat på kvalitetstertil) visar TVÄRTOM mönster mot litteraturen:
      momentum starkare bland LÅG-kvalitetsbolag (IC 0,093) än hög (IC 0,014)
      i detta urval. Ingen produktionsändring.
- [x] **4. [SCN-KÖP-2] Korrelationsfiltret slår ihop vikt i stället för att
      ersätta med nästa kandidat** 🟢→🟠 – `_correlation_filter`
      (`backtester.py:283-332`) kan ge FÄRRE effektiva unika innehav än
      MAX_POSITIONS. **Steg 1 KLAR, se UTVECKLINGSLOGG #125** (loggad under
      nattkö-numreringen innan pausen bekräftades här — checkbox eftersläpande
      fixad 2026-07-30 ~15:12). 0% av de relevanta ombalanseringstillfällena
      (≥MAX_POSITIONS kandidater) tappade en effektiv plats pga sammanslagning
      — konsekvent bred kandidatbuffert. Steg 2 (påfyllnadsvariant) avfärdad
      som lågprioriterat, ingen uppföljning.
- [ ] **5. [EDGE-6] Fasta ensemblevikter LGBM 0,6/LSTM 0,4 aldrig
      ablation-testade** 🟠→🔴 – `models/ensemble.py:28,40-44`. **BLOCKERAD,
      se UTVECKLINGSLOGG #128:** ingen tränad LSTM finns i denna sandlåda
      (`combine()` faller tillbaka till LGBM-only), och att träna en är
      historiskt ett 12+ timmars CPU-jobb (se `models/lstm_model.py`s
      checkpoint-kommentar om 2026-07-24-incidenten) – mycket dyrare än
      svepet i sig. **Öppen fråga till användaren** innan detta kan göras.
- [x] **6. [EDGE-4] Riskjusterad momentum som RANKNINGSFEATURE (inte bara
      positionsstorlek)** 🟡 – **KLAR, se UTVECKLINGSLOGG #123.**
      `tune_riskadj_momentum_ic.py` skrivet och kört. Resultat: LOVANDE –
      konsekvent HOLDOUT-förbättring för båda momentum-varianter (12-1:
      IC 0,055→0,093, 66%→83% hit rate; 13v kort: IC 0,025→0,052), ungefär
      oförändrat i DEV/pooled. God kandidat för uppföljande LambdaRank-
      ablation i full modell (nästa steg, ej gjort här).

## TIER 2 – Medel prioritet (värdefullt, något dyrare/osäkrare)

- [x] **7. [EDGE-3] Regimspecifik modellering (regim som feature eller
      separat modell)** 🟠🔴 – **Steg 1 KLAR, se UTVECKLINGSLOGG #137 –
      strukturellt dömt, inte bara svagt.** `regime_code` som delad
      kategorisk feature gav BIT-IDENTISKA resultat mot baseline på alla 25
      splits – LambdaRank rankar INOM varje datums grupp, och en feature som
      är identisk för alla tickers samma dag kan per konstruktion aldrig
      bidra till att skilja dem åt. Steg 2 (två separata regimblandade
      modeller) är därför den ENDA framkomliga vägen om frågan ska besvaras
      – kvarstår som ett större, egen-session-🔴-åtagande, inte gjort.
- [ ] **8. [SCN-HÅLL-1] Säljvaktens fem icke-riktkurs-bekräftelser (melt-up,
      värderingszon, CMF-distribution, insynskluster, röda PM-flaggor) aldrig
      isolerat validerade** 🟡 – **BLOCKERAD, se UTVECKLINGSLOGG #135.**
      `flow_snapshot.csv`/`_load_scores()` är rena ögonblicksbilder utan
      datumdimension, `model_target_price.csv` (som #25 byggde på) finns
      inte i sandlådan – ingen historik att backtesta mot förrän en sådan
      börjar sparas. Öppen fråga till användaren om historisk loggning ska
      startas.
- [x] **9. [RISK-2] Winsorisera/ranktransformera extrema regressionsmål**
      🟡 – **KLAR (kodläsning, ingen omträning), se UTVECKLINGSLOGG #136.**
      Premissen håller inte: `target_return` tränas aldrig som kontinuerligt
      regressionsmål (bara `pd.qcut`-baserade rangordningsetiketter, redan
      magnitud-okänsliga), och #111/#113/#114:s extremvärden kom från andra
      skripts egna beräkningar, inte modellens träningsetikett. Förväntad
      effekt av en omträning: försumbar. Lågprioriterad öppen fråga om
      användaren ändå vill ha den tomma bekräftelsen.
- [x] **10. [EDGE-9] Ekonomisk målfunktion vid hyperparameterval** 🟠→🟢 –
      **KLAR utan ny körning, se UTVECKLINGSLOGG #138** (återanvände redan
      insamlad data från #126). Dev-portfölj-CAGR som urvalskriterium hade
      valt exakt de två varianter #126 redan flaggade som overfitting
      (dev-upp/holdout-ner) – NDCG/IC+holdout-disciplinen är mer robust,
      inte mindre. Byt INTE urvalskriterium. Ingen produktionsändring.
- [x] **11. [SCN-SÄLJ-2] Cash-drag-kostnad av mellanliggande exits
      (`_trend_exit`/`_atr_stop_exit`) aldrig separat kvantifierad** 🟢 –
      **KLAR, se UTVECKLINGSLOGG #130.** `tune_cash_drag_atr.py` skrivet och
      kört (large, ATR_STOP_MULT=3,5x): 97 exits, snitt 27,4 veckor kontant
      till nästa ombalansering, snitt missad benchmark-avkastning +6,90% per
      exit, 72,2% av tillfällena hade stigande benchmark under kontant-
      perioden. Blev samtidigt förklaringen till att #116:s ATR-stop-
      rekommendation reverserades (se buggmönster 12, samma post).
- [x] **12. [EDGE-12] Kör CONDITIONAL_MODEL_AUDIT.md:s "Prioriterade
      kombination" (6 lager) som EN sammanhållen backtest** 🟠 – **KLAR
      (lager 3-6, 1-2 uteslutna – saknad källkod), se UTVECKLINGSLOGG #139.
      FÖRKASTAD:** qualified-holder+Otto-block förbättrar dev-MaxDD
      (-10,9%→-7,7%) men Sharpe/CAGR vänder båda negativt i holdout
      (+0,42→-0,30 / +2,0%→-1,0%) – klassiskt dev-mixed/holdout-ner-mönster.
      Otto-blockeringen visade sig dessutom nästan aldrig bindande (1 av
      113 tillfällen) – testade i praktiken ren qualified-holder-förlängning.
      Ingen produktionsändring.
- [x] **13. [RISK-1] Precision/Recall/F1 + kalibrering per
      sannolikhetsintervall** 🟢 – **KLAR, se UTVECKLINGSLOGG #132 – avslöjade
      en STÖRRE produktionsbugg under vägen:** `prob_up` är alltid exakt 0,5
      (samma bugg i `main.py` som i alla `tune_*.py`-skript, `predict()`
      anropas per-ticker i stället för tvärsnittsvis). Portföljurval/backtest
      opåverkat (rangordningen faller igenom till `prob_raw`), men det
      `prob_up`-tal som visas för användaren är meningslöst. Precision/recall
      i sig genuina: Dev +22,4pp över basfrekvens, Holdout -3,3pp under.
      Öppen fråga till användaren om produktionsfix.
- [ ] **14. [RISK-3] Nedsiderisk modellerad separat (P(avkastning<−X%))**
      🟡 – FKO diagnostik, unchecked.

## TIER 3 – Lägre prioritet / större investering

- [x] **15. [EDGE-5] Triple-barrier-target (López de Prado) som alternativ
      till XS_TARGET-kvantilen** 🔴 – **Pilot KLAR, se UTVECKLINGSLOGG #153.**
      Blandad bild: 76,2% av observationerna får en tidigare/mer informativ
      etikett (metodologiskt starkt argument), men riktningssignalen är
      oklar (Spearman mom_12_1↔upper-hit ≈ 0, trots att både upper/lower-
      grupperna har högre momentum än timeout-gruppen – momentum verkar
      predicera SNABBHET, inte RIKTNING). Värt en riktig pilot-omträning om
      man vill gå vidare, men inget uppenbart produktionsbeslut från detta
      ensamt. Skilt från redan köade `tune_metalabel.py`.
- [x] **16. [EDGE-8] Dynamiskt antal positioner (MAX_POSITIONS) baserat på
      bredd/dispersion** 🟠 – **BÅDA STEGEN KLARA. Steg 1 (#151): förutsättningen
      håller (corr varierar 0,13-0,60). Steg 2 (#152): NOLLRESULTAT ändå** –
      en 3-nivås N-regel (8/15/20) ger ingen mätbar skillnad mot fast N=15,
      dev nästan identiskt, holdout marginellt sämre (tunt underlag, 1-2
      ombalanseringar i holdout). Diversifieringsvinsten av N±5 är för
      svag jämfört med aktieurvalets egen edge. Ingen produktionsändring.
- [x] **17. [SCN-REBAL-1] ISK-skatteuttagets proportionella tvångsförsäljning
      vs rankningsbaserad** 🟠 – **KLAR, se UTVECKLINGSLOGG #148.**
      Bit-identiska resultat – tvångsförsäljningsgrenen triggade aldrig
      under 2010-2026, kassan räckte alltid till skatten. Frågan är moot.
      Femte "sällan bindande"-fyndet ikväll. Ingen produktionsändring.
- [x] **18. [SCN-REBAL-4] Test 11:s re-entry-tröskel (#102, högst
      prioriterade SHADOW-fynd i Tier 2) omskriven mot produktionens
      kalenderbaserade rebalansering** 🟠 – **KLAR, se UTVECKLINGSLOGG #149.
      Kvällens starkaste positiva fynd.** Bekräftar och skärper originalet:
      holdout CAGR fördubblas (+2,0%→+4,2%), Sharpe mer än fördubblas
      (0,42→1,08), MaxDD nästan halveras (-7,3%→-3,3%) vid 10%-tröskeln,
      mot en dev-kostnad på ~2pp CAGR. Monotont, konsekvent, 297 faktiskt
      bindande blockeringar (inte "sällan bindande" som de flesta andra
      testerna ikväll). Rekommenderas höjas till "redo för
      produktionsövervägande" – bör verifieras mot small-segmentet och/
      eller en oberoende period innan faktiskt beslut.
- [x] **19. [EDGE-7] Empirisk skattning av Kelly `win_loss_ratio` (fast 1,5)**
      🟡 – **KLAR, se UTVECKLINGSLOGG #143.** Nyanserat: helperiod-medel
      (3,05) farligt uppblåst av extremvinnare; holdout-medel/median
      (0,96/0,51) ligger UNDER antagandet – 1,5 kan vara optimistiskt,
      inte konservativt. Irrelevant idag (`SIZING_MODE=inverse_vol`).
- [x] **20. [SCN-SÄLJ-4] `REFILL_DISCOUNT=0,10` aldrig svept/validerad** 🟡 –
      **KLAR, se UTVECKLINGSLOGG #145.** Triggade bara 1-7 gånger totalt
      över 2010-2026 oavsett tröskel (5/10/15/20%) – backtest-utfallet är
      identiskt mellan alla varianter och ingen påfyllnad alls. Samma
      "sällan bindande"-mönster som #125/#127/#139. Ingen produktionsändring.
- [x] **21. [SCN-HÅLL-2] `_trend_exit` + `_atr_stop_exit` samtidigt aktiverade
      (aldrig testade tillsammans, bara var för sig i #115/#116)** 🟠 –
      **KLAR, se UTVECKLINGSLOGG #150.** trend_exit DOMINERAR helt (anropas
      först i koden) – "båda på" ger EXAKT samma siffror som trend_exit
      ensam, atr_stop:s bidrag försvinner spårlöst. Ingen ny risk, bara en
      ren maskeringseffekt. Ingen produktionsändring.
- [ ] **22. [RISK-4] Automatiska sanity-checks före träning** 🟡 – engångsbygge.
- [x] **23. [EDGE-11] Accrual-anomali (Sloan, (CFO−NI)/tillgångar)** 🟡 –
      **KLAR, FÖRKASTAD, se UTVECKLINGSLOGG #142.** IC försumbart och fel
      tecken vid 26v (+0,028), exakt noll vid 52v (+0,001, trots stor
      kvintilspread – sannolikt svansbrus). Replikerar inte i detta
      svenska mikrobolagstunga urval. Ingen produktionsändring.
- [x] **24. [SCN-KÖP-3] Nykvalificerade bolag (78-104v historik) vs
      etablerade – prestandaskillnad vid köp** 🟢 – **KLAR, se
      UTVECKLINGSLOGG #140. Oron besannades INTE** – nykvalificerade
      bolag presterar BÄTTRE (högre median/vinstandel, lägre volatilitet
      på 26-52v) än etablerade i köpsignalerna, inte sämre. Ingen
      produktionsändring, trygghetsbekräftelse.
- [x] **25. [SCN-HÅLL-4] Individ-drawdown-golv saknas när portföljnivån
      maskerar en enskild positions -40/-50%-ras** 🟢 (mätning) → 🟠 (fix-
      test) – **BÅDA stegen KLARA. Steg 1 (#141): real risk, kvantifierad**
      (28/383 hållperioder ≤-40%, 68% osynliga för Drawdown Guard). **Steg 2
      (#147): en cash-drag-medveten rotationsvariant testad** – till
      skillnad från #130s ATR-stop (som skadade via cash-drag) förbättrar
      en strängare -40%-tröskel (bara 22 triggers/16 år) resultatet svagt,
      och rotation vinner marginellt över kontant-exit på holdouten
      (CAGR +2,30% mot +2,20%, Sharpe 0,47 mot 0,46). Litet urval (n=22),
      riktningsindikation. Rekommendation: rotation > kontant-exit, håll
      tröskeln sträng. Ej implementerad i produktion ännu.

## TIER 4 – Lägst prioritet / diagnostik utan tydlig åtgärd ännu

- [x] 26. [SCN-KÖP-4] MOMENTUM_GATE vs entry_policy "overextended"-konflikt 🟢
      – **KLAR (ren kodläsning), se UTVECKLINGSLOGG #154.** Strukturellt
      omöjlig konflikt: grinden är aktiv bara för large, blockeringen bara
      för small – aldrig samtidigt på samma segment.
- [x] 27. [SCN-HÅLL-3] SMA20-whipsaw-frekvens (skärper LCA-26) 🟢 –
      **KLAR, se UTVECKLINGSLOGG #158.** 41,5% av SMA20-nedåtkorsningar
      återhämtar sig inom 4v – förklarar troligen varför #115:s trend_exit
      var så skadlig. Bekräftande kontext, ingen ny åtgärd.
- [x] 28. [SCN-REBAL-2] Ackumulerad viktdrift under REBALANCE_BUFFER_PCT
      (skärper LCA-32) 🟢 – **KLAR, se UTVECKLINGSLOGG #161.** Real drift:
      viktspridning dubblas i snitt över en ombalanseringscykel, störst
      position växer 11,9%→16,2% i snitt, upp till 28-35% i volatila år
      (2020/2022). Ingen befintlig mekanism fångar detta mellan
      ombalanseringar. Ingen produktionsändring, men värt att känna till.
- [x] 29. [SCN-REBAL-3] Flerveckors uppbyggnadsfördröjning via
      `_liquidity_cap` (skärper LCA-10) 🟢 – **KLAR, se UTVECKLINGSLOGG
      #162.** Strukturellt gap bekräftat (ingen påfyllnad mellan
      ombalanseringar, kan ge upp till ett HELT ÅRS undervikt, inte bara
      "några veckor"), men bara 2 tillfällen totalt 2010-2026 – sjätte
      "sällan bindande"-fyndet ikväll. Ej mätt för small-segmentet.
- [x] 30. [SCN-SÄLJ-1] Sälj-köp-korrelationsöverlapp samma vecka 🟢 –
      **KLAR, se UTVECKLINGSLOGG #157.** Vanligt, inte ovanligt: 100% av
      handelsåren hade minst en sektoröverlapp, snitt 62% av sålda
      sektorer återköpta samma vecka. Rimligt tolkat som sunt
      temarotation, inte ett problem. Ingen produktionsändring.
- [x] 31. [SCN-SÄLJ-3] "Modellen har släppt bolaget"-flaggans redundans i
      säljvakten 🟢 – **KLAR, se UTVECKLINGSLOGG #163. INTE redundant:**
      47,0% av händelserna hade ingen annan bekräftelse alls samtidigt –
      bär genuint egen information, inte bara en eko av pris-signaler.
- [x] 32. [SCN-SYS-1] Dubbel exekveringskostnad vid samtidig derisk+trend/ATR-exit samma vecka/ticker (verifiering, sannolikt inte en bugg) 🟢
      – **KLAR, se UTVECKLINGSLOGG #155. Bekräftat: ingen bugg**, två
      separata legitimt kostnadsberäknade affärer.
- [x] 33. [EDGE-10] Osäkerhet via walk-forward-split-oenighet 🟡 –
      **KLAR, se UTVECKLINGSLOGG #164. Validerat, fungerar som avsett:**
      angränsande modeller är mer överens om extrema aktier, mer oense om
      mittenaktier (Spearman -0,271) – ett äkta osäkerhetsmått. Kunde
      användas som konfidensfilter, inte implementerat.
- [x] 34. [EDGE-13] Long-short/hedge-känslighetsanalys (mätning, bygg ingen
      blankningskod) 🟢 – **KLAR men INKONKLUSIV, se UTVECKLINGSLOGG #159.**
      Bara 2 av 17 år hade djup nog kandidatpool för en ren mätning
      (samma tunnhet som #156). Använd decil-baserad evidens (Test 8,
      n i tiotusental) i stället om frågan behöver besvaras robust.
- [ ] 35. [EDGE-14] Finkornig Avanza-temastyrka som feature – ⚠️ möjlig dubblett av redan förkastade #108, testa bara om grov GICS-upplösning misstänks vara orsaken
      – **Bedömning 2026-07-30: inget som pekar mot att GICS-upplösningen
      var boven i #108:s förkastande (svag/inkonsekvent på alla mått, inte
      ett gränsfall) – låg prioritet att driva vidare, medvetet ej körd.**
- [ ] 36. [EDGE-15] Periodisk hyperparameter-omval inom walk-forward 🔴 –
      stort infrastrukturarbete (MODELLANALYS punkt 11), medvetet ej
      påbörjat ikväll, kräver en egen session.
- [ ] 37. [EDGE-16] Nordisk universumutvidgning via Börsdata 🔴 – stort
      datainhämtningsprojekt, medvetet ej påbörjat ikväll, kräver en egen
      session/beslut om datakällor.
- [x] 38. [RISK-5] Feature distribution drift train/val/test per fold 🟡 –
      **KLAR, se UTVECKLINGSLOGG #160.** Generellt mycket stabilt (0,1%
      av par har stor drift), men `resid_mom` sticker ut kraftigt (5x mer
      instabil än näst mest). Samma feature som redan är #121:s starkaste
      solo-IC-fynd – värt att hålla ett öga på, inte uppenbart ett problem.
- [x] 39. [RISK-6] MIN_HISTORY_WEEKS=78-effekt på nynoteringar 🟢 –
      **REDAN BESVARAD av #24/[SCN-KÖP-3] (UTVECKLINGSLOGG #140)**, som
      var en uttrycklig skärpning av just denna post – nykvalificerade
      bolag presterar BÄTTRE än etablerade i köpsignalerna, ingen negativ
      MIN_HISTORY_WEEKS-effekt hittad. Ingen ny körning behövdes.
- [x] 40. [RISK-7] Antal köpsignaler per fold (degenererat allt/inget) 🟢
      – **KLAR, se UTVECKLINGSLOGG #156. Händer faktiskt** (2010: 0/95
      kvalificerade, hela året kontant; 2012/2022 också tunna), men det
      är `MOMENTUM_GATE`s avsedda funktion, inte en bugg – exakt de år
      man skulle förvänta sig (finanskris/skuldkris/räntehöjning).

---

## Medvetet bortvalda dubbletter (från research-fasen, gäller hela denna fil)

- Residual-momentum i sig (MODELLANALYS §5 sa "saknas") – redan implementerat
  som `resid_mom`; omformulerat till post #2 ovan (stale bugfix) i stället.
- Meta-labeling – redan `tune_metalabel.py` i nattkön; post #15 (triple-barrier)
  är medvetet en ANNAN hypotes (primär target, inte sekundärt filter).
- Breddstyrd exponering – redan `tune_breadth_gate.py` (#75, förkastad); post
  #16 gäller antal positioner, inte total exponering.
- Sektor-gap GICS-nivå – redan `tune_sector_theme_gap.py` (#108, förkastad);
  post #35 flaggad som möjlig dubblett, låg prioritet.
- Deflated Sharpe / label-uniqueness / experimentregistry / point-in-time-data
  (FKO #14-17) – redan identifierade som "kräver användarens vägledning" i
  handoff-filen, INTE återinförda här.
- LCA-1 till LCA-35 – helt undvikna. Där ett scenario (Tier 1/3/4 SCN-poster)
  ligger nära en LCA-post är det medvetet SKÄRPT med en konkret testmetod
  LCA-listan saknade (t.ex. #27/#28/#29 skärper LCA-32/LCA-10/LCA-26), inte
  en ren dubblett.
