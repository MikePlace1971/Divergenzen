# /utils/daten/data_loader.py
import datetime
from typing import Optional

import oandapyV20
import oandapyV20.endpoints.instruments as instruments
import pandas as pd
import yfinance as yf

# Supported timeframes (H4 and D1 only)
TIMEFRAME_MAP = {
    "H4": {"yfinance": "4h", "oanda": "H4", "hours": 4},
    "D1": {"yfinance": "1d", "oanda": "D", "hours": 24},
}

# Fixed history window for chart display per timeframe (in days)
LOOKBACK_DAYS = {
    "H4": 150,
    "D1": 335,
}

# Hard limits imposed by yfinance per interval (in days)
YF_MAX_LOOKBACK_DAYS = {
    "4h": 730,
    "1d": 3650,
}


def fetch_yfinance_data(symbol: str, interval: str, days: int) -> pd.DataFrame:
    """Download price data from Yahoo Finance for the selected interval."""

    if interval not in ("4h", "1d"):
        print(f"[Warnung] Unsupported interval fuer Yahoo Finance: {interval}")
        return pd.DataFrame()

    max_days = YF_MAX_LOOKBACK_DAYS.get(interval)
    if max_days is not None:
        days = min(days, max_days)

    start_date = datetime.datetime.utcnow() - datetime.timedelta(days=days)

    try:
        df = yf.download(
            symbol,
            interval=interval,
            start=start_date.strftime("%Y-%m-%d"),
            auto_adjust=True,
            progress=False,
            group_by="ticker",
        )
    except Exception as exc:
        print(f"[Fehler] Fehler bei yfinance ({symbol}): {exc}")
        return pd.DataFrame()

    if df.empty:
        print(f"[Warnung] Keine Yahoo-Daten fuer {symbol}.")
        return pd.DataFrame()

    if isinstance(df.columns, pd.MultiIndex):
        df = df.droplevel(0, axis=1)

    df = df.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "close",
            "Volume": "volume",
        }
    )

    df = df[["open", "high", "low", "close", "volume"]]
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(None)
    df.index.name = "time"

    return df.sort_index()


def fetch_oanda_data(
    symbol: str,
    timeframe: str,
    days: int,
    min_bars: int,
    access_token: Optional[str],
) -> pd.DataFrame:
    """Download price data from the OANDA API for the selected timeframe."""

    if not access_token:
        print("[Warnung] Kein OANDA-Access-Token angegeben.")
        return pd.DataFrame()

    info = TIMEFRAME_MAP.get(timeframe.upper(), {})
    granularity = info.get("oanda")
    hours = info.get("hours")
    if not granularity or not hours:
        print(f"[Warnung] Ungueltiger OANDA-Timeframe: {timeframe}")
        return pd.DataFrame()

    bars_per_day = max(int(24 / hours), 1)
    bars = max(int(days * bars_per_day), min_bars)

    client = oandapyV20.API(access_token=access_token)
    params = {"granularity": granularity, "count": bars + 10, "price": "M"}

    try:
        request = instruments.InstrumentsCandles(instrument=symbol, params=params)
        candles = client.request(request).get("candles", [])
    except Exception as exc:
        print(f"[Fehler] Fehler bei OANDA ({symbol}): {exc}")
        return pd.DataFrame()

    rows = []
    for candle in candles:
        if not candle.get("complete"):
            continue
        rows.append(
            {
                "time": pd.to_datetime(candle["time"], utc=True).tz_convert(None),
                "open": float(candle["mid"]["o"]),
                "high": float(candle["mid"]["h"]),
                "low": float(candle["mid"]["l"]),
                "close": float(candle["mid"]["c"]),
                "volume": int(candle["volume"]),
            }
        )

    if not rows:
        print(f"[Warnung] Keine OANDA-Daten fuer {symbol}.")
        return pd.DataFrame()

    df = pd.DataFrame(rows).set_index("time").sort_index()
    return df.tail(bars)


def load_data(
    symbol: str,
    source: str,
    timeframe: str,
    lookback: int = 200,
    oanda_token: Optional[str] = None,
) -> pd.DataFrame:
    """Load price data from the selected source (H4/D1 only)."""

    timeframe = timeframe.upper()
    if timeframe not in TIMEFRAME_MAP:
        print(f"[Warnung] Ungueltiger Timeframe: {timeframe} (nur H4 und D1 erlaubt).")
        return pd.DataFrame()

    days_to_fetch = LOOKBACK_DAYS.get(timeframe)
    if days_to_fetch is None:
        days_to_fetch = 180

    if source == "yfinance":
        interval = TIMEFRAME_MAP[timeframe]["yfinance"]
        df = fetch_yfinance_data(symbol, interval, days_to_fetch)
    elif source == "oanda":
        df = fetch_oanda_data(symbol, timeframe, days_to_fetch, lookback, oanda_token)
    else:
        print(f"[Warnung] Unbekannte Datenquelle: {source}")
        return pd.DataFrame()

    return df.sort_index() if not df.empty else df
