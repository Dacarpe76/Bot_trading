import pandas as pd
import yfinance as yf
import requests
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime, timedelta

# --- CONFIGURATION ---
START_DATE = "2010-01-01"
END_DATE = "2020-12-31"
INITIAL_CAPITAL = 500
MONTHLY_DCA = 100
FEE = 0.001 

# --- PMI DATA (2010-2020) ---
PMI_DATA = {
    # 2010
    '2010-01': 57.2, '2010-02': 55.8, '2010-03': 58.8, '2010-04': 58.1, '2010-05': 58.3, '2010-06': 56.4,
    '2010-07': 56.4, '2010-08': 58.0, '2010-09': 56.3, '2010-10': 57.7, '2010-11': 56.6, '2010-12': 57.0,
    # 2011
    '2011-01': 59.0, '2011-02': 59.3, '2011-03': 59.1, '2011-04': 58.9, '2011-05': 53.5, '2011-06': 56.6,
    '2011-07': 52.9, '2011-08': 53.0, '2011-09': 52.8, '2011-10': 51.8, '2011-11': 52.1, '2011-12': 53.9,
    # 2012
    '2012-01': 54.1, '2012-02': 52.6, '2012-03': 53.4, '2012-04': 54.8, '2012-05': 50.7, '2012-06': 49.7,
    '2012-07': 49.8, '2012-08': 49.6, '2012-09': 51.5, '2012-10': 51.7, '2012-11': 49.5, '2012-12': 50.7,
    # 2013
    '2013-01': 52.3, '2013-02': 53.1, '2013-03': 51.3, '2013-04': 50.0, '2013-05': 49.0, '2013-06': 50.9,
    '2013-07': 54.9, '2013-08': 55.7, '2013-09': 56.2, '2013-10': 56.4, '2013-11': 57.3, '2013-12': 56.5,
    # 2014
    '2014-01': 53.1, '2014-02': 53.7, '2014-03': 53.7, '2014-04': 54.9, '2014-05': 53.2, '2014-06': 55.3,
    '2014-07': 57.1, '2014-08': 59.0, '2014-09': 56.6, '2014-10': 59.0, '2014-11': 58.7, '2014-12': 55.5,
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
    # 2020 included for completion logic overlap
    '2020-01': 50.9, '2020-02': 50.1, '2020-03': 49.1, '2020-04': 41.5, '2020-05': 43.1, '2020-06': 52.6,
    '2020-07': 54.2, '2020-08': 56.0, '2020-09': 55.4, '2020-10': 59.3, '2020-11': 57.5, '2020-12': 60.7,
}

def get_historical_data():
    print("Fetching historical data (2010-2020)...")
    tickers = ['BTC-USD', 'ETH-USD', 'GLD', 'DX-Y.NYB', 'SPY', '^VIX']
    # Start slightly earlier to get initial data
    data = yf.download(tickers, start="2009-12-01", end="2021-01-01")['Close']
    data.index = pd.to_datetime(data.index)
    return data

def backtest():
    df = get_historical_data()
    df = df.bfill() # Backward fill
    
    # CALCULATE SMA 200 for BTC
    df['BTC_SMA200'] = df['BTC-USD'].rolling(window=200).mean()
    
    # CALCULATE VOLATILITY (VIX) MOVING AVERAGE (20 days)
    # Using VIX as proxy for Crypto Volatility in this era
    df['VIX_SMA20'] = df['^VIX'].rolling(window=20).mean()

    # Trim to start date (after window calc)
    df = df[df.index >= START_DATE]

    # Portfolio State
    holdings = {'BTC': 0, 'ETH': 0, 'SOL': 0, 'PAXG': 0, 'USDT': INITIAL_CAPITAL}
    avg_buy_prices = {'BTC': 0, 'ETH': 0, 'SOL': 0, 'PAXG': 0}
    cash_invested = INITIAL_CAPITAL
    
    # S&P Benchmark
    first_valid_idx = df['SPY'].first_valid_index()
    initial_spy_price = df.loc[first_valid_idx]['SPY']
    spy_holdings = INITIAL_CAPITAL / initial_spy_price
    spy_invested = INITIAL_CAPITAL
    
    portfolio_values = []
    spy_values = []
    
    dates = df.index
    print("Running simulation...")
    
    for i, date in enumerate(dates):
        try:
            row = df.iloc[i]
            year_month = date.strftime("%Y-%m")
            
            # --- PRICES & PROXIES ---
            # Handle BTC 
            btc_price = row['BTC-USD']
            if pd.isna(btc_price):
                 # Before BTC data (2010-mid 2010 mostly missing in YF sometimes)
                 # We skip trading until data exists
                 if portfolio_values:
                    portfolio_values.append({'date': date, 'value': portfolio_values[-1]['value'], 'invested': cash_invested})
                    spy_values.append({'date': date, 'value': spy_values[-1]['value']})
                 continue

            eth_price = row.get('ETH-USD', np.nan)
            
            # GLD is Proxy for PAXG
            gld_price = row['GLD'] 
            
            prices = {
                'BTC': btc_price,
                'ETH': eth_price,
                'SOL': 0, # Not avail
                'PAXG': gld_price, # PROXY
                'SPY': row['SPY']
            }
            
            # --- INDICATORS ---
            dxy = row['DX-Y.NYB']
            vix = row['^VIX']
            pmi = PMI_DATA.get(year_month, 50)
            
            # --- DCA ---
            if i == 0 or date.month != dates[i-1].month:
                holdings['USDT'] += MONTHLY_DCA
                cash_invested += MONTHLY_DCA
                spy_holdings += MONTHLY_DCA / prices['SPY']
                spy_invested += MONTHLY_DCA

            # --- MODE DETERMINATION ---
            # --- SAFETY SWITCHES ---
            btc_sma200 = row['BTC_SMA200']
            vix_sma20 = row['VIX_SMA20']
            
            mode = "SHIELD" # Default
            
            # 1. Bear Market Check (SMA 200)
            if not pd.isna(btc_price) and not pd.isna(btc_sma200) and btc_price < btc_sma200:
                mode = "BEAR_SHIELD" # New Mode: 70% PAXG, 30% USDT
            
            else:
                # 2. Volatility Check
                # If VIX is rising (Current > SMA20), block ATTACK
                volatility_rising = (vix > vix_sma20)
                
                if vix > 30 and not volatility_rising:
                     mode = "ATTACK"
                elif dxy < 103 and pmi > 50:
                     mode = "CRUISE"
                else:
                     mode = "SHIELD"
                
                # If Volatility Rising, downgrade ATTACK to CRUISE/SHIELD?
                # User: "If volatility rises... Fear is not a buying opportunity" -> Block Attack
                if mode == "ATTACK" and volatility_rising:
                    mode = "SHIELD" # Fallback defensive

            # --- TARGET WEIGHTS & NORMALIZATION ---
            # Assets available check
            avail_assets = ['BTC', 'PAXG'] # Always available (PAXG via GLD)
            if not pd.isna(eth_price): # ETH available?
                avail_assets.append('ETH')
            
            raw_targets = {}
            if mode == "ATTACK":
                # Ideal: SOL 40, ETH 30, BTC 30
                raw_targets = {'SOL': 0.40, 'ETH': 0.30, 'BTC': 0.30, 'PAXG': 0.0}
            elif mode == "CRUISE":
                # Ideal: BTC 40, ETH 30, SOL 30
                raw_targets = {'BTC': 0.40, 'ETH': 0.30, 'SOL': 0.30, 'PAXG': 0.0}
            elif mode == "BEAR_SHIELD":
                 # New Conservative Mode: 70% PAXG, 30% USDT
                 raw_targets = {'BTC': 0.0, 'PAXG': 0.70, 'USDT': 0.30, 'ETH': 0.0, 'SOL': 0.0}
            else: # SHIELD
                # Ideal: BTC 40, PAXG 40, USDT 20
                raw_targets = {'BTC': 0.40, 'PAXG': 0.40, 'USDT': 0.20, 'ETH': 0.0, 'SOL': 0.0}
            
            # Normalize
            final_targets = {}
            total_weight = 0
            
            # First pass: sum weights of available assets
            for asset, w in raw_targets.items():
                if w > 0:
                    if asset == 'USDT': 
                         total_weight += w
                         continue
                    if asset == 'SOL': continue # Never avail 2010-2020
                    if asset == 'ETH' and 'ETH' not in avail_assets: continue
                    total_weight += w
            
            if total_weight == 0: 
                # Fallback purely to USDT if nothing fits (unlikely)
                final_targets = {'USDT': 1.0}
            else:
                for asset, w in raw_targets.items():
                    if asset == 'SOL': continue
                    if asset == 'ETH' and 'ETH' not in avail_assets: continue
                    
                    if w > 0:
                        final_targets[asset] = w / total_weight

            # --- REBALANCE ---
            # Calc Total Value
            current_val = holdings['USDT']
            if not pd.isna(prices['BTC']): current_val += holdings['BTC'] * prices['BTC']
            if not pd.isna(prices['ETH']): current_val += holdings['ETH'] * prices['ETH']
            current_val += holdings['PAXG'] * prices['PAXG']
            
            # Sells
            for asset in ['BTC', 'ETH', 'PAXG']:
                if asset not in final_targets and holdings[asset] > 0:
                    # Sell all if not in target (e.g. ETH became unavail? No, logic prevents)
                    # Actually if target is 0.
                    pass
                
                target_ratio = final_targets.get(asset, 0)
                price = prices[asset]
                if pd.isna(price): continue
                
                target_usd = current_val * target_ratio
                curr_usd = holdings[asset] * price
                diff = target_usd - curr_usd
                
                if diff < -1:
                    # Zero Loss Check (Simple: Don't sell crypto in loss unless Shield)
                    avg_buy = avg_buy_prices.get(asset, 0)
                    if asset in ['BTC', 'ETH'] and price < avg_buy and mode != "SHIELD":
                        continue
                        
                    sell_amt = abs(diff) / price
                    holdings[asset] -= sell_amt
                    holdings['USDT'] += abs(diff) * (1 - FEE)

            # Buys
            # Recalc cash after sells
            current_val_after_sells = holdings['USDT']
            current_val_after_sells += holdings['BTC'] * prices['BTC']
            if not pd.isna(prices['ETH']): current_val_after_sells += holdings['ETH'] * prices['ETH']
            current_val_after_sells += holdings['PAXG'] * prices['PAXG']

            for asset in ['BTC', 'ETH', 'PAXG']:
                target_ratio = final_targets.get(asset, 0)
                price = prices.get(asset, 0)
                if pd.isna(price) or price == 0: continue
                
                target_usd = current_val_after_sells * target_ratio
                curr_usd = holdings[asset] * price
                diff = target_usd - curr_usd
                
                if diff > 1 and holdings['USDT'] > diff:
                    buy_amt = diff / price
                    holdings[asset] += buy_amt
                    holdings['USDT'] -= diff
                    
                    # Avg Buy
                    prev = holdings[asset] - buy_amt
                    if holdings[asset] > 0:
                        old_cost = prev * avg_buy_prices.get(asset, 0)
                        new_cost = buy_amt * price
                        avg_buy_prices[asset] = (old_cost + new_cost) / holdings[asset]

            # Record
            total_port = holdings['USDT'] 
            total_port += holdings['BTC'] * prices['BTC']
            if not pd.isna(prices['ETH']): total_port += holdings['ETH'] * prices['ETH']
            total_port += holdings['PAXG'] * prices['PAXG']
            
            portfolio_values.append({'date': date, 'value': total_port, 'invested': cash_invested})
            spy_values.append({'date': date, 'value': spy_holdings * prices['SPY']})

        except Exception as e:
            # print(e)
            pass

    # Plot
    res_df = pd.DataFrame(portfolio_values).set_index('date')
    spy_df = pd.DataFrame(spy_values).set_index('date')
    
    plt.figure(figsize=(12, 6))
    plt.plot(res_df.index, res_df['value'], label='5 Cubes (Proxy)')
    plt.plot(spy_df.index, spy_df['value'], label='S&P 500')
    plt.plot(res_df.index, res_df['invested'], label='Invested', linestyle='--', color='black')
    plt.title("5 Cubes Strategy Proxy (2010-2020)\nProxies: GLD for PAXG, VIX>30 for Fear")
    plt.legend()
    plt.grid(True)
    plt.savefig('backtest_2010_2020.png')
    
    final = res_df['value'].iloc[-1]
    sp_final = spy_df['value'].iloc[-1]
    inv = res_df['invested'].iloc[-1]
    
    print(f"--- 2010-2020 RESULTS ---")
    print(f"Invested: {inv:.2f}")
    print(f"5 Cubes: {final:.2f}")
    print(f"S&P 500: {sp_final:.2f}")

if __name__ == "__main__":
    backtest()
