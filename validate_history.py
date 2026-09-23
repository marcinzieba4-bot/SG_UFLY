"""Check the backtest's option pricing against real historical SPXW prices (Barchart).

    python validate_history.py            # fetch (cached in data/barchart_hist/) and report
    python validate_history.py --step 10  # sample fewer expiries

Sample: an expiry every `step` trading days from June 2023 (start of Barchart's
weekly history) to the data end.  For each expiry, take the strikes the strategy
would sell at 5DTE for the target deltas under the backtest's calibrated pricing.
Barchart's daily history of those contracts gives the real closing price on each
day from 5DTE to 1DTE; the model prices the same contract that day (at the carry
forward).  The comparison is the implied-vol ratio market / model: 1.0 means the
backtest collects the right premium, 0.90 means its vols are 10% too high.

Caveat: Barchart's daily close is the last trade (not the bid/ask mid) and may be
stamped up to 16:15 ET, after the 16:00 SPX close.  Medians over many
observations wash most of that out.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import brentq

from ufly.backtest import Config, atm_vols, short_end_factor
from ufly.barchart import fetch_history, option_symbol
from ufly.data import DATA_DIR, load_market
from ufly.vol import Smile, VarianceClock, bs_call

OUT = Path(__file__).resolve().parent / "results"
TARGETS = (0.05, 0.075, 0.10)
DIV_YIELD = 0.013


def build_sample(daily: pd.DataFrame, cfg: Config, step: int, start: str = "2023-06-05", targets=TARGETS):
    dates = daily.index
    clock = VarianceClock(dates.values, cfg.clock)
    _, sig_close, rho, eff10 = atm_vols(daily, cfg, clock)
    smile = Smile(cfg.smile)
    first = int(np.searchsorted(dates, pd.Timestamp(start)))
    rows = []
    for ie in range(first + 5, len(dates), step):
        d = ie - 5
        S, T = float(daily.spx_close.iloc[d]), float(clock.T(d, 1.0, ie))
        a = sig_close[d] * cfg.atm_mult * float(short_end_factor(T, rho[d], eff10[d])[0])
        K = np.round(smile.strike_for_delta(np.array(targets), S, a, T) / cfg.strike_step) * cfg.strike_step
        for t, k in zip(targets, K):
            rows.append(dict(expiry=dates[ie], ie=ie, d0=d, target=t, K=float(k),
                             symbol=option_symbol(dates[ie], float(k))))
    return pd.DataFrame(rows).drop_duplicates("symbol"), clock, sig_close, rho, eff10, smile


def real_price_pnl(o: pd.DataFrame, sample: pd.DataFrame, daily: pd.DataFrame, clock, half_spread=0.03):
    """Sell each sampled contract at its real 5DTE close (less half-spread), hedge the
    delta at each daily close, hold to expiry.  Same trades priced by the model for
    comparison.  P&L in bp of the notional (SPX level at sale)."""
    obs = o.set_index(["expiry", "K", "date"]).sort_index()
    rows = []
    for c in sample.itertuples():
        d0 = daily.index[c.d0]
        if (c.expiry, c.K, d0) not in obs.index:
            continue
        first = obs.loc[(c.expiry, c.K, d0)]
        S0 = float(daily.spx_close.iloc[c.d0])
        payoff = max(float(daily.spx_close.iloc[c.ie]) - c.K, 0.0)
        res = {"expiry": c.expiry, "target": c.target, "atm": first.atm}
        for kind, px0, iv0 in (("real", first.market, first.iv_mkt), ("model", first.model, first.iv_mod)):
            hedge = 0.0
            for t in range(c.d0, c.ie):
                day = daily.index[t]
                S, S1 = float(daily.spx_close.iloc[t]), float(daily.spx_close.iloc[t + 1])
                T = float(clock.T(t, 1.0, c.ie))
                if (c.expiry, c.K, day) in obs.index:
                    r = obs.loc[(c.expiry, c.K, day)]
                    iv = r.iv_mkt if kind == "real" else r.iv_mod
                else:
                    iv = iv0
                hedge += float(bs_call(S, c.K, iv, T)[1]) * (S1 - S)
            prem = px0 - max(0.025, half_spread * px0)
            res[f"pnl_{kind}_bp"] = 1e4 * (prem - payoff + hedge) / S0
            res[f"prem_{kind}_bp"] = 1e4 * prem / S0
        res["payoff_bp"] = 1e4 * payoff / S0
        rows.append(res)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=int, default=5)
    ap.add_argument("--wing-mult", type=float, default=Config().wing_mult,
                    help="evaluate the model with this call-wing multiplier (1.0 = 22-Sep chain calibration)")
    ap.add_argument("--wing-beta", type=float, default=0.0, help="... and this wing vol beta")
    ap.add_argument("--tag", default="", help="suffix for the output files")
    ap.add_argument("--targets", default="0.05,0.075,0.10", help="deltas of the sampled strikes at 5DTE (0.5 = ATM)")
    ap.add_argument("--core", default="0.03,0.12", help="model-delta range for the headline statistics")
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)

    daily, _ = load_market()
    cfg = Config(wing_mult=1.0)   # strike selection fixed to the chain-calibrated model (cached contract set)
    targets = tuple(float(x) for x in args.targets.split(","))
    lo, hi = (float(x) for x in args.core.split(","))
    sample, clock, sig_close, rho, eff10, smile = build_sample(daily, cfg, args.step, targets=targets)
    wmult = lambda t: args.wing_mult * np.exp(args.wing_beta * (sig_close[t] - 0.12))
    hist = fetch_history(sample.symbol.tolist(), DATA_DIR / "barchart_hist")

    import yfinance as yf
    irx = yf.download("^IRX", start="2023-01-01", progress=False, auto_adjust=False)["Close"].squeeze()
    irx.index = pd.to_datetime(irx.index).tz_localize(None)
    rate = (irx.reindex(daily.index).ffill() / 100).fillna(0.045)

    obs = []
    for c in sample.itertuples():
        h = hist[c.symbol]
        if h.empty:
            continue
        h = h.set_index("date")
        for t in range(c.d0, c.ie):                       # 5DTE ... 1DTE, at each close
            day = daily.index[t]
            if day not in h.index:
                continue
            px, vol = float(h.loc[day, "close"]), float(h.loc[day, "volume"])
            if not (px >= 0.10 and vol >= 5):
                continue
            S = float(daily.spx_close.iloc[t])
            T = float(clock.T(t, 1.0, c.ie))
            Tcal = (c.expiry - day).days / 365
            F = S * np.exp((rate.iloc[t] - DIV_YIELD) * Tcal)
            a = sig_close[t] * cfg.atm_mult * float(short_end_factor(T, rho[t], eff10[t])[0])
            iv_mod = float(smile.vol(c.K, F, a, T, wmult(t)))
            mod, dlt, _ = bs_call(F, c.K, iv_mod, T)
            intrinsic = max(F - c.K, 0.0)
            if px <= intrinsic + 0.02:
                continue
            try:
                iv_mkt = brentq(lambda v: bs_call(F, c.K, v, T)[0] - px, 1e-3, 5.0)
            except ValueError:
                continue
            obs.append(dict(date=day, expiry=c.expiry, dte=c.ie - t, K=c.K, target=c.target, S=S,
                            otm_pct=100 * (c.K / F - 1), atm=a, model_delta=float(dlt), market=px,
                            model=float(mod), iv_mkt=iv_mkt, iv_mod=iv_mod, volume=vol,
                            weekend=int((c.expiry - day).days > (c.ie - t))))
    o = pd.DataFrame(obs)
    o["iv_ratio"] = o.iv_mkt / o.iv_mod
    o["px_ratio"] = o.market / o.model
    RAW = DATA_DIR / "barchart_analysis"          # contains Barchart prices: git-ignored, not redistributed
    RAW.mkdir(parents=True, exist_ok=True)
    o.to_csv(RAW / f"history_check_obs{args.tag}.csv", index=False, float_format="%.6g")

    core = o[(o.model_delta >= lo) & (o.model_delta <= hi)]
    q = lambda s: pd.Series({"n": len(s), "median IV ratio": s.iv_ratio.median(),
                             "IQR low": s.iv_ratio.quantile(0.25), "IQR high": s.iv_ratio.quantile(0.75),
                             "median price ratio": s.px_ratio.median()})
    by_dte = core.groupby("dte").apply(q)
    by_delta = o.groupby(pd.cut(o.model_delta, [0, 0.025, 0.05, 0.075, 0.10, 0.15, 0.3, 1.0])).apply(q)
    by_regime = core.groupby(pd.cut(100 * core.atm, [0, 10, 12, 14, 17, 25, 100])).apply(q)
    by_half = core.groupby(core.date.dt.year.astype(str) + "H" + ((core.date.dt.month > 6) + 1).astype(str)).apply(q)
    by_wkend = core.groupby("weekend").apply(q)
    slope = np.polyfit(core.atm - 0.12, np.log(core.iv_ratio), 1)[0]
    overall = q(core)

    # time series chart: 1-month rolling median of the IV ratio
    ts = core.set_index("date").iv_ratio.sort_index()
    roll = ts.rolling("30D").median()
    fig, axs = plt.subplots(1, 2, figsize=(11, 3.8))
    axs[0].scatter(ts.index, ts.values, s=3, color="#86b6ef", label="observations")
    axs[0].plot(roll.index, roll.values, color="#2a78d6", lw=1.6, label="30-day rolling median")
    axs[0].axhline(1.0, color="#52514e", lw=0.8, ls="--")
    axs[0].set_ylim(0.5, 1.5)
    axs[0].set_title(f"Real / model implied vol, {100 * lo:.0f}-{100 * hi:.0f} delta SPXW calls (1-5DTE)",
                     fontsize=10, fontweight="bold")
    axs[0].legend(fontsize=8, frameon=False)
    import matplotlib.dates as mdates
    axs[0].xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 7)))
    axs[0].xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    axs[0].tick_params(axis="x", rotation=30)
    reg = by_regime.dropna()
    axs[1].bar([str(i) for i in reg.index], reg["median IV ratio"], color="#2a78d6", width=0.6)
    axs[1].axhline(1.0, color="#52514e", lw=0.8, ls="--")
    axs[1].set_ylim(0.6, 1.2)
    axs[1].set_xlabel("model ATM vol at the observation (%, business time)")
    axs[1].set_title("Median real / model IV by vol regime", fontsize=10, fontweight="bold")
    for ax in axs:
        ax.grid(True, color="#e4e3df", lw=0.6)
        ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(); fig.savefig(OUT / f"history_check{args.tag}.png", dpi=150); plt.close(fig)

    pnl = real_price_pnl(o, sample, daily, clock)
    per_exp = pnl.groupby("expiry")[["pnl_real_bp", "pnl_model_bp"]].sum()
    ann = np.sqrt(252 / args.step)
    pnl_tab = pd.DataFrame({
        k: {"contracts": len(pnl), "avg premium (bp)": pnl[f"prem_{k}_bp"].mean(),
            "avg payoff (bp)": pnl.payoff_bp.mean(), "avg P&L hedged (bp)": pnl[f"pnl_{k}_bp"].mean(),
            "hit rate": (pnl[f"pnl_{k}_bp"] > 0).mean(),
            "Sharpe (per-expiry series, ann.)": per_exp[f"pnl_{k}_bp"].mean() / per_exp[f"pnl_{k}_bp"].std() * ann,
            "worst expiry (bp)": per_exp[f"pnl_{k}_bp"].min()}
        for k in ("real", "model")})
    pnl_by_target = pnl.groupby("target")[["prem_real_bp", "prem_model_bp", "payoff_bp", "pnl_real_bp", "pnl_model_bp"]].mean()
    pnl.to_csv(RAW / f"history_check_trades{args.tag}.csv", index=False, float_format="%.6g")

    fmt = lambda df: df.round(3).to_markdown()
    md = ["# Pricing check vs real historical SPXW prices (Barchart)\n",
          f"Model evaluated with call-wing multiplier {args.wing_mult} and wing vol beta {args.wing_beta} "
          "(1.0 / 0.0 = the backtest's chain-calibrated pricing).\n",
          f"Contracts: {sample.symbol.nunique()} sampled ({o.expiry.nunique()} expiries with data), "
          f"{len(o)} daily observations from {o.date.min().date()} to {o.date.max().date()}. "
          "IV ratio = implied vol of the real closing price / backtest model vol for the same "
          "contract and day (1.0 = the backtest's pricing is right).\n",
          f"**Core sample (model delta {100 * lo:.0f}-{100 * hi:.0f}%): median IV ratio {overall['median IV ratio']:.3f} "
          f"(IQR {overall['IQR low']:.3f}-{overall['IQR high']:.3f}), median price ratio "
          f"{overall['median price ratio']:.3f}, n = {int(overall['n'])}.** "
          f"Slope of ln(ratio) on ATM vol: {slope:.2f} per 1.00 of vol.\n",
          "## By days to expiry (core)\n", fmt(by_dte),
          "\n## By model delta (all observations)\n", fmt(by_delta),
          "\n## By vol regime (core)\n", fmt(by_regime),
          "\n## By half-year (core)\n", fmt(by_half),
          "\n## Across a weekend or not (core)\n", fmt(by_wkend),
          "\n## Real-price mini-backtest (sell at 5DTE close, daily close delta hedge, hold to expiry)\n",
          "Same contracts sold at the real closing price vs at the model price (both less a 3% half-spread, "
          f"min 0.025). One expiry every {args.step} trading days, strikes at "
          f"{', '.join(f'{100 * t:g}' for t in targets)} delta; "
          "P&L in bp of the notional.\n", fmt(pnl_tab),
          "\nBy target delta (averages, bp):\n", fmt(pnl_by_target),
          ]
    (OUT / f"HISTORY_CHECK{args.tag}.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
