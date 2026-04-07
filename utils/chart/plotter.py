# /utils/chart/plotter.py
from __future__ import annotations

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter, MaxNLocator

from modules.rsi_wilder import compute_rsi_wilder

# Verhindert, dass Matplotlib neue/aktualisierte Fenster nach vorne holt
try:
    mpl.rcParams["figure.raise_window"] = False
except Exception:
    pass


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
    required_columns = {"open", "high", "low", "close"}

    if data is None or data.empty:
        raise ValueError("Keine Daten zum Plotten vorhanden.")

    if not required_columns.issubset(data.columns):
        missing = sorted(required_columns.difference(data.columns))
        raise ValueError(f"Fehlende Spalten: {missing}")

    if not isinstance(data.index, pd.DatetimeIndex):
        raise ValueError("Index ist kein DatetimeIndex.")

    if data.index.has_duplicates:
        raise ValueError("Zeitindex enthält Duplikate.")

    if not data.index.is_monotonic_increasing:
        raise ValueError("Zeitindex ist nicht aufsteigend sortiert.")


def _normalize_sma_column_names(data: pd.DataFrame) -> pd.DataFrame:
    renamed = []
    for col in data.columns:
        if isinstance(col, str) and col.startswith("SMA "):
            renamed.append(col.replace(" ", ""))
        else:
            renamed.append(col)
    data.columns = renamed
    return data


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


def plot_candles(
    df: pd.DataFrame,
    title: str = "",
    name: str | None = None,
    symbol: str | None = None,
    index: str | None = None,
    timeframe: str | None = None,
    divergences: dict | None = None,
    rsi_lower: float = 30.0,
    rsi_upper: float = 70.0,
    rsi_period: int = 14,
):
    # -----------------------------------------------------------
    # Datenvorbereitung
    # -----------------------------------------------------------
    try:
        data = _prepare_data(df)
        _validate_data(data)
    except ValueError as exc:
        print(f"[Fehler] {exc}")
        return

    bars_before = len(data)

    if "rsi" not in data.columns:
        data["rsi"] = compute_rsi_wilder(data["close"], period=int(rsi_period))

    if "rsi_hist" not in data.columns:
        data["rsi_hist"] = data["rsi"] - 50

    data = _normalize_sma_column_names(data)

    # -----------------------------------------------------------
    # Titelaufbau
    # -----------------------------------------------------------
    parts = []
    if name:
        parts.append(name)
    if symbol:
        parts.append(f"({symbol})")
    if index or timeframe:
        tf_text = f"{index or ''} | Zeitrahmen: {timeframe or ''}".strip(" |")
        parts.append(f"[{tf_text}]")
    full_title = " ".join(parts) if parts else title or "Chart"

    # -----------------------------------------------------------
    # Kompakte X-Achse ohne Zeitlücken
    # -----------------------------------------------------------
    x = np.arange(len(data), dtype=float)
    pos_by_time = {ts: i for i, ts in enumerate(data.index)}

    if len(x) != bars_before:
        print("[Fehler] Beim Erstellen der Plot-Achse gingen Bars verloren.")
        return

    # -----------------------------------------------------------
    # Plot-Struktur
    # -----------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(
        2,
        1,
        figsize=(13, 7),
        sharex=True,
        gridspec_kw={"height_ratios": [3, 1]},
    )
    fig.suptitle(full_title, fontsize=12, fontweight="bold", y=0.98)

    # -----------------------------------------------------------
    # Candlestick-Darstellung
    # -----------------------------------------------------------
    candle_width = 0.65
    color_up = "#00B050"
    color_down = "#FF0000"

    for i, (_, row) in enumerate(data.iterrows()):
        xi = x[i]
        o = float(row["open"])
        c = float(row["close"])
        h = float(row["high"])
        l = float(row["low"])

        color = color_up if c >= o else color_down

        ax1.vlines(xi, l, h, color=color, linewidth=1, alpha=0.9)

        body_bottom = min(o, c)
        body_height = abs(c - o)

        if body_height < (h - l) * 0.002:
            body_height = max((h - l) * 0.002, 1e-6)

        rect = Rectangle(
            (xi - candle_width / 2, body_bottom),
            candle_width,
            body_height,
            facecolor=color,
            edgecolor="black",
            linewidth=0.5,
            alpha=0.95,
            zorder=3,
        )
        ax1.add_patch(rect)

    # -----------------------------------------------------------
    # Divergenzen: Preis UND RSI
    # -----------------------------------------------------------
    if divergences:
        y_range = float(data["high"].max()) - float(data["low"].min())
        y_range = max(y_range, 1e-6)
        offset_price = y_range * 0.01
        offset_rsi = 2.0

        for i1, i2 in divergences.get("bullish", []):
            if i1 in pos_by_time and i2 in pos_by_time:
                x1 = pos_by_time[i1]
                x2 = pos_by_time[i2]

                ax1.plot(
                    [x1, x2],
                    [
                        float(data.loc[i1, "low"]) - offset_price,
                        float(data.loc[i2, "low"]) - offset_price,
                    ],
                    color="green",
                    linewidth=2,
                    alpha=0.9,
                )

                ax2.plot(
                    [x1, x2],
                    [
                        float(data.loc[i1, "rsi"]) - offset_rsi,
                        float(data.loc[i2, "rsi"]) - offset_rsi,
                    ],
                    color="green",
                    linewidth=2,
                    alpha=0.9,
                )

        for i1, i2 in divergences.get("bearish", []):
            if i1 in pos_by_time and i2 in pos_by_time:
                x1 = pos_by_time[i1]
                x2 = pos_by_time[i2]

                ax1.plot(
                    [x1, x2],
                    [
                        float(data.loc[i1, "high"]) + offset_price,
                        float(data.loc[i2, "high"]) + offset_price,
                    ],
                    color="red",
                    linewidth=2,
                    alpha=0.9,
                )

                ax2.plot(
                    [x1, x2],
                    [
                        float(data.loc[i1, "rsi"]) + offset_rsi,
                        float(data.loc[i2, "rsi"]) + offset_rsi,
                    ],
                    color="red",
                    linewidth=2,
                    alpha=0.9,
                )

    # -----------------------------------------------------------
    # RSI-Darstellung
    # -----------------------------------------------------------
    ax2.plot(x, data["rsi"].to_numpy(), color="black", linewidth=1.1)
    ax2.axhline(rsi_upper, color="red", linewidth=1.0,
                linestyle="-", alpha=0.8)
    ax2.axhline(rsi_lower, color="green",
                linewidth=1.0, linestyle="-", alpha=0.8)
    ax2.set_ylim(0, 100)
    ax2.set_ylabel("RSI (Wilder)", fontsize=9)
    ax2.grid(True, linestyle=":", alpha=0.3)

    # -----------------------------------------------------------
    # SMA-Linien
    # -----------------------------------------------------------
    sma_cols = [c for c in data.columns if isinstance(
        c, str) and c.startswith("SMA")]
    if sma_cols:
        try:
            sma_sorted = sorted(
                sma_cols, key=lambda col: int(col.replace("SMA", "")), reverse=True
            )
        except Exception:
            sma_sorted = sma_cols

        colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]

        for i, col in enumerate(sma_sorted):
            color = colors[i % len(colors)]
            ax1.plot(
                x,
                data[col].to_numpy(),
                color=color,
                linewidth=1.2,
                linestyle="-",
                alpha=0.9,
                label=col,
            )

        ax1.legend(fontsize=8)

    # -----------------------------------------------------------
    # Formatierung
    # -----------------------------------------------------------
    ax1.grid(True, linestyle=":", alpha=0.3)
    ax1.set_ylabel("Kurs", fontsize=9)

    ax1.xaxis.set_major_locator(MaxNLocator(nbins=10, integer=True))
    ax1.xaxis.set_major_formatter(_make_time_formatter(data.index))

    ax2.xaxis.set_major_locator(MaxNLocator(nbins=10, integer=True))
    ax2.xaxis.set_major_formatter(_make_time_formatter(data.index))

    # rechts etwas Platz, ohne Zeitlücken zurückzubringen
    ax1.set_xlim(-0.5, len(data) - 0.5 + 2.0)
    ax2.set_xlim(ax1.get_xlim())

    plt.tight_layout()

    backend_name = plt.get_backend().lower()
    is_gui_backend = any(
        token in backend_name for token in ("qt", "gtk", "tk", "wx", "macosx")
    )

    if not is_gui_backend:
        plt.close(fig)
        return

    try:
        manager = plt.get_current_fig_manager()
        if manager is None:
            raise RuntimeError("Kein GUI-Backend verfügbar.")

        # Qt: Fenster nicht aktivieren und keinen Fokus anfordern
        if "qt" in backend_name:
            try:
                from matplotlib.backends.qt_compat import QtCore

                win = getattr(manager, "window", None)
                if win is not None:
                    try:
                        win.setAttribute(
                            QtCore.Qt.WA_ShowWithoutActivating, True)
                    except Exception:
                        pass
                    try:
                        win.setFocusPolicy(QtCore.Qt.NoFocus)
                    except Exception:
                        pass
            except Exception:
                pass

        plt.show(block=False)
        plt.pause(0.001)

        while plt.fignum_exists(fig.number):
            plt.pause(0.1)

    except Exception as exc:
        print(f"Fehler beim Anzeigen des Charts: {exc}")
    finally:
        if plt.fignum_exists(fig.number):
            plt.close(fig)
