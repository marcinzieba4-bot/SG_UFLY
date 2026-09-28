"""One consistent comparison of the three implementations, with Calmar ratios by account size.

    python run_summary.py          # writes results/SUMMARY.md

  IBKR         XSP 20-30 delta calls, ~10DTE, hedged 3x a day with MES (retail programme)
  tastytrade   Micro E-mini S&P options, same strikes/tenor, MES hedge in the same futures account
  GS           institutional core: far-OTM SPXW ladder (2-5DTE), hedged hourly, prime-broker margin

2011-2026, whole contracts at today's sizes, broker-specific fees; retail programmes at a 5%
volatility budget, institutional at 2.5% (recommended, tail-budgeted) and 5%.  Small accounts are
run with 3 rounding seeds (which contract slots fill first) and the median is reported with the
Calmar range.  Calmar = annual return over cash / |max drawdown|, full period.
Margin: rules-based = Cboe naked index call formula (15%/10%) + futures margin; risk-based =
worst hedged-book loss over -8%..+6% moves (TIMS range; -6%..+6% SPAN proxy for Micro E-mini
options), before broker add-ons.
"""
from __future__ import annotations

import json
from dataclasses import replace
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

from make_factsheets import INST, RETAIL, WIN
from ufly.backtest import Config, run
from ufly.data import DATA_DIR, load_market
from ufly.paths import build_marks

OUT = Path(__file__).resolve().parent / "results"
START, END = "2011-01-03", "2026-09-22"
STRESS = (-0.10, -0.08, -0.06, -0.05, 0.03, 0.05, 0.06, 0.08, 0.12)
TIMS = ["stress_-8%", "stress_-6%", "stress_-5%", "stress_+3%", "stress_+5%", "stress_+6%"]
SPAN = ["stress_-6%", "stress_-5%", "stress_+3%", "stress_+5%", "stress_+6%"]
SEEDS = (7, 8, 9)

DATA = {}


def _init():
    daily, hourly = load_market()
    DATA.update(daily=daily, hourly=hourly, full=build_marks(daily.loc[START:END], hourly),
                win=build_marks(daily.loc[WIN:END], hourly))


def stats(r: pd.DataFrame, scan: list[str]) -> dict:
    ret = r.ret
    nav = (1 + ret).cumprod()
    dd = (nav / nav.cummax() - 1).min()
    cagr = nav.iloc[-1] ** (252 / len(ret)) - 1
    calm = r[r.atm_2d < 0.12]
    return {"Return %/yr": 100 * cagr, "Vol %": 100 * ret.std() * np.sqrt(252),
            "Sharpe": ret.mean() / ret.std() * np.sqrt(252), "MaxDD %": 100 * dd, "Calmar": cagr / -dd,
            "Rules-based margin % NAV": 100 * (r.regt_margin / r.nav).median(),
            "Risk-based margin % NAV": 100 * ((-r[scan].min(axis=1)).clip(lower=0) / 100).median(),
            "+8% gap, calm % NAV": calm["stress_+8%"].median(),
            "Fees % NAV/yr": 100 * 252 * (r.fees / r.nav.shift(1).fillna(100.0)).mean(),
            "Contracts open": r.contracts_open.mean()}


def job(args):
    key, cfg, scan, window = args
    marks = DATA["win" if window else "full"]
    return key, stats(run(cfg, DATA["daily"], DATA["hourly"], marks).daily, scan)


def main():
    fs = json.loads((OUT / "factsheet_data.json").read_text())
    k_ret, k_inst = fs["retail"]["leverage_for_5pct"], fs["inst"]["leverage_for_5pct"]
    k_mes = 0.371                                               # run_tasty.py, 5% vol
    daily, _ = load_market()
    ref = float(daily.spx_close.loc[:END].dropna().iloc[-1])
    wf = str(DATA_DIR / "barchart_analysis" / "wing_level.csv")
    common = dict(start=START, end=END, stress=STRESS, index_ref=ref)
    progs = {
        "IBKR (XSP + MES)": dict(
            cfg=Config(leverage=k_ret, **common, **RETAIL), scan=TIMS,
            acct=dict(opt_mult=10.0, opt_fee_usd=0.75, hedge_mult=5.0, hedge_fee_usd=0.61),
            sizes=(25e3, 50e3, 100e3, 250e3, 1e6)),
        "tastytrade (Micro E-mini options + MES)": dict(
            cfg=replace(Config(leverage=k_mes, **common, **RETAIL), tc_model="mes", tc_scale=1.5), scan=SPAN,
            acct=dict(opt_mult=5.0, opt_fee_usd=1.25, hedge_mult=5.0, hedge_fee_usd=1.41),
            sizes=(25e3, 50e3, 75e3, 100e3, 250e3)),
        "GS institutional, 2.5% budget": dict(
            cfg=Config(leverage=k_inst / 2, **common, **INST), scan=TIMS,
            acct=dict(opt_mult=100.0, opt_fee_usd=0.70, hedge_mult=5.0, hedge_fee_usd=0.20),
            sizes=(1e6, 2e6, 5e6, 10e6, 25e6)),
        "GS institutional, 5% budget": dict(
            cfg=Config(leverage=k_inst, **common, **INST), scan=TIMS,
            acct=dict(opt_mult=100.0, opt_fee_usd=0.70, hedge_mult=5.0, hedge_fee_usd=0.20),
            sizes=(1e6, 2e6, 5e6, 10e6, 25e6)),
    }
    jobs = []
    for p, spec in progs.items():
        jobs.append(((p, "no rounding, no fees", 0), spec["cfg"], spec["scan"], False))
        win = replace(spec["cfg"], start=WIN, wing_file=wf)
        jobs.append(((p, "real-price window 2023-26", 0), win, spec["scan"], True))
        for i, a in enumerate(spec["sizes"]):
            seeds = SEEDS if i < len(spec["sizes"]) - 1 else SEEDS[:1]
            for s in seeds:
                jobs.append(((p, f"${a / 1e6:g}m" if a >= 1e6 else f"${a / 1e3:.0f}k", s),
                             replace(spec["cfg"], account_usd=a, seed=s, **spec["acct"]), spec["scan"], False))
    # GS with the richness signal on the real-price window, at the 2.5% core's notional
    sig = replace(progs["GS institutional, 2.5% budget"]["cfg"], start=WIN, wing_file=wf, roll_min_wing=0.85)
    jobs.append((("GS institutional, 2.5% budget", "real-price window, + signal", 0), sig, TIMS, True))
    with Pool(4, initializer=_init) as pool:
        res = dict(pool.imap(job, jobs))
    rows = {}
    for (p, size, _), st in res.items():
        rows.setdefault((p, size), []).append(st)
    out = {}
    for key, lst in rows.items():
        df = pd.DataFrame(lst)
        row = df.median().to_dict()
        row["Calmar range"] = f"{df.Calmar.min():.2f}-{df.Calmar.max():.2f}" if len(df) > 1 else ""
        out[key] = row
    order = list(dict.fromkeys((j[0][0], j[0][1]) for j in jobs))
    t = pd.DataFrame(out).T.loc[order]
    cols = ["Return %/yr", "MaxDD %", "Calmar", "Calmar range", "Sharpe", "Vol %", "Rules-based margin % NAV",
            "Risk-based margin % NAV", "+8% gap, calm % NAV", "Fees % NAV/yr", "Contracts open"]
    t = t[cols]
    num = [c for c in cols if c != "Calmar range"]
    t[num] = t[num].astype(float).round(2)
    md = ["# Summary: IBKR, tastytrade and institutional (GS) implementations\n",
          f"2011-2026 unless marked, whole contracts at today's sizes (SPX {ref:,.0f}). Median of 3 rounding seeds "
          "for all but the largest size in each block. Fees per contract: IBKR XSP $0.75, MES $0.61; tastytrade "
          "Micro E-mini option $1.25, MES $1.41 (option costs 1.5x the fitted quote model); GS SPXW $0.70, "
          "hedge $0.20 per MES-equivalent (ES bulk).\n", t.to_markdown()]
    (OUT / "SUMMARY.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
