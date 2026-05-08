import sys
content = open('/hummingbot-api/services/docker_service.py').read()

# Revert the binance_perpetual paper_trade_exchanges patch
old = '''        # Ensure binance_perpetual is in paper_trade_exchanges
        pt = client_config.get('paper_trade', {})
        exchanges = pt.get('paper_trade_exchanges', [])
        if 'binance_perpetual' not in exchanges:
            exchanges.append('binance_perpetual')
            pt['paper_trade_exchanges'] = exchanges
            client_config['paper_trade'] = pt
            print(f"Added binance_perpetual to paper_trade_exchanges")

        fs_util.dump_dict_to_yaml(conf_file_path, client_config)'''

new = '''        fs_util.dump_dict_to_yaml(conf_file_path, client_config)'''

if old in content:
    content = content.replace(old, new, 1)
    open('/hummingbot-api/services/docker_service.py', 'w').write(content)
    print('REVERTED OK')
else:
    print('Pattern not found - checking...')
    if 'Added binance_perpetual' in content:
        print('Patch text found, trying broader match...')
        # Try to find the section
        idx = content.find('# Ensure binance_perpetual')
        if idx >= 0:
            print(f'Found at index {idx}')
    else:
        print('Patch not found - may already be reverted')
