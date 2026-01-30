import pandas as pd
import os
import glob
from datetime import timedelta

# Configuration
LOG_FILE = "TRH_Opportunities_Log.csv"
RESEARCH_PATTERN = "TRH_Research_*.csv"
OUTPUT_FILE = "Short_Analysis_Results.csv"

# Simulation Params (Theoretical)
TP_PCT = 0.015  # 1.5% Take Profit
SL_PCT = 0.015  # 1.5% Stop Loss
TIME_LIMIT_HOURS = 8

def load_research_data():
    all_files = sorted(glob.glob(RESEARCH_PATTERN))
    print(f"Loading {len(all_files)} research files...")
    
    dfs = []
    for f in all_files:
        try:
            # Use on_bad_lines='skip' (pandas >= 1.3) or error_bad_lines=False (older)
            # engine='python' is safer for varying row lengths
            df = pd.read_csv(f, on_bad_lines='skip', engine='python')
            df['Timestamp'] = pd.to_datetime(df['Timestamp'])
            dfs.append(df)
        except Exception as e:
            print(f"Skipping {f} entirely due to: {e}")
            
    if not dfs:
        return pd.DataFrame()
        
    full_df = pd.concat(dfs).sort_values('Timestamp').reset_index(drop=True)
    full_df.set_index('Timestamp', inplace=True)
    
    # Ensure no duplicates
    full_df = full_df[~full_df.index.duplicated(keep='first')]
    
    return full_df

def analyze_shorts():
    print("Loading opportunities...")
    try:
        ops = pd.read_csv(LOG_FILE)
        ops['Timestamp'] = pd.to_datetime(ops['Timestamp'])
    except Exception as e:
        print(f"Error loading log: {e}")
        return

    # Filter for Potential Shorts
    # Logic: High RSI usually triggers Shorts. VRel > 3 is aggressive.
    # We will analyze ANY signal where RSI > 50 as a "Hypothetical Short"
    # to see which ones would have worked.
    
    short_candidates = ops[ops['RSI'] > 50].copy()
    print(f"Found {len(short_candidates)} potential short candidates (RSI > 50).")
    
    market_data = load_research_data()
    if market_data.empty:
        print("No market data found.")
        return

    results = []
    
    for idx, row in short_candidates.iterrows():
        entry_time = row['Timestamp']
        entry_price = row['Price']
        
        # Get data slice starting from entry time
        # We look up to TIME_LIMIT_HOURS ahead
        end_time = entry_time + timedelta(hours=TIME_LIMIT_HOURS)
        
        # Use simple slicing on DateTimeIndex
        # Optimize: ensure market_data is sorted index
        
        # We need data strictly after entry_time
        
        future_data = market_data[entry_time:end_time]
        
        if future_data.empty:
            continue
            
        # Analyze outcome
        # Short: We want Price < Entry.
        # Max Benefit in window (Lowest Low)
        min_price = future_data['Low'].min()
        max_price = future_data['High'].max() # Risk (Highest High)
        
        if pd.isna(min_price) or pd.isna(max_price):
            continue

        max_profit_pct = (entry_price - min_price) / entry_price
        max_drawdown_pct = (max_price - entry_price) / entry_price
        
        # Did we hit TP or SL first?
        # Iterate row by row for precise timing
        outcome = "TIME_LIMIT"
        final_pnl = (entry_price - future_data.iloc[-1]['Close']) / entry_price
        
        for t, candle in future_data.iterrows():
            # Check Low for TP
            curr_low = candle['Low']
            curr_high = candle['High']
            
            # Check SL first (Conservative: assume Worst Case if both in same candle?)
            # Or assume standard candle mechanics.
            # Let's check High for SL first.
            
            dd = (curr_high - entry_price) / entry_price
            if dd >= SL_PCT:
                outcome = "STOP_LOSS"
                final_pnl = -SL_PCT
                break
                
            profit = (entry_price - curr_low) / entry_price
            if profit >= TP_PCT:
                outcome = "TAKE_PROFIT"
                final_pnl = TP_PCT
                break
        
        results.append({
            'Timestamp': entry_time,
            'Price': entry_price,
            'RSI': row['RSI'],
            'VRel': row['VRel'],
            'ERR': row['ERR'],
            'Decision': row['Decision_Outcome'],
            'Max_Profit_Pct': max_profit_pct * 100,
            'Max_DD_Pct': max_drawdown_pct * 100,
            'Outcome': outcome,
            'Final_PnL_Pct': final_pnl * 100
        })

    results_df = pd.DataFrame(results)
    
    if results_df.empty:
        print("No results generated.")
        return
        
    print("\n--- Analysis Results (Short Candidates) ---")
    print(results_df['Outcome'].value_counts())
    
    print("\nAverage Max Potential Profit: {:.2f}%".format(results_df['Max_Profit_Pct'].mean()))
    
    # Filter for High Quality Setup (Aggressive params: VRel > 3, ERR > 2.5)
    high_qual = results_df[ (results_df['VRel'] > 3.0) & (results_df['ERR'] > 2.5) ]
    print(f"\n--- High Quality Candidates (VRel>3, ERR>2.5) Count: {len(high_qual)} ---")
    if not high_qual.empty:
        print(high_qual['Outcome'].value_counts())
        print("Avg Max Profit: {:.2f}%".format(high_qual['Max_Profit_Pct'].mean()))
        
    results_df.to_csv(OUTPUT_FILE, index=False)
    print(f"\nSaved detailed analysis to {OUTPUT_FILE}")

if __name__ == "__main__":
    analyze_shorts()
