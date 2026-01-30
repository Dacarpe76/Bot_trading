import pandas as pd
import os

LOG_FILE = "TRH_Opportunities_Log.csv"
RESEARCH_DIR = "."

def inspect():
    if not os.path.exists(LOG_FILE):
        print(f"File {LOG_FILE} not found.")
        return

    print(f"--- Loading {LOG_FILE} ---")
    df = pd.read_csv(LOG_FILE)
    
    print("\nColumns:", df.columns.tolist())
    
    if 'Signal_Type' in df.columns:
        print("\nUnique Signal_Type:")
        print(df['Signal_Type'].unique())
        
    if 'Decision_Outcome' in df.columns:
        print("\nUnique Decision_Outcome:")
        print(df['Decision_Outcome'].unique())

    if 'Strategy_IDs' in df.columns:
         print("\nUnique Strategy_IDs:")
         print(df['Strategy_IDs'].unique())
         
    # Check a Research File
    research_files = sorted([f for f in os.listdir(RESEARCH_DIR) if f.startswith("TRH_Research_") and f.endswith(".csv")])
    if research_files:
        r_file = research_files[-1]
        print(f"\n--- Loading latest research file: {r_file} ---")
        rdf = pd.read_csv(os.path.join(RESEARCH_DIR, r_file), nrows=5)
        print("Columns:", rdf.columns.tolist())
    else:
        print("\nNo TRH_Research files found.")

if __name__ == "__main__":
    inspect()
