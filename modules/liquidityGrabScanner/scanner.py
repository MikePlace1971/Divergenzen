"""
modules/liquidtyGrabScanner/scanner.py

Scannt ausgewählte Märkte nach Liquidity Grabs und Runs.

Die Datei lädt Kursdaten, übergibt sie an den Detector, bewertet die
Treffer und zeigt anschließend die relevantesten Charts.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

import questionary

from utils.daten.data_loader import load_data
from .detector import LiquidityGrabDetector
from .plotter import plot_liquidity_grab_chart


def _resolve_oanda_token(cfg: Dict[str, Any]) -> str | None:
    """
    Holt den OANDA-Token bevorzugt aus der Umgebungsvariable,
    deren Name in der config.yaml steht.
    """
    oanda_cfg = cfg.get("oanda", {}) if isinstance(cfg, dict) else {}

    token_env_name = oanda_cfg.get("access_token_env", "OANDA_ACCESS_TOKEN")
    token = os.getenv(token_env_name)

    # Fallback nur für Altbestand
    if not token:
        token = oanda_cfg.get("access_token")

    return token


def scan_liquidity_grabs(
    markets: Dict[str, List[Dict[str, Any]]],
    cfg: Dict[str, Any],
    timeframe_choices: List[str],
) -> None:
    """
    Interaktiver Scanner:
    - Märkte wählen
    - Timeframe wählen
    - Liquidity-Grabs finden
    - Ergebnisse sortieren
    - Charts öffnen
    """
    lg_cfg = cfg.get("liquidity_grab", {}) if isinstance(cfg, dict) else {}
    detector = LiquidityGrabDetector(cfg)

    market_choices = [
        questionary.Choice(title=key, value=key, checked=True)
        for key in markets.keys()
    ]

    selected_markets = questionary.checkbox(
        "Märkte für Liquidity-Grab-Scan auswählen:",
        choices=market_choices,
        validate=lambda sel: bool(
            sel) or "Bitte mindestens einen Markt wählen.",
    ).ask()

    if not selected_markets:
        print("[INFO] Keine Märkte ausgewählt.")
        return

    timeframe = questionary.select(
        "Bitte Timeframe auswählen:",
        choices=timeframe_choices,
    ).ask()

    if not timeframe:
        print("[INFO] Auswahl abgebrochen.")
        return

    lookback_bars = int(lg_cfg.get("lookback_bars", 260))
    allow_multiple = bool(lg_cfg.get(
        "allow_multiple_signals_per_symbol", True))
    oanda_token = _resolve_oanda_token(cfg)

    print("\n================ STARTE LIQUIDITY-GRAB-SCANNER ================")
    print(
        f"[INFO] timeframe={timeframe} | lookback={lookback_bars} | "
        f"confirmation={lg_cfg.get('confirmation_mode', 'reclaim_only')}\n"
    )

    results: List[Tuple[str, str, str, Dict[str, Any]]] = []

    for market_key in selected_markets:
        entries = markets.get(market_key, [])
        total = len(entries)

        print(f"--- Scanne Markt: {market_key} ({total} Werte) ---")

        for i, entry in enumerate(entries, start=1):
            symbol = entry.get("symbol")
            if not symbol:
                continue

            name = entry.get("name", symbol)
            source = entry.get(
                "source",
                cfg.get("settings", {}).get("default_source", "yfinance"),
            )

            print(
                f"[{market_key}] {i:>3}/{total} {symbol:<14} lade Daten...".ljust(
                    100),
                end="\r",
                flush=True,
            )

            df = load_data(
                symbol=symbol,
                source=source,
                timeframe=timeframe,
                lookback=lookback_bars,
                oanda_token=oanda_token,
            )

            if df is None or df.empty:
                print(
                    f"[{market_key}] {i:>3}/{total} {symbol:<14} keine Daten".ljust(
                        100),
                    end="\r",
                    flush=True,
                )
                continue

            analysis = detector.analyze(df)
            signals = analysis.get("signals", [])
            levels = analysis.get("levels", [])

            if not signals:
                print(
                    f"[{market_key}] {i:>3}/{total} {symbol:<14} keine Signale".ljust(
                        100),
                    end="\r",
                    flush=True,
                )
                continue

            if not allow_multiple:
                signals = signals[:1]

            results.append(
                (
                    symbol,
                    name,
                    market_key,
                    {
                        "df": analysis.get("df", df),
                        "signals": signals,
                        "levels": levels,
                    },
                )
            )

            best_signal = signals[0]
            print(
                f"[{market_key}] {i:>3}/{total} {symbol:<14} "
                f"{best_signal.direction.upper()} {best_signal.signal_type.upper()} "
                f"score={best_signal.score:.0f}".ljust(120),
                end="\r",
                flush=True,
            )

        print()

        best_per_symbol = {}

        for symbol, name, market_key, payload in results:
            signals = payload.get("signals", [])
            if not signals:
                continue

            best = signals[0]
            key = (symbol, market_key)

            if key not in best_per_symbol:
                best_per_symbol[key] = (symbol, name, market_key, payload)
            else:
                old_best = best_per_symbol[key][3]["signals"][0]
                if best.score > old_best.score:
                    best_per_symbol[key] = (symbol, name, market_key, payload)

        results = list(best_per_symbol.values())

    if not results:
        print("\n[INFO] Keine Liquidity-Grabs in den ausgewählten Märkten gefunden.")
        return

    # Beste Ergebnisse zuerst sortieren
    results.sort(
        key=lambda item: item[3]["signals"][0].score if item[3]["signals"] else 0,
        reverse=True,
    )

    print("\n================ TREFFER-ZUSAMMENFASSUNG ================")
    for symbol, name, market_key, payload in results:
        best = payload["signals"][0]
        print(
            f"{symbol:<12} | {market_key:<16} | "
            f"{best.direction:<7} | {best.signal_type:<11} | "
            f"Score={best.score:>6.2f} | Sweep={best.sweep_percent:>6.3f}% | "
            f"Level={best.level_price:.5f} | {name}"
        )

    print("\n[INFO] Öffne Charts nacheinander. Fenster schließen → nächster Chart.\n")

    for symbol, name, market_key, payload in results:
        df = payload["df"]
        signals = payload["signals"]
        levels = payload["levels"]

        title = f"{name} ({symbol}) [{market_key}] {timeframe} | Liquidity Grab"

        plot_liquidity_grab_chart(
            df=df,
            signals=signals,
            levels=levels,
            title=title,
        )

    print("\n[OK] Liquidity-Grab-Scan abgeschlossen.\n")
