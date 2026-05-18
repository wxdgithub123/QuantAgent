from hummingbot.client.settings import AllConnectorSettings
s = AllConnectorSettings()

# Check what trading pairs binance (spot) supports
binance = s.get_connector_settings().get('binance')
if binance:
    try:
        inst = binance.non_trading_connector_instance_with_default_configuration(trading_pairs=['BTC-USDT', 'BTC-USDT-PERP'])
        print(f'Instance: {type(inst).__name__}')
        print(f'Status: {inst.status}')
    except Exception as e:
        print(f'Error: {e}')

# Also check binance_perpetual
bp = s.get_connector_settings().get('binance_perpetual')
if bp:
    try:
        inst2 = bp.non_trading_connector_instance_with_default_configuration(trading_pairs=['BTC-USDT'])
        print(f'Perp Instance: {type(inst2).__name__}')
        print(f'Perp status: {inst2.status}')
    except Exception as e:
        print(f'Perp Error: {e}')

# Check what pair formats are accepted
print('---Spot pair format---')
binance2 = s.get_connector_settings().get('binance')
if binance2:
    try:
        inst3 = binance2.non_trading_connector_instance_with_default_configuration(trading_pairs=['BTCB-USDT'])
        print(f'BTCB-USDT: OK')
    except Exception as e:
        print(f'BTCB-USDT Error: {e}')
