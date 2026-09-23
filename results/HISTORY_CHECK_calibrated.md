# Pricing check vs real historical SPXW prices (Barchart)

Model evaluated with call-wing multiplier 0.82 and wing vol beta 0.0 (1.0 / 0.0 = the backtest's chain-calibrated pricing).

Contracts: 495 sampled (163 expiries with data), 1697 daily observations from 2023-06-05 to 2026-09-17. IV ratio = implied vol of the real closing price / backtest model vol for the same contract and day (1.0 = the backtest's pricing is right).

**Core sample (model delta 3-12%): median IV ratio 1.006 (IQR 0.916-1.101), median price ratio 1.029, n = 634.** Slope of ln(ratio) on ATM vol: -0.71 per 1.00 of vol.

## By days to expiry (core)

|   dte |   n |   median IV ratio |   IQR low |   IQR high |   median price ratio |
|------:|----:|------------------:|----------:|-----------:|---------------------:|
|     1 |  28 |             1.134 |     1.045 |      1.275 |                1.732 |
|     2 |  63 |             1.004 |     0.963 |      1.14  |                1.019 |
|     3 | 108 |             1.031 |     0.914 |      1.131 |                1.159 |
|     4 | 171 |             0.99  |     0.92  |      1.104 |                0.954 |
|     5 | 264 |             0.989 |     0.906 |      1.07  |                0.947 |

## By model delta (all observations)

| model_delta   |   n |   median IV ratio |   IQR low |   IQR high |   median price ratio |
|:--------------|----:|------------------:|----------:|-----------:|---------------------:|
| (0.0, 0.025]  | 809 |             1.006 |     0.921 |      1.087 |                1.056 |
| (0.025, 0.05] | 393 |             0.986 |     0.9   |      1.093 |                0.924 |
| (0.05, 0.075] | 240 |             1.011 |     0.929 |      1.096 |                1.05  |
| (0.075, 0.1]  |  54 |             1.057 |     0.962 |      1.14  |                1.245 |
| (0.1, 0.15]   |  53 |             1.065 |     0.976 |      1.126 |                1.223 |
| (0.15, 0.3]   |  84 |             1.013 |     0.925 |      1.079 |                1.032 |
| (0.3, 1.0]    |  64 |             0.992 |     0.917 |      1.133 |                0.994 |

## By vol regime (core)

| atm       |   n |   median IV ratio |   IQR low |   IQR high |   median price ratio |
|:----------|----:|------------------:|----------:|-----------:|---------------------:|
| (0, 10]   | 166 |             1.068 |     0.981 |      1.155 |                1.356 |
| (10, 12]  | 183 |             1.043 |     0.952 |      1.123 |                1.221 |
| (12, 14]  | 126 |             0.977 |     0.887 |      1.043 |                0.906 |
| (14, 17]  |  85 |             0.937 |     0.87  |      1.021 |                0.7   |
| (17, 25]  |  61 |             0.927 |     0.804 |      0.989 |                0.654 |
| (25, 100] |  13 |             1.034 |     0.947 |      1.079 |                1.187 |

## By half-year (core)

| date   |   n |   median IV ratio |   IQR low |   IQR high |   median price ratio |
|:-------|----:|------------------:|----------:|-----------:|---------------------:|
| 2023H1 |  20 |             1.153 |     1.092 |      1.203 |                1.809 |
| 2023H2 |  97 |             1.112 |     1.033 |      1.154 |                1.609 |
| 2024H1 | 123 |             1.083 |     1.009 |      1.131 |                1.411 |
| 2024H2 |  91 |             0.985 |     0.911 |      1.094 |                0.928 |
| 2025H1 |  77 |             0.986 |     0.892 |      1.067 |                0.929 |
| 2025H2 | 123 |             0.941 |     0.891 |      0.985 |                0.733 |
| 2026H1 |  77 |             0.884 |     0.788 |      0.978 |                0.51  |
| 2026H2 |  26 |             0.984 |     0.833 |      1.041 |                0.917 |

## Across a weekend or not (core)

|   weekend |   n |   median IV ratio |   IQR low |   IQR high |   median price ratio |
|----------:|----:|------------------:|----------:|-----------:|---------------------:|
|         0 | 162 |             1.064 |     0.939 |      1.171 |                1.324 |
|         1 | 472 |             0.992 |     0.913 |      1.083 |                0.968 |

## Real-price mini-backtest (sell at 5DTE close, daily close delta hedge, hold to expiry)

Same contracts sold at the real closing price vs at the model price (both less a 3% half-spread, min 0.025). One expiry every 5 trading days, strikes at 5, 7.5, 10 delta; P&L in bp of the notional.

|                                  |     real |    model |
|:---------------------------------|---------:|---------:|
| contracts                        |  372     |  372     |
| avg premium (bp)                 |    2.688 |    2.904 |
| avg payoff (bp)                  |    3.686 |    3.686 |
| avg P&L hedged (bp)              |    1.348 |    1.609 |
| hit rate                         |    0.634 |    0.642 |
| Sharpe (per-expiry series, ann.) |    0.872 |    1.281 |
| worst expiry (bp)                | -161.963 | -113.078 |

By target delta (averages, bp):

|   target |   prem_real_bp |   prem_model_bp |   payoff_bp |   pnl_real_bp |   pnl_model_bp |
|---------:|---------------:|----------------:|------------:|--------------:|---------------:|
|    0.05  |          1.096 |           1.433 |       0.551 |         2.124 |          2.373 |
|    0.075 |          2.387 |           2.666 |       2.741 |         1.407 |          1.869 |
|    0.1   |          4.195 |           4.261 |       6.971 |         0.692 |          0.782 |
