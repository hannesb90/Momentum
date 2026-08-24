# RESEARCH MASTER INDEX — RESEARCH V TO RESEARCH AF (FINAL SYSTEM DOCUMENTATION)

---

## SYSTEM STATUS & SYSTEM MANIFEST
- **System Lock Timestamp**: 2026-08-10T17:46:37+02:00
- **First Untouched Forward Decision Panel**: **2026-09-04 (Panel #67)**
- **System Freeze Manifest**: `file:///home/hannesb/momentum_v2/research_k/final_system_freeze_manifest.json`
- **SHA256 Manifest Hash**: **`a4266200b32bf4786d6171418083a365d1f1dd6b79f9d001218855007de903d0`**

---

## SUMMARY OF RESEARCH STAGES & FORMAL CLASSIFICATIONS

```
┌───────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                               RESEARCH MASTER INDEX — STAGES V THROUGH AF                                         │
├───────────┬────────────────────────────────────────────────────────┬──────────────────────────────────────────────┤
│ Stage     │ Focus / Topic                                          │ Final Classification / Outcome               │
├───────────┼────────────────────────────────────────────────────────┼──────────────────────────────────────────────┤
│ **V**     │ Portfolio Risk Architecture (Inverse Vol + Target Vol) │ V-A & V-B Forward Challengers Justified      │
│ **V-AUDIT**│ Continuous Risk Plateau & PIT Volatility Audit         │ V-A (InvVol) & V-B (TV15) Validated          │
│ **W**     │ Forward Freeze & Untouched Journaling Protocol         │ SHA256 Locked, Append-Only Journals Created  │
│ **X**     │ Orthogonal Portfolio Improvement Lab (X0-X7)           │ V-A & V-B Remain Champion Controls           │
│ **Y**     │ Capital Deployment & Monthly Contribution Engine       │ SMA Cash Defensive Engine Confirmed (Y1-A)   │
│ **Y-AUDIT**│ Cash Reconciliation & Defensive Holding Durations     │ 100% Cash Attributed, Fractional Drag Identified│
│ **Y-OPS** │ Fractional Drag & T-2 Pre-Funding Operational Audit    │ Integer Share Rounding (0.03% Drag), T-2 Safe│
│ **Z**     │ Model-Risk, Robustness & Block-Bootstrap Audit         │ Platform Immutability Verified (5k Bootstrap)│
│ **AA**    │ Decision Overrides & Trade-Gating Audit               │ Level 1 Implementations Live, Level 2 Shadow │
│ **AB**    │ Exhaustive Decision-Tree & Sidecut Completeness Audit  │ Sidecut Space Exhausted (94.7% Coverage)     │
│ **AC**    │ Fundamental Confirmation Conditional on Momentum       │ Volatility Reduction Identified (34.2% vs 57%)│
│ **AC-AUDIT**│ Delisted Exposure & Survivorship Impact Audit         │ Low/Moderate Survivorship Risk (Directional) │
│ **AD**    │ Fundamental Risk Signal Beyond Inverse Volatility      │ ORTHOGONAL RISK SIGNAL (Beta = -0.0400)      │
│ **AD-VAL**│ Multivariate, OOS Walk-Forward & Exposure Audit       │ AD VALIDATED (OOS Delta MAE = +0.0033)       │
│ **AE**    │ Reopening Previously Blocked Signals (Size, Dilution)  │ Size & Dilution Redundant Against Vol60      │
│ **AE-REC**│ Size & Dilution Mathematical Reconciliation Audit      │ SIZE B (Stat. Incr. / Econ. Redundant)       │
│ **AF**    │ Remaining Orthogonal Signals (Sector, Insider, AF5)    │ NO ADDITIONAL SIGNAL (AD Sole Risk Overlay)  │
└───────────┴────────────────────────────────────────────────────────┴──────────────────────────────────────────────┘
```

---

## THE SIX (6) IMMUTABLE FORWARD MODELS

```
┌──────────────────────────────────────┬────────────────────────────────┬───────────────────────────────────────────┐
│ Model Key                            │ Portfolio Role                 │ Target Specifications                     │
├──────────────────────────────────────┼────────────────────────────────┼───────────────────────────────────────────┤
│ **1. T0_A_CONTROL_H0**               │ Canonical Baseline Control     │ Equal-weight 50/50 12m+18m Momentum Top30 │
│ **2. CONTROL_C_SMA200**              │ Entry-Gated Control            │ H0 + SMA200 SKIP Entry Gate on T Close    │
│ **3. VA_RETURN_CHALLENGER**          │ Champion (Return-Optimized)    │ Control C + Inverse Vol 60d (1-6% caps)   │
│ **4. VB_CAPITAL_PRESERVATION_CHALL** │ Champion (Capital-Preserving)  │ V-A + Target Vol 15%                      │
│ **5. SHADOW_ERC_X2**                 │ Equal Risk Contribution Shadow │ Control C + Equal Risk Contribution 60d   │
│ **6. SHADOW_FUNDAMENTAL_RISK_OVERLAY**│ Orthogonal Risk Overlay Shadow│ V-A + 0.75x Unconfirmed Risk Overlay      │
└──────────────────────────────────────┴────────────────────────────────┴───────────────────────────────────────────┘
```

---

## KEY EMPIRICAL FINDINGS

1. **SMA200 SKIP Gate**: Acts as a primary prognostic risk filter, raising baseline CAGR by **+4.01 pp** (from 7.61% to 11.62%) and lowering MaxDD from -33.81% to -28.75%.
2. **Target Volatility 15% (V-B)**: Halves the Ulcer Index (from 0.137 to **0.064**) and cuts MaxDD to **-17.14%**.
3. **Transaction Cost Robustness**: Break-even one-way transaction cost exceeds **400 bp**, ensuring extreme immunity against trading friction.
4. **Synthetic Tail Risk (5,000 Block-Bootstrap Paths)**: V-B Median MaxDD is **-14.38%** with only a 4.4% probability of MaxDD > 25%.
5. **Execution Efficiency**: Greedy Integer-Share Allocation reduces fractional rounding drag from **3.03% to 0.03%**.
6. **Orthogonal Fundamental Risk Signal**: Fundamental confirmation provides a statistically significant, multivariate-validated reduction in future realized volatility ($\beta = \mathbf{-0.0425}, t = -3.73, p < 0.001$) and improves walk-forward OOS risk forecasting ($\Delta \text{MAE} = \mathbf{+0.00331}$).

---

## FORWARD GOVERNANCE PROTOCOL

- All development on 2021–2026 data is **OFFICIALLY CLOSED AND SEALED**.
- Forward panels execute every 8 weeks starting **2026-09-04**.
- Append-only immutable journals record all forward holdings and trades under `file:///home/hannesb/momentum_v2/journals/`.
- No post-hoc tuning or parameter modifications are permitted under any circumstances.
