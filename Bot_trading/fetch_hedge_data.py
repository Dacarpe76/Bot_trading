import yfinance as yf
import pandas as pd
import requests
import time
from datetime import datetime

def fetch_yfinance_data(tickers, start_date):
    print(f"Fetching {tickers} from yfinance...")
    try:
        data = yf.download(tickers, start=start_date, progress=False, group_by='ticker', auto_adjust=False)
        return data
    except Exception as e:
        print(f"Error fetching YF data: {e}")
        return pd.DataFrame()

def fetch_fear_and_greed(limit=0):
    print("Fetching Fear & Greed Index...")
    url = f"https://api.alternative.me/fng/?limit={limit}&format=json"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if 'data' not in data:
            return pd.DataFrame()
            
        records = []
        for item in data['data']:
            # timestamp is unix string
            dt = datetime.fromtimestamp(int(item['timestamp']))
            records.append({
                'date': dt.strftime('%Y-%m-%d'),
                'fng_value': int(item['value']),
                'fng_classification': item['value_classification']
            })
            
        df = pd.DataFrame(records)
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        return df.sort_index()
    except Exception as e:
        print(f"Error fetching Fear & Greed: {e}")
        return pd.DataFrame()

def main():
    start_date = "2019-01-01"
    
    # 1. Fetch DXY (DX-Y.NYB) and ETH (ETH-EUR)
    # Note: DXY symbol on Yahoo is often 'DX-Y.NYB' or 'DX=F'
    tickers = "DX-Y.NYB ETH-EUR" 
    
    yf_data = fetch_yfinance_data(tickers, start_date)
    
    # Process DXY
    if 'DX-Y.NYB' in yf_data.columns.levels[0]:
        dxy = yf_data['DX-Y.NYB'][['Adj Close']].copy()
    else:
        # Fallback if ticker structure is flat or different
        dxy = yf_data[['Adj Close']].copy() # Risky if multiple
        
    dxy.columns = ['DXY']
    
    # Process ETH
    if 'ETH-EUR' in yf_data.columns.levels[0]:
        eth = yf_data['ETH-EUR'][['Adj Close']].copy()
    else:
        eth = pd.DataFrame() # Should handle fallback
    
    eth.columns = ['ETH_Price']
    
    # 2. Fetch Fear & Greed
    # limit=0 gets all history
    fng = fetch_fear_and_greed(limit=0)
    
    # 3. Merge
    print("Merging data...")
    # Clean indices
    if dxy.index.tz is not None: dxy.index = dxy.index.tz_localize(None)
    if eth.index.tz is not None: eth.index = eth.index.tz_localize(None)
    
    combined = dxy.join(eth, how='outer').join(fng, how='outer')
    
    # Forward fill to handle weekends/holidays differences
    combined = combined.ffill()
    
    # Filter from 2020
    combined = combined.loc["2020-01-01":]
    
    output_file = "hedge_data.csv"
    combined.to_csv(output_file)
    print(f"Saved hedge data to {output_file}. Last date: {combined.index[-1]}")
    print(combined.tail())

if __name__ == "__main__":
    main()
