# Retail programme with a richness signal (2023-06-05 to 2026-09-22)

Retail = XSP-style execution (real XSP spreads), 20-30 delta calls at 10DTE, hedged 3x a day. Every variant is shown at the notional that runs the every-day programme at 5% volatility; 'Ret @5% vol' re-scales each to 5% volatility. Signals use the previous day's reading unless marked same-day.

|                                       |   Return %/yr |   Vol % |   Sharpe |   Calmar |   MaxDD % |   Ret @5% vol |   Sharpe 2023-24 |   Sharpe 2025-26 |   Days sold % |   +5% gap, calm, same size % |
|:--------------------------------------|--------------:|--------:|---------:|---------:|----------:|--------------:|-----------------:|-----------------:|--------------:|-----------------------------:|
| Retail, sells every day               |          5.06 |    5    |     1.01 |     0.97 |     -5.23 |          5.06 |             0.67 |             1.29 |         98.79 |                        -9.7  |
| Far-wing signal >= 0.85, same-day     |          1.12 |    2.73 |     0.42 |     0.29 |     -3.88 |          2.1  |             0.12 |             1.27 |         31.04 |                        -2.04 |
| Far-wing signal >= 0.85               |          1.07 |    2.75 |     0.4  |     0.28 |     -3.85 |          2.01 |             0.08 |             1.27 |         31.04 |                        -1.89 |
| Far-wing signal >= 0.80               |          2.52 |    3.61 |     0.71 |     0.74 |     -3.41 |          3.53 |             0.39 |             1.1  |         46.62 |                        -5.32 |
| Far-wing signal >= 0.90               |          0.11 |    1.65 |     0.08 |     0.04 |     -2.63 |          0.39 |             0.06 |             0.45 |         15.7  |                         0    |
| Retail-zone signal, top 2/3 (>= 0.99) |          2.4  |    3.93 |     0.62 |     0.48 |     -5.03 |          3.12 |             0.6  |             0.66 |         65.94 |                        -7.52 |
| Retail-zone signal, top 1/3 (>= 1.06) |          0.71 |    2.52 |     0.29 |     0.23 |     -3.16 |          1.47 |             0.13 |             1.24 |         31.4  |                        -3.01 |
| Far wing above its 6m median          |          2.14 |    3.39 |     0.64 |     0.51 |     -4.22 |          3.21 |            -0.09 |             1.2  |         38.65 |                        -3.17 |
| Retail zone above its 6m median       |          2.14 |    3.3  |     0.66 |     0.55 |     -3.9  |          3.29 |             0.06 |             1.24 |         43.36 |                        -4.7  |

## Real trades by richness at the sale date

Real 20-30 delta SPXW calls sold at their 10DTE close, hedged daily, held to expiry (one expiry every 10 days).

|                           |   level (median) |   trades |   avg P&L, bp |   avg premium, bp |   Sharpe (per trade x sqrt 26) |   worst, bp |
|:--------------------------|-----------------:|---------:|--------------:|------------------:|-------------------------------:|------------:|
| ('far wing', 'cheap')     |             0.73 |       43 |         14.99 |             36.66 |                           3.67 |      -26.89 |
| ('far wing', 'middle')    |             0.81 |       42 |          2.94 |             44.32 |                           0.42 |     -108.16 |
| ('far wing', 'rich')      |             0.91 |       43 |          4.32 |             34.29 |                           0.92 |      -59.1  |
| ('retail zone', 'cheap')  |             0.97 |       43 |         14.12 |             38.11 |                           2.25 |     -108.16 |
| ('retail zone', 'middle') |             1.03 |       42 |          4.17 |             42.67 |                           0.79 |     -102.92 |
| ('retail zone', 'rich')   |             1.1  |       43 |          3.99 |             34.45 |                           0.86 |      -59.1  |

Sanity check: institutional core + far-wing signal, same-day, Sharpe 2.27.
