import pandas as pd
import yfinance as yf
import requests
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime, timedelta

# --- CONFIGURATION ---
START_DATE = "2020-01-01"
END_DATE = datetime.now().strftime("%Y-%m-%d")
INITIAL_CAPITAL = 500
MONTHLY_DCA = 100 # EUR/USD (Assuming parity for simplicity or just USD base)
FEE = 0.001 # 0.1% trading fee

# --- HISTORICAL PMI DATA (HARDCODED from search) ---
# Format: 'YYYY-MM': Value
PMI_DATA = {
    '2020-01': 50.9, '2020-02': 50.1, '2020-03': 49.1, '2020-04': 41.5, '2020-05': 43.1, '2020-06': 52.6,
    '2020-07': 54.2, '2020-08': 56.0, '2020-09': 55.4, '2020-10': 59.3, '2020-11': 57.5, '2020-12': 60.7,
    '2021-01': 58.7, '2021-02': 60.8, '2021-03': 64.7, '2021-04': 60.7, '2021-05': 61.2, '2021-06': 60.6,
    '2021-07': 60.8, '2021-08': 59.9, '2021-09': 61.1, '2021-10': 60.8, '2021-11': 61.1, '2021-12': 58.7,
    '2022-01': 57.6, '2022-02': 58.6, '2022-03': 57.1, '2022-04': 55.4, '2022-05': 55.4, '2022-06': 53.0,
    '2022-07': 52.8, '2022-08': 52.8, '2022-09': 50.9, '2022-10': 50.2, '2022-11': 49.0, '2022-12': 48.4,
    '2023-01': 47.4, '2023-02': 47.7, '2023-03': 46.3, '2023-04': 47.1, '2023-05': 46.9, '2023-06': 46.0,
    '2023-07': 46.4, '2023-08': 47.6, '2023-09': 49.0, '2023-10': 46.7, '2023-11': 49.4, '2023-12': 47.4,
    '2024-01': 49.1, '2024-02': 47.8, '2024-03': 50.3, '2024-04': 49.2, '2024-05': 48.7, '2024-06': 48.5,
    '2024-07': 46.8, '2024-08': 47.2, '2024-09': 47.2, '2024-10': 46.5, '2024-11': 48.4, '2024-12': 48.0, # Approx
    '2025-01': 48.0 # Approx/Carry forward
}

def get_historical_data():
    print("Fetching historical data...")
    
    # 1. Asset Prices
    tickers = ['BTC-USD', 'ETH-USD', 'SOL-USD', 'PAXG-USD', 'DX-Y.NYB', 'SPY']
    # Note: SOL data might be limited in early 2020 but should be fine. PAXG too.
    data = yf.download(tickers, start=START_DATE, end=END_DATE)['Close']
    
    # 2. Fear & Greed
    print("Fetching Fear & Greed history...")
    url = "https://api.alternative.me/fng/?limit=0"
    r = requests.get(url)
    fng_data = r.json()['data']
    fng_df = pd.DataFrame(fng_data)
    fng_df['timestamp'] = pd.to_datetime(fng_df['timestamp'], unit='s')
    fng_df.set_index('timestamp', inplace=True)
    fng_df = fng_df['value'].astype(int).sort_index()
    # Resample to daily to match yfinance (fill fwd just in case)
    fng_df = fng_df.resample('D').ffill()
    
    # Combine
    combined = data.copy()
    combined.index = pd.to_datetime(combined.index)
    
    # Merge F&G
    # We reindex F&G to match combined index
    combined['FNG'] = fng_df.reindex(combined.index, method='ffill')
    
    return combined

def backtest():
    df = get_historical_data()
    
    # Portfolio State
    holdings = {'BTC': 0, 'ETH': 0, 'SOL': 0, 'PAXG': 0, 'USDT': INITIAL_CAPITAL}
    avg_buy_prices = {'BTC': 0, 'ETH': 0, 'SOL': 0, 'PAXG': 0}
    cash_invested = INITIAL_CAPITAL
    
    # S&P 500 Benchmark State
    # Find first valid SPY price
    first_valid_idx = df['SPY'].first_valid_index()
    initial_spy_price = df.loc[first_valid_idx]['SPY']
    
    spy_holdings = INITIAL_CAPITAL / initial_spy_price
    spy_invested = INITIAL_CAPITAL
    
    portfolio_values = []
    spy_values = []
    
    dates = df.index
    
    print("Running simulation...")
    
    for i, date in enumerate(dates):
        # 0. Data for today
        try:
            row = df.iloc[i]
            year_month = date.strftime("%Y-%m")
            
            # Prices
            prices = {
                'BTC': row[('BTC-USD', 'Close')] if isinstance(row.keys(), tuple) else row['BTC-USD'],
                'ETH': row['ETH-USD'],
                'SOL': row['SOL-USD'],
                'PAXG': row['PAXG-USD'],
                'SPY': row['SPY']
            }
            # Handle NaNs (e.g. holidays or missing data)
            if pd.isna(prices['BTC']) or pd.isna(prices['SPY']):
                # Append previous value or skip
                if portfolio_values:
                    portfolio_values.append({'date': date, 'value': portfolio_values[-1]['value']})
                    spy_values.append({'date': date, 'value': spy_values[-1]['value']})
                continue

            # Indicators
            dxy = row['DX-Y.NYB']
            fng = row['FNG']
            pmi = PMI_DATA.get(year_month, 50) # Default to 50 if missing
            
            # 1. DCA (Once a month - let's say 1st of month or first trading day)
            if i == 0 or date.month != dates[i-1].month:
                holdings['USDT'] += MONTHLY_DCA
                cash_invested += MONTHLY_DCA
                
                # S&P Strategy: Buy immediately
                shares_to_buy = MONTHLY_DCA / prices['SPY']
                spy_holdings += shares_to_buy
                spy_invested += MONTHLY_DCA
            
            # 2. Determine Mode
            # REUSE LOGIC FROM BOT
            mode = "SHIELD"
            if fng < 30:
                mode = "ATTACK"
            elif dxy < 103 and pmi > 50:
                mode = "CRUISE"
            
            # 3. Target Ratios
            # ATTACK: 40% SOL, 30% ETH, 30% BTC
            # CRUISE: 40% BTC, 30% ETH, 30% SOL
            # SHIELD: 40% BTC, 40% PAXG, 20% USDT
            
            targets = {}
            if mode == "ATTACK":
                targets = {'SOL': 0.40, 'ETH': 0.30, 'BTC': 0.30, 'PAXG': 0.0, 'USDT': 0.0}
            elif mode == "CRUISE":
                targets = {'BTC': 0.40, 'ETH': 0.30, 'SOL': 0.30, 'PAXG': 0.0, 'USDT': 0.0}
            else: # SHIELD
                targets = {'BTC': 0.40, 'PAXG': 0.40, 'USDT': 0.20, 'ETH': 0.0, 'SOL': 0.0}
                
            # 4. Rebalance Logic
            # Calculate Total Value
            current_val = holdings['USDT']
            for asset in ['BTC', 'ETH', 'SOL', 'PAXG']:
                current_val += holdings[asset] * prices[asset]
            
            # Execute Trades (Simplified for Backtest: adjust to targets)
            # Apply Zero Loss Rule Logic:
            # "No sell BTC/ETH/SOL if price < avg_buy UNLESS Shield mode (Defensive Rebalancing)"
            
            # We calculate ideal amounts
            # Check for sells first
            
            for asset in ['BTC', 'ETH', 'SOL', 'PAXG']:
                target_ratio = targets.get(asset, 0)
                target_usd = current_val * target_ratio
                current_asset_usd = holdings[asset] * prices[asset]
                
                diff_usd = target_usd - current_asset_usd
                
                if diff_usd < -1: # Selling (tolerance $1)
                    # Check Zero Loss
                    avg_buy = avg_buy_prices.get(asset, 0)
                    if asset in ['BTC', 'ETH', 'SOL'] and prices[asset] < avg_buy and mode != "SHIELD":
                        # HOLD (Do not sell)
                        continue 
                    
                    # Sell
                    sell_amt = abs(diff_usd) / prices[asset]
                    holdings[asset] -= sell_amt
                    holdings['USDT'] += abs(diff_usd) * (1 - FEE)
            
            # Recalculate value after sells to have cash for buys
            current_val_after_sells = holdings['USDT']
            for asset in ['BTC', 'ETH', 'SOL', 'PAXG']:
                current_val_after_sells += holdings[asset] * prices[asset]

            # Executes Buys
            for asset in ['BTC', 'ETH', 'SOL', 'PAXG']:
                target_ratio = targets.get(asset, 0)
                target_usd = current_val_after_sells * target_ratio
                current_asset_usd = holdings[asset] * prices[asset]
                diff_usd = target_usd - current_asset_usd
                
                if diff_usd > 1 and holdings['USDT'] > diff_usd: # Buying
                    buy_amt = diff_usd / prices[asset]
                    cost = diff_usd
                    holdings[asset] += buy_amt
                    holdings['USDT'] -= cost
                    
                    # Update Avg Buy Price
                    prev_amt = holdings[asset] - buy_amt
                    if holdings[asset] > 0:
                        # Simple Weighted Avg approximation
                        old_cost = prev_amt * avg_buy_prices.get(asset, 0)
                        new_cost = buy_amt * prices[asset]
                        avg_buy_prices[asset] = (old_cost + new_cost) / holdings[asset]


            # Record Value
            total_port_value = holdings['USDT']
            for asset in ['BTC', 'ETH', 'SOL', 'PAXG']:
                total_port_value += holdings[asset] * prices[asset]
                
            spy_port_value = spy_holdings * prices['SPY']
            
            portfolio_values.append({'date': date, 'value': total_port_value, 'invested': cash_invested})
            spy_values.append({'date': date, 'value': spy_port_value})
            
        except Exception as e:
            # print(f"Error on {date}: {e}") # Reduce noise
            pass

    # Results
    res_df = pd.DataFrame(portfolio_values)
    res_df.set_index('date', inplace=True)
    spy_df = pd.DataFrame(spy_values)
    spy_df.set_index('date', inplace=True)
    
    # Plot
    plt.figure(figsize=(12, 6))
    plt.plot(res_df.index, res_df['value'], label='5 Cubes Strategy')
    plt.plot(spy_df.index, spy_df['value'], label='S&P 500 (DCA)')
    plt.plot(res_df.index, res_df['invested'], label='Total Invested', linestyle='--', color='black', linewidth=1.5)
    plt.title('5 Cubes Strategy vs S&P 500 (Initial 500€ + DCA 100€/mo)')
    plt.ylabel('Portfolio Value (USD/EUR)')
    plt.legend()
    plt.grid(True)
    plt.savefig('backtest_results.png')
    
    final_val = res_df['value'].iloc[-1]
    final_spy = spy_df['value'].iloc[-1]
    invested = res_df['invested'].iloc[-1]
    
    print(f"--- RESULTS ---")
    print(f"Total Invested: {invested:.2f}")
    print(f"5 Cubes Final Value: {final_val:.2f}")
    print(f"S&P 500 Final Value: {final_spy:.2f}")
    print(f"Strategy Return: {((final_val - invested)/invested)*100:.2f}%")
    print(f"S&P 500 Return: {((final_spy - invested)/invested)*100:.2f}%")

if __name__ == "__main__":
    backtest()
