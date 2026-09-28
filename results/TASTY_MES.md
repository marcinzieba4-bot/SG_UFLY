# Micro E-mini options route: cost sensitivity and SPY hedge (2011-2026, 5% vol budget)

Costs x1 = spread model fitted to the most liquid weekly series (pre-market 2026-09-28); the new cash-settled weeklies quoted about 2x wider pre-market. Margin: SPAN proxy (-6%..+6% scan) for the futures account; the SPY variant adds 50% of the SPY position and gets no netting.

|                                      |   Return %/yr |   Vol % |   Sharpe |   MaxDD % |   Margin % NAV (median) |   Margin % NAV (95th) |   Fees % NAV/yr |   Cost / premium % |
|:-------------------------------------|--------------:|--------:|---------:|----------:|------------------------:|----------------------:|----------------:|-------------------:|
| XSP costs (reference), fractional    |          7.08 |    5.02 |     1.39 |     -7.52 |                   10.18 |                 14.03 |            0    |               7.05 |
| Micro E-mini, costs x1, fractional   |          8.38 |    5.02 |     1.63 |     -6.93 |                   10.17 |                 14.03 |            0    |               4.33 |
| Micro E-mini, costs x1.5, fractional |          7.4  |    5.02 |     1.45 |     -7.31 |                   10.17 |                 14.03 |            0    |               6.57 |
| Micro E-mini, costs x2, fractional   |          6.44 |    5.03 |     1.27 |     -7.91 |                   10.18 |                 14.03 |            0    |               8.86 |
| Micro E-mini + MES, costs x1.5, $25k |          5.65 |    7.53 |     0.77 |    -23.32 |                   10.51 |                 17.88 |            0.93 |               7.37 |
| Micro E-mini + MES, costs x2, $25k   |          5.37 |    7.06 |     0.78 |    -11.9  |                   10.57 |                 17.02 |            0.92 |               9.83 |
| Micro E-mini + SPY, costs x1.5, $25k |          6.7  |    5.58 |     1.19 |     -7.79 |                   60.35 |                148.4  |            0.32 |               7.43 |
| Micro E-mini + MES, costs x1.5, $50k |          6.98 |    5.62 |     1.23 |    -11.4  |                   10.2  |                 15.06 |            0.81 |               7.37 |
| Micro E-mini + MES, costs x2, $50k   |          4.03 |    6.36 |     0.65 |    -16.13 |                   10.12 |                 15.84 |            0.86 |               9.97 |
| Micro E-mini + SPY, costs x1.5, $50k |          7.03 |    5.05 |     1.37 |     -8.61 |                   59.82 |                137.47 |            0.32 |               7.42 |
| Micro E-mini + MES, costs x1.5, $75k |          6.66 |    5.33 |     1.24 |    -11.25 |                   10.13 |                 14.63 |            0.78 |               7.38 |
| Micro E-mini + MES, costs x2, $75k   |          4.83 |    5.46 |     0.89 |    -12.62 |                   10.2  |                 14.62 |            0.79 |               9.91 |
| Micro E-mini + SPY, costs x1.5, $75k |          7.24 |    5.1  |     1.4  |     -7.91 |                   60.35 |                136.3  |            0.32 |               7.38 |
