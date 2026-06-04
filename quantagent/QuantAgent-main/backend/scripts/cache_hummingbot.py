"""Add response caching to hummingbot endpoints."""
import re

path = '/app/app/api/v1/endpoints/hummingbot.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

endpoints = ['docker', 'connectors', 'portfolio', 'bots', 'orders', 'positions']

for ep_name in endpoints:
    cache_key = f"hb_{ep_name}"

    # Find function start
    func_start = content.find(f"async def get_{ep_name}():")
    if func_start == -1:
        print(f"{ep_name}: NOT FOUND")
        continue

    # Find next function/class/route
    next_func = len(content)
    for marker in ['\nasync def ', '\n@router.get', '\n@router.post', '\nclass ', '\ndef ']:
        idx = content.find(marker, func_start + 1)
        if idx != -1 and idx < next_func:
            next_func = idx

    func_body = content[func_start:next_func]

    # Replace return make_response -> result = make_response
    modified = func_body.replace('return make_response(connected=', 'result = make_response(connected=')

    # Find where to insert cache_set and return (before the function closing)
    # Find the last 'result = make_response' and add cache + return after it
    last_result = modified.rfind('result = make_response(')
    if last_result == -1:
        print(f"{ep_name}: no result assignment found, skipping")
        continue

    # Find matching closing paren
    paren_count = 0
    end_pos = last_result
    for i in range(last_result, len(modified)):
        c = modified[i]
        if c == '(':
            paren_count += 1
        elif c == ')':
            paren_count -= 1
            if paren_count == 0:
                end_pos = i + 1
                break

    # Insert cache_set after the last result assignment, add return
    before = modified[:end_pos]
    after = modified[end_pos:]
    modified = before + "\n" + f'    _cache_set("{cache_key}", result)\n    return result' + after

    content = content[:func_start] + modified + content[next_func:]
    print(f"{ep_name}: DONE")

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("\nAll done! Restart backend to apply.")
