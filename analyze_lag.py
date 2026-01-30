import pandas as pd
import sys

# Load Data
try:
    df = pd.read_csv('/home/daniel/Bot_agresivo/TRH_Research_2026_01_25.csv', on_bad_lines='skip')
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    df = df.sort_values('Timestamp')
except Exception as e:
    print(f"Error loading CSV: {e}")
    sys.exit(1)

# Select relevant columns
cols = ['Timestamp', 'Symbol', 'Close']
df = df[cols]

# Remove duplicates
df = df.drop_duplicates(subset=['Timestamp', 'Symbol'], keep='last')

# Pivot to have symbols as columns
df_pivot = df.pivot(index='Timestamp', columns='Symbol', values='Close')
df_pivot = df_pivot.sort_index()

# Calculate % Returns (1-minute)
returns = df_pivot.pct_change() * 100

# Find biggest XBT Drop
try:
    if 'XBT/EUR' not in returns.columns:
        print("XBT/EUR not found in data.")
        sys.exit(0)
        
    worst_drop_idx = returns['XBT/EUR'].idxmin()
    worst_drop_val = returns.loc[worst_drop_idx, 'XBT/EUR']
    
    print(f"Biggest XBT Drop detected at: {worst_drop_idx}")
    print(f"Drop Magnitude: {worst_drop_val:.4f}%")
    
    # Get a window around this event (-2 min to +5 min)
    start_loc = df_pivot.index.get_loc(worst_drop_idx) - 2
    end_loc = df_pivot.index.get_loc(worst_drop_idx) + 6
    
    start_loc = max(0, start_loc)
    end_loc = min(len(df_pivot), end_loc)
    
    window_prices = df_pivot.iloc[start_loc:end_loc]
    window_returns = returns.iloc[start_loc:end_loc]
    
    print("\n--- Price Action Window ---")
    target_cols = ['XBT/EUR', 'ETH/EUR', 'SOL/EUR', 'XRP/EUR', 'ADA/EUR']
    # Filter only existing
    target_cols = [c for c in target_cols if c in df_pivot.columns]
    
    print(window_returns[target_cols].round(4).to_string())
    
    # Check simplified Lag
    print("\n--- Lag Analysis (Drop Start) ---")
    for col in target_cols:
        if col == 'XBT/EUR': continue
        
        # Find min in this window
        min_idx = window_returns[col].idxmin()
        time_diff = (min_idx - worst_drop_idx).total_seconds()
        
        print(f"{col}: Worst drop at {min_idx} (Diff: {time_diff}s)")

except Exception as e:
    print(f"Analysis failed: {e}")
