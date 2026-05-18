import os
# Search for any perpetual paper connector in hummingbot package
for base in ['/opt/conda/envs/hummingbot-api/lib/python3.12/site-packages/hummingbot',
             '/opt/conda/envs/hummingbot/lib/python3.13/site-packages/hummingbot']:
    for root, dirs, files in os.walk(base):
        for f in files:
            if f.endswith('.py'):
                full = os.path.join(root, f)
                try:
                    with open(full) as fh:
                        content = fh.read()
                    if 'paper_trade' in content.lower() and ('perpetual' in content.lower() or 'futures' in content.lower()):
                        print(f'{full}: has paper + perpetual')
                except:
                    pass
