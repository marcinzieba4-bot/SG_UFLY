# Pricing check vs real historical SPXW prices (Barchart)

Model evaluated with call-wing multiplier 0.82 and wing vol beta 0.0 (1.0 / 0.0 = the backtest's chain-calibrated pricing).

Contracts: 328 sampled (82 expiries with data), 2121 daily observations from 2023-06-05 to 2026-09-10. IV ratio = implied vol of the real closing price / backtest model vol for the same contract and day (1.0 = the backtest's pricing is right).

**Core sample (model delta 3-40%): median IV ratio 1.021 (IQR 0.950-1.096), median price ratio 1.057, n = 1234.** Slope of ln(ratio) on ATM vol: -0.81 per 1.00 of vol.

## By days to expiry (core)

|   dte |   n |   median IV ratio |   IQR low |   IQR high |   median price ratio |
|------:|----:|------------------:|----------:|-----------:|---------------------:|
|     1 |  41 |             1.096 |     1.034 |      1.231 |                1.349 |
|     2 |  65 |             1.037 |     0.938 |      1.17  |                1.107 |
|     3 |  88 |             1.035 |     0.965 |      1.11  |                1.09  |
|     4 | 117 |             1.021 |     0.946 |      1.086 |                1.057 |
|     5 | 141 |             1.003 |     0.926 |      1.074 |                1.011 |
|     6 | 158 |             1.013 |     0.949 |      1.059 |                1.032 |
|     7 | 153 |             1.015 |     0.95  |      1.096 |                1.036 |
|     8 | 148 |             1.04  |     0.957 |      1.091 |                1.086 |
|     9 | 155 |             1.027 |     0.95  |      1.097 |                1.076 |
|    10 | 168 |             1.018 |     0.965 |      1.093 |                1.039 |

## By model delta (all observations)

| model_delta   |   n |   median IV ratio |   IQR low |   IQR high |   median price ratio |
|:--------------|----:|------------------:|----------:|-----------:|---------------------:|
| (0.0, 0.025]  | 466 |             1.004 |     0.924 |      1.091 |                1.029 |
| (0.025, 0.05] | 244 |             1     |     0.914 |      1.1   |                1     |
| (0.05, 0.075] | 175 |             1.005 |     0.906 |      1.103 |                1.022 |
| (0.075, 0.1]  |  97 |             1.039 |     0.933 |      1.127 |                1.158 |
| (0.1, 0.15]   | 163 |             1.019 |     0.964 |      1.091 |                1.064 |
| (0.15, 0.3]   | 419 |             1.028 |     0.967 |      1.093 |                1.064 |
| (0.3, 1.0]    | 557 |             1.008 |     0.944 |      1.08  |                1.007 |

## By vol regime (core)

| atm       |   n |   median IV ratio |   IQR low |   IQR high |   median price ratio |
|:----------|----:|------------------:|----------:|-----------:|---------------------:|
| (0, 10]   | 253 |             1.091 |     1.033 |      1.166 |                1.273 |
| (10, 12]  | 402 |             1.045 |     0.985 |      1.105 |                1.12  |
| (12, 14]  | 259 |             0.989 |     0.931 |      1.045 |                0.977 |
| (14, 17]  | 164 |             0.968 |     0.899 |      1.025 |                0.916 |
| (17, 25]  | 125 |             0.968 |     0.876 |      1.027 |                0.907 |
| (25, 100] |  31 |             0.926 |     0.855 |      1.007 |                0.88  |

## By half-year (core)

| date   |   n |   median IV ratio |   IQR low |   IQR high |   median price ratio |
|:-------|----:|------------------:|----------:|-----------:|---------------------:|
| 2023H1 |  37 |             1.117 |     1.05  |      1.168 |                1.336 |
| 2023H2 | 190 |             1.069 |     1.019 |      1.124 |                1.19  |
| 2024H1 | 205 |             1.085 |     1.034 |      1.157 |                1.25  |
| 2024H2 | 164 |             1.065 |     0.977 |      1.162 |                1.185 |
| 2025H1 | 169 |             0.966 |     0.907 |      1.022 |                0.909 |
| 2025H2 | 229 |             0.997 |     0.947 |      1.046 |                0.99  |
| 2026H1 | 173 |             0.924 |     0.839 |      0.998 |                0.829 |
| 2026H2 |  67 |             1     |     0.926 |      1.041 |                1.001 |

## Across a weekend or not (core)

|   weekend |    n |   median IV ratio |   IQR low |   IQR high |   median price ratio |
|----------:|-----:|------------------:|----------:|-----------:|---------------------:|
|         0 |  152 |             1.072 |     0.968 |      1.207 |                1.216 |
|         1 | 1082 |             1.016 |     0.948 |      1.086 |                1.044 |

## Real-price mini-backtest (sell at 5DTE close, daily close delta hedge, hold to expiry)

Same contracts sold at the real closing price vs at the model price (both less a 3% half-spread, min 0.025). One expiry every 10 trading days, strikes at 5, 10, 20, 30 delta; P&L in bp of the notional.

|                                  |     real |    model |
|:---------------------------------|---------:|---------:|
| contracts                        |  194     |  194     |
| avg premium (bp)                 |   27.407 |   26.402 |
| avg payoff (bp)                  |   43.371 |   43.371 |
| avg P&L hedged (bp)              |    6.603 |    5.809 |
| hit rate                         |    0.655 |    0.639 |
| Sharpe (per-expiry series, ann.) |    1.591 |    1.373 |
| worst expiry (bp)                | -183.935 | -119.767 |

By target delta (averages, bp):

|   target |   prem_real_bp |   prem_model_bp |   payoff_bp |   pnl_real_bp |   pnl_model_bp |
|---------:|---------------:|----------------:|------------:|--------------:|---------------:|
|     0.05 |          2.637 |           2.046 |       0     |         1.947 |          0.332 |
|     0.1  |          6.826 |           6.698 |       8.89  |         6.194 |          6.409 |
|     0.2  |         24.068 |          23.483 |      43.682 |         7.916 |          7.207 |
|     0.3  |         50.64  |          48.647 |      77.931 |         7.429 |          6.318 |
