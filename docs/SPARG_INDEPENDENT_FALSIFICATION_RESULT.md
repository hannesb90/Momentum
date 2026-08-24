# Spår G — oberoende validering och falsifiering

Slutklassificering: **D) DATA-/IMPLEMENTATIONSBLOCKERARE**  
Status: **STOPPAD ENLIGT G0**  
Champion ändrad: **nej**  
F/D/A/B/C/E ändrade: **nej**

## Slutsats

Spår F:s rapporterade 25,4 % netto-CAGR, Sharpe 1,146 och MaxDD -4,3 % kan inte valideras. Portföljurvalet använder tillgängligheten av den framtida 52-veckorstargeten som investerbarhetsfilter. Instrument som senare saknar en vanlig forward-52w-label — framför allt framtida terminalinstrument — tas bort innan momentumranking och top-30-val.

Detta är look-ahead och survivorship i själva backtestuniversumet. Spår G stoppas utan reparation.

## Konkret kodbevis

`tools/spard_neutral_race.py:41-50` bygger analysdatan. På rad 47 sker:

```python
if t["target_fwd52w"] is None:
    continue
```

`tools/sparf_systematic_momentum.py:8` importerar denna `load_data`. Rankings och innehav skapas därefter enbart från de överlevande raderna (`tools/sparf_systematic_momentum.py:35-49`). Samma filtrerade rader används för benchmark.

Targettillgänglighet är legitim för IC-utvärdering men får inte avgöra vilka aktier som var investerbara vid beslutstidpunkten.

## Omfattning

På de 20 historiska OOS-paneldatum som Spår F använder:

- Fryst CORE innehåller 7 016 investerbarhetsrader.
- Spår F skapar 6 781 championprediktioner.
- 235 rader, 3,35 %, tas bort därför att framtida `target_fwd52w` är null.
- 231 av de 235 raderna gäller verifierade terminalinstrument.
- 24 terminalinstrument påverkas.
- Fullt tidsenligt universum skulle ändra top-30 på 7 av championens 10 faktiska 8-veckorsrebalancedatum.

Påverkade rebalancedatum och framtidsfiltrerade top-30-kandidater:

| Rebalancedatum | Borttagna framtida terminalinstrument |
|---|---|
| 2024-01-26 | CCOR-B |
| 2024-07-12 | CALTX |
| 2024-09-06 | CALTX |
| 2024-12-27 | DORO, ABLI, PROB |
| 2025-02-21 | ABLI, DORO |
| 2025-04-18 | DORO |
| 2025-06-13 | CS, DORO |

Ett särskilt tydligt exempel är DORO: bolaget försvinner ur april/juni 2025-rankingen eftersom vanlig 52v-target saknas inför den verifierade avnoteringen 2025-12-17. Den framtida händelsen påverkar alltså ett tidigare innehavsbeslut.

## Downstream-effekt

Felet påverkar:

1. championens rankings och innehav,
2. turnover och kostnader,
3. portföljavkastning, drawdown och Sharpe,
4. ticker- och sektorkoncentration,
5. benchmark, som använder samma survivor-filtrerade universum,
6. terminaltestet, eftersom flera terminalinstrument aldrig tillåts komma in i portföljen.

Den befintliga terminalhanteringen i `price_returns()` räcker inte: den kan bara hantera instrument som först har tillåtits in i ranking-/innehavsuniversumet.

Felet finns även i F1-referensen och Spår D:s portföljjämförelser, eftersom samma `load_data` används. IC-beräkningar får fortsatt kräva observerad target, men portföljinnehav måste konstrueras oberoende av framtida labeltillgänglighet.

## G1

F:s frysta predictions- och resultathashar finns och har tidigare reproducerats, men frysningen innehåller ingen separat holdingsartefakt eller holdingshash. G1:s krav på byte-för-byte-jämförelse av frysta innehav kan därför inte uppfyllas.

Detta är sekundärt till den bekräftade universumbuggen men måste åtgärdas i en framtida korrekt rebuild.

## Ej genomförda tester

G2–G11 kördes inte efter blockeraren. Kostnadsstress, rebalancefaser, bootstrap eller ablation på felaktiga innehav skulle ge falsk precision och strida mot G0:s stopregel.

## Vad som måste öppnas

Spår G får inte reparera championen. Följande tidigare resultat måste öppnas och byggas om utanför G:

1. Spår D:s portföljutvärdering och benchmarkuniversum.
2. Spår F:s F1-referens, samtliga challengers, championval och portföljmått.
3. Rankings och holdings måste sparas separat före utfall, med SHA256.
4. Portfolio-universum ska komma från PIT-investerbarhet vid datum T, aldrig från om framtida target senare kan beräknas.
5. Terminalinstrument måste tillåtas väljas och därefter värderas med den verifierade ekonomiska terminalhändelsen.

Först efter denna rebuild kan ett nytt Spår G startas från G0.
