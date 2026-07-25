# Villkorade modellager – audit 2026-07-25

Alla lager får endast agera efter att primärmodellen kvalificerat bolaget.
Utveckling sker före 2024; 2024+ används som kontroll. Ingen ändring är live.

| Lager | Villkorat test | Resultat | Beslut |
|---|---|---|---|
| Meta-ranking | Primär topp-20 → sekundär topp-10 | 13v medel 1,97→3,52%, IR 0,52→0,90, hit +0,4pp (104 kontrollveckor) | Shadow |
| Qualified holder | Topp-10 köps alltid; alla trendintakta avhopp hålls 4v som extra innehav | Fast kapital: modern CAGR 3,14→12,13%, Sharpe 0,26→0,81, MaxDD −22,96→−12,39%. Månadssparande: TWR-CAGR 12,29→19,31%, Sharpe 0,72→1,08 | Shadow |
| Fundamenta | Bonus/exit efter primärurval | Isolerad entry-bonus och binär exit försämrade alpha. Modern holder-förbättring har bara ett jämförbart fundamentalutfall | Förkastad för alpha; rådgivande |
| Insyn | Bonus efter primärurval | Isolerad villkorad bonus gav lägre CAGR än baslinjen; 26v-eventedge räcker inte i portfölj | Förkastad |
| Rapport | Feature inom rankmodell/top-20 | Rapportmognad förbättrade modern challenger-CAGR 11,7→16,5%. Smal reaktionsmodell förkastad. 8–28d efter rapport: modern excess +1,03 till +1,90%, men svagt före 2024 | Mognad shadow; offset endast mätning |
| Otto | Blockera karantän endast för trendintakt tidigare innehav med hög egen värdering | Modern Otto-high median −0,4/−1,2/−4,7% vid 13/26/52v mot +3,7/+5,1/+6,5% för ej hög. Ingen användbar pre-2024-täckning | Shadow-blocker |

## Metodanmärkningar

- Meta-skriptet var tidigare okörbart: fundamenta/rapportfeatures kopplades
  inte på och komplett-rad-kravet tömde tvärsnittet. Båda felen är rättade.
- Meta-kontrollen använder den sista DEV-modellen som fryst extrapolering i
  kontrollperioden, samma avsedda arkitektur som det gamla skriptet.
- Negativ rapportoffset (köp före kommande rapport) testas inte mot faktiskt
  framtida publiceringsdatum. Det vore lookahead utan historiska
  rapportkalender-snapshots.
- 2024+-perioden är återanvänd i många experiment. Promotion kräver ny
  framåtblickande shadow-data; historiken räcker bara för kandidatur.

## Prioriterad kombination

1. Primär rank-challenger med rapportmognad.
2. Meta-ranking endast inom dess topp-20.
3. Ordinarie topp-10 köps alltid.
4. Qualified holders får 4v extra plats.
5. Otto-high blockerar endast denna extra karantän.
6. Rapportoffset 8–28d loggas, men påverkar inget förrän liveutfall mognat.
