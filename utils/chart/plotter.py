# /utils/chart/plotter.py
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
from modules.rsi_wilder import compute_rsi_wilder


def plot_candles(
    df: pd.DataFrame,
    title: str = "",
    name: str | None = None,
    symbol: str | None = None,
    index: str | None = None,
    timeframe: str | None = None,
    divergences: dict | None = None,
):
    required_columns = {"open", "high", "low", "close"}
    if df is None or df.empty or not required_columns.issubset(df.columns):
        print("[Fehler] Keine Daten zum Plotten oder Spalten fehlen.")
        return

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
    # Datenvorbereitung
    # -----------------------------------------------------------
    data = df.copy()
    if not isinstance(data.index, pd.DatetimeIndex):
        data.index = pd.to_datetime(data.index, errors="coerce")
    if getattr(data.index, "tz", None) is not None:
        data.index = data.index.tz_convert(None)
    data = data[~data.index.isna()]
    if data.empty:
        print("[Fehler] Zeitindex konnte nicht interpretiert werden.")
        return

    if "rsi" not in data.columns:
        data["rsi"] = compute_rsi_wilder(data["close"])
    if "rsi_hist" not in data.columns:
        data["rsi_hist"] = data["rsi"] - 50

    # -----------------------------------------------------------
    # Plot-Struktur
    # -----------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(13, 7), sharex=True, gridspec_kw={"height_ratios": [3, 1]}
    )
    fig.suptitle(full_title, fontsize=12, fontweight="bold", y=0.98)

    # -----------------------------------------------------------
    # Candlestick-Darstellung
    # -----------------------------------------------------------
    x = mdates.date2num(data.index)
    unique_x = np.unique(x)
    candle_width = 0.6 if unique_x.size <= 1 else np.diff(unique_x).min() * 0.7

    COLOR_UP = "#00B050"
    COLOR_DOWN = "#FF0000"

    for xi, (_, row) in zip(x, data.iterrows()):
        o, c, h, l = row["open"], row["close"], row["high"], row["low"]
        color = COLOR_UP if c >= o else COLOR_DOWN
        ax1.vlines(xi, l, h, color=color, linewidth=1, alpha=0.9)
        body_bottom = min(o, c)
        body_height = abs(c - o)
        if body_height < (h - l) * 0.002:
            body_height = max((h - l) * 0.002, 1e-6)
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
        ax1.add_patch(rect)

    # Padding rechts, damit letzte Kerze nicht abgeschnitten wird
    if unique_x.size > 1:
        step = float(np.diff(np.sort(unique_x)).min())
    else:
        step = 1.0
    pad = step * 1.5
    ax1.set_xlim(x.min(), x.max() + pad)
    ax2.set_xlim(ax1.get_xlim())

    # -----------------------------------------------------------
    # Vereinheitliche SMA-Spaltennamen: 'SMA 20' -> 'SMA20' (falls vorhanden)
    # und entferne doppelte Spalten (falls vorhanden)
    new_cols = []
    for c in data.columns:
        if isinstance(c, str) and c.startswith("SMA "):
            new_cols.append(c.replace(" ", ""))
        else:
            new_cols.append(c)
    data.columns = new_cols

    # -----------------------------------------------------------
    # Divergenzen: Preis UND RSI
    # -----------------------------------------------------------
    if divergences:
        y_range = data["high"].max() - data["low"].min()
        offset_price = y_range * 0.01
        offset_rsi = 2.0

        for i1, i2 in divergences.get("bullish", []):
            if i1 in data.index and i2 in data.index:
                ax1.plot(
                    [mdates.date2num(i1), mdates.date2num(i2)],
                    [
                        data.loc[i1, "low"] - offset_price,
                        data.loc[i2, "low"] - offset_price,
                    ],
                    color="green",
                    linewidth=2,
                    alpha=0.9,
                )
                ax2.plot(
                    [mdates.date2num(i1), mdates.date2num(i2)],
                    [
                        data.loc[i1, "rsi"] - offset_rsi,
                        data.loc[i2, "rsi"] - offset_rsi,
                    ],
                    color="green",
                    linewidth=2,
                    alpha=0.9,
                )

        for i1, i2 in divergences.get("bearish", []):
            if i1 in data.index and i2 in data.index:
                ax1.plot(
                    [mdates.date2num(i1), mdates.date2num(i2)],
                    [
                        data.loc[i1, "high"] + offset_price,
                        data.loc[i2, "high"] + offset_price,
                    ],
                    color="red",
                    linewidth=2,
                    alpha=0.9,
                )
                ax2.plot(
                    [mdates.date2num(i1), mdates.date2num(i2)],
                    [
                        data.loc[i1, "rsi"] + offset_rsi,
                        data.loc[i2, "rsi"] + offset_rsi,
                    ],
                    color="red",
                    linewidth=2,
                    alpha=0.9,
                )

    # -----------------------------------------------------------
    # RSI-Darstellung
    # -----------------------------------------------------------
    ax2.plot(data.index, data["rsi"], color="black", linewidth=1.1)
    ax2.axhline(70, color="red", linewidth=1.0, linestyle="-", alpha=0.8)
    ax2.axhline(30, color="green", linewidth=1.0, linestyle="-", alpha=0.8)
    ax2.set_ylim(0, 100)
    ax2.set_ylabel("RSI (Wilder)", fontsize=9)
    ax2.grid(True, linestyle=":", alpha=0.3)

    # -----------------------------------------------------------
    # Formatierung
    # -----------------------------------------------------------
    # Zeichne vorhandene SMA-Linien (z. B. SMA20, SMA200, SMA{n})
    sma_cols = [c for c in data.columns if isinstance(c, str) and c.startswith("SMA")]
    if sma_cols:
        # Priorisiere längere Perioden zuerst (z.B. SMA200 unter SMA20 im Plot)
        try:
            sma_sorted = sorted(
                sma_cols, key=lambda x: int(x.replace("SMA", "")), reverse=True
            )
        except Exception:
            sma_sorted = sma_cols

        colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]  # blau, orange, grün, rot
        for i, col in enumerate(sma_sorted):
            color = colors[i % len(colors)]
            ax1.plot(
                data.index,
                data[col],
                color=color,
                linewidth=1.2,
                linestyle="-",
                alpha=0.9,
                label=col,
            )
        ax1.legend(fontsize=8)

    ax1.grid(True, linestyle=":", alpha=0.3)
    ax1.set_ylabel("Kurs", fontsize=9)
    locator = mdates.AutoDateLocator()
    formatter = mdates.ConciseDateFormatter(locator)
    ax1.xaxis.set_major_locator(locator)
    ax1.xaxis.set_major_formatter(formatter)

    fig.autofmt_xdate()
    plt.tight_layout()

    def save_chart_fallback(error: Exception | None = None) -> Path:
        charts_dir = Path('output') / 'charts'
        charts_dir.mkdir(parents=True, exist_ok=True)
        base_parts = [symbol or name or title or 'chart']
        if timeframe:
            base_parts.append(timeframe)
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        base_parts.append(timestamp)
        filename = '_'.join(part for part in base_parts if part)
        safe_name = ''.join(ch if ch.isalnum() or ch in ('-', '_') else '_' for ch in filename) or 'chart'
        output_path = charts_dir / f"{safe_name}.png"
        fig.savefig(output_path, dpi=120)
        if error:
            print(f"[WARN] Interaktives Anzeigen fehlgeschlagen: {error}. Chart gespeichert unter {output_path}")
        else:
            print(f"[INFO] Chart gespeichert unter {output_path}")
        return output_path

    backend_name = plt.get_backend().lower()
    is_gui_backend = any(token in backend_name for token in ('qt', 'gtk', 'tk', 'wx', 'macosx'))

    if not is_gui_backend:
        save_chart_fallback()
        plt.close(fig)
        return

    try:
        manager = plt.get_current_fig_manager()
        if manager is None:
            raise RuntimeError('Kein GUI-Backend verfügbar.')
        plt.show(block=False)

        while plt.fignum_exists(fig.number):
            plt.pause(0.1)
    except Exception as exc:
        save_chart_fallback(exc)
    finally:
        if plt.fignum_exists(fig.number):
            plt.close(fig)
