import json
import glob
import csv
import os
import zipfile
from datetime import datetime

def export_data():
    print("Iniciando consolidación de datos (Versión Standalone)...")
    
    # 1. Consolidar Historial de Operaciones
    all_trades = []
    state_files = glob.glob("wallet_state_*.json")
    
    headers = []
    
    for file in state_files:
        strat_id = file.replace("wallet_state_", "").replace(".json", "")
        try:
            with open(file, 'r') as f:
                state = json.load(f)
                history = state.get('history', [])
                for trade in history:
                    trade['strategy_id'] = strat_id
                    all_trades.append(trade)
                    # Collect all possible keys for headers
                    for key in trade.keys():
                        if key not in headers:
                            headers.append(key)
        except Exception as e:
            print(f"Error procesando {file}: {e}")

    csv_ops_file = "total_operations_history.csv"
    if all_trades:
        try:
            with open(csv_ops_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                writer.writerows(all_trades)
            print(f"Historial consolidado: {len(all_trades)} operaciones en {csv_ops_file}")
        except Exception as e:
            print(f"Error escribiendo CSV: {e}")
            csv_ops_file = None
    else:
        print("No se encontraron operaciones en el historial.")
        csv_ops_file = None

    # 2. Archivos de Mercado
    market_files = ["TRH_Opportunities_Log.csv", "market_research.csv", "bot_activity.log"]
    existing_market_files = [f for f in market_files if os.path.exists(f)]
    
    # 3. Empaquetar todo en un ZIP
    zip_name = f"BT_FULL_DATA_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    try:
        with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Añadir CSV de operaciones
            if csv_ops_file and os.path.exists(csv_ops_file):
                zipf.write(csv_ops_file)
                
            # Añadir archivos de mercado
            for f in existing_market_files:
                zipf.write(f)
                
            # Añadir estados individuales
            for f in state_files:
                zipf.write(f)
        print(f"\n¡Éxito! Archivo consolidado generado: {zip_name}")
    except Exception as e:
        print(f"Error creando ZIP: {e}")
        return None
        
    return zip_name

if __name__ == "__main__":
    zip_result = export_data()
    if zip_result:
        with open("last_export_name.txt", "w") as f:
            f.write(zip_result)
