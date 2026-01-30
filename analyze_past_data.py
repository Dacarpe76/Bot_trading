import pandas as pd
import glob
import os
import ta

def analyze_data():
    files = glob.glob("TRH_Research_*.csv")
    if not files:
        print("No CSV files found.")
        return
        
    print(f"Reading {len(files)} files...")
    df_list = []
    for f in files:
        try:
            df = pd.read_csv(f)
            # Ensure DateTime
            if 'Timestamp' in df.columns:
                df['Timestamp'] = pd.to_datetime(df['Timestamp'])
                df = df.sort_values('Timestamp')
            df_list.append(df)
        except: pass
        
    if not df_list: return
    df = pd.concat(df_list, ignore_index=True)
    
    # Calc RSI if missing
    if 'RSI' not in df.columns:
        print("Calculating missing RSI...")
        try:
            # Need to calc per symbol ideally, but for rough estimation global is ok if sorted?
            # No, MUST calc per symbol.
            df['RSI'] = 50.0
            for sym in df['Symbol'].unique():
                mask = df['Symbol'] == sym
                # sub_df = df.loc[mask]
                close = df.loc[mask, 'Close']
                if len(close) > 14:
                    rsi = ta.momentum.RSIIndicator(close, window=14).rsi()
                    df.loc[mask, 'RSI'] = rsi
        except Exception as e:
            print(f"RSI Calc Failed: {e}")
            
    # Normalize numeric
    cols = ['VRel', 'ERR', 'RSI', 'ADX_14', 'Dist_EMA200_Pct', 'High', 'Low', 'Upper_Wick_Size', 'Lower_Wick_Size']
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')
            
    # Mecha
    df['Total_Len'] = df['High'] - df['Low']
    df['Max_Wick'] = df[['Upper_Wick_Size', 'Lower_Wick_Size']].max(axis=1)
    df['Wick_Pct'] = df['Max_Wick'] / df['Total_Len'].replace(0, 1)

    # --- COUNTS ---
    counts = {}
    
    # S1/S2: VRel > 4.0, ERR > 3.5, PinBar Mecha > 70% (0.7)
    mask_s1_strict = (df['VRel'] > 4.0) & (df['ERR'] > 3.5) & (df['Wick_Pct'] > 0.70)
    counts['S1_Sniper'] = mask_s1_strict.sum()
    counts['S2_Cent'] = mask_s1_strict.sum()
    
    # S1/S2 NO WICK (Hypothetical)
    mask_s1_nowick = (df['VRel'] > 4.0) & (df['ERR'] > 3.5)
    counts['S1_Sniper_NO_WICK'] = mask_s1_nowick.sum()
    
    # S3/S4
    mask_base = (df['VRel'] > 3.0) & (df['ERR'] > 2.5)
    mask_climax_L = (df['VRel'] > 10.0) & (df['RSI'] < 15.0)
    mask_climax_S = (df['VRel'] > 10.0) & (df['RSI'] > 85.0)
    mask_s3 = mask_base | mask_climax_L | mask_climax_S
    counts['S3_Aggressive'] = mask_s3.sum()
    counts['S4_AggrCent'] = mask_s3.sum()
    
    # S5
    if 'Current_Trend_1h' in df.columns:
        trend = df['Current_Trend_1h'].astype(str).str.contains('Bullish', case=False)
        ema = (df['Dist_EMA200_Pct'] >= 0) & (df['Dist_EMA200_Pct'] <= 0.005)
        vrel = df['VRel'] > 1.5
        adx = df['ADX_14'] > 25
        # Fib check skipped for estimation
        counts['S5_Pullback'] = (trend & ema & vrel & adx).sum()
    else:
        counts['S5_Pullback'] = 0
        
    # S6 ERIT
    if 'PinBar' in df.columns:
        pin = df['PinBar'].astype(str).str.contains('True', case=False)
        # Approx Confluence
        erit = pin & (df['VRel'] > 1.5) & (df['ADX_14'] > 25)
        counts['S6_ERIT'] = erit.sum()
    else:
        counts['S6_ERIT'] = 0

    print("\nRESULTADOS ESTIMADOS:")
    for k, v in counts.items():
        print(f"{k}: {v} entradas")
        
if __name__ == "__main__":
    analyze_data()
