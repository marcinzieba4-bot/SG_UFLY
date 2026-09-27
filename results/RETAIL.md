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

## 3. Sell a cheaper-to-trade option and delta-hedge?

Real SPXW prices (Barchart, Jun 2023 - Sep 2026): each contract sold at its closing mid, delta-hedged at each daily close (retail-friendly), held to expiry. Net = minus the median real half-spread for that tenor x delta cell (spread map from Yahoo closing quotes). Delta bucket = real delta at the sale.

|   sale DTE | delta at sale   |   trades |   gross edge (bp/trade) |   gross Sharpe |   XSP cost (bp) |   XSP net (bp/trade) |   XSP net (bp/day held) |   SPXW cost (bp) |   SPXW net (bp/trade) |   SPXW net (bp/day held) |   worst trade (bp) |
|-----------:|:----------------|---------:|------------------------:|---------------:|----------------:|---------------------:|------------------------:|-----------------:|----------------------:|-------------------------:|-------------------:|
|          5 | 1-3d            |      156 |                    0.64 |           0.58 |            0.19 |                 0.45 |                    0.09 |             0.1  |                  0.55 |                     0.11 |             -69.08 |
|          5 | 3-7d            |      170 |                    1    |           0.52 |            0.77 |                 0.22 |                    0.04 |             0.16 |                  0.84 |                     0.17 |             -90.81 |
|          5 | 7-12d           |       47 |                    5.94 |           3.97 |            0.97 |                 4.97 |                    0.99 |             0.19 |                  5.75 |                     1.15 |             -20.87 |
|          5 | 12-20d          |       74 |                   -0.14 |          -0.03 |            1.1  |                -1.23 |                   -0.25 |             0.19 |                 -0.33 |                    -0.07 |             -85.53 |
|          5 | 20-30d          |       73 |                    3.66 |           0.73 |            1.29 |                 2.36 |                    0.47 |             0.19 |                  3.46 |                     0.69 |             -94.52 |
|          5 | ~ATM            |      163 |                    6.17 |           1.38 |            1.48 |                 4.69 |                    0.94 |             0.26 |                  5.92 |                     1.18 |            -124.06 |
|         10 | 3-7d            |       31 |                    4.44 |           1.47 |            0.77 |                 3.66 |                    0.37 |             0.23 |                  4.21 |                     0.42 |             -15.84 |
|         10 | 12-20d          |       46 |                    7.65 |           1.67 |            1.1  |                 6.55 |                    0.66 |             0.39 |                  7.26 |                     0.73 |             -63.04 |
|         10 | 20-30d          |       60 |                    5.6  |           0.97 |            1.23 |                 4.37 |                    0.44 |             0.39 |                  5.21 |                     0.52 |            -108.16 |
|         10 | 30-45d          |       21 |                   13.71 |           2.41 |            1.29 |                12.42 |                    1.24 |             0.39 |                 13.33 |                     1.33 |             -31.12 |

Median half-spread, % of premium (XSP):

| tenor   |   1-3d |   12-20d |   20-30d |   3-7d |   30-45d |   7-12d |   ~ATM |
|:--------|-------:|---------:|---------:|-------:|---------:|--------:|-------:|
| 1       |   60   |      9.3 |      5.5 |   23.3 |      4.3 |    12.5 |    4.9 |
| 11-15   |   61.9 |     12.8 |      8.6 |   30.4 |      4.9 |    20   |    3.4 |
| 16-22   |   65.5 |     11.7 |      7.6 |   31.9 |      4.6 |    19.4 |    3.1 |
| 2-3     |   42.9 |      9.7 |      6.4 |   36.8 |      2.7 |    19   |    3.3 |
| 23-32   |   62.5 |     12.2 |      7.4 |   30.6 |      4.7 |    17.2 |    4.5 |
| 4-5     |   33.3 |      8.9 |      6.5 |   25.5 |      2.7 |    17.6 |    2.6 |
| 6-10    |   28.6 |      7   |      4.5 |   18.2 |      2.7 |    12   |    2.8 |

## 4. Engine: far-OTM strip vs cheaper-to-trade calls, XSP costs, by hedge frequency

Daily roll with overlapping positions, 1x NAV notional per roll, crossing the real XSP spread (half-spread = min(0.10 + 20% x mid, 0.70 + 1.2% x mid) SPX points), hedged with SPY/MES at 0.10 points per unit. Risk columns are scaled to 5% annualised vol so rows compare; gap = instant move on the closing book, calm-market median. The 12-45 delta and ATM pricing is validated against real prices (real / model IV 1.01-1.04).

|                                                                   |   Sharpe |   Ret @5% vol |   MaxDD @5% vol |   Worst day @5% vol |   gap +5% calm @5% vol |   gap -5% calm @5% vol |   cost / premium % |
|:------------------------------------------------------------------|---------:|--------------:|----------------:|--------------------:|-----------------------:|-----------------------:|-------------------:|
| ('2011-2026', 'Far-OTM, low-delta tilt (1-5d), 2-5DTE', 'hourly') |     0.73 |          3.67 |          -16.17 |               -3.74 |                 -28.25 |                  -1.52 |              30.72 |
| ('2011-2026', 'Far-OTM, low-delta tilt (1-5d), 2-5DTE', '3x')     |     0.47 |          2.37 |          -15.34 |               -5.22 |                 -23.51 |                  -1.26 |              30.74 |
| ('2011-2026', 'Far-OTM, low-delta tilt (1-5d), 2-5DTE', 'daily')  |    -0.13 |         -0.67 |          -27.47 |               -4.98 |                 -18.29 |                  -0.98 |              31.13 |
| ('2011-2026', 'Far-OTM, 5-10d tilt, 2-5DTE', 'hourly')            |     0.54 |          2.69 |          -17.8  |               -3.73 |                 -24.54 |                  -1.84 |              26.9  |
| ('2011-2026', 'Far-OTM, 5-10d tilt, 2-5DTE', '3x')                |     0.28 |          1.4  |          -20.85 |               -4.57 |                 -20.64 |                  -1.55 |              26.96 |
| ('2011-2026', 'Far-OTM, 5-10d tilt, 2-5DTE', 'daily')             |    -0.45 |         -2.27 |          -41.6  |               -4.92 |                 -15.55 |                  -1.17 |              27.7  |
| ('2011-2026', '20-30d calls, 5DTE', 'hourly')                     |     1.41 |          7.07 |           -9.12 |               -2.96 |                 -11.09 |                  -4.86 |               8.9  |
| ('2011-2026', '20-30d calls, 5DTE', '3x')                         |     0.95 |          4.76 |          -12.56 |               -3.14 |                  -9.69 |                  -4.25 |               9.24 |
| ('2011-2026', '20-30d calls, 5DTE', 'daily')                      |    -0.53 |         -2.63 |          -34.17 |               -5.03 |                  -6.83 |                  -2.99 |              12.27 |
| ('2011-2026', '20-30d calls, 10DTE', 'hourly')                    |     1.76 |          8.82 |           -6.36 |               -3.21 |                  -9.92 |                  -5.37 |               5.46 |
| ('2011-2026', '20-30d calls, 10DTE', '3x')                        |     1.39 |          6.96 |           -7.17 |               -3.17 |                  -9.05 |                  -4.9  |               5.68 |
| ('2011-2026', '20-30d calls, 10DTE', 'daily')                     |     0.4  |          2.02 |          -13.55 |               -5.38 |                  -7.38 |                  -4    |               7.66 |
| ('2011-2026', '30-45d calls, 10DTE', 'hourly')                    |     1.8  |          9.02 |           -6.33 |               -3.54 |                  -6.66 |                  -6.39 |               3.45 |
| ('2011-2026', '30-45d calls, 10DTE', '3x')                        |     1.37 |          6.83 |           -7.13 |               -3.42 |                  -6.04 |                  -5.78 |               3.59 |
| ('2011-2026', '30-45d calls, 10DTE', 'daily')                     |     0.13 |          0.66 |          -14.59 |               -4.27 |                  -4.8  |                  -4.6  |               5.12 |
| ('2011-2026', 'ATM calls, 5DTE', 'hourly')                        |     1.85 |          9.26 |          -10.51 |               -4.08 |                  -5.5  |                  -7.19 |               3.75 |
| ('2011-2026', 'ATM calls, 5DTE', '3x')                            |     1.21 |          6.05 |          -10.96 |               -3.93 |                  -4.74 |                  -6.2  |               3.97 |
| ('2011-2026', 'ATM calls, 5DTE', 'daily')                         |    -0.55 |         -2.76 |          -29.88 |               -5.06 |                  -3.27 |                  -4.29 |               5.66 |
| ('Jun-2023+', 'Far-OTM, low-delta tilt (1-5d), 2-5DTE', 'hourly') |     1.1  |          5.48 |           -6.78 |               -3.06 |                 -36.65 |                  -1.87 |              26.16 |
| ('Jun-2023+', 'Far-OTM, low-delta tilt (1-5d), 2-5DTE', '3x')     |     0.51 |          2.55 |           -6.55 |               -4.27 |                 -29.4  |                  -1.5  |              26.16 |
| ('Jun-2023+', 'Far-OTM, low-delta tilt (1-5d), 2-5DTE', 'daily')  |    -0.08 |         -0.42 |          -10.48 |               -4.45 |                 -21.27 |                  -1.09 |              26.18 |
| ('Jun-2023+', 'Far-OTM, 5-10d tilt, 2-5DTE', 'hourly')            |     0.62 |          3.09 |           -8.36 |               -2.33 |                 -27.3  |                  -2.24 |              22.44 |
| ('Jun-2023+', 'Far-OTM, 5-10d tilt, 2-5DTE', '3x')                |     0.06 |          0.32 |           -9.39 |               -2.69 |                 -22.28 |                  -1.83 |              22.45 |
| ('Jun-2023+', 'Far-OTM, 5-10d tilt, 2-5DTE', 'daily')             |    -0.41 |         -2.07 |          -12.79 |               -2.92 |                 -16.16 |                  -1.33 |              22.48 |
| ('Jun-2023+', '20-30d calls, 5DTE', 'hourly')                     |     0.49 |          2.47 |           -9.85 |               -2.29 |                 -11.23 |                  -5.29 |               6.06 |
| ('Jun-2023+', '20-30d calls, 5DTE', '3x')                         |     0.21 |          1.06 |          -10.34 |               -1.95 |                  -9.6  |                  -4.51 |               6.07 |
| ('Jun-2023+', '20-30d calls, 5DTE', 'daily')                      |    -0.39 |         -1.95 |          -15.11 |               -3.19 |                  -7.4  |                  -3.48 |               6.13 |
| ('Jun-2023+', '20-30d calls, 10DTE', 'hourly')                    |     1.25 |          6.26 |           -5.76 |               -2.1  |                 -10.81 |                  -6.5  |               4.56 |
| ('Jun-2023+', '20-30d calls, 10DTE', '3x')                        |     1.01 |          5.06 |           -5.16 |               -2.4  |                  -9.7  |                  -5.84 |               4.56 |
| ('Jun-2023+', '20-30d calls, 10DTE', 'daily')                     |     0.38 |          1.92 |           -7.99 |               -2.12 |                  -8.13 |                  -4.86 |               4.61 |
| ('Jun-2023+', '30-45d calls, 10DTE', 'hourly')                    |     0.93 |          4.63 |           -6.75 |               -2.17 |                  -7.33 |                  -7.35 |               3.03 |
| ('Jun-2023+', '30-45d calls, 10DTE', '3x')                        |     0.69 |          3.45 |           -6.62 |               -3.16 |                  -6.48 |                  -6.48 |               3.04 |
| ('Jun-2023+', '30-45d calls, 10DTE', 'daily')                     |     0.02 |          0.09 |          -10.75 |               -2.7  |                  -5.26 |                  -5.27 |               3.08 |
| ('Jun-2023+', 'ATM calls, 5DTE', 'hourly')                        |     0.44 |          2.19 |          -11.06 |               -2.68 |                  -5.41 |                  -7.73 |               2.88 |
| ('Jun-2023+', 'ATM calls, 5DTE', '3x')                            |     0.38 |          1.88 |          -10.56 |               -3.23 |                  -4.56 |                  -6.52 |               2.88 |
| ('Jun-2023+', 'ATM calls, 5DTE', 'daily')                         |    -0.36 |         -1.81 |          -14.7  |               -3.49 |                  -3.32 |                  -4.75 |               2.92 |
