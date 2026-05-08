from hummingbot.connector.exchange.binance.binance_perpetual import BinancePerpetualExchange
from hummingbot.client.settings import AllConnectorSettings

s = AllConnectorSettings()
bp = s.get_connector_settings().get('binance_perpetual')

# Create a non-trading instance
inst = bp.non_trading_connector_instance_with_default_configuration(trading_pairs=['BTC-USDT'])
print(f'Connector: {type(inst).__name__}')
print(f'Trading pair: BTC-USDT')

# Check what credentials it needs
from hummingbot.client.config.security import Security
from hummingbot.client.config.client_config_map import ClientConfigMap

# Check paper_trade_exchanges setting
print(f'Is paper trade?: {inst.name}')

# Check what happens when we call restore_trading_rules
# The key question: does binance_perpetual work without API keys?
print(f'API key required: {inst.name}')
