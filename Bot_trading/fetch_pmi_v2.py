import pandas_datareader.data as web
import pandas as pd
from datetime import datetime

def fetch_pmi_datareader():
    print("Fetching ISM Manufacturing PMI (NAPMPMI) from FRED via pandas_datareader...")
    start_date = "2015-01-01"
    end_date = datetime.now().strftime("%Y-%m-%d")
    
    try:
        # NAPMPMI: ISM Manufacturing PMI
        df = web.DataReader('NAPMPMI', 'fred', start_date, end_date)
        
        # Reset index to have DATE column
        df.reset_index(inplace=True)
        
        # Save
        filename = "pmi_history.csv"
        df.to_csv(filename, index=False)
        print(f"✅ Successfully saved {len(df)} records to {filename}")
        print(df.tail())
        
    except Exception as e:
        print(f"❌ Error fetching data: {e}")

if __name__ == "__main__":
    fetch_pmi_datareader()
