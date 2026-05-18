from hummingbot.connector.exchange.paper_trade import create_paper_trade_market
from hummingbot.connector.exchange.paper_trade.paper_trade_exchange import PaperTradeExchange

# Test creating paper market for binance_perpetual
try:
    mkt = create_paper_trade_market('binance_perpetual', ['BTC-USDT'])
    print(f'Type: {type(mkt).__name__}')
    print(f'Is PaperTradeExchange: {isinstance(mkt, PaperTradeExchange)}')
    print(f'Wrapped: {type(mkt._connector).__name__}')
    print(f'NAME: {mkt.name}')
    print(f'Requires API key: check - {mkt.name}')
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()

# Check what the connector init needs
from hummingbot.connector.exchange.paper_trade import get_connector_class
cls = get_connector_class('binance_perpetual')
print(f'\nConnector class for binance_perpetual: {cls}')
