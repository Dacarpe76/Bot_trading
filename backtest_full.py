import pandas as pd
import yfinance as yf
import requests
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime, timedelta

# --- CONFIGURATION ---
START_DATE = "2015-01-01"
END_DATE = datetime.now().strftime("%Y-%m-%d")
INITIAL_CAPITAL = 500
MONTHLY_DCA = 50
FEE = 0.001

# --- PMI DATA (2015-2025) ---
# Merged from previous sources
PMI_DATA = {
    # 2015
    '2015-01': 53.5, '2015-02': 52.9, '2015-03': 51.5, '2015-04': 51.3, '2015-05': 52.8, '2015-06': 53.5,
    '2015-07': 52.7, '2015-08': 51.1, '2015-09': 50.2, '2015-10': 50.1, '2015-11': 48.6, '2015-12': 48.0,
    # 2016
    '2016-01': 48.2, '2016-02': 49.5, '2016-03': 51.8, '2016-04': 50.8, '2016-05': 51.3, '2016-06': 53.2,
    '2016-07': 52.6, '2016-08': 49.4, '2016-09': 51.5, '2016-10': 51.9, '2016-11': 53.2, '2016-12': 54.7,
    # 2017
    '2017-01': 56.0, '2017-02': 57.7, '2017-03': 57.2, '2017-04': 54.8, '2017-05': 54.9, '2017-06': 57.8,
    '2017-07': 56.3, '2017-08': 58.8, '2017-09': 60.8, '2017-10': 58.7, '2017-11': 58.2, '2017-12': 59.7,
    # 2018
    '2018-01': 59.1, '2018-02': 60.8, '2018-03': 59.3, '2018-04': 57.3, '2018-05': 58.7, '2018-06': 60.2,
    '2018-07': 58.1, '2018-08': 61.3, '2018-09': 59.8, '2018-10': 57.7, '2018-11': 59.3, '2018-12': 54.1,
    # 2019
    '2019-01': 56.6, '2019-02': 54.2, '2019-03': 55.3, '2019-04': 52.8, '2019-05': 52.1, '2019-06': 51.7,
    '2019-07': 51.2, '2019-08': 49.1, '2019-09': 47.8, '2019-10': 48.3, '2019-11': 48.1, '2019-12': 47.2,
    # 2020
    '2020-01': 50.9, '2020-02': 50.1, '2020-03': 49.1, '2020-04': 41.5, '2020-05': 43.1, '2020-06': 52.6,
    '2020-07': 54.2, '2020-08': 56.0, '2020-09': 55.4, '2020-10': 59.3, '2020-11': 57.5, '2020-12': 60.7,
    # 2021
    '2021-01': 58.7, '2021-02': 60.8, '2021-03': 64.7, '2021-04': 60.7, '2021-05': 61.2, '2021-06': 60.6,
    '2021-07': 60.8, '2021-08': 59.9, '2021-09': 61.1, '2021-10': 60.8, '2021-11': 61.1, '2021-12': 58.7,
    # 2022
    '2022-01': 57.6, '2022-02': 58.6, '2022-03': 57.1, '2022-04': 55.4, '2022-05': 55.4, '2022-06': 53.0,
    '2022-07': 52.8, '2022-08': 52.8, '2022-09': 50.9, '2022-10': 50.2, '2022-11': 49.0, '2022-12': 48.4,
    # 2023
    '2023-01': 47.4, '2023-02': 47.7, '2023-03': 46.3, '2023-04': 47.1, '2023-05': 46.9, '2023-06': 46.0,
    '2023-07': 46.4, '2023-08': 47.6, '2023-09': 49.0, '2023-10': 46.7, '2023-11': 49.4, '2023-12': 47.4,
    # 2024
    '2024-01': 49.1, '2024-02': 47.8, '2024-03': 50.3, '2024-04': 49.2, '2024-05': 48.7, '2024-06': 48.5,
    '2024-07': 46.8, '2024-08': 47.2, '2024-09': 47.2, '2024-10': 46.5, '2024-11': 48.4, '2024-12': 48.0,
    # 2025
    '2025-01': 48.0
}

def get_historical_data():
    print("Fetching historical data (2015-Present)...")
    tickers = ['BTC-USD', 'ETH-USD', 'SOL-USD', 'PAXG-USD', 'GLD', 'DX-Y.NYB', 'SPY', '^VIX']
    data = yf.download(tickers, start=START_DATE, end=END_DATE)['Close']
    
    # FETCH F&G INDEX
    try:
        url = "https://api.alternative.me/fng/?limit=0"
        r = requests.get(url)
        fng_data = r.json()['data']
        fng_df = pd.DataFrame(fng_data)
        fng_df['timestamp'] = pd.to_datetime(fng_df['timestamp'], unit='s')
        fng_df.set_index('timestamp', inplace=True)
        fng_df = fng_df['value'].astype(int).sort_index()
        fng_df = fng_df.resample('D').ffill()
        
        data.index = pd.to_datetime(data.index)
        data['FNG'] = fng_df.reindex(data.index, method='ffill')
    except:
        print("Error fetching F&G, will use VIX proxy if missing")
        data['FNG'] = np.nan

    return data

def backtest():
    df = get_historical_data()
    df = df.bfill()
    
    # S&P Benchmark
    first_valid_idx = df['SPY'].first_valid_index()
    initial_spy_price = df.loc[first_valid_idx]['SPY']
    spy_holdings = INITIAL_CAPITAL / initial_spy_price
    spy_invested = INITIAL_CAPITAL
    
    # Portfolio
    holdings = {'BTC': 0, 'ETH': 0, 'SOL': 0, 'PAXG': 0, 'USDT': INITIAL_CAPITAL}
    avg_buy_prices = {'BTC': 0, 'ETH': 0, 'SOL': 0, 'PAXG': 0}
    cash_invested = INITIAL_CAPITAL
    
    # Indicators Calc
    df['BTC_SMA200'] = df['BTC-USD'].rolling(window=200).mean()
    df['VIX_SMA20'] = df['^VIX'].rolling(window=20).mean()
    df = df[df.index >= START_DATE]
    
    portfolio_values = []
    spy_values = []
    
    dates = df.index
    print(f"Running simulation from {START_DATE}...")
    
    for i, date in enumerate(dates):
        try:
            row = df.iloc[i]
            year_month = date.strftime("%Y-%m")
            
            # --- PRICES ---
            btc = row['BTC-USD']
            eth = row.get('ETH-USD', np.nan)
            sol = row.get('SOL-USD', np.nan)
            paxg = row.get('PAXG-USD', np.nan)
            gld = row['GLD']
            spy = row['SPY']
            
            # Gold Logic: Use PAXG if available, else GLD
            gold_price = paxg if not pd.isna(paxg) else gld
            gold_asset_name = 'PAXG' # We track as PAXG in holdings, but use GLD price if needed
            
            prices = {
                'BTC': btc,
                'ETH': eth,
                'SOL': sol,
                'PAXG': gold_price,
                'USDT': 1.0
            }
            
            if pd.isna(btc) or pd.isna(spy): continue

            # --- INDICATORS ---
            dxy = row['DX-Y.NYB']
            vix = row['^VIX']
            fng = row.get('FNG', np.nan)
            pmi = PMI_DATA.get(year_month, 50)
            
            btc_sma200 = row['BTC_SMA200']
            vix_sma20 = row['VIX_SMA20']
            
            # --- DCA ---
            if i == 0 or date.month != dates[i-1].month:
                holdings['USDT'] += MONTHLY_DCA
                cash_invested += MONTHLY_DCA
                spy_holdings += MONTHLY_DCA / spy
                spy_invested += MONTHLY_DCA

            # --- SAFETY SWITCH & MODE ---
            mode = "SHIELD"
            
            # 1. Bear Shield (SMA 200)
            if not pd.isna(btc_sma200) and btc < btc_sma200:
                mode = "BEAR_SHIELD"
            else:
                # 2. Volatility Check
                volatility_rising = (vix > vix_sma20)
                
                # F&G Logic (Use actual F&G if available, else VIX proxy)
                is_fear = False
                if not pd.isna(fng):
                    is_fear = (fng < 30)
                else:
                    is_fear = (vix > 30) # Proxy
                
                if is_fear and not volatility_rising:
                    mode = "ATTACK"
                elif dxy < 103 and pmi > 50:
                    mode = "CRUISE"
                else:
                    mode = "SHIELD"
                
                if mode == "ATTACK" and volatility_rising:
                    mode = "SHIELD"

            # --- TARGETS ---
            raw_targets = {}
            if mode == "ATTACK":
                raw_targets = {'SOL': 0.40, 'ETH': 0.30, 'BTC': 0.30, 'PAXG': 0.0}
            elif mode == "CRUISE":
                raw_targets = {'BTC': 0.40, 'ETH': 0.30, 'SOL': 0.30, 'PAXG': 0.0}
            elif mode == "BEAR_SHIELD":
                # 70% Gold, 30% Cash
                raw_targets = {'BTC': 0.0, 'PAXG': 0.70, 'USDT': 0.30, 'ETH': 0.0, 'SOL': 0.0}
            else: # SHIELD
                # 40% BTC, 40% Gold, 20% Cash
                raw_targets = {'BTC': 0.40, 'PAXG': 0.40, 'USDT': 0.20, 'ETH': 0.0, 'SOL': 0.0}

            # Normalize for Availability
            avail_assets = ['BTC', 'PAXG', 'USDT']
            if not pd.isna(eth): avail_assets.append('ETH')
            if not pd.isna(sol): avail_assets.append('SOL')
            
            final_targets = {}
            total_w = 0
            for a, w in raw_targets.items():
                if a in avail_assets: total_w += w
            
            if total_w == 0: final_targets = {'USDT': 1.0}
            else:
                for a, w in raw_targets.items():
                    if a in avail_assets:
                        final_targets[a] = w / total_w
            
            # --- REBALANCE ---
            # Total Value
            current_val = holdings['USDT']
            for a in ['BTC', 'ETH', 'SOL', 'PAXG']:
                if not pd.isna(prices[a]):
                    current_val += holdings[a] * prices[a]
            
            # Sells
            for a in ['BTC', 'ETH', 'SOL', 'PAXG']:
                p = prices.get(a, np.nan)
                if pd.isna(p) or p == 0: continue
                
                target_ratio = final_targets.get(a, 0)
                target_usd = current_val * target_ratio
                curr_usd = holdings[a] * p
                diff = target_usd - curr_usd
                
                if diff < -1:
                    # Zero Loss Check
                    avg_buy = avg_buy_prices.get(a, 0)
                    is_crypto = a in ['BTC', 'ETH', 'SOL']
                    # Exception: Panic Sell in Bear Shield? 
                    # User: "Mode Conservateur Automatique... move to Gold/USDC". So SELL even in loss.
                    # Logic: "El bot detecta... y se convierte en una roca".
                    # So Bear Shield OVERRIDES Zero Loss.
                    
                    if is_crypto and p < avg_buy and mode not in ["SHIELD", "BEAR_SHIELD"]:
                         continue
                         
                    sell_amt = abs(diff) / p
                    holdings[a] -= sell_amt
                    holdings['USDT'] += abs(diff) * (1 - FEE)

            # Buys
            curr_val_after = holdings['USDT']
            for a in ['BTC', 'ETH', 'SOL', 'PAXG']:
                if not pd.isna(prices[a]):
                     curr_val_after += holdings[a] * prices[a]
            
            for a in ['BTC', 'ETH', 'SOL', 'PAXG']:
                p = prices.get(a, np.nan)
                if pd.isna(p) or p == 0: continue
                
                target_ratio = final_targets.get(a, 0)
                target_usd = curr_val_after * target_ratio
                curr_usd = holdings[a] * p
                diff = target_usd - curr_usd
                
                if diff > 1 and holdings['USDT'] > diff:
                    buy_amt = diff / p
                    holdings[a] += buy_amt
                    holdings['USDT'] -= diff
                    
                    if holdings[a] > 0:
                        prev = holdings[a] - buy_amt
                        old_c = prev * avg_buy_prices.get(a, 0)
                        new_c = buy_amt * p
                        avg_buy_prices[a] = (old_c + new_c) / holdings[a]

            # Record
            tot = holdings['USDT']
            for a in ['BTC', 'ETH', 'SOL', 'PAXG']:
                 if not pd.isna(prices[a]): tot += holdings[a] * prices[a]
            
            portfolio_values.append({'date': date, 'value': tot, 'invested': cash_invested})
            spy_values.append({'date': date, 'value': spy_holdings * spy})
            
        except Exception as e:
            # print(e)
            pass

    # Plot
    res_df = pd.DataFrame(portfolio_values).set_index('date')
    spy_df = pd.DataFrame(spy_values).set_index('date')
    
    plt.figure(figsize=(12, 6))
    plt.plot(res_df.index, res_df['value'], label='5 Cubes (Safety Switch)')
    plt.plot(spy_df.index, spy_df['value'], label='S&P 500')
    plt.plot(res_df.index, res_df['invested'], label='Invested', linestyle='--', color='black')
    plt.title("5 Cubes Strategy (2015-Present)\nInitial 500€ + DCA 50€/mo | With Safety Switch")
    plt.legend()
    plt.grid(True)
    plt.savefig('backtest_full.png')
    
    final = res_df['value'].iloc[-1]
    sp_final = spy_df['value'].iloc[-1]
    inv = res_df['invested'].iloc[-1]
    
    print(f"--- 2015-Present RESULTS ---")
    print(f"Invested: {inv:.2f}")
    print(f"5 Cubes: {final:.2f}")
    print(f"S&P 500: {sp_final:.2f}")
    print(f"Strategy Return: {((final - inv)/inv)*100:.2f}%")

if __name__ == "__main__":
    backtest()
