from hummingbot.client.settings import AllConnectorSettings
s = AllConnectorSettings()
for name in ['binance_perpetual', 'binance_perpetual_testnet', 'binance']:
    inst = s.get_connector_settings().get(name)
    if inst:
        has_method = hasattr(inst, 'non_trading_connector_instance_with_default_configuration')
        print(f'{name}: has_non_trading={has_method}')
        try:
            i = inst.non_trading_connector_instance_with_default_configuration(trading_pairs=['BTC-USDT'])
            print(f'  Instance OK: {type(i).__name__}')
        except Exception as e:
            print(f'  Error: {e}')
