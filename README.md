# Divergenzen-Scanner

Ein Python-Tool zur automatisierten Erkennung von Bullish- und Bearish-Divergenzen zwischen Kurs und RSI in verschiedenen Märkten (z. B. Aktienindizes, OANDA-Instrumente). Die Analyse und Visualisierung erfolgt interaktiv über die Konsole.

## Features

- **Automatische Marktdatenbeschaffung** von OANDA und Yahoo Finance
- **Divergenz-Erkennung** (RSI/Preis) nach TradingView-Logik
- **Interaktive Auswahl** von Märkten, Symbolen und Zeitrahmen
- **Visualisierung**: Candlestick-Charts mit markierten Divergenzen
- **Konfigurierbar** über YAML-Dateien

## Projektstruktur

```
main.py
config/
    config.yaml
    get_all_markets.py
    markets.yaml
    sort_markets_yaml.py
modules/
    divergence_detector.py
    rsi_wilder.py
utils/
    chart/plotter.py
    daten/data_loader.py
```

## Einstiegspunkt

Starte das Tool mit:

```bash
python main.py
```

## Konfiguration

- Die Datei `config/config.yaml` enthält alle Einstellungen (z. B. OANDA-API, Divergenz-Parameter, Märkte).
- Märkte werden in `config/markets.yaml` gepflegt (automatisch generierbar mit `get_all_markets.py`).

## Abhängigkeiten

Alle benötigten Pakete findest du in `requirements.txt`. Installation z. B. mit:

```bash
pip install -r requirements.txt
```

## Beispielablauf

1. **Markt und Symbol wählen** (interaktiv)
2. **Zeitrahmen wählen** (z. B. H4, D1)
3. **Analyse und Chartanzeige** mit markierten Divergenzen

## Hinweise

- OANDA-API-Zugangsdaten müssen in `config.yaml` hinterlegt werden.
- Die Visualisierung benötigt eine grafische Oberfläche (matplotlib).
