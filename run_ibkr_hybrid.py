"""IBKR retail programme (XSP + MES) with the hybrid hedge: MES lots topped up with a fine instrument.

    python run_ibkr_hybrid.py      # writes results/IBKR_HYBRID.md

The top-up is SPY shares for US residents; EU retail clients can't buy SPY (PRIIPs) and would use
IBKR's US 500 index CFD instead (fine size, ~5% margin, financing on the small top-up position
not modelled).  Same seeds and sizes as run_summary.py, 5% volatility budget, 2011-2026.
"""
from __future__ import annotations

import json
from dataclasses import replace
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

from make_factsheets import RETAIL
from run_summary import DATA, END, SEEDS, START, STRESS, _init
from ufly.backtest import Config, run
from ufly.data import load_market

OUT = Path(__file__).resolve().parent / "results"
SIZES = (25e3, 50e3, 100e3, 250e3)


def job(args):
    key, cfg = args
    r = run(cfg, DATA["daily"], DATA["hourly"], DATA["full"]).daily
    ret = r.ret
    nav = (1 + ret).cumprod()
    dd = (nav / nav.cummax() - 1).min()
    cagr = nav.iloc[-1] ** (252 / len(ret)) - 1
    return key, {"Return %/yr": 100 * cagr, "MaxDD %": 100 * dd, "Calmar": cagr / -dd,
                 "Sharpe": ret.mean() / ret.std() * np.sqrt(252), "Vol %": 100 * ret.std() * np.sqrt(252),
                 "Top-up position % NAV (avg)": 100 * (r.hedge_units2.abs() * r.spot / r.nav).mean(),
                 "Fees % NAV/yr": 100 * 252 * (r.fees / r.nav.shift(1).fillna(100.0)).mean()}


def main():
    fs = json.loads((OUT / "factsheet_data.json").read_text())
    daily, _ = load_market()
    ref = float(daily.spx_close.loc[:END].dropna().iloc[-1])
    base = Config(start=START, end=END, stress=STRESS, index_ref=ref, leverage=fs["retail"]["leverage_for_5pct"],
                  opt_mult=10.0, opt_fee_usd=0.75, hedge_mult=5.0, hedge_fee_usd=0.61,
                  hedge_mult2=0.1, hedge_fee2_usd=0.002, **RETAIL)
    jobs = [((f"${a / 1e3:.0f}k", s), replace(base, account_usd=a, seed=s))
            for i, a in enumerate(SIZES) for s in (SEEDS if i < len(SIZES) - 1 else SEEDS[:1])]
    with Pool(4, initializer=_init) as pool:
        res = dict(pool.imap(job, jobs))
    groups = {}
    for (size, _), st in res.items():
        groups.setdefault(size, []).append(st)
    rows = {}
    for size, lst in groups.items():
        df = pd.DataFrame(lst)
        row = df.median().round(2).to_dict()
        row["Calmar range"] = f"{df.Calmar.min():.2f}-{df.Calmar.max():.2f}" if len(df) > 1 else ""
        rows[f"IBKR, MES + top-up, {size}"] = row
    t = pd.DataFrame.from_dict(rows, orient="index")
    t = t[["Return %/yr", "MaxDD %", "Calmar", "Calmar range", "Sharpe", "Vol %", "Top-up position % NAV (avg)",
           "Fees % NAV/yr"]]
    md = ["# IBKR retail programme with the hybrid hedge (MES lots + fine top-up), 5% vol budget, 2011-2026\n",
          "Median of 3 rounding seeds (1 for $250k). Fees: XSP $0.75, MES $0.61, top-up ~$0.002 per share-equivalent.\n",
          t.to_markdown()]
    (OUT / "IBKR_HYBRID.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
