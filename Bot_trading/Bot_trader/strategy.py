import ta
import pandas as pd
import bot_config as config

class Strategy:
    def __init__(self):
        self.rsi_period = config.RSI_PERIOD
        self.sma_fast = config.SMA_FAST
        self.sma_slow = config.SMA_SLOW
        self.pmi_threshold = config.PMI_THRESHOLD

    def calculate_indicators(self, data):
        """Calcula medias móviles y RSI sobre el DataFrame de datos"""
        # Calcular indicadores para BTC
        data['BTC_RSI'] = ta.momentum.RSIIndicator(close=data['BTC_Close'], window=self.rsi_period).rsi()
        data['BTC_SMA50'] = ta.trend.SMAIndicator(close=data['BTC_Close'], window=self.sma_fast).sma_indicator()
        data['BTC_SMA200'] = ta.trend.SMAIndicator(close=data['BTC_Close'], window=self.sma_slow).sma_indicator()
        
        # Calcular indicadores para ORO
        data['GOLD_RSI'] = ta.momentum.RSIIndicator(close=data['GOLD_Close'], window=self.rsi_period).rsi()
        data['GOLD_SMA50'] = ta.trend.SMAIndicator(close=data['GOLD_Close'], window=self.sma_fast).sma_indicator()
        data['GOLD_SMA200'] = ta.trend.SMAIndicator(close=data['GOLD_Close'], window=self.sma_slow).sma_indicator()
        
        return data


    def get_signal(self, current_data_row, pmi_value):
        """
        Determina la asignación de activos basada en PMI y Técnico.
        Retorna un diccionario con los pesos objetivo para BTC y GOLD.
        """
        signal_log = []
        
        # --- FILTRO DE SEGURIDAD (SMA 200) ---
        # Si el precio está por debajo de la media de 200 días, estamos en BEAR MARKET.
        # En este caso, ignoramos señales macro positivas y somos defensivos.
        btc_price = current_data_row['BTC_Close']
        btc_sma200 = current_data_row.get('BTC_SMA200', 0)
        
        is_bear_trend = False
        if btc_sma200 > 0 and btc_price < btc_sma200:
            is_bear_trend = True
            signal_log.append(f"TREND ALERT: Price ({btc_price:.2f}) < SMA200 ({btc_sma200:.2f}). Mercado Bajista.")
        
        # Regla 1: MACRO - PMI (Predictor de Ciclo)
        # Si PMI < 47 (Contracción) OR Tendencia Bajista -> Preferencia ORO (Refugio)
        if pmi_value < self.pmi_threshold or is_bear_trend:
            if is_bear_trend:
                signal_log.append(f"DEFENSE MODE: Activado por SMA200 (aunque PMI sea {pmi_value})")
            else:
                signal_log.append(f"MACRO ALERT: PMI {pmi_value} < {self.pmi_threshold}. Contracción Económica Detectada.")
            
            # ESTRATEGIA SHORT:
            # En lugar de solo reducir exposición (0.2), nos ponemos cortos (-0.2)
            # para ganar dinero con la caída.
            # Mantenemos Oro como cobertura principal (0.8).
            # Cash implícito será: 1.0 - (-0.2 + 0.8) = 0.4 (40% Cash real + dinero de la venta corta)
            target_btc = -0.2
            target_gold = 0.8
        else:
            signal_log.append(f"MACRO OK: PMI {pmi_value} >= {self.pmi_threshold}. Expansión/Normalidad.")
            target_btc = 0.6
            target_gold = 0.4

        # Regla 2: TÉCNICO - RSI (Sobreventa/Sobrecompra extremos)
        # Ajuste fino sobre la asignación base
        btc_rsi = current_data_row.get('BTC_RSI', 50)
        
        if btc_rsi < config.RSI_OVERSOLD:
            signal_log.append(f"RSI ALERT: BTC Oversold ({btc_rsi:.2f}). Oportunidad de acumulación.")
            # Si estamos en zona de compra fuerte, incrementamos exposición BTC ligeramente si no estamos en crisis total
            # Aceptamos acumular un poco incluso en bear trend si está muy sobrevendido (rebote gato muerto)
            if pmi_value >= self.pmi_threshold: 
                target_btc += 0.1
                target_gold -= 0.1
                
        elif btc_rsi > config.RSI_OVERBOUGHT:
            signal_log.append(f"RSI ALERT: BTC Overbought ({btc_rsi:.2f}). Tomar ganancias parciales.")
            # Reducir exposición BTC
            target_btc -= 0.1
            target_gold += 0.1
        
        # Normalizar pesos (asegurar que sumen 1.0, el resto va a Cash implícitamente si se desea, 
        # pero aquí simplificamos a asignación total entre activos + cash si no suma 1)
        # En este modelo simple, asumimos 100% invertido entre BTC y Gold salvo cash de reserva
        
        # Limites 0-1
        target_btc = max(0.0, min(1.0, target_btc))
        target_gold = max(0.0, min(1.0, target_gold))
        
        # Re-normalizar si suman > 1
        total = target_btc + target_gold
        if total > 1.0:
            target_btc /= total
            target_gold /= total
            
        return {
            'btc_weight': target_btc, 
            'gold_weight': target_gold,
            'log': signal_log
        }
