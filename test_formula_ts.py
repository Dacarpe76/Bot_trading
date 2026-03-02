from kraken_bot import config

t_id = "test"
target_net = 0.50 # let's say trigger is 0.50 EUR
pos = {
    'margin': 20.0,
    'itemized_fees': 0.05,
    'size': 14.32,  # DOT/EUR e.g. 20 EUR / 1.396
    'type': 'LONG'
}
dist_eur = 0.15

# What get_price_for_net_pnl does:
numerator = (target_net - dist_eur) + pos['margin'] + pos.get('itemized_fees', 0.0)
fee_rate = config.FEE_SPOT_TAKER
denominator = pos['size'] * (1 - fee_rate)

ts_price = numerator / denominator
print("TS price:", ts_price)

# Reverse check
gross_pnl = (ts_price - 1.39622) * pos['size']
net = gross_pnl - pos.get('itemized_fees', 0) - (pos['size'] * ts_price * fee_rate)

print("Actual Net at TS:", net)

