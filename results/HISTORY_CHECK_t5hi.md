# Pricing check vs real historical SPXW prices (Barchart)

Model evaluated with call-wing multiplier 0.82 and wing vol beta 0.0 (1.0 / 0.0 = the backtest's chain-calibrated pricing).

Contracts: 166 sampled (83 expiries with data), 778 daily observations from 2023-06-05 to 2026-09-17. IV ratio = implied vol of the real closing price / backtest model vol for the same contract and day (1.0 = the backtest's pricing is right).

**Core sample (model delta 12-40%): median IV ratio 1.025 (IQR 0.954-1.086), median price ratio 1.052, n = 388.** Slope of ln(ratio) on ATM vol: 0.01 per 1.00 of vol.

## By days to expiry (core)

|   dte |   n |   median IV ratio |   IQR low |   IQR high |   median price ratio |
|------:|----:|------------------:|----------:|-----------:|---------------------:|
|     1 |  27 |             1.102 |     0.976 |      1.147 |                1.231 |
|     2 |  47 |             1.036 |     0.96  |      1.134 |                1.101 |
|     3 |  57 |             1.015 |     0.949 |      1.115 |                1.04  |
|     4 |  93 |             1.04  |     0.953 |      1.086 |                1.06  |
|     5 | 164 |             1.013 |     0.956 |      1.066 |                1.026 |

## By model delta (all observations)

| model_delta   |   n |   median IV ratio |   IQR low |   IQR high |   median price ratio |
|:--------------|----:|------------------:|----------:|-----------:|---------------------:|
| (0.0, 0.025]  |  97 |             1.056 |     0.996 |      1.131 |                1.507 |
| (0.025, 0.05] |  45 |             1.059 |     0.963 |      1.138 |                1.358 |
| (0.05, 0.075] |  45 |             1.085 |     0.993 |      1.159 |                1.434 |
| (0.075, 0.1]  |  30 |             1.068 |     0.985 |      1.181 |                1.287 |
| (0.1, 0.15]   |  53 |             1.066 |     0.95  |      1.136 |                1.239 |
| (0.15, 0.3]   | 266 |             1.015 |     0.953 |      1.083 |                1.035 |
| (0.3, 1.0]    | 242 |             1.01  |     0.928 |      1.081 |                1.008 |

## By vol regime (core)

| atm       |   n |   median IV ratio |   IQR low |   IQR high |   median price ratio |
|:----------|----:|------------------:|----------:|-----------:|---------------------:|
| (0, 10]   |  83 |             1.058 |     1.002 |      1.116 |                1.12  |
| (10, 12]  | 109 |             1.032 |     0.959 |      1.1   |                1.069 |
| (12, 14]  |  84 |             0.999 |     0.915 |      1.048 |                0.998 |
| (14, 17]  |  63 |             0.997 |     0.968 |      1.067 |                0.994 |
| (17, 25]  |  40 |             1.011 |     0.935 |      1.045 |                1.021 |
| (25, 100] |   9 |             1.102 |     1.085 |      1.149 |                1.231 |

## By half-year (core)

| date   |   n |   median IV ratio |   IQR low |   IQR high |   median price ratio |
|:-------|----:|------------------:|----------:|-----------:|---------------------:|
| 2023H1 |  13 |             1.041 |     1.028 |      1.089 |                1.088 |
| 2023H2 |  55 |             1.078 |     1.023 |      1.132 |                1.192 |
| 2024H1 |  56 |             1.069 |     1.025 |      1.124 |                1.139 |
| 2024H2 |  65 |             0.986 |     0.916 |      1.074 |                0.973 |
| 2025H1 |  51 |             1.034 |     0.974 |      1.087 |                1.069 |
| 2025H2 |  60 |             1.007 |     0.946 |      1.042 |                1.015 |
| 2026H1 |  68 |             0.985 |     0.915 |      1.037 |                0.967 |
| 2026H2 |  20 |             0.95  |     0.867 |      1.005 |                0.868 |

## Across a weekend or not (core)

|   weekend |   n |   median IV ratio |   IQR low |   IQR high |   median price ratio |
|----------:|----:|------------------:|----------:|-----------:|---------------------:|
|         0 | 102 |             1.089 |     0.984 |      1.21  |                1.174 |
|         1 | 286 |             1.009 |     0.947 |      1.068 |                1.02  |

## Real-price mini-backtest (sell at 5DTE close, daily close delta hedge, hold to expiry)

Same contracts sold at the real closing price vs at the model price (both less a 3% half-spread, min 0.025). One expiry every 10 trading days, strikes at 20, 30 delta; P&L in bp of the notional.

|                                  |     real |    model |
|:---------------------------------|---------:|---------:|
| contracts                        |  164     |  164     |
| avg premium (bp)                 |   25.212 |   24.689 |
| avg payoff (bp)                  |   35.711 |   35.711 |
| avg P&L hedged (bp)              |    1.202 |    0.033 |
| hit rate                         |    0.573 |    0.616 |
| Sharpe (per-expiry series, ann.) |    0.243 |    0.006 |
| worst expiry (bp)                | -221.911 | -307.496 |

By target delta (averages, bp):

|   target |   prem_real_bp |   prem_model_bp |   payoff_bp |   pnl_real_bp |   pnl_model_bp |
|---------:|---------------:|----------------:|------------:|--------------:|---------------:|
|      0.2 |         16.507 |          16.364 |      26.179 |         0.463 |         -0.422 |
|      0.3 |         33.918 |          33.014 |      45.244 |         1.941 |          0.488 |
