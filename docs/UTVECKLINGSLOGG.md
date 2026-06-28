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

**Etablerade sanningar ur loggen:**
1. Modellen är **maxad på prisdata** – feature-additioner överanpassar (#7, #8).
2. Risk-hygien (#14, #15, #17) gör kurvan snyggare men **skapar ingen ny alfa** –
   kvar i negativt territorium mot OMXS30.
3. **Alt-data (regulatorisk PM-text) bär ingen OOS-drift** (#18) – inte i order,
   inte i rapporter, inte i VD-ord, inte på någon horisont. Både pris- OCH
   text-sentiment-vägarna är därmed uttömda. Marknaden prisar uppenbarligen in
   även PM-*tonen* effektivt på vår horisont, inte bara den snabba reaktionen.

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
- **Montrose-mäklarorder = riktiga pengar** – bara läs-läge implementerat; varje
  orderläggning ska gate:as hårt/bekräftas. Användarens riktiga portfölj
  (~170 k kr) är känslig finansiell data.

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
   (OMXS30 = den ärliga, oslagna ribban) vs jaga alt-data-edge. + regulatorisk
   (MiFID) bedömning före publik lansering (se MODELLANALYS.md §6.4).

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
