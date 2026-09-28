"""tastytrade small accounts: Micro E-mini options hedged with SPY shares, or MES lots topped up with SPY.

    python run_tasty_hybrid.py     # writes results/TASTY_HYBRID.md (MES-only rows from results/SUMMARY.md)

  SPY only      the whole hedge in SPY shares (securities account, 50% margin, no netting)
  MES + SPY     whole MES lots (rounded down) in the futures account, netted with the options,
                plus SPY shares for the leftover fraction of a lot ($0-39k)

Same programme, seeds and sizes as run_summary.py (5% volatility budget, 2011-2026).
Margin = futures account (options + MES) worst loss over -6%..+6% (SPAN proxy) + 50% of the SPY
shares; the SPY position's P&L is stripped from the futures-account scan.
"""
from __future__ import annotations

from dataclasses import replace
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

from make_factsheets import RETAIL
from run_summary import END, SEEDS, SPAN, START, STRESS, DATA, _init
from ufly.backtest import Config, run
from ufly.data import load_market

OUT = Path(__file__).resolve().parent / "results"
SIZES = (25e3, 50e3, 75e3, 100e3, 250e3)


def job(args):
    key, cfg = args
    r = run(cfg, DATA["daily"], DATA["hourly"], DATA["full"]).daily
    ret = r.ret
    nav = (1 + ret).cumprod()
    dd = (nav / nav.cummax() - 1).min()
    cagr = nav.iloc[-1] ** (252 / len(ret)) - 1
    spy = r.hedge_units2 if cfg.hedge_mult2 > 0 else r.hedge_units      # SPY part of the hedge (index units)
    fut = pd.DataFrame({c: r[c] - 100 * spy * r.spot * float(c[7:-1]) / 100 / r.nav for c in SPAN})
    spy_m = 0.5 * spy.abs() * r.spot / r.nav
    margin = (-fut.min(axis=1)).clip(lower=0) / 100 + spy_m
    return key, {"Return %/yr": 100 * cagr, "MaxDD %": 100 * dd, "Calmar": cagr / -dd,
                 "Sharpe": ret.mean() / ret.std() * np.sqrt(252), "Vol %": 100 * ret.std() * np.sqrt(252),
                 "Margin % NAV (median)": 100 * margin.median(), "Margin % NAV (95th)": 100 * margin.quantile(0.95),
                 "SPY position % NAV (avg)": 100 * (spy.abs() * r.spot / r.nav).mean(),
                 "Fees % NAV/yr": 100 * 252 * (r.fees / r.nav.shift(1).fillna(100.0)).mean()}


def main():
    daily, _ = load_market()
    ref = float(daily.spx_close.loc[:END].dropna().iloc[-1])
    base = replace(Config(start=START, end=END, stress=STRESS, index_ref=ref, leverage=0.371, **RETAIL),
                   tc_model="mes", tc_scale=1.5, opt_mult=5.0, opt_fee_usd=1.25)
    variants = {
        "SPY only": dict(hedge_mult=0.1, hedge_fee_usd=0.001),
        "MES + SPY top-up": dict(hedge_mult=5.0, hedge_fee_usd=1.41, hedge_mult2=0.1, hedge_fee2_usd=0.001),
    }
    jobs = []
    for v, kw in variants.items():
        for i, a in enumerate(SIZES):
            for s in (SEEDS if i < len(SIZES) - 1 else SEEDS[:1]):
                jobs.append(((v, f"${a / 1e3:.0f}k", s), replace(base, account_usd=a, seed=s, **kw)))
    with Pool(4, initializer=_init) as pool:
        res = dict(pool.imap(job, jobs))
    groups = {}
    for (v, size, _), st in res.items():
        groups.setdefault((v, size), []).append(st)
    rows = {}
    for key, lst in groups.items():
        df = pd.DataFrame(lst)
        row = df.median().to_dict()
        row["Calmar range"] = f"{df.Calmar.min():.2f}-{df.Calmar.max():.2f}" if len(df) > 1 else ""
        rows[key] = row
    # MES-only rows from the summary run (same programme, seeds and sizes)
    for line in (OUT / "SUMMARY.md").read_text().splitlines():
        if line.startswith("| ('tastytrade") and "$" in line:
            c = [x.strip() for x in line.strip().strip("|").split("|")]
            rows[("MES only", c[0].split("'")[3])] = {
                "Return %/yr": float(c[1]), "MaxDD %": float(c[2]), "Calmar": float(c[3]), "Calmar range": c[4],
                "Sharpe": float(c[5]), "Vol %": float(c[6]), "Margin % NAV (median)": float(c[8]),
                "Fees % NAV/yr": float(c[10])}
    t = pd.DataFrame.from_dict(rows, orient="index")
    order = [(v, f"${a / 1e3:.0f}k") for a in SIZES for v in ("MES only", "SPY only", "MES + SPY top-up")]
    t = t.loc[[o for o in order if o in t.index]]
    cols = ["Return %/yr", "MaxDD %", "Calmar", "Calmar range", "Sharpe", "Vol %", "Margin % NAV (median)",
            "Margin % NAV (95th)", "SPY position % NAV (avg)", "Fees % NAV/yr"]
    t = t[cols]
    num = [c for c in cols if c != "Calmar range"]
    t[num] = t[num].astype(float).round(2)
    md = ["# tastytrade small accounts: hedge alternatives (Micro E-mini options, 5% vol budget, 2011-2026)\n",
          "Median of 3 rounding seeds (1 for $250k). Option costs 1.5x the fitted quote model; fees: Micro E-mini "
          "option $1.25, MES $1.41 per side, SPY ~$0.001/share. Margin: SPAN proxy for the futures account + 50% of "
          "SPY shares (securities account, no netting). MES-only rows from results/SUMMARY.md.\n", t.to_markdown()]
    (OUT / "TASTY_HYBRID.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
