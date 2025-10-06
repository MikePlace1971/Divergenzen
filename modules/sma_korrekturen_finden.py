# /modules/sma_korrekturen_finden.py
import time
import pandas as pd
from utils.chart.plotter import plot_candles
from utils.daten.data_loader import load_data
from modules.divergence_detector import DivergenceDetector


def finde_sma_korrekturen(markets, cfg, timeframe_choices):
    """
    Scannt ausgewählte Märkte und findet Werte, bei denen
    der Schlusskurs über dem SMA200, aber unter dem SMA20 liegt.
    """

    import questionary

    market_choices = [
        questionary.Choice(title=key, value=key, checked=True) for key in markets.keys()
    ]
    selected_markets = questionary.checkbox(
        "Märkte für SMA-Korrektur-Scan auswählen:",
        choices=market_choices,
        validate=lambda sel: bool(sel) or "Bitte mindestens einen Markt wählen.",
    ).ask()

    if not selected_markets:
        print("[INFO] Keine Märkte ausgewählt.")
        return

    timeframe = questionary.select(
        "Bitte Timeframe auswählen:", choices=timeframe_choices
    ).ask()

    if not timeframe:
        print("[INFO] Auswahl abgebrochen.")
        return

    print("\n================ STARTE SMA-KORREKTUR-SCANNER ================")

    results = []
    # SMA-Perioden aus Konfiguration (Fallbacks: 200/20)
    sma_cfg = cfg.get("SMA", {}) if isinstance(cfg, dict) else {}
    langfristig = int(sma_cfg.get("langfristig", 200))
    kurzfristig = int(sma_cfg.get("kurzfristig", 20))
    # Divergence-Detector bauen (Konfiguration berücksichtigen)
    div_cfg = cfg.get(
        "divergence", {"rsi_period": 14, "fractal_periods": 4, "max_bars_diff": 30}
    )
    detector = DivergenceDetector(
        rsi_period=div_cfg.get("rsi_period", 14),
        fractal_periods=div_cfg.get("fractal_periods", 4),
        max_bars_diff=div_cfg.get("max_bars_diff", 30),
    )
    for market_key in selected_markets:
        print(f"\n--- Scanne Markt: {market_key} ---")
        for entry in markets.get(market_key, []):
            symbol = entry.get("symbol")
            name = entry.get("name", symbol)
            source = entry.get(
                "source", cfg.get("settings", {}).get("default_source", "yfinance")
            )
            oanda_token = cfg.get("oanda", {}).get("access_token")
            lookback = cfg.get("auswertung", {}).get("maximal_bars", 200)

            df = load_data(symbol, source, timeframe, lookback, oanda_token)
            if df.empty:
                continue

            # Berechne SMAs anhand der konfigurierten Perioden
            df[f"SMA{kurzfristig}"] = df["close"].rolling(window=kurzfristig).mean()
            df[f"SMA{langfristig}"] = df["close"].rolling(window=langfristig).mean()

            if len(df) < max(langfristig, kurzfristig):
                continue

            last = df.iloc[-1]
            sma_long_col = f"SMA{langfristig}"
            sma_short_col = f"SMA{kurzfristig}"
            if (
                last["close"] > last[sma_long_col]
                and last["close"] < last[sma_short_col]
            ):
                print(f"[TREFFER] {name} ({symbol}) erfüllt SMA-Korrektur-Bedingung.")
                results.append((name, symbol, market_key, df))

            time.sleep(0.3)

    if not results:
        print("\n[INFO] Keine SMA-Korrektur-Werte gefunden.")
        return

    print("\n================ TREFFER-ZUSAMMENFASSUNG ===============")
    for name, symbol, market_key, _ in results:
        print(f"- {name} ({symbol}) | {market_key}")

    print("\n[INFO] Öffne Charts nacheinander. Fenster schließen, um fortzufahren...\n")
    for name, symbol, market_key, df in results:
        # Berechne Divergenzen für das gesamte DataFrame und übergebe sie an den Plot
        div_result = detector.find_divergences(df)
        plot_candles(
            df,
            title=f"{symbol} [{market_key}] {timeframe}",
            name=name,
            symbol=symbol,
            index=market_key,
            timeframe=timeframe,
            divergences=div_result,
        )

    print("\n[OK] SMA-Korrektur-Scan abgeschlossen.")
