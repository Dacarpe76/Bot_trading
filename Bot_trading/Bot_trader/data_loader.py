import yfinance as yf
import pandas as pd

import pandas_datareader.data as web
import datetime
import requests
from io import StringIO
import bot_config as config

class MarketData:
    def __init__(self):
        self.btc_symbol = config.SYMBOL_BTC
        self.gold_symbol = config.SYMBOL_GOLD
        
    def get_market_data(self, period="5y", start_date=None):
        """Descarga datos históricos de Yahoo Finance"""
        print(f"Descargando datos para {self.btc_symbol} y {self.gold_symbol}...")
        
        if start_date:
             # Yahoo finance espera YYYY-MM-DD
             btc = yf.Ticker(self.btc_symbol).history(start=start_date, interval="1d")
             gold = yf.Ticker(self.gold_symbol).history(start=start_date, interval="1d")
        else:
             btc = yf.Ticker(self.btc_symbol).history(period=period, interval="1d")
             gold = yf.Ticker(self.gold_symbol).history(period=period, interval="1d")
        
        # Limpieza básica
        if btc.empty:
            print(f"ERROR: No se descargaron datos para {self.btc_symbol}")
        if gold.empty:
            print(f"ERROR: No se descargaron datos para {self.gold_symbol}")
            
        print(f"BTC records: {len(btc)}, Gold records: {len(gold)}")
        
        btc = btc[['Close']].rename(columns={'Close': 'BTC_Close'})
        gold = gold[['Close']].rename(columns={'Close': 'GOLD_Close'})
        
        # Eliminar zona horaria si existe para facilitar merge
        btc.index = btc.index.tz_localize(None)
        gold.index = gold.index.tz_localize(None)
        
        # Unir DataFrames (inner join para tener datos coincidents)
        data = pd.concat([btc, gold], axis=1, join='inner').dropna()
        
        print(f"Registros coincidentes tras merge: {len(data)}")
        
        if data.empty:
            print("ADVERTENCIA: DataFrame combinado está vacío. Verifique símbolos o fechas.")
            
        return data

    def get_current_price(self, symbol):
        """Obtiene el precio actual (último cierre disponible en simulación)"""
        ticker = yf.Ticker(symbol)
        try:
             price = ticker.fast_info['last_price']
        except:
             data = ticker.history(period='1d')
             if not data.empty:
                 price = data['Close'].iloc[-1]
             else:
                 price = 0.0
        return price

    def get_pmi_data_fred(self, start_date, end_date):
        """Descarga PMI (intenta local, luego FRED, luego default)."""
        print(f"Obteniendo datos PMI [{start_date} - {end_date}]...")
        
        # 1. Intentar Cargar Local
        try:
            print("Buscando 'pmi_history.csv' local...")
            pmi = pd.read_csv('pmi_history.csv', parse_dates=['DATE'], index_col='DATE')
            pmi.rename(columns={'NAPMPMI': 'PMI'}, inplace=True) # Por si acaso tiene header viejo
            
            pmi_daily = pmi.resample('D').ffill()
            pmi_daily = pmi_daily.loc[start_date:end_date]
            print(f"Datos PMI LOCALES cargados: {len(pmi_daily)} días.")
            return pmi_daily
        except Exception as e:
            print(f"No se pudo cargar local ({e}). Intentando FRED...")

        # 2. Intentar FRED (Legacy fallback)
        fred_url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=NAPMPMI"
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(fred_url, headers=headers)
            if response.status_code == 200:
                csv_data = StringIO(response.text)
                pmi = pd.read_csv(csv_data, parse_dates=['DATE'], index_col='DATE')
                pmi.rename(columns={'NAPMPMI': 'PMI'}, inplace=True)
                pmi_daily = pmi.resample('D').ffill()
                pmi_daily = pmi_daily.loc[start_date:end_date]
                return pmi_daily
        except:
            pass
            
        # 3. Default
        print("Usando valor por defecto constante.")
        dates = pd.date_range(start=start_date, end=end_date)
        return pd.DataFrame({'PMI': config.PMI_DEFAULT}, index=dates)

    def get_macro_data(self, start_date, end_date):
        """Descarga VIX (Yahoo) y TIPS 10Y (FRED)"""
        print(f"Obteniendo datos Macro (VIX, TIPS) [{start_date} - {end_date}]...")
        
        # 1. VIX (Yahoo Finance)
        try:
            vix = yf.Ticker("^VIX").history(start=start_date, end=end_date, interval="1d")
            vix = vix[['Close']].rename(columns={'Close': 'VIX'})
            vix.index = vix.index.tz_localize(None)
        except Exception as e:
            print(f"Error descargando VIX: {e}")
            vix = pd.DataFrame()

        # 2. TIPS 10Y (FRED: DFII10) and Fed Funds Rate (FRED: DFF)
        # Real Yield 10 Year & Interest Rates
        try:
            fred_data = web.DataReader(['DFII10', 'DFF'], 'fred', start_date, end_date)
            fred_data.rename(columns={'DFII10': 'TIPS', 'DFF': 'FED_RATE'}, inplace=True)
        except Exception as e:
            print(f"Error descargando datos FRED: {e}")
            fred_data = pd.DataFrame()
            
        # Unificar
        macro = pd.concat([vix, fred_data], axis=1)
        
        # Rellenar (forward fill para fines de semana/festivos)
        macro = macro.ffill().fillna(0.0) # 0.0 es un riesgo si no hay datos, ojo
        
        # Recortar al rango solicitado
        macro = macro.loc[start_date:end_date]
        
        print(f"Datos Macro cargados: {len(macro)} registros.")
        return macro

    def get_pmi_data(self):
        """Legacy wrapper (single value) - No usar en backtest histórico real"""
        return config.PMI_DEFAULT
