# Barchart window backtest (2023-06-05 to 2026-09-22)

Pricing: chain-calibrated model with the call-wing level set each day from real SPXW prices (Barchart; median 0.80, 10th-90th pct 0.69-0.92); ATM pricing validated against real ATM prices (median IV ratio 1.02). Hourly hedging uses real SPX hourly bars from Oct 2023.

|                                                        |   CAGR % |   Vol % |   Sharpe |   Ret @5% vol |   MaxDD % |   Worst day % |   Days sold (%) |   Sharpe, real hourly bars only |
|:-------------------------------------------------------|---------:|--------:|---------:|--------------:|----------:|--------------:|----------------:|--------------------------------:|
| Tilted, wing x0.82 (constant)                          |     3.55 |    2.22 |     1.58 |          7.9  |     -3    |         -1    |           99.76 |                            1.66 |
| Tilted, wing x0.82, hedge daily                        |     0.76 |    3.73 |     0.22 |          1.1  |     -7.17 |         -2.26 |           99.76 |                            0.27 |
| Tilted, wing from real prices (daily)                  |     3.15 |    2.17 |     1.44 |          7.19 |     -3.1  |         -1    |           99.76 |                            1.33 |
| Tilted, real wing, hedge daily                         |     0.29 |    3.67 |     0.1  |          0.49 |     -8.05 |         -2.13 |           99.76 |                            0.04 |
| Tilted, real wing, sell only if wing >= 0.76 (top 2/3) |     2.71 |    1.83 |     1.47 |          7.36 |     -2.84 |         -1    |           65.94 |                            1.34 |
| Tilted, real wing, sell only if wing >= 0.85 (top 1/3) |     2.07 |    1.05 |     1.96 |          9.8  |     -0.72 |         -0.72 |           31.88 |                            1.94 |
| Top 1/3 filter, hedge daily                            |     1.65 |    1.53 |     1.08 |          5.38 |     -1.57 |         -1.21 |           31.88 |                            1.14 |
| Low-delta tilt, real wing                              |     2.86 |    1.45 |     1.95 |          9.77 |     -1.72 |         -0.91 |           99.76 |                            1.83 |
| ATM calls 4-5DTE (ATM pricing validated)               |     2.65 |    7.01 |     0.41 |          2.04 |    -15.62 |         -3.71 |           99.52 |                            0.23 |
| ATM calls 4-5DTE, hedge daily                          |    -4.7  |   11.55 |    -0.36 |         -1.79 |    -33.68 |         -8.94 |           99.52 |                           -0.41 |
