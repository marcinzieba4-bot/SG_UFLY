"""Check the model's option prices against a real SPXW chain.

    python validate_chain.py                  # CBOE delayed-quotes snapshot, compare, save to data/chains/
    python validate_chain.py --source yahoo   # Yahoo chain (closing NBBO; use when the CBOE CDN is stale)
    python validate_chain.py --source barchart  # barchart.com chain incl. Barchart IV / delta (headless Chromium)
    python validate_chain.py --file X         # use a saved snapshot (.json CBOE or .csv Yahoo)
    python validate_chain.py --calibrate      # also solve the ATM multiplier that matches market bids

SPX/SPXW options are listed only on Cboe, so these quotes are the same NBBO a
broker such as IBKR shows (IBKR adds its own greeks / model IV).

The model is priced at each expiry's put-call-parity forward, so snapshots taken
at slightly different times (sources differ) stay comparable.
For each 2-5DTE expiry it compares the model ATM vol with the market ATM vol
(business time) and the model bid with the real bid for the 1..10-delta strip,
and fits the call wing (vol / ATM vs normalised moneyness) to the market.
Run it daily: the history of snapshots is the data needed to test whether the
upside wing premium assumed in the backtest is stable.
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.special import ndtr, ndtri

from ufly.backtest import Config, atm_vols, short_end_factor
from ufly.data import DATA_DIR, load_market
from ufly.vol import Smile, VarianceClock, bs_call

URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/_SPX.json"
CHAINS = DATA_DIR / "chains"


def fetch(source: str = "cboe", n_exp: int = 8) -> Path:
    CHAINS.mkdir(parents=True, exist_ok=True)
    if source == "cboe":
        raw = urllib.request.urlopen(URL, timeout=120).read()
        day = json.loads(raw)["data"]["last_trade_time"][:10]
        p = CHAINS / f"spx_{day}.json"
        p.write_bytes(raw)
        return p
    if source == "barchart":
        from ufly.barchart import fetch_chain
        ch, spot, ts = fetch_chain(n_exp)
        ch["spot"], ch["day"], ch["snapshot"] = spot, ts.date().isoformat(), ts.isoformat()
        p = CHAINS / f"spx_{ts.date().isoformat()}_barchart.csv"
        ch.to_csv(p, index=False)
        return p
    import yfinance as yf
    t = yf.Ticker("^SPX")
    rows = []
    for e in t.options[:n_exp]:
        oc = t.option_chain(e)
        for cp, df in (("C", oc.calls), ("P", oc.puts)):
            df = df[df.contractSymbol.str.startswith("SPXW")]
            rows.append(pd.DataFrame({"exp": pd.Timestamp(e), "cp": cp, "K": df.strike, "bid": df.bid,
                                      "ask": df.ask, "volume": df.volume, "oi": df.openInterest,
                                      "last_trade": df.lastTradeDate}))
    ch = pd.concat(rows, ignore_index=True)
    last = pd.to_datetime(ch.last_trade, utc=True).max().tz_convert("America/New_York")
    ch["spot"] = float(yf.Ticker("^GSPC").history(period="5d").Close.iloc[-1])
    ch["day"] = last.date().isoformat()
    p = CHAINS / f"spx_{ch.day.iloc[0]}_yahoo.csv"
    ch.to_csv(p, index=False)
    return p


def load_chain(path: Path):
    path = Path(path)
    if path.suffix == ".csv":
        ch = pd.read_csv(path, parse_dates=["exp"])
        return pd.Timestamp(ch.day.iloc[0]), float(ch.spot.iloc[0]), ch
    data = json.loads(path.read_text())["data"]
    rows = []
    for o in data["options"]:
        m = re.match(r"(SPXW?)(\d{6})([CP])(\d{8})", o["option"])
        if m and m[1] == "SPXW":
            rows.append(dict(exp=pd.Timestamp("20" + m[2]), cp=m[3], K=int(m[4]) / 1000,
                             bid=o["bid"], ask=o["ask"], volume=o["volume"], oi=o["open_interest"]))
    return pd.Timestamp(data["last_trade_time"][:10]), float(data["current_price"]), pd.DataFrame(rows)


def compare(chain_path, cfg: Config = Config(), dtes=(2, 3, 4, 5)):
    day, S, ch = load_chain(chain_path)
    daily, _ = load_market()
    daily = daily.loc[:day]
    if daily.index[-1] != day:
        raise SystemExit(f"no market data for {day.date()} yet")
    dates = daily.index.append(pd.bdate_range(day + pd.Timedelta(days=1), periods=15))
    clock = VarianceClock(dates.values, cfg.clock)
    _, sc, rho, eff10 = atm_vols(daily, cfg, VarianceClock(daily.index.values, cfg.clock))
    dl = len(daily) - 1
    sm = Smile(cfg.smile)
    wm = cfg.wing_mult * float(np.exp(cfg.wing_vol_beta * (sc[dl] - 0.12)))
    strip, wing, quotes = [], [], []
    for n in dtes:
        e = dates[dl + n]
        c = ch[(ch.exp == e) & (ch.cp == "C")].set_index("K")
        p = ch[(ch.exp == e) & (ch.cp == "P")].set_index("K")
        if c.empty:
            continue
        T = float(clock.T(dl, 1.0, dl + n))
        a = sc[dl] * cfg.atm_mult * (float(short_end_factor(T, rho[dl], eff10[dl])[0]) if cfg.short_end else 1.0)
        cm, pm = (c.bid + c.ask) / 2, (p.bid + p.ask) / 2
        Ks = c.index.intersection(p.index)
        near = Ks[np.argsort(np.abs(Ks - S))[:6]]
        F = float(np.median(near + (cm - pm).loc[near]))
        ivf = lambda px, K: brentq(lambda v: bs_call(F, K, v, T)[0] - px, 1e-4, 5)
        K0 = near[0]
        atm_mkt = 0.5 * (ivf(cm[K0], K0) + ivf(pm[K0] + F - K0, K0))
        tg = np.asarray(cfg.deltas, float)
        K = np.maximum(np.round(sm.strike_for_delta(tg, F, a, T, wm) / cfg.strike_step) * cfg.strike_step,
                       np.ceil(F / cfg.strike_step) * cfg.strike_step)
        mid = bs_call(F, K, sm.vol(K, F, a, T, wm), T)[0]
        bid = mid - np.maximum(cfg.tc_opt_min, cfg.tc_opt_pct * mid)
        for t, k, b in zip(tg, K, bid):
            if k in c.index and b >= cfg.min_bid:
                strip.append(dict(dte=n, delta=t, K=k, model_atm=a, market_atm=atm_mkt,
                                  model_bid=b, market_bid=c.loc[k].bid, market_ask=c.loc[k].ask))
        otm = []
        for k in c.index[c.index > F]:
            if c.loc[k].bid < 0.05:
                continue
            v = ivf(cm[k], k)
            dlt = ndtr((np.log(F / k) + 0.5 * v * v * T) / (v * np.sqrt(T)))
            if 0.005 <= dlt <= 0.5:
                wing.append(dict(z=np.log(k / F) / (atm_mkt * np.sqrt(T)), ratio=v / atm_mkt, delta=dlt))
                otm.append((k, v, dlt))
        # actual quotes at the strikes nearest each target delta (market delta)
        if otm:
            ks, vs, ds = map(np.array, zip(*otm))
            for t in cfg.deltas:
                i = int(np.argmin(np.abs(ds - t)))
                k = ks[i]
                r = c.loc[k]
                mod_mid = float(bs_call(F, k, sm.vol(k, F, a, T, wm), T)[0])
                quotes.append(dict(expiry=e.date(), dte=n, target=t, strike=k, otm_pct=100 * (k / F - 1),
                                   bid=r.bid, ask=r.ask, mid=(r.bid + r.ask) / 2, spread=r.ask - r.bid,
                                   iv=vs[i], delta=ds[i], volume=r.get("volume", np.nan), oi=r.get("oi", np.nan),
                                   bc_iv=r.get("bc_iv", np.nan), bc_delta=r.get("bc_delta", np.nan),
                                   model_mid=mod_mid,
                                   model_bid=mod_mid - max(cfg.tc_opt_min, cfg.tc_opt_pct * mod_mid)))
    strip, wing = pd.DataFrame(strip), pd.DataFrame(wing)
    compare.quotes = pd.DataFrame(quotes).drop_duplicates(["expiry", "strike"])
    a_, b_ = np.linalg.lstsq(np.c_[wing.z, wing.z ** 2], wing.ratio - 1, rcond=None)[0]
    f = lambda z: 1 + a_ * z + b_ * z * z
    fit = {"call10/ATM": f(ndtri(0.9)), "call1/ATM": f(ndtri(0.99))}
    return day, strip, fit


def bid_ratio(strip: pd.DataFrame) -> float:
    return strip.market_bid.sum() / strip.model_bid.sum()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--source", choices=["cboe", "yahoo", "barchart"], default="cboe")
    args = ap.parse_args()
    path = Path(args.file) if args.file else fetch(args.source)
    cfg = Config()
    day, strip, fit = compare(path, cfg)
    pd.set_option("display.width", 200)
    print(f"SPXW chain {day.date()}  ({path.name})")
    print("ATM vol (business time):")
    print(strip.groupby("dte")[["model_atm", "market_atm"]].first().round(4))
    print("market bid / model bid by delta x DTE:")
    print((strip.assign(r=strip.market_bid / strip.model_bid)
           .pivot_table(index="delta", columns="dte", values="r")).round(2))
    print(f"premium-weighted market/model bid: {bid_ratio(strip):.3f}")
    print("market call wing fit: " + ", ".join(f"{k} = {v:.3f}" for k, v in fit.items()))
    q = compare.quotes
    print(f"\nSPXW call quotes nearest each target delta (spot {load_chain(path)[1]:.2f}):")
    q = q.dropna(axis=1, how="all")
    print(q.round({"otm_pct": 2, "mid": 3, "spread": 2, "iv": 4, "delta": 3, "model_mid": 2, "model_bid": 2,
                   "bc_iv": 4, "bc_delta": 3}).to_string(index=False))
    if args.calibrate:
        m = brentq(lambda m: bid_ratio(compare(path, replace(cfg, atm_mult=m))[1]) - 1.0, 0.6, 1.4, xtol=1e-3)
        print(f"ATM multiplier matching market bids: {m:.3f}")


if __name__ == "__main__":
    main()
