# /utils/chart/donchian_plotter.py

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter, MaxNLocator


def _prepare_data(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()

    if not isinstance(data.index, pd.DatetimeIndex):
        data.index = pd.to_datetime(data.index, errors="coerce")

    if getattr(data.index, "tz", None) is not None:
        data.index = data.index.tz_convert(None)

    data = data[~data.index.isna()]
    data = data.sort_index()
    return data


def _validate_data(data: pd.DataFrame) -> None:
    required = {"open", "high", "low", "close"}

    if data is None or data.empty:
        raise ValueError("Keine Daten vorhanden.")

    if not required.issubset(data.columns):
        missing = sorted(required.difference(data.columns))
        raise ValueError(f"Fehlende OHLC-Spalten: {missing}")

    if not isinstance(data.index, pd.DatetimeIndex):
        raise ValueError("Index ist kein DatetimeIndex.")

    if data.index.has_duplicates:
        raise ValueError("Zeitindex enthält Duplikate.")

    if not data.index.is_monotonic_increasing:
        raise ValueError("Zeitindex ist nicht aufsteigend sortiert.")


def _make_time_formatter(index: pd.DatetimeIndex) -> FuncFormatter:
    def _formatter(value, _pos):
        i = int(round(value))
        if i < 0 or i >= len(index):
            return ""

        ts = index[i]

        inferred = pd.infer_freq(index)
        if inferred and "D" in inferred.upper():
            return ts.strftime("%d.%m.%Y")

        return ts.strftime("%d.%m\n%H:%M")

    return FuncFormatter(_formatter)


def plot_donchian_chart(
    df: pd.DataFrame,
    title: str = "",
    symbol: str | None = None,
    index: str | None = None,
    timeframe: str | None = None,
) -> None:
    data = _prepare_data(df)

    try:
        _validate_data(data)
    except ValueError as exc:
        print(f"[Fehler] {exc}")
        return

    bars_before = len(data)

    # Kompakte X-Achse ohne Zeitlücken
    x = np.arange(len(data), dtype=float)

    if len(x) != bars_before:
        print("[Fehler] Inkonsistente Bar-Anzahl im Plotter.")
        return

    # === ENTRY SIGNAL ERKENNEN ===
    entry_index = None
    entry_color = None

    if {"SMA200", "don_high", "don_low"}.issubset(data.columns):
        last = data.iloc[-1]

        # SHORT Setup
        if last["close"] < last["SMA200"] and last["high"] >= last["don_high"]:
            entry_index = len(data) - 1
            entry_color = "#FF0000"

        # LONG Setup
        elif last["close"] > last["SMA200"] and last["low"] <= last["don_low"]:
            entry_index = len(data) - 1
            entry_color = "#00B050"

    # === Plot vorbereiten ===
    fig, ax = plt.subplots(figsize=(14, 7))
    fig.suptitle(title, fontsize=12, fontweight="bold")

    candle_width = 0.7

    # === Kerzen zeichnen ===
    for i, (_, row) in enumerate(data.iterrows()):
        xi = x[i]
        o = float(row["open"])
        c = float(row["close"])
        h = float(row["high"])
        l = float(row["low"])

        color = "#00B050" if c >= o else "#FF0000"

        ax.vlines(xi, l, h, color=color, linewidth=1)

        body_height = max(abs(c - o), 1e-6)
        rect = Rectangle(
            (xi - candle_width / 2, min(o, c)),
            candle_width,
            body_height,
            facecolor=color,
            edgecolor="black",
            linewidth=0.5,
            zorder=3,
        )
        ax.add_patch(rect)

    # === SMA200 ===
    if "SMA200" in data.columns:
        ax.plot(
            x,
            data["SMA200"].to_numpy(),
            color="#1f77b4",
            linewidth=1.4,
            label="SMA200",
        )

    # === Donchian Kanal ===
    if "don_high" in data.columns and "don_low" in data.columns:
        ax.plot(
            x,
            data["don_high"].to_numpy(),
            color="#FFA500",
            linestyle="--",
            linewidth=1.4,
            label="Donchian High",
        )
        ax.plot(
            x,
            data["don_low"].to_numpy(),
            color="#FFA500",
            linestyle="--",
            linewidth=1.4,
            label="Donchian Low",
        )

    # === Entry Marker ===
    if entry_index is not None and entry_color is not None:
        row = data.iloc[entry_index]
        y_range = max(float(data["high"].max()) -
                      float(data["low"].min()), 1e-6)

        if entry_color == "#00B050":
            marker_y = float(row["low"]) - y_range * 0.015
            marker = "^"
        else:
            marker_y = float(row["high"]) + y_range * 0.015
            marker = "v"

        ax.scatter(
            [float(entry_index)],
            [marker_y],
            color=entry_color,
            marker=marker,
            s=110,
            zorder=6,
        )

    # === Stil & Achsen ===
    ax.set_ylabel("Preis")
    ax.grid(True, linestyle=":", alpha=0.35)

    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(fontsize=9)

    # Rechts etwas Platz
    ax.set_xlim(-1, len(data) + 6)

    # Echte Zeitlabels auf kompakter Achse
    ax.xaxis.set_major_locator(MaxNLocator(nbins=10, integer=True))
    ax.xaxis.set_major_formatter(_make_time_formatter(data.index))

    plt.tight_layout()
    plt.show()
