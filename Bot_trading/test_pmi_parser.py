import re
import pandas as pd

def parse_pmi_file(file_path):
    pmi_data = []
    
    month_map = {
        'Enero': 1, 'Febrero': 2, 'Marzo': 3, 'Abril': 4, 'Mayo': 5, 'Junio': 6,
        'Julio': 7, 'Agosto': 8, 'Septiembre': 9, 'Octubre': 10, 'Noviembre': 11, 'Diciembre': 12
    }
    
    current_year = None
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Check for year header like "Mes (2020)"
        year_match = re.search(r'Mes \((\d{4})\)', line)
        if year_match:
            current_year = int(year_match.group(1))
            continue
            
        # Skip headers line starting with tab or specific words
        if 'EE. UU.' in line:
            continue
            
        # Parse data lines
        # Expected format: MonthName Value1 Value2 ...
        parts = line.split()
        if not parts:
            continue
            
        month_name = parts[0]
        if month_name in month_map and current_year:
            month_num = month_map[month_name]
            
            # The US ISM value is the first value after the month name
            # Handle potential asterisks or dashes
            try:
                val_str = parts[1].replace('*', '')
                if val_str == '--':
                    continue
                pmi_value = float(val_str)
                
                date_str = f"{current_year}-{month_num:02d}-01"
                pmi_data.append({'DATE': date_str, 'PMI': pmi_value})
            except (ValueError, IndexError):
                continue

    return pd.DataFrame(pmi_data)

if __name__ == "__main__":
    df = parse_pmi_file('/home/daniel/Bot_trading/PMI_anuales')
    print(df)
    # Check if we have data for all expected months
    print(f"Total rows: {len(df)}")
