# Retail implementation check

## 1. Futures cannot emulate the short options

The synthetic short strip holds minus the strip's delta in futures, hourly (no premium, no payoff).

|                                                               |   Ann. return % |   Vol % |   Sharpe |   MaxDD % |
|:--------------------------------------------------------------|----------------:|--------:|---------:|----------:|
| ('Real options: sell strip, hedge with futures', '2011-2026') |            3.62 |    2.36 |     1.53 |     -4.52 |
| ('Real options: sell strip, hedge with futures', 'Jun-2023+') |            3.22 |    2.28 |     1.41 |     -3    |
| ('Futures only: synthetic short strip', '2011-2026')          |           -6.16 |    5.29 |    -1.16 |    -65.37 |
| ('Futures only: synthetic short strip', 'Jun-2023+')          |          -10.38 |    5.81 |    -1.79 |    -30.17 |

## 2. Real options with retail execution costs

Half-spread paid on each sale: SPXW max(0.025, 3% of mid); XSP limit orders max(0.05, 10%); XSP crossing max(0.05, 20%) (SPX-point equivalents; XSP tick 0.01 = 0.10 SPX points, so strikes with a bid below 0.10 are skipped). Hedge with SPY shares / MES: 0.10 points per unit. Jun-2023+ rows use the daily wing level from real Barchart prices.

|                                                                                                    |   CAGR % |   Vol % |   Sharpe |   MaxDD % |
|:---------------------------------------------------------------------------------------------------|---------:|--------:|---------:|----------:|
| ('2011-2026', 'SPXW (institutional)', 'tilted')                                                    |     3.65 |    2.36 |     1.53 |     -4.52 |
| ('2011-2026', 'SPXW (institutional)', 'low-delta')                                                 |     2.67 |    1.53 |     1.73 |     -2.92 |
| ('2011-2026', 'XSP, limit orders (half the spread)', 'tilted')                                     |     3.13 |    2.35 |     1.32 |     -4.91 |
| ('2011-2026', 'XSP, limit orders (half the spread)', 'low-delta')                                  |     2.33 |    1.5  |     1.55 |     -3.07 |
| ('2011-2026', 'XSP, crossing the spread', 'tilted')                                                |     2.04 |    2.36 |     0.87 |     -5.82 |
| ('2011-2026', 'XSP, crossing the spread', 'low-delta')                                             |     1.77 |    1.5  |     1.17 |     -3.55 |
| ('Jun-2023+ (real wing)', 'SPXW (institutional)', 'tilted')                                        |     3.15 |    2.17 |     1.44 |     -3.1  |
| ('Jun-2023+ (real wing)', 'SPXW (institutional)', 'low-delta')                                     |     2.86 |    1.45 |     1.95 |     -1.72 |
| ('Jun-2023+ (real wing)', 'SPXW (institutional)', 'low-delta, rich-wing days only')                |     1.53 |    0.67 |     2.27 |     -0.45 |
| ('Jun-2023+ (real wing)', 'XSP, limit orders (half the spread)', 'tilted')                         |     2.58 |    2.17 |     1.18 |     -3.31 |
| ('Jun-2023+ (real wing)', 'XSP, limit orders (half the spread)', 'low-delta')                      |     2.54 |    1.45 |     1.74 |     -1.77 |
| ('Jun-2023+ (real wing)', 'XSP, limit orders (half the spread)', 'low-delta, rich-wing days only') |     1.43 |    0.67 |     2.13 |     -0.45 |
| ('Jun-2023+ (real wing)', 'XSP, crossing the spread', 'tilted')                                    |     1.58 |    2.18 |     0.73 |     -3.66 |
| ('Jun-2023+ (real wing)', 'XSP, crossing the spread', 'low-delta')                                 |     1.97 |    1.45 |     1.35 |     -1.91 |
| ('Jun-2023+ (real wing)', 'XSP, crossing the spread', 'low-delta, rich-wing days only')            |     1.25 |    0.66 |     1.88 |     -0.49 |
