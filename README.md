# Divergenzen-Scanner

Ein Python-Tool zur Erkennung von Bullish- und Bearish-Divergenzen (Preis vs. RSI) sowie zum Finden von SMA-Korrekturen in verschiedenen Märkten (z. B. OANDA-Instrumente und Aktienindizes via Yahoo Finance). Steuerung und Auswahl erfolgen interaktiv über die Konsole; Charts werden angezeigt oder bei fehlendem GUI-Backend automatisch gespeichert.

## Features

- Datenquellen: OANDA und Yahoo Finance (yfinance)
- Divergenz-Erkennung (RSI nach Wilder/TradingView-Logik) mit Fraktal-Pivots
- Interaktive Auswahl von Märkten, Symbolen und Zeitrahmen (H4, D1)
- SMA-Korrektur-Scan: Schlusskurs über SMA lang, aber unter SMA kurz
- Candlestick-Visualisierung inkl. markierter Divergenzen und RSI (30/70)
- Konfigurierbar über YAML (`config/config.yaml`, `config/markets.yaml`)

## Projektstruktur

```
main.py
config/
  config.yaml
  markets.yaml
  get_all_markets.py
  sort_markets_yaml.py
modules/
  divergence_detector.py
  rsi_wilder.py
  sma_korrekturen_finden.py
utils/
  chart/plotter.py
  daten/data_loader.py
requirements.txt
```

## Installation

- Python 3.10+ empfohlen
- Abhängigkeiten installieren:

```bash
pip install -r requirements.txt
```

Hinweis: Für das Skript `config/get_all_markets.py` wird zusätzlich `pytickersymbols` benötigt:

```bash
pip install pytickersymbols
```

## Konfiguration

Die Datei `config/config.yaml` steuert Verhalten, Quellen und Parameter. Wichtige Schlüssel:

- `settings.timeframe`: Standard-Zeitrahmen (`H4` oder `D1`)
- `settings.timeframe_choices`: Optional, Liste zur Anzeige in der Auswahl
- `settings.default_source`: `yfinance` (Standard) oder `oanda`
- `settings.markets_file`: Pfad zur Märkte-Datei (z. B. `config/markets.yaml`)
- `oanda.access_token` und `oanda.account_id`: Zugangsdaten für OANDA
- `divergence`:
  - `rsi_period`: RSI-Periode (Standard 14)
  - `fractal_periods`: Fraktal-Fenstergröße (Standard 4)
  - `max_bars_diff`: Maximale Balkenanzahl zwischen Pivot-Paaren
- `SMA.langfristig` / `SMA.kurzfristig`: Perioden für SMA-Korrektur-Scan
- `auswertung.maximal_bars`: Anzahl letzter Bars für die Zusammenfassung

Beispiel (Platzhalter, bitte eigene Werte eintragen):

```
settings:
  timeframe: D1
  default_source: yfinance
  markets_file: config/markets.yaml
SMA:
  langfristig: 200
  kurzfristig: 25
oanda:
  access_token: "<DEIN_OANDA_TOKEN>"
  account_id: "<DEINE_OANDA_ACCOUNT_ID>"
divergence:
  rsi_period: 14
  fractal_periods: 4
  max_bars_diff: 30
auswertung:
  maximal_bars: 200
```

Sicherheit: Lege keine echten Zugangsdaten in Git-Repositories ab. Nutze lokale, ignorierte Konfigurationsdateien oder Umgebungsvariablen. (Der aktuelle Code liest die Werte aus `config/config.yaml`.)

## Märkte-Datei (`config/markets.yaml`)

Struktur: `markets` ist ein Mapping von Markt-Namen zu Listen von Einträgen mit `symbol`, optional `name` und `source` (`yfinance` oder `oanda`). Beispiel:

```
markets:
  OANDA_CURRENCY:
    - symbol: EUR_USD
      source: oanda
      name: EUR/USD
  DAX:
    - symbol: SAP.DE
      source: yfinance
      name: SAP SE
```

- Erzeugen/aktualisieren: `python config/get_all_markets.py` (OANDA via API, Indizes via pytickersymbols)
- Sortieren (nur Ausgabe in neue Datei): `python config/sort_markets_yaml.py`

## Nutzung

Tool starten:

```bash
python main.py
```

Interaktive Modi in `main.py`:

- Einzelnen Wert analysieren: Markt → Symbol → Zeitrahmen → Chart mit markierten Divergenzen
- Märkte scannen: Auswahl von Märkten und Zeitrahmen, dann Modus wählen:
  - Divergenzen finden: Ausgabe einer Trefferliste; Charts werden nacheinander geöffnet/gespeichert
  - SMA Korrekturen finden: Treffer, bei denen Schlusskurs > SMA lang und < SMA kurz; Charts inkl. Divergenz-Markierungen

## Daten und Zeitrahmen

- Unterstützte Zeitrahmen: `H4` und `D1`
- Yahoo Finance: automatische Begrenzung der Historie je Intervall; Startdatum wird anhand eines festen Fensters gewählt
- OANDA: Download per `oandapyV20` (Zugangsdaten erforderlich)

## Visualisierung und Ausgabe

- Interaktive Anzeige mit Matplotlib; RSI (0–100) mit 30/70-Linien
- Bei fehlendem GUI-Backend werden Charts automatisch unter `output/charts` als PNG gespeichert
- SMAs aus Daten (`SMA20`, `SMA200`, ...) werden, wenn vorhanden, mit geplottet

## Hinweise und Grenzen

- Nur `H4` und `D1` werden unterstützt
- Für OANDA ist ein gültiges `access_token` und `account_id` nötig
- `config/get_all_markets.py` benötigt zusätzlich `pytickersymbols`
- Ergebnisse dienen der Analyseunterstützung und sind keine Handelsberatung

