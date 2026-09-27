"""Numbers behind the two client documents (retail and institutional).

    python make_factsheets.py     # writes results/factsheet_data.json

Each programme's daily excess returns are scaled to a 5% annualised volatility
budget (returns scale linearly with notional); the institutional core is also shown
at 2.5%, and the signal at the core's notional (``*_samesize``).  Retail = XSP-style execution
(real XSP spreads, hedged 3x a day); institutional core = SPXW far-wing ladder,
hourly hedge; signal overlay = the same on the Barchart window with the call-wing
level taken from real prices and a rich-wing filter.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from run_backtest import LOW_DELTA_W, TILT_DTE_W
from ufly.backtest import Config, run
from ufly.data import DATA_DIR, load_market
from ufly.paths import build_marks

OUT = Path(__file__).resolve().parent / "results"
TARGET = 0.05
WIN = "2023-06-05"

RETAIL = dict(dtes=(10,), weights=(1.0,), deltas=(0.20, 0.25, 0.30), hedge="3x",
              tc_model="xsp", min_bid=0.10, tc_hedge_pts=0.10)
INST = dict(weights=TILT_DTE_W, delta_weights=LOW_DELTA_W)

EPISODES = [("Aug 2011 US downgrade", "2011-07-22", "2011-08-19"), ("Aug 2015 China deval", "2015-08-17", "2015-08-25"),
            ("Feb 2018 Volmageddon", "2018-01-26", "2018-02-08"), ("Q4 2018 sell-off", "2018-09-20", "2018-12-24"),
            ("Covid crash", "2020-02-19", "2020-03-23"), ("Covid rebound", "2020-03-23", "2020-04-17"),
            ("2022 bear market", "2022-01-03", "2022-10-12"), ("Nov 2022 CPI rally", "2022-11-09", "2022-11-11"),
            ("Aug 2024 yen unwind", "2024-07-16", "2024-08-05"), ("Apr 2025 tariff shock", "2025-04-02", "2025-04-08"),
            ("Apr 2025 tariff pause", "2025-04-08", "2025-04-10")]


def scaled(r: pd.Series) -> tuple[pd.Series, float]:
    k = TARGET / (r.std() * np.sqrt(252))
    return r * k, k


def stats(r: pd.Series, spx: pd.Series) -> dict:
    nav = (1 + r).cumprod()
    yrs = len(r) / 252
    cagr = nav.iloc[-1] ** (1 / yrs) - 1
    vol = r.std() * np.sqrt(252)
    dd = nav / nav.cummax() - 1
    under = dd < 0
    runs, cur = [], 0
    for u in under:
        cur = cur + 1 if u else 0
        runs.append(cur)
    m = (1 + r).groupby(r.index.to_period("M")).prod() - 1
    ms = (1 + spx.reindex(r.index).fillna(0)).groupby(r.index.to_period("M")).prod() - 1
    worst_spx = ms.nsmallest(max(3, len(ms) // 10)).index
    down = r[r < 0]
    return {
        "CAGR": cagr, "Volatility": vol, "Sharpe": r.mean() / r.std() * np.sqrt(252),
        "Sortino": r.mean() * 252 / (down.std() * np.sqrt(252)), "Calmar": cagr / -dd.min(),
        "Max drawdown": dd.min(), "Longest drawdown (months)": max(runs) / 21,
        "Worst day": r.min(), "Worst month": m.min(), "Best month": m.max(),
        "Positive months": (m > 0).mean(), "Monthly skew": m.skew(),
        "Correlation to S&P 500 (daily)": r.corr(spx.reindex(r.index)),
        "Correlation to S&P 500 (monthly)": m.corr(ms),
        "Beta to S&P 500": np.cov(r, spx.reindex(r.index).fillna(0))[0, 1] / spx.reindex(r.index).var(),
        "Avg month in S&P's worst 10% of months": m.loc[worst_spx].mean(),
        "S&P avg in those months": ms.loc[worst_spx].mean(),
    }


def monthly_rows(r: pd.Series) -> list[dict]:
    nav = 100 * (1 + r).cumprod()
    dd = nav / nav.cummax() - 1
    mn = nav.groupby(nav.index.to_period("M")).last()
    mdd = dd.groupby(dd.index.to_period("M")).min()
    return [{"month": f"{p.year}-{p.month:02d}-01", "nav": round(float(v), 2), "dd": round(float(mdd.loc[p]), 4)}
            for p, v in mn.items()]


def yearly_rows(r: pd.Series) -> list[dict]:
    y = (1 + r).groupby(r.index.year).prod() - 1
    last = r.index[-1]
    return [{"year": f"{k} YTD" if k == last.year and last.month < 12 else str(k), "ret": round(float(v), 4)}
            for k, v in y.items()]


def episodes(r: pd.Series, spx: pd.Series) -> list[dict]:
    rows = []
    for name, a, b in EPISODES:
        rr = r.loc[a:b].iloc[1:]
        ss = spx.loc[a:b].iloc[1:]
        if len(rr):
            rows.append({"episode": name, "window": f"{pd.Timestamp(a):%d %b %Y} - {pd.Timestamp(b):%d %b %Y}",
                         "strategy": float((1 + rr).prod() - 1), "spx": float((1 + ss).prod() - 1)})
    return rows


def gap_stress(daily: pd.DataFrame, k: float) -> dict:
    calm = daily[daily.atm_2d < 0.12]
    out = {}
    for c in [c for c in daily.columns if c.startswith("stress_")]:
        out[c.replace("stress_", "")] = {"median": float(daily[c].median() * k / 100),
                                         "calm median": float(calm[c].median() * k / 100),
                                         "worst 5%": float(daily[c].quantile(0.05) * k / 100)}
    return out


def programme(name, cfg, daily, hourly, marks, spx):
    res = run(cfg, daily, hourly, marks)
    r, k = scaled(res.daily.ret)
    return {"name": name, "leverage_for_5pct": k, "raw_vol": float(res.daily.ret.std() * np.sqrt(252)),
            "stats": stats(r, spx), "monthly": monthly_rows(r), "yearly": yearly_rows(r),
            "episodes": episodes(r, spx), "gap": gap_stress(res.daily, k),
            "cost_to_premium": float(res.daily.opt_cost.sum() / res.daily.prem_mid.sum()),
            "short_notional_x_nav": float((res.daily.short_notional / res.daily.nav).mean() * k),
            "returns": r, "res": res}


def main():
    daily, hourly = load_market()
    spx = daily.spx_close.pct_change().loc["2011-01-03":"2026-09-22"]
    marks_full = build_marks(daily.loc["2011-01-03":"2026-09-22"], hourly)
    marks_win = build_marks(daily.loc[WIN:"2026-09-22"], hourly)
    wf = str(DATA_DIR / "barchart_analysis" / "wing_level.csv")
    progs = {
        "retail": programme("Retail (XSP)", Config(**RETAIL), daily, hourly, marks_full, spx),
        "retail_win": programme("Retail, real-price window", Config(start=WIN, wing_file=wf, **RETAIL), daily, hourly, marks_win, spx),
        "inst": programme("Institutional core", Config(**INST), daily, hourly, marks_full, spx),
        "inst_win": programme("Institutional core, real-price window", Config(start=WIN, wing_file=wf, **INST), daily, hourly, marks_win, spx),
        "inst_sig": programme("Institutional + signal, real-price window",
                              Config(start=WIN, wing_file=wf, roll_min_wing=0.85, **INST), daily, hourly, marks_win, spx),
    }
    out = {k: {kk: vv for kk, vv in v.items() if kk not in ("returns", "res")} for k, v in progs.items()}
    # overlay charts: both window series at 5% vol, and at the core's notional (signal not levered up)
    core, sig = progs["inst_win"], progs["inst_sig"]
    k = core["leverage_for_5pct"]
    same = {"core": core["res"].daily.ret * k, "signal": sig["res"].daily.ret * k}
    for key, a, b in (("overlay", core["returns"], sig["returns"]), ("overlay_samesize", same["core"], same["signal"])):
        ov = pd.DataFrame({"core": 100 * (1 + a).cumprod(), "signal": 100 * (1 + b).cumprod()})
        ov = ov.groupby(ov.index.to_period("M")).last()
        out[key] = [{"month": f"{p.year}-{p.month:02d}-01", "series": s, "nav": round(float(ov.loc[p, c]), 2)}
                    for p in ov.index for c, s in (("core", "Core"), ("signal", "Core + signal"))]
    out["core_samesize"] = {"stats": stats(same["core"], spx), "gap": gap_stress(core["res"].daily, k)}
    out["signal_samesize"] = {"stats": stats(same["signal"], spx), "gap": gap_stress(sig["res"].daily, k),
                              "days_active": float((sig["res"].daily.n_sold > 0).mean())}
    # institutional core at a 2.5% budget: half the 5% notional
    inst = progs["inst"]
    out["inst_2p5"] = {"stats": stats(inst["returns"] / 2, spx), "gap": gap_stress(inst["res"].daily, inst["leverage_for_5pct"] / 2)}
    out["spx_stats"] = {"CAGR": float((1 + spx).prod() ** (252 / len(spx)) - 1), "Volatility": float(spx.std() * np.sqrt(252)),
                        "Max drawdown": float(((1 + spx).cumprod() / (1 + spx).cumprod().cummax() - 1).min())}
    (OUT / "factsheet_data.json").write_text(json.dumps(out, indent=1, default=float))
    for k, v in progs.items():
        s = v["stats"]
        print(f"{v['name']:45s} CAGR {100*s['CAGR']:.2f}%  vol {100*s['Volatility']:.2f}%  Sharpe {s['Sharpe']:.2f}  "
              f"Calmar {s['Calmar']:.2f}  MaxDD {100*s['Max drawdown']:.2f}%  lev {v['leverage_for_5pct']:.2f}")


if __name__ == "__main__":
    main()
