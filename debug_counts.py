import pandas as pd

LOG_FILE = "TRH_Opportunities_Log.csv"
RES_FILE = "Short_Analysis_Results.csv"

def debug():
    log = pd.read_csv(LOG_FILE)
    res = pd.read_csv(RES_FILE)
    
    print(f"Log Rows: {len(log)}")
    print(f"Res Rows: {len(res)}")
    
    # Check RSI > 75 count
    log_high = log[ (log['RSI'] > 75) & (log['VRel'] > 3) ]
    res_high = res[ (res['RSI'] > 75) & (res['VRel'] > 3) ]
    
    print(f"Log (RSI>75, VRel>3) Count: {len(log_high)}")
    print(f"Res (RSI>75, VRel>3) Count: {len(res_high)}")
    
    if not log_high.empty:
        print("Sample Log RSI:", log_high['RSI'].head().tolist())
        
    if not res_high.empty:
        print("Sample Res RSI:", res_high['RSI'].head().tolist())

if __name__ == "__main__":
    debug()
