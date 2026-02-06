import ccxt
import requests
import json
import config

def test_telegram():
    print("Testing Telegram connectivity...")
    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": config.MY_CHAT_ID,
        "text": "Hola. Sistema de Inversión Kraken iniciado. Conectividad verificada."
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        print(f"Telegram message sent successfully. Response: {response.json()}")
    except requests.exceptions.HTTPError as e:
        print(f"Error sending Telegram message: {e}")
        if e.response is not None:
             print(f"Response content: {e.response.text}")
    except Exception as e:
        print(f"Unexpected error: {e}")

def test_kraken():
    print("\nTesting Kraken connectivity and fetching prices...")
    try:
        kraken = ccxt.kraken({
            'apiKey': config.KRAKEN_API_KEY,
            'secret': config.KRAKEN_PRIVATE_KEY,
        })
        
        # Load markets
        kraken.load_markets()
        
        # Fetch tickers for BTC/EUR and PAXG/EUR (or PAXG/USD if EUR not available directly, 
        # but specs mention EUR/ISDC liquidity. Let's try standard pairs)
        # Checking BTC/EUR
        btc_ticker = kraken.fetch_ticker('BTC/EUR')
        print(f"BTC/EUR Price: {btc_ticker['last']} EUR")
        
        # Checking PAXG/EUR - If not available, might need PAXG/USD or XAU mappings
        # Kraken often uses XBT for BTC and sometimes specific codes for Gold. 
        # PAXG is Paxos Gold.
        try:
            paxg_ticker = kraken.fetch_ticker('PAXG/EUR')
            print(f"PAXG/EUR Price: {paxg_ticker['last']} EUR")
        except:
            print("PAXG/EUR pair not found directly, checking PAXG/USD...")
            paxg_ticker = kraken.fetch_ticker('PAXG/USD')
            print(f"PAXG/USD Price: {paxg_ticker['last']} USD")

    except Exception as e:
        print(f"Error connecting to Kraken: {e}")

if __name__ == "__main__":
    test_telegram()
    test_kraken()
