import json
import glob
import os
import time

# Fecha objetivo: 2026-03-01 00:00:00 (Timestamp: 1772323200)
TARGET_START_TIME = 1772323200 

def fix_wallets():
    state_files = glob.glob("wallet_state_*.json")
    print(f"Encontrados {len(state_files)} archivos de estado.")
    
    for file_path in state_files:
        try:
            with open(file_path, 'r') as f:
                state = json.load(f)
            
            modified = False
            
            # 1. Armonizar start_time a la fecha de puesta a cero
            if state.get('start_time', 0) != TARGET_START_TIME:
                print(f"Fixing start_time for {file_path}: {state.get('start_time')} -> {TARGET_START_TIME}")
                state['start_time'] = TARGET_START_TIME
                modified = True
            
            # 2. Resetear balances problematicos (como el -0.25 de VectorFlujo)
            # Solo si no hay posiciones abiertas para evitar descuadres
            if not state.get('positions', {}):
                current_balance = state.get('balance', 500.0)
                if current_balance < 450.0: # Umbral para detectar balances incorrectos/negativos
                    print(f"Resetting balance for {file_path}: {current_balance} -> 500.0")
                    state['balance'] = 500.0
                    modified = True

            if modified:
                with open(file_path, 'w') as f:
                    json.dump(state, f, indent=4)
                print(f"Archivo {file_path} actualizado.")
                
        except Exception as e:
            print(f"Error procesando {file_path}: {e}")

if __name__ == "__main__":
    fix_wallets()
