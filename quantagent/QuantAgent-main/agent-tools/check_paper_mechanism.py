from hummingbot.connector.exchange.paper_trade import create_paper_trade_market, PaperTradeExchange

# What does paper_trade_exchanges actually do?
# It should wrap connectors listed there in PaperTradeExchange
# Let's see how the strategy uses it

# The key question: if I add binance_perpetual to paper_trade_exchanges,
# does the connector_manager wrap it automatically?

# Check if there's a config that enables paper for binance_perpetual
from hummingbot.client.settings import AllConnectorSettings
s = AllConnectorSettings()
bp = s.get_connector_settings().get('binance_perpetual')

# Check the connector's config class
import inspect
cls = type(bp)
print(f'Connector settings class: {cls.__name__}')
print(f'Module: {cls.__module__}')

# Check if there's a paper_trade setting
try:
    from hummingbot.client.config.client_config_map import ClientConfigMap
    ccfg = ClientConfigMap()
    pt = getattr(ccfg, 'paper_trade', None)
    if pt:
        print(f'paper_trade config: {pt}')
        exchanges = getattr(pt, 'paper_trade_exchanges', None)
        print(f'paper_trade_exchanges: {exchanges}')
except Exception as e:
    print(f'Error: {e}')

# Test: can we create binance_perpetual as paper trade market?
try:
    mkt = create_paper_trade_market('binance_perpetual', ['BTC-USDT'])
    print(f'\ncreate_paper_trade_market(binance_perpetual) -> {type(mkt).__name__}')
    print(f'  .name = {mkt.name}')
    print(f'  .trade_types = {mkt.trade_types}')
except Exception as e:
    print(f'Error: {e}')
