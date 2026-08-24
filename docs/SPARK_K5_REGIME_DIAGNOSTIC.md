# Spår K5 — Regimdiagnostik av fryst H0

Status: **SLUTFÖRD OCH FRYST**  
Run ID: `K5_REGIME_DIAGNOSTIC_V1`  
Preregistrering SHA256: `f71f91ce53c4ba52d3b58686ad4be20c66de6025b4fd2c759191a05f3c56f70e`

## Slutsats

**Inget preregistrerat regimesamband klassificeras som stabilt.** Två samband är svaga/osäkra och fyra har otillräcklig data. Ingen gate, exposure-scaling, parameterändring eller challenger har skapats.

H0:s rankings, holdings och avkastningar ändrades aldrig. Regimerna grupperar endast redan frysta H0-observationer. Target användes enbart i efterhandsberäkningen av IC.

## IC-resultat

| Regim | Tillstånd | Paneldatum | Mean IC52 | Median IC52 | Top-30 IC | Positiv IC | Klassificering |
|---|---|---:|---:|---:|---:|---:|---|
| Marknadstrend 6m | Positiv | 16 | 0,1594 | 0,1669 | −0,0392 | 100 % | OTILLRÄCKLIG DATA |
|  | Negativ | 4 | 0,1396 | 0,1463 | +0,0317 | 100 % |  |
| Marknadsvolatilitet 3m | Låg | 17 | 0,1619 | 0,1679 | −0,0476 | 100 % | OTILLRÄCKLIG DATA |
|  | Hög | 3 | 0,1190 | 0,1020 | +0,1026 | 100 % |  |
| Market breadth 6m | Bred | 12 | 0,1663 | 0,1746 | −0,0288 | 100 % | **SVAGT/OSÄKERT** |
|  | Smal | 8 | 0,1393 | 0,1471 | −0,0194 | 100 % |  |
| Styrränteförändring 6m | Ej stigande | 17 | 0,1405 | 0,1484 | −0,0421 | 100 % | OTILLRÄCKLIG DATA |
|  | Stigande | 3 | 0,2404 | 0,2596 | +0,0716 | 100 % |  |
| Yield curve 10Y−2Y | Positiv | 12 | 0,1257 | 0,1313 | −0,0372 | 100 % | **SVAGT/OSÄKERT** |
|  | Inverterad | 8 | 0,2001 | 0,1985 | −0,0068 | 100 % |  |
| VIX | Normal | 19 | 0,1592 | 0,1660 | −0,0400 | 100 % | OTILLRÄCKLIG DATA |
|  | Stress ≥25 | 1 | 0,0841 | 0,0841 | +0,2601 | 100 % |  |

### Breadth

Bred marknad hade +0,0269 högre mean IC än smal marknad. Sambandet passerar inte den preregistrerade effektgränsen +0,03, Top-30 IC är något sämre i bred regim och första kronologiska halvan saknar båda tillstånd. Det är därför inte tidsstabilt belagt.

Den befintliga H0-portföljen hade diagnostiskt excess-CAGR 20,29 % i breda perioder och 9,61 % i smala perioder. Detta är 14 respektive 12 icke-oberoende perioder och får inte användas som gatebevis. Top-3 stod för 36,2 % respektive 67,3 % av aritmetiskt bidrag.

### Yield curve

Resultatet går **mot** den preregistrerade riktningen: inverterad kurva hade mean IC 0,2001 mot 0,1257 för positiv kurva. Skillnaden är inte tidsstabil — den ena kronologiska halvan saknar båda tillstånd — och portföljmåtten ger inte en entydig bild. Ingen ny hypotes eller omvänd gate skapas ex post.

### Övriga regimer

Negativ marknadstrend har 4 IC-datum, hög volatilitet 3, stigande ränta 3 och VIX-stress 1. De observerade skillnaderna redovisas men är metodiskt otillräckliga. Ingen av dem får omklassificeras efter tecknet på fullsample-resultatet.

## Övergångar

Övergångsräkningar finns maskinläsbart. Inget transitionpar hade tillräckligt balanserade observationer för ett separat stabilitetspåstående. Inga övergångsregler byggdes.

## Beslut

- `market_breadth_6m`: **SVAGT/OSÄKERT SAMBAND** — värd att följa i ny untouched data, inte värd en gatepreregistrering nu.
- `yield_curve_10y_2y`: **SVAGT/OSÄKERT SAMBAND** — motsatt hypotesriktning och instabilt; ingen gate.
- Övriga fyra: **OTILLRÄCKLIG DATA**.
- **STABILT DIAGNOSTISKT SAMBAND: 0/6.**

## Artefakter

- `research_k/results/K5_REGIME_DIAGNOSTIC_V1/regime_results.json`
- `research_k/results/K5_REGIME_DIAGNOSTIC_V1/run_provenance.json`
- `research_k/results/K5_REGIME_DIAGNOSTIC_V1/manifest.json`

Manifest SHA256: `9447684351c0cde761e2ef1b7e0686a900c34e76c0f1e175f653079ce37d9494`.

