"""Run the upside-vol-premium backtest, scenarios and report.

    python run_backtest.py            # uses cached data in ./data (downloads if missing)
    python run_backtest.py --refresh  # re-download Yahoo + VolVue data

Outputs go to ./results (summary tables, charts, RESULTS_TABLES.md).
"""
from __future__ import annotations

import argparse
import os
from dataclasses import replace
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ufly import data as mdata
from ufly import volvue
from ufly.backtest import Config, run
from ufly.metrics import attribution, stats, yearly
from ufly.paths import build_marks
from ufly.vol import SmileParams

OUT = Path(__file__).resolve().parent / "results"

# reference palette (dataviz skill), light mode
C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "font.size": 9, "axes.titlesize": 10,
    "axes.titleweight": "bold", "axes.titlecolor": INK, "legend.frameon": False, "lines.linewidth": 1.4,
})


def ensure_data(refresh: bool) -> None:
    if refresh or not (mdata.DATA_DIR / "daily.csv").exists():
        mdata.download(refresh=True)
    if os.environ.get("VOLVUE_API_KEY") and (refresh or volvue.load("SPX") is None):
        volvue.download("SPX")


def scenarios(base: Config) -> list[Config]:
    s = SmileParams
    return [
        base,
        replace(base, name="ATM proxy VIX9D/1.17", atm_source="vix9d"),
        replace(base, name="Hedge daily (close)", hedge="daily"),
        replace(base, name="Unhedged", hedge="none"),
        replace(base, name="No t-costs", tc_opt_min=0.0, tc_opt_pct=0.0, tc_hedge_pts=0.0, min_bid=0.0),
        replace(base, name="High t-costs", tc_opt_min=0.05, tc_opt_pct=0.05, tc_hedge_pts=0.25),
        replace(base, name="Wing lean (0.88/0.94)", smile=s(call10=0.88, call1=0.94)),
        replace(base, name="Wing rich (0.96/1.12)", smile=s(call10=0.96, call1=1.12)),
        replace(base, name="Listed expiries only", listed_only=True),
        replace(base, name="Weekly roll (4x/roll)", roll="weekly", leverage=4.0),
        replace(base, name="Synthetic intraday only", use_real_hourly=False),
    ]


def wing_grid(base: Config, daily, hourly, marks) -> pd.DataFrame:
    """Scale the call-wing vols (relative to ATM) to find the break-even wing."""
    rows = []
    for m in [0.80, 0.84, 0.88, 0.92, 0.96, 1.00, 1.04, 1.08]:
        sp = SmileParams(call10=0.92 * m, call1=1.02 * m)
        r = run(replace(base, name=f"wing x{m:.2f}", smile=sp), daily, hourly, marks)
        st = stats(r.daily)
        rows.append({"wing scale": m, "10d call / ATM": sp.call10, "1d call / ATM": sp.call1,
                     "CAGR %": st["CAGR %"], "Vol %": st["Vol %"], "Sharpe": st["Sharpe"],
                     "MaxDD %": st["MaxDD %"]})
    return pd.DataFrame(rows)


def fmt_table(df: pd.DataFrame, digits: int = 2) -> str:
    return df.round(digits).to_markdown()


def charts(res: dict, base_name: str, wing: pd.DataFrame, lev_res) -> None:
    b = res[base_name]
    d = b.daily

    # 1) NAV: base + key variants
    fig, ax = plt.subplots(figsize=(9, 4.2))
    for i, k in enumerate([base_name, "Hedge daily (close)", "Unhedged", "Listed expiries only", "Wing lean (0.88/0.94)"]):
        nv = res[k].daily.nav
        ax.plot(nv.index, nv, color=C[i], lw=1.8 if i == 0 else 1.2, label=k)
    ax.set_yscale("log")
    ax.set_title("Strategy NAV (start = 100, 1x NAV notional per daily roll, excess return)")
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout(); fig.savefig(OUT / "nav_variants.png", dpi=150); plt.close(fig)

    # 2) tearsheet for base
    fig, axs = plt.subplots(3, 2, figsize=(11, 10))
    ax = axs[0, 0]
    ax.plot(d.index, d.nav, color=C[0], label="Base (1x)")
    ax.plot(lev_res.daily.index, lev_res.daily.nav, color=C[1], label=f"Scaled {lev_res.cfg.leverage:.1f}x")
    ax.set_yscale("log"); ax.set_title("NAV (log)"); ax.legend(fontsize=8)
    ax = axs[0, 1]
    for i, (lab, nv) in [(1, (f"Scaled {lev_res.cfg.leverage:.1f}x", lev_res.daily.nav)), (0, ("Base (1x)", d.nav))]:
        dd = 100 * (nv / nv.cummax() - 1)
        ax.plot(dd.index, dd, color=C[i], lw=1.0, label=lab)
    ax.set_title("Drawdown (%)"); ax.legend(fontsize=8)
    ax = axs[1, 0]
    y = yearly(d)
    labels = [f"{v} YTD" if v == d.index[-1].year and d.index[-1].month < 12 else str(v) for v in y.index]
    ax.bar(labels, y.values, color=C[0], width=0.7)
    ax.set_title("Calendar-year return, base (%)"); ax.tick_params(axis="x", rotation=45)
    ax = axs[1, 1]
    att = attribution(d)
    keys = [k for k in att if k not in ("Open MTM",)]
    vals = [att[k] for k in keys]
    cols = [C[0] if v >= 0 else C[7] for v in vals]
    ax.barh(keys[::-1], vals[::-1], color=cols[::-1])
    ax.set_title("P&L attribution, cumulative (% of initial NAV, additive)")
    ax = axs[2, 0]
    tr = b.trades
    g = tr.groupby("target_delta").agg(implied=("delta0", "mean"), realised=("itm", "mean"))
    x = np.arange(len(g))
    ax.bar(x - 0.2, 100 * g.implied, 0.38, color=C[0], label="Delta at sale (≈ implied prob.)")
    ax.bar(x + 0.2, 100 * g.realised, 0.38, color=C[1], label="Realised ITM frequency")
    ax.set_xticks(x, [f"{int(round(100 * v))}d" for v in g.index])
    ax.set_title("Upside premium: implied vs realised ITM probability (%)"); ax.legend(fontsize=8)
    ax = axs[2, 1]
    ax.plot(wing["1d call / ATM"], wing["Sharpe"], color=C[0], marker="o", ms=4, label="Sharpe")
    ax.axhline(0, color=INK2, lw=0.8)
    ax.axvline(1.02, color=C[1], lw=1.0, ls="--", label="base assumption")
    ax.set_xlabel("1-delta call vol / ATM (10-delta call scaled alike)")
    ax.set_title("Sensitivity to call-wing pricing"); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(OUT / "tearsheet.png", dpi=150); plt.close(fig)

    # 3) P&L by delta bucket and DTE (delta-hedged, per trade attribution)
    fig, axs = plt.subplots(1, 2, figsize=(10, 3.6))
    pd_ = tr.groupby("target_delta")[["pnl_static", "pnl_hedged"]].sum()
    x = np.arange(len(pd_))
    axs[0].bar(x - 0.2, pd_.pnl_static, 0.38, color=C[0], label="Static (premium - payoff)")
    axs[0].bar(x + 0.2, pd_.pnl_hedged, 0.38, color=C[1], label="Delta-hedged")
    axs[0].set_xticks(x, [f"{int(round(100 * v))}d" for v in pd_.index])
    axs[0].set_title("Cumulative P&L by strike delta (NAV pts, before hedge costs)"); axs[0].legend(fontsize=8)
    pt = tr.groupby("dte")[["pnl_static", "pnl_hedged"]].sum()
    x = np.arange(len(pt))
    axs[1].bar(x - 0.2, pt.pnl_static, 0.38, color=C[0], label="Static")
    axs[1].bar(x + 0.2, pt.pnl_hedged, 0.38, color=C[1], label="Delta-hedged")
    axs[1].set_xticks(x, [f"{v}DTE" for v in pt.index])
    axs[1].set_title("Cumulative P&L by tenor (NAV pts)"); axs[1].legend(fontsize=8)
    fig.tight_layout(); fig.savefig(OUT / "pnl_by_slice.png", dpi=150); plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    ensure_data(args.refresh)
    OUT.mkdir(exist_ok=True)

    daily, hourly = mdata.load_market()
    base = Config(name="Base", atm_source="volvue" if daily["atm10"].notna().any() else "vix9d")
    marks = build_marks(daily.loc[base.start:], hourly, seed=base.seed, f_on=base.clock.f_on)

    res = {}
    for cfg in scenarios(base):
        m = None if not cfg.use_real_hourly else marks
        res[cfg.name] = run(cfg, daily, hourly, m)
        print(f"done: {cfg.name}")

    # vol-scaled version of base (target ~6% annualised vol)
    base_vol = stats(res["Base"].daily)["Vol %"]
    lev = round(6.0 / base_vol, 1)
    lev_res = run(replace(base, name=f"Base scaled {lev}x", leverage=lev), daily, hourly, marks)

    wing = wing_grid(base, daily, hourly, marks)

    # --- tables
    summ = pd.DataFrame({k: stats(r.daily, r.intraday) for k, r in res.items()}).T
    summ.loc[lev_res.cfg.name] = pd.Series(stats(lev_res.daily, lev_res.intraday))
    summ.to_csv(OUT / "summary.csv")
    years = pd.DataFrame({"Base": yearly(res["Base"].daily),
                          lev_res.cfg.name: yearly(lev_res.daily),
                          "Listed expiries only": yearly(res["Listed expiries only"].daily),
                          "Unhedged": yearly(res["Unhedged"].daily)})
    att = pd.DataFrame({k: attribution(res[k].daily) for k in
                        ["Base", "Hedge daily (close)", "Unhedged", "No t-costs", "High t-costs"]})

    b = res["Base"]
    tr = b.trades
    bucket = tr.groupby("target_delta").agg(
        sold=("K", "size"), avg_otm_pct=("K", lambda k: 0), delta_at_sale=("delta0", "mean"),
        itm_freq=("itm", "mean"), avg_mid=("mid", "mean"), avg_payoff=("payoff_unit", "mean"),
        pnl_static=("pnl_static", "sum"), pnl_hedged=("pnl_hedged", "sum"))
    bucket["avg_otm_pct"] = tr.assign(otm=100 * (tr.K / tr.spot0 - 1)).groupby("target_delta").otm.mean()
    bucket["payoff/premium"] = bucket.avg_payoff / bucket.avg_mid
    bucket.index = [f"{int(round(100 * v))}d" for v in bucket.index]
    tenor = tr.groupby("dte").agg(delta_at_sale=("delta0", "mean"), itm_freq=("itm", "mean"),
                                  pnl_static=("pnl_static", "sum"), pnl_hedged=("pnl_hedged", "sum"))

    # sub-periods for base
    sub = {}
    for lab, a, z in [("2011-2016", "2011", "2016"), ("2017-2021", "2017", "2021"),
                      ("2022-2026 (daily expiries listed)", "2022", "2026"),
                      ("Oct-2023+ (real hourly bars)", "2023-10-25", "2026")]:
        dd = b.daily.loc[a:z].copy()
        dd["nav"] = 100 * dd.nav / (dd.nav.iloc[0] / (1 + dd.ret.iloc[0]))   # rebase: 100 before first day
        sub[lab] = stats(dd)
    sub = pd.DataFrame(sub).T[["CAGR %", "Vol %", "Sharpe", "MaxDD %", "Worst day %"]]

    # real vs synthetic intraday on the real-hourly window
    rw = b.daily.real_hourly
    syn = res["Synthetic intraday only"].daily
    cmp_ = pd.DataFrame({
        "real hourly": b.daily.ret[rw], "synthetic": syn.ret[rw]})
    real_vs_syn = pd.DataFrame({
        "Ann. return %": 100 * cmp_.mean() * 252, "Ann. vol %": 100 * cmp_.std() * np.sqrt(252),
        "Worst day %": 100 * cmp_.min()})
    real_vs_syn.loc["daily-return correlation"] = [cmp_.corr().iloc[0, 1], np.nan, np.nan]

    worst = b.daily.assign(spx_ret=100 * b.daily.spot.pct_change(), strat_ret=100 * b.daily.ret,
                           atm_vol_pct=daily.loc[b.daily.index, "atm10"])
    worst = worst.nsmallest(10, "strat_ret")[["spx_ret", "strat_ret", "atm_vol_pct"]]
    worst.index = worst.index.date

    diag = {
        "Avg ATM vol at sale (business, %)": 100 * tr.sig_atm.mean(),
        "Avg IV sold (%)": 100 * tr.iv.mean(),
        "Avg strike OTM (%)": 100 * (tr.K / tr.spot0 - 1).mean(),
        "Avg short notional (x NAV)": (b.daily.short_notional / b.daily.nav).mean(),
        "Avg option half-spread / mid (%)": 100 * (b.daily.opt_cost.sum() / b.daily.prem_mid.sum()),
        "Strikes skipped (bid < 0.05) (%)": 100 * b.daily.n_skipped.sum() / (b.daily.n_sold.sum() + b.daily.n_skipped.sum()),
        "Premium kept after payoff, static (%)": 100 * (1 - b.daily.payoff.sum() / (b.daily.prem_mid - b.daily.opt_cost).sum()),
    }

    md = ["# Results tables (auto-generated by run_backtest.py)\n",
          f"Period: {b.daily.index[0].date()} to {b.daily.index[-1].date()} "
          f"({len(b.daily)} trading days). ATM source: {base.atm_source}.\n",
          "## Scenario summary\n", fmt_table(summ[["CAGR %", "Vol %", "Sharpe", "Sortino", "MaxDD %",
                                                   "MaxDD intraday %", "Calmar", "Worst day %",
                                                   "Worst 5d %", "Skew", "Hit rate %"]]),
          "\n## Calendar-year returns (%)\n", fmt_table(years),
          "\n## P&L attribution (% of initial NAV, additive)\n", fmt_table(att, 1),
          "\n## Base: by strike delta\n", fmt_table(bucket, 3),
          "\n## Base: by tenor\n", fmt_table(tenor, 3),
          "\n## Base: sub-periods\n", fmt_table(sub),
          "\n## Call-wing sensitivity (base)\n", fmt_table(wing.set_index("wing scale"), 3),
          "\n## Real hourly vs synthetic intraday paths (same days, Oct-2023+)\n", fmt_table(real_vs_syn),
          "\n## Base: 10 worst days\n", fmt_table(worst),
          "\n## Base: diagnostics\n", fmt_table(pd.Series(diag, name="value").to_frame()),
          ]
    (OUT / "RESULTS_TABLES.md").write_text("\n".join(md) + "\n")
    b.daily.to_csv(OUT / "base_daily.csv", float_format="%.6g")
    charts(res, "Base", wing, lev_res)
    print("\n".join(md))


if __name__ == "__main__":
    main()
