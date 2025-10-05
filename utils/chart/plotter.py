import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

def plot_candles(df: pd.DataFrame, title: str = ""):
    if df.empty:
        print("Keine Daten zum Plotten.")
        return

    df = df.copy()
    x = mdates.date2num(pd.to_datetime(df.index))

    fig, ax = plt.subplots(figsize=(12,6))
    ax.set_title(title)

    up = df["close"] >= df["open"]
    down = ~up

    # grüne Kerzen
    ax.bar(
        x[up.values], 
        (df.loc[up, "close"] - df.loc[up, "open"]).values, 
        bottom=df.loc[up, "open"].values,
        color="green", width=0.02
    )

    # rote Kerzen
    ax.bar(
        x[down.values], 
        (df.loc[down, "close"] - df.loc[down, "open"]).values, 
        bottom=df.loc[down, "open"].values,
        color="red", width=0.02
    )

    # Dochte
    ax.vlines(x, df["low"].values, df["high"].values, color="black", linewidth=0.5)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d\n%H:%M"))
    ax.grid(True, linestyle="--", alpha=0.4)
    plt.tight_layout()
    plt.show()
