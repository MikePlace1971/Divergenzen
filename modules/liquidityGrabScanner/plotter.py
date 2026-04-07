"""
modules/liquidityGrabScanner/plotter.py
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter, MaxNLocator

from .detector import LiquiditySignal
from .levels import LiquidityLevel
from .pattern_overlay import find_engulfings, find_fair_value_gaps

try:
    mpl.rcParams["figure.raise_window"] = False
except Exception:
    pass


def _signal_color(signal: LiquiditySignal) -> str:
    # Stage farblich leicht priorisieren
    if signal.stage >= 3:
        return "#7a1fa2" if signal.direction == "bullish" else "#c2185b"
    if signal.stage >= 2:
        return "#008000" if signal.direction == "bullish" else "#cc0000"

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
        s.stage, s.score, s.signal_time), reverse=True)[0]
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

    data = data[~data.index.isna()]
    data = data.sort_index()
    return data


def _validate_plot_data(data: pd.DataFrame) -> None:
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


def _filter_signals_for_visible_range(
    data: pd.DataFrame,
    signals: List[LiquiditySignal],
) -> List[LiquiditySignal]:
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
            s.stage, s.score, s.signal_time), reverse=True)[0]
        if best_signal.signal_time in data.index:
            best_loc = data.index.get_loc(best_signal.signal_time)
            if isinstance(best_loc, slice):
                best_loc = best_loc.start
            if isinstance(best_loc, int) and best_loc < start_idx:
                start_idx = max(0, best_loc - 10)

    subset = data.iloc[start_idx:].copy()

    if len(subset) > len(data):
        raise ValueError("Zoom-Subset ist größer als die Ausgangsdaten.")

    return subset


def _get_overlay_cfg(data: pd.DataFrame) -> dict:
    if hasattr(data, "attrs") and isinstance(data.attrs, dict):
        return data.attrs.get("overlay_cfg", {}) or {}
    return {}


def _build_x_mapping(data: pd.DataFrame) -> tuple[np.ndarray, dict[pd.Timestamp, int]]:
    x = np.arange(len(data), dtype=float)
    pos_by_time = {ts: i for i, ts in enumerate(data.index)}
    return x, pos_by_time


def _make_time_formatter(index: pd.DatetimeIndex) -> FuncFormatter:
    def _formatter(value, _pos):
        i = int(round(value))
        if i < 0 or i >= len(index):
            return ""

        ts = index[i]

        if len(index) <= 40:
            return ts.strftime("%d.%m\n%H:%M")

        inferred = pd.infer_freq(index)
        if inferred and "D" in inferred.upper():
            return ts.strftime("%d.%m.%Y")

        return ts.strftime("%d.%m\n%H:%M")

    return FuncFormatter(_formatter)


def _render_chart(
    data: pd.DataFrame,
    signals: List[LiquiditySignal],
    levels: List[LiquidityLevel],
    title: str = "",
):
    _validate_plot_data(data)

    bars_before = len(data)
    sorted_signals = sorted(signals, key=lambda s: (
        s.stage, s.score, s.signal_time), reverse=True)

    fig, ax = plt.subplots(figsize=(15, 7.8))
    fig.suptitle(title, fontsize=12, fontweight="bold", y=0.98)

    x, pos_by_time = _build_x_mapping(data)

    bars_after = len(x)
    if bars_before != bars_after:
        raise ValueError("Beim Aufbau der Plot-Achse gingen Bars verloren.")

    candle_width = 0.65

    color_up = "#00B050"
    color_down = "#FF0000"

    for i, (_, row) in enumerate(data.iterrows()):
        xi = x[i]
        o = float(row["open"])
        h = float(row["high"])
        l = float(row["low"])
        c = float(row["close"])

        color = color_up if c >= o else color_down

        ax.vlines(xi, l, h, color=color, linewidth=1.0, alpha=0.95, zorder=2)

        rect = Rectangle(
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
        ax.plot(x, data[col].to_numpy(), linewidth=1.15,
                alpha=0.9, label=col, zorder=1)

    overlay_cfg = _get_overlay_cfg(data)

    show_fvg = bool(overlay_cfg.get("show_fvg", True))
    show_engulfing = bool(overlay_cfg.get("show_engulfing", True))
    max_fvg_boxes = int(overlay_cfg.get("max_fvg_boxes", 4))
    max_engulfings = int(overlay_cfg.get("max_engulfings", 6))
    fvg_extend_bars = int(overlay_cfg.get("fvg_extend_bars", 5))
    min_fvg_gap_percent = float(overlay_cfg.get("min_fvg_gap_percent", 0.03))
    fvg_alpha = float(overlay_cfg.get("fvg_alpha", 0.08))
    engulfing_alpha = float(overlay_cfg.get("engulfing_alpha", 0.55))

    if show_fvg:
        fvg_list = find_fair_value_gaps(
            data, min_gap_percent=min_fvg_gap_percent)
        fvg_list = fvg_list[-max_fvg_boxes:]

        for fvg in fvg_list:
            if fvg.end_time not in pos_by_time:
                continue

            left = float(pos_by_time[fvg.end_time])
            right = left + max(fvg_extend_bars, 1)
            color = "#00aa55" if fvg.direction == "bullish" else "#cc3333"

            rect = Rectangle(
                (left, fvg.bottom),
                width=max(right - left, 0.8),
                height=max(fvg.top - fvg.bottom, 1e-6),
                facecolor=color,
                edgecolor=color,
                linewidth=0.8,
                alpha=fvg_alpha,
                zorder=0.4,
            )
            ax.add_patch(rect)

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

    if show_engulfing:
        engulfings = find_engulfings(data)
        engulfings = engulfings[-max_engulfings:]

        for patt in engulfings:
            if patt.time not in pos_by_time:
                continue

            xi = pos_by_time[patt.time]
            row = data.loc[patt.time]
            color = "#00aa55" if patt.direction == "bullish" else "#cc3333"

            if patt.direction == "bullish":
                marker_y = float(row["low"]) - y_range * 0.010
                va = "top"
            else:
                marker_y = float(row["high"]) + y_range * 0.010
                va = "bottom"

            ax.text(
                xi,
                marker_y,
                "E",
                color=color,
                fontsize=7,
                alpha=engulfing_alpha,
                ha="center",
                va=va,
                zorder=5,
                bbox=dict(
                    boxstyle="round,pad=0.10",
                    facecolor="white",
                    edgecolor=color,
                    alpha=0.30,
                    linewidth=0.7,
                ),
            )

    for idx, signal in enumerate(sorted_signals):
        if signal.signal_time not in pos_by_time:
            continue

        xi = pos_by_time[signal.signal_time]
        row = data.loc[signal.signal_time]
        sig_color = _signal_color(signal)

        ax.axhline(
            y=float(signal.level_price),
            color=sig_color,
            linestyle="-",
            linewidth=2.1 if idx == 0 else 1.3,
            alpha=0.78 if idx == 0 else 0.50,
            zorder=1,
        )

        if signal.reference_time in pos_by_time:
            ref_x = pos_by_time[signal.reference_time]
            ax.scatter(
                [ref_x],
                [float(signal.level_price)],
                s=32,
                marker="o",
                facecolors="white",
                edgecolors=sig_color,
                linewidths=1.0,
                alpha=0.9,
                zorder=5,
            )

        if signal.follow_through and signal.follow_through_time in pos_by_time:
            ft_x = pos_by_time[signal.follow_through_time]
            ft_price = float(data.loc[signal.follow_through_time, "close"])
            ax.scatter(
                [ft_x],
                [ft_price],
                s=48,
                marker="s",
                color=sig_color,
                alpha=0.85,
                zorder=6,
            )

        if signal.mss_confirmed and signal.mss_time in pos_by_time:
            mss_x = pos_by_time[signal.mss_time]
            mss_price = float(data.loc[signal.mss_time, "close"])
            ax.scatter(
                [mss_x],
                [mss_price],
                s=65,
                marker="D",
                color=sig_color,
                alpha=0.88,
                zorder=6,
            )

            if signal.mss_level is not None:
                ax.axhline(
                    y=float(signal.mss_level),
                    color=sig_color,
                    linestyle="--",
                    linewidth=1.0,
                    alpha=0.35,
                    zorder=1,
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
            xi,
            ymin=min(float(signal.level_price), sweep_extreme),
            ymax=max(float(signal.level_price), sweep_extreme),
            color=sig_color,
            linewidth=2.1 if idx == 0 else 1.4,
            alpha=0.82,
            zorder=4,
        )

        marker_size = 110 if idx == 0 else 72
        if signal.stage == 2:
            marker_size += 10
        if signal.stage == 3:
            marker_size += 20

        ax.scatter(
            [xi],
            [marker_y],
            color=sig_color,
            marker=marker,
            s=marker_size,
            zorder=6,
        )

        if idx == 0:
            direction_text = "BULL" if signal.direction == "bullish" else "BEAR"
            flags = []

            if signal.reclaimed:
                flags.append("reclaim")
            if signal.follow_through:
                flags.append("follow-through")
            if signal.mss_confirmed:
                flags.append("mss/choch")
            if signal.equal_pool:
                flags.append("equal")
            if signal.level_touches > 1:
                flags.append(f"touches={signal.level_touches}")

            label = (
                f"{signal.stage_label}\n"
                f"{direction_text} {signal.signal_type.upper()} | Score {signal.score:.0f}\n"
                f"Level: {signal.level_price:.4f}\n"
                f"Sweep: {signal.sweep_percent:.3f}%\n"
                f"Wick: {signal.wick_ratio:.2f}\n"
                f"Trend: {signal.trend} | WithTrend: {signal.with_trend}\n"
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
                    alpha=0.90,
                ),
                zorder=7,
            )

    ax.set_ylabel("Preis")
    ax.grid(True, linestyle=":", alpha=0.28)

    ax.xaxis.set_major_locator(MaxNLocator(nbins=10, integer=True))
    ax.xaxis.set_major_formatter(_make_time_formatter(data.index))

    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(fontsize=8, loc="upper left")

    ax.set_xlim(-0.5, len(data) - 0.5 + 1.5)

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
    overlay_cfg: dict | None = None,
) -> Path | None:
    required = {"open", "high", "low", "close"}
    if df is None or df.empty or not required.issubset(df.columns):
        print("[Fehler] Keine gültigen OHLC-Daten zum Speichern vorhanden.")
        return None

    data = _prepare_data(df)
    try:
        _validate_plot_data(data)
    except ValueError as exc:
        print(f"[Fehler] {exc}")
        return None

    if zoom_last_fraction is not None:
        data = _build_subset_for_zoom(
            data=data,
            signals=signals,
            zoom_fraction=zoom_last_fraction,
            min_bars=min_zoom_bars,
        )

    data.attrs["overlay_cfg"] = overlay_cfg or {}
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
    overlay_cfg: dict | None = None,
):
    required = {"open", "high", "low", "close"}
    if df is None or df.empty or not required.issubset(df.columns):
        print("[Fehler] Keine Daten zum Plotten vorhanden.")
        return

    data = _prepare_data(df)
    try:
        _validate_plot_data(data)
    except ValueError as exc:
        print(f"[Fehler] {exc}")
        return

    data.attrs["overlay_cfg"] = overlay_cfg or {}
    visible_signals = _filter_signals_for_visible_range(data, signals)

    fig = _render_chart(
        data=data,
        signals=visible_signals,
        levels=levels,
        title=title,
    )

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
