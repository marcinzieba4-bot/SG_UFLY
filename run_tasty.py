"""Retail programme redesigned for a tastytrade account under $100k.

    python run_tasty.py            # writes results/TASTY.md

Two tastytrade constraints break the original (naked XSP calls + MES hedge) below
$100k: the house margin on naked cash-settled index calls (25% of the index less the
OTM amount, minimum 15%) with no offset from futures held in the separate futures
account, and the MES lot size (~$39k of delta) against a small account.  Candidates:

  XSP call spreads      sell the same 20-30 delta calls, buy a far wing: margin = width
  SPY-share hedge       ~$770 per share instead of ~$39k per MES
  Micro E-mini options  options on MES futures ($5 x index, half an XSP) margined with
                        the MES hedge in one futures account (SPAN-style offsets)

All at the 5% volatility budget, 2011-2026, whole contracts at today's sizes.
Margin: XSP legs by tastytrade's rules (naked 25%/15%, spreads = width) plus hedge
margin (MES ~7% of notional, SPY 50%); Micro E-mini options ~ worst loss of the hedged
futures account over -6%..+6% moves (a SPAN proxy, before exchange/broker minimums).
"""
from __future__ import annotations

import json
from dataclasses import replace
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

from make_factsheets import RETAIL
from ufly.backtest import Config, run
from ufly.data import load_market
from ufly.paths import build_marks

OUT = Path(__file__).resolve().parent / "results"
START, END = "2011-01-03", "2026-09-22"
STRESS = (-0.10, -0.08, -0.06, -0.05, 0.03, 0.05, 0.06, 0.08, 0.12)
SPAN = ["stress_-6%", "stress_-5%", "stress_+3%", "stress_+5%", "stress_+6%"]
FEES = {"XSP": 1.15, "MES_OPT": 1.25, "MES": 1.41, "SPY": 0.001}   # tastytrade, $ per contract/share, approx.
ACCOUNTS = (25e3, 50e3, 75e3)

DAILY = HOURLY = MARKS = None


def _init():
    global DAILY, HOURLY, MARKS
    DAILY, HOURLY = load_market()
    MARKS = build_marks(DAILY.loc[START:END], HOURLY)


def vol_of(args):
    name, cfg = args
    r = run(cfg, DAILY, HOURLY, MARKS).daily.ret
    return name, float(r.std() * np.sqrt(252))


def job(args):
    name, cfg, span = args
    r = run(cfg, DAILY, HOURLY, MARKS).daily
    ret = r.ret
    nav = (1 + ret).cumprod()
    dd = (nav / nav.cummax() - 1).min()
    cagr = nav.iloc[-1] ** (252 / len(ret)) - 1
    margin = (-r[SPAN].min(axis=1)).clip(lower=0) / 100 if span else r.regt_margin / r.nav
    calm = r[r.atm_2d < 0.12]
    return name, {
        "Return %/yr": 100 * cagr, "Vol %": 100 * ret.std() * np.sqrt(252),
        "Sharpe": ret.mean() / ret.std() * np.sqrt(252), "MaxDD %": 100 * dd,
        "Margin % NAV (median)": 100 * margin.median(), "Margin % NAV (95th)": 100 * margin.quantile(0.95),
        "Contracts open (avg)": r.contracts_open.mean(), "Hedge units (avg)": r.hedge_contracts.mean(),
        "Fees % NAV/yr": 100 * 252 * (r.fees / r.nav.shift(1).fillna(100.0)).mean(),
        "+5% gap calm % NAV": calm["stress_+5%"].median(), "+8% gap calm % NAV": calm["stress_+8%"].median(),
        "+12% gap calm % NAV": calm["stress_+12%"].median(),
    }


def main():
    daily, _ = load_market()
    ref = float(daily.spx_close.loc[:END].dropna().iloc[-1])
    common = dict(start=START, end=END, stress=STRESS, index_ref=ref, naked_hi=0.25, naked_lo=0.15)
    base = Config(**common, **RETAIL)
    structures = {
        "naked XSP": base,
        "XSP spread, 5d wing": replace(base, wing_delta=0.05),
        "XSP spread, 10d wing": replace(base, wing_delta=0.10),
        "naked Micro E-mini options": replace(base, tc_model="mes"),
        "Micro E-mini spread, 5d wing": replace(base, tc_model="mes", wing_delta=0.05),
    }
    hedges = {
        "MES": dict(hedge_mult=5.0, hedge_fee_usd=FEES["MES"], fut_margin_pct=0.07),
        "SPY": dict(hedge_mult=0.1, hedge_fee_usd=FEES["SPY"], fut_margin_pct=0.5),
    }
    plan = [("naked XSP", "MES"), ("naked XSP", "SPY"), ("XSP spread, 5d wing", "MES"), ("XSP spread, 5d wing", "SPY"),
            ("XSP spread, 10d wing", "SPY"), ("naked Micro E-mini options", "MES"), ("Micro E-mini spread, 5d wing", "MES")]
    with Pool(4, initializer=_init) as pool:
        vols = dict(pool.imap(vol_of, list(structures.items())))
        k = {n: 0.05 / v for n, v in vols.items()}
        jobs = []
        for sname, hname in plan:
            mes_opt = "Micro" in sname
            c0 = replace(structures[sname], leverage=k[sname])
            jobs.append((f"{sname} + {hname}, fractional", c0, mes_opt))
            for acct in ACCOUNTS:
                c = replace(c0, account_usd=acct, opt_mult=5.0 if mes_opt else 10.0,
                            opt_fee_usd=FEES["MES_OPT"] if mes_opt else FEES["XSP"], **hedges[hname])
                jobs.append((f"{sname} + {hname}, ${acct / 1e3:.0f}k", c, mes_opt))
        rows = dict(pool.imap(job, jobs))
    t = pd.DataFrame(rows).T.loc[[j[0] for j in jobs]]
    lev = pd.Series(k, name="leverage for 5% vol").round(3)
    md = ["# Retail programme for a tastytrade account under $100k (2011-2026, today's contract sizes)\n",
          f"Index reference {ref:,.0f}: XSP ${ref * 10:,.0f}, Micro E-mini option / MES future ${ref * 5:,.0f}, "
          f"SPY share ~${ref / 10:,.0f}. Fees (approx., $): {FEES}. 5% volatility budget for each structure.\n",
          lev.to_frame().to_markdown(), "", t.round(2).to_markdown()]
    (OUT / "TASTY.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
