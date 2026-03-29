"""
modules/liquidityGrabScanner/scanner.py
"""

from __future__ import annotations

import os
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import questionary

from utils.daten.data_loader import load_data
from .detector import LiquidityGrabDetector
from .plotter import plot_liquidity_grab_chart, save_liquidity_grab_chart_image


def _resolve_oanda_token(cfg: Dict[str, Any]) -> str | None:
    oanda_cfg = cfg.get("oanda", {}) if isinstance(cfg, dict) else {}

    token_env_name = oanda_cfg.get("access_token_env", "OANDA_ACCESS_TOKEN")
    token = os.getenv(token_env_name)

    if not token:
        token = oanda_cfg.get("access_token")

    return token


def _sanitize_filename(text: str) -> str:
    bad_chars = '<>:"/\\|?*'
    result = text
    for ch in bad_chars:
        result = result.replace(ch, "_")
    return result.replace(" ", "_")


def _create_output_paths(base_root: str = "outputs/liquidity_grab_scans") -> tuple[Path, Path, Path]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    scan_dir = Path(base_root) / timestamp
    full_dir = scan_dir / "full"
    zoom_dir = scan_dir / "zoom"

    full_dir.mkdir(parents=True, exist_ok=True)
    zoom_dir.mkdir(parents=True, exist_ok=True)

    return scan_dir, full_dir, zoom_dir


def _zip_scan_folder(scan_dir: Path) -> Path:
    zip_path = scan_dir / f"{scan_dir.name}.zip"

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in scan_dir.rglob("*"):
            if file_path.is_file() and file_path != zip_path:
                zf.write(file_path, arcname=file_path.relative_to(scan_dir))

    return zip_path


def scan_liquidity_grabs(
    markets: Dict[str, List[Dict[str, Any]]],
    cfg: Dict[str, Any],
    timeframe_choices: List[str],
) -> None:
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

    save_chart_images = bool(lg_cfg.get("save_chart_images", True))
    show_chart_windows = bool(lg_cfg.get("show_chart_windows", True))
    zoom_fraction = float(lg_cfg.get("save_zoom_fraction", 1 / 3))
    min_zoom_bars = int(lg_cfg.get("save_zoom_min_bars", 30))

    scan_dir = None
    full_dir = None
    zoom_dir = None

    if save_chart_images:
        scan_dir, full_dir, zoom_dir = _create_output_paths()

    print("\n================ STARTE LIQUIDITY-GRAB-SCANNER ================")
    print(
        f"[INFO] timeframe={timeframe} | lookback={lookback_bars} | "
        f"confirmation={lg_cfg.get('confirmation_mode', 'reclaim_only')}"
    )

    if save_chart_images and scan_dir is not None:
        print(f"[INFO] Charts werden gespeichert in: {scan_dir}")

    print()

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
            f"Wick={best.wick_ratio:>5.2f} | Level={best.level_price:.5f} | {name}"
        )

    print()

    saved_count = 0

    for symbol, name, market_key, payload in results:
        df = payload["df"]
        signals = payload["signals"]
        levels = payload["levels"]

        title = f"{name} ({symbol}) [{market_key}] {timeframe} | Liquidity Grab"
        base_filename = _sanitize_filename(
            f"{market_key}_{symbol}_{timeframe}")

        if save_chart_images and full_dir and zoom_dir:
            full_path = full_dir / f"{base_filename}_full.png"
            zoom_path = zoom_dir / f"{base_filename}_zoom.png"

            saved1 = save_liquidity_grab_chart_image(
                df=df,
                signals=signals,
                levels=levels,
                title=f"{title} | FULL",
                file_path=full_path,
                zoom_last_fraction=None,
            )
            if saved1:
                saved_count += 1

            saved2 = save_liquidity_grab_chart_image(
                df=df,
                signals=signals,
                levels=levels,
                title=f"{title} | ZOOM_LAST_THIRD",
                file_path=zoom_path,
                zoom_last_fraction=zoom_fraction,
                min_zoom_bars=min_zoom_bars,
            )
            if saved2:
                saved_count += 1

        if show_chart_windows:
            plot_liquidity_grab_chart(
                df=df,
                signals=signals,
                levels=levels,
                title=title,
            )

    zip_path = None
    if save_chart_images and scan_dir is not None:
        zip_path = _zip_scan_folder(scan_dir)

    print("\n[OK] Liquidity-Grab-Scan abgeschlossen.")
    if save_chart_images and scan_dir is not None:
        print(f"[INFO] Scan-Ordner: {scan_dir}")
        print(f"[INFO] Gespeicherte Bilder: {saved_count}")
    if zip_path is not None:
        print(f"[INFO] ZIP-Datei: {zip_path}")
    print()
