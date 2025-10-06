# /main.py
import time
from typing import Any, Dict, List, Optional
from modules.sma_korrekturen_finden import finde_sma_korrekturen

import questionary
import yaml

from modules.divergence_detector import DivergenceDetector
from utils.chart.plotter import plot_candles
from utils.daten.data_loader import load_data


DEFAULT_TIMEFRAME_CHOICES = ["H4", "D1"]


def load_config() -> Optional[Dict[str, Any]]:
    try:
        with open("config/config.yaml", "r", encoding="utf-8") as stream:
            return yaml.safe_load(stream)
    except FileNotFoundError:
        print("[ERROR] config/config.yaml nicht gefunden.")
    except yaml.YAMLError as exc:
        print(f"[ERROR] Konnte config.yaml nicht einlesen: {exc}")
    return None


def load_markets(path: str) -> Optional[Dict[str, List[Dict[str, Any]]]]:
    try:
        with open(path, "r", encoding="utf-8") as stream:
            data = yaml.safe_load(stream)
            return data.get("markets", {}) if isinstance(data, dict) else {}
    except FileNotFoundError:
        print(f"[ERROR] Maerkte-Datei {path} nicht gefunden.")
    except yaml.YAMLError as exc:
        print(f"[ERROR] Konnte Maerkte-Datei nicht einlesen: {exc}")
    return None


def get_timeframe_choices(cfg: Dict[str, Any]) -> List[str]:
    settings = cfg.get("settings", {})
    configured = settings.get("timeframe_choices")
    if isinstance(configured, list) and configured:
        choices = [str(item).upper() for item in configured if item]
    else:
        choices = list(DEFAULT_TIMEFRAME_CHOICES)

    default_entry = settings.get("timeframe")
    if isinstance(default_entry, str):
        normalized = default_entry.upper()
        if normalized and normalized not in choices:
            choices.append(normalized)

    seen = set()
    ordered = []
    for item in DEFAULT_TIMEFRAME_CHOICES + choices:
        if item not in seen:
            ordered.append(item)
            seen.add(item)
    return ordered


def build_detector(cfg: Dict[str, Any]) -> DivergenceDetector:
    div_cfg = cfg.get(
        "divergence",
        {"rsi_period": 14, "fractal_periods": 4, "max_bars_diff": 30},
    )
    return DivergenceDetector(
        rsi_period=div_cfg.get("rsi_period", 14),
        fractal_periods=div_cfg.get("fractal_periods", 4),
        max_bars_diff=div_cfg.get("max_bars_diff", 30),
    )


def analyze_symbol(
    symbol_entry: Dict[str, Any],
    market_key: str,
    cfg: Dict[str, Any],
    timeframe: str,
    detector: DivergenceDetector,
) -> Optional[Dict[str, Any]]:
    source = symbol_entry.get(
        "source", cfg.get("settings", {}).get("default_source", "yfinance")
    )
    symbol = symbol_entry.get("symbol")
    name = symbol_entry.get("name", symbol or "")

    if not symbol:
        print(f"[WARN] Kein Symbol in Eintrag {symbol_entry}.")
        return None

    lookback = cfg.get("auswertung", {}).get("maximal_bars", 200)
    oanda_token = cfg.get("oanda", {}).get("access_token")

    print(
        f"\n[INFO] Lade {symbol} ({symbol_entry.get('name', symbol)}) "
        f"aus {market_key} ({source}, {timeframe})"
    )

    raw_df = load_data(
        symbol,
        source,
        timeframe,
        lookback=lookback,
        oanda_token=oanda_token,
    )

    if raw_df is None or raw_df.empty:
        print(f"[WARN] Keine Daten fuer {symbol}.")
        return None

    bars_for_analysis = (
        lookback if isinstance(lookback, int) and lookback > 0 else len(raw_df)
    )
    analysis_df = raw_df.tail(bars_for_analysis) if bars_for_analysis else raw_df

    print(
        f"[INFO] {len(raw_df)} Bars geladen, verwende {len(analysis_df)} Bars fuer Divergenz."
    )

    full_result = detector.find_divergences(raw_df)

    if analysis_df.empty:
        recent_bullish = []
        recent_bearish = []
    else:
        window_start = analysis_df.index[0]

        def _filter_recent(pairs):
            return [pair for pair in pairs if pair[1] >= window_start]

        recent_bullish = _filter_recent(full_result.get("bullish", []))
        recent_bearish = _filter_recent(full_result.get("bearish", []))

    bullish = len(recent_bullish)
    bearish = len(recent_bearish)

    if bullish or bearish:
        print(
            f"[OK] {name} ({symbol}) -> {bullish} Bullish / {bearish} Bearish Divergenzen (letzte {len(analysis_df)} Bars)"
        )
    else:
        print(
            f"[INFO] {name} ({symbol}) -> Keine Divergenzen in den letzten {len(analysis_df)} Bars gefunden"
        )

    return {
        "symbol": symbol,
        "name": name,
        "market": market_key,
        "bullish": bullish,
        "bearish": bearish,
        "result": full_result,
        "recent_divergences": {"bullish": recent_bullish, "bearish": recent_bearish},
        "df": raw_df,
        "analysis_df": analysis_df,
        "timeframe": timeframe,
    }


def run_single_analysis(
    markets: Dict[str, List[Dict[str, Any]]],
    cfg: Dict[str, Any],
    detector: DivergenceDetector,
    timeframe_choices: List[str],
) -> None:
    market_key = questionary.select(
        "Bitte Markt auswaehlen:", choices=list(markets.keys())
    ).ask()
    if not market_key:
        print("[INFO] Auswahl abgebrochen.")
        return

    entries = markets.get(market_key, [])
    if not entries:
        print(f"[WARN] Kein Eintrag fuer Markt {market_key} gefunden.")
        return

    symbol_choice = questionary.select(
        f"Bitte Symbol aus {market_key} auswaehlen:",
        choices=[
            questionary.Choice(
                title=f"{entry['symbol']} ({entry.get('name', entry['symbol'])})",
                value=entry,
            )
            for entry in entries
        ],
    ).ask()
    if not symbol_choice:
        print("[INFO] Auswahl abgebrochen.")
        return

    timeframe = questionary.select(
        "Bitte Timeframe auswaehlen:", choices=timeframe_choices
    ).ask()
    if not timeframe:
        print("[INFO] Auswahl abgebrochen.")
        return

    result = analyze_symbol(symbol_choice, market_key, cfg, timeframe, detector)
    if result:
        plot_candles(
            result["df"],
            title=f"{result['symbol']} [{result['market']}] {timeframe}",
            name=result["name"],
            symbol=result["symbol"],
            index=result["market"],
            timeframe=timeframe,
            divergences=result["result"],
        )


def run_market_scanner(
    markets: Dict[str, List[Dict[str, Any]]],
    cfg: Dict[str, Any],
    detector: DivergenceDetector,
    timeframe_choices: List[str],
) -> None:
    scan_mode = questionary.select(
        "Was möchtest du scannen?",
        choices=[
            questionary.Choice("Divergenzen finden", "divergence"),
            questionary.Choice("SMA Korrekturen finden", "sma"),
        ],
    ).ask()

    if scan_mode == "divergence":
        # bisheriger Divergenz-Scanner
        market_choices = [
            questionary.Choice(title=key, value=key, checked=True)
            for key in markets.keys()
        ]
        selected_markets = questionary.checkbox(
            "Märkte zum Scannen auswählen:",
            choices=market_choices,
            validate=lambda sel: bool(sel) or "Bitte mindestens einen Markt wählen.",
        ).ask()
        if not selected_markets:
            print("[INFO] Auswahl abgebrochen.")
            return

        timeframe = questionary.select(
            "Bitte Timeframe auswählen:", choices=timeframe_choices
        ).ask()
        if not timeframe:
            print("[INFO] Auswahl abgebrochen.")
            return

        print("\n================ STARTE DIVERGENZ-SCANNER ================")

        results: List[Dict[str, Any]] = []
        for market_key in selected_markets:
            print(f"\n--- Scanne Markt: {market_key} ---")
            for entry in markets.get(market_key, []):
                analysis = analyze_symbol(entry, market_key, cfg, timeframe, detector)
                if analysis:
                    results.append(analysis)
                time.sleep(0.4)

        found = [item for item in results if item["bullish"] or item["bearish"]]

        print("\n================ ERGEBNIS-ZUSAMMENFASSUNG ===============")
        if not found:
            print("Keine Divergenzen in den ausgewählten Märkten gefunden.")
            return

        for item in found:
            print(
                f"- {item['name']} ({item['symbol']}) | {item['market']} | "
                f"{item['bullish']} Bullish / {item['bearish']} Bearish"
            )

        print(
            "\n[INFO] Öffne Charts nacheinander. Fenster schließen, um fortzufahren...\n"
        )
        for item in found:
            plot_candles(
                item["df"],
                title=f"{item['symbol']} [{item['market']}] {timeframe}",
                name=item["name"],
                symbol=item["symbol"],
                index=item["market"],
                timeframe=timeframe,
                divergences=item["result"],
            )

        print("\n[OK] Analyse abgeschlossen.")

    elif scan_mode == "sma":
        # neue Funktion für SMA-Korrekturen
        finde_sma_korrekturen(markets, cfg, timeframe_choices)

    else:
        print("[INFO] Auswahl abgebrochen.")


def main() -> None:
    cfg = load_config()
    if not cfg:
        return

    markets_path = cfg.get("settings", {}).get("markets_file")
    if not markets_path:
        print("[ERROR] Kein markets_file in der Konfiguration angegeben.")
        return

    markets = load_markets(markets_path)
    if not markets:
        print("[ERROR] Keine Maerkte geladen.")
        return

    timeframe_choices = get_timeframe_choices(cfg)
    detector = build_detector(cfg)

    mode = questionary.select(
        "Moechtest du einen Einzelwert analysieren oder Maerkte scannen?",
        choices=[
            questionary.Choice("Einzelnen Wert analysieren", "single"),
            questionary.Choice("Maerkte scannen", "scan"),
        ],
    ).ask()

    if mode == "single":
        run_single_analysis(markets, cfg, detector, timeframe_choices)
    elif mode == "scan":
        run_market_scanner(markets, cfg, detector, timeframe_choices)
    else:
        print("[INFO] Auswahl abgebrochen.")


if __name__ == "__main__":
    main()
