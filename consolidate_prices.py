import pandas as pd
import glob
import os

def consolidate_data():
    print("🔍 Buscando archivos TRH_Research_*.csv...")
    files = glob.glob("data/TRH_Research_*.csv")
    if not files:
        print("❌ No se encontraron archivos TRH_Research_*.csv en el directorio actual.")
        return

    print(f"📦 Procesando {len(files)} archivos...")
    all_chunks = []
    
    for file in files:
        try:
            # Usar on_bad_lines='skip' para ignorar líneas de logs de estrategia que rompen el CSV
            df = pd.read_csv(file, on_bad_lines='skip', low_memory=False)
            
            # Asegurarse de que las columnas necesarias existen
            required = ['Timestamp', 'Symbol', 'Open', 'High', 'Low', 'Close', 'Volume']
            if not all(col in df.columns for col in required):
                print(f"⚠️ Saltando {file}: faltan columnas requeridas.")
                continue
            
            # Filtrar filas que sean cabeceras repetidas o basura
            # (El Symbol no debería ser 'Symbol')
            df = df[df['Symbol'] != 'Symbol']
            
            # Convertir precios a numérico, forzando NaN en errores y luego eliminando esos NaN
            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df = df.dropna(subset=required)
            
            # Solo nos quedamos con los datos brutos de precio y volumen
            df = df[required]
            all_chunks.append(df)
        except Exception as e:
            print(f"❌ Error procesando {file}: {e}")

    if not all_chunks:
        print("❌ No hay datos válidos para procesar.")
        return

    print("🔄 Concatenando datos...")
    full_df = pd.concat(all_chunks, ignore_index=True)
    
    print("🕒 Convirtiendo timestamps...")
    # Usar format='mixed' para manejar timestamps con y sin milisegundos
    full_df['Timestamp'] = pd.to_datetime(full_df['Timestamp'], format='mixed', errors='coerce')
    full_df = full_df.dropna(subset=['Timestamp'])
    
    # Redondear al minuto para asegurar alineación perfecta si hubiera milisegundos
    full_df['Timestamp'] = full_df['Timestamp'].dt.floor('min')
    
    print("📈 Remuestreando a velas de 5 minutos...")
    # Agrupamos por Symbol y remuestreamos cada uno
    consolidated = []
    symbols = full_df['Symbol'].unique()
    
    for symbol in symbols:
        symbol_df = full_df[full_df['Symbol'] == symbol].set_index('Timestamp').sort_index()
        
        # Resample OHLCV
        resampled = symbol_df.resample('5min').agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        })
        
        # Eliminar filas vacías resultantes del resample si las hay
        resampled = resampled.dropna(subset=['Open'])
        
        resampled['Symbol'] = symbol
        consolidated.append(resampled.reset_index())

    print("📋 Finalizando y ordenando...")
    final_df = pd.concat(consolidated, ignore_index=True)
    # Ordenar por Symbol y luego Timestamp
    final_df = final_df.sort_values(['Symbol', 'Timestamp'])
    
    output_path = "data/consolidated_5m_prices.csv"
    os.makedirs("data", exist_ok=True)
    final_df.to_csv(output_path, index=False)
    
    print(f"✅ Archivo creado exitosamente en {output_path}")
    print(f"📊 Total de velas de 5m: {len(final_df)}")
    print(f"🪙 Monedas procesadas: {', '.join(symbols)}")

if __name__ == "__main__":
    consolidate_data()
