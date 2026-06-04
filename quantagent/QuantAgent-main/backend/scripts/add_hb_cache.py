"""Add 15s in-memory cache to hummingbot GET endpoints."""
import re

path = '/app/app/api/v1/endpoints/hummingbot.py'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# ---- Step 1: Add time import ----
if 'import time' not in content.split('\n')[:45]:
    content = content.replace(
        'from fastapi import APIRouter, HTTPException, Request',
        'from fastapi import APIRouter, HTTPException, Request\nimport time',
    )

# ---- Step 2: Add cache globals and helpers after APIRouter() ----
cache_code = '''
# ---- request cache (15s TTL) ----
_hb_cache: dict = {}
_HB_CACHE_TTL = 15.0

def _hb_get(key: str) -> dict | None:
    e = _hb_cache.get(key)
    if e and (time.monotonic() - e[0]) < _HB_CACHE_TTL:
        return e[1]
    return None

def _hb_set(key: str, data: dict) -> None:
    _hb_cache[key] = (time.monotonic(), data)
'''

if 'def _hb_get' not in content:
    content = content.replace(
        'router = APIRouter()',
        'router = APIRouter()' + cache_code,
    )

# ---- Step 3: For each hummingbot GET endpoint, transform:
#   async def get_xxx():
#       try:
#           ...
#           return make_response(...)
#       except ...:
#           return make_response(...)
#
# into:
#   async def get_xxx():
#       c = _hb_get("hb_xxx")
#       if c: return c
#       try:
#           ...
#           r = make_response(...)
#       except ...:
#           r = make_response(...)
#       _hb_set("hb_xxx", r)
#       return r
# ----

endpoints = {
    'status':     'hb_status',
    'docker':     'hb_docker',
    'connectors': 'hb_connectors',
    'portfolio':  'hb_portfolio',
    'bots':       'hb_bots',
    'orders':     'hb_orders',
    'positions':  'hb_positions',
}

for ep_name, cache_key in endpoints.items():
    # Find function
    marker = f'async def get_{ep_name}():'
    func_start = content.find(marker)
    if func_start == -1:
        print(f'{ep_name}: SKIP (not found)')
        continue

    # Find function body start (first non-blank line after docstring)
    # Find the end of the function (next async def or @router or class)
    next_idx = len(content)
    for pat in ['\nasync def ', '\n@router.', '\nclass ', '\ndef ', '\n# ----']:
        i = content.find(pat, func_start + len(marker))
        if i != -1 and i < next_idx:
            next_idx = i

    func_body = content[func_start:next_idx]

    # Skip if already cached
    if '_hb_get' in func_body:
        print(f'{ep_name}: already cached')
        continue

    # Add cache check after docstring
    # Find the '''docstring''' or """docstring""" and add after it
    doc_end = 0
    for q in ["'''", '"""']:
        first = func_body.find(q)
        if first != -1:
            second = func_body.find(q, first + 3)
            if second != -1:
                doc_end = second + 3
                break

    if doc_end == 0:
        # Try to find after function signature line
        doc_end = func_body.find('\n') + 1

    before = func_body[:doc_end]
    after = func_body[doc_end:]

    cache_check = f'\n    c = _hb_get("{cache_key}")\n    if c:\n        return c\n'
    modified = before + cache_check + after

    # Replace 'return make_response' with 'r = make_response'
    modified = modified.replace('return make_response(connected=', 'r = make_response(connected=')

    # Add _hb_set + return r before function closing
    # Find the last 'r = make_response' or last 'except' block
    # Simpler: replace the function's last line(s) to add cache set + return
    modified = modified.rstrip()
    if not modified.endswith('return r'):
        # Add cache set + return at very end
        modified += f'\n    _hb_set("{cache_key}", r)\n    return r'

    content = content[:func_start] + modified + content[next_idx:]
    print(f'{ep_name}: cached')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print('\nDone!')
