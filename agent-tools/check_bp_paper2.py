from hummingbot.connector.exchange.paper_trade import create_paper_trade_market
# Try creating a paper trade market for binance_perpetual
try:
    mkt = create_paper_trade_market('binance_perpetual', ['BTC-USDT'])
    print(f'PaperTrade market created: {type(mkt).__name__}')
    print(f'Wrapped connector: {type(mkt._connector).__name__}')
except Exception as e:
    print(f'Error creating paper market: {e}')

# Check if binance connector is available as paper
try:
    mkt2 = create_paper_trade_market('binance', ['BTCB-USDT'])
    print(f'Spot paper market: {type(mkt2).__name__}')
except Exception as e:
    print(f'Spot error: {e}')
