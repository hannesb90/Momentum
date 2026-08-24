# H0_V3_WINDOW_2_EXTENSION

Datum: 2026-08-19 · Status: **GENOMFÖRD**
Preregistrering SHA256: `52c222b2a4bb7896826018292158e451c8980bb999022f35a75fa5e8a968d543`
Låst **före** någon fönster-2-avkastning beräknades.

H0 V3:s original är orört. Inga ML-modeller tränade. Inga parametrar optimerade.

---

## GENOMFÖRANDEORDNING

1. Pre-flight PASS — H0 V3:s frysning, indata, implementation, eligibility och fönster-1-facit (79 paneler, CAGR 26,61 %) verifierade
2. Extension-runner byggd
3. **Negativ kontroll på fönster 1 — bitidentisk**
4. Preregistrering låst
5. Fönster 2 kört
6. PIT-kontroll PASS
7. Reproduktionskontroll PASS

---

## IMPLEMENTATION — INGEN H0-LOGIK DUPLICERAD

`tools/h0_v3_window2_kor.py` importerar `tools/h0_v3_kor.py` och anropar dess `main()`
oförändrad. AST-kontroll: extensionen definierar tre funktioner (`sha`, `bygg_isin_hint`,
`kor`) och innehåller **noll** förekomster av signal-, ranking-, momentum- eller portföljkod.

Fyra modulattribut patchas: `PREREG`, `FREEZE`, `OUT`, `_ISIN`. Prisfilens sökväg är hårdkodad
*inuti* `main()` och kan inte nås som modulkonstant — den omdirigeras via
`revalidation_sandbox`, samma mekanism som redan används i `revalidation_runner`. Den frysta
filen ändras inte.

**Kosmetisk avvikelse:** den frysta modulens utskrift säger *"H0 2014-2019"* även i fönster 2.
Strängen är hårdkodad i `print()`. Den påverkar ingen beräkning och får inte ändras.

---

## NEGATIV KONTROLL — BITIDENTISK

Extension-runnern kördes på fönster 1 och jämfördes mot den frysta artefakten.
**0 avvikelser** utöver `run_utc`.

| Krav | Fryst | Kontroll |
|---|---|---|
| Paneler | 79 | 79 |
| CAGR | 26,61 % | 26,61 % |
| MaxDD | −13,08 % | −13,08 % |
| Vol | 14,11 % | 14,11 % |
| Sharpe | 1,7273 | 1,7273 |
| Benchmark CAGR | 18,70 % | 18,70 % |
| Excess | +7,91 % | +7,91 % |
| KI | [+4,34 %, +13,78 %] | identisk |
| t | 2,395 | 2,395 |
| Dom | STÖD | STÖD |
| **Nettoserie H0, 79 värden** | — | **identisk** |
| **Nettoserie universum** | — | **identisk** |

---

## VAD SOM ÄNDRADES — OCH INTE

**Enda tillåtna förändring: `ONLY_TEMPORAL_WINDOW_EXTENSION`.**

Låst och oförändrat: signal, momentumdefinition, lookbacks, ranking, Top-N, rebalanscadens,
viktning (invers vol^1,5), SMA200-grind, bekräftelsemultiplikator, vikttak, eligibility-semantik,
PIT-medlemskap, identitetshantering, avnoteringshantering, missing-data, kostnader, benchmark,
portföljkonstruktion. `specifikation` är ordagrant kopierad ur fönster 1:s preregistrering.

### Prislagret — en avvikelse jag måste redovisa öppet

Valt: `validated/prices/prices_validated.json`.

Fönster 1 använde det kanoniska H0-prislagret för sin period. Den strikta 2020–2026-analogen är
det kanoniska H0-lagret för den perioden — samma lager som projektets övriga 2020–2026-forskning.
Att i stället välja det reparerade v4-lagret hade ändrat **två** saker, fönster *och* prislager,
och därmed brutit `ONLY_TEMPORAL_WINDOW_EXTENSION`.

`REP_MODEL_RACE_H0V3/temporal_split.json` anger `prices_adjustment_repair_v4` för fönster 2 och
`prices_h1419_gated` för fönster 1. **Båda avviker från vad H0 V3 faktiskt använder.** De fälten
beskriver vilket lager *modellracet* ska beräkna features ur, inte vilket lager H0 V3-baslinjen
vilar på. Baslinjen måste vara internt konsistent med sig själv över båda fönstren.

**Känd defektexponering:** lagret innehåller de åtta oåtgärdade justeringsbrotten. Jag mätte
deras faktiska genomslag: **VBG-B ligger i Top-30 i fyra paneler** (2020-03-26, 2020-04-23,
2020-05-21, 2020-06-18) inom åtta veckor från sitt brott 2020-04-29, vars spuriösa faktorkvot är
1,534062. Övriga sju brottsinstrument förekommer inte i Top-30 nära sina brottsdatum.

Det innebär att fönster 2:s resultat bär en känd, kvantifierad kontaminering i fyra av 86 paneler.
Den får inte åtgärdas här — det vore en dataändring utöver fönsterbytet.

---

## PIT-KONTROLL — PASS

86 paneler, 30 416 kandidatrader, **28 229 eligible (92,81 %)**.

| Orsak | Antal |
|---|---|
| MEMBER_VIA_ORDERBOOK | 27 570 |
| PRE_LISTING (avvisad) | 1 965 |
| MEMBER_VIA_ISIN_KEDJA | 640 |
| CONFIRMED_CODE_REUSE (avvisad) | 172 |
| UNRESOLVED | 41 |
| MEMBER_VIA_ISIN_DIREKT | 19 |
| POST_DELISTING (avvisad) | 9 |

| Krav | Utfall |
|---|---|
| **INVALID TOP30** | **0** |
| **LOOK-AHEAD VIOLATIONS** | **0** |
| non-STO inclusions | 0 |

Verifierat per beslutsdatum: källmånaden är strikt före beslutsmånaden, sista prisobservation
≤ paneldatum, ISIN endast som uppslagsnyckel, pre-listing och post-delisting avvisas,
`terminal_events` används inte, segment endast som Main Market-markör, `known_from`-regeln
inbyggd i `kallmanad()`.

---

## FÖNSTER 2 — RESULTAT

| | H0 V3 | Likaviktat universum |
|---|---|---|
| CAGR | **12,99 %** | 7,46 % |
| Vol | 19,68 % | 20,64 % |
| MaxDD | −27,42 % | −34,81 % |
| Sharpe | 0,546 | 0,253 |

**Excess CAGR +5,53 %** · KI [+0,26 %, +11,51 %] · t 1,14 · 97,9 % positiva bootstraps ·
**DOM: STÖD**

86 paneler, medelinnehav 26,8.

### Hur detta ska läsas

Fönster 2 är **väsentligt svagare** än fönster 1: CAGR 12,99 % mot 26,61 %, Sharpe 0,55 mot 1,73,
MaxDD −27,4 % mot −13,1 %. Excess är +5,53 pp mot +7,91 pp, och konfidensintervallets nedre gräns
ligger på +0,26 pp — knappt över noll. t-värdet 1,14 når inte konventionell signifikans; domen
STÖD följer av att bootstrapintervallet inte omsluter noll, vilket är den preregistrerade regeln.

Detta rapporteras och **ingenting ändras**. H0 V3 får ingen ny modellstatus av att fönster 2 körs.
Att fönstret nu är känt som det saknade fönstret gör det särskilt viktigt att det inte tillåts
påverka någon design.

---

## STATUSSEMANTIK

`H0 V3` = **FROZEN PIT-correct baseline** — oförändrad.
`H0_V3_WINDOW_2_EXTENSION` = **kompletterande benchmark-evidens**.

---

## REPRODUCERBARHET

Två oberoende körningar, bitvis jämförelse: **0 avvikelser** utöver `run_utc`, nettoserien
identisk. Full determinism — bootstrap använder `np.random.default_rng(20260815)` ur den frysta
modulen, ingen modellträning, ingen bibliotekso-determinism.

---

## MODELLRACETS BLOCKERARE

`REP_MODEL_RACE_H0V3` kräver H0 V3-baslinje i båda fönstren. Nu finns:

- Fönster 1: `research_k/h0_v3/h0_v3_RESULTAT.json` — 79 paneler
- Fönster 2: `research_k/h0_v3_window2/result.json` — 86 paneler

Modellracets preregistrering är **oförändrad**, sha `8c301cf82a0c05f4…`.

---

## ARTEFAKTER

`research_k/h0_v3_window2/` — `preregistration.json` `52c222b2a4bb7896…` ·
`PREREG_FREEZE.json` · `result.json` `870973a784ebe1bf…` · `negative_control.json` ·
`pit_audit.json` · `reproducibility_manifest.json` · `execution_manifest.json` ·
`implementation_manifest.json` · `input_manifest.json` · `temporal_window.json` ·
`provenance_manifest.json` · `adjustment_break_exposure.json`
Kod: `tools/h0_v3_window2_kor.py`
