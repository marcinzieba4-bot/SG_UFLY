"""SPXW option chain snapshot from barchart.com (public delayed quotes).

There is no Barchart API key in this environment, so the chain is read the way
the barchart.com options page reads it: a headless Chromium session loads the
page (which sets the site's cookies) and then requests the page's own JSON
endpoint (`/proxies/core-api/v1/options/get`) for each expiry.  Low volume,
for personal research; the snapshot is stored under data/ (git-ignored).

Besides bid/ask/volume/OI, Barchart supplies its own implied vol and greeks.
Quotes are delayed; the SPX price is taken from Barchart at the same time so
the chain and the underlying are consistent.
"""
from __future__ import annotations

import asyncio
import json
import os

import pandas as pd

PAGE = "https://www.barchart.com/stocks/quotes/$SPX/options"
API = "/proxies/core-api/v1/options/get?symbol=%24SPX&raw=1&orderBy=strikePrice&orderDir=asc"
FIELDS = ("symbol,optionType,strikePrice,expirationDate,bidPrice,askPrice,midpoint,lastPrice,volume,"
          "openInterest,volatility,delta,gamma,theta,vega,tradeTime,expirationType")
QUOTE = "/proxies/core-api/v1/quotes/get?symbols=%24SPX&raw=1&fields=symbol,lastPrice,tradeTime"
CHROMIUM = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium")

_JS = """async (u) => { const r = await fetch(u, {headers: {accept: 'application/json'}, credentials: 'include'});
                       return [r.status, await r.text()]; }"""


async def _fetch(n_exp: int) -> tuple[pd.DataFrame, float, pd.Timestamp]:
    from playwright.async_api import async_playwright

    proxy = os.environ.get("HTTPS_PROXY")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, executable_path=CHROMIUM,
                                          proxy={"server": proxy} if proxy else None,
                                          args=["--ignore-certificate-errors"])
        ctx = await browser.new_context(ignore_https_errors=True, user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"))
        page = await ctx.new_page()
        await page.goto(PAGE, wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(6000)

        async def get(url):
            status, txt = await page.evaluate(_JS, url)
            if status != 200:
                raise RuntimeError(f"barchart {status}: {txt[:200]}")
            return json.loads(txt)

        seed = (pd.Timestamp.now(tz="America/New_York").normalize() + pd.offsets.BDay(1)).date()
        first = await get(API + "&fields=" + FIELDS + f"&expirationDate={seed}&expirationType=weekly&meta=expirations")
        exps = sorted(set(first["meta"]["expirations"].get("weekly", [])))[:n_exp]
        rows = []
        for e in exps:
            j = await get(API + "&fields=" + FIELDS + f"&expirationDate={e}&expirationType=weekly")
            recs = j["data"] if isinstance(j["data"], list) else [x for v in j["data"].values() for x in v]
            rows += [r["raw"] for r in recs]
        q = (await get(QUOTE))["data"][0]["raw"]
        await browser.close()
    df = pd.DataFrame(rows)
    ts = pd.to_datetime(q["tradeTime"], unit="s", utc=True).tz_convert("America/New_York")
    return df, float(q["lastPrice"]), ts


def fetch_chain(n_exp: int = 8) -> tuple[pd.DataFrame, float, pd.Timestamp]:
    """Normalised chain (exp, cp, K, bid, ask, volume, oi, bc_iv, bc_delta), SPX price, quote time."""
    raw, spot, ts = asyncio.run(_fetch(n_exp))
    ch = pd.DataFrame({
        "exp": pd.to_datetime(raw.expirationDate), "cp": raw.optionType.str[0], "K": raw.strikePrice.astype(float),
        "bid": raw.bidPrice, "ask": raw.askPrice, "volume": raw.volume, "oi": raw.openInterest,
        "bc_iv": raw.volatility, "bc_delta": raw.delta,
        "trade_time": pd.to_datetime(raw.tradeTime, unit="s", utc=True, errors="coerce"),
    })
    ch = ch[ch.bid.notna() & ch.ask.notna()]
    return ch, spot, ts


HIST = "/proxies/timeseries/historical/queryeod.ashx?symbol={}&data=daily&maxrecords=640&volume=contract&order=asc"


def option_symbol(expiry: pd.Timestamp, strike: float, cp: str = "C") -> str:
    """Barchart symbol of an SPXW (PM-settled) option, e.g. $SPX|20250618|6100.00WC."""
    return f"$SPX|{expiry:%Y%m%d}|{strike:.2f}W{cp}"


async def _history(symbols: list[str], delay_ms: int) -> dict[str, str]:
    from playwright.async_api import async_playwright
    import urllib.parse

    proxy = os.environ.get("HTTPS_PROXY")
    out = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, executable_path=CHROMIUM,
                                          proxy={"server": proxy} if proxy else None,
                                          args=["--ignore-certificate-errors"])
        ctx = await browser.new_context(ignore_https_errors=True, user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"))
        page = await ctx.new_page()
        await page.goto(PAGE, wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(5000)
        for s in symbols:
            status, txt = await page.evaluate(_JS, HIST.format(urllib.parse.quote(s, safe="")))
            out[s] = txt if status == 200 else ""
            await page.wait_for_timeout(delay_ms)
        await browser.close()
    return out


def fetch_history(symbols: list[str], cache_dir, delay_ms: int = 700) -> dict[str, pd.DataFrame]:
    """Daily OHLC / volume / OI of (possibly expired) option contracts; cached per symbol.
    Barchart keeps SPXW weekly history from about late May 2023."""
    from pathlib import Path

    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    fname = lambda s: cache / (s.replace("$", "").replace("|", "_") + ".csv")
    todo = [s for s in dict.fromkeys(symbols) if not fname(s).exists()]
    if todo:
        for s, txt in asyncio.run(_history(todo, delay_ms)).items():
            fname(s).write_text(txt)
    res = {}
    for s in dict.fromkeys(symbols):
        txt = fname(s).read_text().strip()
        rows = [l.split(",") for l in txt.split("\n") if l.count(",") >= 6]
        df = pd.DataFrame([r[1:8] for r in rows], columns=["date", "open", "high", "low", "close", "volume", "oi"])
        if len(df):
            df["date"] = pd.to_datetime(df.date)
            df[df.columns[1:]] = df[df.columns[1:]].apply(pd.to_numeric, errors="coerce")
        res[s] = df
    return res
