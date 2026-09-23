"""Upside vol premium strategy: sell short-dated far-OTM SPX call strips,
hold to expiry, delta-hedge intraday.

Mechanics (defaults)
--------------------
* Roll: every trading day at the close (``roll="daily"``) or on the first
  trading day of each week (``roll="weekly"``).
* On each roll, for each target expiry (2, 3, 4, 5 trading days ahead, 25% each)
  sell a strip of calls at 1%, 2%, ..., 10% delta (equal notional per strike,
  strikes on the listed 5-point grid).  Notional sold per roll = ``leverage`` x NAV.
* Sale at mid minus half-spread ``max(tc_opt_min, tc_opt_pct * mid)``; strikes
  whose bid would be below the 0.05 minimum tick are not sold.
* Options are held to expiry and cash-settled on the official close (SPXW PM).
* ATM vol: VolVue SPX 10d ATM IV at the close; intraday it moves from the open
  level with a spot-vol beta (-5 on rallies, -7 on sell-offs).
* Delta hedge with the index (futures-like, zero carry) at every mark:
  open, 10:30 ... 15:30, close ("hourly"), or only at the close ("daily"),
  or never ("none").  Hedge cost ``tc_hedge_pts`` index points per unit traded.
* Returns are excess returns (collateral interest not included).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .paths import build_marks
from .vol import ClockParams, SmileParams, Smile, VarianceClock, bs_call


@dataclass(frozen=True)
class Config:
    name: str = "base"
    dtes: tuple = (2, 3, 4, 5)
    weights: tuple = (0.25, 0.25, 0.25, 0.25)
    deltas: tuple = tuple(np.round(np.arange(1, 11) / 100, 2))
    leverage: float = 1.0
    roll: str = "daily"            # daily | weekly
    listed_only: bool = False      # only sell expiries SPX actually listed at the time
    hedge: str = "hourly"          # hourly | daily | none
    strike_step: float = 5.0
    min_bid: float = 0.05
    tc_opt_min: float = 0.025      # min half-spread paid on option sale (index pts)
    tc_opt_pct: float = 0.03       # half-spread as fraction of mid
    tc_hedge_pts: float = 0.15     # ES half-spread + fees, index pts per unit traded
    atm_source: str = "volvue"     # volvue (SPX 10d ATM IV) | vix9d (VIX9D / atm_ratio)
    svb_up: float = -5.0           # intraday spot-vol beta, d ln(ATM) / d ln(S), rallies (2011-26 fit)
    svb_down: float = -7.0         # ... sell-offs
    smile: SmileParams = field(default_factory=SmileParams)
    clock: ClockParams = field(default_factory=ClockParams)
    use_real_hourly: bool = True
    seed: int = 7
    start: str = "2011-01-03"
    end: str | None = None


@dataclass
class Result:
    cfg: Config
    daily: pd.DataFrame      # per-day NAV + P&L attribution
    intraday: pd.Series      # NAV at every mark
    trades: pd.DataFrame     # one row per option sold


def listed_expiries(dates: pd.DatetimeIndex) -> np.ndarray:
    """SPX PM-settled short-dated expiries by listing date: Fridays (weeklies) and
    month-end throughout; Wednesdays from 2016-02-23; Mondays from 2016-08-15;
    Tuesdays from 2022-04-18; Thursdays from 2022-05-11.  A holiday Friday rolls to
    the last trading day of the week."""
    wd = dates.weekday
    s = pd.Series(dates, index=dates)
    week_last = s.groupby([dates.isocalendar().year.values, dates.isocalendar().week.values]).transform("max")
    month_last = s.groupby([dates.year, dates.month]).transform("max")
    ok = (s == week_last).values | (s == month_last).values
    ok |= (wd == 2) & (dates >= "2016-02-23")
    ok |= (wd == 0) & (dates >= "2016-08-15")
    ok |= (wd == 1) & (dates >= "2022-04-18")
    ok |= (wd == 3) & (dates >= "2022-05-11")
    return ok


def atm_vols(mkt: pd.DataFrame, cfg: Config, clock: VarianceClock):
    """Business-time ATM vol at the open (used for intraday marks) and at the close.

    volvue: close = VolVue SPX 10d ATM mean IV (bad prints / gaps replaced by
            VIX9D x local VolVue/VIX9D ratio); open = previous close scaled by the
            VIX9D open / previous VIX9D close move (no look-ahead).
    vix9d : VIX9D / atm_ratio at open and close.
    """
    v9o, v9c = mkt.vix9d_open.values / 100, mkt.vix9d_close.values / 100
    if cfg.atm_source == "vix9d":
        k = clock.cal_to_business(1.0, 9) / cfg.smile.atm_ratio
        return v9o * k, v9c * k
    if cfg.atm_source != "volvue":
        raise ValueError(cfg.atm_source)
    atm = mkt["atm10"] / 100
    ratio = np.log(atm / mkt.vix9d_close * 100)
    local = ratio.rolling(21, min_periods=5).median().ffill().fillna(np.log(1 / cfg.smile.atm_ratio))
    bad = atm.isna() | ((ratio - local).abs() > 0.35)
    atm = atm.where(~bad, mkt.vix9d_close / 100 * np.exp(local)).values
    k = clock.cal_to_business(1.0, 10)
    close = atm * k
    open_ = np.concatenate([[close[0]], close[:-1] * v9o[1:] / v9c[:-1]])
    return open_, close


def run(cfg: Config, daily_mkt: pd.DataFrame, hourly_mkt: pd.DataFrame | None, marks=None) -> Result:
    mkt = daily_mkt.loc[cfg.start:cfg.end] if cfg.end else daily_mkt.loc[cfg.start:]
    dates = mkt.index
    N = len(dates)
    if marks is None:
        marks = build_marks(mkt, hourly_mkt, seed=cfg.seed, f_on=cfg.clock.f_on,
                            use_real=cfg.use_real_hourly)
    clock = VarianceClock(dates.values, cfg.clock)
    smile = Smile(cfg.smile)
    sig_open, sig_close = atm_vols(mkt, cfg, clock)

    if cfg.roll == "daily":
        roll_day = np.ones(N, bool)
    elif cfg.roll == "weekly":
        wk = dates.isocalendar().week.values * 10000 + dates.isocalendar().year.values
        roll_day = np.concatenate([[True], wk[1:] != wk[:-1]])
    else:
        raise ValueError(cfg.roll)

    listed = listed_expiries(dates) if cfg.listed_only else np.ones(N, bool)
    deltas = np.asarray(cfg.deltas, float)
    nstrk = len(deltas)
    cap = N * len(cfg.dtes) * nstrk
    R = {k: np.zeros(cap) for k in ("K", "q", "mid", "bid", "iv", "delta0", "spot0",
                                     "hunits", "hpnl", "payoff", "sig_atm")}
    Ri = {k: np.zeros(cap, int) for k in ("d0", "exp", "dte")}
    Rt = np.zeros(cap)                   # target delta
    n_rec = 0
    active = np.zeros(0, int)

    nav0 = 100.0
    cash = nav0
    h = 0.0                              # hedge, units of index (long > 0)
    last_S = marks[0].spot[0]

    cols = ["nav", "spot", "prem_mid", "opt_cost", "payoff", "hedge_pnl", "hedge_cost",
            "liab", "short_notional", "net_delta_units", "n_sold", "n_skipped"]
    out = np.zeros((N, len(cols)))
    intraday_t, intraday_nav = [], []

    for d in range(N):
        dm = marks[d]
        prem_mid = opt_cost = payoff_tot = hpnl_tot = hcost_tot = 0.0
        n_sold = n_skip = 0
        nmk = len(dm.u)
        for i in range(nmk):
            u, S = float(dm.u[i]), float(dm.spot[i])
            is_close = i == nmk - 1
            dS = S - last_S
            hpnl_tot += h * dS
            cash += h * dS
            if active.size:
                R["hpnl"][active] += R["hunits"][active] * dS
            last_S = S
            if is_close:
                sig = sig_close[d]
            else:                                  # open-level vol moved by spot-vol beta
                x = np.log(S / dm.spot[0])
                sig = sig_open[d] * float(np.clip(np.exp((cfg.svb_up if x > 0 else cfg.svb_down) * x), 0.4, 2.5))

            if is_close:
                # --- settle options expiring today at the official close
                exp_now = active[Ri["exp"][active] == d]
                if exp_now.size:
                    po = R["q"][exp_now] * np.maximum(S - R["K"][exp_now], 0.0)
                    R["payoff"][exp_now] = po
                    payoff_tot += po.sum()
                    cash -= po.sum()
                    R["hunits"][exp_now] = 0.0
                    active = active[Ri["exp"][active] != d]
                # --- roll: sell new strips
                if roll_day[d]:
                    if active.size:
                        T = clock.T(d, 1.0, Ri["exp"][active])
                        K = R["K"][active]
                        liab = np.sum(R["q"][active] * bs_call(S, K, smile.vol(K, S, sig, T), T)[0])
                    else:
                        liab = 0.0
                    nav = cash - liab
                    tranches = [(dte, w) for dte, w in zip(cfg.dtes, cfg.weights)
                                if d + dte < N and listed[d + dte]]
                    wsum = sum(w for _, w in tranches)
                    for dte, w in tranches:
                        e = d + dte
                        if cfg.listed_only:          # keep total notional per roll constant
                            w = w * sum(cfg.weights) / wsum
                        T = float(clock.T(d, 1.0, e))
                        K = smile.strike_for_delta(deltas, S, sig, T)
                        K = np.maximum(np.round(K / cfg.strike_step) * cfg.strike_step,
                                       np.ceil(S / cfg.strike_step) * cfg.strike_step)
                        iv = smile.vol(K, S, sig, T)
                        mid, dl, _ = bs_call(S, K, iv, T)
                        hs = np.maximum(cfg.tc_opt_min, cfg.tc_opt_pct * mid)
                        bid = mid - hs
                        ok = bid >= cfg.min_bid
                        q = w * cfg.leverage * nav / S / nstrk
                        n_skip += int((~ok).sum())
                        idx = np.arange(n_rec, n_rec + ok.sum())
                        n_rec += ok.sum()
                        if idx.size == 0:
                            continue
                        n_sold += idx.size
                        for k, v in (("K", K[ok]), ("mid", mid[ok]), ("bid", bid[ok]), ("iv", iv[ok]),
                                     ("delta0", dl[ok])):
                            R[k][idx] = v
                        R["q"][idx] = q
                        R["spot0"][idx] = S
                        R["sig_atm"][idx] = sig
                        Ri["d0"][idx], Ri["exp"][idx], Ri["dte"][idx] = d, e, dte
                        Rt[idx] = deltas[ok]
                        prem_mid += q * mid[ok].sum()
                        opt_cost += q * hs[ok].sum()
                        cash += q * bid[ok].sum()
                        active = np.concatenate([active, idx])

            # --- mark to market + delta hedge
            if active.size:
                T = clock.T(d, u, Ri["exp"][active])
                K = R["K"][active]
                px, dl, _ = bs_call(S, K, smile.vol(K, S, sig, T), T)
                pos_delta = R["q"][active] * dl          # hedge units per position
                liab = float(np.sum(R["q"][active] * px))
            else:
                pos_delta = np.zeros(0)
                liab = 0.0
            do_hedge = cfg.hedge == "hourly" or (cfg.hedge == "daily" and is_close)
            if do_hedge:
                target = float(pos_delta.sum())
                c = abs(target - h) * cfg.tc_hedge_pts
                hcost_tot += c
                cash -= c
                h = target
                if active.size:
                    R["hunits"][active] = pos_delta
            intraday_t.append(dm.date + pd.Timedelta(hours=9.5 + 6.5 * u))
            intraday_nav.append(cash - liab)

        short_notional = float(R["q"][active].sum() * S) if active.size else 0.0
        out[d] = [cash - liab, S, prem_mid, opt_cost, payoff_tot, hpnl_tot, hcost_tot, liab,
                  short_notional, h - (pos_delta.sum() if active.size else 0.0), n_sold, n_skip]

    daily = pd.DataFrame(out, index=dates, columns=cols)
    daily["ret"] = daily.nav.pct_change().fillna(daily.nav.iloc[0] / nav0 - 1)
    daily["real_hourly"] = [m.real for m in marks]
    n = n_rec
    trades = pd.DataFrame({
        "date": dates[Ri["d0"][:n]], "expiry": dates[Ri["exp"][:n]], "dte": Ri["dte"][:n],
        "target_delta": Rt[:n], "K": R["K"][:n], "spot0": R["spot0"][:n], "q": R["q"][:n],
        "mid": R["mid"][:n], "bid": R["bid"][:n], "iv": R["iv"][:n], "sig_atm": R["sig_atm"][:n],
        "delta0": R["delta0"][:n], "payoff_unit": R["payoff"][:n] / np.where(R["q"][:n] > 0, R["q"][:n], 1),
        "hedge_pnl": R["hpnl"][:n],
    })
    trades["S_T"] = mkt.spx_close.values[Ri["exp"][:n]]
    trades["itm"] = trades.S_T > trades.K
    trades["pnl_static"] = trades.q * (trades.bid - trades.payoff_unit)
    trades["pnl_hedged"] = trades.pnl_static + trades.hedge_pnl
    intraday = pd.Series(intraday_nav, index=pd.DatetimeIndex(intraday_t), name="nav")
    return Result(cfg, daily, intraday, trades)
