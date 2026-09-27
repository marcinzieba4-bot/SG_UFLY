"""Retail implementation check.

1. Can futures emulate selling the deep-OTM calls?  The synthetic short strip holds
   minus the strip's delta in futures (no option premium, no payoff): it is exactly
   the opposite of the strip backtest's hedge leg.
2. What is left after retail execution costs?  XSP (mini-SPX, 1/10 size) spreads on
   5-10 delta calls were ~20% of mid (half-spread) vs ~4% for SPXW (quotes of
   2026-09-25).  Hedge with SPY shares (fractional, penny spread) or MES futures.

    python run_retail.py     # needs data from run_backtest.py / run_barchart_window.py
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

# execution cost sets (half-spread paid when selling; SPX-point equivalents)
COSTS = {
    "SPXW (institutional)": dict(tc_opt_min=0.025, tc_opt_pct=0.03, min_bid=0.05, tc_hedge_pts=0.15),
    "XSP, limit orders (half the spread)": dict(tc_opt_min=0.05, tc_opt_pct=0.10, min_bid=0.10, tc_hedge_pts=0.10),
    "XSP, crossing the spread": dict(tc_opt_min=0.05, tc_opt_pct=0.20, min_bid=0.10, tc_hedge_pts=0.10),
}


def futures_only(daily_csv: Path) -> pd.DataFrame:
    d = pd.read_csv(daily_csv, index_col=0, parse_dates=True)
    prev = d.nav.shift().fillna(100.0)
    series = {"Real options: sell strip, hedge with futures": d.ret,
              "Futures only: synthetic short strip": (-d.hedge_pnl - d.hedge_cost) / prev}
    rows = {}
    for lab, r in series.items():
        for per, a in (("2011-2026", "2011"), ("Jun-2023+", START)):
            x = r.loc[a:]
            nav = (1 + x).cumprod()
            rows[(lab, per)] = {"Ann. return %": 100 * x.mean() * 252, "Vol %": 100 * x.std() * np.sqrt(252),
                                "Sharpe": x.mean() / x.std() * np.sqrt(252),
                                "MaxDD %": 100 * (nav / nav.cummax() - 1).min()}
    return pd.DataFrame(rows).T


def main():
    fut = futures_only(OUT / "tilted_daily.csv")
    daily, hourly = load_market()
    wf = DATA_DIR / "barchart_analysis" / "wing_level.csv"
    have_wing = wf.exists()
    rows = {}
    for period, start in (("2011-2026", "2011-01-03"), ("Jun-2023+ (real wing)", START)):
        marks = build_marks(daily.loc[start:"2026-09-22"], hourly)
        for cname, cost in COSTS.items():
            for sname, extra in (("tilted", dict(delta_weights=TILT_DELTA_W)),
                                 ("low-delta", dict(delta_weights=LOW_DELTA_W)),
                                 ("low-delta, rich-wing days only", dict(delta_weights=LOW_DELTA_W, roll_min_wing=0.85))):
                if "rich" in sname and not (period.startswith("Jun") and have_wing):
                    continue
                cfg = Config(name=f"{sname}", start=start, weights=TILT_DTE_W, **extra, **cost)
                if period.startswith("Jun") and have_wing:
                    cfg = replace(cfg, wing_file=str(wf))
                st = stats(run(cfg, daily, hourly, marks).daily)
                rows[(period, cname, sname)] = {k: st[k] for k in ("CAGR %", "Vol %", "Sharpe", "MaxDD %")}
                print("done:", period, cname, sname, flush=True)
    t = pd.DataFrame(rows).T
    md = ["# Retail implementation check\n",
          "## 1. Futures cannot emulate the short options\n",
          "The synthetic short strip holds minus the strip's delta in futures, hourly (no premium, no payoff).\n",
          fut.round(2).to_markdown(),
          "\n## 2. Real options with retail execution costs\n",
          "Half-spread paid on each sale: SPXW max(0.025, 3% of mid); XSP limit orders max(0.05, 10%); XSP crossing "
          "max(0.05, 20%) (SPX-point equivalents; XSP tick 0.01 = 0.10 SPX points, so strikes with a bid below "
          "0.10 are skipped). Hedge with SPY shares / MES: 0.10 points per unit. Jun-2023+ rows use the daily "
          "wing level from real Barchart prices.\n",
          t.round(2).to_markdown()]
    (OUT / "RETAIL.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
