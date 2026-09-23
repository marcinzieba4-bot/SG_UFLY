"""Upside vol premium strategy: sell short-dated far-OTM SPX call strips,
hold to expiry, delta-hedge intraday.

Mechanics (defaults)
--------------------
* Roll: every trading day at the close (``roll="daily"``) or on the first
  trading day of each week (``roll="weekly"``).
* On each roll, for each target expiry (``dtes`` trading days ahead, ``weights``)
  sell a strip of calls at the ``deltas`` targets (weighted by ``delta_weights``,
  equal if None), strikes on the listed 5-point grid.  Notional sold per roll =
  ``leverage`` x NAV.
* Sale at mid minus half-spread ``max(tc_opt_min, tc_opt_pct * mid)``; strikes
  whose bid would be below the 0.05 minimum tick are not sold.
* Options are held to expiry and cash-settled on the official close (SPXW PM).
* Vol surface: VolVue SPXW 10-day ATM IV at the close -> business time over the
  exact 10-day window -> short-end factor for the option's tenor (VIX1D / VIX9D)
  -> call-wing smile fitted to the SPXW chain.  Intraday the ATM level moves from
  the open with a spot-vol beta (-5 on rallies, -7 on sell-offs).
* Delta hedge with the index (futures-like, zero carry) at every mark:
  open, 10:30 ... 15:30, close ("hourly"), or only at the close ("daily"),
  or never ("none").  Hedge cost ``tc_hedge_pts`` index points per unit traded.
* ``mode="replica"``: the call strip is only *virtual*; the strategy instead
  sells ATM calls expiring in ``replica_dte`` days, sized each close to match the
  dollar gamma of the virtual strip ("artificial 5-10 delta" built from ATM).
* Returns are excess returns (collateral interest not included).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .paths import build_marks
from .vol import ClockParams, SmileParams, Smile, VarianceClock, bs_call, bs_gamma


@dataclass(frozen=True)
class Config:
    name: str = "base"
    dtes: tuple = (2, 3, 4, 5)
    weights: tuple = (0.25, 0.25, 0.25, 0.25)
    deltas: tuple = tuple(np.round(np.arange(1, 11) / 100, 2))
    delta_weights: tuple | None = None   # per-strike weights (normalised); None = equal
    leverage: float = 1.0
    roll: str = "daily"            # daily | weekly
    listed_only: bool = False      # only sell expiries SPX actually listed at the time
    hedge: str = "hourly"          # hourly | daily | none
    strike_step: float = 5.0
    min_bid: float = 0.05
    tc_opt_min: float = 0.025      # min half-spread paid on option sale (index pts)
    tc_opt_pct: float = 0.03       # half-spread as fraction of mid
    tc_hedge_pts: float = 0.15     # ES half-spread + fees, index pts per unit traded
    atm_source: str = "volvue_w"   # volvue_w (SPXW 10d; SPX before 2014-04) | volvue (SPX monthly root) | vix9d
    short_end: bool = True         # scale 10d ATM to the option's tenor with VIX1D / VIX9D
    rho_default: float = 0.86      # median VIX1D / VIX9D (2023-26), used before VIX1D exists
    atm_mult: float = 0.973        # ATM vol multiplier matching SPXW chain bids (validate_chain.py, 2026-09-22)
    svb_up: float = -5.0           # intraday spot-vol beta, d ln(ATM) / d ln(S), rallies (2011-26 fit)
    svb_down: float = -7.0         # ... sell-offs
    wing_pre2022: float = 1.0      # stress: call-wing vol multiplier before 2022-05 (pre daily expiries / 0DTE boom)
    wing_vol_slope: float = 0.0    # stress: wing multiplier falls by this x (ATM - 12%) when vol is high (floor 0.75)
    stress: tuple = (-0.10, -0.05, 0.03, 0.05, 0.08, 0.12)   # instantaneous gap shocks evaluated at each close
    mode: str = "strip"            # strip | replica
    replica_dte: int = 1
    smile: SmileParams = field(default_factory=SmileParams)
    clock: ClockParams = field(default_factory=ClockParams)
    use_real_hourly: bool = True
    seed: int = 7
    start: str = "2011-01-03"
    end: str | None = "2026-09-22"


@dataclass
class Result:
    cfg: Config
    daily: pd.DataFrame      # per-day NAV + P&L attribution
    intraday: pd.Series      # NAV at every mark
    trades: pd.DataFrame     # one row per option sold (real and, in replica mode, virtual)


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


def _clean(atm: pd.Series, v9: pd.Series, fallback_ratio: float) -> pd.Series:
    """Replace gaps / bad prints (>35% off the local VolVue/VIX9D ratio) by VIX9D x local ratio."""
    ratio = np.log(atm / v9)
    local = ratio.rolling(21, min_periods=5).median().ffill().fillna(np.log(1 / fallback_ratio))
    bad = atm.isna() | ((ratio - local).abs() > 0.35)
    return atm.where(~bad, v9 * np.exp(local))


def atm_vols(mkt: pd.DataFrame, cfg: Config, clock: VarianceClock):
    """10-day ATM level in business time at the open (intraday marks) and close,
    plus the per-date VIX1D/VIX9D ratio and the 10-day window size (eff. days)."""
    v9o, v9c = mkt.vix9d_open / 100, mkt.vix9d_close / 100
    eff10 = clock.window_eff(mkt.index.values, 10)
    if cfg.atm_source == "vix9d":
        close = v9c / cfg.smile.atm_ratio * np.sqrt((9 / 365) * 252 / clock.window_eff(mkt.index.values, 9))
    else:
        spx = _clean(mkt["atm10"] / 100, v9c, cfg.smile.atm_ratio)
        if cfg.atm_source == "volvue":
            atm = spx
        elif cfg.atm_source == "volvue_w":
            spxw = mkt["atm10w"] / 100
            first = spxw.first_valid_index()
            atm = spx.copy()
            if first is not None:        # SPXW where it exists (cleaned), SPX monthly root before
                atm.loc[first:] = _clean(spxw.loc[first:], v9c.loc[first:], cfg.smile.atm_ratio)
        else:
            raise ValueError(cfg.atm_source)
        close = atm * np.sqrt((10 / 365) * 252 / eff10)
    close = close.values
    open_ = np.concatenate([[close[0]], close[:-1] * v9o.values[1:] / v9c.values[:-1]])
    rho = (mkt.vix1d_close / mkt.vix9d_close).clip(0.4, 1.4).fillna(cfg.rho_default).values
    return open_, close, rho, eff10


def run(cfg: Config, daily_mkt: pd.DataFrame, hourly_mkt: pd.DataFrame | None, marks=None) -> Result:
    mkt = daily_mkt.loc[cfg.start:cfg.end] if cfg.end else daily_mkt.loc[cfg.start:]
    dates = mkt.index
    N = len(dates)
    if marks is None:
        marks = build_marks(mkt, hourly_mkt, seed=cfg.seed, f_on=cfg.clock.f_on,
                            use_real=cfg.use_real_hourly)
    marks = marks[:N]
    clock = VarianceClock(dates.values, cfg.clock)
    smile = Smile(cfg.smile)
    sig_open, sig_close, rho, eff10 = atm_vols(mkt, cfg, clock)
    lam = (eff10 - rho ** 2) / np.maximum(eff10 - 1, 1e-6)   # keeps the 10d average variance unchanged
    replica = cfg.mode == "replica"
    wm = np.where(dates < "2022-05-11", cfg.wing_pre2022, 1.0) * \
        np.clip(1.0 - cfg.wing_vol_slope * np.maximum(sig_close - 0.12, 0.0), 0.75, 1.0)

    def atm_for(sig, d, T):
        """ATM vol for options with business time-to-expiry T (years), at 10d level `sig`."""
        T = np.atleast_1d(T)
        if not cfg.short_end:
            return np.full_like(T, sig * cfg.atm_mult, dtype=float)
        x = np.maximum(T * 252, 1e-6)
        k2 = (rho[d] ** 2 * np.minimum(x, 1) + lam[d] * np.maximum(x - 1, 0)) / x
        return sig * cfg.atm_mult * np.sqrt(k2)

    if cfg.roll == "daily":
        roll_day = np.ones(N, bool)
    elif cfg.roll == "weekly":
        wk = dates.isocalendar().week.values * 10000 + dates.isocalendar().year.values
        roll_day = np.concatenate([[True], wk[1:] != wk[:-1]])
    else:
        raise ValueError(cfg.roll)

    listed = listed_expiries(dates) if cfg.listed_only else np.ones(N, bool)
    deltas = np.asarray(cfg.deltas, float)
    dw = np.ones(len(deltas)) if cfg.delta_weights is None else np.asarray(cfg.delta_weights, float)
    dw = dw / dw.sum()
    cap = N * (len(cfg.dtes) * len(deltas) + 1)
    R = {k: np.zeros(cap) for k in ("K", "q", "mid", "bid", "iv", "delta0", "spot0",
                                     "hunits", "hpnl", "payoff", "sig_atm")}
    Ri = {k: np.zeros(cap, int) for k in ("d0", "exp", "dte")}
    Rt = np.zeros(cap)                   # target delta
    Rreal = np.zeros(cap, bool)
    n_rec = 0
    active = np.zeros(0, int)            # real positions (in NAV, hedged)
    virt = np.zeros(0, int)              # virtual strip (replica mode only)

    def price(idx, d, u, S, sig):
        T = clock.T(d, u, Ri["exp"][idx])
        K = R["K"][idx]
        iv = smile.vol(K, S, atm_for(sig, d, T), T, wm[d])
        return bs_call(S, K, iv, T), iv, T

    def add(K, mid, bid, iv, dl, q, S, sig, d, e, dte, tgt, real):
        nonlocal n_rec
        idx = np.arange(n_rec, n_rec + len(K))
        n_rec += len(K)
        R["K"][idx], R["mid"][idx], R["bid"][idx], R["iv"][idx], R["delta0"][idx] = K, mid, bid, iv, dl
        R["q"][idx], R["spot0"][idx], R["sig_atm"][idx] = q, S, sig
        Ri["d0"][idx], Ri["exp"][idx], Ri["dte"][idx] = d, e, dte
        Rt[idx], Rreal[idx] = tgt, real
        return idx

    nav0 = 100.0
    cash = nav0
    h = 0.0                              # hedge, units of index (long > 0)
    last_S = marks[0].spot[0]

    cols = ["nav", "spot", "prem_mid", "opt_cost", "payoff", "hedge_pnl", "hedge_cost",
            "liab", "short_notional", "net_delta_units", "n_sold", "n_skipped", "atm_2d", "atm_5d"]
    cols += [f"stress_{x:+.0%}" for x in cfg.stress]
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
                for book in ("real", "virt"):
                    ids = active if book == "real" else virt
                    exp_now = ids[Ri["exp"][ids] == d]
                    if exp_now.size:
                        po = R["q"][exp_now] * np.maximum(S - R["K"][exp_now], 0.0)
                        R["payoff"][exp_now] = po
                        if book == "real":
                            payoff_tot += po.sum()
                            cash -= po.sum()
                            R["hunits"][exp_now] = 0.0
                            active = active[Ri["exp"][active] != d]
                        else:
                            virt = virt[Ri["exp"][virt] != d]
                liab = float(np.sum(R["q"][active] * price(active, d, 1.0, S, sig)[0][0])) if active.size else 0.0
                nav = cash - liab
                # --- roll: sell new strips (real, or virtual in replica mode)
                if roll_day[d]:
                    tranches = [(dte, w) for dte, w in zip(cfg.dtes, cfg.weights)
                                if d + dte < N and listed[d + dte]]
                    wsum = sum(w for _, w in tranches)
                    for dte, w in tranches:
                        e = d + dte
                        if cfg.listed_only:          # keep total notional per roll constant
                            w = w * sum(cfg.weights) / wsum
                        T = float(clock.T(d, 1.0, e))
                        a = float(atm_for(sig, d, T)[0])
                        K = smile.strike_for_delta(deltas, S, a, T)
                        K = np.maximum(np.round(K / cfg.strike_step) * cfg.strike_step,
                                       np.ceil(S / cfg.strike_step) * cfg.strike_step)
                        iv = smile.vol(K, S, a, T, wm[d])
                        mid, dl, _ = bs_call(S, K, iv, T)
                        hs = np.maximum(cfg.tc_opt_min, cfg.tc_opt_pct * mid)
                        bid = mid - hs
                        ok = bid >= cfg.min_bid
                        q = w * cfg.leverage * nav / S * dw[ok]
                        n_skip += int((~ok).sum())
                        n_sold += int(ok.sum())
                        if not ok.any():
                            continue
                        idx = add(K[ok], mid[ok], bid[ok], iv[ok], dl[ok], q, S, a, d, e, dte, deltas[ok], not replica)
                        if replica:
                            virt = np.concatenate([virt, idx])
                        else:
                            prem_mid += float(q @ mid[ok])
                            opt_cost += float(q @ hs[ok])
                            cash += float(q @ bid[ok])
                            active = np.concatenate([active, idx])
                # --- replica: sell ATM calls matching the virtual strip's dollar gamma
                if replica and virt.size and d + cfg.replica_dte < N:
                    (px_v, _, _), iv_v, T_v = price(virt, d, 1.0, S, sig)
                    g_target = float(np.sum(R["q"][virt] * bs_gamma(S, R["K"][virt], iv_v, T_v)))
                    e = d + cfg.replica_dte
                    T = float(clock.T(d, 1.0, e))
                    a = float(atm_for(sig, d, T)[0])
                    K = np.array([np.ceil(S / cfg.strike_step) * cfg.strike_step])
                    iv = smile.vol(K, S, a, T, wm[d])
                    mid, dl, _ = bs_call(S, K, iv, T)
                    hs = np.maximum(cfg.tc_opt_min, cfg.tc_opt_pct * mid)
                    q = g_target / float(bs_gamma(S, K, iv, T)[0])
                    idx = add(K, mid, mid - hs, iv, dl, q, S, a, d, e, cfg.replica_dte, np.array([0.5]), True)
                    prem_mid += q * float(mid[0])
                    opt_cost += q * float(hs[0])
                    cash += q * float(mid[0] - hs[0])
                    active = np.concatenate([active, idx])
                    n_sold += 1

            # --- mark to market + delta hedge (real book)
            if active.size:
                (px, dl, _), _, _ = price(active, d, u, S, sig)
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

        # instantaneous gap shocks on the closing book (vol moves with the spot-vol beta), % of NAV
        stress = []
        for x in cfg.stress:
            if not active.size:
                stress.append(0.0)
                continue
            S2 = S * (1 + x)
            sig2 = sig * float(np.clip(np.exp((cfg.svb_up if x > 0 else cfg.svb_down) * np.log1p(x)), 0.4, 2.5))
            px2 = price(active, d, 1.0, S2, sig2)[0][0]
            dv = float(np.sum(R["q"][active] * px2)) - liab
            stress.append(100 * (h * (S2 - S) - dv) / (cash - liab))
        short_notional = float(R["q"][active].sum() * S) if active.size else 0.0
        a2 = float(atm_for(sig_close[d], d, np.array([2 / 252]))[0])
        a5 = float(atm_for(sig_close[d], d, np.array([5 / 252]))[0])
        out[d] = [cash - liab, S, prem_mid, opt_cost, payoff_tot, hpnl_tot, hcost_tot, liab,
                  short_notional, h - (pos_delta.sum() if active.size else 0.0), n_sold, n_skip, a2, a5, *stress]

    daily = pd.DataFrame(out, index=dates, columns=cols)
    daily["ret"] = daily.nav.pct_change().fillna(daily.nav.iloc[0] / nav0 - 1)
    daily["real_hourly"] = [m.real for m in marks]
    n = n_rec
    trades = pd.DataFrame({
        "date": dates[Ri["d0"][:n]], "expiry": dates[Ri["exp"][:n]], "dte": Ri["dte"][:n],
        "target_delta": Rt[:n], "K": R["K"][:n], "spot0": R["spot0"][:n], "q": R["q"][:n],
        "mid": R["mid"][:n], "bid": R["bid"][:n], "iv": R["iv"][:n], "sig_atm": R["sig_atm"][:n],
        "delta0": R["delta0"][:n], "payoff_unit": R["payoff"][:n] / np.where(R["q"][:n] > 0, R["q"][:n], 1),
        "hedge_pnl": R["hpnl"][:n], "real": Rreal[:n],
    })
    trades["S_T"] = mkt.spx_close.values[Ri["exp"][:n]]
    trades["itm"] = trades.S_T > trades.K
    trades["pnl_static"] = trades.q * (trades.bid - trades.payoff_unit)
    trades["pnl_hedged"] = trades.pnl_static + trades.hedge_pnl
    intraday = pd.Series(intraday_nav, index=pd.DatetimeIndex(intraday_t), name="nav")
    return Result(cfg, daily, intraday, trades)
