"""Market data download + cache (Yahoo Finance via yfinance).

Daily:  ^GSPC OHLC, ^VIX9D OHLC, ^VIX close (2011+), ^VIX1D close (2023-04+)
Hourly: ^GSPC 1h bars (Yahoo only serves the last ~730 days)

Files are cached to ./data so the backtest is reproducible offline.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
START = "2010-06-01"


def _flatten(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def download(refresh: bool = False) -> None:
    import yfinance as yf

    DATA_DIR.mkdir(exist_ok=True)
    daily = DATA_DIR / "daily.csv"
    if refresh or not daily.exists():
        spx = _flatten(yf.download("^GSPC", start=START, interval="1d", auto_adjust=False, progress=False))
        v9 = _flatten(yf.download("^VIX9D", start=START, interval="1d", auto_adjust=False, progress=False))
        vix = _flatten(yf.download("^VIX", start=START, interval="1d", auto_adjust=False, progress=False))
        v1 = _flatten(yf.download("^VIX1D", start=START, interval="1d", auto_adjust=False, progress=False))
        out = pd.DataFrame({
            "spx_open": spx["Open"], "spx_high": spx["High"], "spx_low": spx["Low"], "spx_close": spx["Close"],
            "vix9d_open": v9["Open"], "vix9d_close": v9["Close"], "vix_close": vix["Close"],
            "vix1d_close": v1["Close"],
        })
        out.index = pd.to_datetime(out.index).tz_localize(None).normalize()
        out.index.name = "date"
        out.round(4).to_csv(daily)

    hourly = DATA_DIR / "spx_hourly.csv"
    if refresh or not hourly.exists():
        h = _flatten(yf.download("^GSPC", period="730d", interval="1h", auto_adjust=False, progress=False))
        h.index = pd.to_datetime(h.index).tz_convert("America/New_York").tz_localize(None)
        h.index.name = "datetime"
        h[["Open", "High", "Low", "Close"]].round(4).to_csv(hourly)


def load_daily() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "daily.csv", index_col=0, parse_dates=True)
    return df.dropna(subset=["spx_open", "spx_close"])


def load_hourly() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "spx_hourly.csv", index_col=0, parse_dates=True)


if __name__ == "__main__":
    download(refresh=True)
    d = load_daily()
    h = load_hourly()
    print(d.tail(), d.shape, d.isna().sum(), sep="\n")
    print(h.head(10), h.shape, sep="\n")


def load_market(start: str = "2011-01-03") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cleaned daily frame (with days missing from the Yahoo daily feed rebuilt
    from hourly bars, and an in-progress last session dropped) + hourly bars."""
    d = load_daily()
    h = load_hourly()
    last_day = h.index.max().normalize()
    now_ny = pd.Timestamp.now(tz="America/New_York").tz_localize(None)
    if now_ny < last_day + pd.Timedelta(hours=16, minutes=15):   # session still in progress
        h = h[h.index.normalize() < last_day]
        d = d[d.index < last_day]
    for day, g in h.groupby(h.index.normalize()):
        if day not in d.index:
            d.loc[day] = {"spx_open": g.Open.iloc[0], "spx_high": g.High.max(), "spx_low": g.Low.min(),
                          "spx_close": g.Close.iloc[-1]}
    d = d.sort_index()
    d[["vix9d_open", "vix9d_close", "vix_close"]] = d[["vix9d_open", "vix9d_close", "vix_close"]].ffill()
    d = d[d.index >= start]
    if "vix1d_close" in d:              # VIX1D only exists from 2023-04; ffill single missing days there
        first = d.vix1d_close.first_valid_index()
        if first is not None:
            d.loc[first:, "vix1d_close"] = d.loc[first:, "vix1d_close"].ffill()
    else:
        d["vix1d_close"] = np.nan
    from .volvue import load as load_volvue
    for col, tkr in (("atm10", "SPX"), ("atm10w", "SPXW")):
        vv = load_volvue(tkr)
        d[col] = vv["iv_mean_10"].reindex(d.index) if vv is not None else np.nan
    return d, h
