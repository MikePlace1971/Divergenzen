"""
modules/liquidityGrabScanner/plotter.py

Zeichnet Liquidity-Grabs mit Candlesticks, relevanten Levels und Signalmarkierungen.

Der Plot ist bewusst auf Klarheit optimiert:
- das wichtigste Signal wird deutlich hervorgehoben
- das zugehörige Referenzlevel wird stark markiert
- der Sweep wird sichtbar gemacht
- andere Levels bleiben dezent im Hintergrund
"""

from __future__ import annotations

from typing import List

import matplotlib as mpl
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from .detector import LiquiditySignal
from .levels import LiquidityLevel

try:
    mpl.rcParams["figure.raise_window"] = False
except Exception:
    pass


def _signal_color(signal: LiquiditySignal) -> str:
    """
    Farbwahl je Signaltyp und Richtung.
    """
    if signal.signal_type == "run":
        return "#ff8c00"  # orange
    if signal.direction == "bullish":
        return "#008000"  # grün
    return "#cc0000"      # rot


def _level_color(level: LiquidityLevel) -> str:
    """
    buy_side = Liquidität über Hochs -> eher rot
    sell_side = Liquidität unter Tiefs -> eher grün
    """
    if level.side == "buy_side":
        return "#cc6666"
    return "#66aa66"


def plot_liquidity_grab_chart(
    df: pd.DataFrame,
    signals: List[LiquiditySignal],
    levels: List[LiquidityLevel],
    title: str = "",
):
    """
    Zeichnet einen Candlestick-Chart mit:
    - Candles
    - dezenten Hintergrund-Levels
    - klar hervorgehobenen Signal-Leveln
    - Sweep-Markierung
    - Info-Label am Signal
    """
    if df is None or df.empty:
        print("[Fehler] Keine Daten zum Plotten vorhanden.")
        return

    required = {"open", "high", "low", "close"}
    if not required.issubset(df.columns):
        print("[Fehler] OHLC-Spalten fehlen für den Chart.")
        return

    data = df.copy()

    if not isinstance(data.index, pd.DatetimeIndex):
        data.index = pd.to_datetime(data.index, errors="coerce")

    if getattr(data.index, "tz", None) is not None:
        data.index = data.index.tz_convert(None)

    data = data[~data.index.isna()]
    if data.empty:
        print("[Fehler] Zeitindex ungültig.")
        return

    # Nur beste Signale plotten, falls Liste sortiert ist:
    # erstes Signal = wichtigstes Signal
    sorted_signals = sorted(
        signals,
        key=lambda s: (s.score, s.signal_time),
        reverse=True,
    )

    fig, ax = plt.subplots(figsize=(15, 7.8))
    fig.suptitle(title, fontsize=12, fontweight="bold", y=0.98)

    # ---------------------------------------------------
    # Candles
    # ---------------------------------------------------
    x = mdates.date2num(data.index)

    if len(data) > 1:
        diffs = pd.Series(x).diff().dropna()
        candle_width = max(diffs.min() * 0.65, 0.02)
    else:
        candle_width = 0.3

    color_up = "#00B050"
    color_down = "#FF0000"

    for xi, (_, row) in zip(x, data.iterrows()):
        o = float(row["open"])
        h = float(row["high"])
        l = float(row["low"])
        c = float(row["close"])

        color = color_up if c >= o else color_down

        ax.vlines(xi, l, h, color=color, linewidth=1.0, alpha=0.95, zorder=2)

        body_bottom = min(o, c)
        body_height = max(abs(c - o), 1e-6)

        rect = plt.Rectangle(
            (xi - candle_width / 2, body_bottom),
            candle_width,
            body_height,
            facecolor=color,
            edgecolor="black",
            linewidth=0.5,
            alpha=0.95,
            zorder=3,
        )
        ax.add_patch(rect)

    # ---------------------------------------------------
    # Optionale SMA-Linien
    # ---------------------------------------------------
    sma_cols = [c for c in data.columns if isinstance(
        c, str) and c.startswith("SMA")]
    for col in sma_cols:
        ax.plot(
            data.index,
            data[col],
            linewidth=1.15,
            alpha=0.9,
            label=col,
            zorder=1,
        )

    # ---------------------------------------------------
    # Hintergrund-Levels (dezent)
    # ---------------------------------------------------
    highlighted_level_keys = set()
    for sig in sorted_signals:
        highlighted_level_keys.add((sig.level_side, round(sig.level_price, 8)))

    for lvl in levels:
        level_key = (lvl.side, round(float(lvl.price), 8))
        if level_key in highlighted_level_keys:
            continue

        ax.axhline(
            y=float(lvl.price),
            color=_level_color(lvl),
            linestyle="--" if lvl.is_equal_pool else ":",
            linewidth=0.9,
            alpha=0.22,
            zorder=0,
        )

    # ---------------------------------------------------
    # Signal-Level + Sweep + Marker + Info
    # ---------------------------------------------------
    y_min = float(data["low"].min())
    y_max = float(data["high"].max())
    y_range = max(y_max - y_min, 1e-6)
    text_offset = y_range * 0.018

    for idx, signal in enumerate(sorted_signals):
        if signal.signal_time not in data.index:
            continue

        row = data.loc[signal.signal_time]
        sig_color = _signal_color(signal)

        # Signal-Level stark hervorheben
        ax.axhline(
            y=signal.level_price,
            color=sig_color,
            linestyle="-",
            linewidth=1.8 if idx == 0 else 1.3,
            alpha=0.75 if idx == 0 else 0.50,
            zorder=1,
        )

        # Referenzzeitpunkt markieren, falls vorhanden
        if signal.reference_time in data.index:
            ax.scatter(
                [signal.reference_time],
                [signal.level_price],
                s=30,
                marker="o",
                facecolors="white",
                edgecolors=sig_color,
                linewidths=1.0,
                alpha=0.9,
                zorder=5,
            )

        # Sweep-Linie: vom Level zum Extrem der Signal-Candle
        if signal.direction == "bullish":
            sweep_extreme = float(row["low"])
            marker_y = sweep_extreme - y_range * 0.015
            marker = "^"
            text_va = "bottom"
            info_y = marker_y + text_offset
        else:
            sweep_extreme = float(row["high"])
            marker_y = sweep_extreme + y_range * 0.015
            marker = "v"
            text_va = "top"
            info_y = marker_y - text_offset

        ax.vlines(
            signal.signal_time,
            ymin=min(signal.level_price, sweep_extreme),
            ymax=max(signal.level_price, sweep_extreme),
            color=sig_color,
            linewidth=2.0 if idx == 0 else 1.4,
            alpha=0.8,
            zorder=4,
        )

        # Marker am Signal
        ax.scatter(
            [signal.signal_time],
            [marker_y],
            color=sig_color,
            marker=marker,
            s=95 if idx == 0 else 70,
            zorder=6,
        )

        # Kompaktes Signal-Label
        direction_text = "BULL" if signal.direction == "bullish" else "BEAR"
        signal_text = signal.signal_type.upper()

        flags = []
        if signal.reclaimed:
            flags.append("reclaim")
        if signal.confirmed:
            flags.append("confirm")
        if signal.equal_pool:
            flags.append("equal")
        if signal.level_touches > 1:
            flags.append(f"touches={signal.level_touches}")

        flags_text = " | ".join(flags) if flags else "raw"

        label = (
            f"{direction_text} {signal_text} | {signal.score:.0f}\n"
            f"Level: {signal.level_price:.4f}\n"
            f"Sweep: {signal.sweep_percent:.3f}%\n"
            f"{flags_text}"
        )

        ax.annotate(
            label,
            xy=(signal.signal_time, marker_y),
            xytext=(8, 0 if signal.direction == "bullish" else 0),
            textcoords="offset points",
            fontsize=8,
            color=sig_color,
            va=text_va,
            ha="left",
            bbox=dict(
                boxstyle="round,pad=0.25",
                facecolor="white",
                edgecolor=sig_color,
                alpha=0.85,
            ),
            zorder=7,
        )

    # ---------------------------------------------------
    # Chart-Layout
    # ---------------------------------------------------
    ax.set_ylabel("Preis")
    ax.grid(True, linestyle=":", alpha=0.28)

    locator = mdates.AutoDateLocator()
    formatter = mdates.ConciseDateFormatter(locator)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(formatter)

    # Legende nur wenn wirklich Labels vorhanden sind
    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(fontsize=8, loc="upper left")

    # Etwas rechter Rand
    if len(data.index) > 1:
        extra_right = (data.index[-1] - data.index[-2]) * 2
        ax.set_xlim(data.index[0], data.index[-1] + extra_right)

    fig.autofmt_xdate()
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

        plt.show(block=False)
        plt.pause(0.001)

        while plt.fignum_exists(fig.number):
            plt.pause(0.1)

    except Exception as exc:
        print(f"[Fehler] Chart konnte nicht angezeigt werden: {exc}")
    finally:
        if plt.fignum_exists(fig.number):
            plt.close(fig)
