"""Minimum account size: whole contracts, whole hedge lots, per-contract fees and margin.

    python run_accounts.py          # writes results/ACCOUNTS.md

Each programme runs 2011-2026 at its volatility budget with contract sizes held at
today's index level (SPX ~7,700: XSP ~$77k, SPXW ~$770k, MES ~$38.5k notional), so
the contract-to-account ratio is today's throughout.  Options are sold in whole
contracts (each strike/expiry slot carries its fraction forward), hedges are rounded
to whole futures (or near-continuous SPY shares).

Margin: Reg-T = rules-based naked index call margin (premium + max(15% of underlying
- OTM amount, 10%)) plus ~7% on futures; portfolio margin ~ worst loss of the hedged
book over index moves from -8% to +6% (the OCC/TIMS range for broad-based indexes),
before any broker add-ons.
"""
from __future__ import annotations

import json
from dataclasses import replace
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

from make_factsheets import INST, RETAIL
from ufly.backtest import Config, run
from ufly.data import load_market
from ufly.paths import build_marks

OUT = Path(__file__).resolve().parent / "results"
START, END = "2011-01-03", "2026-09-22"
STRESS = (-0.10, -0.08, -0.05, 0.03, 0.05, 0.06, 0.08, 0.12)
PM_RANGE = ["stress_-8%", "stress_-5%", "stress_+3%", "stress_+5%", "stress_+6%"]
FEES = {"XSP": 1.00, "SPXW": 1.50, "MES": 0.85, "SPY": 0.005}   # $ per contract / share, all-in (approximate)

DAILY = HOURLY = MARKS = None


def _init():
    global DAILY, HOURLY, MARKS
    DAILY, HOURLY = load_market()
    MARKS = build_marks(DAILY.loc[START:END], HOURLY)


def job(args):
    name, cfg = args
    r = run(cfg, DAILY, HOURLY, MARKS).daily
    ret = r.ret
    nav = (1 + ret).cumprod()
    dd = (nav / nav.cummax() - 1).min()
    cagr = nav.iloc[-1] ** (252 / len(ret)) - 1
    regt = r.regt_margin / r.nav
    pm = (-r[PM_RANGE].min(axis=1)).clip(lower=0) / 100
    calm = r[r.atm_2d < 0.12]
    return name, {
        "Return %/yr": 100 * cagr, "Vol %": 100 * ret.std() * np.sqrt(252),
        "Sharpe": ret.mean() / ret.std() * np.sqrt(252), "MaxDD %": 100 * dd,
        "Contracts sold/day": r.contracts_sold.mean(), "Days with a sale %": 100 * (r.contracts_sold > 0).mean(),
        "Contracts open (avg)": r.contracts_open.mean(), "Hedge lots (avg)": r.hedge_contracts.mean(),
        "Reg-T margin % NAV (median)": 100 * regt.median(), "Reg-T margin % NAV (95th)": 100 * regt.quantile(0.95),
        "PM estimate % NAV (median)": 100 * pm.median(), "PM estimate % NAV (95th)": 100 * pm.quantile(0.95),
        "+5% gap, calm % NAV": calm["stress_+5%"].median(),
    }


def main():
    fs = json.loads((OUT / "factsheet_data.json").read_text())
    k_ret, k_inst = fs["retail"]["leverage_for_5pct"], fs["inst"]["leverage_for_5pct"]
    daily, _ = load_market()
    ref = float(daily.spx_close.loc[:END].dropna().iloc[-1])
    common = dict(start=START, end=END, stress=STRESS, index_ref=ref)
    retail = Config(leverage=k_ret, **common, **RETAIL)
    inst = Config(**common, **INST)
    jobs = [("Retail, fractional (reference)", retail)]
    for acct in (25e3, 50e3, 100e3, 250e3, 1e6):
        xsp = dict(account_usd=acct, opt_mult=10.0, opt_fee_usd=FEES["XSP"])
        jobs.append((f"Retail ${acct / 1e3:,.0f}k, MES hedge",
                     replace(retail, **xsp, hedge_mult=5.0, hedge_fee_usd=FEES["MES"])))
        if acct <= 100e3:
            jobs.append((f"Retail ${acct / 1e3:,.0f}k, SPY-share hedge",
                         replace(retail, **xsp, hedge_mult=0.1, hedge_fee_usd=FEES["SPY"])))
    for budget, k in (("2.5%", k_inst / 2), ("5%", k_inst)):
        base = replace(inst, leverage=k)
        jobs.append((f"Institutional {budget}, fractional (reference)", base))
        for acct in (250e3, 500e3, 1e6, 2e6, 5e6):
            jobs.append((f"Institutional {budget}, ${acct / 1e6:g}m, MES hedge",
                         replace(base, account_usd=acct, opt_mult=100.0, opt_fee_usd=FEES["SPXW"],
                                 hedge_mult=5.0, hedge_fee_usd=FEES["MES"])))
    with Pool(4, initializer=_init) as pool:
        rows = dict(pool.imap(job, jobs))
    t = pd.DataFrame(rows).T.loc[[n for n, _ in jobs]]
    md = ["# Minimum account size (2011-2026, contract sizes at today's index level)\n",
          f"Index reference {ref:,.0f}: XSP ${ref * 10:,.0f}, SPXW ${ref * 100:,.0f}, MES ${ref * 5:,.0f} notional per contract. "
          f"Retail at its 5% volatility budget (leverage {k_ret:.2f}); institutional at 2.5% and 5% ({k_inst / 2:.2f} / {k_inst:.2f}). "
          f"Fees per contract: {FEES}. 'PM estimate' = worst hedged-book loss over -8%..+6% index moves, before broker add-ons.\n",
          t.round(2).to_markdown()]
    (OUT / "ACCOUNTS.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
