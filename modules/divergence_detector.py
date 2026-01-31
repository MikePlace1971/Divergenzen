# /modules/divergence_detector.py
import pandas as pd
from .rsi_wilder import compute_rsi_wilder


class DivergenceDetector:
    def __init__(self, rsi_period=14, fractal_periods=4, max_bars_diff=30):
        """
        Initialisiert den Divergenz-Detektor mit den gewünschten Parametern.
        Diese Werte entsprechen den Einstellungen im TradingView-Skript.
        """
        self.rsi_period = rsi_period
        self.fractal_periods = fractal_periods
        self.max_bars_diff = max_bars_diff

    def find_divergences(self, df: pd.DataFrame):
        """
        Findet Bullish- und Bearish-Divergenzen zwischen RSI und Kursdaten.
        Rückgabe:
        {
            "df": pd.DataFrame(... mit RSI-Spalte),
            "bullish": [(idx1, idx2), ...],
            "bearish": [(idx1, idx2), ...]
        }
        """
        if df is None or df.empty:
            return {"df": df, "bullish": [], "bearish": []}

        data = df.copy()
        data["rsi"] = compute_rsi_wilder(data["close"], self.rsi_period)
        data["rsi_hist"] = data["rsi"] - 50
        data["ema_50"] = data["close"].ewm(span=50, adjust=False).mean()

        n = self.fractal_periods
        if n <= 0:
            return {"df": data, "bullish": [], "bearish": []}

        data["up_fractal"] = False
        data["down_fractal"] = False

        bullish, bearish = [], []
        up_pivots, down_pivots = [], []

        for detect_idx in range(2 * n, len(data)):
            pivot_idx = detect_idx - n
            left_idx = pivot_idx - n
            if left_idx < 0:
                continue

            window = data.iloc[left_idx:detect_idx + 1]

            # Skip if insufficient data or NaNs are present in the window
            if window[["high", "low", "close", "ema_50", "rsi_hist"]].isna().any().any():
                continue

            pivot_high = data["high"].iloc[pivot_idx]
            left_high = window["high"].iloc[:n].max()
            right_high = window["high"].iloc[n + 1:].max()

            if (
                pivot_high > left_high
                and pivot_high > right_high
                and data["close"].iloc[pivot_idx] > data["ema_50"].iloc[pivot_idx]
            ):
                data.iloc[pivot_idx, data.columns.get_loc("up_fractal")] = True
                prev_idx = up_pivots[-1] if up_pivots else None
                up_pivots.append(pivot_idx)

                if (
                    prev_idx is not None
                    and (pivot_idx - prev_idx) <= self.max_bars_diff
                ):
                    curr_hist = data["rsi_hist"].iloc[pivot_idx]
                    prev_hist = data["rsi_hist"].iloc[prev_idx]
                    if (
                        curr_hist > 0
                        and prev_hist > 0
                        and curr_hist < prev_hist
                        and data["high"].iloc[pivot_idx] > data["high"].iloc[prev_idx]
                    ):
                        bearish.append(
                            (data.index[prev_idx], data.index[detect_idx]))

            pivot_low = data["low"].iloc[pivot_idx]
            left_low = window["low"].iloc[:n].min()
            right_low = window["low"].iloc[n + 1:].min()

            if (
                pivot_low < left_low
                and pivot_low < right_low
                and data["close"].iloc[pivot_idx] < data["ema_50"].iloc[pivot_idx]
            ):
                data.iloc[pivot_idx, data.columns.get_loc(
                    "down_fractal")] = True
                prev_idx = down_pivots[-1] if down_pivots else None
                down_pivots.append(pivot_idx)

                if (
                    prev_idx is not None
                    and (pivot_idx - prev_idx) <= self.max_bars_diff
                ):
                    curr_hist = data["rsi_hist"].iloc[pivot_idx]
                    prev_hist = data["rsi_hist"].iloc[prev_idx]
                    if (
                        curr_hist < 0
                        and prev_hist < 0
                        and curr_hist > prev_hist
                        and data["low"].iloc[pivot_idx] < data["low"].iloc[prev_idx]
                    ):
                        bullish.append(
                            (data.index[prev_idx], data.index[detect_idx]))

        return {"df": data, "bullish": bullish, "bearish": bearish}
