# utils/daten/data_loader.py
import pandas as pd
import yfinance as yf
import oandapyV20
import oandapyV20.endpoints.instruments as instruments

TIMEFRAME_MAP = {
    "D1": {"yfinance": "1d", "oanda": "D"},
    "H4": {"yfinance": "4h", "oanda": "H4"},
    "H1": {"yfinance": "1h", "oanda": "H1"},
    "M15": {"yfinance": "15m", "oanda": "M15"},
}


def fetch_yfinance_data(symbol, interval, lookback):
    try:
        df = yf.download(
            symbol,
            period=f"{lookback}d",
            interval=interval,
            group_by="ticker",
            auto_adjust=False,
            progress=False
        )

        # MultiIndex-Spalten auflösen
        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(0, axis=1)

        # Spalten vereinheitlichen
        df = df.rename(columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume"
        })
        df = df[["open", "high", "low", "close", "volume"]]

        # Index vereinheitlichen
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(None)
        df.index.name = "time"

        return df.tail(lookback)

    except Exception as e:
        print(f"❌ Fehler bei yfinance {symbol}: {e}")
        return pd.DataFrame()


def fetch_oanda_data(symbol, granularity, lookback, access_token):
    client = oandapyV20.API(access_token=access_token)
    params = {
        "granularity": granularity,
        "count": lookback + 10,
        "price": "M"  # Mid-Prices
    }
    r = instruments.InstrumentsCandles(instrument=symbol, params=params)

    try:
        candles = client.request(r)["candles"]
        rows = []
        for c in candles:
            if not c["complete"]:
                continue
            rows.append({
                "time": pd.to_datetime(c["time"], utc=True).tz_convert(None),
                "open": float(c["mid"]["o"]),
                "high": float(c["mid"]["h"]),
                "low": float(c["mid"]["l"]),
                "close": float(c["mid"]["c"]),
                "volume": int(c["volume"])
            })
        df = pd.DataFrame(rows).set_index("time")
        return df.tail(lookback)

    except Exception as e:
        print(f"❌ Fehler bei OANDA {symbol}: {e}")
        return pd.DataFrame()


def load_data(symbol, source, timeframe, lookback=200, oanda_token=None):
    tf = TIMEFRAME_MAP[timeframe][source]

    if source == "yfinance":
        return fetch_yfinance_data(symbol, tf, lookback)

    elif source == "oanda":
        if not oanda_token:
            print("❌ OANDA Token fehlt")
            return pd.DataFrame()
        return fetch_oanda_data(symbol, tf, lookback, oanda_token)

    else:
        print(f"❌ Unbekannte Quelle: {source}")
        return pd.DataFrame()
