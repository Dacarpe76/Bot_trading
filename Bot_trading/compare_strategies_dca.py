
import sys
import os
import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt
from datetime import datetime
import warnings

# Suppress pandas warnings
warnings.simplefilter(action='ignore', category=FutureWarning)

# Add path to Bot_trader
sys.path.append(os.path.join(os.getcwd(), 'Bot_trader'))
try:
    import bot_config
    from data_loader import MarketData
    from strategy import Strategy as MacroStrategy
    from policy import Policy
except ImportError:
    pass # Will handle if modules missing

# --- CONFIGURATION ---
START_DATE = "2020-01-01"
INITIAL_CAPITAL = 500.0
MONTHLY_CONTRIBUTION = 50.0

class BacktestEngine:
    def __init__(self):
        self.market = MarketData()
        self.macro_strategy = MacroStrategy()
        self.macro_policy = Policy()
        
    def fetch_all_data(self):
        print("📥 Fetching Data...")
        start_dt = pd.to_datetime(START_DATE) - pd.Timedelta(days=365) # For indicators
        start_str = start_dt.strftime("%Y-%m-%d")
        
        # 1. Base Market Data (BTC, Gold) from shared loader
        # NOTE: MarketData usually fetches BTC/USD and XAU/USD
        hist_data = self.market.get_market_data(start_date=start_str)
        hist_data = self.macro_strategy.calculate_indicators(hist_data) # Computes SMA200, MACD, etc.
        
        # 2. Additional Assets for Binance Strategy (ETH, SOL, PAXG, SPY)
        # Using yfinance for simplicity on these specific tickers
        tickers = {
            'ETH': 'ETH-USD',
            'SOL': 'SOL-USD',
            'PAXG': 'PAXG-USD',
            'SP500': '^GSPC' # S&P 500 Index
        }
        
        other_data = pd.DataFrame()
        
        for name, ticker in tickers.items():
            print(f"   Fetching {name} ({ticker})...")
            df = yf.download(ticker, start=start_str, progress=False)
            if df.empty:
                print(f"   ⚠️ Warning: No data for {name}")
                continue
            
            # Normalize YF data structure (Adj Close -> Close)
            if isinstance(df.columns, pd.MultiIndex):
                df = df['Adj Close'] if 'Adj Close' in df.columns else df['Close']
            else:
                 df = df['Adj Close'] if 'Adj Close' in df else df['Close']
            
            # If it's a Series, name it.
            if isinstance(df, pd.Series):
                df.name = f"{name}_Close"
                other_strats_df = df.to_frame()
            else:
                other_strats_df = df.rename(columns={ticker: f"{name}_Close"})
                
            # If columns still not right (check multi-symbol download behavior)
            if len(other_strats_df.columns) == 1:
                other_strats_df.columns = [f"{name}_Close"]
                
            other_data = other_data.join(other_strats_df, how='outer')

        # 3. Macro Indicators (PMI, DXY, VIX, F&G)
        # Assuming MarketData has logic or we use yfinance/custom for DXY/VIX
        # PMI is tricky, let's try to load from MarketData or fill default
        pmi_series = self.market.get_pmi_data_fred(start_date=start_str, end_date=datetime.now().strftime("%Y-%m-%d"))
        
        # Join all
        # Use hist_data index as master? No, use outer join of all
        
        full_df = hist_data.join(other_data, how='outer')
        if not pmi_series.empty:
             full_df['PMI'] = full_df.index.map(lambda d: pmi_series.loc[d]['PMI'] if d in pmi_series.index else np.nan)
        else:
             full_df['PMI'] = np.nan
             
        full_df['PMI'] = full_df['PMI'].ffill().fillna(50.0)
        
        # DXY & VIX from YFinance if not in MarketData
        if 'VIX' not in full_df.columns:
             vix = yf.download("^VIX", start=start_str, progress=False)
             if isinstance(vix, pd.DataFrame):
                 vix = vix['Close'] if 'Close' in vix.columns else vix.iloc[:, 0]
             vix.name = "VIX"
             full_df = full_df.join(vix, how='left')
             
        if 'DXY' not in full_df.columns:
             dxy = yf.download("DX-Y.NYB", start=start_str, progress=False)
             if isinstance(dxy, pd.DataFrame):
                 dxy = dxy['Close'] if 'Close' in dxy.columns else dxy.iloc[:, 0]
             dxy.name = "DXY"
             full_df = full_df.join(dxy, how='left')
             
        # Fear & Greed: Hard to get historical for free easily without CSV.
        # We will simulate F&G using Volatility/RSI proxy for backtest or just VIX.
        # Proxy: If VIX > 30 -> Fear (20), If VIX < 15 -> Greed (70)
        # This is a simplification.
        
        # DEBUG PRINTS
        print(f"   Indices match check: Hist {hist_data.index[0]} vs VIX {vix.index[0] if 'vix' in locals() and not vix.empty else 'N/A'}")
        print(f"   Full DF columns: {full_df.columns}")
        
        full_df['FNG_PROXY'] = 50 
        if 'VIX' in full_df.columns:
            full_df.loc[full_df['VIX'] > 25, 'FNG_PROXY'] = 25 # Extreme Fear
            full_df.loc[full_df['VIX'] < 15, 'FNG_PROXY'] = 75 # Greed
        elif '^VIX' in full_df.columns:
            full_df.rename(columns={'^VIX': 'VIX'}, inplace=True)
            full_df.loc[full_df['VIX'] > 25, 'FNG_PROXY'] = 25 
            full_df.loc[full_df['VIX'] < 15, 'FNG_PROXY'] = 75
        else:
            print("   ⚠️ VIX column missing! Defaulting F&G Proxy to 50.")
            
        if 'DX-Y.NYB' in full_df.columns:
             full_df.rename(columns={'DX-Y.NYB': 'DXY'}, inplace=True)
        
        # Fill NAs
        full_df.ffill(inplace=True)
        full_df.fillna(method='bfill', inplace=True)
        
        # Trim to start date
        full_df = full_df.loc[START_DATE:]
        return full_df

class StrategyRunner:
    def __init__(self, name, start_capital):
        self.name = name
        self.cash = start_capital
        self.holdings = {} # {asset: amount}
        self.avg_buy = {} # {asset: price}
        self.portfolio_history = []
        self.total_invested = start_capital
        self.trade_log = []

    def inject_capital(self, amount, price_map):
        self.cash += amount
        self.total_invested += amount
        if self.portfolio_history:
             self.portfolio_history[-1]['invested'] = self.total_invested 

    def get_value(self, prices):
        val = self.cash
        for asset, amt in self.holdings.items():
            price = prices.get(f"{asset}_Close", 0)
            val += amt * price
        return val

    def record(self, date, prices):
        val = self.get_value(prices)
        self.portfolio_history.append({
            'date': date,
            'equity': val,
            'invested': self.total_invested
        })

class KrakenRunner(StrategyRunner):
    def __init__(self, start_capital, strategy, policy):
        super().__init__("Kraken (Macro)", start_capital)
        self.strategy = strategy
        self.policy = policy
        # Initialize default avg_buy keys to avoid KeyError in Policy
        self.avg_buy = {'BTC': 0, 'GOLD': 0}
        
    def on_day(self, date, row):
        # 1. Prepare Data
        # Map DB columns to Strategy expected keys
        current_prices = {
            'BTC': row.get('BTC_Close', 0), 
            'GOLD': row.get('GOLD_Close', 0)
        }
        
        if current_prices['BTC'] == 0: return # Skip if no data
        
        pmi = row.get('PMI', 50)
        tips = row.get('TIPS', 1.0) # Might be missing, ignore logic for now if so
        vix = row.get('VIX', 20)
        
        # 2. Get Logic
        # Adapting MultiBacktest logic
        # StandardStrategy.get_signal expects a row with indicators
        # We need to ensure 'row' has what strategy needs (MACD, RSI...)
        
        raw_signal = self.strategy.get_signal(row, pmi)
        regimen = self.policy.detectar_regimen(pmi, tips, vix)
        
        decision = self.policy.aplicar_politica(
            raw_weights=raw_signal,
            current_prices=current_prices,
            holdings=self.holdings,
            avg_prices=self.avg_buy,
            regimen=regimen
        )
        
        # 3. Rebalance (Simplified Rebalance Logic)
        # Policy gives us target weights (e.g. BTC 0.6, GOLD 0.4, CASH 0.0)
        # But 'holdings' in policy includes cash calc.
        
        total_val = self.get_value({k+'_Close': v for k,v in current_prices.items()})
        
        for asset, target_weight in [('BTC', decision.get('btc_weight', 0)), ('GOLD', decision.get('gold_weight', 0))]:
            target_val = total_val * target_weight
            price = current_prices[asset]
            if price == 0: continue
            
            current_amt = self.holdings.get(asset, 0)
            current_asset_val = current_amt * price
            diff = target_val - current_asset_val
            
            # Threshold 5 EUR
            if abs(diff) < 5: continue
            
            if diff > 0:
                # Buy
                if self.cash >= diff:
                    amt = diff / price
                    self.cash -= diff
                    self.holdings[asset] = current_amt + amt
                    
                    # Update Avg Buy
                    old_cost = self.avg_buy.get(asset, 0) * current_amt
                    new_cost = old_cost + diff
                    self.avg_buy[asset] = new_cost / (current_amt + amt)
            else:
                # Sell
                sell_val = abs(diff)
                amt = sell_val / price
                if current_amt >= amt:
                    self.holdings[asset] = current_amt - amt
                    self.cash += sell_val
        

class BinanceRunner(StrategyRunner):
    def __init__(self, start_capital):
        super().__init__("Binance (5 Cubes)", start_capital)
        
    def on_day(self, date, row):
        # 1. Indicators
        price_btc = row.get('BTC_Close', 0)
        sma200 = row.get('BTC_SMA_200', 0)
        fng = row.get('FNG_PROXY', 50)
        dxy = row.get('DXY', 100)
        pmi = row.get('PMI', 50)
        
        prices = {
            'BTC': price_btc,
            'ETH': row.get('ETH_Close', 0),
            'SOL': row.get('SOL_Close', 0),
            'PAXG': row.get('PAXG_Close', 0)
        }
        
        # If BTC is 0, we can't do anything
        if price_btc == 0: return

        # 2. Determine Mode
        mode = "SHIELD"
        
        # Bear Shield (Priority 1)
        if sma200 > 0 and price_btc < sma200:
            mode = "BEAR_SHIELD"
            targets = {'PAXG': 0.70, 'USDT': 0.30, 'BTC': 0.0, 'ETH': 0.0, 'SOL': 0.0}
        
        else:
            # Logic: Attack/Cruise/Shield
            if fng < 30: # Fear -> Attack
                mode = "ATTACK"
                targets = {'SOL': 0.40, 'ETH': 0.30, 'BTC': 0.30, 'PAXG': 0.0, 'USDT': 0.0}
            elif dxy < 103 and pmi > 50:
                mode = "CRUISE"
                targets = {'BTC': 0.40, 'ETH': 0.30, 'SOL': 0.30, 'PAXG': 0.0, 'USDT': 0.0}
            else:
                mode = "SHIELD"
                targets = {'BTC': 0.40, 'PAXG': 0.40, 'USDT': 0.20, 'ETH': 0.0, 'SOL': 0.0}
        
        # 3. Calculate Trades
        # Total Value (Cash is USDT)
        val = self.get_value({k+'_Close': v for k,v in prices.items()})
        
        # --- ZERO LOSS LOGIC check ---
        # If we need to sell crypto (BTC/ETH/SOL), check if Price < AvgBuy.
        # EXCEPTION: If mode is BEAR_SHIELD, we sell anyway (Panic/Protection).
        
        is_bear_defensive = (mode == 'BEAR_SHIELD')
        
        # We need to process SELLS first to free cash
        # Then BUYS.
        
        # Use a temporary holdings map to calculate changes
        # But wait, we iterate targets.
        
        # Simple Loop: Calculate diffs
        # Warning: If we can't sell due to ZeroLoss, we might not have cash to Buy.
        # So effective weights will drift. That is acceptable for ZeroLoss strategy.
        
        for asset, weight in targets.items():
            if asset == 'USDT': continue # Cash
            
            target_val = val * weight
            price = prices.get(asset, 0)
            if price == 0: continue # Asset not active yet (e.g. SOL in early 2020)
            
            current_amt = self.holdings.get(asset, 0)
            current_val = current_amt * price
            diff = target_val - current_val
            
            if abs(diff) < 5: continue
            
            if diff < 0:
                # SELL
                # Zero Loss Check
                avg = self.avg_buy.get(asset, 0)
                if not is_bear_defensive and avg > 0 and price < avg:
                    # HOLD
                    continue
                
                sell_val = abs(diff)
                sell_amt = sell_val / price
                self.holdings[asset] = max(0, current_amt - sell_amt)
                self.cash += sell_val
                
        # Now BUYS (Second Pass to use freed cash)
        # Recalculate Cash? No, simple accumulation.
        for asset, weight in targets.items():
             if asset == 'USDT': continue
             
             target_val = val * weight
             price = prices.get(asset, 0)
             if price == 0: continue
             
             current_amt = self.holdings.get(asset, 0)
             current_val = current_amt * price
             diff = target_val - current_val
             
             if diff > 5:
                 # BUY
                 if self.cash >= diff:
                     amt = diff / price
                     self.cash -= diff
                     self.holdings[asset] = current_amt + amt
                     
                     # Update Avg
                     old_cost = self.avg_buy.get(asset, 0) * current_amt
                     new_cost = old_cost + diff
                     self.avg_buy[asset] = new_cost / (current_amt + amt)

class SP500Runner(StrategyRunner):
    def __init__(self, start_capital):
        super().__init__("S&P 500 (Passive)", start_capital)
        
    def on_day(self, date, row):
        # Simply buy SP500 with all available cash
        price = row.get('SP500_Close', 0)
        if price == 0: return
        
        if self.cash > 1:
            amt = self.cash / price
            current_amt = self.holdings.get('SP500', 0)
            self.holdings['SP500'] = current_amt + amt
            self.cash = 0
            
            # Avg buy (simple)
            old_cost = self.avg_buy.get('SP500', 0) * current_amt
            new_cost = old_cost + (amt * price)
            self.avg_buy['SP500'] = new_cost / (current_amt + amt)

# --- EXECUTION ---
def run_comparison():
    engine = BacktestEngine()
    data = engine.fetch_all_data()
    
    # Initialize Runners
    kraken = KrakenRunner(INITIAL_CAPITAL, engine.macro_strategy, engine.macro_policy)
    binance = BinanceRunner(INITIAL_CAPITAL)
    sp500 = SP500Runner(INITIAL_CAPITAL)
    
    runners = [kraken, binance, sp500]
    
    # Iterate
    prev_month = None
    
    print(f"🚀 Running Simulation: {initial_capital}€ Start + {monthly_contribution}€/Month")
    
    for date, row in data.iterrows():
        # DCA Logic: Check for new month
        curr_month = date.month
        if prev_month is not None and curr_month != prev_month:
            # Inject Capital
            for r in runners:
                r.inject_capital(MONTHLY_CONTRIBUTION, {})
        prev_month = curr_month
        
        # Run Strategy
        for r in runners:
            r.on_day(date, row)
            r.record(date, row)
            
    # --- REPORTING ---
    final_stats = []
    
    plt.figure(figsize=(12, 6))
    
    for r in runners:
        df = pd.DataFrame(r.portfolio_history)
        if df.empty: continue
        
        df.set_index('date', inplace=True)
        final_val = df.iloc[-1]['equity']
        invested = df.iloc[-1]['invested']
        pnl = final_val - invested
        roi = (pnl / invested) * 100
        
        final_stats.append({
            'Strategy': r.name,
            'Final Equity': final_val,
            'Total Invested': invested,
            'PnL': pnl,
            'ROI %': roi
        })
        
        plt.plot(df.index, df['equity'], label=f"{r.name} (ROI: {roi:.1f}%)")
        
        # Save CSV
        df.to_csv(f"results_{r.name.split()[0].lower()}.csv")
        
    # Add 'Total Invested' line
    # Just take from one runner
    df_inv = pd.DataFrame(runners[0].portfolio_history)
    df_inv.set_index('date', inplace=True)
    plt.plot(df_inv.index, df_inv['invested'], 'k--', alpha=0.5, label='Total Invested')
        
    plt.title(f"Strategy Comparison (DCA {MONTHLY_CONTRIBUTION}€/mo)")
    plt.ylabel("Portfolio Value (€)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.savefig("strategy_comparison_dca.png")
    print("\n✅ Simulation Complete. Chart saved to 'strategy_comparison_dca.png'")
    
    # Print Table
    res_df = pd.DataFrame(final_stats)
    print("\n" + res_df.to_string(index=False))

if __name__ == "__main__":
    # Fix global variable usage inside function by defining them or passing
    initial_capital = INITIAL_CAPITAL
    monthly_contribution = MONTHLY_CONTRIBUTION
    run_comparison()
