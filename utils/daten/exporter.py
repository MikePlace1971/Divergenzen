# /utils/daten/exporter.py

from pathlib import Path
from typing import Optional
import pandas as pd


def export_dataframe_to_txt(
    df: pd.DataFrame,
    symbol: str,
    source: str,
    timeframe: str,
    base_dir: str = "exports",
    filename: Optional[str] = None,
) -> Path:

    if df is None or df.empty:
        raise ValueError("DataFrame ist leer.")

    # 👉 Zielordner je nach Quelle
    source_folder = "oanda" if source.lower() == "oanda" else "yfinance"
    export_path = Path(base_dir) / source_folder
    export_path.mkdir(parents=True, exist_ok=True)

    safe_symbol = symbol.replace("/", "_").replace(":", "_").replace(" ", "_")
    safe_timeframe = timeframe.replace("/", "_").replace(":", "_").replace(" ", "_")

    if not filename:
        filename = f"{safe_symbol}_{safe_timeframe}.txt"

    file_path = export_path / filename

    export_df = df.copy().sort_index()
    export_df.index.name = "time"

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(f"Symbol: {symbol}\n")
        f.write(f"Quelle: {source}\n")
        f.write(f"Timeframe: {timeframe}\n")
        f.write(f"Bars: {len(export_df)}\n")
        f.write("-" * 80 + "\n")
        f.write(export_df.to_string())
        f.write("\n")

    return file_path