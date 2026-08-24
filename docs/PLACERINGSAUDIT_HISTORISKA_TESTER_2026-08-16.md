# Placeringsaudit av historiska V2-tester

Datum: 2026-08-16. Utlöst av skillnaden mellan lönsamhetsgrinden före
hysteres och portföljkvoten efter hysteres i Steg 4 av
`SEGMENT_HORISONT_DIAGNOSTIK.md`.

## Fråga

Kan ett redan förkastat eller accepterat V2-resultat bero på att regeln låg på
fel sida om hysteresen i stället för på mekanismen? Auditens princip är att
bara testa en alternativ placering när den fortfarande uttrycker **samma
ekonomiska hypotes**. En post-hysteres-exit är exempelvis inte automatiskt
samma regel som att exkludera ett namn ur kandidatlistan före urval.

## Kontroll av den gemensamma motorn

`tools/stack_h_motor.py` har den kanoniska ordningen:

1. Hysteres: tidigare innehav med rank högst 35 behålls.
2. Påfyllnad från ranklistan till 30 namn.
3. SMA-/handlingsbarhetsfilter på det valda innehavet.
4. ERC, FR, vikttak, NTZ och kostnad.

En testfil ska därför redovisa om dess regel ändrar kandidatlistan före steg
1, själva innehavet efter steg 2, eller endast vikter/kalender.

## Resultat

| Testfamilj | Regelplacering i faktisk V2-körning | Dom | Åtgärd |
|---|---|---|---|
| Lönsamhet: grind | Kandidatfilter före hysteres och påfyllnad | Jämförbar pre-urvalsform | Klar; redan körd mot efter-urvalsformen. |
| Lönsamhet: kvot | Tvingat byte efter hysteres/påfyllnad | Jämförbar post-urvalsform | Klar; visar 12,12 % mot 9,90 % för q=30 respektive grind. |
| SPARF F4 gates | `portfolio()` bildar `eligible`, och både behållna namn och påfyllnad måste klara grinden | Redan före hysteres | Ingen omkörning. |
| SPARF F7 trend-/momentum-/drawdown-gates | Samma `gate`-väg som F4 | Redan före hysteres | Ingen omkörning. |
| SPARF F7 rank-exit | Ändrar hysteresbufferten (`buffer=45`) | Hysteresregel, inte kandidatfilter | Ingen meningsfull "före"-variant; ingen omkörning. |
| SPARI Batch 1: signalblend | Ändrar score före rangordning | Före urval per konstruktion | Ingen omkörning. |
| SPARI Batch 1: inverse-vol/target-vol | Håller urvalet konstant och ändrar bara vikter/exponering | Ej urvalskänslig | Ingen omkörning. |
| SPARI Batch 2: DD20, milstolpe, tidsstopp, re-entry | Path-beroende åtgärd på redan ägda namn | En förhandsgrind skulle vara en annan hypotes | Ingen omkörning; status oförändrad. |
| A1 rebalansfrekvens och A2 kohorter | Ändrar kalender, inte kandidatregeln | Ej urvalskänslig | Ingen omkörning. |
| A3 poängutjämning | Ändrar score före rangordning | Före urval per konstruktion | Ingen omkörning. |
| A4 opportunity-cost-byte | Byte efter urval, även mellan rebalanseringar | Efter-urvalsbyte är själva hypotesen | Ingen omkörning. |
| Köpband | Begränsar rekrytering/påfyllnad men låter redan behållna innehav ligga kvar | Hypotesen säger uttryckligen "rekrytera nya innehav" | Ingen omkörning; en hård pre-hysteresgrind vore en separat regel. |
| Topp-5-spärr/re-entry-spärr | Villkor på ett namns tidigare innehavshistorik | Path-beroende innehavsregel | Ingen omkörning. |

## Slutsats

Ingen historisk V2-dom ändras och ingen bred omkörning är motiverad. Det enda
fall där samma ekonomiska villkor rimligen hade två placeringar — lönsamhet —
är redan prövat i båda formerna.

Den nya permanenta kontrollen är i stället: varje ny regel som kan uttryckas
både som kandidatfilter och som portföljtvång ska preregistrera placeringen.
Om båda fortfarande representerar samma ekonomiska hypotes ska båda köras,
redovisas separat och ingen bättre variant väljas efter resultatet.

## Avgränsning

Auditen gäller V2:s aktuella, dokumenterade tester. `momentum_prod_work` är
legacy och dess resultat är redan ersatta av V2 på grund av kända data- och
exekveringsbrister; de återupplivas inte genom denna audit.
