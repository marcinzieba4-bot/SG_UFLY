"""Does a richness signal help the retail (XSP) programme?  Jun 2023 - Sep 2026.

    python validate_history.py --wing-mult 1.0      # far-wing observations (wing_level.csv)
    python validate_history.py --sale-dte 10 --targets 0.05,0.10,0.20,0.30 --step 10 --half-spread 0 --tag _t10
    python run_retail_signal.py                     # writes results/RETAIL_SIGNAL.md

Two richness measures, both real / model implied vol from Barchart prices:
  far wing     3-12 delta calls, 1-5DTE (the institutional signal, wing_level.csv)
  retail zone  15-35 delta calls, 1-10DTE (the strikes the retail programme sells)
Each is a 5-observation-day rolling median.  Signals are traded on the previous day's
reading unless stated, so nothing depends on the closing price the sale is made at.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from make_factsheets import INST, RETAIL, WIN
from ufly.backtest import Config, run
from ufly.data import DATA_DIR, load_market
from ufly.paths import build_marks

OUT = Path(__file__).resolve().parent / "results"
BA = DATA_DIR / "barchart_analysis"
WING = BA / "wing_level.csv"
ZONE = BA / "retail_zone_level.csv"
REL = 126                      # trailing window (trading days) for the relative signal


def zone_series() -> Path:
    o = pd.read_csv(BA / "history_check_obs_t10.csv", parse_dates=["date"])
    z = o[(o.model_delta >= 0.15) & (o.model_delta <= 0.35)]
    w = z.groupby("date").iv_ratio.median().sort_index().rolling(5, min_periods=1).median().rename("zone_level")
    w.to_csv(ZONE)
    return ZONE


def real_trade_terciles() -> pd.DataFrame:
    """Real 20-30 delta calls sold at their 10DTE close, hedged daily, held to expiry (validate_history
    _t10 trades): P&L by tercile of each richness measure on the sale date."""
    tr = pd.read_csv(BA / "history_check_trades_t10.csv")
    tr = tr[tr.target.isin([0.20, 0.30])]
    o = pd.read_csv(BA / "history_check_obs_t10.csv", parse_dates=["date"])
    sale = o[o.dte == 10][["expiry", "target", "date"]].drop_duplicates(["expiry", "target"])
    tr = tr.merge(sale, on=["expiry", "target"], how="inner")
    for name, f in (("far wing", WING), ("retail zone", ZONE)):
        s = pd.read_csv(f, index_col=0, parse_dates=True).iloc[:, 0]
        tr[name] = s.reindex(pd.DatetimeIndex(tr.date) - pd.Timedelta(days=1), method="ffill").values
    rows = {}
    for name in ("far wing", "retail zone"):
        t = tr.dropna(subset=[name])
        t = t.assign(tercile=pd.qcut(t[name], 3, labels=["cheap", "middle", "rich"]))
        for lab, g in t.groupby("tercile", observed=True):
            rows[(name, lab)] = {"level (median)": g[name].median(), "trades": len(g),
                                 "avg P&L, bp": g.pnl_real_bp.mean(), "avg premium, bp": g.prem_real_bp.mean(),
                                 "Sharpe (per trade x sqrt 26)": g.pnl_real_bp.mean() / g.pnl_real_bp.std() * np.sqrt(26),
                                 "worst, bp": g.pnl_real_bp.min()}
    return pd.DataFrame(rows).T


def summary(r: pd.Series, k: float, daily: pd.DataFrame) -> dict:
    x = r * k
    nav = (1 + x).cumprod()
    dd = (nav / nav.cummax() - 1).min()
    yrs = len(x) / 252
    cagr = nav.iloc[-1] ** (1 / yrs) - 1
    vol = x.std() * np.sqrt(252)
    calm = daily[daily.atm_2d < 0.12]
    a, b = x.loc[:"2024-12-31"], x.loc["2025-01-01":]
    return {"Return %/yr": 100 * cagr, "Vol %": 100 * vol, "Sharpe": x.mean() / x.std() * np.sqrt(252),
            "Calmar": cagr / -dd, "MaxDD %": 100 * dd, "Ret @5% vol": 500 * x.mean() * 252 / (vol * 100) if vol else np.nan,
            "Sharpe 2023-24": a.mean() / a.std() * np.sqrt(252), "Sharpe 2025-26": b.mean() / b.std() * np.sqrt(252) if b.std() else np.nan,
            "Days sold %": 100 * (daily.n_sold > 0).mean(),
            "+5% gap, calm, same size %": calm["stress_+5%"].median() * k if len(calm) else np.nan}


def main():
    zone_series()
    terc = real_trade_terciles()
    daily, hourly = load_market()
    marks = build_marks(daily.loc[WIN:"2026-09-22"], hourly)
    base = Config(start=WIN, wing_file=str(WING), **RETAIL)
    zq = pd.read_csv(ZONE, index_col=0).iloc[:, 0].quantile([1 / 3, 2 / 3]).values
    cfgs = {
        "Retail, sells every day": base,
        "Far-wing signal >= 0.85, same-day": replace(base, roll_min_wing=0.85),
        "Far-wing signal >= 0.85": replace(base, roll_min_wing=0.85, signal_lag=1),
        "Far-wing signal >= 0.80": replace(base, roll_min_wing=0.80, signal_lag=1),
        "Far-wing signal >= 0.90": replace(base, roll_min_wing=0.90, signal_lag=1),
        f"Retail-zone signal, top 2/3 (>= {zq[0]:.2f})": replace(base, roll_min_wing=zq[0], signal_file=str(ZONE), signal_lag=1),
        f"Retail-zone signal, top 1/3 (>= {zq[1]:.2f})": replace(base, roll_min_wing=zq[1], signal_file=str(ZONE), signal_lag=1),
        "Far wing above its 6m median": replace(base, roll_min_wing=1.0, signal_rel=REL, signal_lag=1),
        "Retail zone above its 6m median": replace(base, roll_min_wing=1.0, signal_file=str(ZONE), signal_rel=REL, signal_lag=1),
    }
    res = {n: run(c, daily, hourly, marks) for n, c in cfgs.items()}
    k = 0.05 / (res["Retail, sells every day"].daily.ret.std() * np.sqrt(252))   # every variant at the baseline's notional
    rows = {n: summary(r.daily.ret, k, r.daily) for n, r in res.items()}
    # sanity: the institutional signal reproduces the factsheet (Sharpe 2.27)
    inst = run(Config(start=WIN, wing_file=str(WING), roll_min_wing=0.85, **INST), daily, hourly, marks).daily.ret
    t = pd.DataFrame(rows).T
    md = [f"# Retail programme with a richness signal ({WIN} to 2026-09-22)\n",
          "Retail = XSP-style execution (real XSP spreads), 20-30 delta calls at 10DTE, hedged 3x a day. "
          "Every variant is shown at the notional that runs the every-day programme at 5% volatility; "
          "'Ret @5% vol' re-scales each to 5% volatility. Signals use the previous day's reading unless marked same-day.\n",
          t.round(2).to_markdown(), "\n## Real trades by richness at the sale date\n",
          "Real 20-30 delta SPXW calls sold at their 10DTE close, hedged daily, held to expiry (one expiry every 10 days).\n",
          terc.round(2).to_markdown(),
          f"\nSanity check: institutional core + far-wing signal, same-day, Sharpe {inst.mean() / inst.std() * np.sqrt(252):.2f}.\n"]
    (OUT / "RETAIL_SIGNAL.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
