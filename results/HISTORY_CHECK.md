# Pricing check vs real historical SPXW prices (Barchart)

Model evaluated with call-wing multiplier 1.0 and wing vol beta 0.0 (1.0 / 0.0 = the backtest's chain-calibrated pricing).

Contracts: 495 sampled (163 expiries with data), 1697 daily observations from 2023-06-05 to 2026-09-17. IV ratio = implied vol of the real closing price / backtest model vol for the same contract and day (1.0 = the backtest's pricing is right).

**Core sample (model delta 3-12%): median IV ratio 0.803 (IQR 0.735-0.880), median price ratio 0.327, n = 1053.** Slope of ln(ratio) on ATM vol: -0.62 per 1.00 of vol.

## By days to expiry (core)

|   dte |   n |   median IV ratio |   IQR low |   IQR high |   median price ratio |
|------:|----:|------------------:|----------:|-----------:|---------------------:|
|     1 |  55 |             0.898 |     0.835 |      0.957 |                0.58  |
|     2 | 122 |             0.817 |     0.751 |      0.911 |                0.358 |
|     3 | 205 |             0.797 |     0.73  |      0.878 |                0.294 |
|     4 | 299 |             0.785 |     0.722 |      0.859 |                0.268 |
|     5 | 372 |             0.803 |     0.731 |      0.869 |                0.345 |

## By model delta (all observations)

| model_delta   |   n |   median IV ratio |   IQR low |   IQR high |   median price ratio |
|:--------------|----:|------------------:|----------:|-----------:|---------------------:|
| (0.0, 0.025]  | 303 |             0.871 |     0.822 |      0.922 |                0.317 |
| (0.025, 0.05] | 365 |             0.786 |     0.733 |      0.859 |                0.205 |
| (0.05, 0.075] | 328 |             0.794 |     0.728 |      0.873 |                0.288 |
| (0.075, 0.1]  | 252 |             0.812 |     0.743 |      0.899 |                0.385 |
| (0.1, 0.15]   | 270 |             0.837 |     0.773 |      0.921 |                0.512 |
| (0.15, 0.3]   | 109 |             0.905 |     0.831 |      0.963 |                0.782 |
| (0.3, 1.0]    |  70 |             0.969 |     0.889 |      1.107 |                0.965 |

## By vol regime (core)

| atm       |   n |   median IV ratio |   IQR low |   IQR high |   median price ratio |
|:----------|----:|------------------:|----------:|-----------:|---------------------:|
| (0, 10]   | 258 |             0.861 |     0.795 |      0.93  |                0.475 |
| (10, 12]  | 301 |             0.827 |     0.749 |      0.905 |                0.374 |
| (12, 14]  | 203 |             0.773 |     0.709 |      0.834 |                0.272 |
| (14, 17]  | 156 |             0.755 |     0.713 |      0.816 |                0.219 |
| (17, 25]  | 115 |             0.752 |     0.66  |      0.81  |                0.201 |
| (25, 100] |  20 |             0.797 |     0.726 |      0.844 |                0.326 |

## By half-year (core)

| date   |   n |   median IV ratio |   IQR low |   IQR high |   median price ratio |
|:-------|----:|------------------:|----------:|-----------:|---------------------:|
| 2023H1 |  30 |             0.929 |     0.871 |      0.964 |                0.715 |
| 2023H2 | 173 |             0.861 |     0.807 |      0.928 |                0.5   |
| 2024H1 | 175 |             0.873 |     0.825 |      0.926 |                0.529 |
| 2024H2 | 152 |             0.8   |     0.72  |      0.875 |                0.327 |
| 2025H1 | 140 |             0.77  |     0.724 |      0.84  |                0.258 |
| 2025H2 | 186 |             0.75  |     0.715 |      0.803 |                0.228 |
| 2026H1 | 144 |             0.724 |     0.651 |      0.77  |                0.14  |
| 2026H2 |  53 |             0.777 |     0.7   |      0.846 |                0.262 |

## Across a weekend or not (core)

|   weekend |   n |   median IV ratio |   IQR low |   IQR high |   median price ratio |
|----------:|----:|------------------:|----------:|-----------:|---------------------:|
|         0 | 299 |             0.835 |     0.747 |      0.933 |                0.379 |
|         1 | 754 |             0.793 |     0.73  |      0.86  |                0.311 |

## Real-price mini-backtest (sell at 5DTE close, daily close delta hedge, hold to expiry)

Same contracts sold at the real closing price vs at the model price (both less a 3% half-spread, min 0.025). One expiry every 5 trading days, strikes at 5, 7.5, 10 delta; P&L in bp of the notional.

|                                  |     real |   model |
|:---------------------------------|---------:|--------:|
| contracts                        |  372     | 372     |
| avg premium (bp)                 |    2.688 |   7.071 |
| avg payoff (bp)                  |    3.686 |   3.686 |
| avg P&L hedged (bp)              |    1.348 |   6.673 |
| hit rate                         |    0.634 |   0.766 |
| Sharpe (per-expiry series, ann.) |    0.872 |   3.795 |
| worst expiry (bp)                | -161.963 | -51.842 |

By target delta (averages, bp):

|   target |   prem_real_bp |   prem_model_bp |   payoff_bp |   pnl_real_bp |   pnl_model_bp |
|---------:|---------------:|----------------:|------------:|--------------:|---------------:|
|    0.05  |          1.096 |           4.338 |       0.551 |         2.124 |          6.22  |
|    0.075 |          2.387 |           6.753 |       2.741 |         1.407 |          6.573 |
|    0.1   |          4.195 |           9.481 |       6.971 |         0.692 |          7.114 |
