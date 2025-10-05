"""
sort_markets_yaml.py
-----------------------------------
Dieses Skript sortiert alle Einträge in der Datei `markets.yaml`
alphabetisch nach dem Feld "name" innerhalb jeder Markt-Kategorie
(z. B. DAX, MDAX, OANDA_CURRENCY, usw.).

🔹 Originaldatei: config/markets.yaml
🔹 Ausgabe:       config/markets_sorted.yaml (überschreibt NICHT das Original!)

Verwendung:
    python config/sort_markets_yaml.py

Vorteile:
- Einheitliche alphabetische Reihenfolge nach Name
- Übersichtliche Strukturierung
- Keine Duplikate oder unabsichtliche Überschreibungen
"""

import yaml
import os


def sort_markets(input_file="config/markets.yaml", output_file="config/markets_sorted.yaml"):
    """Sortiert alle Märkte alphabetisch nach 'name' und speichert als neue YAML-Datei."""

    # 1️⃣ Sicherstellen, dass die Eingabedatei existiert
    if not os.path.exists(input_file):
        print(f"[FEHLER] Datei nicht gefunden: {input_file}")
        return

    # 2️⃣ Datei laden
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        print(f"[FEHLER] Konnte YAML-Datei nicht lesen: {e}")
        return

    if not isinstance(data, dict) or "markets" not in data:
        print("[FEHLER] Kein 'markets:'-Abschnitt in der Datei gefunden.")
        return

    markets = data["markets"]
    sorted_markets = {}

    # 3️⃣ Jede Marktgruppe (z. B. DAX, MDAX, OANDA_CURRENCY) einzeln sortieren
    for market_name, entries in markets.items():
        if not isinstance(entries, list):
            sorted_markets[market_name] = entries
            continue

        # Nach 'name' alphabetisch sortieren, falls vorhanden
        sorted_entries = sorted(entries, key=lambda x: x.get("name", "").lower())

        # Optional: Doppelte Symbole entfernen (nur erstes Vorkommen behalten)
        seen_symbols = set()
        unique_entries = []
        for entry in sorted_entries:
            symbol = entry.get("symbol")
            if symbol and symbol not in seen_symbols:
                unique_entries.append(entry)
                seen_symbols.add(symbol)

        sorted_markets[market_name] = unique_entries

    # 4️⃣ Neues Dictionary zurückschreiben
    data["markets"] = sorted_markets

    try:
        with open(output_file, "w", encoding="utf-8") as f:
            yaml.dump(data, f, sort_keys=False, allow_unicode=True)
        print(f"[OK] Sortierte Datei wurde erstellt: {output_file}")
    except Exception as e:
        print(f"[FEHLER] Konnte sortierte Datei nicht schreiben: {e}")


if __name__ == "__main__":
    sort_markets()
