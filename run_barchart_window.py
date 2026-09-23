"""Backtest on the Barchart window (Jun 2023 - Sep 2026) with the call-wing level taken
day by day from real SPXW prices, and a rich-wing filter.

    python validate_history.py --wing-mult 1.0   # builds the observations this script reads
    python run_barchart_window.py

The wing level on each date = rolling median (5 observation days) of real / model
implied vol for 3-12 delta calls, measured against the chain-calibrated model
(wing x1.0).  It is observable at the time of trading (it is the price you sell at).
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from run_backtest import LOW_DELTA_W, TILT_DELTA_W, TILT_DTE_W
from ufly.backtest import Config, run
from ufly.data import DATA_DIR, load_market
from ufly.metrics import stats
from ufly.paths import build_marks

OUT = Path(__file__).resolve().parent / "results"
START = "2023-06-05"


def wing_series() -> Path:
    o = pd.read_csv(DATA_DIR / "barchart_analysis" / "history_check_obs.csv", parse_dates=["date"])
    core = o[(o.model_delta >= 0.03) & (o.model_delta <= 0.12)]
    daily = core.groupby("date").iv_ratio.median().sort_index()
    w = daily.rolling(5, min_periods=1).median().rename("wing_mult")
    p = DATA_DIR / "barchart_analysis" / "wing_level.csv"
    w.to_csv(p)
    return p


def main():
    daily, hourly = load_market()
    wf = str(wing_series())
    w = pd.read_csv(wf, index_col=0, parse_dates=True).wing_mult
    base = Config(name="x", start=START, weights=TILT_DTE_W, delta_weights=TILT_DELTA_W)
    marks = build_marks(daily.loc[START:base.end], hourly, seed=base.seed, f_on=base.clock.f_on)
    q = w.quantile([1 / 3, 2 / 3]).values
    cfgs = [
        replace(base, name="Tilted, wing x0.82 (constant)"),
        replace(base, name="Tilted, wing x0.82, hedge daily", hedge="daily"),
        replace(base, name="Tilted, wing from real prices (daily)", wing_file=wf),
        replace(base, name="Tilted, real wing, hedge daily", wing_file=wf, hedge="daily"),
        replace(base, name=f"Tilted, real wing, sell only if wing >= {q[0]:.2f} (top 2/3)", wing_file=wf, roll_min_wing=q[0]),
        replace(base, name=f"Tilted, real wing, sell only if wing >= {q[1]:.2f} (top 1/3)", wing_file=wf, roll_min_wing=q[1]),
        replace(base, name=f"Top 1/3 filter, hedge daily", wing_file=wf, roll_min_wing=q[1], hedge="daily"),
        replace(base, name="Low-delta tilt, real wing", wing_file=wf, delta_weights=LOW_DELTA_W),
        Config(name="ATM calls 4-5DTE (ATM pricing validated)", start=START, dtes=(4, 5), weights=(0.5, 0.5), deltas=(0.5,)),
        Config(name="ATM calls 4-5DTE, hedge daily", start=START, dtes=(4, 5), weights=(0.5, 0.5), deltas=(0.5,), hedge="daily"),
    ]
    rows = {}
    for c in cfgs:
        r = run(c, daily, hourly, marks)
        st = stats(r.daily, r.intraday)
        st["Ret @5% vol"] = 100 * r.daily.ret.mean() * 252 * 5 / (100 * r.daily.ret.std() * np.sqrt(252))
        st["Days sold (%)"] = 100 * (r.daily.n_sold > 0).mean()
        real = r.daily.loc["2023-10-25":]
        rr = real.ret
        st["Sharpe, real hourly bars only"] = rr.mean() / rr.std() * np.sqrt(252)
        rows[c.name] = st
        print("done:", c.name, flush=True)
    t = pd.DataFrame(rows).T[["CAGR %", "Vol %", "Sharpe", "Ret @5% vol", "MaxDD %", "Worst day %",
                               "Days sold (%)", "Sharpe, real hourly bars only"]]
    md = [f"# Barchart window backtest ({START} to {base.end})\n",
          "Pricing: chain-calibrated model with the call-wing level set each day from real SPXW prices "
          f"(Barchart; median {w.median():.2f}, 10th-90th pct {w.quantile(0.1):.2f}-{w.quantile(0.9):.2f}); "
          "ATM pricing validated against real ATM prices (median IV ratio 1.02). "
          "Hourly hedging uses real SPX hourly bars from Oct 2023.\n",
          t.round(2).to_markdown()]
    (OUT / "BARCHART_WINDOW.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
