import glob
import csv
import os

def consolidate_market_research():
    print("Iniciando consolidación de archivos TRH_Research...")
    files = sorted(glob.glob("TRH_Research_*.csv"))
    
    if not files:
        print("No se encontraron archivos TRH_Research.")
        return None
    
    output_file = "TOTAL_MARKET_DATA.csv"
    headers_written = False
    total_rows = 0
    
    with open(output_file, 'w', newline='') as fout:
        for filename in files:
            # Skip copies or temp files if necessary, but here we take all TRH_Research_*.csv
            if "copia" in filename: 
                print(f"Omitiendo copia: {filename}")
                continue
                
            print(f"Procesando: {filename}...")
            try:
                with open(filename, 'r') as fin:
                    reader = csv.reader(fin)
                    header = next(reader)
                    
                    if not headers_written:
                        writer = csv.writer(fout)
                        writer.writerow(header)
                        headers_written = True
                    
                    writer = csv.writer(fout)
                    rows = list(reader)
                    writer.writerows(rows)
                    total_rows += len(rows)
            except Exception as e:
                print(f"Error procesando {filename}: {e}")
                
    print(f"\n¡Éxito! Consolidación completada.")
    print(f"Archivo: {output_file}")
    print(f"Total de filas consolidadas: {total_rows}")
    return output_file

if __name__ == "__main__":
    result = consolidate_market_research()
    if result:
        with open("last_market_export.txt", "w") as f:
            f.write(result)
