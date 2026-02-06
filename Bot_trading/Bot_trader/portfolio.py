from datetime import datetime
import bot_config as config

class PaperPortfolio:
    def __init__(self):
        self.cash = config.INITIAL_CASH
        self.holdings = {
            'BTC': 0.0,
            'GOLD': 0.0
        }
        # Precio promedio de compra ponderado (Weighted Average Price)
        self.avg_price = {
            'BTC': 0.0,
            'GOLD': 0.0
        }
        self.history = []
        self.trade_log = []
        
    def get_total_value(self, current_prices):
        """Calcula el valor total de la cartera en Euros"""
        btc_val = self.holdings['BTC'] * current_prices['BTC']
        gold_val = self.holdings['GOLD'] * current_prices['GOLD']
        return self.cash + btc_val + gold_val

    def rebalance(self, policy_result, current_prices, date):
        """
        Rebalancea la cartera hacia los pesos definidos por la política.
        policy_result: dict con keys 'btc_weight', 'gold_weight', 'usdc_weight', 'force_sell_loss', ...
        """
        target_btc_weight = policy_result.get('btc_weight', 0.0)
        target_gold_weight = policy_result.get('gold_weight', 0.0)
        # target_usdc_weight es el resto
        
        force_sell_loss = policy_result.get('force_sell_loss', False)
        regimen = policy_result.get('regimen', 'UNKNOWN')
        reasons = policy_result.get('policy_log', [])
        
        total_value = self.get_total_value(current_prices)
        
        target_btc_val = total_value * target_btc_weight
        target_gold_val = total_value * target_gold_weight
        
        current_btc_val = self.holdings['BTC'] * current_prices['BTC']
        current_gold_val = self.holdings['GOLD'] * current_prices['GOLD']
        
        log_ops = []
        if reasons:
            log_ops.append(f"POLICY: {regimen} | " + ", ".join(reasons))
        
        # BTC
        diff_btc = target_btc_val - current_btc_val
        if abs(diff_btc) > 10.0: 
            if diff_btc > 0:
                # Comprar BTC
                cost = diff_btc
                if self.cash >= cost:
                    price = current_prices['BTC']
                    units_to_buy = cost / price
                    
                    old_units = self.holdings['BTC']
                    new_units = old_units + units_to_buy
                    if new_units > 0:
                        self.avg_price['BTC'] = ((old_units * self.avg_price['BTC']) + (units_to_buy * price)) / new_units
                    
                    self.cash -= cost
                    self.holdings['BTC'] += units_to_buy
                    
                    op_str = f"BUY  BTC: {units_to_buy:.6f} u. | Cost: {cost:.2f}€"
                    log_ops.append(op_str)
                    
                    self.trade_log.append({
                        'Date': date,
                        'Action': 'BUY',
                        'Asset': 'BTC',
                        'Amount': units_to_buy,
                        'Price': price,
                        'Value': -cost,
                        'Profit': 0.0,
                        'Cash_After': self.cash,
                        'BTC_After': self.holdings['BTC'],
                        'GOLD_After': self.holdings['GOLD']
                    })
            else:
                # Vender BTC
                price = current_prices['BTC']
                avg_buy_price = self.avg_price['BTC']
                
                # REGLA DE VENTA:
                # HODL si (Precio < Avg) Y (NO es venta forzada por política)
                is_loss = (price < avg_buy_price and avg_buy_price > 0)
                
                if is_loss and not force_sell_loss:
                    op_str = f"HODL BTC: Price {price:.2f} < Avg {avg_buy_price:.2f} | HODL por Regla (Régimen {regimen})"
                    log_ops.append(op_str)
                else:
                    # Ejecutar venta
                    sell_val = abs(diff_btc)
                    units_to_sell = sell_val / price
                    profit = (price - avg_buy_price) * units_to_sell if avg_buy_price > 0 else 0.0
                    
                    self.holdings['BTC'] -= units_to_sell
                    self.cash += sell_val
                    
                    tag = " | STOP-LOSS" if (is_loss and force_sell_loss) else ""
                    op_str = f"SELL BTC: {units_to_sell:.6f} u. | Val: {sell_val:.2f}€ | PnL: {profit:.2f}€{tag}"
                    log_ops.append(op_str)
                    
                    self.trade_log.append({
                        'Date': date,
                        'Action': 'SELL',
                        'Asset': 'BTC',
                        'Amount': units_to_sell,
                        'Price': price,
                        'Value': sell_val,
                        'Profit': profit,
                        'Cash_After': self.cash,
                        'BTC_After': self.holdings['BTC'],
                        'GOLD_After': self.holdings['GOLD']
                    })
                
        # GOLD
        diff_gold = target_gold_val - current_gold_val
        if abs(diff_gold) > 10.0: 
            if diff_gold > 0:
                # Comprar GOLD
                cost = diff_gold
                if self.cash >= cost:
                    price = current_prices['GOLD']
                    units_to_buy = cost / price
                    
                    old_units = self.holdings['GOLD']
                    new_units = old_units + units_to_buy
                    if new_units > 0:
                        self.avg_price['GOLD'] = ((old_units * self.avg_price['GOLD']) + (units_to_buy * price)) / new_units

                    self.cash -= cost
                    self.holdings['GOLD'] += units_to_buy
                    
                    op_str = f"BUY  GOLD: {units_to_buy:.6f} u. | Cost: {cost:.2f}€"
                    log_ops.append(op_str)

                    self.trade_log.append({
                        'Date': date,
                        'Action': 'BUY',
                        'Asset': 'GOLD',
                        'Amount': units_to_buy,
                        'Price': price,
                        'Value': -cost,
                        'Profit': 0.0,
                        'Cash_After': self.cash,
                        'BTC_After': self.holdings['BTC'],
                        'GOLD_After': self.holdings['GOLD']
                    })
            else:
                # Vender GOLD
                price = current_prices['GOLD']
                avg_buy_price = self.avg_price['GOLD']
                
                is_loss = (price < avg_buy_price and avg_buy_price > 0)
                
                if is_loss and not force_sell_loss:
                    op_str = f"HODL ORO: Price {price:.2f} < Avg {avg_buy_price:.2f} | HODL por Regla (Régimen {regimen})"
                    log_ops.append(op_str)
                    
                else:
                    sell_val = abs(diff_gold)
                    units_to_sell = sell_val / price
                    profit = (price - avg_buy_price) * units_to_sell if avg_buy_price > 0 else 0.0

                    self.holdings['GOLD'] -= units_to_sell
                    self.cash += sell_val
                    
                    tag = " | STOP-LOSS" if (is_loss and force_sell_loss) else ""
                    op_str = f"SELL GOLD: {units_to_sell:.6f} u. | Val: {sell_val:.2f}€ | PnL: {profit:.2f}€{tag}"
                    log_ops.append(op_str)

                    self.trade_log.append({
                        'Date': date,
                        'Action': 'SELL',
                        'Asset': 'GOLD',
                        'Amount': units_to_sell,
                        'Price': price,
                        'Value': sell_val,
                        'Profit': profit,
                        'Cash_After': self.cash,
                        'BTC_After': self.holdings['BTC'],
                        'GOLD_After': self.holdings['GOLD']
                    })

        return log_ops

    def add_monthly_contribution(self, date=None, amount=None):
        """Simula el aporte mensual de capital"""
        contribution = amount if amount is not None else config.SIMULAR_APORTE_MENSUAL
        self.cash += contribution
        
        self.trade_log.append({
            'Date': date if date else datetime.now(),
            'Action': 'DEPOSIT',
            'Asset': 'CASH',
            'Amount': contribution,
            'Price': 1.0,
            'Value': contribution,
            'Profit': 0.0,
            'Cash_After': self.cash,
            'BTC_After': self.holdings['BTC'],
            'GOLD_After': self.holdings['GOLD']
        })
        
        return f"Aporte Mensual: +{contribution}€ añadidos a Cash."

    def record_daily_status(self, date, current_prices, pmi_val):
        """Registra el estado diario de la cartera en el historial"""
        total_val = self.get_total_value(current_prices)
        self.history.append({
            'Date': date,
            'TotalValue': total_val,
            'Cash': self.cash,
            'BTC_Units': self.holdings['BTC'],
            'BTC_Price': current_prices['BTC'],
            'GOLD_Units': self.holdings['GOLD'],
            'GOLD_Price': current_prices['GOLD'],
            'PMI': pmi_val
        })

    def get_status_str(self, current_prices):
        val = self.get_total_value(current_prices)
        btc_val = self.holdings['BTC'] * current_prices['BTC']
        gold_val = self.holdings['GOLD'] * current_prices['GOLD']
        
        # Calcular retorno si hay historial
        roi_str = ""
        if len(self.history) > 0:
            initial = config.INITIAL_CAPITAL # O usar el primer registro
            # Nota: el ROI se complica con aportes, simplificamos a Valor Total
            
        return (f"PORTFOLIO STATUS:\n"
                f"  Total Value: {val:.2f}€\n"
                f"  Cash:        {self.cash:.2f}€\n"
                f"  BTC:         {self.holdings['BTC']:.6f} u. ({btc_val:.2f}€)\n"
                f"  GOLD:        {self.holdings['GOLD']:.6f} u. ({gold_val:.2f}€)")
