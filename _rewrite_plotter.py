from pathlib import Path

path = Path(''utils/chart/plotter.py'')
text = path.read_text(encoding='utf-8')
text = "import matplotlib.pyplot as plt\nimport matplotlib.dates as mdates\nimport numpy as np\nimport pandas as pd\n\n\n" \
"def plot_candles(df: pd.DataFrame, title: str = \"\"):\n" \
"    required_columns = {''open'', ''high'', ''low'', ''close''}\n" \
"    if df is None or df.empty or not required_columns.issubset(df.columns):\n" \
"        print('[Fehler] Keine Daten zum Plotten oder Spalten fehlen.')\n" \
"        return\n\n" \
"    data = df.copy()\n" \
"    if not isinstance(data.index, pd.DatetimeIndex):\n" \
"        data.index = pd.to_datetime(data.index)\n" \
"    if getattr(data.index, 'tz', None) is not None:\n" \
"        data.index = data.index.tz_convert(None)\n\n" \
"    x = mdates.date2num(data.index)\n\n" \
"    fig, ax = plt.subplots(figsize=(13, 6))\n" \
"    ax.set_title(title, fontsize=12, fontweight='bold', pad=15)\n\n" \
"    unique_x = np.unique(x)\n" \
"    if unique_x.size > 1:\n" \
"        step = np.diff(unique_x).min()\n" \
"        candle_width = step * 0.7\n" \
"    else:\n" \
"        candle_width = 0.6\n\n" \
"    for xi, (_, row) in zip(x, data.iterrows()):\n" \
"        open_price = row[''open'']\n" \
"        close_price = row[''close'']\n" \
"        high_price = row[''high'']\n" \
"        low_price = row[''low'']\n\n" \
"        color = '#26a69a' if close_price >= open_price else '#ef5350'\n\n" \
"        body_bottom = min(open_price, close_price)\n" \
"        body_height = abs(close_price - open_price)\n" \
"        if body_height == 0:\n" \
"            body_height = max((high_price - low_price) * 0.002, 1e-6)\n\n" \
"        ax.vlines(xi, low_price, high_price, color=color, linewidth=1)\n" \
"        rect = plt.Rectangle((xi - candle_width / 2, body_bottom), candle_width, body_height,\n" \
"                             facecolor=color, edgecolor='black', linewidth=0.5, alpha=0.9, zorder=3)\n" \
"        ax.add_patch(rect)\n\n" \
"    ax.xaxis_date()\n" \
"    locator = mdates.AutoDateLocator()\n" \
"    formatter = mdates.ConciseDateFormatter(locator)\n" \
"    ax.xaxis.set_major_locator(locator)\n" \
"    ax.xaxis.set_major_formatter(formatter)\n" \
"    ax.grid(True, linestyle='--', alpha=0.4)\n" \
"    fig.autofmt_xdate()\n" \
"    plt.tight_layout()\n" \
"    plt.show()\n"
path.write_text(text, encoding='utf-8')
