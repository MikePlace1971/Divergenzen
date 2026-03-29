"""
modules/liquidityGrabScanner/plotter.py
"""

from __future__ import annotations

from pathlib import Path
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
    if signal.signal_type == "run":
        return "#ff8c00"
    if signal.direction == "bullish":
        return "#008000"
    return "#cc0000"


def _level_color(level: LiquidityLevel) -> str:
    return "#cc6666" if level.side == "buy_side" else "#66aa66"


def _select_nearest_background_levels(
    levels: List[LiquidityLevel],
    signals: List[LiquiditySignal],
    max_background_levels: int = 4,
) -> List[LiquidityLevel]:
    if not levels or not signals:
        return []

    highlighted_level_keys = {
        (sig.level_side, round(float(sig.level_price), 8))
        for sig in signals
    }

    best_signal = sorted(signals, key=lambda s: (
        s.score, s.signal_time), reverse=True)[0]
    reference_price = float(best_signal.level_price)

    candidates = []
    for lvl in levels:
        level_key = (lvl.side, round(float(lvl.price), 8))
        if level_key in highlighted_level_keys:
            continue
        distance = abs(float(lvl.price) - reference_price)
        candidates.append((distance, lvl))

    candidates.sort(key=lambda x: x[0])
    return [lvl for _, lvl in candidates[:max_background_levels]]


def _prepare_data(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()

    if not isinstance(data.index, pd.DatetimeIndex):
        data.index = pd.to_datetime(data.index, errors="coerce")

    if getattr(data.index, "tz", None) is not None:
        data.index = data.index.tz_convert(None)

    return data[~data.index.isna()]


def _filter_signals_for_visible_range(data: pd.DataFrame, signals: List[LiquiditySignal]) -> List[LiquiditySignal]:
    visible_index = set(data.index)
    return [sig for sig in signals if sig.signal_time in visible_index]


def _build_subset_for_zoom(
    data: pd.DataFrame,
    signals: List[LiquiditySignal],
    zoom_fraction: float = 1 / 3,
    min_bars: int = 30,
) -> pd.DataFrame:
    if data.empty:
        return data

    total = len(data)
    zoom_bars = max(int(total * zoom_fraction), min_bars)
    zoom_bars = min(zoom_bars, total)
    start_idx = total - zoom_bars

    if signals:
        best_signal = sorted(signals, key=lambda s: (
            s.score, s.signal_time), reverse=True)[0]
        if best_signal.signal_time in data.index:
            best_loc = data.index.get_loc(best_signal.signal_time)
            if isinstance(best_loc, slice):
                best_loc = best_loc.start
            if isinstance(best_loc, int) and best_loc < start_idx:
                start_idx = max(0, best_loc - 10)

    return data.iloc[start_idx:].copy()


def _render_chart(
    data: pd.DataFrame,
    signals: List[LiquiditySignal],
    levels: List[LiquidityLevel],
    title: str = "",
):
    sorted_signals = sorted(signals, key=lambda s: (
        s.score, s.signal_time), reverse=True)

    fig, ax = plt.subplots(figsize=(15, 7.8))
    fig.suptitle(title, fontsize=12, fontweight="bold", y=0.98)

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

        rect = plt.Rectangle(
            (xi - candle_width / 2, min(o, c)),
            candle_width,
            max(abs(c - o), 1e-6),
            facecolor=color,
            edgecolor="black",
            linewidth=0.5,
            alpha=0.95,
            zorder=3,
        )
        ax.add_patch(rect)

    sma_cols = [c for c in data.columns if isinstance(
        c, str) and c.startswith("SMA")]
    for col in sma_cols:
        ax.plot(data.index, data[col], linewidth=1.15,
                alpha=0.9, label=col, zorder=1)

    background_levels = _select_nearest_background_levels(
        levels, sorted_signals, 4)
    for lvl in background_levels:
        ax.axhline(
            y=float(lvl.price),
            color=_level_color(lvl),
            linestyle="--" if lvl.is_equal_pool else ":",
            linewidth=0.9,
            alpha=0.20,
            zorder=0,
        )

    y_min = float(data["low"].min())
    y_max = float(data["high"].max())
    y_range = max(y_max - y_min, 1e-6)

    for idx, signal in enumerate(sorted_signals):
        if signal.signal_time not in data.index:
            continue

        row = data.loc[signal.signal_time]
        sig_color = _signal_color(signal)

        ax.axhline(
            y=signal.level_price,
            color=sig_color,
            linestyle="-",
            linewidth=1.8 if idx == 0 else 1.3,
            alpha=0.75 if idx == 0 else 0.50,
            zorder=1,
        )

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

        if signal.direction == "bullish":
            sweep_extreme = float(row["low"])
            marker_y = sweep_extreme - y_range * 0.015
            marker = "^"
            text_y = 0.02
            text_va = "bottom"
        else:
            sweep_extreme = float(row["high"])
            marker_y = sweep_extreme + y_range * 0.015
            marker = "v"
            text_y = 0.98
            text_va = "top"

        ax.vlines(
            signal.signal_time,
            ymin=min(signal.level_price, sweep_extreme),
            ymax=max(signal.level_price, sweep_extreme),
            color=sig_color,
            linewidth=2.0 if idx == 0 else 1.4,
            alpha=0.8,
            zorder=4,
        )

        ax.scatter(
            [signal.signal_time],
            [marker_y],
            color=sig_color,
            marker=marker,
            s=95 if idx == 0 else 70,
            zorder=6,
        )

        if idx == 0:
            direction_text = "BULL" if signal.direction == "bullish" else "BEAR"
            flags = []
            if signal.reclaimed:
                flags.append("reclaim")
            if signal.confirmed:
                flags.append("confirm")
            if signal.equal_pool:
                flags.append("equal")
            if signal.level_touches > 1:
                flags.append(f"touches={signal.level_touches}")

            label = (
                f"{direction_text} {signal.signal_type.upper()} | {signal.score:.0f}\n"
                f"Level: {signal.level_price:.4f}\n"
                f"Sweep: {signal.sweep_percent:.3f}%\n"
                f"Wick: {signal.wick_ratio:.2f}\n"
                f"{' | '.join(flags) if flags else 'raw'}"
            )

            ax.text(
                0.015,
                text_y,
                label,
                transform=ax.transAxes,
                fontsize=8,
                color=sig_color,
                va=text_va,
                ha="left",
                bbox=dict(
                    boxstyle="round,pad=0.25",
                    facecolor="white",
                    edgecolor=sig_color,
                    alpha=0.88,
                ),
                zorder=7,
            )

    ax.set_ylabel("Preis")
    ax.grid(True, linestyle=":", alpha=0.28)

    locator = mdates.AutoDateLocator()
    formatter = mdates.ConciseDateFormatter(locator)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(formatter)

    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(fontsize=8, loc="upper left")

    if len(data.index) > 1:
        extra_right = (data.index[-1] - data.index[-2]) * 2
        ax.set_xlim(data.index[0], data.index[-1] + extra_right)

    fig.autofmt_xdate()
    plt.tight_layout()
    return fig


def save_liquidity_grab_chart_image(
    df: pd.DataFrame,
    signals: List[LiquiditySignal],
    levels: List[LiquidityLevel],
    title: str,
    file_path: str | Path,
    zoom_last_fraction: float | None = None,
    min_zoom_bars: int = 30,
) -> Path | None:
    required = {"open", "high", "low", "close"}
    if df is None or df.empty or not required.issubset(df.columns):
        print("[Fehler] Keine gültigen OHLC-Daten zum Speichern vorhanden.")
        return None

    data = _prepare_data(df)
    if data.empty:
        print("[Fehler] Zeitindex ungültig.")
        return None

    if zoom_last_fraction is not None:
        data = _build_subset_for_zoom(
            data=data,
            signals=signals,
            zoom_fraction=zoom_last_fraction,
            min_bars=min_zoom_bars,
        )

    visible_signals = _filter_signals_for_visible_range(data, signals)

    fig = _render_chart(
        data=data,
        signals=visible_signals,
        levels=levels,
        title=title,
    )

    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(file_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return file_path


def plot_liquidity_grab_chart(
    df: pd.DataFrame,
    signals: List[LiquiditySignal],
    levels: List[LiquidityLevel],
    title: str = "",
):
    required = {"open", "high", "low", "close"}
    if df is None or df.empty or not required.issubset(df.columns):
        print("[Fehler] Keine Daten zum Plotten vorhanden.")
        return

    data = _prepare_data(df)
    if data.empty:
        print("[Fehler] Zeitindex ungültig.")
        return

    visible_signals = _filter_signals_for_visible_range(data, signals)
    fig = _render_chart(data=data, signals=visible_signals,
                        levels=levels, title=title)

    backend_name = plt.get_backend().lower()
    is_gui_backend = any(token in backend_name for token in (
        "qt", "gtk", "tk", "wx", "macosx"))

    if not is_gui_backend:
        plt.close(fig)
        return

    try:
        plt.show(block=False)
        plt.pause(0.001)

        while plt.fignum_exists(fig.number):
            plt.pause(0.1)
    finally:
        if plt.fignum_exists(fig.number):
            plt.close(fig)
