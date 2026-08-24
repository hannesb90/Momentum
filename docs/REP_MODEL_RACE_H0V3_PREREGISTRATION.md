# REP_MODEL_RACE_H0V3 — PREREGISTRERING

Datum: 2026-08-19 · Status: **LÅST FÖRE ALL MODELLTRÄNING**
SHA256: `8c301cf82a0c05f4dc869e757eb1be0320d204bbab934ae400c76e34ccd2555f`

Inga modeller tränade. Inga forskningstester körda. Inga parametrar optimerade.
H0 V3 oförändrad.

---

## VARFÖR DETTA RACE

Den globala re-auditen slog fast **GLOBAL MODEL ARCHITECTURE CURRENTLY IDENTIFIED: NO**.
Sex modellfamiljer kräver ren replikation eftersom deras tidigare förkastanden inte längre
är identifierade:

| Gammalt race | Varför domen inte räcker |
|---|---|
| H1419 sexmodellsracet | Kördes mot **fryst H0, inte H0 V3**, på H1419 V2 där medlemskapet inte var PIT-verifierat, och på **ett** fönster delat i dev/final. Fyra av sex familjer byter tecken. |
| Spår D core-race | `panels/core_panel.json` bär `membership_verified: false` och `membership_basis: HISTORICAL_MEMBERSHIP_UNKNOWN`. Samtliga sex förkastades på en population vars historiska medlemskap var okänt. |

Ingen av dem uppfyllde tvåfönsterkriteriet. Ingen använde H0 V3.

**20 % CAGR är projektets ekonomiska ambitionsnivå — inte ett acceptanskriterium, inte ett
tuningmål, och aldrig skäl att föredra en statistiskt svagare modell.**

---

## MODELLER: SEX INKLUDERADE, FYRA EXKLUDERADE

Samtliga parametrar `LOCKED_FROM_PRIOR`. Ingen sökning.

| Familj | Konfiguration | Ursprung |
|---|---|---|
| ExtraTrees | 300 träd, depth 5, leaf 30, sqrt | H1419-preregistreringen |
| CatBoost | 100 iter, depth 3, lr 0,03, l2 10,0 | H1419-preregistreringen |
| LightGBM | 80 träd, lr 0,03, 7 leaves, depth 3, λ 10,0, α 1,0 | H1419-preregistreringen |
| XGBoost | 300 träd, lr 0,03, depth 3, min_child 20, λ 1,0 | spår D-preregistreringen |
| RandomForest | 300 träd, depth 4, leaf 40, sqrt | H1419-preregistreringen |
| HistGradientBoosting | 100 iter, lr 0,05, 7 leaves, leaf 40, l2 10,0 | H1419-preregistreringen |

För LightGBM och CatBoost finns **två** gamla konfigurationer. H1419-varianten väljs eftersom
den har **samma target och samma featuremängd** som detta race; spår D-varianten hör till en
52-veckors target och 29 features.

**Känd konfound, redovisad öppet:** XGBoost exkluderades ur H1419-racet med motiveringen *"Not
installed in the reproducible venv"* och har därför ingen kapacitetsmatchad konfiguration. Spår
D:s används ordagrant. Den är kraftfullare (300 träd mot LightGBMs 80), vilket blandar arkitektur
med kapacitet. Att konstruera en egen matchning vore närmare tuning än replikation.

**Exkluderade:** Ridge och ElasticNet (förkastandena är identifierade — negativa i båda
delperioderna i båda rollerna, och negativ OOS mean IC i spår D), LSTM
(`INSUFFICIENT_PROVENANCE`), LambdaRank (legacy-linjen är isolerad; objektivfrågan är separat).

**Frö:** 20260819 för samtliga. De gamla kördes med 20260816 respektive 20260808. Att återanvända
ett gammalt frö på ny data ger ingen reproducerbarhetsvinst men riskerar att låsa in ett gynnsamt
utfall. Ett enda nytt frö för alla familjer är neutralt.

---

## UNIVERSUM

H0 V3:s PIT-eligibility, ordagrant. **Ingen modell får tillgång till instrument som H0 V3 inte
betraktar som investerbara vid t.** Samma panelgitter, samma identitetsmodell (orderbook_code som
`instrument_id`, ISIN som tidsbegränsat alias, ingen namnmatchning), samma restriktionsregister.
Avnotering är aldrig en ex-ante-feature.

---

## TARGET

**Aktiens justerade avkastning över de nästa två 4-veckorspanelerna (8 veckor).**

H0 V3 rebalanserar varannan panel. En modell som predikterar 52 veckor men utvärderas på 8
veckors rebalans har horisontmismatch. Regression på absolut avkastning; ingen klassificering,
ingen rankingobjektiv.

- Mot H1419-racet: **LITERAL_REPLICATION** — identisk target.
- Mot spår D: **CLEAN_REIMPLEMENTATION** — den använde `target_fwd52w`, en materiellt annan horisont.

Överlappet (8-veckors target på 4-veckorsgitter = 2 paneler) hanteras med purge, embargo och
Regel 6:s överlappskorrigering `t/√2`.

---

## FEATURES — ARKITEKTUR, INTE DATAMÄNGD

**F0, gemensam kärna: 23 prisbaserade features**, ordagrant den mängd som låstes i
H1419-preregistreringen. H0 V3:s score och rank **ingår** — utan dem kan residualfrågan i steg B
inte ställas alls.

**F1, utökad: 34 features.** Körs **endast** om minst en familj passerar STAGE A eller B på F0.
Passerar ingen på F0 är frågan "räcker mer prisinformation" inte längre meningsfull, och F1 stryks.
Detta är låst i förväg.

**Förbjudna i detta race:** market cap, ICB, segment, turnover, Amihud-illikviditet, volymtrend,
spread, antal avslut, aktieantal, fundamenta, händelser, sektorrelativa mått.

De får inte läggas in bara för att de nu finns. De är populationsfeatures och hör till PHASE_5.

---

## TEMPORAL DESIGN

| Fönster | Träningsstart | Initial träningsslut | Första utvärderingspanel | Slut |
|---|---|---|---|---|
| OOS_WINDOW_1 | 2012-07-02 | 2015-12-31 | 2016-04 | 2019-12-30 |
| OOS_WINDOW_2 | 2020-01-02 | 2022-12-30 | 2023-04 | 2026-07-24 |

Expanderande walk-forward, årlig omträning. **Purge 8 veckor + embargo 4 veckor = 12 veckors gap.**

**Ingen valideringsmängd.** Samtliga hyperparametrar är låsta, så ingenting selekteras. Att införa
en valideringsmängd utan att selektera vore att kasta data utan syfte; att selektera på den vore
parametersökning. Early stopping är avstängt för alla familjer.

Fönstren delar inga observationer och ingen modellinstans.

---

## TESTSTEGE A → B → C

### STAGE A — standalone: kan X slå H0 V3?
Modell X rangordnar H0 V3:s eligible universum, Top-30, likavikt, samma kostnadsmodell.
`GLOBAL_MODEL_SUPPORTED` kräver **allt**: positiv excess i båda fönstren, över placebobandet
2,4 pp i minst ett, **positiv mean IC och positiv top-30 IC i båda**, leave-top-3-out behåller
≥50 % av överavkastningen i båda, MaxDD inte >5 pp sämre, turnover inte >100 % högre, och positiv
excess kvar även vid 40 bp.

*Top-30 IC är det kriterium båda gamla racen fallerade på — samtliga sex familjer hade negativ
top-30 IC i spår D. Det behålls ordagrant eftersom det är den handelsbara delen av tvärsnittet.*

### STAGE B — residual/overlay: tillför X information utöver H0 V3?
Informationsgrind in: mean IC > 0 **och** top-30 IC > 0 i båda fönstren. **En modell som faller
STAGE A men passerar grinden går ändå till B** — ett standalone-underkännande är inget bevis mot
komplementaritet.

**Låst metod, en enda för alla familjer:** H0 V3 producerar Top-30 oförändrat, modell X omordnar
endast dessa och Top-20 hålls. Jämförs mot **både** H0 V3 Top-20 (apples-to-apples) och Top-30.
Metod A och metod C väljs bort här och får inte prövas i efterhand.

### STAGE C — ensemble: slår H0 V3 + X båda komponenterna?
Endast familjer med `INCREMENTAL_OVER_H0`. **Låst metod:** rank average
`0,5 × pct(H0 V3 score) + 0,5 × pct(X score)`, Top-30. Vikten speglar H0 V3:s egen
0,5/0,5-konstruktion och är parameterfri. Ingen viktoptimering, inget grid, ingen Kelly, ingen
post-hoc-vikt, ingen stacking.

**H0 V3 + ExtraTrees ingår som kandidat** men får ingen gynnad behandling. De historiska
+9,97 pp och +10,42 pp får aldrig användas som tröskel, parameterval eller riktningsförväntan.
De är hypotesgenererande.

---

## MULTIPLICITET

Primär kontroll: **den sekventiella stegen** — endast familjer som passerar en nivå går vidare.
Det minskar multipliciteten och förhindrar ensemble-mining.

Sekundär kontroll: **tvåfönsterkravet** — varje kriterium måste hålla oberoende i båda fönstren
med samma tecken. En familj som passerar i ett fönster räknas som fallen.

Holm-Bonferroni-justerade p-värden över de sex familjerna rapporteras per steg som
transparensmått. De är inte grinden; tvåfönsterkravet är grinden. Samtliga sex redovisas alltid
tillsammans, även de som faller.

`UNDERPOWERED` om det 95-procentiga blockbootstrapintervallet (13-panelsblock, 2000 dragningar)
innehåller både +2,4 och −2,4 pp — oavsett punktskattning.

---

## CHAMPION-GATE

Tillåtna slutdomar: **A** H0_V3_REMAINS_GLOBAL_CHAMPION · **B** MODEL_X_REPLACES_H0_GLOBAL ·
**C** H0_PLUS_MODEL_X_GLOBAL_CHAMPION · **D** MULTIPLE_ARCHITECTURES_UNRESOLVED ·
**E** NO_MODEL_MEETS_ROBUSTNESS_GATE.

Default är **A**: om ingen familj passerar något steg står H0 V3 kvar som identifierad global
champion, och racet har då gett ett positivt besked om H0 V3. **E** används bara när någon familj
passerar delvis men ingen uppfyller robusthetskraven, så att arkitekturen förblir oidentifierad.

Först när en global arkitektur är identifierad får conditional research licensieras.

---

## KOSTNADER

20 bp per envägs viktomsättning — identisk med H0 V3:s frysta modell. Känslighet redovisas vid
10 och 40 bp. **Inga kostnadsundantag.** ExtraTrees historiska +40 % turnover ska synas fullt ut.
Nasdaqs spread- och likviditetsdata får inte användas för en optimerad exekveringsmodell här.

---

## FÖRBJUDET TILLS RACET ÄR KLART

ICB R1–R5 · size replication · Size × ICB · market-cap heterogeneity · liquidity heterogeneity ·
G-HET · G-SIZE-HET · G-HIER · hold/replace · diversification rules · nya exitregler ·
execution optimization · portfolio weighting optimization.

Samtliga ligger downstream från global modellarkitektur.

---

## EXEKVERINGSKRAV

Racet **måste** köras via `tools/revalidation_runner.py` i REVALIDATION-mode. En körning utan
exekveringsmanifest avvisas av `validate_revalidation_run`.

---

## ARTEFAKTER

| Fil | SHA256 |
|---|---|
| `preregistration.json` | `8c301cf82a0c05f4…` |
| `PREREG_FREEZE.json` | `4e2eea2c74643f38…` |
| `model_specifications.json` | `8093dba9dee1b499…` |
| `feature_manifest.json` | `f4bf96e75da10eb0…` |
| `temporal_split.json` | `74ef77762b15571d…` |
| `acceptance_gates.json` | `7fd3595ca9b49f3e…` |
| `input_manifest.json` | `1158fa3744798d43…` — 19 indata, alla hashade |
| `provenance_manifest.json` | `f97947adfd0a6d09…` |
