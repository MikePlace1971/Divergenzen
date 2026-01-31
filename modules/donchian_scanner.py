# /modules/donchian_scanner.py

from utils.daten.data_loader import load_data
from utils.chart.donchian_plotter import plot_donchian_chart

def scan_donchian(selected_markets, markets, cfg, timeframe):
    source = cfg["settings"]["default_source"]
    sma_period = cfg["SMA"]["langfristig"]
    donchian_period = cfg["donchian"]["period"]
    warn = cfg["donchian"]["warn_distance_percent"] / 100   # z.B. 2% → 0.02

    results = []

    print("\n================ STARTE DONCHIAN-SCANNER ===============")

    for market_key in selected_markets:
        print(f"\n--- Scanne Markt: {market_key} ---")

        for asset in markets.get(market_key, []):
            symbol = asset["symbol"]

            df = load_data(symbol=symbol, source=source, timeframe=timeframe)
            if df.empty or len(df) < donchian_period:
                continue

            # Indikatoren
            df["SMA200"] = df["close"].rolling(sma_period).mean()
            df["don_high"] = df["high"].rolling(donchian_period).max()
            df["don_low"] = df["low"].rolling(donchian_period).min()

            last = df.iloc[-1]

            # ===== SHORT SETUPS =====
            if last["close"] < last["SMA200"]:
                # Short Entry Setup (Touch Donchian High)
                if last["high"] >= last["don_high"]:
                    results.append((symbol, market_key, "SHORT-Setup (Touch Donchian High)", df))
                    continue
                # Short Watchlist
                if last["close"] >= last["don_high"] * (1 - warn):
                    results.append((symbol, market_key, f"SHORT-Watchlist (innerhalb {cfg['donchian']['warn_distance_percent']}%)", df))
                    continue

            # ===== LONG SETUPS =====
            if last["close"] > last["SMA200"]:
                # Long Entry Setup (Touch Donchian Low)
                if last["low"] <= last["don_low"]:
                    results.append((symbol, market_key, "LONG-Setup (Touch Donchian Low)", df))
                    continue
                # Long Watchlist
                if last["close"] <= last["don_low"] * (1 + warn):
                    results.append((symbol, market_key, f"LONG-Watchlist (innerhalb {cfg['donchian']['warn_distance_percent']}%)", df))
                    continue

    print("\n================ ERGEBNISSE ===============")
    if not results:
        print("Keine Signale gefunden.")
        return

    for sym, mk, msg, _ in results:
        print(f"{sym:<12} | {mk:<12} | {msg}")

    print("\n[INFO] Öffne Charts nacheinander. Fenster schließen → nächster Chart.\n")

    for sym, mk, msg, df in results:
        plot_donchian_chart(
            df,
            title=f"{sym} | {mk} | {msg}",
            symbol=sym,
            index=mk,
            timeframe=timeframe
        )

    print("\n[OK] Alle Charts angezeigt.\n")
