import ccxt
import pandas as pd
import yfinance as yf
import requests
import time
import datetime
import json
import os
import config

# --- CONSTANTS ---
MODES = {
    'ATTACK': {'SOL': 0.40, 'ETH': 0.30, 'BTC': 0.30, 'PAXG': 0.0, 'STABLE': 0.0},
    'CRUISE': {'BTC': 0.40, 'ETH': 0.30, 'SOL': 0.30, 'PAXG': 0.0, 'STABLE': 0.0},
    'SHIELD': {'BTC': 0.40, 'ETH': 0.0, 'SOL': 0.0, 'PAXG': 0.40, 'STABLE': 0.20}
}
STATE_FILE = "portfolio_state.json"

class FiveCubesBot:
    def __init__(self):
        self.exchange = ccxt.binance({
            'apiKey': config.API_KEY,
            'secret': config.SECRET_KEY,
            'enableRateLimit': True,
        })
        self.mode = "UNKNOWN"
        self.indicators = {}
        self.state = self.load_state()
        self.portfolio = {}

    def load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading state: {e}")
        return {'avg_buy_price': {}}

    def save_state(self):
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump(self.state, f, indent=4)
        except Exception as e:
            print(f"Error saving state: {e}")

    def get_portfolio(self):
        """Fetches current balances and normalizes to USD value."""
        # 1. Sweep EUR if needed (Simulated or Real)
        # self.sweep_eur_to_stable() # Implement later in Execution phase

        print("Fetching portfolio...")
        try:
            # fetchBalance is unified in CCXT
            balance = self.exchange.fetch_balance()
            
            # Extract relevant assets
            assets = ['BTC', 'ETH', 'SOL', 'PAXG', config.STABLECOIN]
            total_value = 0
            self.portfolio = {}

            # Create a list oftickers to fetch prices for
            # Note: CCXT fetch_tickers might be efficient
            tickers_to_fetch = [config.BTC_SYMBOL, config.ETH_SYMBOL, config.SOL_SYMBOL, config.PAXG_SYMBOL]
            prices = self.exchange.fetch_tickers(tickers_to_fetch)

            for asset in assets:
                amount = balance['total'].get(asset, 0.0)
                usd_value = 0.0
                
                if asset == config.STABLECOIN:
                    usd_value = amount # 1:1 roughly
                    price = 1.0
                else:
                    symbol = f"{asset}/{config.STABLECOIN}"
                    if symbol in prices:
                        price = prices[symbol]['last']
                        usd_value = amount * price
                    else:
                        print(f"Price not found for {asset}")
                        price = 0

                self.portfolio[asset] = {
                    'amount': amount,
                    'usd_value': usd_value,
                    'price': price
                }
                total_value += usd_value

            self.portfolio['total_usd'] = total_value
            print(f"Portfolio Status: Total Value = ${total_value:.2f}")
            for asset in assets:
                 data = self.portfolio.get(asset, {})
                 print(f"  - {asset}: {data.get('amount', 0):.4f} (${data.get('usd_value', 0):.2f})")

        except Exception as e:
            print(f"Error fetching portfolio: {e}")
            # Mock portfolio for dry run or error handling
            self.portfolio = {'total_usd': 0}


    def fetch_indicators(self):
        """Fetches Fear&Greed, DXY, and PMI."""
        print("Fetching indicators...")
        
        # 1. Fear & Greed
        try:
            fng_response = requests.get("https://api.alternative.me/fng/?limit=1")
            fng_data = fng_response.json()
            self.indicators['fng'] = int(fng_data['data'][0]['value'])
            print(f"Fear & Greed Index: {self.indicators['fng']}")
        except Exception as e:
            print(f"Error fetching Fear & Greed: {e}")
            self.indicators['fng'] = 50 # Default neutral

        # 2. DXY (Dollar Index)
        try:
            dxy_ticker = yf.Ticker("DX-Y.NYB")
            # Get the last closing price
            dxy_history = dxy_ticker.history(period="5d")
            if not dxy_history.empty:
                self.indicators['dxy'] = dxy_history['Close'].iloc[-1]
                print(f"DXY Index: {self.indicators['dxy']:.2f}")
            else:
                 # Fallback if ticker symbol is wrong or data missing
                 print("DXY data empty, trying 'DX=F' (Futures)")
                 dxy_ticker = yf.Ticker("DX=F")
                 dxy_history = dxy_ticker.history(period="5d")
                 self.indicators['dxy'] = dxy_history['Close'].iloc[-1]
                 print(f"DXY Index (Futures): {self.indicators['dxy']:.2f}")

        except Exception as e:
            print(f"Error fetching DXY: {e}")
            self.indicators['dxy'] = 100.0 # Default neutral/safe

        # 3. US Manufacturing PMI
        # Defensive default as APIs are tricky
        self.indicators['pmi'] = 50.1 # Placeholder: "Growth"
        print(f"US Manufacturing PMI: {self.indicators['pmi']} (Placeholder)")
    
    def determine_mode(self):
        """Decides the mode based on indicators."""
        fng = self.indicators.get('fng', 50)
        dxy = self.indicators.get('dxy', 100)
        pmi = self.indicators.get('pmi', 50)
        
        print(f"Analyzing Market Conditions: F&G={fng}, DXY={dxy}, PMI={pmi}")

        # LOGIC
        if fng < config.FEAR_AND_GREED_THRESHOLD:
            self.mode = "ATTACK"
        elif dxy < config.DXY_THRESHOLD and pmi > config.PMI_THRESHOLD:
            self.mode = "CRUISE"
        else:
            self.mode = "SHIELD" # Default defensive if DXY is high or PMI is low

        print(f"Selected Mode: {self.mode}")
        return self.mode
    
    def calculate_rebalance(self):
        """Calculates trades to align portfolio with target mode."""
        if self.mode == "UNKNOWN":
            print("Mode unknown, cannot rebalance.")
            return []

        print(f"Calculating rebalance for mode: {self.mode}...")
        target_ratios = MODES[self.mode]
        total_value = self.portfolio.get('total_usd', 0)
        
        if total_value == 0:
            print("Portfolio empty or error fetching.")
            return []

        trades = []
        
        # We need to process SELLS first to free up USDT, then BUYS?
        # Or just calculate difference and let execution handle order.
        # Ideally, generate a list of Desired Changes.
        
        for asset, target_pct in target_ratios.items():
            if asset == 'STABLE': continue # Handled implicitely by the rest
            
            target_usd = total_value * target_pct
            current_data = self.portfolio.get(asset, {'usd_value': 0, 'amount': 0, 'price': 0})
            current_usd = current_data.get('usd_value', 0)
            price = current_data.get('price', 0)
            
            if price == 0:
                print(f"Skipping {asset}, no price.")
                continue

            diff_usd = target_usd - current_usd
            
            # Simple threshold to avoid dust trades (e.g. $10)
            if abs(diff_usd) < 10: 
                continue

            amount_diff = diff_usd / price
            symbol = f"{asset}/{config.STABLECOIN}"
            
            if diff_usd < 0:
                # SELLING
                # Zero Loss Check
                avg_buy = self.state.get('avg_buy_price', {}).get(asset, 0)
                
                # Rule: "No vender ... en pérdidas ... a menos que sea necesario para rebalanceo defensivo"
                # "Defensive Rebalancing" = Entering SHIELD mode.
                is_defensive = (self.mode == 'SHIELD')
                
                if avg_buy > 0 and price < avg_buy and not is_defensive:
                    print(f"ZERO LOSS PROTECTION: Holding {asset} despite target. Current: {price}, Buy: {avg_buy}")
                    continue 
                
                trades.append({
                    'symbol': symbol,
                    'side': 'sell',
                    'amount': abs(amount_diff),
                    'usd_value': abs(diff_usd),
                    'asset': asset
                })

            elif diff_usd > 0:
                # BUYING
                trades.append({
                    'symbol': symbol,
                    'side': 'buy',
                    'amount': abs(amount_diff),
                    'usd_value': abs(diff_usd),
                    'asset': asset
                })
        
        # Sort sells before buys to ensure liquidity? 
        # Actually proper execution handles this, but a list is fine.
        print(f"Rebalance Trades Calculated: {len(trades)}")
        for t in trades:
            print(f" - {t['side'].upper()} {t['symbol']}: {t['amount']:.4f} (${t['usd_value']:.2f})")
            
        return trades

    def sweep_eur_to_stable(self):
        """Converts any EUR balance to STABLECOIN."""
        try:
            # If using mock exchange, simulate balance
            if getattr(self, 'is_mock', False):
                 eur_balance = 0
            else:
                 balance = self.exchange.fetch_balance()
                 eur_balance = balance['total'].get('EUR', 0)

            if eur_balance > 5: # Threshold to avoid dust
                print(f"Sweeping {eur_balance:.2f} EUR to {config.STABLECOIN}...")
                symbol = f"EUR/{config.STABLECOIN}"
                if config.DRY_RUN:
                    print(" [DRY RUN] Would SELL EUR/USDT market.")
                else:
                    self.exchange.create_market_sell_order(symbol, eur_balance)
                    print("Sweep executed.")
        except Exception as e:
            print(f"Error sweeping EUR: {e}")

    def execute_trades(self, trades):
        """Executes the calculated trades."""
        if not trades:
            print("No trades to execute.")
            return

        print("Executing trades...")
        # Execute Sells first
        sells = [t for t in trades if t['side'] == 'sell']
        buys = [t for t in trades if t['side'] == 'buy']
        
        for trade in sells + buys:
            symbol = trade['symbol']
            side = trade['side']
            amount = trade['amount']
            asset = trade['asset']
            
            print(f" >>> {side.upper()} {amount:.5f} {symbol}")
            
            if config.DRY_RUN:
                print(" [DRY RUN] Order skipped.")
                # Simulate state update for Dry Run logic verification if needed
                continue
                
            try:
                # Execute Order
                order = self.exchange.create_order(symbol, 'market', side, amount)
                print(f"Order executed: {order['id']}")
                
                # Update Average Buy Price
                if side == 'buy':
                    # Calculate new weighted average
                    current_avg = self.state.get('avg_buy_price', {}).get(asset, 0)
                    current_qty = self.portfolio.get(asset, {}).get('amount', 0)
                    # Note: portfolio amount is BEFORE this trade.
                    
                    price = order.get('average', trade['usd_value']/amount) # fallback
                    
                    if current_qty + amount > 0:
                        new_avg = ((current_avg * current_qty) + (price * amount)) / (current_qty + amount)
                        if 'avg_buy_price' not in self.state: self.state['avg_buy_price'] = {}
                        self.state['avg_buy_price'][asset] = new_avg
                        self.save_state()
                        print(f"Updated Avg Buy Price for {asset}: {new_avg:.2f}")

            except Exception as e:
                print(f"Order failed: {e}")
                
    def run(self):
        print("--- 5 Cubes Bot Starting ---")
        if config.API_KEY == 'YOUR_BINANCE_API_KEY': # Default placeholder
             print("!!! WARNING: API KEYS NOT SET. USING MOCK EXCHANGE !!!")
             self.is_mock = True
             # Mock Portfolio
             self.portfolio = {
                 'total_usd': 5000,
                 'BTC': {'amount': 0.1, 'usd_value': 4000, 'price': 40000},
                 'USDT': {'amount': 1000, 'usd_value': 1000, 'price': 1},
                 'ETH': {'amount': 0, 'usd_value': 0, 'price': 2200},
                 'SOL': {'amount': 0, 'usd_value': 0, 'price': 90},
                 'PAXG': {'amount': 0, 'usd_value': 0, 'price': 2000}
             }
             print("Mock Portfolio Loaded.")
        
        if config.DRY_RUN:
            print("!!! DRY RUN MODE ACTIVE !!!")
        
        # 1. Sweep EUR
        self.sweep_eur_to_stable()
        
        # 2. Analyze Market
        self.fetch_indicators()
        self.determine_mode()
        
        # 3. Get Portfolio (only if not mocked)
        if not getattr(self, 'is_mock', False):
            self.get_portfolio()
        
        # 4. Calculate & Execute
        trades = self.calculate_rebalance()
        self.execute_trades(trades)
        
        print("--- Routine Finished ---")

if __name__ == "__main__":
    bot = FiveCubesBot()
    bot.run()
