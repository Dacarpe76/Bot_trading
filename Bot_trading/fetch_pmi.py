import pandas as pd
import requests
from io import StringIO
from datetime import datetime, timedelta

def download_pmi():
    print("Downloading ISM Manufacturing PMI data from FRED...")
    
    # FRED URL for ISM Manufacturing PMI (NAPMPMI)
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=NAPMPMI"
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            csv_data = StringIO(response.text)
            df = pd.read_csv(csv_data)
            
            # Save to CSV
            output_file = "pmi_history.csv"
            df.to_csv(output_file, index=False)
            print(f"✅ Successfully saved {len(df)} records to {output_file}")
            print(df.tail())
        else:
            print(f"❌ Failed to download. Status code: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    download_pmi()
