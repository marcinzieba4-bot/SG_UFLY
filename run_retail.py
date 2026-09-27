"""Retail implementation check.

1. Can futures emulate selling the deep-OTM calls?  The synthetic short strip holds
   minus the strip's delta in futures (no option premium, no payoff): it is exactly
   the opposite of the strip backtest's hedge leg.
2. What is left after retail execution costs?  XSP (mini-SPX, 1/10 size) spreads on
   5-10 delta calls were ~20% of mid (half-spread) vs ~4% for SPXW (quotes of
   2026-09-25).  Hedge with SPY shares (fractional, penny spread) or MES futures.

    python run_retail.py     # needs data from run_backtest.py / run_barchart_window.py
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from run_backtest import LOW_DELTA_W, TILT_DELTA_W, TILT_DTE_W
from ufly.backtest import Config, run
from ufly.data import DATA_DIR, load_market
from ufly.metrics import stats
from ufly.paths import build_marks

OUT = Path(__file__).resolve().parent / "results"
START = "2023-06-05"

# execution cost sets (half-spread paid when selling; SPX-point equivalents)
COSTS = {
    "SPXW (institutional)": dict(tc_opt_min=0.025, tc_opt_pct=0.03, min_bid=0.05, tc_hedge_pts=0.15),
    "XSP, limit orders (half the spread)": dict(tc_opt_min=0.05, tc_opt_pct=0.10, min_bid=0.10, tc_hedge_pts=0.10),
    "XSP, crossing the spread": dict(tc_opt_min=0.05, tc_opt_pct=0.20, min_bid=0.10, tc_hedge_pts=0.10),
}


def futures_only(daily_csv: Path) -> pd.DataFrame:
    d = pd.read_csv(daily_csv, index_col=0, parse_dates=True)
    prev = d.nav.shift().fillna(100.0)
    series = {"Real options: sell strip, hedge with futures": d.ret,
              "Futures only: synthetic short strip": (-d.hedge_pnl - d.hedge_cost) / prev}
    rows = {}
    for lab, r in series.items():
        for per, a in (("2011-2026", "2011"), ("Jun-2023+", START)):
            x = r.loc[a:]
            nav = (1 + x).cumprod()
            rows[(lab, per)] = {"Ann. return %": 100 * x.mean() * 252, "Vol %": 100 * x.std() * np.sqrt(252),
                                "Sharpe": x.mean() / x.std() * np.sqrt(252),
                                "MaxDD %": 100 * (nav / nav.cummax() - 1).min()}
    return pd.DataFrame(rows).T


TENOR_BINS, TENOR_LABELS = [0, 1, 3, 5, 10, 15, 22, 32], ["1", "2-3", "4-5", "6-10", "11-15", "16-22", "23-32"]
DELTA_BINS = [0, 0.03, 0.07, 0.12, 0.2, 0.3, 0.45, 0.55]
DELTA_LABELS = ["1-3d", "3-7d", "7-12d", "12-20d", "20-30d", "30-45d", "~ATM"]


def spread_map(refresh: bool = False) -> pd.DataFrame:
    """Median half-spread (% of mid and bp of notional) for SPXW and XSP calls by days to
    expiry x delta, from Yahoo closing quotes.  Only the aggregated medians are saved."""
    path = OUT / "spread_map.csv"
    if path.exists() and not refresh:
        return pd.read_csv(path)
    import yfinance as yf
    from scipy.optimize import brentq
    from ufly.vol import bs_call
    spot = float(yf.Ticker("^GSPC").history(period="5d").Close.iloc[-1])
    rows = []
    for tk, pref, scale in (("^XSP", "XSP", 0.1), ("^SPX", "SPXW", 1.0)):
        t = yf.Ticker(tk)
        for e in t.options:
            oc = t.option_chain(e)
            last = pd.to_datetime(oc.calls.lastTradeDate, utc=True).max().tz_convert("America/New_York")
            now = last.normalize().tz_localize(None) + pd.Timedelta(hours=16)
            if (pd.Timestamp(e) - now).days > 45:
                break
            c = oc.calls[oc.calls.contractSymbol.str.startswith(pref)].set_index("strike")
            p = oc.puts[oc.puts.contractSymbol.str.startswith(pref)].set_index("strike")
            S = spot * scale
            Ks = c.index.intersection(p.index)
            if len(Ks) < 6:
                continue
            near = Ks[np.argsort(np.abs(Ks - S))[:6]]
            F = float(np.median(near + ((c.bid + c.ask) / 2 - (p.bid + p.ask) / 2).loc[near]))
            T = ((pd.Timestamp(e) + pd.Timedelta(hours=16)) - now).total_seconds() / (365 * 86400)
            dte = int(np.busday_count(now.date(), pd.Timestamp(e).date()))
            for k, r in c[c.index > F * 0.995].iterrows():
                if not (r.bid > 0 and r.ask > r.bid):
                    continue
                mid = (r.bid + r.ask) / 2
                try:
                    v = brentq(lambda x: bs_call(F, k, x, T)[0] - mid, 1e-3, 5)
                except ValueError:
                    continue
                rows.append(dict(product=pref, dte=dte, delta=float(bs_call(F, k, v, T)[1]),
                                 hs_pct=100 * (r.ask - r.bid) / 2 / mid, cost_bp=1e4 * (r.ask - r.bid) / 2 / S,
                                 volume=r.volume))
    r = pd.DataFrame(rows)
    r["tenor"] = pd.cut(r.dte, TENOR_BINS, labels=TENOR_LABELS)
    r["dbucket"] = pd.cut(r.delta, DELTA_BINS, labels=DELTA_LABELS)
    m = (r.groupby(["product", "tenor", "dbucket"], observed=True)
         .agg(hs_pct=("hs_pct", "median"), cost_bp=("cost_bp", "median"), volume=("volume", "median"), n=("dte", "size"))
         .reset_index())
    m.to_csv(path, index=False, float_format="%.4g")
    return m


def tenor_table(smap: pd.DataFrame) -> pd.DataFrame:
    """Real-price edge (Barchart SPXW history, sold at mid, daily-close delta hedge, held to
    expiry) by sale tenor x strike delta, net of the real XSP / SPXW half-spread."""
    raw = DATA_DIR / "barchart_analysis"
    steps = {"_t5lo": 5, "_t5atm": 5, "_t5hi": 10, "_t10": 10}      # sampling interval (trading days)
    frames = [pd.read_csv(raw / f"history_check_trades{t}.csv", parse_dates=["expiry"]).assign(step=k)
              for t, k in steps.items() if (raw / f"history_check_trades{t}.csv").exists()]
    tr = pd.concat(frames, ignore_index=True)
    tr["tenor"] = pd.cut(tr.sale_dte, TENOR_BINS, labels=TENOR_LABELS).astype(str)
    tr["dbucket"] = pd.cut(tr.delta_real0, DELTA_BINS, labels=DELTA_LABELS).astype(str)
    cost = smap.assign(tenor=smap.tenor.astype(str), dbucket=smap.dbucket.astype(str)) \
        .pivot_table(index=["tenor", "dbucket"], columns="product", values="cost_bp")
    tr = tr.join(cost, on=["tenor", "dbucket"])
    rows = []
    for (n, db), g in tr.groupby(["sale_dte", "dbucket"]):
        if len(g) < 20:
            continue
        per = g.groupby("expiry")
        gross = per.pnl_real_bp.mean()
        row = {"sale DTE": n, "delta at sale": db, "trades": len(g),
               "gross edge (bp/trade)": g.pnl_real_bp.mean(),
               "gross Sharpe": gross.mean() / gross.std() * np.sqrt(252 / g.step.iloc[0])}
        for prod in ("XSP", "SPXW"):
            c = g[prod].median()
            net = g.pnl_real_bp - g[prod]
            row[f"{prod} cost (bp)"] = c
            row[f"{prod} net (bp/trade)"] = net.mean()
            row[f"{prod} net (bp/day held)"] = net.mean() / n
        row["worst trade (bp)"] = g.pnl_real_bp.min()
        rows.append(row)
    order = {k: i for i, k in enumerate(DELTA_LABELS)}
    return pd.DataFrame(rows).sort_values(["sale DTE", "delta at sale"], key=lambda s: s.map(order) if s.name == "delta at sale" else s)


CANDIDATES = {
    "Far-OTM, low-delta tilt (1-5d), 2-5DTE": dict(weights=TILT_DTE_W, delta_weights=LOW_DELTA_W),
    "Far-OTM, 5-10d tilt, 2-5DTE": dict(weights=TILT_DTE_W, delta_weights=TILT_DELTA_W),
    "20-30d calls, 5DTE": dict(dtes=(5,), weights=(1.0,), deltas=(0.20, 0.25, 0.30)),
    "20-30d calls, 10DTE": dict(dtes=(10,), weights=(1.0,), deltas=(0.20, 0.25, 0.30)),
    "30-45d calls, 10DTE": dict(dtes=(10,), weights=(1.0,), deltas=(0.30, 0.375, 0.45)),
    "ATM calls, 5DTE": dict(dtes=(5,), weights=(1.0,), deltas=(0.50,)),
}


def cheap_options_engine(daily, hourly) -> pd.DataFrame:
    """Full engine (daily roll, overlapping positions) with XSP execution costs from real quotes,
    for far-OTM strips vs cheaper-to-trade nearer-the-money calls, hedged hourly / 3x / daily."""
    wf = DATA_DIR / "barchart_analysis" / "wing_level.csv"
    rows = {}
    for period, start in (("2011-2026", "2011-01-03"), ("Jun-2023+", START)):
        marks = build_marks(daily.loc[start:"2026-09-22"], hourly)
        for name, spec in CANDIDATES.items():
            for hedge in ("hourly", "3x", "daily"):
                cfg = Config(name=name, start=start, hedge=hedge, tc_model="xsp", min_bid=0.10, tc_hedge_pts=0.10, **spec)
                if period.startswith("Jun") and wf.exists():
                    cfg = replace(cfg, wing_file=str(wf))
                r = run(cfg, daily, hourly, marks)
                st = stats(r.daily)
                vol = st["Vol %"]
                k = 5.0 / vol if vol > 0 else np.nan
                calm = r.daily[r.daily.atm_2d < 0.12]
                rows[(period, name, hedge)] = {
                    "Sharpe": st["Sharpe"], "Ret @5% vol": 100 * r.daily.ret.mean() * 252 * k,
                    "MaxDD @5% vol": st["MaxDD %"] * k, "Worst day @5% vol": st["Worst day %"] * k,
                    "gap +5% calm @5% vol": calm["stress_+5%"].median() * k,
                    "gap -5% calm @5% vol": calm["stress_-5%"].median() * k,
                    "cost / premium %": 100 * r.daily.opt_cost.sum() / max(r.daily.prem_mid.sum(), 1e-9)}
                print("done:", period, name, hedge, flush=True)
    return pd.DataFrame(rows).T


def main():
    fut = futures_only(OUT / "tilted_daily.csv")
    smap = spread_map()
    tt = tenor_table(smap)
    eng = cheap_options_engine(*load_market())
    daily, hourly = load_market()
    wf = DATA_DIR / "barchart_analysis" / "wing_level.csv"
    have_wing = wf.exists()
    rows = {}
    for period, start in (("2011-2026", "2011-01-03"), ("Jun-2023+ (real wing)", START)):
        marks = build_marks(daily.loc[start:"2026-09-22"], hourly)
        for cname, cost in COSTS.items():
            for sname, extra in (("tilted", dict(delta_weights=TILT_DELTA_W)),
                                 ("low-delta", dict(delta_weights=LOW_DELTA_W)),
                                 ("low-delta, rich-wing days only", dict(delta_weights=LOW_DELTA_W, roll_min_wing=0.85))):
                if "rich" in sname and not (period.startswith("Jun") and have_wing):
                    continue
                cfg = Config(name=f"{sname}", start=start, weights=TILT_DTE_W, **extra, **cost)
                if period.startswith("Jun") and have_wing:
                    cfg = replace(cfg, wing_file=str(wf))
                st = stats(run(cfg, daily, hourly, marks).daily)
                rows[(period, cname, sname)] = {k: st[k] for k in ("CAGR %", "Vol %", "Sharpe", "MaxDD %")}
                print("done:", period, cname, sname, flush=True)
    t = pd.DataFrame(rows).T
    md = ["# Retail implementation check\n",
          "## 1. Futures cannot emulate the short options\n",
          "The synthetic short strip holds minus the strip's delta in futures, hourly (no premium, no payoff).\n",
          fut.round(2).to_markdown(),
          "\n## 2. Real options with retail execution costs\n",
          "Half-spread paid on each sale: SPXW max(0.025, 3% of mid); XSP limit orders max(0.05, 10%); XSP crossing "
          "max(0.05, 20%) (SPX-point equivalents; XSP tick 0.01 = 0.10 SPX points, so strikes with a bid below "
          "0.10 are skipped). Hedge with SPY shares / MES: 0.10 points per unit. Jun-2023+ rows use the daily "
          "wing level from real Barchart prices.\n",
          t.round(2).to_markdown(),
          "\n## 3. Sell a cheaper-to-trade option and delta-hedge?\n",
          "Real SPXW prices (Barchart, Jun 2023 - Sep 2026): each contract sold at its closing mid, delta-hedged at "
          "each daily close (retail-friendly), held to expiry. Net = minus the median real half-spread for that "
          "tenor x delta cell (spread map from Yahoo closing quotes). Delta bucket = real delta at the sale.\n",
          tt.round(2).to_markdown(index=False),
          "\nMedian half-spread, % of premium (XSP):\n",
          smap[smap["product"] == "XSP"].pivot_table(index="tenor", columns="dbucket", values="hs_pct",
                                                     observed=True).round(1).to_markdown(),
          "\n## 4. Engine: far-OTM strip vs cheaper-to-trade calls, XSP costs, by hedge frequency\n",
          "Daily roll with overlapping positions, 1x NAV notional per roll, crossing the real XSP spread "
          "(half-spread = min(0.10 + 20% x mid, 0.70 + 1.2% x mid) SPX points), hedged with SPY/MES at 0.10 points per "
          "unit. Risk columns are scaled to 5% annualised vol so rows compare; gap = instant move on the closing "
          "book, calm-market median. The 12-45 delta and ATM pricing is validated against real prices "
          "(real / model IV 1.01-1.04).\n",
          eng.round(2).to_markdown()]
    (OUT / "RETAIL.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
