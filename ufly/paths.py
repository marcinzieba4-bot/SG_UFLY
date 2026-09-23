"""Intraday (hourly) SPX marks per trading day.

Each trading day gets a list of marks: open (u=0), hourly marks 10:30..15:30,
and the official close (u=1, the SPXW PM settlement print).

* Real   : Yahoo 1h bars (available from late 2023).
* Synthetic (earlier history): a Brownian bridge from the real open to the real
  close, with intraday variance from the day's Parkinson (high/low) estimator,
  clipped to the real [low, high] range.  Yahoo's SPX open is stale (= previous
  close) on many pre-2017 days; there the open is imputed by bridging the
  close-to-close move with an overnight variance share `f_on`.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

N_INTRADAY = 6  # 10:30 .. 15:30


@dataclass
class DayMarks:
    date: pd.Timestamp
    u: np.ndarray       # session fraction of each mark, 0=open ... 1=close
    spot: np.ndarray    # SPX at each mark (last = official close)
    real: bool          # True if from actual hourly bars


def _synthetic_day(rng, prev_close, o, h, l, c, stale_open, f_on):
    lnL, lnH = np.log(l), np.log(h)
    park = (np.log(h / l)) ** 2 / (4 * np.log(2))          # intraday variance
    if stale_open:
        day_var = park / (1 - f_on)
        r = np.log(c / prev_close)
        x = f_on * r + np.sqrt(f_on * (1 - f_on) * day_var) * rng.standard_normal()
        o = float(np.exp(np.clip(np.log(prev_close) + x, lnL, lnH)))
    u = np.linspace(0, 1, N_INTRADAY + 2)
    x0, x1 = np.log(o), np.log(c)
    # sequential Brownian bridge on the interior marks
    path = [x0]
    for i in range(1, len(u) - 1):
        du, rem = u[i] - u[i - 1], 1.0 - u[i - 1]
        mean = path[-1] + (x1 - path[-1]) * du / rem
        var = park * du * (rem - du) / rem
        path.append(mean + np.sqrt(max(var, 0.0)) * rng.standard_normal())
    path.append(x1)
    path = np.clip(np.array(path), lnL, lnH)
    path[-1] = x1
    return u, np.exp(path), o


def build_marks(daily: pd.DataFrame, hourly: pd.DataFrame | None, seed: int = 7,
                f_on: float = 0.20, use_real: bool = True) -> list[DayMarks]:
    rng = np.random.default_rng(seed)
    hourly_days = {}
    if hourly is not None and use_real:
        for day, g in hourly.groupby(hourly.index.normalize()):
            hourly_days[day] = g
    out = []
    prev_close = None
    for dt, row in daily.iterrows():
        o, h, l, c = row.spx_open, row.spx_high, row.spx_low, row.spx_close
        if dt in hourly_days:
            g = hourly_days[dt]
            spot = np.concatenate([[g.Open.iloc[0]], g.Close.values[:-1], [c]])
            u = np.linspace(0, 1, len(spot))
            out.append(DayMarks(dt, u, spot, True))
        else:
            stale = prev_close is not None and abs(o / prev_close - 1) < 2e-4 and dt.year < 2017
            u, spot, _ = _synthetic_day(rng, prev_close if prev_close else o, o, h, l, c, stale, f_on)
            out.append(DayMarks(dt, u, spot, False))
        prev_close = c
    return out
