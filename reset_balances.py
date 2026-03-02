import os
import json
import glob

def reset_wallets():
    wallet_files = glob.glob('wallet_state_*.json')
    print(f"Found {len(wallet_files)} wallet files.")
    
    for file_path in wallet_files:
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            # Reset balance_eur to 500.0
            # Also reset 'balance' (available cash) to 500.0 if there are no open positions
            # to ensure a clean state.
            old_balance = data.get('balance_eur', 'N/A')
            data['balance_eur'] = 500.0
            
            # If no open positions, we can safely reset the available cash too
            if not data.get('positions'):
                data['balance'] = 500.0
            
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=4)
            
            print(f"Reset {file_path}: {old_balance} -> 500.0")
        except Exception as e:
            print(f"Error processing {file_path}: {e}")

if __name__ == "__main__":
    reset_wallets()
