
import pandas as pd

class Policy:
    def __init__(self):
        # Configuración de Bandas USDC (Cash)
        self.BANDA_USDC = {
            "NEUTRAL":      (0.15, 0.40),
            "BULL_FUERTE":  (0.10, 0.25),
            "RIESGO_ALTO":  (0.40, 0.60)
        }
        
        # Umbrales
        self.TAKE_PROFIT = 0.30
        self.STRONG_TP = 0.60
        self.MAX_LOSS_SELL = -0.20 # Sólo vender en pérdida si < -20% Y Riesgo Alto
    
    def detectar_regimen(self, pmi, tips, vix, fed_rate_delta=0.0):
        """
        Define el régimen de mercado basado en Macro.
        PMI: ISM Manufacturing (>50 expansión, >55 fuerte)
        TIPS: 10Y Real Yield
        VIX: Volatilidad
        fed_rate_delta: Cambio en tasas de interés (3 meses). > 0.5 indica ciclo subidas agresivo.
        """
        # Ajuste de umbrales basado en sentido común macro actual
        
        # Bull Fuerte: Crecimiento sólido (PMI>55), dinero barato (TIPS<1.5), calma (VIX<15), no subidas agresivas
        if pmi > 55 and tips < 2.0 and vix < 20 and fed_rate_delta < 0.25: 
            return "BULL_FUERTE"
            
        # Riesgo Alto: 
        # 1. Contracción (PMI<48)
        # 2. Estrés Financiero (TIPS>2.5 o VIX>30)
        # 3. Subidas Agresivas de Tipos (fed_rate_delta > 0.5% en 3 meses) -> Mata valoraciones
        if pmi < 48 or tips > 2.5 or vix > 30 or fed_rate_delta > 0.5:
            return "RIESGO_ALTO"
            
        return "NEUTRAL"
        
    def aplicar_politica(self, raw_weights, current_prices, holdings, avg_prices, regimen):
        """
        Orquesta la política de cartera:
        1. Ajustar por beneficios (Take Profit)
        2. Gestión de Stop Loss condicional (en Riesgo Alto)
        3. Aplicar bandas de USDC según régimen
        """
        w_btc = raw_weights.get('btc_weight', 0.0)
        w_gold = raw_weights.get('gold_weight', 0.0)
        # El resto implícito es USDC inicial, pero recalcularemos
        w_usdc = 1.0 - (w_btc + w_gold)
        
        # Estado actual de PnL latente
        btc_price = current_prices.get('BTC', 0)
        gold_price = current_prices.get('GOLD', 0)
        
        if btc_price == 0: btc_price = 1.0 # Avoid zero div
        if gold_price == 0: gold_price = 1.0

        cost_btc = avg_prices.get('BTC', 0)
        if cost_btc == 0: cost_btc = btc_price
        
        cost_gold = avg_prices.get('GOLD', 0)
        if cost_gold == 0: cost_gold = gold_price
        
        gain_btc = (btc_price - cost_btc) / cost_btc
        gain_gold = (gold_price - cost_gold) / cost_gold
        
        log_reasons = []

        # --- 1. Ajuste por Beneficios (Take Profit) ---
        # Si RIESGO_ALTO, forzamos venta parcial si hay ALGÚN beneficio
        if regimen == "RIESGO_ALTO":
            if gain_btc > 0.0:
                shift = 0.05
                if w_btc >= shift:
                    w_btc -= shift
                    w_usdc += shift
                    log_reasons.append(f"TP DEFENSA (BTC +{gain_btc:.1%})")
            if gain_gold > 0.0:
                shift = 0.03
                if w_gold >= shift:
                    w_gold -= shift
                    w_usdc += shift
                    log_reasons.append(f"TP DEFENSA (GOLD +{gain_gold:.1%})")

        # Si BULL_FUERTE, take profit solo si ganancias muy grandes
        elif regimen == "BULL_FUERTE":
            if gain_btc > self.STRONG_TP: # >60%
                shift = 0.05
                w_btc -= shift
                w_usdc += shift
                log_reasons.append(f"TP BULL STRONG (BTC +{gain_btc:.1%})")
                
        # --- 2. Stop Loss Condicional ---
        # "No vender en pérdida salvo que régimen sea RIESGO_ALTO y pérdida > 20%"
        # Esto lo manejamos ajustando los pesos. Si el peso baja, portfolio intentará vender.
        
        force_sell_loss = False
        if regimen == "RIESGO_ALTO":
            # Si la pérdida es catastrófica, reducimos exposición
            if gain_btc < self.MAX_LOSS_SELL: # < -20%
                shift = 0.05
                if w_btc >= shift:
                    w_btc -= shift
                    w_usdc += shift
                    force_sell_loss = True
                    log_reasons.append(f"STOP LOSS MACRO (BTC {gain_btc:.1%})")
                    
        # --- 3. Clamp Bandas USDC ---
        min_usdc, max_usdc = self.BANDA_USDC.get(regimen, (0.15, 0.40))
        
        # Asegurar USDC dentro de banda
        w_usdc = max(min_usdc, min(max_usdc, w_usdc))
        
        # Re-normalizar BTC/Oro manteniendo proporción
        rest_risk = 1.0 - w_usdc
        total_risk = w_btc + w_gold
        
        if total_risk > 0:
            w_btc = rest_risk * (w_btc / total_risk)
            w_gold = rest_risk * (w_gold / total_risk)
        else:
            w_btc = 0
            w_gold = 0 # Todo a cash
            
        return {
            'btc_weight': w_btc,
            'gold_weight': w_gold,
            'usdc_weight': w_usdc, # Nuevo explícito
            'regimen': regimen,
            'force_sell_loss': force_sell_loss,
            'policy_log': log_reasons
        }
