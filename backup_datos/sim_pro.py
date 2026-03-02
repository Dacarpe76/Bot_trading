import pandas as pd
import glob
import os
import numpy as np

# --- Configuración Dynamic DCA ---
INIT_BALANCE = 500.0
TP_NET_PCT = 1.0  # +1% neto
# Entrada = Balance / 50
# DCA = 1% de entrada cada 1% de caída desde precio entrada

def load_mixed_data():
    archivos = sorted(glob.glob("TRH_Research_2026_*.csv"))
    if not archivos:
        print("❌ No se ven los archivos TRH_Research. ¿Estás en la carpeta correcta?")
        return None, None
    
    print(f"📂 Procesando {len(archivos)} archivos de research (carga robusta)...")
    
    event_rows = []
    price_rows = []
    
    HEADERS_36 = [
        'Timestamp','Symbol','Event','Strategy_ID','Price',
        'Open','High','Low','Close','Volume',
        'ATR_14','Bollinger_Upper','Bollinger_Lower','Bollinger_Width',
        'MFI_14','OBV','Volume_Mean_20',
        'Stoch_K','Stoch_D','Stoch_RSI_K','ADX_14',
        'Candle_Body_Size','Upper_Wick_Size','Lower_Wick_Size','Wick_Body_Ratio',
        'Pivot_P','Pivot_R1','Pivot_S1',
        'Dist_EMA200_Pct','Current_Trend_1h','Fibonacci_Level',
        'VRel','ERR','PinBar','Decision_Log','Market_Regime'
    ]
    
    HEADERS_33 = [
        'Timestamp','Symbol','Open','High','Low','Close','Volume',
        'ATR_14','Bollinger_Upper','Bollinger_Lower','Bollinger_Width',
        'MFI_14','OBV','Volume_Mean_20',
        'Stoch_K','Stoch_D','Stoch_RSI_K','ADX_14',
        'Candle_Body_Size','Upper_Wick_Size','Lower_Wick_Size','Wick_Body_Ratio',
        'Pivot_P','Pivot_R1','Pivot_S1',
        'Dist_EMA200_Pct','Current_Trend_1h','Fibonacci_Level',
        'VRel','ERR','PinBar','Decision_Log','Active_Pos_Count'
    ]

    for f in archivos:
        try:
            with open(f, 'r') as file:
                lines = file.readlines()
                for line in lines:
                    if line.startswith('Timestamp'): continue 
                    parts = line.strip().split(',')
                    if len(parts) == 36:
                        event_rows.append(parts)
                    elif len(parts) == 33:
                        price_rows.append(parts)
                    elif len(parts) >= 34:
                         if 'Open_DCA_V2' in parts: event_rows.append(parts[:36])
                         else: price_rows.append(parts[:33])
        except Exception as e:
            print(f"⚠️ Error leyendo {f}: {e}")

    df_events = pd.DataFrame(event_rows, columns=HEADERS_36)
    df_price = pd.DataFrame(price_rows, columns=HEADERS_33)
    
    for df in [df_events, df_price]:
        if df.empty: continue
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
        for col in ['Open', 'High', 'Low', 'Close', 'Price']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
    
    df_events = df_events.dropna(subset=['Timestamp']).sort_values(['Symbol', 'Timestamp'])
    df_price = df_price.dropna(subset=['Timestamp']).sort_values(['Symbol', 'Timestamp'])
    
    return df_events, df_price

def simular_dynamic_dca():
    df_events, df_price = load_mixed_data()
    if df_events is None or df_events.empty:
        print("❌ No se encontraron eventos.")
        return

    entradas = df_events[
        (df_events['Strategy_ID'] == 'RollingDCA_v2') & 
        (df_events['Event'] == 'Open_DCA_V2')
    ].copy()

    print(f"🎯 Entradas detectadas: {len(entradas)}")
    if len(entradas) == 0: return

    realized_balance = INIT_BALANCE
    floating_pnl = 0.0
    closed_count = 0
    hold_count = 0
    total_realized_pnl = 0.0

    for _, entry in entradas.iterrows():
        symbol = entry['Symbol']
        entry_time = entry['Timestamp']
        entry_price = entry['Price']
        
        futuro = df_price[(df_price['Symbol'] == symbol) & (df_price['Timestamp'] >= entry_time)]
        if futuro.empty: continue
        
        # Lógica de Usuario:
        # 1. Entrada = Balance Actual / 50
        base_size_eur = realized_balance / 50.0
        dca_unit_eur = base_size_eur * 0.01 # 1% de la entrada
        
        pos_qty = base_size_eur / entry_price
        avg_price = entry_price
        total_invested = base_size_eur
        
        # DCA: 1% de entrada cada 1% de caída desde PRECIO DE ENTRADA
        # Trigger levels: 0.99, 0.98, 0.97... del entry_price original
        last_dca_level = 0 # 0% drop
        
        exit_price = None
        
        # Trailing Stop Config
        TS_ACTIVATION_PCT = 1.0 # Activa al +1%
        TS_DISTANCE_PCT = 0.3   # Distancia de 0.3%
        
        ts_active = False
        ts_stop_level_pct = -100.0
        
        for _, candle in futuro.iloc[1:].iterrows():
            low_p = candle['Low']
            high_p = candle['High']
            
            # --- Lógica de Trailing Stop ---
            current_high_pnl = (high_p - avg_price) / avg_price * 100.0
            current_low_pnl = (low_p - avg_price) / avg_price * 100.0
            
            # 1. Activar / Actualizar Trailing
            if current_high_pnl >= TS_ACTIVATION_PCT:
                ts_active = True
                potential_stop = current_high_pnl - TS_DISTANCE_PCT
                if potential_stop > ts_stop_level_pct:
                    ts_stop_level_pct = potential_stop
            
            # 2. Verificar si el stop salta
            if ts_active and current_low_pnl <= ts_stop_level_pct:
                exit_price = avg_price * (1 + (ts_stop_level_pct / 100.0))
                break
                
            # 3. Verificar DCA (Cada 1% desde Entry Price)
            drop_from_entry = (entry_price - low_p) / entry_price
            target_dca_level = int(drop_from_entry * 100) # ej: 0.034 -> 3
            
            if target_dca_level > last_dca_level:
                # Compraríamos por cada nivel cruzado entre last y target
                for level in range(last_dca_level + 1, target_dca_level + 1):
                    buy_price = entry_price * (1 - (level / 100.0))
                    # Si el low de la vela es más bajo que el nivel, compramos al nivel (orden limitada)
                    # Si ya empezamos la vela por debajo, compramos al low o entry corregido
                    # Por simplicidad: compramos al nivel exacto
                    buy_qty = dca_unit_eur / buy_price
                    
                    # Update average
                    new_total_qty = pos_qty + buy_qty
                    new_total_val = (pos_qty * avg_price) + (buy_qty * buy_price)
                    avg_price = new_total_val / new_total_qty
                    
                    pos_qty = new_total_qty
                    total_invested += dca_unit_eur
                
                last_dca_level = target_dca_level
        
        if exit_price:
            profit = (pos_qty * exit_price) - total_invested
            realized_balance += profit
            total_realized_pnl += profit
            closed_count += 1
        else:
            last_p = futuro.iloc[-1]['Close']
            u_pnl = (pos_qty * last_p) - total_invested
            floating_pnl += u_pnl
            hold_count += 1

    print(f"\n--- ESTUDIO ESTRATEGIA: Dynamic DCA (Custom) ---")
    print(f"💰 Balance Inicial: {INIT_BALANCE:.2f}€")
    print(f"✅ Cerradas (TP 1%): {closed_count}")
    print(f"⏳ En HOLD (Open): {hold_count}")
    print(f"------------------------------------------")
    print(f"💵 Realized PnL: {total_realized_pnl:+.2f}€")
    print(f"📉 Floating (Hold): {floating_pnl:+.2f}€")
    print(f"🏦 Balance Realizado: {realized_balance:.2f}€")
    print(f"📊 ROI (Cerradas): {((realized_balance/INIT_BALANCE)-1)*100:+.2f}%")
    print(f"📈 Net Equity (Inc. Hold): {((realized_balance + floating_pnl)/INIT_BALANCE - 1)*100:+.2f}%")

if __name__ == "__main__":
    simular_dynamic_dca()