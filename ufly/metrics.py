"""Performance statistics."""
from __future__ import annotations

import numpy as np
import pandas as pd


def stats(daily: pd.DataFrame, intraday: pd.Series | None = None) -> dict:
    r = daily.ret
    nav = daily.nav
    yrs = len(r) / 252
    cagr = (nav.iloc[-1] / 100.0) ** (1 / yrs) - 1
    vol = r.std() * np.sqrt(252)
    dd = nav / nav.cummax() - 1
    r5 = nav.pct_change(5)
    out = {
        "CAGR %": 100 * cagr,
        "Vol %": 100 * vol,
        "Sharpe": r.mean() / r.std() * np.sqrt(252),
        "Sortino": r.mean() / r[r < 0].std() * np.sqrt(252),
        "MaxDD %": 100 * dd.min(),
        "Calmar": cagr / -dd.min() if dd.min() < 0 else np.nan,
        "Worst day %": 100 * r.min(),
        "Worst 5d %": 100 * r5.min(),
        "Best day %": 100 * r.max(),
        "Skew": r.skew(),
        "Kurt": r.kurt(),
        "Hit rate %": 100 * (r > 0).mean(),
    }
    if intraday is not None:
        idd = intraday / intraday.cummax() - 1
        out["MaxDD intraday %"] = 100 * idd.min()
    return out


def yearly(daily: pd.DataFrame) -> pd.Series:
    nav = daily.nav
    first = pd.Series([100.0], index=[nav.index[0] - pd.Timedelta(days=1)])
    y = pd.concat([first, nav]).groupby(lambda x: x.year).last()
    return 100 * y.pct_change().dropna()


def attribution(daily: pd.DataFrame) -> dict:
    """Cumulative P&L split, in % of starting NAV (additive, not compounded)."""
    nav0 = 100.0
    total = daily.nav.iloc[-1] - nav0
    return {
        "Premium @mid": daily.prem_mid.sum() / nav0 * 100,
        "Option t-cost": -daily.opt_cost.sum() / nav0 * 100,
        "Payoff paid": -daily.payoff.sum() / nav0 * 100,
        "Delta hedge P&L": daily.hedge_pnl.sum() / nav0 * 100,
        "Hedge t-cost": -daily.hedge_cost.sum() / nav0 * 100,
        "Open MTM": -daily.liab.iloc[-1] / nav0 * 100,
        "Total": total / nav0 * 100,
    }
