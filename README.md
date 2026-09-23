# SG_UFLY: Upside Vol Premium backtest (short-dated far-OTM SPX calls)

A simulation of a systematic **upside volatility premium** strategy:

> On every roll date the strategy sells deep OTM **1-delta to 10-delta calls** across four
> short-dated listed expiries (**2, 3, 4, 5 DTE**), each with **25%** weight, to spread risk
> evenly across maturities. The position is **delta-hedged every hour** intraday. Calls are
> **held to maturity**.

Backtest window: **3 Jan 2011 – 22 Sep 2026** (3,953 SPX trading days).

![tearsheet](results/tearsheet.png)

## Headline results

Returns are excess returns (collateral interest is not included). The base case sells
1x NAV of notional per daily roll, which averages 3.5x NAV of short 1–10-delta calls outstanding.

| Scenario | CAGR % | Vol % | Sharpe | Max DD % | Max DD intraday % | Worst day % |
|---|---:|---:|---:|---:|---:|---:|
| **Base** (hourly hedge, daily roll, VolVue ATM) | **8.0** | 1.6 | **4.9** | -2.5 | -3.0 | -1.2 |
| Base scaled to ~6% vol (3.8x notional) | 33.7 | 6.0 | 4.9 | -9.3 | -11.1 | -4.5 |
| Hedge once a day (close) | 5.6 | 2.4 | 2.3 | -6.2 | -7.1 | -1.9 |
| Unhedged | 4.1 | 3.3 | 1.2 | -6.8 | -7.3 | -4.9 |
| Only expiries SPX actually listed at the time | 7.6 | 1.6 | 4.6 | -2.3 | -2.8 | -1.2 |
| Weekly roll (same notional per expiry) | 7.1 | 1.7 | 4.0 | -2.7 | -3.5 | -1.9 |
| Call wing 4% cheaper (0.88 / 0.94 × ATM) | 6.6 | 1.6 | 3.9 | -3.5 | -4.0 | -1.2 |
| Call wing 20% cheaper (0.74 / 0.82 × ATM) | 0.8 | 2.2 | 0.4 | -9.6 | – | – |
| No transaction costs | 8.9 | 1.6 | 5.4 | -2.3 | -2.8 | -1.2 |
| High transaction costs | 7.4 | 1.6 | 4.5 | -2.6 | -3.1 | -1.2 |

Full tables are in [`results/RESULTS_TABLES.md`](results/RESULTS_TABLES.md): yearly returns, P&L
attribution, results by strike delta and tenor, sub-periods, the call-wing grid, the worst days
and diagnostics.

## Conclusions you can act on

1. **Hourly hedging is where most of the risk-adjusted return comes from.** Moving from
   daily-close hedging to hourly roughly doubles the Sharpe (2.3 → 4.9) and cuts the drawdown
   from -6.2% to -2.5%. Unhedged, the strategy only reaches Sharpe 1.2 and has a -4.9% worst
   day. Keep the hourly hedge (or finer) and treat it as non-negotiable.
2. **The edge is real in the data: far-OTM short-dated calls finish in the money much less
   often than their delta implies.** 5-delta calls finished ITM 3.1% of the time and 1-delta
   calls 0.1%, against 5% and 1% priced in. SPX's upside moves are thinner-tailed than
   option prices assume.
3. **Most of the dollar P&L comes from the 5–10-delta strikes and the 4–5DTE tenors.**
   1–3-delta calls keep most of their premium (payoff is only 6–27% of premium) but add
   little P&L and suffer most from the 0.05 tick. 5DTE earns about twice what 2DTE earns
   after hedging. If you ever tilt away from equal weights, tilt towards 5–10 delta and 4–5DTE.
4. **The risk is short gamma in both directions, not just melt-ups.** The worst days were
   crashes (8 Aug 2011, 16 Mar 2020) and the day after an upside shock (10 Apr 2025).
   Whipsaw days where the index reverses intraday also hurt (7 Apr 2020, 16 Jan 2018).
   On 9 Apr 2025 (SPX +9.5%) the book was down about 1.1% intraday but closed up, because the
   ATM vol collapse (57% → 34%) marked the remaining short calls down.
   At ~6% target vol, budget for a -5% day and a -10% to -11% drawdown.
5. **The biggest open question is wing pricing, and it has to be checked against real
   quotes.** VolVue only provides ATM implied vol, not strike- or delta-level vols, so the
   1–10-delta call vols come from an assumed smile (10-delta call at 0.92 × ATM, 1-delta call
   at 1.02 × ATM). Each 4% cheaper wing costs about 1 point of Sharpe; the strategy
   breaks even when the wing is about 20% cheaper than assumed. **Before trading, pull real SPXW
   chains** (CBOE DataShop, OptionMetrics, ORATS or your broker) and compare the traded 1–10-delta
   call vol / ATM ratios with these.
6. **Execution matters, but it isn't decisive.** Going from zero costs to high costs moves the
   Sharpe from 5.4 to 4.5. The 0.05 minimum tick is what hurts the 1–2-delta strikes.
   Work orders near mid; avoid crossing the full spread on cheap wings.
7. **Keep the daily roll.** A weekly roll with the same notional per expiry has a lower Sharpe
   (4.0) and a worse worst day (-1.9%), because the daily ladder diversifies entry dates.
   The design works in today's market: SPX has had daily expiries since May 2022, and the
   2022–2026 sub-period is as good as the full sample (Sharpe 5.0).
8. **Treat Sharpe ≈ 5 as a model upper bound, not a forecast.** Options are marked on a model
   surface anchored to VolVue ATM vol, and the wing has no time-varying premium or vol-of-vol.
   Live trading will realise considerably less. Size off the drawdown and worst-day
   numbers, not off the Sharpe.

## How the simulation works

| Component | Implementation |
|---|---|
| Underlying | SPX, daily OHLC (Yahoo). Real **hourly bars from Oct 2023**. Before that, synthetic hourly marks come from a Brownian bridge between the real open and close, with intraday variance from the daily high/low range, clipped to [low, high]. On the overlapping window the synthetic paths give 8.4% vs 7.9% annualised return (0.89 correlation), so the pre-2023 results are slightly flattering. |
| Roll | Every trading day at the close. Sells expiries d+2, d+3, d+4 and d+5 trading days, 25% of the roll notional each. |
| Strike strip | Each expiry sells 10 strikes at 1%, 2%, …, 10% call delta (equal notional), snapped to the 5-point SPX strike grid. |
| Sizing | Notional sold per roll = 1.0 × NAV (so each expiry accumulates 1× NAV across its four sale dates). `leverage` scales it. |
| ATM implied vol | **VolVue SPX 10-day ATM mean IV** (EOD; bad prints and gaps are replaced by VIX9D × the local VolVue/VIX9D ratio). Intraday, the vol moves from the open level with a spot-vol beta (−5 on rallies, −7 on sell-offs, both fitted 2011–26). VolVue also validates the VIX9D proxy: median VIX9D / ATM = 1.17. |
| Smile | Quadratic in normalised moneyness z = ln(K/F)/(σ_ATM√T). Call wing is anchored at 10-delta = 0.92 × ATM and 1-delta = 1.02 × ATM. **This is an assumption** (see conclusion 5). |
| Time / variance clock | Business time: each trading day = 1 unit of variance, 20% overnight and 80% intraday, plus 0.10 for each weekend or holiday day. The shares were estimated from SPX 2017–26 open/close data. |
| Execution | Sell at mid − max(0.025, 3% × mid). A strike isn't sold if its bid would be below 0.05. |
| Settlement | Held to expiry, cash-settled on the official close (SPXW PM settlement). |
| Delta hedge | Rebalanced at the open, 10:30, 11:30, …, 15:30 and the close to the Black-Scholes delta at the smile vol. Uses SPX/ES as a zero-carry future, costing 0.15 index points per unit traded. |
| Returns | Excess return (no T-bill interest on collateral), NAV starts at 100. |

### Limitations

- **No historical strike-level SPXW quotes.** Wing vols and bid/ask spreads are modelled.
- Before May 2022, SPX didn't list every weekday expiry. The base case assumes it did; the
  "listed expiries only" scenario uses the real listing calendar and reallocates weight.
- The wing premium is static relative to ATM. In reality it varies (for example, call-wing bid in
  2020–21 or dealer supply in calm markets).
- Margin, financing and collateral yield are ignored. Returns are excess returns on NAV.
- Hedging at hourly marks can't capture moves between marks (e.g. the 13:18 spike on 9 Apr 2025
  was only hedged at 13:30).

## Run it

```bash
pip install -r requirements.txt
export VOLVUE_API_KEY=...            # optional; falls back to the VIX9D proxy for ATM vol
python run_backtest.py               # downloads data to ./data on first run, writes ./results
python run_backtest.py --refresh     # force re-download
```

Code layout:

- `ufly/data.py`: Yahoo download/cache and cleaning (missing days rebuilt from hourly bars; the in-progress session is dropped)
- `ufly/volvue.py`: VolVue API client (`api.volvue.com/query`)
- `ufly/vol.py`: Black-Scholes, smile model, strike-for-delta solver, business-time variance clock
- `ufly/paths.py`: hourly marks (real or bridged)
- `ufly/backtest.py`: strategy engine (`Config` holds every parameter)
- `ufly/metrics.py`: performance statistics
- `run_backtest.py`: scenarios, tables and charts

Raw market data (`data/`) is git-ignored and not redistributed. It is re-downloaded from Yahoo
and VolVue on first run.
