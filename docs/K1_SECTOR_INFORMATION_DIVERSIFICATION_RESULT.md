# K1 — sector information and sector diversification

## Scope and preregistration

K1 was locked before target/results were read. H0/H1/H2 were not changed. Selection used the target-free V4 decision universe and post-decision execution. No ML, grid search, industry-relative test, value data or event data was used.

Information tests used a fixed Top-90 H0 candidate population and a fixed 50/50 rank blend. Sector momentum was the equal-weight sector mean H0 score; sector-relative momentum was stock H0 minus its sector mean; breadth was the share of sector members with positive 12-month momentum.

The diversification rule filled Top 30 in H0 order but, within the next three available H0-ranked candidates, preferred the least represented sector. K1G soft penalty was skipped before results because a defensible non-arbitrary penalty could not be selected without parameter search.

## 1. Sector momentum

Classification: **SVAGT STÖD**, not strong support.

Within the fixed momentum pool, mean IC52 increased by 0.0214, median by 0.0584 and Top-30 IC by 0.0369. Positive-IC share increased by 0.20. The effect failed temporal falsification: ΔIC was −0.0266 in the first chronological half and +0.0694 in the second. The classification was identical after excluding the six manual terminal labels.

The signal is therefore period-dependent evidence, not a basis for a new sector overlay.

## 2. Sector-relative momentum

Classification: **INGET STÖD**.

Δ mean IC52 was −0.0004 (−0.0003 without the manual six). Top-30 ΔIC was slightly positive, but positive-date share fell by 0.05 and the chronological halves had opposite signs (+0.0063, −0.0071).

## 3. Sector breadth

Classification: **INGET STÖD**.

Δ mean IC52 was −0.0125 and Δ Top-30 IC was −0.0674. Chronological effects again reversed (−0.0611, +0.0361). Excluding the manual six did not change the conclusion.

## 4. H0 sector concentration

At H0 rebalances:

- Mean number of represented sectors: 6.77.
- Mean largest-sector weight: 29.49%.
- Mean top-two-sector weight: 51.54%.
- Mean HHI: 0.2056.
- Mean effective number of sectors: 4.93.

The full time path and the worst-period sector contributions are stored machine-readably. Twenty-four terminal instruments participated in the ranked sample and eight were actually held by H0: ABLI, CALTX, CCOR-B, CS, DORO, NPAPER, PROB and RESURS.

## 5. Momentum-preserving sector diversification

Classification under the preregistered rule: **INGET STÖD**.

Historically, the tie-break reduced mean HHI from 0.2056 to 0.1964 (4.49%), raised effective sectors from 4.93 to 5.15, lowered largest-sector weight from 29.49% to 26.92%, and lowered top-two weight from 51.54% to 47.95%. It also happened to improve CAGR from 25.29% to 27.27%, excess Sharpe from 1.379 to 1.488 and MaxDD from −4.43% to −2.94%, with slightly lower turnover.

These attractive figures do not override the preregistration. Required HHI reduction was at least 5%; observed reduction was only 4.49%. The first chronological half also had lower CAGR than H0 (26.12% versus 27.32%), while the second was better. Thus the rule did not meet all precommitted support requirements.

There were 414 substitution decisions across all panel selections. Each choice was confined to the next three available candidates; mean score sacrificed per substitution was 0.01236. Leave-top-3 CAGR was 15.15% for H0 and 17.28% for the diversified diagnostic; leave-top-5 was 10.83% and 11.96%. These diagnostics do not rescue the failed support rule.

The six-manual-label sensitivity produced the same holdings, concentration and classification; only TETY disappeared from the ranked terminal diagnostic and benchmark changed marginally. No manual-label instrument drove the conclusion.

## Reproducibility

Active output: `research_k/results/K1_SECTOR_INFORMATION_DIVERSIFICATION_V2`.

- Preregistration SHA256: `bcf7868ffefd654d4694b712d66509aeef78feb88af950c94db4b0d6731c2319`.
- Result aggregate SHA256: `1e6caf4619529f50a8777cb3081a907f4f665c6a5055a3ed67581b821f74091b`.
- The verifier checks every output byte plus preregistration, sector freeze and H0 rankings.

## Final decisions

**SECTOR TILLFÖR INTE ALPHA.** Sector momentum showed only unstable weak evidence; sector-relative momentum and breadth showed none.

**H0 BÖR FÖRBLI OFÖRÄNDRAD.** The diversification diagnostic was promising historically but failed its preregistered concentration threshold. It is not promoted, and no champion artifact has been changed.

Historical K1 tuning is now closed. The promising but unapproved construction idea is registered separately as `K1_FORWARD_MOMENTUM_PRESERVING_SECTOR_DIVERSIFICATION_V1`; it may only be evaluated as a prospectively sealed challenger on new, previously unseen data. The 5% threshold and all tie-break parameters remain unchanged.
