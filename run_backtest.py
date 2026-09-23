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
from ufly.vol import ClockParams, SmileParams

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

# weight tilt: 80% of strike notional on 5-10 delta, 70% of roll notional on 4-5DTE
TILT_DELTA_W = (0.05,) * 4 + (0.8 / 6,) * 6
TILT_DTE_W = (0.15, 0.15, 0.35, 0.35)
MAIN = "Tilted"
V1 = "v1 assumptions (equal wt)"
STRESS = "Tilted, stress pricing"
TARGET_VOL = 5.0


def ensure_data(refresh: bool) -> None:
    if refresh or not (mdata.DATA_DIR / "daily.csv").exists():
        mdata.download(refresh=True)
    if os.environ.get("VOLVUE_API_KEY") and (refresh or volvue.load("SPXW") is None):
        volvue.download("SPX")
        volvue.download("SPXW")


def scenarios() -> list[Config]:
    tilted = Config(name=MAIN, weights=TILT_DTE_W, delta_weights=TILT_DELTA_W)
    return [
        Config(name=V1, atm_source="volvue", short_end=False, atm_mult=1.0,
               smile=SmileParams(call10=0.92, call1=1.02), clock=ClockParams(w_nt=0.10)),
        Config(name="Calibrated, equal weights"),
        tilted,
        Config(name="Concentrated (5-10d, 4-5DTE only)", dtes=(4, 5), weights=(0.5, 0.5),
               deltas=tuple(np.round(np.arange(5, 11) / 100, 2))),
        replace(tilted, name="Tilted, no chain haircut (ATM x1.00)", atm_mult=1.0),
        replace(tilted, name="Tilted, hedge daily (close)", hedge="daily"),
        replace(tilted, name="Tilted, unhedged", hedge="none"),
        replace(tilted, name="Tilted, high t-costs", tc_opt_min=0.05, tc_opt_pct=0.05, tc_hedge_pts=0.25),
        replace(tilted, name="Tilted, listed expiries only", listed_only=True),
        replace(tilted, name=STRESS, wing_pre2022=0.9, wing_vol_slope=0.5, atm_mult=0.94,
                tc_opt_min=0.05, tc_opt_pct=0.05, tc_hedge_pts=0.25),
        Config(name="ATM calls (50d), 4-5DTE", dtes=(4, 5), weights=(0.5, 0.5), deltas=(0.5,)),
        replace(tilted, name="ATM replica of tilted strip (1DTE)", mode="replica", replica_dte=1),
    ]


def sensitivity(base: Config, daily, hourly, marks) -> pd.DataFrame:
    """Re-price the tilted strategy with the call wing and the ATM level shifted."""
    rows = []
    for kind, grid in (("wing", [0.80, 0.85, 0.90, 0.95, 1.00, 1.05]), ("atm", [0.90, 0.94, 0.973, 1.00, 1.03])):
        for m in grid:
            if kind == "wing":
                cfg = replace(base, smile=SmileParams(call10=1.01 * m, call1=1.16 * m))
            else:
                cfg = replace(base, atm_mult=m)
            st = stats(run(cfg, daily, hourly, marks).daily)
            rows.append({"shift": kind, "multiplier": m, "10d call vol/ATM": cfg.smile.call10,
                         "1d call vol/ATM": cfg.smile.call1, "ATM mult": cfg.atm_mult,
                         "CAGR %": st["CAGR %"], "Vol %": st["Vol %"], "Sharpe": st["Sharpe"],
                         "MaxDD %": st["MaxDD %"]})
    return pd.DataFrame(rows)


def fmt_table(df: pd.DataFrame, digits: int = 2) -> str:
    return df.round(digits).to_markdown()


def scaled_nav(r: pd.Series, target=TARGET_VOL) -> pd.Series:
    k = target / (100 * r.std() * np.sqrt(252))
    return 100 * (1 + k * r).cumprod()


def charts(res: dict, sens: pd.DataFrame, lev_res) -> None:
    b = res[MAIN]
    d = b.daily

    fig, ax = plt.subplots(figsize=(9, 4.4))
    keys = [MAIN, STRESS, "Concentrated (5-10d, 4-5DTE only)", V1,
            "ATM calls (50d), 4-5DTE", "ATM replica of tilted strip (1DTE)"]
    for i, k in enumerate(keys):
        nv = scaled_nav(res[k].daily.ret)
        ax.plot(nv.index, nv, color=C[i], lw=1.8 if i == 0 else 1.1, label=k)
    ax.set_yscale("log")
    ax.set_title(f"NAV, each scaled to {TARGET_VOL:.0f}% annualised vol (excess return)")
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout(); fig.savefig(OUT / "nav_variants.png", dpi=150); plt.close(fig)

    fig, axs = plt.subplots(3, 2, figsize=(11, 10))
    ax = axs[0, 0]
    ax.plot(d.index, d.nav, color=C[0], label="Tilted (1x)")
    ax.plot(lev_res.daily.index, lev_res.daily.nav, color=C[1], label=f"Scaled {lev_res.cfg.leverage:.1f}x")
    ax.set_yscale("log"); ax.set_title("NAV (log), tilted strategy, calibrated pricing"); ax.legend(fontsize=8)
    ax = axs[0, 1]
    for i, (lab, nv) in [(1, (f"Scaled {lev_res.cfg.leverage:.1f}x", lev_res.daily.nav)), (0, ("Tilted (1x)", d.nav))]:
        dd = 100 * (nv / nv.cummax() - 1)
        ax.plot(dd.index, dd, color=C[i], lw=1.0, label=lab)
    ax.set_title("Drawdown (%)"); ax.legend(fontsize=8)
    ax = axs[1, 0]
    y = yearly(lev_res.daily)
    labels = [f"{v} YTD" if v == d.index[-1].year and d.index[-1].month < 12 else str(v) for v in y.index]
    ax.bar(labels, y.values, color=[C[0] if v >= 0 else C[7] for v in y.values], width=0.7)
    ax.set_title(f"Calendar-year return, scaled {lev_res.cfg.leverage:.1f}x (%)"); ax.tick_params(axis="x", rotation=45)
    ax = axs[1, 1]
    att = attribution(d)
    keys = [k for k in att if k != "Open MTM"]
    vals = [att[k] for k in keys]
    ax.barh(keys[::-1], vals[::-1], color=[C[0] if v >= 0 else C[7] for v in vals][::-1])
    ax.set_title("P&L attribution, tilted 1x (% of initial NAV, additive)")
    ax = axs[2, 0]
    tr = b.trades
    g = tr.groupby("target_delta").agg(implied=("delta0", "mean"), realised=("itm", "mean"))
    x = np.arange(len(g))
    ax.bar(x - 0.2, 100 * g.implied, 0.38, color=C[0], label="Delta at sale (≈ implied prob.)")
    ax.bar(x + 0.2, 100 * g.realised, 0.38, color=C[1], label="Realised ITM frequency")
    ax.set_xticks(x, [f"{int(round(100 * v))}d" for v in g.index])
    ax.set_title("Implied vs realised ITM probability (%)"); ax.legend(fontsize=8)
    ax = axs[2, 1]
    for i, kind, lab in [(0, "wing", "Call-wing vol multiplier"), (1, "atm", "ATM vol multiplier")]:
        s = sens[sens["shift"] == kind]
        ax.plot(s.multiplier, s.Sharpe, color=C[i], marker="o", ms=4, label=lab)
    ax.axhline(0, color=INK2, lw=0.8)
    ax.axvline(1.0, color=INK2, lw=0.8, ls="--")
    ax.set_xlabel("multiplier on calibrated pricing (1.0 = matches SPXW chain 2026-09-22)")
    ax.set_title("Sharpe vs option pricing assumptions"); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(OUT / "tearsheet.png", dpi=150); plt.close(fig)

    fig, axs = plt.subplots(1, 2, figsize=(10, 3.6))
    pd_ = tr.groupby("target_delta")[["pnl_static", "pnl_hedged"]].sum()
    x = np.arange(len(pd_))
    axs[0].bar(x - 0.2, pd_.pnl_static, 0.38, color=C[0], label="Static (premium - payoff)")
    axs[0].bar(x + 0.2, pd_.pnl_hedged, 0.38, color=C[1], label="Delta-hedged")
    axs[0].set_xticks(x, [f"{int(round(100 * v))}d" for v in pd_.index])
    axs[0].set_title("Tilted: cumulative P&L by strike delta (NAV pts)"); axs[0].legend(fontsize=8)
    pt = tr.groupby("dte")[["pnl_static", "pnl_hedged"]].sum()
    x = np.arange(len(pt))
    axs[1].bar(x - 0.2, pt.pnl_static, 0.38, color=C[0], label="Static")
    axs[1].bar(x + 0.2, pt.pnl_hedged, 0.38, color=C[1], label="Delta-hedged")
    axs[1].set_xticks(x, [f"{v}DTE" for v in pt.index])
    axs[1].set_title("Tilted: cumulative P&L by tenor (NAV pts)"); axs[1].legend(fontsize=8)
    fig.tight_layout(); fig.savefig(OUT / "pnl_by_slice.png", dpi=150); plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    ensure_data(args.refresh)
    OUT.mkdir(exist_ok=True)

    daily, hourly = mdata.load_market()
    cfgs = scenarios()
    base = cfgs[0]
    marks = build_marks(daily.loc[base.start:base.end], hourly, seed=base.seed, f_on=base.clock.f_on)

    res = {}
    for cfg in cfgs:
        res[cfg.name] = run(cfg, daily, hourly, marks)
        print(f"done: {cfg.name}", flush=True)
    tilted = next(c for c in cfgs if c.name == MAIN)

    lev = round(6.0 / stats(res[MAIN].daily)["Vol %"], 1)
    lev_res = run(replace(tilted, name=f"Tilted scaled {lev}x", leverage=lev), daily, hourly, marks)
    sens = sensitivity(tilted, daily, hourly, marks)
    print("done: sensitivity", flush=True)

    # --- tables
    summ = pd.DataFrame({k: stats(r.daily, r.intraday) for k, r in res.items()}).T
    summ.loc[lev_res.cfg.name] = pd.Series(stats(lev_res.daily, lev_res.intraday))
    summ[f"Ret @{TARGET_VOL:.0f}% vol"] = [
        100 * r.daily.ret.mean() * 252 * TARGET_VOL / (100 * r.daily.ret.std() * np.sqrt(252))
        for r in list(res.values()) + [lev_res]]
    summ.to_csv(OUT / "summary.csv")
    years = pd.DataFrame({k: yearly(res[k].daily) for k in
                          [MAIN, STRESS, "Calibrated, equal weights", V1, "ATM calls (50d), 4-5DTE",
                           "ATM replica of tilted strip (1DTE)"]})
    years[lev_res.cfg.name] = yearly(lev_res.daily)
    att = pd.DataFrame({k: attribution(res[k].daily) for k in
                        [V1, "Calibrated, equal weights", MAIN, "Tilted, hedge daily (close)",
                         "ATM calls (50d), 4-5DTE", "ATM replica of tilted strip (1DTE)"]})

    b = res[MAIN]
    tr = b.trades
    bucket = tr.groupby("target_delta").agg(
        sold=("K", "size"), delta_at_sale=("delta0", "mean"), itm_freq=("itm", "mean"),
        avg_mid=("mid", "mean"), avg_payoff=("payoff_unit", "mean"),
        pnl_static=("pnl_static", "sum"), pnl_hedged=("pnl_hedged", "sum"))
    bucket.insert(1, "avg_otm_pct", tr.assign(otm=100 * (tr.K / tr.spot0 - 1)).groupby("target_delta").otm.mean())
    bucket["payoff/premium"] = bucket.avg_payoff / bucket.avg_mid
    bucket.index = [f"{int(round(100 * v))}d" for v in bucket.index]
    tenor = tr.groupby("dte").agg(delta_at_sale=("delta0", "mean"), itm_freq=("itm", "mean"),
                                  pnl_static=("pnl_static", "sum"), pnl_hedged=("pnl_hedged", "sum"))

    sub = {}
    for lab, a, z in [("2011-2016", "2011", "2016"), ("2017-2021", "2017", "2021"),
                      ("2022-2026 (daily expiries listed)", "2022", "2026"),
                      ("Oct-2023+ (real hourly bars)", "2023-10-25", "2026")]:
        dd = b.daily.loc[a:z].copy()
        dd["nav"] = 100 * dd.nav / (dd.nav.iloc[0] / (1 + dd.ret.iloc[0]))   # rebase: 100 before first day
        sub[lab] = stats(dd)
    sub = pd.DataFrame(sub).T[["CAGR %", "Vol %", "Sharpe", "MaxDD %", "Worst day %"]]

    worst = b.daily.assign(spx_ret=100 * b.daily.spot.pct_change(), strat_ret=100 * b.daily.ret,
                           atm_2d_pct=100 * b.daily.atm_2d)
    worst = worst.nsmallest(10, "strat_ret")[["spx_ret", "strat_ret", "atm_2d_pct"]]
    worst.index = worst.index.date

    diag = {
        "Avg 2DTE ATM vol (business, %)": 100 * b.daily.atm_2d.mean(),
        "Avg 5DTE ATM vol (business, %)": 100 * b.daily.atm_5d.mean(),
        "Avg IV sold (%)": 100 * tr.iv.mean(),
        "Avg strike OTM (%)": 100 * (tr.K / tr.spot0 - 1).mean(),
        "Avg short notional (x NAV)": (b.daily.short_notional / b.daily.nav).mean(),
        "Avg option half-spread / mid (%)": 100 * (b.daily.opt_cost.sum() / b.daily.prem_mid.sum()),
        "Strikes skipped (bid < 0.05) (%)": 100 * b.daily.n_skipped.sum() / (b.daily.n_sold.sum() + b.daily.n_skipped.sum()),
        "Premium kept after payoff, static (%)": 100 * (1 - b.daily.payoff.sum() / (b.daily.prem_mid - b.daily.opt_cost).sum()),
    }

    # gap stress: instantaneous shocks on each closing book (% of NAV)
    def stress_table(dd: pd.DataFrame, lab: str) -> pd.DataFrame:
        sc = dd.filter(like="stress_")
        calm = dd.atm_2d < 0.12
        t = pd.DataFrame({"median": sc.median(), "worst 5%": sc.quantile(0.05), "worst": sc.min(),
                          "median, calm (2d ATM<12%)": sc[calm].median(), "worst, calm": sc[calm].min()}).T
        t.columns = [c.replace("stress_", "gap ") for c in t.columns]
        t.index = [f"{lab}: {i}" for i in t.index]
        return t
    stress = pd.concat([stress_table(b.daily, "1x"), stress_table(lev_res.daily, f"{lev_res.cfg.leverage:.1f}x")])
    gap = (daily.spx_open / daily.spx_close.shift() - 1)[daily.index >= "2017-01-01"] * 100
    gaps = pd.DataFrame({"largest up-gaps %": gap.nlargest(5).round(2).values,
                         "date (up)": gap.nlargest(5).index.date,
                         "largest down-gaps %": gap.nsmallest(5).round(2).values,
                         "date (down)": gap.nsmallest(5).index.date})

    chain_md = []
    chain = mdata.DATA_DIR / "chains" / "spx_2026-09-22.json"
    if chain.exists():
        from validate_chain import bid_ratio, compare
        day, strip, fit = compare(chain, Config())
        piv = (strip.assign(r=strip.market_bid / strip.model_bid)
               .pivot_table(index="delta", columns="dte", values="r"))
        atm = strip.groupby("dte")[["model_atm", "market_atm"]].first()
        chain_md = [f"\n## Pricing check vs real SPXW chain ({day.date()} close)\n",
                    "ATM vol, business time:\n", fmt_table(atm, 4),
                    "\nMarket bid / model bid:\n", fmt_table(piv),
                    f"\nPremium-weighted market/model bid: {bid_ratio(strip):.3f}. "
                    f"Market call-wing fit: 10d = {fit['call10/ATM']:.3f} x ATM, 1d = {fit['call1/ATM']:.3f} x ATM.\n"]

    cols = ["CAGR %", "Vol %", "Sharpe", f"Ret @{TARGET_VOL:.0f}% vol", "MaxDD %", "MaxDD intraday %",
            "Worst day %", "Worst 5d %", "Skew", "Hit rate %"]
    md = ["# Results tables (auto-generated by run_backtest.py)\n",
          f"Period: {b.daily.index[0].date()} to {b.daily.index[-1].date()} ({len(b.daily)} trading days). "
          "Pricing: VolVue SPXW 10d ATM -> short-end (VIX1D/VIX9D) -> call wing, calibrated to the SPXW chain "
          "(except the v1 row).\n",
          "## Scenario summary\n", fmt_table(summ[cols]),
          "\n## Calendar-year returns (%)\n", fmt_table(years),
          "\n## P&L attribution (% of initial NAV, additive)\n", fmt_table(att, 1),
          "\n## Tilted: by strike delta\n", fmt_table(bucket, 3),
          "\n## Tilted: by tenor\n", fmt_table(tenor, 3),
          "\n## Tilted: sub-periods\n", fmt_table(sub),
          "\n## Tilted: sensitivity to option pricing\n", fmt_table(sens.set_index(["shift", "multiplier"]), 3),
          *chain_md,
          "\n## Tilted: gap stress test (instantaneous move on the closing book, % of NAV)\n",
          "Hourly hedging cannot react to an overnight gap. Vol moves with the spot-vol beta.\n",
          fmt_table(stress),
          "\nLargest SPX overnight gaps since 2017 (open vs previous close):\n", gaps.to_markdown(index=False),
          "\n## Tilted: 10 worst days\n", fmt_table(worst),
          "\n## Tilted: diagnostics\n", fmt_table(pd.Series(diag, name="value").to_frame()),
          ]
    (OUT / "RESULTS_TABLES.md").write_text("\n".join(md) + "\n")
    b.daily.to_csv(OUT / "tilted_daily.csv", float_format="%.6g")
    old = OUT / "base_daily.csv"
    if old.exists():
        old.unlink()
    charts(res, sens, lev_res)
    print("\n".join(md))


if __name__ == "__main__":
    main()
