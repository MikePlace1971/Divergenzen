# /modules/rsi_wilder.py
import pandas as pd


def compute_rsi_wilder(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Berechnet den RSI nach Welles Wilder (exponentiell geglättet).
    Diese Variante entspricht der Berechnung, die auch TradingView verwendet.
    """
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(
        alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return rsi
