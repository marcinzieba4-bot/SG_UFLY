"""VolVue end-of-day implied vol (https://volvue.com, API key in $VOLVUE_API_KEY).

VolVue publishes constant-maturity ATM implied vols (call / put / mean of the
ATM options with expiries closest to the target, Black-Scholes, 10/20/30...
calendar days) plus an IV-skew measure; there is no per-strike / per-delta
wing data.

Ticker matters: "SPX" is the monthly (AM-settled) root, so its "10-day" vol
comes from the nearest *monthly* expiry (often 2-4 weeks away).  "SPXW" (the
weeklies/dailies, from 2014-04) gives a true ~10-day ATM vol and matches the
CBOE chain (2026-09-22: SPXW 10.35 vs chain 10.31; SPX 11.25 = Oct-16 monthly).

The raw vendor data is cached to data/ (git-ignored) and not redistributed.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from io import StringIO

import pandas as pd

from .data import DATA_DIR

API = "https://api.volvue.com/query"
FIELDS = ["ticker", "date", "iv_mean_10", "iv_call_10", "iv_put_10", "iv_skew_10",
          "iv_mean_20", "iv_mean_30", "hv_cc_10"]


def query(tickers, start, end, fields=FIELDS) -> pd.DataFrame:
    key = os.environ["VOLVUE_API_KEY"]
    data = {"startDate": start, "endDate": end, "lastDateOnly": False, "tickers": list(tickers),
            "fields": list(fields), "conditions": [], "order": [{"field": "date", "direction": "asc"}],
            "limit": None}
    url = API + "?" + urllib.parse.urlencode({"apiKey": key, "format": "csv", "data": json.dumps(data)})
    with urllib.request.urlopen(url, timeout=120) as r:
        return pd.read_csv(StringIO(r.read().decode()), parse_dates=["date"])


def download(ticker: str = "SPX", start: str = "2010-01-01", end: str = "2026-12-31") -> pd.DataFrame:
    frames = []
    for y in range(int(start[:4]), int(end[:4]) + 1):      # year chunks keep responses small
        frames.append(query([ticker], f"{y}-01-01", f"{y}-12-31"))
    df = pd.concat([f for f in frames if len(f)]).drop_duplicates("date").set_index("date").sort_index()
    df.to_csv(DATA_DIR / f"volvue_{ticker.lower()}.csv")
    return df


def load(ticker: str = "SPX") -> pd.DataFrame | None:
    p = DATA_DIR / f"volvue_{ticker.lower()}.csv"
    if not p.exists():
        return None
    return pd.read_csv(p, index_col=0, parse_dates=True)


if __name__ == "__main__":
    for t in ["SPX", "SPXW", "SPY"]:
        df = download(t)
        print(t, df.shape, df.index.min().date(), df.index.max().date())
        print(df.notna().mean().round(3).to_dict())
