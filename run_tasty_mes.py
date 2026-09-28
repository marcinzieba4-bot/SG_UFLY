"""Micro E-mini option route for tastytrade under $100k: cost sensitivity and an SPY hedge.

    python run_tasty_mes.py        # writes results/TASTY_MES.md

The fitted Micro E-mini option spread model (tc_model 'mes') came from one pre-market
snapshot of the most liquid weekly series; the new cash-settled weeklies quoted about
twice as wide.  Costs are scaled 1.5x and 2x here.  The SPY-share hedge sits in the
securities account, so its margin (50%) does not net against the futures account:
margin = options-only SPAN proxy (worst loss over -6%..+6%) + 50% of the SPY position.
"""
from __future__ import annotations

from dataclasses import replace
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

from make_factsheets import RETAIL
from run_tasty import END, FEES, SPAN, START, STRESS, _init
import run_tasty
from ufly.backtest import Config, run

OUT = Path(__file__).resolve().parent / "results"
K_MES = 0.371                       # leverage for 5% vol, naked Micro E-mini options (run_tasty.py)


def job(args):
    name, cfg, spy = args
    r = run(cfg, run_tasty.DAILY, run_tasty.HOURLY, run_tasty.MARKS).daily
    ret = r.ret
    nav = (1 + ret).cumprod()
    dd = (nav / nav.cummax() - 1).min()
    cagr = nav.iloc[-1] ** (252 / len(ret)) - 1
    if spy:   # options-only scan (strip the hedge's P&L) + 50% on the SPY shares
        opt = pd.DataFrame({c: r[c] - 100 * r.hedge_units * r.spot * float(c[7:-1]) / 100 / r.nav for c in SPAN})
        margin = (-opt.min(axis=1)).clip(lower=0) / 100 + 0.5 * r.hedge_units.abs() * r.spot / r.nav
    else:
        margin = (-r[SPAN].min(axis=1)).clip(lower=0) / 100
    return name, {"Return %/yr": 100 * cagr, "Vol %": 100 * ret.std() * np.sqrt(252),
                  "Sharpe": ret.mean() / ret.std() * np.sqrt(252), "MaxDD %": 100 * dd,
                  "Margin % NAV (median)": 100 * margin.median(), "Margin % NAV (95th)": 100 * margin.quantile(0.95),
                  "Fees % NAV/yr": 100 * 252 * (r.fees / r.nav.shift(1).fillna(100.0)).mean(),
                  "Cost / premium %": 100 * r.opt_cost.sum() / r.prem_mid.sum()}


def main():
    daily = run_tasty.load_market()[0]
    ref = float(daily.spx_close.loc[:END].dropna().iloc[-1])
    base = replace(Config(start=START, end=END, stress=STRESS, index_ref=ref, leverage=K_MES, **RETAIL), tc_model="mes")
    mes = dict(opt_mult=5.0, opt_fee_usd=FEES["MES_OPT"])
    jobs = [("XSP costs (reference), fractional", replace(base, tc_model="xsp"), False)]
    for sc in (1.0, 1.5, 2.0):
        jobs.append((f"Micro E-mini, costs x{sc:g}, fractional", replace(base, tc_scale=sc), False))
    for acct in (25e3, 50e3, 75e3):
        for sc in (1.5, 2.0):
            jobs.append((f"Micro E-mini + MES, costs x{sc:g}, ${acct / 1e3:.0f}k",
                         replace(base, tc_scale=sc, account_usd=acct, hedge_mult=5.0, hedge_fee_usd=FEES["MES"], **mes), False))
        jobs.append((f"Micro E-mini + SPY, costs x1.5, ${acct / 1e3:.0f}k",
                     replace(base, tc_scale=1.5, account_usd=acct, hedge_mult=0.1, hedge_fee_usd=FEES["SPY"], **mes), True))
    with Pool(4, initializer=_init) as pool:
        rows = dict(pool.imap(job, jobs))
    t = pd.DataFrame(rows).T.loc[[j[0] for j in jobs]]
    md = ["# Micro E-mini options route: cost sensitivity and SPY hedge (2011-2026, 5% vol budget)\n",
          "Costs x1 = spread model fitted to the most liquid weekly series (pre-market 2026-09-28); the new "
          "cash-settled weeklies quoted about 2x wider pre-market. Margin: SPAN proxy (-6%..+6% scan) for the "
          "futures account; the SPY variant adds 50% of the SPY position and gets no netting.\n",
          t.round(2).to_markdown()]
    (OUT / "TASTY_MES.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
