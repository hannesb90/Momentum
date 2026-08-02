# Holdout-status – 2026-08-02

## Beslutsstatus

Den historiska holdouten är forskningsexponerad och får inte användas som nytt
adoptionsbevis. N3-29 till N3-40 har därför körts utan holdout och samtliga
rapporter anger `holdout_used=false`. Inga av dessa tester har ändrat produktion.

Det genuina framåttestet är N2 Stage-07 och är fryst i
`results/niva2_stages/07_forward_preregistration.json`:

- startdatum: 2026-07-27;
- minsta observationstid: 52 veckor;
- insamling: veckovis och fail-closed;
- status: protokoll fryst, ännu inte validerings-PASS;
- tidigaste ordinarie beslutspunkt: efter minst 52 kompletta veckor, cirka
  2027-07-26, under förutsättning att datainsamlingen är komplett.

## Senaste forskningsankare

N3-36 är det reproducerbara kanoniska forskningsankaret: 13v LambdaRank-target,
52v rotation, seed 42, 21 walk-forward-splits och OOF 2016-03-21–2021-06-07.
Resultat: 22,2% CAGR, 1,61 Sharpe och -18,7% MaxDD mot index-CAGR 15,2%.
Detta är DEV/OOF-forskning, inte ny holdout.

N3-39 bekräftade rankinformation men inte sannolikhetskalibrering. N3-40
bekräftade implementerbarhet vid 100 000 kr men inte generell skalbarhet.
Ingen av slutsatserna ersätter det framåtriktade holdoutprotokollet.

