import csv
import os

def merge_all_market_data():
    print("Iniciando fusión total de datos de mercado (Robust Mode)...")
    research_file = "TOTAL_MARKET_DATA.csv"
    ops_log_file = "TRH_Opportunities_Log.csv"
    output_file = "CONSOLIDADO_MERCADO_TOTAL.csv"
    
    if not os.path.exists(research_file):
        print(f"Error: {research_file} no existe.")
        return
        
    all_headers = []
    
    # 1. Collect all unique headers
    with open(research_file, 'r', errors='ignore') as f:
        reader = csv.reader(f)
        try:
            h = next(reader)
            all_headers.extend([x.strip() for x in h if x.strip()])
        except StopIteration:
            pass

    if os.path.exists(ops_log_file):
        with open(ops_log_file, 'r', errors='ignore') as f:
            reader = csv.reader(f)
            try:
                h = next(reader)
                for x in h:
                    x = x.strip()
                    if x and x not in all_headers:
                        all_headers.append(x)
            except StopIteration:
                pass
    
    print(f"Columnas detectadas en total: {len(all_headers)}")
    
    with open(output_file, 'w', newline='') as fout:
        writer = csv.DictWriter(fout, fieldnames=all_headers, extrasaction='ignore')
        writer.writeheader()
        
        # Write Research Data
        print("Escribiendo datos de investigación...")
        with open(research_file, 'r', errors='ignore') as fin:
            reader = csv.DictReader(fin)
            # Ensure keys are stripped
            for row in reader:
                # Clean keys just in case
                clean_row = { (k.strip() if k else None): v for k, v in row.items() }
                writer.writerow(clean_row)
                
        # Write Ops Log Data
        if os.path.exists(ops_log_file):
            print("Escribiendo logs de oportunidades...")
            with open(ops_log_file, 'r', errors='ignore') as fin:
                reader = csv.DictReader(fin)
                for row in reader:
                    clean_row = { (k.strip() if k else None): v for k, v in row.items() }
                    writer.writerow(clean_row)
                    
    print(f"\n¡Éxito! Archivo consolidado total: {output_file}")
    return output_file

if __name__ == "__main__":
    result = merge_all_market_data()
    if result:
        with open("last_market_total.txt", "w") as f:
            f.write(result)
