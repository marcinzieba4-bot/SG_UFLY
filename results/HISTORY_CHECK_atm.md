# Pricing check vs real historical SPXW prices (Barchart)

Model evaluated with call-wing multiplier 0.82 and wing vol beta 0.0 (1.0 / 0.0 = the backtest's chain-calibrated pricing).

Contracts: 165 sampled (165 expiries with data), 762 daily observations from 2023-06-05 to 2026-09-17. IV ratio = implied vol of the real closing price / backtest model vol for the same contract and day (1.0 = the backtest's pricing is right).

**Core sample (model delta 30-70%): median IV ratio 1.019 (IQR 0.956-1.092), median price ratio 1.018, n = 469.** Slope of ln(ratio) on ATM vol: 0.23 per 1.00 of vol.

## By days to expiry (core)

|   dte |   n |   median IV ratio |   IQR low |   IQR high |   median price ratio |
|------:|----:|------------------:|----------:|-----------:|---------------------:|
|     1 |  40 |             1.157 |     1.018 |      1.274 |                1.1   |
|     2 |  59 |             1.046 |     0.959 |      1.172 |                1.041 |
|     3 |  86 |             1.023 |     0.948 |      1.127 |                1.021 |
|     4 | 121 |             1.024 |     0.956 |      1.092 |                1.023 |
|     5 | 163 |             1.001 |     0.956 |      1.046 |                1.001 |

## By model delta (all observations)

| model_delta   |   n |   median IV ratio |   IQR low |   IQR high |   median price ratio |
|:--------------|----:|------------------:|----------:|-----------:|---------------------:|
| (0.0, 0.025]  |  20 |             1.077 |     1.031 |      1.112 |                1.774 |
| (0.025, 0.05] |  10 |             1.133 |     1.065 |      1.18  |                1.921 |
| (0.05, 0.075] |  13 |             1.233 |     1.123 |      1.27  |                2.263 |
| (0.075, 0.1]  |   5 |             1.156 |     1.144 |      1.285 |                1.742 |
| (0.1, 0.15]   |  21 |             1.181 |     1.111 |      1.262 |                1.678 |
| (0.15, 0.3]   |  72 |             1.097 |     1.028 |      1.219 |                1.245 |
| (0.3, 1.0]    | 621 |             1.014 |     0.939 |      1.102 |                1.011 |

## By vol regime (core)

| atm       |   n |   median IV ratio |   IQR low |   IQR high |   median price ratio |
|:----------|----:|------------------:|----------:|-----------:|---------------------:|
| (0, 10]   | 110 |             1.009 |     0.955 |      1.124 |                1.008 |
| (10, 12]  | 135 |             1.016 |     0.959 |      1.078 |                1.015 |
| (12, 14]  |  90 |             1.007 |     0.942 |      1.078 |                1.007 |
| (14, 17]  |  73 |             1.032 |     0.951 |      1.088 |                1.033 |
| (17, 25]  |  55 |             1.053 |     1.004 |      1.106 |                1.042 |
| (25, 100] |   6 |             1.118 |     1.038 |      1.183 |                1.145 |

## By half-year (core)

| date   |   n |   median IV ratio |   IQR low |   IQR high |   median price ratio |
|:-------|----:|------------------:|----------:|-----------:|---------------------:|
| 2023H1 |  12 |             0.952 |     0.938 |      1.058 |                0.958 |
| 2023H2 |  67 |             1.017 |     0.978 |      1.063 |                1.018 |
| 2024H1 |  68 |             1.022 |     0.965 |      1.163 |                1.019 |
| 2024H2 |  74 |             1.012 |     0.914 |      1.119 |                1.011 |
| 2025H1 |  70 |             1.027 |     0.949 |      1.142 |                1.027 |
| 2025H2 |  73 |             1.034 |     0.981 |      1.097 |                1.03  |
| 2026H1 |  74 |             1.023 |     0.961 |      1.074 |                1.02  |
| 2026H2 |  31 |             0.99  |     0.947 |      1.058 |                0.99  |

## Across a weekend or not (core)

|   weekend |   n |   median IV ratio |   IQR low |   IQR high |   median price ratio |
|----------:|----:|------------------:|----------:|-----------:|---------------------:|
|         0 | 159 |             1.087 |     1.008 |      1.193 |                1.082 |
|         1 | 310 |             1     |     0.948 |      1.052 |                1     |

## Real-price mini-backtest (sell at 5DTE close, daily close delta hedge, hold to expiry)

Same contracts sold at the real closing price vs at the model price (both less a 3% half-spread, min 0.025). One expiry every 5 trading days, strikes at 50 delta; P&L in bp of the notional.

|                                  |     real |    model |
|:---------------------------------|---------:|---------:|
| contracts                        |  163     |  163     |
| avg premium (bp)                 |   76.335 |   76.184 |
| avg payoff (bp)                  |   90.726 |   90.726 |
| avg P&L hedged (bp)              |    3.813 |    3.282 |
| hit rate                         |    0.65  |    0.613 |
| Sharpe (per-expiry series, ann.) |    0.853 |    0.729 |
| worst expiry (bp)                | -127.646 | -176.225 |

By target delta (averages, bp):

|   target |   prem_real_bp |   prem_model_bp |   payoff_bp |   pnl_real_bp |   pnl_model_bp |
|---------:|---------------:|----------------:|------------:|--------------:|---------------:|
|      0.5 |         76.335 |          76.184 |      90.726 |         3.813 |          3.282 |
