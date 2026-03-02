from kraken_bot import config

t_id = "test"
target_net = 0.50 
pos = {
    'margin': 20.0,
    'itemized_fees': 0.05,
    'size': 14.32,  
    'type': 'LONG',
    'layer': 'Layer1'
}

dist_eur = 0.15

# From code:
net_val = 0.50 # e.g. currently at 0.50 profit
# if not is_active and net_val >= trigger_eur:
pos['ts_status'] = "ACTIVE"

# The formula in get_price_for_net_pnl is:
# numerator = target_net + pos['margin'] + pos.get('itemized_fees', 0.0)
target_net_stop = net_val - dist_eur
numerator = target_net_stop + pos['margin'] + pos.get('itemized_fees', 0.0)
fee_rate = config.FEE_SPOT_TAKER
denominator = pos['size'] * (1 - fee_rate)
ts_price = numerator / denominator

print("ts_price calculated:", ts_price)

# The real issue is calculating Gross vs Net and getting the correct Price formula.
# We want the price such that:
# Gross = (Price - Avg) * Size
# Net = Gross - Fees_paid - (Size * Price * exit_fee_rate)
# Net = (Price * Size - Avg * Size) - Fees_paid - Price * Size * exit_fee_rate
# Net = Price * Size * (1 - exit_fee_rate) - Avg * Size - Fees_paid
# Price * Size * (1 - exit_fee_rate) = Net + Avg * Size + Fees_paid
# Price = (Net + Avg * Size + Fees_paid) / (Size * (1 - exit_fee_rate))

# Let's compare the code's numerator with the correct one
avg_price = 1.39622
correct_numerator = target_net_stop + (avg_price * pos['size']) + pos.get('itemized_fees', 0.0)
correct_ts_price = correct_numerator / denominator
print("Correct ts_price should be:", correct_ts_price)

print("Wait, what does the code use?")
print("Code uses pos['margin'] instead of (avg_price * pos['size'])")

# In SPOT, margin == avg_price * size (roughly, entry cost).
# In FUTURES, margin == (avg_price * size) / Leverage.
# SentinelTurbo uses LEVERAGE!
# Ah! If leverage is x2, margin is HALF of the position value.
# So numerator is using margin (10 EUR) instead of position value (20 EUR).
# That makes the TS price half of what it should be!

# Let's demonstrate:
leverage = 2
pos['margin'] = (avg_price * pos['size']) / leverage
print("Margin with x2:", pos['margin'])
code_numerator = target_net_stop + pos['margin'] + pos.get('itemized_fees', 0.0)
code_ts = code_numerator / denominator
print("TS price with code formula (using margin):", code_ts)

