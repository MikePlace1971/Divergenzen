import time
from typing import Any, Dict, List, Tuple

import pandas as pd
import questionary

from utils.daten.data_loader import load_data
from modules.rsi_wilder import compute_rsi_wilder
from utils.chart.plotter import plot_candles


def scan_rsi_range(
    markets: Dict[str, List[Dict[str, Any]]],
    cfg: Dict[str, Any],
    timeframe_choices: List[str],
) -> None:
    """
    Scannt ausgewählte Märkte:
    - zeigt am Ende Werte, deren RSI im Bereich [lower, upper] liegt (Range-Liste)
    - plottet nach dem Durchlauf nur Ausreißer: RSI < lower oder RSI > upper
    - zeigt beim Scan Fortschritt (Symbol + RSI), damit man sieht, dass was passiert
    """

    # --- Config lesen (mit Defaults) ---
    rsi_cfg = cfg.get("rsi_scanner", {}) if isinstance(cfg, dict) else {}
    period = int(rsi_cfg.get("period", 14))
    lower = float(rsi_cfg.get("lower", 30))
    upper = float(rsi_cfg.get("upper", 70))
    default_lookback = int(rsi_cfg.get("lookback_bars", 200))

    if lower >= upper:
        print(f"[ERROR] rsi_scanner.lower ({lower}) muss kleiner sein als upper ({upper}).")
        return

    # --- Märkte wählen ---
    market_choices = [
        questionary.Choice(title=key, value=key, checked=True) for key in markets.keys()
    ]
    selected_markets = questionary.checkbox(
        "Märkte für RSI-Scan auswählen:",
        choices=market_choices,
        validate=lambda sel: bool(sel) or "Bitte mindestens einen Markt wählen.",
    ).ask()

    if not selected_markets:
        print("[INFO] Keine Märkte ausgewählt.")
        return

    # --- Timeframe wählen ---
    timeframe = questionary.select(
        "Bitte Timeframe auswählen:", choices=timeframe_choices
    ).ask()

    if not timeframe:
        print("[INFO] Auswahl abgebrochen.")
        return

    print("\n================ STARTE RSI-SCANNER ================")
    print(f"[INFO] RSI period={period}, lower={lower}, upper={upper}, timeframe={timeframe}\n")

    # Range-Ergebnisse (wie bisher)
    in_range: List[Tuple[str, str, str, float]] = []  # (symbol, name, market_key, rsi)

    # Ausreißer für Plot
    below: List[Tuple[str, str, str, float, pd.DataFrame]] = []  # + df
    above: List[Tuple[str, str, str, float, pd.DataFrame]] = []  # + df

    oanda_token = cfg.get("oanda", {}).get("access_token")

    for market_key in selected_markets:
        entries = markets.get(market_key, [])
        total = len(entries)
        print(f"--- Scanne Markt: {market_key} ({total} Werte) ---")

        for i, entry in enumerate(entries, start=1):
            symbol = entry.get("symbol")
            if not symbol:
                continue

            name = entry.get("name", symbol)
            source = entry.get("source", cfg.get("settings", {}).get("default_source", "yfinance"))

            # genug Bars laden, damit RSI stabil ist
            lookback = max(default_lookback, period * 4)

            df = load_data(
                symbol=symbol,
                source=source,
                timeframe=timeframe,
                lookback=lookback,
                oanda_token=oanda_token,
            )

            if df is None or df.empty or "close" not in df.columns:
                # Fortschritt trotzdem anzeigen
                print(f"[{market_key}] {i:>3}/{total} {symbol:<12} -> keine Daten".ljust(80), end="\r", flush=True)
                continue

            df = df.copy()
            df["rsi"] = compute_rsi_wilder(df["close"], period)

            last_rsi = df["rsi"].iloc[-1]
            if pd.isna(last_rsi):
                print(f"[{market_key}] {i:>3}/{total} {symbol:<12} -> RSI NaN".ljust(80), end="\r", flush=True)
                continue

            last_rsi_f = float(last_rsi)

            # Live-Fortschritt (damit man sieht, dass es läuft)
            print(
                f"[{market_key}] {i:>3}/{total} {symbol:<12} RSI={last_rsi_f:>6.2f}  {name}".ljust(120),
                end="\r",
                flush=True,
            )

            # Range-Liste (wie bisher)
            if lower <= last_rsi_f <= upper:
                in_range.append((symbol, name, market_key, last_rsi_f))

            # Ausreißer sammeln (für Plot)
            if last_rsi_f < lower:
                below.append((symbol, name, market_key, last_rsi_f, df))
            elif last_rsi_f > upper:
                above.append((symbol, name, market_key, last_rsi_f, df))

            time.sleep(0.12)

        # Zeilenumbruch nach Markt, damit die \r-Zeile nicht „hängen bleibt“
        print()

    # ----------- Terminal-Ausgabe (Range) -----------
    print("\n================ ERGEBNISSE (RSI im Bereich) ================")
    if not in_range:
        print("Keine Werte im Bereich gefunden.")
    else:
        in_range.sort(key=lambda x: x[3])
        for sym, name, mk, rsi in in_range:
            print(f"{sym:<12} | {mk:<18} | RSI={rsi:>6.2f} | {name}")

    # ----------- Ausreißer-Info -----------
    print("\n================ AUSREISSER (für Plot) ================")
    print(f"RSI < {lower}: {len(below)}")
    print(f"RSI > {upper}: {len(above)}")

    if not below and not above:
        print("\n[OK] Keine Ausreißer – daher keine Charts geöffnet.\n")
        return

    print("\n[INFO] Öffne Charts nacheinander (Fenster schließen → nächster Chart)...\n")

    # Erst untere, dann obere Ausreißer – jeweils sortiert
    below.sort(key=lambda x: x[3])          # am stärksten „unten“ zuerst
    above.sort(key=lambda x: -x[3])         # am stärksten „oben“ zuerst

    for sym, name, mk, rsi, df in below:
        plot_candles(
            df,
            title=f"{sym} | {mk} | RSI {rsi:.2f} < {lower}",
            name=name,
            symbol=sym,
            index=mk,
            timeframe=timeframe,
            divergences=None,
            rsi_lower=lower,
            rsi_upper=upper,
            rsi_period=period,
        )

    for sym, name, mk, rsi, df in above:
        plot_candles(
            df,
            title=f"{sym} | {mk} | RSI {rsi:.2f} > {upper}",
            name=name,
            symbol=sym,
            index=mk,
            timeframe=timeframe,
            divergences=None,
            rsi_lower=lower,
            rsi_upper=upper,
            rsi_period=period,
        )

    print("\n[OK] RSI-Scan abgeschlossen.\n")
