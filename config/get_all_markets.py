import oandapyV20
import oandapyV20.endpoints.accounts as accounts
from pytickersymbols import PyTickerSymbols
import yaml

"""
📄 get_all_markets.py

Erstellt automatisch die Datei `markets.yaml` mit Symbolen aus:
1. 🔐 OANDA (über API)
2. 📈 Yahoo Finance via pytickersymbols

Yahoo-Ticker erhalten automatisch das richtige Suffix wie `.DE`, `.PA`, `.AS` etc.
"""

# Konfiguration laden
with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)


# 📡 OANDA-Symbole
def get_oanda_markets():
    client = oandapyV20.API(access_token=config["oanda"]["access_token"])
    r = accounts.AccountInstruments(accountID=config["oanda"]["account_id"])
    resp = client.request(r)

    grouped = {"OANDA_CURRENCY": [], "OANDA_Indices": [], "OANDA_METAL": []}
    for inst in resp.get("instruments", []):
        eintrag = {
            "symbol": inst["name"],
            "source": "oanda",
            "name": inst["displayName"]
        }
        if inst["type"] == "CURRENCY":
            grouped["OANDA_CURRENCY"].append(eintrag)
        elif inst["type"] == "CFD":
            grouped["OANDA_Indices"].append(eintrag)
        elif inst["type"] == "METAL":
            grouped["OANDA_METAL"].append(eintrag)
    return grouped


# 📈 Suffix-Mapping für YFinance
YF_SUFFIX = {
    "DAX": ".DE",
    "MDAX": ".DE",
    "SDAX": ".DE",
    "TECDAX": ".DE",
    "AEX": ".AS",
    "CAC 40": ".PA",
    "BEL 20": ".BR",
    "FTSE 100": ".L",
    "IBEX 35": ".MC",
    "DOW JONES": "",
    "NASDAQ 100": "",
    "S&P 100": ""
}


def get_yf_markets():
    ts = PyTickerSymbols()
    indices = YF_SUFFIX.keys()
    result = {}

    for index in indices:
        print(f"📥 Lade lokale Daten für {index} ...")
        try:
            suffix = YF_SUFFIX[index]
            stocks = ts.get_stocks_by_index(index)
            result[index] = []

            for stock in stocks:
                symbol = stock.get("symbol")
                name = stock.get("name", symbol)

                if not symbol:
                    continue

                # Kein Suffix bei US-Symbolen
                if suffix and not symbol.endswith(suffix):
                    symbol += suffix

                result[index].append({
                    "symbol": symbol,
                    "source": "yfinance",
                    "name": name
                })

            print(f"✅ {index}: {len(result[index])} Symbole")
        except Exception as e:
            print(f"❌ Fehler bei {index}: {e}")
            result[index] = []

    return result


# 🏗 markets.yaml bauen
def build_markets_yaml():
    print("📡 Lade OANDA-Märkte ...")
    markets = get_oanda_markets()

    print("📊 Lade Aktien-Indizes von Yahoo Finance (lokal) ...")
    markets.update(get_yf_markets())

    with open("markets.yaml", "w", encoding="utf-8") as f:
        yaml.dump(markets, f, allow_unicode=True, sort_keys=False)

    print("\n✅ markets.yaml erfolgreich erstellt.")


if __name__ == "__main__":
    build_markets_yaml()
