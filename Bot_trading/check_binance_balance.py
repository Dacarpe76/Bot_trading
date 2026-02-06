
import os
import time
import hmac
import hashlib
import requests
import json
from dotenv import load_dotenv

# Load env from Bot_trader/.env
dotenv_path = os.path.join(os.path.dirname(__file__), 'Bot_trader', '.env')
load_dotenv(dotenv_path)

API_KEY = os.getenv('BINANCE_API_KEY')
SECRET_KEY = os.getenv('BINANCE_SECRET_KEY')

BASE_URL = 'https://api.binance.com'

def get_server_time_offset():
    try:
        resp = requests.get(f"{BASE_URL}/api/v3/time")
        server_time = resp.json()['serverTime']
        local_time = int(time.time() * 1000)
        offset = server_time - local_time
        print(f"⏱️ Time Offset calculated: {offset}ms")
        return offset
    except:
        return 0

def get_timestamp(offset=0):
    return int(time.time() * 1000) + offset

def check_account():
    offset = get_server_time_offset()
    
    endpoint = '/api/v3/account'
    params = {
        'timestamp': get_timestamp(offset),
        # recvWindow allows for network delay
        'recvWindow': 5000 
    }
    
    # Helper inside or outside? outside was deleted. restoring locally or outside.
    query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
    signature = hmac.new(SECRET_KEY.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
    query = f"{query_string}&signature={signature}"
    # query = sign_params(params) <--- replaced line
    
    url = f"{BASE_URL}{endpoint}?{query}"
    
    headers = {
        'X-MBX-APIKEY': API_KEY
    }
    
    print(f"📡 Connecting to Binance API...")
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            print("✅ Connection Successful!")
            print(f"   Account Type: {data.get('accountType', 'Unknown')}")
            print(f"   Can Trade: {data.get('canTrade')}")
            print(f"   Can Withdraw: {data.get('canWithdraw')}")
            print(f"   Can Deposit: {data.get('canDeposit')}")
            
            print("\n💰 Balances > 0:")
            has_balance = False
            for asset in data.get('balances', []):
                free = float(asset['free'])
                locked = float(asset['locked'])
                if free > 0 or locked > 0:
                    print(f"   - {asset['asset']}: Free={free}, Locked={locked}")
                    has_balance = True
            
            if not has_balance:
                print("   (No funds found)")
                
        else:
            print(f"❌ Error {response.status_code}: {response.text}")
            
    except Exception as e:
        print(f"❌ Exception: {e}")

if __name__ == "__main__":
    if not API_KEY or not SECRET_KEY:
        print("❌ Error: API Keys not found in .env")
    else:
        # Mask key for printing
        print(f"🔑 Using Key: {API_KEY[:6]}...{API_KEY[-4:]}")
        check_account()
