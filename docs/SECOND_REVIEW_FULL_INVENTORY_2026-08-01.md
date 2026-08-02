# Fullständig second review – samtliga test, metoder och tune-skript

Datum: 2026-08-01. Inventering: 97 test-/analysfiler i `momentum_ml` och 92
sparade tune-/scorecard-/backtestutdata. Dokumentet kompletterar SR-1–SR-14 i
`SECOND_REVIEW_TESTER_2026-08-01.md`.

## Revisionsregler

Varje tidigare test bedöms som en av: **beslutsduglig**, **diagnostisk**,
**inaktiv** (regeln band inte), **metodfel**, **datablockerad**, **ej körd** eller
**annat delsystem**. Ett nytt test tas bara upp om mekanismen skiljer sig från
tidigare test. Den forskningsexponerade holdouten får aldrig välja variant.

Gemensamma problem över materialet:

- Baslinjerna skiljer sig kraftigt mellan skript; SR-9 är obligatorisk gate.
- Många äldre slutsatser valdes med holdout och är nu endast diagnostik.
- Några test kör gammal konfiguration, annat universum eller förenklad simulator.
- Flera ”nollresultat” var inaktiva: koncentrationstak, ISK-försäljningssätt,
  refill och entry policy band nästan aldrig.
- `regime_feature` och äldre interaktionsskript ändrade i praktiken inte rankingen.
- Gamla sannolikhetsmått är inkompatibla med LambdaRank-score.
- Fundamentaresultat kan inte generaliseras till Small innan PIT-täckningen är löst.

## Ytterligare identifierade tester, SR-15–SR-44

### Modell, target och träningsmetod

#### SR-15 – Adaptiv sample-age i stället för fast exponential decay

Fast 52/104/208v decay försämrade portföljen, men förbättrade vissa svaga splits.
Testa change-point-styrd viktning: börja decay först när feature-/IC-drift passerar
en förregistrerad nivå. Kontroll: samma effektiva sampelstorlek med slumpviktning.

#### SR-16 – Hyperparameterplatå och nested walk-forward

Enstaka hyperparametrar gav stora skillnader, men valet exponerades mot holdout.
Kartlägg en liten lokal platå runt nuvarande värden och välj stabil region via
inner walk-forward, inte bästa punkt. Rapportera parameterkänslighet och rank-
korrelation, inte bara CAGR.

#### SR-17 – Missingness som PIT-signal

Native NaN förbättrade DEV men var instabilt; nollfyllning blandar ”saknas” med
ekonomiskt noll. Testa värde + missing-indikator + datans ålder per fundamental.
Separera strukturellt saknat (ej rapporterat) från tekniskt inhämtningsfel.

#### SR-18 – Selektiv monotonicitet med ekonomisk teckengate

Globala monotonic constraints förbättrade vissa perioder men inte konsekvent.
Förregistrera constraints endast för robust teckenstabila features och lämna
momentum/interaktioner fria. Jämför modellkomplexitet och splitstabilitet.

#### SR-19 – Datumviktning med capped group mass

Equal-date/unweighted-resultaten är motstridiga mellan versioner. Testa en enda
kanonisk implementation där varje datum får lika totalvikt men enskilda rader
cap:as, samt kontrollera `group`/sample-weight-semantiken direkt i LightGBM.

#### SR-20 – Checkpointensemble, inte checkpointval

Rank-IC-baserat checkpointval gav högre DEV-CAGR men låg stabilitet. Testa medelrank
från de 3–5 bästa inner-DEV-checkpointsen. Hypotesen är lägre variants och mindre
beroende av ett brusigt early-stopping-mått.

#### SR-21 – Redundanskluster och grupp-dropout

Multikollinearitet + ablation antyder utbytbara momentumfeatures. Klustra features
på PIT-DEV, behåll en representant per kluster eller använd random group dropout.
Mät stabilitet i feature importance och rang, inte bara medelavkastning.

#### SR-22 – Asymmetrisk rankingloss

Bottenrankade aktier steg mer än topprankade i det hypotetiska short-testet;
modellen är alltså inte symmetriskt användbar. Testa loss/vikter som endast
optimerar ordningen i övre svansen och inte straffas för felordning i botten.

#### SR-23 – Competing-risk target från triple barrier

Triple-barrier-piloten visade 42% upper, 34% lower och 24% timeout. Testa två
separata modeller: sannolikhet för upper före lower samt tid till barriär. Använd
dem som veto/tie-break ovanpå 52v-rank, inte som ersättande huvudtarget.

#### SR-24 – Residualmodell mellan rankers

CatBoost/LambdaRank/objective-tester ska följas upp med felkomplementaritet per
datum. Träna challenger på residualordningen bland endast toppkvantilen; adoptera
bara om datumvis rankfel är lågt korrelerat och netto-top-k förbättras.

### Fundamental- och alternativdata

#### SR-25 – Accrual × lönsamhet/kassaflödeskvalitet

Låga accruals hade cirka +13 pp 52v Q1–Q5-spread men nära noll linjär IC. Det
tyder på svans/nonlinearitet. Testa sektor-/storleksneutral låg-accrual-veto endast
för bolag med svag ROA eller negativ CFO; undvik en kontinuerlig global feature.

#### SR-26 – Kassaflödesinflektionens persistens

Separera en engångsinflektion från 2–3 rapporter av förbättrad CFO, och neutralisera
för working-capital-reversal, sektor och bolagsstorlek. Testa som event/tie-break
med korrekt publiceringslagg.

#### SR-27 – Fundamentamodell som residual till ROA

Börsdata-LGBM slog inte enkel ROA. Testa om övriga fundamenta kan förklara
framtidsavkastning efter att ROA-rank tagits bort, med monotont additiv modell.
Om residual-IC saknas stängs hela komplexa fundamentaspåret.

#### SR-28 – Rapportfärskhet × fundamentalsignal

Samma fundamentavärde bör väga olika beroende på dagar sedan rapport. Testa ROA,
accrual och kassaflödesinflektion i 0–30/31–90/>90 dagars PIT-kohorter samt om
signalens halveringstid skiljer sig mellan sektorer.

#### SR-29 – Uppmärksamhet mäts relativt förväntad rapportvolym

Attention-gap gav inte stöd för enkel låg volym; hög volym såg ibland starkare ut.
Residualisera rapportvolym mot aktiens normala rapportvolym, absolut surprise och
marknadsvolym. Testa interaktion, inte median-split.

#### SR-30 – Utdelningssignal: hållbarhet och horisontskifte

Dividend-gap bytte tecken mellan 8v och 26v. Testa utdelningshöjning endast när
FCF-täckning, nettoskuld och utdelningshistorik stödjer hållbarheten. Förregistrera
26/52v; ingen kortsiktig gapregel.

#### SR-31 – Informativ insiderintensitet

FI-data hade tillräcklig täckning medan äldre insynscache inte hade det. Testa
nettoköp relativt lön/förmögenhetsproxy, flera oberoende insiders, roll, bolags-
storlek och köp nära rapportförbud. Använd transaktionens publiceringsdatum.

#### SR-32 – Värdering som villkorad förväntad avkastning, inte veto

Otto-banden var sällsynta och kombinerade veto försämrade CAGR. Testa kontinuerlig
egen-historisk värderingspercentil × positivt momentum × stabil EBIT. Värdering får
endast bryta lika momentumrank, inte blockera starka vinnare.

#### SR-33 – Quality × momentum med dubbel neutralisering

Det dedikerade skriptet finns men saknar sparat körresultat. Kör PIT-säkert efter
fundamentagaten och neutralisera kvalitet för sektor/storlek. Testa om momentum-
edge och vänstersvans skiljer sig mellan kvalitetskvartiler.

#### SR-34 – Rapporthändelser som gemensam eventmodell

PEAD, attention, crowding, dip reversal, earnings/dividend/sentiment gaps har
testats eller planerats separat och riskerar multipeltestning. Bygg ett gemensamt
eventbord med samma cutoff och matched controls; pröva huvudkomponenterna
surprise, reaktion, volym, crowding och efterföljande rankförändring i en enda
förregistrerad modell.

### Portfölj, rotation och risk

#### SR-35 – Staggered 52v-kohorter

52v target betyder inte att hela portföljen måste roteras samma vecka per år.
Testa 4 eller 13 överlappande kohorter med samma genomsnittliga 52v hålltid,
kapital, signal och kostnader. Detta minskar timingrisk utan att byta alpha-signal.

#### SR-36 – Rank-hysteresis/turnover buffer

I stället för generell re-entry-spärr: behåll innehav tills det lämnar topp-N plus
en buffert och köp först när kandidat går in i topp-N minus buffert. Förregistrera
en enda buffert från DEV-rankstabilitet och jämför nettoedge per undviken affär.

#### SR-37 – Cash-alternativ vid gate/stop

Momentumgrind och ATR-stop tappade CAGR främst genom kontantdrag. Jämför kontant
med XACT Sverige/kort ränta och omedelbar näst-rankad aktie. Då separeras värdet i
exitbeslutet från kostnaden för parkeringsvalet.

#### SR-38 – Bredd/regim som hedgekvot, inte binär gate

Breadth-gate gav liten/ingen alpha men viss riskskillnad. Testa kontinuerlig hedge
eller indexandel med oförändrad aktieranking och riskbudget, så stock-selection-
alpha separeras från marknadsbeta.

#### SR-39 – Faktor- och benchmarkattribuering

Mät alpha mot OMXS30, bred Sverige, equal-weight samt storlek/value/quality/
momentumfaktorer. Dekomponera om förbättringar är stock-selection, size tilt,
sektor, beta eller likviditet. Primärmål ska vara residual alpha efter kostnader.

#### SR-40 – Capture/miss-kohort

För de största framtida vinnarna som modellen missade: mät exakt blockerande steg
(universum, historiklängd, likviditet, feature-NaN, rank, sektorfilter, korrelation,
entry-policy). Jämför mot fångade vinnare med samma ex-ante-egenskaper och skapa
bara features för systematiska, observerbara skillnader.

#### SR-41 – Exekveringsfördröjning och signaldecay

Kör nästa-bar med 1/2/5 handelsdagars fördröjning, öppning/VWAP-proxy, spread och
gap. Mät alpha-halveringstid per signaltyp. Årsrebalansering kan dölja att vissa
eventfeatures måste exekveras snabbare än prisdata tillåter.

#### SR-42 – AUM-kapacitetskurva och successiv fill

Utöka SR-14 till portföljnivå: 1/5/10/25/50 MSEK, deltagandegrad, spreadimpact,
ofyllda order och successiv fill. Rapportera netto-alpha och time-to-fill per AUM,
Large och Small separat.

### Valideringsprotokoll

#### SR-43 – Placebo- och leakage-batteri

Varje ny featurefamilj ska klara: en veckas extra lagg, datumpermutation inom
bolag, tickerpermutation inom datum, omvänd target och avsiktlig framtidsfeature
som positiv kontroll. Testet ska fallera högt när positiv kontroll tas bort och
ge noll för placebo; annars litar vi inte på pipelinen.

#### SR-44 – Multiple-testing ledger och reality check

Registrera alla varianter – även krascher och tysta omkörningar – med hypotes,
primärmål och antal frihetsgrader. Använd block-bootstrap/White reality check eller
FDR på DEV-resultat samt deflated Sharpe. Detta hindrar 97 skript från att skapa
en vinnare av slump.

## Full täckningsmatris för befintliga filer

### Modell/träning

- `tune_lambdarank_vs_baseline`, `tune_catboost_vs_lambdarank`,
  `tune_objective_comparison`, `tune_hyperparams`: SR-16, SR-22, SR-24, SR-44.
- `tune_age_weight`, `tune_equal_date_weight`: SR-15, SR-19.
- `tune_rank_metric_selection`, `tune_rank_calibration`,
  `tune_precision_recall_calibration`: SR-11, SR-20.
- `tune_nan_handling`, `tune_feature_multicollinearity`, `tune_ablation`,
  `tune_model_dropped_redundancy`: SR-17, SR-21.
- `tune_monotonic`, `tune_v2_features`, `tune_interaction`: SR-18, SR-21.
- `tune_triple_barrier`, `tune_downside_veto_model`, `tune_metalabel`:
  SR-23; meta/downside får inte öppna gammal holdout igen.
- `tune_horizon`, `tune_horizon_optimized`, `tune_horizon_ensemble`,
  `tune_lambdarank_robustness`: SR-1, SR-16, SR-35.
- `tune_disagreement_filter`, `tune_split_disagreement`, `tune_abstention_gate`:
  SR-2, SR-20.
- `tune_regime_feature`, `tune_regime_exposure`: SR-3, SR-38.
- `tune_sector_categorical`, `tune_universe`: SR-3, SR-39 samt gemensam
  representation med segment-/sektorhuvud som senare arkitekturtest.

### Fundamenta/altdata

- `tune_fundamentals`, `tune_borsdata_fundamental_lgbm`: SR-27, SR-28.
- `tune_accrual_anomaly`, `tune_cashflow_inflection`: SR-25, SR-26.
- `tune_quality_momentum_interact`, `tune_quality_score_validation`,
  `tune_hold_forever_fundamentals`: SR-33; LLM-kvalitet förblir blockerad där
  historiska snapshots saknas.
- `tune_pead`, `tune_attention_gap`, `tune_report_crowding`,
  `tune_report_dip_reversal`, `tune_earnings_reaction_gap`: SR-29, SR-34.
- `tune_dividend_gap`: SR-30, SR-34.
- `tune_insider_gap`, `tune_insider_gap_fi`: SR-31, SR-34.
- `tune_sentiment_gap`, `tune_case_tracker`: datablockerade tills riktiga
  historiska snapshots finns; därefter SR-34.
- `tune_otto_valuation_band`, `tune_otto_valuation_continuous`,
  `tune_qualified_holder_otto_combined`, `tune_global_relative_value`: SR-32.
- `tune_sector_theme_gap`, `tune_resid_mom_ic`, `tune_riskadj_momentum_ic`,
  `tune_riskadj_momentum_ablation`: SR-3, SR-8; solo-IC först, full modell sedan.

### Portfölj/exits/risk

- `tune_sizing`, `tune_dynamic_positions_backtest`,
  `tune_dynamic_positions_precheck`, `tune_concentration_cap`,
  `tune_correlation_filter_freq`: SR-12, SR-13, SR-39.
- `tune_reentry_threshold_production`, `tune_refill_discount`,
  `tune_entry_policy_backtest`: SR-4, SR-36.
- `tune_atr_stop`, `tune_cash_drag_atr`, `tune_asymmetric_exit`,
  `tune_combined_exits`, `tune_individual_drawdown_floor`,
  `tune_individual_drawdown_floor_rotate`: SR-5, SR-37.
- `tune_takeprofit`, `tune_anchor_exit`: SR-6.
- `tune_gate`, `tune_breadth_gate`, `tune_dispersion_proxy`, `tune_voltarget`:
  SR-13, SR-38.
- `tune_slippage_vix`, `tune_liquidity_cap_delay`: SR-41, SR-42.
- `tune_isk_derisk_ranked`, `tune_isk_tax`: skatte-/implementationstest, inte
  alpha; SR-9 krävs eftersom den rankbaserade varianten var inaktiv.
- `tune_kelly_win_loss_ratio`: irrelevant medan live-sizing är inverse-vol;
  återöppnas bara om sizing-arkitekturen ändras.
- `tune_leverage_holding_period`, `backtest_bear_hedge`, `backtest_bull_hedge`:
  SR-38, SR-41; separat ETF-/riskdelsystem.
- `tune_large_small_allocation`, `backtest_core_allocation`,
  `backtest_theme_satellite`, `tune_etf_rotation`: allokeringsdelsystem; SR-39 och
  SR-42, men inte stock-rank-alpha.
- `tune_idx_mix`: PIT-OMX30-testet är redan köat; resultatet hör till SR-39:s
  benchmark-/active-share-attribuering, inte en fristående ny feature.
- `backtest_core_dip_timing`, `backtest_core_crisis_buying`: sparande-/timing-
  delsystem; stäng som separat mandat om målet är enbart Momentum-alpha.

### Diagnostik och metodkontroll

- `capture_analysis`, `era_analysis`, `tune_hold_forever`: SR-15, SR-35, SR-40.
- `tune_newly_qualified_vs_established`: SR-7; PIT-universum krävs före sleeve.
- `tune_lambdarank_common`: delad testhelper, inte ett självständigt experiment;
  omfattas av SR-9, SR-43 och SR-44.
- `tune_feature_sanity_checks`, `tune_feature_drift`: SR-17, SR-43.
- `tune_statistical_power`: SR-44.
- `tune_combined_validation`, `tune_integrated_backtest`: SR-9 och SR-39.
- `security_analysis`: narrativt verktyg, uttryckligen ingen signal/test.
- `tune_case_tracker`: diagnostik tills tidsstämplade historiska case finns.

## Slutlig prioritering efter fullinventeringen

### P0 – bygg före all ny forskning

1. SR-9 gemensam baslinjeparitet.
2. SR-10 corporate-action-audit.
3. SR-43 placebo/leakage-batteri.
4. SR-44 multiple-testing ledger.

### P1 – högst sannolik alpha

1. SR-1 villkorad 52v+13v.
2. SR-3 regim×aktie-interaktioner.
3. SR-22 upper-tail-rankingloss.
4. SR-25 accrual×quality.
5. SR-33 quality×momentum, efter PIT-gate.
6. SR-40 systematisk analys av missade vinnare.

### P2 – nettoalpha genom bättre portföljmekanik

1. SR-35 staggered 52v-kohorter.
2. SR-36 rank-hysteresis.
3. SR-37 alternativ till kontant efter exit/gate.
4. SR-41 execution-delay/signaldecay.
5. SR-42 AUM-kapacitet.

### P3 – lovande men datakrävande

SR-7/SR-17/SR-25–SR-34. Dessa körs först efter godkänd PIT-täckning för den
aktuella datakällan och segmentet.

## Explicit stängda sökvägar

- Ingen ytterligare blind hyperparameter-, horizon- eller stop-loss-grid.
- Ingen optimering på gammal holdout.
- Ingen ren regimetikett i en tvärsnittsranker.
- Ingen sannolikhetskalibrering direkt på LambdaRank-score.
- Ingen LLM/sentiment/case-signal utan historiska snapshots.
- Ingen Small-slutsats från nuvarande fundamentamatris.
- Ingen variant kallas negativ om den aldrig band; den klassas som inaktiv.
