import yaml
import questionary
from utils.daten.data_loader import load_data
from utils.chart.plotter import plot_candles


def main():
    # Konfiguration laden
    with open("config/config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    markets_path = cfg["settings"]["markets_file"]
    with open(markets_path, "r", encoding="utf-8") as f:
        markets = yaml.safe_load(f)["markets"]

    # Markt auswählen
    market_key = questionary.select(
        "Bitte Markt auswählen:",
        choices=list(markets.keys())
    ).ask()

    # Symbol innerhalb dieses Marktes auswählen
    symbols_list = markets[market_key]
    symbol_entry = questionary.select(
        f"Bitte Symbol aus {market_key} auswählen:",
        choices=[f'{s["symbol"]} ({s["name"]})' for s in symbols_list]
    ).ask()

    # Symbol-Objekt zurückholen
    selected_symbol = next(s for s in symbols_list if s["symbol"] in symbol_entry)

    # Timeframe auswählen
    timeframe = questionary.select(
        "Bitte Timeframe auswählen:",
        choices=["M15", "H1", "H4", "D1"]
    ).ask()

    source = selected_symbol.get("source", cfg["settings"]["default_source"])
    symbol = selected_symbol["symbol"]

    print(f"\n📊 Lade Daten für {symbol} ({market_key}, {source}, {timeframe})\n")

    # Lookback und Token aus config.yaml ziehen
    lookback = cfg["settings"].get("lookback", 200)
    oanda_token = cfg.get("oanda", {}).get("access_token")

    df = load_data(symbol, source, timeframe, lookback=lookback, oanda_token=oanda_token)

    if df is None or df.empty:
        print(f"⚠️ Keine Daten für {symbol}")
        return

    plot_candles(df, title=f"{symbol} [{market_key}] {timeframe}")


if __name__ == "__main__":
    main()
