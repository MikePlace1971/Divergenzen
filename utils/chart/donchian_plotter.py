# /utils/chart/donchian_plotter.py

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def plot_donchian_chart(df, title="", symbol=None, index=None, timeframe=None):

    data = df.copy()

    required = {"open", "high", "low", "close"}
    if data.empty or not required.issubset(data.columns):
        print("[Fehler] Daten unvollständig – Chart kann nicht angezeigt werden.")
        return

    # Index reset -> KEINE Zeitlücken im Chart
    data = data.reset_index(drop=True)
    x = np.arange(len(data))

    # === ENTRY SIGNAL ERKENNEN ===
    entry_index = None
    if (
        "SMA200" in data.columns
        and "don_high" in data.columns
        and "don_low" in data.columns
    ):

        last = data.iloc[-1]

        # SHORT Setup
        if last["close"] < last["SMA200"] and last["high"] >= last["don_high"]:
            entry_index = len(data) - 1
            entry_color = "#FF0000"  # rot

        # LONG Setup
        elif last["close"] > last["SMA200"] and last["low"] <= last["don_low"]:
            entry_index = len(data) - 1
            entry_color = "#00B050"  # grün

        else:
            entry_color = None
    else:
        entry_color = None

    # === Plot vorbereiten ===
    fig, ax = plt.subplots(figsize=(14, 7))
    fig.suptitle(title, fontsize=12, fontweight="bold")

    candle_width = 0.7

    # === Kerzen zeichnen ===
    for xi, (_, row) in zip(x, data.iterrows()):
        o, c, h, l = row["open"], row["close"], row["high"], row["low"]
        color = "#00B050" if c >= o else "#FF0000"
        ax.vlines(xi, l, h, color=color, linewidth=1)
        ax.add_patch(
            plt.Rectangle(
                (xi - candle_width / 2, min(o, c)),
                candle_width,
                abs(c - o),
                facecolor=color,
                edgecolor="black",
                linewidth=0.5,
                zorder=3,
            )
        )

    # === SMA200 ===
    if "SMA200" in data.columns:
        ax.plot(x, data["SMA200"], color="#1f77b4", linewidth=1.4, label="SMA200")

    # === Donchian Kanal ===
    if "don_high" in data.columns and "don_low" in data.columns:
        ax.plot(
            x,
            data["don_high"],
            color="#FFA500",
            linestyle="--",
            linewidth=1.4,
            label="Donchian High",
        )
        ax.plot(
            x,
            data["don_low"],
            color="#FFA500",
            linestyle="--",
            linewidth=1.4,
            label="Donchian Low",
        )

    # === Stil & Achsen ===
    ax.set_ylabel("Preis")
    ax.grid(True, linestyle=":", alpha=0.35)
    ax.legend(fontsize=9)

    # WICHTIG → Rechts Platz für Übersicht
    ax.set_xlim(-1, len(data) + 6)

    # X-Achse = Kerzenindex → keine Datumslabels
    ax.set_xticks([])

    plt.tight_layout()
    plt.show()
