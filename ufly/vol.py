"""Option pricing, short-dated SPX smile model and the business-time variance clock.

Smile
-----
Implied vol is parameterised in *normalised moneyness*

    z = ln(K / F) / (sigma_atm * sqrt(T))

so the same shape applies at every tenor/vol level (sticky-delta regime):

    sigma(z) = sigma_atm * f(z)
    f(z) = 1 + a z + b_call z^2     (z >= 0, call wing)
    f(z) = 1 + a z + b_put  z^2     (z <  0, put wing)

(a, b_call) are solved from two call-wing anchors (vol of the 10-delta and
1-delta call as a ratio of ATM vol); b_put from the 10-delta put anchor.

ATM level
---------
Default: VolVue SPXW 10-day ATM implied vol (see volvue.py), converted to
business time over the exact 10-calendar-day window, then scaled to the
option's own tenor with a short-end factor from VIX1D / VIX9D (backtest.py).
Proxy: VIX9D / atm_ratio (VolVue median VIX9D / ATM10 = 1.17, 2011-2026).

Variance clock
--------------
Options are priced in business time: each trading day carries one unit of
variance, split into an overnight part (close->open, incl. weekend/holiday
news: `f_on + w_nt * non_trading_days`) and an intraday part (1 - f_on)
spread evenly across the session.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.special import ndtr, ndtri

SQ2PI = np.sqrt(2.0 * np.pi)


def npdf(x):
    return np.exp(-0.5 * x * x) / SQ2PI


@dataclass(frozen=True)
class SmileParams:
    # call-wing anchors fitted to the CBOE SPXW chain, 2026-09-22 close, 2-5DTE
    # (v1 of this backtest assumed 0.92 / 1.02)
    call10: float = 1.01   # 10-delta call vol / ATM vol
    call1: float = 1.16    # 1-delta call vol / ATM vol
    put10: float = 1.30    # 10-delta put vol / ATM vol (only used for ITM calls)
    atm_ratio: float = 1.17  # VIX9D / ATM vol (VolVue median 2011-26), proxy mode only
    z_cap: float = 4.0     # smile is flat beyond |z| > z_cap
    floor: float = 0.5     # min vol ratio

    def coeffs(self) -> tuple[float, float, float]:
        z10, z1 = ndtri(0.90), ndtri(0.99)  # approx |d1| of 10d / 1d options
        A = np.array([[z10, z10 ** 2], [z1, z1 ** 2]])
        a, bc = np.linalg.solve(A, [self.call10 - 1.0, self.call1 - 1.0])
        bp = (self.put10 - 1.0 + a * z10) / z10 ** 2
        return float(a), float(bc), float(bp)


class Smile:
    def __init__(self, p: SmileParams = SmileParams()):
        self.p = p
        self.a, self.bc, self.bp = p.coeffs()

    def f(self, z):
        z = np.clip(z, -self.p.z_cap, self.p.z_cap)
        b = np.where(z >= 0, self.bc, self.bp)
        return np.maximum(1.0 + self.a * z + b * z * z, self.p.floor)

    def vol(self, K, F, sig_atm, T, wing_mult=1.0):
        """Smile vol.  `wing_mult` rescales call-wing vols: ramps from 1 at ATM to
        `wing_mult` at the 10-delta point (z = 1.28) and beyond."""
        s = sig_atm * np.sqrt(T)
        z = np.log(K / F) / s
        ramp = np.clip(z / 1.2816, 0.0, 1.0)
        return sig_atm * self.f(z) * (1.0 + (wing_mult - 1.0) * ramp)

    def strike_for_delta(self, delta, F, sig_atm, T, wing_mult=1.0, iters: int = 60):
        """Call strike whose BS delta (at its own smile vol, incl. `wing_mult`) equals `delta`."""
        s = sig_atm * np.sqrt(T)
        delta = np.asarray(delta, dtype=float)
        lo = np.zeros_like(delta)
        hi = np.full_like(delta, 3.0 * self.p.z_cap)
        for _ in range(iters):
            mid = 0.5 * (lo + hi)
            fz = self.f(mid) * (1.0 + (wing_mult - 1.0) * np.clip(mid / 1.2816, 0.0, 1.0))
            d1 = -mid / fz + 0.5 * s * fz
            too_high = ndtr(d1) > delta          # delta still too big -> go further OTM
            lo = np.where(too_high, mid, lo)
            hi = np.where(too_high, hi, mid)
        z = 0.5 * (lo + hi)
        return F * np.exp(z * s)


def bs_gamma(F, K, sig, T):
    T = np.maximum(T, 1e-10)
    st = sig * np.sqrt(T)
    d1 = (np.log(F / K) + 0.5 * st * st) / st
    return npdf(d1) / (F * st)


def bs_call(F, K, sig, T):
    """Undiscounted Black call price, delta, vega (per 1.00 vol). Vectorised."""
    T = np.maximum(T, 1e-10)
    st = sig * np.sqrt(T)
    d1 = (np.log(F / K) + 0.5 * st * st) / st
    d2 = d1 - st
    price = F * ndtr(d1) - K * ndtr(d2)
    return price, ndtr(d1), F * np.sqrt(T) * npdf(d1)


@dataclass(frozen=True)
class ClockParams:
    f_on: float = 0.20     # overnight share of a trading day's variance (SPX 2017-26: ~0.22)
    w_nt: float = 0.05     # variance per weekend/holiday day, in trading days (SPXW chain fit 0-0.05;
                           # realised SPX 2011-26: 0.02-0.07)


class VarianceClock:
    """Business-time clock in 'effective trading days' over a trading calendar."""

    def __init__(self, dates, p: ClockParams = ClockParams()):
        self.p = p
        dates = np.asarray(dates, dtype="datetime64[D]")
        gap = np.diff(dates).astype(int)
        nt = np.concatenate([[0], gap - 1])            # non-trading days before each date
        self.overnight = p.f_on + p.w_nt * nt
        self.f_id = 1.0 - p.f_on
        self.cum_close = np.cumsum(self.overnight + self.f_id)  # clock at close of day j

    def now(self, d: int, u: float) -> float:
        """Clock at trading day index d, session fraction u in [0,1] (0=open, 1=close)."""
        return self.cum_close[d] - (1.0 - u) * self.f_id

    def T(self, d: int, u: float, exp_idx):
        """Year fraction (business, /252) from (d,u) to close of exp_idx."""
        return np.maximum(self.cum_close[exp_idx] - self.now(d, u), 0.0) / 252.0

    def window_eff(self, dates, days: int):
        """Effective trading days in the `days`-calendar-day window after each date."""
        d0 = np.asarray(dates, dtype="datetime64[D]")
        ext = np.concatenate([d0, np.busday_offset(d0[-1], np.arange(1, 30), roll="forward")])
        n_td = np.searchsorted(ext, d0 + days, side="right") - np.searchsorted(ext, d0, side="right")
        return n_td + self.p.w_nt * (days - n_td)

    def cal_to_business(self, vol, days: float):
        """Vol quoted on a calendar clock over `days` calendar days -> business-time vol.
        E.g. 9 calendar days ~ 6.21 trading days + 2.79 non-trading days."""
        td = days * 252 / 365
        eff = td + (days - td) * self.p.w_nt
        return vol * np.sqrt((days / 365) * 252 / eff)
